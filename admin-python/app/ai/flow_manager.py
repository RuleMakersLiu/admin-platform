"""完整开发流水线引擎

具备自治能力：
  - 自动阶段推进（迭代循环，非递归）
  - Code Review 失败自动回退开发阶段修复
  - 测试失败自动触发 Bug 修复循环
  - LLM 调用自动重试（指数退避）
  - AgentMemory 记忆集成
  - 数据库持久化
"""
import json
import uuid
import asyncio
import logging
import os
import re
import time
from datetime import datetime
from enum import Enum
from typing import Awaitable, Callable, AsyncGenerator, Dict, List, Optional, Any, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents import AgentService
from app.ai import backend_scaffold  # noqa: F401  (注册 backend_scaffolder skill)
from app.ai.pipeline_skills import ensure_workspace, get_workspace_path
from app.ai.skills import SkillStatus, skill_registry
from app.ai.model_router import pipeline_context
from app.models.agent_models import DevPipeline, ProjectKnowledge
from app.services.memory_service import MemoryService, MemoryType
from app.services.user_evolution_service import UserEvolutionService
from app.core.database import async_session_maker

logger = logging.getLogger(__name__)

MAX_FIX_ITERATIONS = 3
MAX_PREVIEW_GENERATION_ATTEMPTS = 3
MAX_LLM_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds
LLM_STAGE_TIMEOUT = 600  # 单阶段 LLM 调用最大超时（秒）
LLM_STREAM_IDLE_TIMEOUT = 45  # seconds without stream chunks before fallback
LLM_FINAL_REPLY_TIMEOUT = 90  # seconds to wait for non-stream fallback reply

# 子智能体评审关卡（步骤 2/3/5）：顺序阶段的产物经 LLM-as-judge 评审；不过则带意见
# 重生成，重试 MAX_FIX_ITERATIONS 次仍不过 → 交人工。backend_dev 走 fan-out（非顺序），
# 其"3次→人工"由下游 code_review 修复循环兜底（耗尽已改 escalate）。
REVIEW_GATE_PASS_SCORE = 60
REVIEW_GATE_CRITERIA: Dict[str, List[str]] = {
    "requirement": [
        "需求描述清晰、可执行，无歧义",
        "覆盖了用户提出的核心功能点",
        "无明显矛盾、遗漏或不合理假设",
    ],
    "delivery": [
        "API 契约完整：每个接口含路径、方法、请求字段、响应字段",
        "前后端字段命名与类型对齐",
        "覆盖需求中的核心交互与数据流",
    ],
}


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_CONFIRM = "waiting_confirm"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    # 某阶段重试耗尽，暂停等人工修改/确认（非终态：不写 eval；重启后自然存活）
    NEEDS_HUMAN = "needs_human"


async def recover_stale_running_pipelines() -> int:
    """Mark running pipelines from a previous process as failed on startup."""
    from sqlalchemy import text

    stale_error = "服务重启后上一轮执行已中断，请重新执行当前阶段。"
    async with async_session_maker() as session:
        result = await session.execute(
            text(
                """
                UPDATE dev_pipeline
                SET
                  status = 'failed',
                  stages_data = CASE
                    WHEN stages_data IS NOT NULL AND current_stage IS NOT NULL THEN
                      jsonb_set(
                        jsonb_set(
                          jsonb_set(
                            stages_data::jsonb,
                            ARRAY[current_stage, 'status'],
                            to_jsonb('failed'::text),
                            true
                          ),
                          ARRAY[current_stage, 'error'],
                          to_jsonb(CAST(:stale_error AS text)),
                          true
                        ),
                        ARRAY[current_stage, 'completed_at'],
                        to_jsonb(to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS.MS')),
                        true
                      )::text
                    ELSE stages_data
                  END,
                  update_time = (extract(epoch from now()) * 1000)::bigint
                WHERE status = 'running' AND is_deleted = 0
                """
            ),
            {"stale_error": stale_error},
        )
        await session.commit()
        return result.rowcount or 0


STAGE_DEFINITIONS = [
    # 产品设计流程
    {"key": "requirement",    "name": "需求分析",   "agent": "PM",  "need_confirm": True},
    {"key": "page_design",    "name": "页面设计",   "agent": "PM",  "need_confirm": True},
    {"key": "prototype",      "name": "前端预览代码", "agent": "FE",  "need_confirm": True},
    {"key": "delivery",       "name": "交付包",     "agent": "PJM", "need_confirm": True},
    # 开发流程
    {"key": "frontend_dev",   "name": "前端开发",   "agent": "FE",  "need_confirm": True},
    {"key": "backend_dev",    "name": "后端开发",   "agent": "BE",  "need_confirm": True},
    {"key": "code_review",    "name": "代码审查",   "agent": "QA",  "need_confirm": True},
    {"key": "testing",        "name": "自动化测试", "agent": "QA",  "need_confirm": False},
    {"key": "commit",         "name": "代码提交",   "agent": "PJM", "need_confirm": False},
    {"key": "deploy",         "name": "部署发布",   "agent": "PJM", "need_confirm": False},
    {"key": "eval",           "name": "自动测评",   "agent": "QA",  "need_confirm": False},
    {"key": "report",         "name": "总结报告",   "agent": "RPT", "need_confirm": False},
]

STAGE_KEYS = [s["key"] for s in STAGE_DEFINITIONS]
STAGE_NAMES = {s["key"]: s["name"] for s in STAGE_DEFINITIONS}
PIPELINE_MODE_STAGES = {
    "full": STAGE_KEYS,
    "frontend_contract_review": [
        "requirement",
        "page_design",
        "prototype",
        "delivery",
        "code_review",
        "report",
    ],
}


def _get_stage_agent(stage_key: str) -> str:
    for s in STAGE_DEFINITIONS:
        if s["key"] == stage_key:
            return s["agent"]
    return "PM"


def _stage_needs_confirm(stage_key: str) -> bool:
    for s in STAGE_DEFINITIONS:
        if s["key"] == stage_key:
            return s["need_confirm"]
    return False


def _build_code_review_fix_feedback(
    parsed: Dict[str, Any], raw_output: str
) -> Tuple[str, str]:
    """Build code-review failure feedback from a failed review result.

    Returns (mismatch_feedback, fix_feedback). mismatch_feedback is returned
    separately because the caller reuses it both inside fix_feedback and as a
    repair-issue entry. Pure function — no side effects.
    """
    mismatch_feedback = ""
    field_mismatches = parsed.get("field_mismatches")
    if isinstance(field_mismatches, list) and field_mismatches:
        mismatch_feedback = "\n".join(
            "- "
            + "，".join(
                str(part)
                for part in (
                    item.get("severity"),
                    item.get("location"),
                    f"当前: {item.get('frontend_field')}" if item.get("frontend_field") else "",
                    f"应为: {item.get('contract_field')}" if item.get("contract_field") else "",
                    item.get("fix"),
                )
                if part
            )
            for item in field_mismatches
            if isinstance(item, dict)
        )
    fix_feedback = "\n".join(
        part.strip()
        for part in (
            "自动审查未通过，请只修复审查指出的问题，生成完整可运行代码。",
            parsed.get("contract_alignment", ""),
            mismatch_feedback,
            parsed.get("fix_suggestions", ""),
            "必须保留现有页面、现有接口、现有查询条件和现有表格列；只做本次需求的增量改造。",
            raw_output[:500] if not parsed.get("fix_suggestions") else "",
        )
        if part and str(part).strip()
    )
    return mismatch_feedback, fix_feedback


def _should_pause_for_stage(stage_key: str, auto_review_fix_active: bool = False) -> bool:
    if not _stage_needs_confirm(stage_key):
        return False
    # Code-review self-repair is an internal loop. After a failed review, the
    # regenerated prototype and delivery contract must flow straight into the
    # next review; otherwise the pipeline appears stuck before it can re-check.
    if auto_review_fix_active and stage_key != "code_review":
        return False
    return True


def _stage_keys_for_mode(pipeline_mode: str = "full") -> List[str]:
    return PIPELINE_MODE_STAGES.get(pipeline_mode or "full", STAGE_KEYS)


def _fix_loop_stage_for_mode(stage_keys: List[str]) -> str:
    if "frontend_dev" in stage_keys:
        return "frontend_dev"
    if "prototype" in stage_keys:
        return "prototype"
    return stage_keys[0] if stage_keys else ""


def _has_code_review_fix_loop(stage_keys: List[str]) -> bool:
    return bool(_fix_loop_stage_for_mode(stage_keys))


def _is_product_preview_code_stage(stage_key: str, pipe_config: Dict[str, Any]) -> bool:
    return stage_key == "prototype" and pipe_config.get("pipeline_mode") == "frontend_contract_review"


def _is_product_pm_design_stage(stage_key: str, pipe_config: Dict[str, Any]) -> bool:
    return stage_key == "page_design" and pipe_config.get("pipeline_mode") == "frontend_contract_review"


def _compact_context(text: str, limit: int = 4000) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[context truncated]"


def _compact_fix_feedback(text: str, limit: int = 1800) -> str:
    text = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    if len(text) <= limit:
        return text

    priority_lines: List[str] = []
    markers = (
        "自动审查未通过",
        "审查结论",
        "需修复",
        "当前:",
        "应为:",
        "critical",
        "major",
        "修复建议",
        "必须保留",
        "目标",
        "路径",
        "queryParam",
        "field_mismatches",
    )
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and any(marker in stripped for marker in markers):
            priority_lines.append(stripped)
    summary = "\n".join(priority_lines) or text
    return summary[:limit] + "\n...[fix feedback compressed]"


def _build_auto_repair_summary(
    retry_count: int,
    repaired_stage: str,
    fix_feedback: str,
    stage_auto_fixes: Optional[List[str]] = None,
) -> str:
    """Build a user-readable summary after code-review self-repair succeeds."""
    feedback = _compact_fix_feedback(fix_feedback, 1200)
    feedback_lines = [
        line.strip().lstrip("-* ")
        for line in feedback.splitlines()
        if line.strip()
    ][:10]
    auto_fix_lines = [
        str(line).strip()
        for line in (stage_auto_fixes or [])
        if str(line).strip()
    ][:10]

    parts = [
        f"自动审查发现问题后，系统已自动回到 {STAGE_NAMES.get(repaired_stage, repaired_stage)} 修复。",
        f"修复轮次：{retry_count}",
    ]
    if feedback_lines:
        parts.append("修复依据：")
        parts.extend(f"- {line}" for line in feedback_lines)
    if auto_fix_lines:
        parts.append("代码自动修正：")
        parts.extend(f"- {line}" for line in auto_fix_lines)
    parts.append("修复后已重新执行自动审查，本轮审查通过。")
    return "\n".join(parts)


_PIPELINE_TEMP_DIR = ".pipeline-temp"
_REPAIR_TEMP_DIR = f"{_PIPELINE_TEMP_DIR}/repairs"


def _split_repair_values(text: str) -> List[str]:
    values = []
    for part in re.split(r"、|，|；|,|;", text or ""):
        cleaned = part.strip().strip("。.")
        if cleaned:
            values.append(cleaned)
    return values


def _build_repair_tasks_from_issues(issues: List[str]) -> List[Dict[str, Any]]:
    """Split review issues into small repair tasks that can be tracked independently."""
    tasks: List[Dict[str, Any]] = []

    def add_task(category: str, title: str, detail: str, target: str = "") -> None:
        sequence = len(tasks) + 1
        tasks.append({
            "id": f"{category}-{sequence}",
            "category": category,
            "title": title,
            "target": target,
            "detail": detail,
            "status": "pending",
        })

    for issue in issues or []:
        text = str(issue or "").strip()
        if not text:
            continue

        if "ApiResult" in text or "扁平 code/message/msg" in text:
            target_match = re.match(r"(.+?) 的 mock/API 响应", text)
            target = target_match.group(1) if target_match else ""
            add_task("api_response_envelope", "修复接口响应包装格式", text, target)
            continue

        api_match = re.search(r"API 模块未覆盖：(.+)", text)
        if api_match:
            for endpoint in _split_repair_values(api_match.group(1)):
                add_task("api_contract", f"补齐接口覆盖 {endpoint}", text, endpoint)
            continue

        action_match = re.search(r"新增/创建入口，但前端页面未体现：(.+)", text)
        if action_match:
            for action in _split_repair_values(action_match.group(1)):
                add_task("action_coverage", f"补齐页面操作入口 {action}", text, action)
            continue

        component_match = re.search(r"页面设计要求使用项目组件，但前端页面未体现：(.+)", text)
        if component_match:
            for component in _split_repair_values(component_match.group(1)):
                add_task("component_usage", f"补齐项目组件 {component}", text, component)
            continue

        page_match = re.search(r"主页面[“\"](.+?)[”\"]没有对应的前端页面文件", text)
        if page_match:
            page_name = page_match.group(1)
            add_task("page_file", f"补齐页面文件：{page_name}", text, page_name)
            continue

        pagination_match = re.search(r"(.+?) 使用 STable 时必须处理分页字段 (page|count)", text)
        if pagination_match:
            target = f"{pagination_match.group(1)}#{pagination_match.group(2)}"
            add_task("table_pagination", f"补齐表格分页字段 {pagination_match.group(2)}", text, target)
            continue

        list_match = re.search(r"(.+?) 使用 STable 时必须处理分页对象 list 字段", text)
        if list_match:
            add_task("table_pagination", "补齐表格分页 list 字段", text, f"{list_match.group(1)}#list")
            continue

        array_guard_match = re.search(r"(.+?) 访问数组前缺少默认空数组兜底", text)
        if array_guard_match:
            add_task("runtime_guard", "补齐数组默认值兜底", text, array_guard_match.group(1))
            continue

        pagination_interaction_match = re.search(r"(.+?) 的 mock 分页没有按 pageNo/pageSize 切换数据", text)
        if pagination_interaction_match:
            add_task("pagination_interaction", "修复 mock 翻页数据切换", text, pagination_interaction_match.group(1))
            continue

        add_task("other", "修复预览审查问题", text)

    return tasks


_REPAIR_CATEGORY_LABELS = {
    "api_response_envelope": "接口响应格式",
    "api_contract": "接口覆盖",
    "component_usage": "项目组件使用",
    "page_file": "页面文件完整性",
    "table_pagination": "表格分页适配",
    "pagination_interaction": "分页交互",
    "action_coverage": "按钮操作覆盖",
    "runtime_guard": "首屏运行兜底",
    "other": "其他预览问题",
}


def _build_repair_task_feedback(tasks: List[Dict[str, Any]], issues: List[str]) -> str:
    if not tasks:
        return "\n".join(f"- {issue}" for issue in issues[:12])

    lines = [
        "上一版前端预览代码没有通过检查。请按下面的修复任务逐项处理，禁止整体换业务方向或减少页面数量。",
        "修复原则：一次只围绕清单中的功能点补齐；保留已正确的代码；最终输出仍然必须是完整 JSON 文件数组。",
        "",
        "## 修复任务清单",
    ]
    for index, task in enumerate(tasks[:12], 1):
        label = _REPAIR_CATEGORY_LABELS.get(task.get("category"), task.get("category") or "修复项")
        target = f"（目标：{task.get('target')}）" if task.get("target") else ""
        lines.append(f"{index}. [{label}] {task.get('title')}{target}")
    lines.extend([
        "",
        "## 必须满足",
        "- API/mock 响应如果项目要求 ApiResult，必须使用 { message: { code: 0, message: 'ok' }, traceId, data }，禁止扁平 { code, message, data }。",
        "- 页面设计声明的每个主页面都必须有对应前端页面文件。",
        "- 页面设计声明的接口必须在 API 模块中覆盖。",
        "- 页面设计要求的项目组件必须在页面中实际使用。",
        "- STable 的 loadData 必须返回 list、page、count；访问数组前必须做 [] 兜底。",
    ])
    return "\n".join(lines)


def _build_preview_failure_message(tasks: List[Dict[str, Any]], issues: List[str]) -> str:
    if not tasks:
        return "前端预览仍未通过检查，请重新生成当前阶段。"
    grouped: Dict[str, int] = {}
    for task in tasks:
        category = str(task.get("category") or "other")
        grouped[category] = grouped.get(category, 0) + 1
    summaries = [
        f"{_REPAIR_CATEGORY_LABELS.get(category, category)} {count} 项"
        for category, count in grouped.items()
    ]
    first_tasks = "；".join(str(task.get("title") or "") for task in tasks[:4] if task.get("title"))
    details = "；".join(str(issue) for issue in issues[:8])
    return (
        "前端预览仍未生成完整可运行页面。"
        f"当前剩余 {len(tasks)} 个修复点：{'、'.join(summaries)}。"
        f"优先处理：{first_tasks}。"
        f" 技术详情：{details}"
    )


def _repair_attempt_file_path(stage: str, attempt: int) -> str:
    safe_stage = re.sub(r"[^A-Za-z0-9_-]+", "-", stage or "unknown").strip("-") or "unknown"
    safe_attempt = max(1, int(attempt or 1))
    return f"{_REPAIR_TEMP_DIR}/{safe_stage}/attempt-{safe_attempt}.json"


async def _record_repair_attempt_temp_file(
    pipeline_id: str,
    stage: str,
    attempt: int,
    issues: List[str],
    feedback: str,
    source_stage: str = "",
) -> List[Dict[str, Any]]:
    tasks = _build_repair_tasks_from_issues(issues)
    payload = {
        "pipeline_id": pipeline_id,
        "source_stage": source_stage or stage,
        "repair_stage": stage,
        "attempt": max(1, int(attempt or 1)),
        "issues": [str(issue) for issue in issues or [] if str(issue).strip()],
        "tasks": tasks,
        "feedback": feedback or "",
        "created_at": datetime.now().isoformat(),
    }
    try:
        await skill_registry.execute(
            "file_writer",
            root_path=get_workspace_path(pipeline_id),
            files={
                _repair_attempt_file_path(stage, attempt): json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                )
            },
        )
    except Exception as exc:
        logger.warning("Failed to record repair temp file for %s/%s: %s", pipeline_id, stage, exc)
    return tasks


async def _cleanup_pipeline_temp_files(pipeline_id: str) -> None:
    try:
        await skill_registry.execute(
            "file_cleaner",
            root_path=get_workspace_path(pipeline_id),
            paths=[_PIPELINE_TEMP_DIR],
        )
    except Exception as exc:
        logger.warning("Failed to cleanup pipeline temp files for %s: %s", pipeline_id, exc)


async def _cleanup_temp_path(path: str) -> None:
    if not path:
        return
    root_path = os.path.dirname(path)
    basename = os.path.basename(path)
    if not root_path or not basename:
        return
    try:
        await skill_registry.execute(
            "file_cleaner",
            root_path=root_path,
            paths=[basename],
        )
    except Exception as exc:
        logger.warning("Failed to cleanup temp path %s: %s", path, exc)


def _init_stages_for_mode(pipeline_mode: str = "full") -> Dict[str, Any]:
    allowed = set(_stage_keys_for_mode(pipeline_mode))
    return {
        s["key"]: {
            "stage": s["key"],
            "agent_type": s["agent"],
            "status": "pending",
            "output": "",
            "structured_output": {},
            "preview_html": "",
            "code_files": {},
            "error": "",
            "started_at": None,
            "completed_at": None,
        }
        for s in STAGE_DEFINITIONS
        if s["key"] in allowed
    }


def _init_stages() -> Dict[str, Any]:
    return _init_stages_for_mode("full")


def _validate_project_skill_ready(project_skill: Dict[str, Any]) -> None:
    status = str(project_skill.get("skill_status") or "").lower()
    content = str(project_skill.get("skill_content") or "").strip()
    if status != "confirmed" or not content:
        raise ValueError("Project skill must be confirmed before creating this pipeline")


def _build_pipeline_skill_snapshot(project_skill: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "project_id": str(project_skill.get("project_id") or ""),
        "project_name": project_skill.get("project_name") or "",
        "repo_url": project_skill.get("repo_url") or "",
        "skill_content": project_skill.get("skill_content") or "",
        "project_analysis_schema": project_skill.get("project_analysis_schema") or "",
        "generation_contract": project_skill.get("generation_contract") or "",
        "verification_contract": project_skill.get("verification_contract") or "",
        "skill_version": project_skill.get("skill_version") or 1,
        "confirmed_at": project_skill.get("confirmed_at"),
    }


def _build_pipeline_artifact(stages: Dict[str, Any]) -> Dict[str, Any]:
    preview_stage = stages.get("prototype", {}) or stages.get("ui_preview", {})
    delivery_stage = stages.get("delivery", {})
    frontend_stage = stages.get("frontend_dev", {})
    review_stage = stages.get("code_review", {})
    review = {}
    if review_stage.get("status") == "completed":
        review = review_stage.get("structured_output") or {}
    if review_stage.get("status") == "completed" and not review:
        review = {"output": review_stage.get("output", "")}

    return {
        "preview_html": preview_stage.get("preview_html", ""),
        "preview_source": preview_stage.get("preview_html", "") or preview_stage.get("output", ""),
        "api_contract": delivery_stage.get("output", ""),
        "frontend_files": frontend_stage.get("code_files", {}) or preview_stage.get("code_files", {}) or {},
        "review": review,
        "review_status": review_stage.get("status", "pending"),
        "review_output": review_stage.get("output", "") if review_stage.get("status") == "completed" else "",
        "report": (stages.get("report", {}) or {}).get("output", ""),
    }


# ==================== 默认 Prompt 模板 ====================
# 可通过 API /flow/prompts/defaults 读取，支持项目级自定义覆盖

def _knowledge_to_project_skill_dict(project_skill: ProjectKnowledge) -> Dict[str, Any]:
    return {
        "project_id": project_skill.project_id,
        "project_name": project_skill.project_name,
        "repo_url": project_skill.repo_url or "",
        "skill_content": project_skill.skill_content or "",
        "project_analysis_schema": project_skill.project_analysis_schema or "",
        "generation_contract": project_skill.generation_contract or "",
        "verification_contract": project_skill.verification_contract or "",
        "skill_status": project_skill.skill_status or "",
        "skill_version": project_skill.skill_version or 1,
        "confirmed_at": project_skill.confirmed_at,
    }


PIPELINE_GLOBAL_PROMPT_CONTRACT = """

## 全局执行契约（所有阶段必须遵守）
1. 事实边界：只能基于用户需求、已匹配 Project Skill、项目代码参考、上游阶段产物和明确修复反馈推理；不确定的信息必须写入“假设/待确认”，禁止伪造接口、字段、组件、权限或外部事实。
2. 范围边界：只处理当前阶段职责，不提前替代后续阶段，也不遗漏当前阶段必须交付的内容；如果当前阶段输出格式有特殊要求，以当前阶段“输出格式/输出要求”为最高优先级。
3. 逻辑边界：每个结论都要能追溯到业务目标、页面行为、数据字段、权限策略或接口契约；前端字段、mock 字段、API 字段、后端字段必须保持同名同义同类型。
4. 异常边界：必须覆盖空数据、加载中、无权限、接口失败、重复提交、并发操作、数据越权、输入非法、分页越界、状态流转非法等边界。
5. 项目边界：优先复用匹配项目的目录结构、组件、API 封装、权限约定、响应模型和命名风格；不知道是否存在的组件/工具不要引用。
6. 输出边界：不要寒暄，不要解释自己如何工作；不要输出与当前阶段无关的散文。Markdown 阶段直接输出文档；JSON 阶段必须输出可解析 JSON；代码阶段必须给完整文件内容。
7. 自检要求：输出前检查是否满足当前阶段清单、是否存在字段不一致、是否遗漏权限/异常/验收标准、是否有不可执行或不可验证内容。
8. 文件上下文边界：涉及文件审查、比对、搜索或读取时，优先按 workspace_path 和相对路径使用文件搜索/文件读取 skill；prompt 中只传文件清单、路径、行数和关键符号摘要，避免粘贴完整文件正文。
9. 多轮修复边界：重新生成或自动修复只携带压缩后的失败摘要、字段差异、目标文件路径和必要契约；禁止反复粘贴历史完整源码、完整日志或完整产物，防止上下文膨胀造成误判。
"""


DEFAULT_STAGE_PROMPTS: Dict[str, str] = {
    "requirement": """请根据以下用户需求，生成一份完整、可交付、可评审的需求文档(PRD)。

用户需求:
{{user_request}}

## 已识别项目
- 前端项目: {{frontend_project_name}}
- 前端技术栈: {{frontend_tech}}
- 后端项目: {{backend_project_name}}
- 后端技术栈: {{backend_tech}}

## 参考项目
如果上方有「Confirmed Frontend Project Skill Snapshot」「Confirmed Backend/API Project Skill Snapshot」「前端项目代码参考」或「后端项目代码参考」，请同时结合前端和后端项目的现有架构、字段、组件、接口规范来撰写需求，保持与项目一致的技术风格。

## PRD 输出边界
- 只描述本需求相关范围；明确“不做范围”和“暂不支持范围”。
- 不把技术实现细节写成业务事实；不确定内容进入“假设与待确认问题”。
- 需求必须能被页面设计、API 契约和 QA 测试直接消费。

## 需求分析执行步骤
必须按下面顺序完成分析，并把每一步的结论写进 PRD 对应章节：
1. 输入盘点：逐条识别用户原始诉求、已匹配前端项目、已匹配后端项目、可用项目约束和缺失信息；如果前后端项目为空或不确定，写入待确认。
2. 业务目标拆解：把用户一句话需求拆成业务目标、目标角色、使用场景、成功结果和不做范围；不要把实现方案当成业务目标。
3. 功能点拆分：按 P0/P1/P2/P3 拆成独立功能点；每个功能点必须写清触发入口、前置条件、输入、处理规则、输出、失败反馈。
4. 流程建模：为主流程、异常流程、取消/回退、失败重试、状态流转分别给出步骤；每一步写清操作者、系统动作、数据变化和下一状态。
5. 数据建模：从功能点中提取数据对象和字段；逐字段确认类型、必填、默认值、枚举、校验、脱敏、审计、是否来自既有接口或新增接口。
6. 权限建模：按菜单/页面/按钮/API/数据范围拆权限；每个权限点写清角色、资源、动作、条件、拒绝态、隐藏/禁用策略和审计要求。
7. 边界与风险排查：逐项覆盖空数据、加载中、无权限、接口失败、重复提交、并发操作、数据越权、输入非法、分页越界和状态非法。
8. 验收标准落地：把每个 P0/P1 功能转换成可测试的验收标准；每条验收标准必须包含场景、操作、预期结果和可验证数据。
9. 待确认收口：只把影响设计/开发/测试继续执行的信息列入待确认，并说明如果不确认时采用的临时假设。

直接输出 Markdown 格式的 PRD 文档（不要用代码块包裹），不要写任何寒暄、开场白或解释，直接从标题开始。必须包含:
1. 项目概述：业务目标、目标用户、使用场景；必须分别写明前端参考项目和后端参考项目。
2. 范围边界：本次做什么、不做什么、依赖什么、有哪些外部系统或上游数据。
3. 功能需求列表：按 P0/P1/P2/P3 标注优先级，每项写清触发条件、输入、处理规则、输出结果。
4. 用户故事与业务流程：主流程、异常流程、状态流转、失败重试和取消/回退。
5. 数据对象与字段：字段名、类型、是否必填、默认值、枚举、校验、脱敏/审计要求。
6. 权限与数据范围：角色、页面权限、按钮权限、API 权限、数据范围、越权处理。
7. 非功能需求：性能、并发、可用性、安全、兼容性、可观测性。
8. 验收标准：每条都必须可测试，覆盖正常路径、边界路径、权限路径和异常路径。
9. 假设与待确认问题：列出需要产品/前后端/测试确认的事项。""",

    "page_design": """基于以下需求文档，进行详细、边界清晰、可直接开发的页面设计。

## 已识别项目
- 前端项目: {{frontend_project_name}}
- 前端技术栈: {{frontend_tech}}
- 后端项目: {{backend_project_name}}
- 后端技术栈: {{backend_tech}}

## 需求文档
{{requirement_output}}

## 页面设计边界
- 页面设计必须忠实承接 PRD，不新增无来源功能，不遗漏 P0/P1 功能。
- 每个页面都要写清入口、路由、默认状态、退出/返回路径。
- 所有字段必须与数据对象/API 契约候选保持一致；如果命名待定，显式标注待确认。

## 页面设计执行步骤
必须按下面顺序完成设计，并把每一步的结论写进页面设计对应章节：
1. PRD 对齐：先摘出 PRD 中的 P0/P1 功能、角色权限、数据对象、验收标准和待确认项；页面设计不得跳过这些输入。
2. 页面拆分：按用户任务链路拆主页面、详情页、创建/编辑页、弹窗/抽屉和辅助页面；每个页面写清为什么需要、由哪个功能点驱动。
3. 入口与路由设计：为每个页面确定菜单入口、路由路径、路由参数、默认落点、面包屑、返回路径和跨页面跳转条件。
4. 布局分区：按首屏优先级拆顶部筛选区、主内容区、批量操作区、行操作区、详情区、表单区和反馈区；写清每个区域展示什么。
5. 字段落表：逐页面列出搜索字段、表格列、详情字段、表单字段、隐藏字段和提交字段；每个字段写清展示名、字段 key、类型、来源、校验、格式化。
6. 交互流程细化：逐按钮/操作写清启用条件、点击后动作、二次确认、提交参数、成功反馈、失败反馈、刷新范围和是否防重复提交。
7. 状态矩阵设计：每个页面都要覆盖默认、加载中、空数据、搜索无结果、无权限、接口异常、提交中、提交失败、脏数据离开确认。
8. 权限与数据范围落点：把 PRD 权限点映射到菜单、路由、按钮、行操作、API 和数据范围；写清 permission key、隐藏/禁用/提示、审计点。
9. API 契约草案：按页面和操作列出接口方法、路径建议、请求参数、响应字段、分页结构、错误码和 mock/真实接口边界。
10. 开发确认清单：输出前检查页面清单是否覆盖 P0/P1、字段是否同名同义、状态是否完整、权限是否落点明确、API 是否足够支撑原型和开发。

请直接输出 Markdown 格式的页面设计文档（不要用代码块包裹），必须包含:
1. 页面清单及层级关系：菜单入口、路由、默认落点、面包屑、跨页面跳转。
2. 页面布局：区域划分、首屏信息优先级、表格/详情/表单/看板/配置页形态。
3. 字段定义：字段名、展示名、类型、是否必填、默认值、枚举、校验规则、格式化方式。
4. 查询与筛选：搜索项、默认筛选、重置逻辑、分页、排序、导出边界。
5. 按钮和操作：新增、编辑、删除、批量、导入导出、启停、审批、回退等操作的启用条件和二次确认。
6. 弹窗/抽屉/表单交互：打开来源、字段、校验、提交参数、成功/失败反馈、关闭策略。
7. 页面状态矩阵：空数据、加载中、无权限、搜索无结果、接口异常、提交中、重复提交、脏数据确认。
8. 权限控制点：菜单/页面/按钮/API/数据范围 permission key、展示策略、禁用/隐藏/无权限提示、审计点。
9. API 契约草案：每个页面列出需要的接口、方法、参数、响应字段和错误场景。
10. 开发确认要点：前端组件、后端接口、权限 key、字段命名、数据范围和性能边界。""",

    "prototype": """根据需求文档和页面设计，直接生成可写入匹配前端项目的前端预览代码。

## 需求文档
{{requirement_output}}

## 页面设计
{{page_design_output}}

## 本次预览页面范围
{{prototype_focus}}

## 前端技术栈
{{frontend_tech}}

## 用户需求
{{user_request}}

## 重要：参考项目
结合 Frontend Project Skill，优先复用现有项目的目录、组件库、路由、API 封装、权限判断、表格/表单模式和样式规范。不要展开解释。
如果没有匹配到前端项目或 Project Skill 信息不足，不要生成独立 demo 页面，应该让本阶段失败并说明缺少匹配项目依据。
如果「前端项目关键文件参考」里提供了「与本需求相关的已确认前端页面路径」，这些路径是判断现有功能的唯一可信依据；不要选择无关业务页面。

## 生成目标
本阶段就是前端代码生成阶段，不再有后续单独的“前端开发”阶段。产物会直接覆盖到匹配前端项目的沙箱副本中，并通过该项目自己的 npm 脚本启动预览。
你生成的是“对匹配前端项目的增量文件修改”，不是创建一个新项目、独立页面、独立演示系统或脱离项目的 demo。

## 产品经理验收目标
产品经理不关心代码结构细节，只关心一个结果：点击“启动真实前端预览”后，能打开一个与需求匹配、首屏不报错、按钮能点、列表/详情/表单状态完整的可用页面。
如果页面设计列出了多个主页面，prototype 必须交付完整页面集，而不是只生成其中 1 个页面。每个主页面都要有真实前端页面文件；共用 API/mock/service 可以复用同一个模块，但页面文件数量必须覆盖页面设计清单。

## 实现要求
1. 根据目标技术栈生成真实项目代码，不要再输出纯静态 HTML mock。
2. 根据匹配项目的真实技术栈生成文件：Vue 后台通常生成 `src/views/**/*.vue` + `src/api/*.js`；React 后台通常生成 `src/pages/**/*.tsx|jsx` + service/api 文件；uni-app/小程序项目按项目现有 `pages/**`、`*.vue` 或 `*.wxml/*.js/*.json/*.wxss` 结构生成。不要把所有项目都当 Vue 后台。
   - 文件路径必须像目标项目里的真实业务模块路径，优先沿用 Project Skill 或代码参考里的目录命名。
   - 如果用户需求表达的是“现有/已有/当前/原有页面或功能上增加、修改、优化、补充筛选/字段/按钮/查询”，必须修改「与本需求相关的已确认前端页面路径」中的现有页面；禁止凭语义新建 `src/views/**/List.vue` 或 `src/pages/**/List.vue` 来冒充改造，禁止选择与已确认页面路径无关的业务页面。
   - 现有功能改造必须做最小增量：旧表格列、旧列表数据、旧查询接口、旧 mixin、旧组件、旧操作列都是既有能力，不要重写整页架构，不要重新生成整页 mock 数据或新建一套列表 API。比如“给现有零售商品列表增加商品ID筛选项”，只需要在现有页面新增查询控件、queryParam 和请求参数传递；已存在页面改造一律复用原 API/原数据流，不输出 `mockProductList`、`Mock.mock`、`mockRequestWrapper`、`Promise.resolve` 假接口或完整假数据。
   - Mock 边界必须先判断页面来源：已存在页面不要 mock，只改现有页面和现有 API 调用参数；全新页面为了真实前端预览可用，需要在独立 API/service 模块提供与 API 契约一致的 mock 数据，但不能与真实请求函数同名重复导出。
   - 如果用户说“新增/增加/添加某个筛选项”，这是新增筛选项，不是把已有筛选项改名。必须保留原页面已有筛选控件及其 `queryParam` 字段，再为新增筛选项绑定 API 契约确认的独立请求字段。例如新增“商品ID”时，保留原“商品编号”及 `queryParam.productCode`，再新增“商品ID”及 `queryParam.id`。只有用户明确说“改名/调整文案/重命名”时，才允许修改旧 label/placeholder。
   - 修改现有 Vue 列表页时必须保留原页面的 `ListMixin`/`mixins`、`<s-table :data="loadData">`、`url.list` 接口、已有 columns/slots/操作按钮和已有导入；除非用户明确要求删除，否则不要用本地 `data()`、新 API 文件或新接口替代原列表加载方式。
   - 如果找不到与现有功能对应的已确认页面路径，本阶段不要编造新页面，应输出空 JSON 数组让系统失败并在修复反馈中暴露“缺少真实页面路径”。
   - 禁止生成 `Demo`、`Example`、`Standalone`、`SandboxPreview`、`PreviewOnly`、`MockPage`、`GeneratedPage` 这类独立演示路径或组件名。
   - 禁止生成新的 `package.json`、`vite.config.*`、`main.*`、`App.*`、`index.html` 来伪造一个独立应用。
3. 第一屏必须匹配需求页面类型：列表页要有搜索筛选、表格和批量/行操作；详情页要有分区详情、状态标签、返回/编辑/启停等操作；表单页要有校验、提交、取消和异常提示；配置/看板页要有对应业务控件和状态。
4. 所有按钮必须有真实前端交互，不允许出现未定义函数、空 onclick、只展示不响应的控件。
5. Mock 只允许用于全新页面的预览数据；已存在页面改造禁止 mock，必须复用现有 API 封装和页面数据流。小程序项目必须同时给出浏览器 HTML/H5 等效预览文件。
6. 代码要短而完整：页面组件控制在 260 行以内，API/mock 服务模块控制在 120 行以内。
7. 只生成与本需求相关的新增/修改文件，不要输出说明文字。
8. 代码必须体现页面设计中的权限、状态和边界；不要只做 happy path。
9. 新页面 API/service 文件中的 mock 数据必须与页面字段、交付 API 契约候选字段完全一致；已存在页面不生成 mock 数据。
10. 不允许用“占位按钮”“待实现方法”“console.log 替代业务逻辑”来冒充完成。

## 可预览硬约束
1. 先判断页面类型，不要把详情页/表单页/配置页强行写成列表页；列表契约只适用于列表或表格页面。
2. 如果使用项目 `STable` 组件，`loadData` 必须返回分页对象：`{ page, pageNo, pageSize, count, totalCount, list }`，其中 `list` 必须是数组；禁止只返回数组、`result.data` 数组或没有 `list` 的对象。
3. API/mock 服务模块里的列表接口必须返回同一分页对象，可包在 `result` 或 `data` 中，但对象内必须同时提供 `list/page/count/pageNo/totalCount`。
4. 详情/编辑/配置接口必须返回对象，可包在 `result` 或 `data` 中；页面读取前必须有默认空对象，禁止直接对可能为 undefined 的对象取深层字段。
5. 接口函数必须兼容真实接口和 mock 接口，推荐写法：列表 `then(res => res.result || res.data || res)`，详情 `then(res => res.result || res.data || {})`。
6. 小程序/uni-app 页面必须遵循项目路由和页面生命周期：原生小程序至少成对生成 `pages/.../*.wxml` 和 `pages/.../*.js`，需要样式/配置时补 `*.wxss/*.json`；uni-app 使用 `pages/.../*.vue`，不要引用 Web-only 组件。
7. uni-app monorepo 必须按目标应用真实结构生成，例如 `apps/<app>/pages/**/index.vue` 和 `apps/<app>/api/*.ts`；不要生成 Web 后台路径。API/service 必须复用项目已确认的请求导出；如果无法确认 `@hc-agent/http` 是否导出 `http`，禁止写 `import { http } from '@hc-agent/http'` 这类未验证命名导入，改用项目既有 API 文件中的实际封装或页面内预览 mock。
8. 使用 `hasPermission`、`v-action`、权限指令或全局 helper 前必须确认目标项目已有该能力；如果未确认但页面设计要求体现按钮权限，必须在当前页面内定义可运行的最小权限 helper，确保首屏不会因未定义变量报错。
9. 原生小程序必须额外生成 `public/sandbox-miniapp-preview.html`，作为浏览器可打开的 H5 等效预览。该 HTML 必须自包含 CSS/JS/mock 数据，并真实呈现小程序页面的布局、状态和交互；它是验收预览，不替代小程序源码。
10. 禁止引用项目中未确认存在的组件、指令或工具；如果不确定，直接使用目标项目基础组件和本文件内方法。
11. 所有模板事件引用的方法必须实现；表格列的 `scopedSlots` 必须有对应 slot。
12. 代码必须能在首屏无运行时报错：不得访问可能为 undefined 的 `.length`、`.map`、`.filter`，除非先做 `Array.isArray` 或默认空数组。
13. 数组兜底重点在页面组件里完成：例如 `const rows = Array.isArray(payload.list) ? payload.list : []`，模板和渲染逻辑只读取 `rows`；API/mock 服务模块只要返回契约正确的列表对象，不要因为参数处理中的 `.map/.filter/.length` 影响页面可用性。

## 输出格式
只允许输出 JSON 文件数组，不要输出 Markdown，不要输出代码块围栏，不要输出解释文字。系统会直接解析这个 JSON 并写入前端项目。

JSON 格式如下:
[
  {"path": "src/views/system/UserList.vue", "content": "完整文件内容"},
  {"path": "src/api/system.js", "content": "完整文件内容"}
]

要求：
- 必须是合法 JSON，最外层必须是数组
- 每项必须包含 path 和 content
- content 里放完整文件内容，换行用 JSON 字符串转义；必须完整闭合所有 JSON 字符串、对象和数组
- 简单后台 Web 页面通常可以只输出 2 个文件：页面组件 + API/mock 服务模块；如果页面设计声明多个主页面，必须输出覆盖所有主页面的页面文件
- 原生小程序必须输出小程序页面文件 + `public/sandbox-miniapp-preview.html`
- 禁止输出 ```json 或任何 Markdown 包裹
- 输出前必须自检 JSON 合法性、文件路径合理性、方法完整性、字段一致性和首屏运行安全性

示例:
[
  {"path": "src/views/system/UserList.vue", "content": "完整文件内容"},
  {"path": "src/api/system.js", "content": "完整文件内容"}
]""",

    "delivery": """基于需求分析、页面设计和前端预览代码，整理一份完整、边界清晰、可进入开发和测试的交付文档包。

## 后端项目规范来源
- 后端项目: {{backend_project_name}}
- 后端技术栈: {{backend_tech}}

## 需求文档
{{requirement_output}}

## 页面设计
{{page_design_output}}

## 前端预览代码
{{prototype_output}}

## 现有功能改造契约继承规则
- 如果前端预览代码是修改现有页面，交付包必须继承真实页面代码里的接口路径、请求字段、响应字段、权限 key、mixin/组件行为，不得根据中文展示名另起字段或接口。
- 如果需求是“新增/增加/添加某个筛选项”，交付包必须写清楚这是新增字段：保留所有原筛选项及其请求字段，再为新增筛选项使用 API 契约确认的独立请求字段；不得把旧字段改名来冒充新增。例如新增“商品ID”时，应保留原“商品编号”请求字段 `productCode`，新增字段按 API 契约使用 `id`。
- 如果用户只是要求“把商品编号改成商品ID/调整文案”，且真实页面中该筛选绑定的是 `queryParam.productCode`，交付文档中的请求字段也必须写 `productCode`；不得改成未确认的 `goodsId`、`productId`。
- 如果真实页面中列表接口来自 `url.list` 或已有 API 封装，交付文档必须沿用该接口；不得凭空写 `/goods/retail/list`、`/product/retail/list` 等新路径。
- Mock 数据只补充新增/变化字段的示例；旧列表字段、旧接口和旧分页结构按现有页面能力继承，不要把老功能重新设计成另一套 API。

请直接输出 Markdown 格式的交付文档（不要用代码块包裹），包含:
1. PRD 摘要（功能清单、优先级、验收标准）
2. 页面设计规格（字段、按钮、交互、状态、权限）
3. 交互流程说明（主流程 + 异常流程）
4. 边界与异常清单（空数据、无权限、失败重试、重复提交、并发操作、状态非法、分页越界）
5. 前端实现要点（组件选择、状态管理、路由规划、权限展示、字段兜底）
6. API 接口草案（接口路径、请求方法、请求参数、响应格式）
   - 必须单独写明“参考后端项目：{{backend_project_name}}”
   - 必须按后端 Project Skill 的 API Contract Patterns 生成，不能凭空创造另一套规范
   - 必须体现后端鉴权、权限校验、错误响应、Swagger/接口文档规则
   - 响应格式必须逐字遵循后端 Project Skill 中的统一响应模型；如果后端 Skill 定义了 ApiResult/traceId/message/data 结构，所有接口响应示例都必须使用该结构，不允许改成扁平的 {code,message,data}
   - 如果后端项目是 BFF/API 转发层，要明确哪些接口是本层接收、鉴权和转发
   - 每个接口必须列出字段映射表：页面字段、请求字段、响应字段、后端字段、类型、是否必填
7. Mock 数据示例（至少包含列表、详情、异常、无权限数据）
8. 权限规则表（角色 × 操作权限矩阵 + 数据范围条件）
9. 测试验收标准（功能测试用例清单、边界条件、兼容性要求）
10. 开发风险与待确认问题（按前端/后端/API/权限/数据分组）""",

    "ui_preview": """根据需求文档，生成一个静态管理后台页面预览。

## 需求文档
{{requirement_output}}

## 前端技术栈
{{frontend_tech}}

## 用户需求
{{user_request}}

## 输出要求
- 只输出一个 ```html 代码块，不要在代码块前后写任何文字说明
- HTML 必须完整输出，不能被截断，控制在 360 行以内
- `<body>` 必须包含 `data-preview-ready="true"`，主内容容器必须使用 `id="preview-root"`，便于系统自动检查预览是否可用

## 技术方案
纯静态 HTML，不需要 Vue/React/JS，只引入 antd CSS：
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/ant-design-vue@1.7.8/dist/antd.min.css">
用 antd CSS 类名（.ant-btn, .ant-table, .ant-input 等）模拟组件外观。

## 实现要求
1. 纯静态 HTML + CSS，不需要 <script>
2. 第一屏必须是后台工作台，不要做 landing page：左侧菜单、标题区、搜索筛选、主表格、关键操作按钮齐全
3. 主列表页 + 新增/编辑弹窗静态样式 + 删除确认静态样式 + 无权限/空数据/加载中/异常状态
4. 表格放 5 条 mock 数据（中文），状态用 tag 展示，列和字段要贴合需求
5. 必须展示权限效果：菜单/页面/按钮/数据范围至少 3 类；无权限按钮要 disabled 并解释原因
6. 视觉风格要像成熟管理后台：信息密度适中、对齐清晰、颜色克制，避免大面积霓虹、渐变球、营销 hero 和占位文案
7. 所有文字使用中文""",

    "backend_dev": """基于以下需求文档和交付包，生成完整、可维护、边界清晰的后端代码。

需求文档:
{{requirement_output}}

交付包:
{{delivery_output}}

## 目标技术栈
{{backend_tech}}

请根据以上技术栈生成对应的后端代码。如果未指定技术栈，默认使用 Java Spring Boot + MyBatis-Plus。

## 后端实现边界
- 必须严格遵循交付包 API 契约，不得擅自改接口路径、请求字段、响应字段和统一响应模型。
- 必须复用目标后端项目的分层、命名、异常、鉴权、权限、日志和数据访问模式。
- 只实现本需求相关文件；不输出无关框架脚手架和泛化示例。
- 如果交付包信息不足，必须在代码后“待确认问题”列出，不要用虚构字段补齐。

**注意**: 如果前端层是 PHP 转发层（BFF），则后端需要提供完整的 RESTful API 供 PHP 层调用，接口需要考虑：
- 统一的响应格式（code/msg/data）
- 认证 token 的传递和校验
- 分页、排序等通用参数的标准化

## 必须覆盖
1. Controller/API 层：参数接收、校验、鉴权、权限 key、错误响应、幂等/重复提交处理。
2. Service 层：业务规则、状态流转、边界判断、事务边界、并发冲突处理。
3. DAO/Mapper/Repository：查询条件、分页排序、数据范围、索引友好查询。
4. Model/DTO/VO：字段命名、类型、必填、枚举、时间/金额格式、脱敏字段。
5. 数据库：表结构、索引、唯一约束、软删/租户字段、审计字段。
6. 异常和日志：参数错误、无权限、数据不存在、状态非法、外部服务失败。
7. 测试友好性：关键逻辑应可单元测试，避免把所有逻辑塞进 Controller。

输出要求:
- 每个代码块前用 `### 文件: 路径/文件名` 标注
- 用对应语言的代码块包裹（```java, ```php, ```go, ```python, ```sql 等）
- 包含 Controller、Service、Model/Entity、数据库建表 SQL
- 遵循该技术栈的最佳实践和常见分层架构
- 每个文件内容必须完整，不要用“省略”“同上”“TODO 实现”代替
- 代码后附“契约对齐说明”和“待确认问题”，说明接口/字段/权限如何对应交付包

在所有代码之后，请用以下 JSON 格式汇总文件列表（方便自动化解析）:
```json
[
  {"path": "src/main/java/xxx/Controller.java", "content": "完整文件内容"},
  {"path": "src/main/java/xxx/Service.java", "content": "完整文件内容"}
]
```""",

    "frontend_dev": """基于以下需求文档、页面设计、原型预览和 API 契约，生成完整、可运行、边界清晰的前端代码。

需求文档:
{{requirement_output}}

页面设计:
{{page_design_output}}

原型预览参考:
{{prototype_output}}

交付包中的 API 接口定义:
{{delivery_output}}

## 目标技术栈
{{frontend_tech}}

请根据以上技术栈生成对应的前端代码。

## 前端实现边界
- 必须严格遵循页面设计和交付包 API 契约，不得擅自改字段、接口、权限 key 和页面形态。
- 必须复用目标前端项目的目录、路由、API 封装、组件库、权限指令和样式规范。
- 不确定是否存在的组件/工具不要引用；优先使用基础组件和本文件内可维护方法。
- 只输出本需求相关文件；不输出静态演示页或与真实项目脱节的 mock wrapper。
- uni-app/小程序项目不要按普通 Web 后台生成；monorepo 项目必须输出目标应用真实页面路径，例如 `apps/<app>/pages/**/index.vue`，并按 H5 可预览要求补齐页面内 mock/兜底状态。
- 禁止引用未验证的 API 命名导出或权限 helper。使用 `@hc-agent/http`、`hasPermission`、`v-action` 等能力前必须来自 Project Skill/代码参考；否则使用当前文件内可运行的最小 helper 或与页面字段一致的预览 mock，保证首屏不报错。

**技术栈判断规则**:
- 如果技术栈包含 `vue`、`react`、`javascript`、`typescript` 等 → 生成对应前端框架代码
- 如果技术栈包含 `php` → 这通常是 BFF/API 转发层，生成 PHP 控制器代码：
  - 接收前端请求 → 转发到后端 Java API → 返回响应
  - 使用 curl 或 Guzzle 调用后端接口
  - 处理参数转换、鉴权、日志等中间件逻辑
- 如果未指定技术栈 → 默认使用 Vue 3 + Ant Design Vue + TypeScript

输出要求:
- 每个代码块前用 `### 文件: 路径/文件名` 标注
- 用对应语言的代码块包裹（```vue, ```js, ```ts, ```php, ```jsx, ```tsx 等）
- 前端框架项目：包含列表页、表单/弹窗组件、API 服务、路由配置
- PHP 转发层项目：包含 Controller（接收+转发）、Service（业务逻辑）、Middleware（鉴权/日志）、路由配置
- 必须实现加载、空数据、搜索无结果、无权限、接口异常、重复提交、删除二次确认等状态
- 所有事件方法、表单校验、API 调用、字段兜底都必须完整实现
- 列表页必须保证分页字段一致；详情/表单页必须保证对象字段默认值安全
- mock 数据、页面字段、API service 字段和交付包字段必须一致

在所有代码之后，请用以下 JSON 格式汇总文件列表:
```json
[
  {"path": "src/views/List.vue", "content": "完整文件内容"},
  {"path": "src/api/module.js", "content": "完整文件内容"}
]
```""",

    "code_review": """请审查真实前端代码、后端/API 契约和两端字段对齐情况。不要只做泛泛的代码质量评价。

## 需求文档
{{requirement_output}}

## 页面设计
{{page_design_output}}

## 交付包/API 契约
{{delivery_output}}

## 前端预览/真实前端代码
{{prototype_output}}

后端代码:
{{backend_dev_output}}

前端代码:
{{frontend_dev_output}}

## 必审清单
1. 真实前端代码审查：只审查实际生成的前端文件、预览代码和 API/service 文件；如果没有 frontend_dev，则审查 prototype 阶段的真实前端代码。
2. API 契约对齐：逐项核对接口路径、HTTP 方法、query/body 参数名、必填字段、分页字段、详情字段、状态码/错误结构、鉴权和权限 key。
3. 字段一致性：逐项核对页面表格列、详情字段、表单字段、搜索条件、mock 字段、API 请求字段、API 响应字段是否同名同类型；中英文 label 不算字段名一致。
   - 前端请求对象前缀不算字段名差异：例如 `queryParam.id`、`params.id`、`parameter.id` 与 API 契约请求参数 `id` 是同一字段，不得因此判定字段名不一致。
4. 页面形态一致性：列表页核对 list/page/count 等分页契约；详情页核对对象数据和空对象兜底；表单页核对校验规则、提交参数和错误提示；小程序核对源码和 HTML 预览是否表达同一字段和交互。
5. Mock 与真实契约一致性：mock 数据不能用一套字段、真实 API/service 读另一套字段；mock 不能掩盖字段缺失。
6. 代码合理性：组件拆分、状态管理、加载/空/异常态、错误处理、防 undefined、权限指令/按钮态、重复代码、不可达代码、硬编码、无效 import、未实现事件方法。
7. 可预览性：首屏是否可能运行时报错，接口失败是否可降级，预览代码是否依赖不存在的组件/插件/全局变量。
8. 安全和稳定性：token/密钥泄露、XSS、未校验输入、危险 HTML、越权按钮、并发重复提交、接口超时和幂等性。
9. 逻辑正确性：核对业务规则、状态流转、权限条件、数据范围、默认值、枚举映射和边界判断是否前后一致。
10. 可维护性：核对重复代码、命名不清、职责混乱、不可测试逻辑、过度硬编码和与项目规范不一致的实现。

## 输出要求
请输出:
1. 后端/API 契约评分 (A/B/C/D/F)
2. 前端代码评分 (A/B/C/D/F)
3. 契约对齐结论：列出接口级、字段级、权限级差异；每条必须指出“前端使用字段/接口”和“契约或后端提供字段/接口”
4. 代码合理性问题列表（含严重程度: critical/major/minor，标注前端/后端/API/契约）
5. 改进建议（每个问题给出具体修复方案）
6. 是否通过审查 (PASS/FAIL)

如果发现 critical 或 major 问题，标记为 FAIL 并给出详细修复指导。
以下情况必须 FAIL：
- 前端读取的响应字段与 API 契约不一致
- 前端提交参数名与 API 契约不一致
- 页面展示字段、mock 字段和 API 字段三者不一致
- 列表/详情/表单页面形态与接口响应结构不匹配
- 预览依赖不存在的组件、方法、权限指令或全局变量
- 缺少必要的加载/空/异常兜底导致客户现场首屏可能报错

请在输出末尾附带结构化 JSON（方便自动化解析）:
```json
{
  "review_passed": true/false,
  "backend_score": "A/B/C/D/F",
  "frontend_score": "A/B/C/D/F",
  "contract_alignment": "接口和字段对齐结论摘要",
  "field_mismatches": [
    {"severity": "critical/major/minor", "location": "文件或接口", "frontend_field": "前端字段", "contract_field": "契约字段", "fix": "修复方式"}
  ],
  "fix_suggestions": "修复建议摘要"
}
```""",

    "testing": """基于以下需求、页面设计、API 契约和前后端代码，设计测试用例并生成可执行的测试脚本。

需求文档:
{{requirement_output}}

后端代码:
{{backend_dev_output}}

前端代码:
{{frontend_dev_output}}

代码审查结果:
{{code_review_output}}

## 要求

请完成以下两部分输出:

### 第一部分：测试用例分析
1. 测试范围和不测范围：明确本次验证边界。
2. 测试用例列表：含优先级、前置条件、步骤、输入、预期结果。
3. 边界用例：空数据、无权限、非法输入、重复提交、分页越界、状态非法、接口超时。
4. 权限用例：菜单/页面/按钮/API/数据范围分别验证。
5. 契约用例：请求字段、响应字段、分页字段、错误结构、mock 与真实字段一致性。
6. 覆盖率评估：说明已覆盖和未覆盖风险。
7. 发现的 Bug 列表（标注严重程度: critical/major/minor）

### 第二部分：可执行测试脚本
请根据后端技术栈生成对应的自动化测试代码:
- Java: JUnit 5 + MockMvc 测试
- Go: testing 包 + httptest
- Python: pytest + httpx
- PHP: PHPUnit
- Node.js: Jest + supertest

如果后端有 REST API，请生成 API 接口测试脚本，包含:
- 正常流程测试（200 响应）
- 参数校验测试（400 响应）
- 权限测试（401/403 响应）
- 边界条件测试
- 并发/幂等测试（重复点击、重复提交、同一资源并发修改）
- 数据范围测试（不同租户/角色/部门只能访问授权数据）

每个代码块前用 `### 文件: 路径/文件名` 标注。

在输出末尾附带结构化 JSON:
```json
{
  "tests_passed": true/false,
  "bug_details": "发现的问题详情",
  "test_cases_total": 10,
  "test_cases_passed": 8,
  "coverage_estimate": "80%",
  "test_scripts": ["tests/TestController.java"]
}
```""",

    "commit": """请整理以下前后端代码和测试结果，生成准确、边界清晰的提交方案。

后端代码:
{{backend_dev_output}}

前端代码:
{{frontend_dev_output}}

测试结果:
{{testing_output}}

请输出:
1. 变更摘要：按后端、前端、API 契约、测试、配置分组。
2. 后端 Git commit message（Conventional Commits 格式，说明 scope 和主要行为变化）
3. 前端 Git commit message（Conventional Commits 格式，说明 scope 和主要行为变化）
4. 后端变更文件列表：路径、用途、是否新增/修改/删除。
5. 前端变更文件列表：路径、用途、是否新增/修改/删除。
6. 风险与回滚提示：哪些变更影响权限、接口、数据结构或兼容性。
7. 提交前检查清单：测试、lint、构建、迁移、权限配置。""",

    "deploy": """请根据以下信息，生成可执行、可回滚、边界清晰的部署方案。

提交信息:
{{commit_output}}

请输出:
1. 部署范围：涉及服务、前端资源、数据库、配置、权限、缓存。
2. 前置条件：依赖版本、环境变量、数据库迁移、权限菜单、第三方服务。
3. 部署步骤：按顺序写命令/操作、负责人、预计耗时和观察点。
4. 健康检查方案：接口、页面、日志、队列、数据库、Redis、关键业务路径。
5. 灰度和验证：小流量验证、功能验证、权限验证、异常回归。
6. 回滚方案：代码回滚、配置回滚、数据库回滚/补偿、缓存清理。
7. 风险清单：兼容性、数据一致性、权限遗漏、接口超时、并发压力。""",

    "report": """请生成整个项目的总结报告，要求事实清楚、边界明确、结论可追踪。

需求:
{{requirement_output_short}}

代码审查:
{{code_review_output_short}}

测试:
{{testing_output_short}}

自动测评:
{{eval_result}}

请输出:
1. 项目概况：需求目标、范围边界、参考项目、执行模式。
2. 完成功能列表：按阶段说明已完成内容和关键产物。
3. 技术栈总结：前端、后端/API、权限、测试、部署相关信息。
4. 契约与字段对齐结论：接口、字段、权限、mock 与真实数据的一致性。
5. 验证结果：测试、构建、审查、预览、自动测评或部署验证的结论（含自动测评分数）。
6. 已知问题和风险：按严重程度列出影响、原因、规避或修复建议。
7. 后续计划：按优先级列出下一步动作、责任角色和验收标准。""",
}


PM_REQUIREMENT_REVIEW_CONTRACT = """

## 产品经理质量门
请把这份 PRD 当作要交给前端、后端、QA 继续执行的正式输入，必须覆盖：
- 业务目标、目标用户、使用场景、范围边界和不做范围
- 功能清单，按 P0/P1/P2/P3 标注优先级
- 角色与权限矩阵，写清页面级权限和按钮/操作级权限
- 参考成熟权限体系的表达方式：RBAC 用 `subject/role/resource/action`，ABAC 补充租户、部门、本人/下级、状态等条件，资源权限按菜单/页面/按钮/API/数据范围拆开
- 给出至少 3 条策略样例，例如 `role=运营主管, resource=order, action=export, condition=同部门数据`，并说明拒绝态、隐藏态、禁用态和审计日志
- 数据对象与关键字段，包含字段名、类型、是否必填、校验规则、默认值
- 主流程、异常流程、空数据、加载中、无权限、失败重试等状态
- 可验收的 Acceptance Criteria，每条都能被 QA 直接测试
- 明确假设与待确认问题，避免把不确定内容伪装成事实

文档末尾额外输出一个 JSON 代码块，便于系统做质量评审，格式如下：
```json
{
  "pm_quality": {
    "score": 0,
    "ready_for_review": false,
    "missing_items": [],
    "review_focus": [],
    "primary_pages": [],
    "permission_points": [],
    "permission_model": [],
    "data_scope_rules": [],
    "policy_examples": [],
    "data_entities": [],
    "acceptance_criteria": []
  }
}
```
"""


PM_PAGE_DESIGN_REVIEW_CONTRACT = """

## 页面设计质量门
请把页面设计写到前端可以直接做原型、后端可以直接拆接口的程度，必须覆盖：
- 页面清单、路由/入口、层级关系和默认落点
- 每个页面的表格列、搜索项、表单字段、详情字段和字段校验
- 按钮、批量操作、危险操作、二次确认、抽屉/弹窗交互
- 页面状态：空数据、加载中、无权限、搜索无结果、接口异常、提交成功/失败
- 权限点：菜单权限、页面权限、按钮权限、API 权限、数据范围权限；必须写清 permission key 命名、禁用/隐藏/无权限提示和审计点
- 权限设计参考成熟项目模式：RBAC 负责角色到资源动作，ABAC/条件策略负责租户、部门、本人/下级、状态、金额等上下文约束；前端按路由、菜单、按钮、表格行操作分别呈现
- 与 wealth-admin-home / Java / Node / PHP 生成链路相关的实现约束或待确认点

文档末尾额外输出一个 JSON 代码块，便于系统做质量评审，格式如下：
```json
{
  "design_quality": {
    "score": 0,
    "ready_for_review": false,
    "missing_items": [],
    "review_focus": [],
    "primary_pages": [],
    "permission_points": [],
    "permission_model": [],
    "data_scope_rules": [],
    "policy_examples": [],
    "data_entities": [],
    "acceptance_criteria": []
  }
}
```
"""


def _render_prompt_template(template: str, context: Dict[str, Any]) -> str:
    """渲染 prompt 模板，替换变量占位符"""
    user_request = context.get("user_request", "")
    prev_outputs = context.get("stage_outputs", {})

    backend_tech = context.get("backend_tech", "")
    frontend_tech = context.get("frontend_tech", "")
    backend_project_name = context.get("backend_project_name", "")
    frontend_project_name = context.get("frontend_project_name", "")
    workspace_path = context.get("workspace_path", "")
    prototype_focus = _prototype_focus_from_page_design(prev_outputs.get("page_design", {}))
    prototype_output = _stage_code_files_for_prompt(
        prev_outputs.get("prototype", {}),
        fallback=prev_outputs.get("prototype", {}).get("output", "未提供"),
        workspace_path=workspace_path,
    )
    frontend_dev_stage = prev_outputs.get("frontend_dev", {})
    if frontend_dev_stage:
        frontend_dev_output = _stage_code_files_for_prompt(
            frontend_dev_stage,
            fallback=frontend_dev_stage.get("output") or "未提供",
            workspace_path=workspace_path,
        )
    else:
        frontend_dev_output = "未单独生成 frontend_dev；请审查上方 prototype 阶段的真实生成文件清单。"
    backend_dev_output = _stage_code_files_for_prompt(
        prev_outputs.get("backend_dev", {}),
        fallback=prev_outputs.get("backend_dev", {}).get("output", "未提供"),
        workspace_path=workspace_path,
    )

    replacements = {
        "{{user_request}}": user_request[:2000],
        "{{requirement_output}}": prev_outputs.get("requirement", {}).get("output", "未提供")[:1800],
        "{{page_design_output}}": prev_outputs.get("page_design", {}).get("output", "未提供")[:2200],
        "{{prototype_focus}}": prototype_focus,
        "{{prototype_output}}": prototype_output,
        "{{delivery_output}}": prev_outputs.get("delivery", {}).get("output", "未提供")[:3000],
        "{{ui_preview_output}}": prev_outputs.get("ui_preview", {}).get("output", "未提供")[:3000],
        "{{backend_dev_output}}": backend_dev_output,
        "{{frontend_dev_output}}": frontend_dev_output,
        "{{development_output}}": prev_outputs.get("development", {}).get("output", "未提供")[:3000],
        "{{code_review_output}}": prev_outputs.get("code_review", {}).get("output", "未提供")[:2000],
        "{{testing_output}}": prev_outputs.get("testing", {}).get("output", "未提供")[:2000],
        "{{commit_output}}": prev_outputs.get("commit", {}).get("output", "未提供")[:1000],
        "{{backend_tech}}": backend_tech or "未指定",
        "{{frontend_tech}}": frontend_tech or "未指定",
        "{{backend_project_name}}": backend_project_name or "未匹配后端项目",
        "{{frontend_project_name}}": frontend_project_name or "未匹配前端项目",
        # 截断版本（report 阶段用）
        "{{requirement_output_short}}": (prev_outputs.get("requirement", {}).get("output", "未提供") or "")[:500],
        "{{code_review_output_short}}": (prev_outputs.get("code_review", {}).get("output", "未提供") or "")[:500],
        "{{testing_output_short}}": (prev_outputs.get("testing", {}).get("output", "未提供") or "")[:500],
        # eval 阶段自动测评结果（功能/幻觉/视觉分数），折入最终报告
        "{{eval_result}}": (prev_outputs.get("eval", {}).get("output", None) or "自动测评未运行")[:1500],
    }

    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)
    return result


# eval 阶段默认评审标准（无 golden case 时用）
DEFAULT_EVAL_CRITERIA = [
    "需求覆盖：产物实现了用户需求中的核心功能点，无重大遗漏",
    "契约完整：API 路径/方法/请求与响应字段清晰，前后端字段命名与类型对齐",
    "代码质量：结构清晰、无明显错误、具备可编译/可运行的意图",
    "可测试性：包含必要校验、边界处理与可验收的测试要点",
]


def _format_eval_report(structured: Dict[str, Any]) -> str:
    """把 eval 阶段的 judge/幻觉/视觉结构化结果格式化为 markdown 报告。

    作为 eval 阶段产物展示，并经 ``{{eval_result}}`` 折入最终报告。
    """
    lines = ["# 自动测评报告", ""]
    judge = structured.get("judge") or {}
    score = judge.get("overall_score")
    lines.append(f"## 功能评审　总分：{score if score is not None else 'N/A'}/100")
    for c in judge.get("per_criterion") or []:
        if not isinstance(c, dict):
            continue
        mark = "✅" if c.get("passed") else "❌"
        reason = c.get("reason", "")
        lines.append(f"- {mark} {c.get('criterion', '')}：{c.get('score', 'N/A')}" + (f" — {reason}" if reason else ""))
    if judge.get("summary"):
        lines.append(f"\n> {judge['summary']}")
    if judge.get("error"):
        lines.append(f"\n（功能评审异常：{judge['error']}）")

    halluc = structured.get("hallucination") or {}
    hscore = halluc.get("hallucination_score")
    lines.append("")
    lines.append(f"## 幻觉评审　幻觉分：{hscore if hscore is not None else 'N/A'}/100")
    flagged = halluc.get("flagged") or []
    lines.append("虚构嫌疑：" + ("无" if not flagged else ""))
    for f in flagged:
        lines.append(f"- {f}")
    if halluc.get("summary"):
        lines.append(f"\n> {halluc['summary']}")

    if structured.get("vision_error"):
        lines.append("")
        lines.append(f"## 视觉评审　（跳过：{str(structured['vision_error'])[:60]}）")
    elif isinstance(structured.get("vision"), dict):
        vision = structured["vision"]
        vscore = vision.get("overall_score")
        lines.append("")
        lines.append(f"## 视觉评审　渲染分：{vscore if vscore is not None else 'N/A'}/100")
        if vision.get("summary"):
            lines.append(f"\n> {vision['summary']}")

    if structured.get("e2e_error"):
        lines.append("")
        lines.append(f"## E2E 浏览器断言　（跳过：{str(structured['e2e_error'])[:60]}）")
    elif isinstance(structured.get("e2e"), dict):
        e2e = structured["e2e"]
        passed = e2e.get("passed")
        mark = "✅ 通过" if passed else "❌ 未通过"
        src = e2e.get("source") or ""
        src_label = "（真实预览）" if src == "live" else "（渲染桩）"
        lines.append("")
        lines.append(f"## E2E 浏览器断言　{mark}{src_label}")
        issues = e2e.get("issues") or []
        if issues:
            for iss in issues:
                lines.append(f"- ⚠️ {iss}")
        elif not e2e.get("note"):
            lines.append("- 渲染完整，期望控件齐全")
        if e2e.get("note"):
            lines.append(f"\n> {e2e['note']}")

    return "\n".join(lines)


def _stage_code_files_for_prompt(
    stage: Dict[str, Any],
    fallback: str = "",
    workspace_path: str = "",
) -> str:
    code_files = stage.get("code_files") if isinstance(stage, dict) else None
    if not isinstance(code_files, dict) or not code_files:
        return (fallback or "未提供")[:3000]

    header = [
        "以下是真实生成文件清单，不包含文件正文，用于降低 token 消耗。",
        "审查时必须按这些路径通过文件搜索/文件读取能力查看真实文件内容，不要根据流式输出截断猜测缺失逻辑。",
    ]
    if workspace_path:
        header.append(f"workspace_path: {workspace_path}")
    parts: List[str] = ["\n".join(header)]
    for path, content in code_files.items():
        if not isinstance(content, str):
            continue
        safe_path = str(path).replace("\\", "/").lstrip("/")
        symbol_hits = [
            symbol
            for symbol in (
                "queryParam.id",
                "productIdValidateStatus",
                "productIdHelp",
                "searchQuery",
                "searchReset",
                "loadData",
                "STable",
            )
            if symbol in content
        ]
        parts.append(
            f"\n- `{safe_path}` ({len(content.splitlines())} lines, {len(content)} chars)"
            + (f"; key symbols: {', '.join(symbol_hits)}" if symbol_hits else "")
        )
    return "".join(parts)


# ==================== Prompt 构建 ====================

def _build_pipeline_prompt(stage_key: str, context: Dict[str, Any],
                            custom_prompts: Dict[str, str] = None) -> str:
    """根据阶段构建 Agent 的 prompt，注入记忆和修复反馈。支持自定义 prompt 覆盖。"""
    fix_feedback = _compact_fix_feedback(context.get("fix_feedback", ""))
    memories_text = context.get("memories_text", "")

    memory_section = ""
    if memories_text:
        memory_section = f"""
## 历史经验（从过去的执行中学习）
{memories_text}

请参考以上经验，避免重复犯错。
"""

    fix_section = ""
    if fix_feedback:
        fix_section = f"""
## 修复要求
上一次执行发现问题，请根据以下反馈修复：
{fix_feedback}

请针对上述问题进行改进。
"""

    # 优先使用自定义 prompt，否则用默认
    if custom_prompts and custom_prompts.get(stage_key):
        template = custom_prompts[stage_key]
    else:
        template = DEFAULT_STAGE_PROMPTS.get(stage_key, f"请处理 {stage_key} 阶段的任务。")

    prompt = _render_prompt_template(template, context)
    if stage_key == "requirement" and "pm_quality" not in prompt:
        prompt += PM_REQUIREMENT_REVIEW_CONTRACT
    if stage_key == "page_design" and "design_quality" not in prompt:
        prompt += PM_PAGE_DESIGN_REVIEW_CONTRACT
    if stage_key == "prototype" and context.get("pipeline_mode") == "frontend_contract_review":
        mandatory_skills = [
            ("Real Frontend Preview", "real_frontend_preview"),
            ("Backoffice Page Scaffold", "backoffice_page_scaffold"),
        ]
        for skill_title, skill_id in mandatory_skills:
            preview_skill = skill_registry.view_skill(skill_id)
            preview_instructions = (preview_skill or {}).get("instructions", "").strip()
            if not preview_instructions:
                continue
            prompt += f"""

## {skill_title} Skill Contract
The following Skill is mandatory for this stage. If any local prompt text conflicts with it, follow this Skill.

{preview_instructions}
"""
    if stage_key == "code_review" and context.get("pipeline_mode") == "frontend_contract_review":
        prompt += """

## First-Version Review Scope
This pipeline delivers frontend preview code in the preview stage, API contract, and review results.
Do not require backend implementation, test execution, commit, or deployment in this mode.
Focus the review on:
1. Frontend code completeness and whether it can run inside the matched frontend project sandbox.
2. Frontend code consistency with the confirmed Project Skill.
3. API contract completeness: endpoints, methods, params, response shape, error cases, and permissions.
4. Field-level alignment between frontend code, mock data, API contract, and backend/project skill conventions.
5. Code reasonableness: state handling, loading/empty/error states, undefined guards, event handlers, permissions, and maintainability.

Return FAIL with actionable feedback when any of these three checks is incomplete.
"""
    return memory_section + fix_section + PIPELINE_GLOBAL_PROMPT_CONTRACT + prompt


# ==================== 输出解析 ====================

def _has_new_page_structure_signal(text: str) -> bool:
    new_page_signal_markers = (
        "页面位置建议",
        "页面位置",
        "页面功能",
        "菜单入口",
        "路由路径",
        "默认落点",
    )
    return any(marker in (text or "") for marker in new_page_signal_markers) and not re.search(
        r"(?:现有|已有|当前|原有|既有).{0,12}(?:页面|列表|详情|表单|功能)",
        text or "",
    )


def _is_existing_feature_change_request(user_request: str) -> bool:
    text = (user_request or "").strip()
    if not text:
        return False
    if _has_new_page_structure_signal(text):
        return False
    new_feature_markers = (
        "不是现有页面",
        "不是已有页面",
        "不是现有功能",
        "不是已有功能",
        "不是现有页面加字段",
        "不是现有页面改造",
        "新功能页面",
        "新建页面",
        "新增页面",
    )
    if any(marker in text for marker in new_feature_markers):
        return False
    existing_markers = ("现有", "已有", "当前", "原有", "既有")
    explicit_existing_patterns = (
        r"在.+?(?:页面|列表|详情|表单|功能).*(?:增加|添加|新增|补充|改造|优化|调整|修改)",
        r"(?:给|为).+?(?:页面|列表|详情|表单|功能).*(?:增加|添加|新增|补充|改造|优化|调整|修改)",
    )
    change_markers = ("增加", "添加", "新增", "补充", "改造", "优化", "调整", "修改")
    target_markers = ("列表", "页面", "功能", "筛选", "查询", "搜索", "字段", "按钮", "表格")
    if any(marker in text for marker in existing_markers):
        return any(marker in text for marker in target_markers)
    if re.search(r"(?:新增|新建|创建|搭建|生成|做一个|开发一个).*(?:页面|列表|详情|表单|管理|功能|工作台|看板)", text):
        return False
    if any(re.search(pattern, text) for pattern in explicit_existing_patterns):
        return True
    return any(marker in text for marker in change_markers) and any(marker in text for marker in ("筛选", "查询", "搜索", "字段"))


def _is_new_feature_page_request(user_request: str) -> bool:
    text = (user_request or "").strip()
    if not text or _is_existing_feature_change_request(text):
        return False
    if _has_new_page_structure_signal(text):
        return True
    return bool(re.search(r"(?:新增|新建|创建|搭建|生成|做一个|开发一个).*(?:页面|列表|详情|表单|管理|功能|工作台|看板)", text))


def _is_frontend_page_path(path: str) -> bool:
    return (
        path.startswith(("src/views/", "src/pages/", "pages/"))
        and path.endswith((".vue", ".tsx", ".jsx", ".wxml"))
    )


def _is_known_support_page_name(name: str) -> bool:
    return bool(re.search(r"(弹窗|抽屉|modal|drawer|dialog)", name or "", re.I))


def _page_name_tokens(name: str) -> List[str]:
    original = re.sub(r"[`'\"“”‘’（）()\[\]【】]", "", name or "")
    text = original
    text = re.sub(r"(页面|页|列表|详情|表单|管理|配置|审核|创建|新建|编辑)", " ", text)
    tokens = [
        token.strip().lower()
        for token in re.split(r"[^A-Za-z0-9\u4e00-\u9fff]+", text)
        if token.strip()
    ]
    semantic_tokens: List[str] = []
    semantic_map = {
        "首页": ["index", "home", "main"],
        "主页": ["index", "home", "main"],
        "钱包": ["wallet"],
        "交易": ["transaction", "trade"],
        "明细": ["detail", "record", "transaction"],
        "流水": ["record", "transaction"],
        "充值": ["recharge"],
        "提现": ["withdraw"],
        "拼团": ["group"],
        "团购": ["group"],
        "团单": ["团单", "team", "groupteam", "order"],
        "活动": ["activity"],
        "创建": ["create", "edit", "form"],
        "新建": ["create", "edit", "form"],
        "编辑": ["edit", "form"],
        "详情": ["detail"],
        "列表": ["list"],
    }
    for keyword, aliases in semantic_map.items():
        if keyword in original:
            semantic_tokens.extend(aliases)
    result: List[str] = []
    seen = set()
    for token in [*tokens, *semantic_tokens]:
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def _expected_prototype_pages_from_page_design(page_design_stage: Dict[str, Any]) -> List[str]:
    if not isinstance(page_design_stage, dict):
        return []
    structured = page_design_stage.get("structured_output")
    if not isinstance(structured, dict):
        structured = page_design_stage
    design_quality = structured.get("design_quality") if isinstance(structured, dict) else None
    primary_pages = _coerce_string_list(
        design_quality.get("primary_pages") if isinstance(design_quality, dict) else None,
        [],
    )
    if not primary_pages:
        document = str(page_design_stage.get("page_design_document") or page_design_stage.get("output") or "")
        if not document and isinstance(structured, dict):
            document = str(structured.get("page_design_document") or structured.get("output") or "")
        primary_pages = _extract_primary_pages_from_page_design_document(document)
    return [
        page
        for page in primary_pages
        if page and not _is_known_support_page_name(page)
    ][:8]


def _extract_primary_pages_from_page_design_document(document: str) -> List[str]:
    if not document:
        return []
    table_pages = _primary_pages_from_page_design_table(document)
    if table_pages:
        return table_pages
    pages: List[str] = []
    seen = set()

    def add_page(name: str) -> None:
        cleaned = re.sub(r"[`*#]+", "", name or "").strip()
        cleaned = re.sub(r"^\d+(?:\.\d+)*\s*", "", cleaned).strip()
        cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", cleaned).strip()
        if (
            not cleaned
            or cleaned in seen
            or _is_known_support_page_name(cleaned)
            or any(skip in cleaned for skip in ("页面清单", "页面布局", "字段定义", "查询与筛选", "按钮和操作", "页面状态", "权限控制", "API 契约", "开发确认"))
        ):
            return
        if any(keyword in cleaned for keyword in ("页", "列表", "详情", "表单", "编辑", "新增", "创建", "管理")):
            seen.add(cleaned)
            pages.append(cleaned)

    for line in document.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        table_match = re.match(r"^\|\s*([^|]+?)\s*\|", stripped)
        if table_match and "|" in stripped:
            first_cell = table_match.group(1).strip()
            if first_cell not in {"页面名称", "---", "页面/组件", "资源", "按钮名称", "展示名"}:
                add_page(first_cell)
        heading_match = re.match(r"^#{2,4}\s+(.+)$", stripped)
        if heading_match:
            add_page(heading_match.group(1))
        if len(pages) >= 8:
            break
    return pages


def _markdown_table_rows(document: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    headers: List[str] = []
    for line in (document or "").splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and "|" in stripped[1:]):
            headers = []
            continue
        cells = [cell.strip().strip("`") for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        if not headers:
            headers = cells
            continue
        if all(re.fullmatch(r":?-{2,}:?", cell or "") for cell in cells):
            continue
        if len(cells) < len(headers):
            cells.extend([""] * (len(headers) - len(cells)))
        rows.append({headers[index]: cells[index] for index in range(min(len(headers), len(cells)))})
    return rows


def _is_support_page_design_row(row: Dict[str, str]) -> bool:
    name = str(row.get("页面名称") or row.get("页面/组件") or "").strip()
    menu = str(row.get("菜单层级") or row.get("层级") or "").strip()
    route = str(row.get("路由路径") or row.get("路由 Path") or row.get("路由") or "").strip()
    default_landing = str(row.get("默认落点") or "").strip()
    text = f"{name} {menu} {route} {default_landing}"
    if re.search(r"页面内弹窗|通用弹窗|弹窗|抽屉|Modal|Drawer|选择器|组件", text, re.I):
        return True
    if route in {"", "-", "—"} and default_landing in {"", "-", "—"} and re.search(r"新增|编辑|新建|创建|选择", name):
        return True
    return False


def _is_primary_page_design_row(row: Dict[str, str]) -> bool:
    name = str(row.get("页面名称") or row.get("页面/组件") or "").strip()
    if not name or name in {"页面名称", "---", ":---"}:
        return False
    if _is_support_page_design_row(row):
        return False
    route = str(row.get("路由路径") or row.get("路由 Path") or row.get("路由") or "").strip()
    menu = str(row.get("菜单层级") or row.get("层级") or "").strip()
    default_landing = str(row.get("默认落点") or "").strip()
    if route and route not in {"-", "—"}:
        return True
    if menu and not re.search(r"弹窗|组件|通用", menu):
        return True
    if default_landing and default_landing not in {"-", "—"}:
        return True
    return False


def _primary_pages_from_page_design_table(document: str) -> List[str]:
    pages: List[str] = []
    seen = set()
    for row in _markdown_table_rows(document):
        if "页面名称" not in row and "页面/组件" not in row:
            continue
        if not _is_primary_page_design_row(row):
            continue
        name = str(row.get("页面名称") or row.get("页面/组件") or "").strip()
        if name and name not in seen:
            seen.add(name)
            pages.append(name)
    return pages[:8]


def _expected_page_paths_from_page_design_document(document: str) -> Dict[str, List[str]]:
    if not document:
        return {}
    page_paths: Dict[str, List[str]] = {}
    for line in document.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and "|" in stripped):
            continue
        cells = [cell.strip().strip("`") for cell in stripped.strip("|").split("|")]
        if not cells or cells[0] in {"页面名称", "---", "页面/组件"}:
            continue
        paths = [
            _normalize_frontend_component_path(path)
            for path in re.findall(r"(?:@/)?(?:src/)?(?:pages|views|components)/[A-Za-z0-9_./-]+\.(?:vue|tsx|jsx|wxml)", stripped)
        ]
        if not paths:
            continue
        page_paths.setdefault(cells[0], [])
        for path in paths:
            if path not in page_paths[cells[0]]:
                page_paths[cells[0]].append(path)
    return page_paths


def _normalize_frontend_component_path(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").strip().strip("`").lstrip("/")
    if normalized.startswith("@/"):
        normalized = normalized[2:]
    if normalized.startswith("views/"):
        normalized = "src/" + normalized
    if normalized.startswith("components/"):
        normalized = "src/" + normalized
    return normalized.lstrip("/")


def _expected_page_paths_from_page_design_stage(page_design_stage: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    if not isinstance(page_design_stage, dict):
        return {}
    structured = page_design_stage.get("structured_output")
    document = str(page_design_stage.get("page_design_document") or page_design_stage.get("output") or "")
    if not document and isinstance(structured, dict):
        document = str(structured.get("page_design_document") or structured.get("output") or "")
    return _expected_page_paths_from_page_design_document(document)


def _declared_frontend_paths_from_page_design_stage(page_design_stage: Optional[Dict[str, Any]]) -> List[str]:
    page_paths = _expected_page_paths_from_page_design_stage(page_design_stage)
    paths: List[str] = []
    seen = set()
    for declared_paths in page_paths.values():
        for path in declared_paths:
            normalized = _normalize_frontend_component_path(path)
            if normalized and normalized not in seen:
                seen.add(normalized)
                paths.append(normalized)
    return paths


def _is_additive_filter_request(user_request: str = "") -> bool:
    text = user_request or ""
    if not re.search(r"(筛选|查询|搜索|检索|过滤)", text):
        return False
    if re.search(r"(改名|重命名|改成|替换|文案|展示名|label|placeholder)", text, re.I):
        return False
    return bool(re.search(r"(新增|增加|添加|补充|加一个|加上|加个)", text))


def _requested_filter_label(user_request: str = "") -> str:
    text = re.sub(r"\s+", "", user_request or "")
    match = re.search(r"(?:新增|增加|添加|补充|加一个|加上|加个)(?:一个|一项|个|项)?(.{1,24}?)(?:的)?(?:筛选项|筛选|查询项|查询|搜索项|搜索|检索项|检索|过滤项|过滤)", text)
    if not match:
        return ""
    label = match.group(1)
    label = re.sub(r"^(?:现有|已有|当前|原有|页面|列表|表格|商城管理平台|管理平台)+", "", label)
    label = re.sub(r"(?:字段|条件|控件|输入框|筛选项|查询项)$", "", label)
    return label[:16]


def _query_filter_bindings(content: str) -> List[Tuple[str, str]]:
    if not isinstance(content, str):
        return []
    bindings: List[Tuple[str, str]] = []
    for match in re.finditer(
        r"<a-form-item[^>]*label=[\"']([^\"']+)[\"'][\s\S]{0,300}?v-model(?:\.trim)?=[\"']queryParam\.([A-Za-z_$][\w$]*)[\"']",
        content,
        re.I,
    ):
        label, field = match.groups()
        bindings.append((label.strip(), field.strip()))
    return bindings


def _validate_existing_feature_paths(
    files: Dict[str, str],
    user_request: str = "",
    existing_frontend_paths: Optional[List[str]] = None,
) -> List[str]:
    if not _is_existing_feature_change_request(user_request):
        return []

    generated_page_paths = [
        str(path).replace("\\", "/").lstrip("/")
        for path in files
        if _is_frontend_page_path(str(path).replace("\\", "/").lstrip("/"))
    ]
    if not generated_page_paths:
        return []

    existing_paths = {
        str(path).replace("\\", "/").lstrip("/")
        for path in (existing_frontend_paths or [])
        if _is_frontend_page_path(str(path).replace("\\", "/").lstrip("/"))
    }
    if not existing_paths:
        return [
            "用户需求是修改现有功能，但项目代码参考未提供任何已确认存在的前端页面路径；"
            "必须先匹配真实项目源码中的现有页面，不能新生成页面冒充改造"
        ]

    issues = []
    for path in generated_page_paths:
        if path not in existing_paths:
            examples = "、".join(sorted(existing_paths)[:8])
            issues.append(
                f"{path} 不是项目代码参考中已确认存在的页面；用户需求是修改现有功能，"
                f"必须改现有页面路径。可用现有页面示例：{examples}"
            )
    return issues


def _validate_existing_feature_mock_scope(files: Dict[str, str], user_request: str = "") -> List[str]:
    if not _is_existing_feature_change_request(user_request):
        return []

    issues = []
    for path, content in files.items():
        safe_path = str(path).replace("\\", "/").lstrip("/")
        if not safe_path.startswith("src/api/") or not isinstance(content, str):
            continue
        if re.search(
            r"\bmock[A-Za-z0-9_]*List\b|\bMock\.mock\b|\bmockRequest(?:Wrapper)?\b|const\s+mock[A-Za-z0-9_]*\s*=",
            content,
        ):
            issues.append(
                f"{safe_path} 为现有功能改造生成了 mock 列表数据；旧列表数据和旧接口应复用现有能力，"
                "已存在页面不要生成 mock"
            )
        if re.search(r"return\s+(?:new\s+Promise\s*\(|Promise\.resolve\s*\()", content) and re.search(r"\b(list|data)\s*:", content):
            issues.append(
                f"{safe_path} 为现有功能改造生成了模拟接口 Promise；应只在必要时补充现有请求参数，不要重造旧列表数据"
            )
    return issues


def _validate_new_feature_mock_scope(files: Dict[str, str], user_request: str = "") -> List[str]:
    if not _is_new_feature_page_request(user_request):
        return []
    normalized_paths = [str(path).replace("\\", "/").lstrip("/") for path in files]
    has_page = any(
        path.startswith(("src/views/", "src/pages/"))
        and path.endswith((".vue", ".tsx", ".jsx"))
        for path in normalized_paths
    )
    api_contents = [
        content
        for path, content in files.items()
        if str(path).replace("\\", "/").lstrip("/").startswith("src/api/") and isinstance(content, str)
    ]
    if not has_page or not api_contents:
        return []
    combined_api = "\n".join(api_contents)
    combined_all = "\n".join(content for content in files.values() if isinstance(content, str))
    has_network_request = re.search(r"\brequest\s*\(|\baxios\s*\.", combined_api)
    has_mock = re.search(
        r"\bMock\.mock\b|\bmock[A-Za-z0-9_]*\b|Promise\.resolve\s*\(|return\s+new\s+Promise\s*\(",
        combined_all,
    )
    if has_mock:
        return []
    if has_network_request:
        return [
            "全新页面需要提供与 API 契约一致的 mock 数据；"
            "当前 API 模块只调用真实 request，缺少 mock/fallback 数据，后端未实现时无法首屏预览"
        ]
    return ["全新页面需要提供与 API 契约一致的 mock 数据，确保真实前端预览首屏可用"]


def _project_skill_requires_nested_api_result(pipe_config: Optional[Dict[str, Any]] = None) -> bool:
    if not isinstance(pipe_config, dict):
        return False
    snapshots = []
    for key in ("backend_project_skill_snapshot", "project_skill_snapshot"):
        snapshot = pipe_config.get(key)
        if isinstance(snapshot, dict):
            snapshots.append(snapshot)
    snapshots.extend(
        snapshot
        for snapshot in (pipe_config.get("backend_project_skill_snapshots") or [])
        if isinstance(snapshot, dict)
    )
    combined = "\n".join(str(snapshot.get("skill_content") or "") for snapshot in snapshots)
    return bool(
        "ApiResult" in combined
        and "traceId" in combined
        and re.search(r'"message"\s*:\s*\{|"message"\s+是对象|message 是对象', combined)
    )


def _validate_api_response_envelope(
    files: Dict[str, str],
    pipe_config: Optional[Dict[str, Any]] = None,
) -> List[str]:
    if not _project_skill_requires_nested_api_result(pipe_config):
        return []
    issues: List[str] = []
    flat_success_pattern = re.compile(
        r"(?:resolve|return|data|result)?\s*\(?\s*\{\s*"
        r"(?:code\s*:\s*(?:200|0)|['\"]code['\"]\s*:\s*(?:200|0))"
        r"[\s\S]{0,180}?"
        r"(?:msg\s*:|message\s*:\s*['\"]|['\"]msg['\"]\s*:|['\"]message['\"]\s*:\s*['\"])",
        re.I,
    )
    for path, content in files.items():
        safe_path = str(path).replace("\\", "/").lstrip("/")
        if not safe_path.startswith("src/api/") or not isinstance(content, str):
            continue
        if flat_success_pattern.search(content) and not re.search(r"message\s*:\s*\{[\s\S]{0,120}code\s*:\s*0", content):
            issues.append(
                f"{safe_path} 的 mock/API 响应使用扁平 code/message/msg 结构；"
                "后端 Project Skill 要求 ApiResult 包装为 { message: { code: 0, message: 'ok' }, traceId, data }"
            )
    return issues


def _permission_keys_from_design(document: str) -> List[str]:
    """从页面设计文档抽取【显式声明】的权限 key。

    只认出现在「权限/permission」上下文行里的 ns:action 形 token，避免把 JSON 示例、
    CSS、URL 片段、普通字段名等误判为权限声明——否则登录页这类无权限页也会被误伤。
    """
    if not document:
        return []
    excluded_prefixes = {"http", "https"}
    result: List[str] = []
    seen = set()
    for line in document.splitlines():
        if not re.search(r"权限|permission", line, re.I):
            continue  # 仅在显式提到权限的行里找权限码
        for tok in re.findall(r"\b([A-Za-z][\w-]*(?::[A-Za-z][\w-]*)+)\b", line):
            if tok.split(":", 1)[0] in excluded_prefixes or tok in seen:
                continue
            seen.add(tok)
            result.append(tok)
    return result[:20]


def _generated_pages_look_auth_only(files: Dict[str, str]) -> bool:
    """生成的页面是否全是登录/注册/鉴权类（这类页本就无需权限控制）。"""
    auth_re = re.compile(r"(login|logout|signin|signup|register|auth|forgot|reset|登录|注册|鉴权)", re.I)
    page_paths = [
        str(p).replace("\\", "/").lstrip("/")
        for p, c in files.items()
        if isinstance(c, str) and str(p).replace("\\", "/").lstrip("/").endswith((".vue", ".tsx", ".jsx"))
    ]
    if not page_paths:
        return False
    return all(bool(auth_re.search(p)) for p in page_paths)


def _api_endpoint_requirements_from_design(document: str) -> List[str]:
    if not document:
        return []
    endpoints: List[str] = []
    seen = set()
    in_api_section = False
    for line in document.splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,5}\s+", stripped):
            in_api_section = bool(re.search(r"\bAPI\b|接口|契约", stripped, re.I))
        if not in_api_section and not re.search(r"接口路径|请求路径|接口地址|API", stripped, re.I):
            continue
        for endpoint in re.findall(r"`(/[^`\s]+)`|['\"](/[^'\"\s]+)['\"]|(?:接口路径|请求路径|接口地址)\s*[：:]\s*(/[^\s，。)）]+)", stripped):
            value = next((item for item in endpoint if item), "")
            value = value.strip().rstrip("，。；;")
            if not value or value in seen:
                continue
            if re.search(r"\{[^}]+\}", value):
                value = re.sub(r"/?\{[^}]+\}", "", value)
            if value.count("/") >= 2 or value.startswith("/api/"):
                seen.add(value)
                endpoints.append(value)
        for value in re.findall(r"`(?:GET|POST|PUT|PATCH|DELETE)\s+(/[^`\s]+)`", stripped, re.I):
            value = value.strip().rstrip("，。；;")
            if value and value not in seen:
                seen.add(value)
                endpoints.append(value)
    return endpoints[:20]


def _endpoint_is_covered_by_api_module(endpoint: str, combined_api: str) -> bool:
    if not endpoint:
        return True
    normalized = endpoint.strip()
    candidates = {normalized}
    if normalized.startswith("/api/"):
        candidates.add(normalized[4:])
    if not normalized.startswith("/api/"):
        candidates.add("/api" + normalized)
    if any(candidate in combined_api for candidate in candidates):
        return True
    segments = [
        segment
        for segment in re.split(r"/+", normalized)
        if segment and not re.fullmatch(r"\{[^}]+\}", segment)
    ]
    terminal = segments[-1] if segments else ""
    if terminal and re.search(rf"[`'\"/]?{re.escape(terminal)}[`'\"\)]", combined_api):
        return True
    return False


def _component_requirements_from_design(document: str) -> List[str]:
    if not document:
        return []
    candidates: List[str] = []
    project_components = {
        "JDictSelectTag",
        "JSearchSelectTag",
        "JDate",
        "JUpload",
        "SForm",
        "STable",
        "Modal",
        "Modal.confirm",
    }
    in_component_section = False
    for line in document.splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,5}\s+", stripped):
            in_component_section = bool(re.search(r"组件|Component", stripped, re.I))
            continue
        for component in project_components:
            if re.search(rf"(?<![A-Za-z0-9_.-]){re.escape(component)}(?![A-Za-z0-9_.-])", stripped):
                candidates.append(component)
        component_context = (
            in_component_section
            or "<" in stripped
            or bool(re.search(r"组件|Component", stripped, re.I))
        )
        data_context = bool(re.search(r"数据对象|数据实体|实体|字段|接口|API|权限|模型|Enum", stripped, re.I))
        if not component_context or data_context:
            continue
        candidates.extend(re.findall(r"`([A-Z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)?)`", stripped))
        candidates.extend(re.findall(r"<([A-Za-z][A-Za-z0-9_-]+)(?:\s|/|>)", stripped))
    result: List[str] = []
    seen = set()
    generic_words = {"API", "JSON", "HTTP", "GET", "POST", "PUT", "DELETE", "URL"}
    for candidate in candidates:
        if candidate in generic_words or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result[:20]


def _action_requirements_from_design(document: str) -> List[str]:
    if not document:
        return []
    actions: List[str] = []
    seen = set()
    in_action_section = False
    for line in document.splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,5}\s+", stripped):
            in_action_section = bool(re.search(r"按钮|操作|动作", stripped))
            continue
        if not re.search(r"新增|新建|创建|添加", line):
            continue
        is_table_row = stripped.startswith("|") and "|" in stripped[1:]
        if not in_action_section and not is_table_row:
            continue
        cells = [cell.strip().strip("`") for cell in stripped.strip("|").split("|")]
        if cells and cells[0] in {"按钮", "按钮名称", "操作", "操作名称", "页面名称", "---", ":---"}:
            continue
        candidates = [cells[0]] if is_table_row and cells else [line]
        for candidate in candidates:
            for action in re.findall(r"(新增[\u4e00-\u9fffA-Za-z0-9_/]{0,12}|新建[\u4e00-\u9fffA-Za-z0-9_/]{0,12}|创建[\u4e00-\u9fffA-Za-z0-9_/]{0,12})", candidate):
                action = action.strip()
                if re.search(r"弹窗|抽屉|页面|组件|路径|时间|排序|倒序|正序", action):
                    continue
                expanded_actions = [action]
                slash_match = re.match(r"^(新增|新建|创建)([^/]+)/(.+)$", action)
                if slash_match:
                    prefix, left, right = slash_match.groups()
                    expanded_actions = [f"{prefix}{left}", f"{prefix}{right}"]
                for expanded in expanded_actions:
                    expanded = expanded.strip()
                    if re.search(r"弹窗|抽屉|页面|组件|路径|时间|排序|倒序|正序", expanded):
                        continue
                    if expanded and expanded not in seen and expanded not in {"新增", "新建", "创建"}:
                        seen.add(expanded)
                        actions.append(expanded)
    return actions[:12]


def _component_is_used(component: str, combined_pages: str) -> bool:
    if not component:
        return True
    kebab = re.sub(r"(?<!^)([A-Z])", r"-\1", component).lower().replace("_", "-")
    return bool(
        re.search(rf"\b{re.escape(component)}\b", combined_pages)
        or re.search(rf"<\s*{re.escape(kebab)}(?:\s|/|>)", combined_pages, re.I)
    )


def _action_is_covered(action: str, combined_pages: str) -> bool:
    if not action:
        return True
    if re.search(r"弹窗|抽屉|组件|页面|页$", action):
        return True
    action = re.sub(r"(?:按钮|入口|操作)$", "", action).strip() or action
    if action in combined_pages:
        return True
    if re.fullmatch(r"(新增|新建|创建)/(编辑|修改)", action):
        has_create = bool(re.search(r"新增|新建|创建|handleAdd|add\w*\s*\(", combined_pages, re.I))
        has_edit = bool(re.search(r"编辑|修改|handleEdit|edit\w*\s*\(", combined_pages, re.I))
        return bool(has_create and has_edit)
    composite_match = re.match(r"^(新增|新建|创建)/(编辑|修改)(.+)$", action)
    if composite_match:
        _create_word, _edit_word, suffix = composite_match.groups()
        suffix = suffix.strip()
        has_create = bool(re.search(r"新增|新建|创建|handleAdd|add\w*\s*\(", combined_pages, re.I))
        has_edit = bool(re.search(r"编辑|修改|handleEdit|edit\w*\s*\(", combined_pages, re.I))
        return bool(has_create and has_edit and (not suffix or suffix in combined_pages))
    if action.startswith(("新增", "新建", "创建")):
        suffix = re.sub(r"^(新增|新建|创建)", "", action)
        return bool(
            re.search(r"新增|新建|创建", combined_pages)
            and (not suffix or suffix in combined_pages)
        )
    return False


def _validate_page_design_frontend_coverage(
    files: Dict[str, str],
    page_design_stage: Optional[Dict[str, Any]] = None,
) -> List[str]:
    if not isinstance(page_design_stage, dict):
        return []
    document = str(page_design_stage.get("page_design_document") or page_design_stage.get("output") or "")
    structured = page_design_stage.get("structured_output")
    if not document and isinstance(structured, dict):
        document = str(structured.get("page_design_document") or structured.get("output") or "")
    if not document:
        return []

    combined_pages = "\n".join(
        content
        for path, content in files.items()
        if isinstance(content, str)
        and str(path).replace("\\", "/").lstrip("/").endswith((".vue", ".tsx", ".jsx"))
    )
    if not combined_pages:
        return []

    issues: List[str] = []
    combined_api = "\n".join(
        content
        for path, content in files.items()
        if isinstance(content, str) and str(path).replace("\\", "/").lstrip("/").startswith("src/api/")
    )
    missing_endpoints = [
        endpoint
        for endpoint in _api_endpoint_requirements_from_design(document)
        if not _endpoint_is_covered_by_api_module(endpoint, combined_api)
    ]
    if missing_endpoints:
        issues.append(
            "页面设计 API 契约声明了接口，但 API 模块未覆盖："
            + "、".join(missing_endpoints[:8])
        )

    permission_keys = _permission_keys_from_design(document)
    if (
        permission_keys
        and not _generated_pages_look_auth_only(files)
        and not re.search(r"\bv-action\b|hasPermission|permission|权限", combined_pages, re.I)
    ):
        issues.append(
            "页面设计声明了按钮/页面权限 key，但前端页面未体现 v-action、hasPermission 或等效权限控制"
        )

    missing_components = [
        component
        for component in _component_requirements_from_design(document)
        if not _component_is_used(component, combined_pages)
    ]
    if missing_components:
        issues.append(
            "页面设计要求使用项目组件，但前端页面未体现："
            + "、".join(missing_components[:8])
        )

    missing_actions = [
        action
        for action in _action_requirements_from_design(document)
        if not _action_is_covered(action, combined_pages)
    ]
    if missing_actions:
        issues.append(
            "页面设计声明了新增/创建入口，但前端页面未体现："
            + "、".join(missing_actions[:8])
        )

    if (
        re.search(r"startTime", document)
        and re.search(r"endTime", document)
        and re.search(r"RangePicker|a-range-picker|range-picker", combined_pages, re.I)
    ):
        has_split = re.search(r"startTime\s*[:=]", combined_pages) and re.search(r"endTime\s*[:=]", combined_pages)
        has_delete_range = re.search(r"delete\s+\w+\.[A-Za-z_$][\w$]*(?:Time|Range|Date|validTime)\b", combined_pages)
        if not (has_split and has_delete_range):
            issues.append(
                "The date range request field must be split into startTime/endTime before API submission, "
                "and the original range field must be removed from the submitted params."
            )

    return issues


def _collect_api_endpoints(content: str) -> List[str]:
    if not isinstance(content, str):
        return []
    return sorted(set(re.findall(r"['\"](/api/[^'\"]+)['\"]", content)))


def _validate_undefined_data_return_refs(path: str, content: str) -> List[str]:
    if not isinstance(content, str) or not path.endswith((".vue", ".js", ".ts", ".tsx", ".jsx")):
        return []
    safe_path = str(path).replace("\\", "/").lstrip("/")
    if safe_path.startswith("src/api/"):
        return []
    issues: List[str] = []
    in_data_method = False
    in_data_return = False
    entered_runtime_function = False
    for line in content.splitlines():
        stripped = line.strip()
        if re.search(r"\bdata\s*\([^)]*\)\s*\{", line):
            in_data_method = True
            in_data_return = False
            entered_runtime_function = False
            continue
        if not in_data_method:
            continue
        if not in_data_return and re.search(r"\breturn\s*\{", line):
            in_data_return = True
            continue
        if not in_data_return:
            continue
        if re.search(r"\b(loadData|[A-Za-z_$][\w$]*)\s*:\s*(?:async\s*)?(?:function\b|[^,\n]*=>)", stripped):
            entered_runtime_function = True
        if not entered_runtime_function and re.match(
            r"[A-Za-z_$][\w$]*\s*:\s*(?:result|res|parameter)\.[A-Za-z_$]",
            stripped,
        ):
            issues.append(
                f"{safe_path} 的 data() 初始返回对象引用了 result/res/parameter 等未定义运行期变量，"
                "会导致 created/首屏渲染时报错"
            )
            break
    return issues


def _validate_mock_pagination_interaction(path: str, content: str) -> List[str]:
    if not isinstance(content, str):
        return []
    safe_path = str(path).replace("\\", "/").lstrip("/")
    if not safe_path.startswith("src/api/"):
        return []
    if not ("pageNo" in content and "pageSize" in content and re.search(r"\blist\s*:", content)):
        return []
    if re.search(r"\blist\s*:\s*\[\s*\]", content):
        return []
    has_real_paging = bool(
        re.search(r"\.slice\s*\(", content)
        or re.search(r"for\s*\([^)]*<\s*(?:pageSize|Number\(pageSize\)|size)", content)
        or re.search(r"Array\.from\s*\([^)]*(?:pageSize|Number\(pageSize\)|size)", content, re.S)
    )
    if not has_real_paging:
        return [
            f"{safe_path} 的 mock 分页没有按 pageNo/pageSize 切换数据；"
            "翻页时必须返回不同页数据，不能每页显示同一批记录"
        ]
    return []


def _validate_existing_feature_preservation(
    files: Dict[str, str],
    user_request: str = "",
    existing_frontend_paths: Optional[List[str]] = None,
    existing_frontend_files: Optional[Dict[str, str]] = None,
) -> List[str]:
    if not _is_existing_feature_change_request(user_request):
        return []
    existing_files = {
        str(path).replace("\\", "/").lstrip("/"): content
        for path, content in (existing_frontend_files or {}).items()
        if isinstance(content, str)
    }
    if not existing_files:
        return []

    issues: List[str] = []
    allowed_paths = {
        str(path).replace("\\", "/").lstrip("/")
        for path in (existing_frontend_paths or [])
        if str(path).strip()
    }
    generated_paths = {str(path).replace("\\", "/").lstrip("/") for path in files}
    explicit_new_api = re.search(r"(新接口|新增接口|新增数据源|mock|模拟数据|假数据)", user_request or "", re.I)
    original_api_paths = {path for path in existing_files if path.startswith("src/api/")}

    for path in generated_paths:
        if (
            path.startswith("src/api/")
            and path not in original_api_paths
            and not explicit_new_api
            and allowed_paths
        ):
            issues.append(
                f"{path} 是为现有功能改造新增的 API 文件；本需求应复用现有页面的查询接口，"
                "除非用户明确要求新增接口或 mock 数据"
            )

    for path in sorted(allowed_paths & generated_paths):
        original = existing_files.get(path, "")
        generated = files.get(path, "")
        if not isinstance(generated, str) or not original:
            continue
        safe_path = path
        original_lower = original.lower()
        generated_lower = generated.lower()

        if "listmixin" in original_lower and "listmixin" not in generated_lower:
            issues.append(f"{safe_path} 原页面使用 ListMixin，生成代码移除了它，属于整页重写而不是现有功能最小改造")
        if re.search(r"\bmixins\s*:", original) and not re.search(r"\bmixins\s*:", generated):
            issues.append(f"{safe_path} 原页面存在 mixins 配置，生成代码不能移除既有列表行为")
        if "<s-table" in original_lower and "<s-table" not in generated_lower:
            issues.append(f"{safe_path} 原页面使用 STable，生成代码不能替换为其他表格或静态列表")
        if re.search(r"<s-table[^>]+:data=[\"']loadData[\"']", original, re.I | re.S) and not re.search(
            r"<s-table[^>]+:data=[\"']loadData[\"']", generated, re.I | re.S
        ):
            issues.append(f"{safe_path} 原页面 STable 使用 loadData，生成代码必须保留该数据加载入口")
        if "queryparam" in original_lower and "queryparam" not in generated_lower:
            issues.append(f"{safe_path} 原页面使用 queryParam 查询对象，生成代码不能改成本地孤立查询状态")
        if re.search(r"(商品id|商品编号|商品id的筛选|商品ID)", user_request or "", re.I):
            if "productCode" in original and "productCode" not in generated:
                issues.append(
                    f"{safe_path} 原页面商品编号/商品ID筛选使用 queryParam.productCode，"
                    "生成代码不能改成未确认的 productId 或丢失既有字段"
                )
        if _is_additive_filter_request(user_request):
            requested_label = _requested_filter_label(user_request)
            original_bindings = _query_filter_bindings(original)
            generated_bindings = _query_filter_bindings(generated)
            generated_labels = {label for label, _field in generated_bindings}
            original_fields = {field for _label, field in original_bindings}
            requested_fields = {
                field
                for label, field in generated_bindings
                if requested_label and requested_label in label
            }
            for label, field in original_bindings:
                if field in generated and label not in generated_labels:
                    issues.append(
                        f"{safe_path} 现有筛选项“{label}”被改名或覆盖；用户需求是新增筛选项，"
                        f"必须保留原筛选项和 queryParam.{field}"
                    )
            if requested_label and requested_label not in generated:
                issues.append(f"{safe_path} 用户需求是新增“{requested_label}”筛选项，但生成代码未出现该筛选控件")
            if requested_label and requested_fields and requested_fields <= original_fields:
                reused = "、".join(f"queryParam.{field}" for field in sorted(requested_fields))
                issues.append(
                    f"{safe_path} 新增“{requested_label}”筛选不能复用原有字段 {reused}；"
                    "必须使用独立请求字段，不能把旧筛选项改名来冒充新增"
                )
            if requested_label and requested_label in generated and not requested_fields:
                issues.append(f"{safe_path} 新增“{requested_label}”筛选项没有绑定 queryParam 请求字段")
            if requested_label and _is_identifier_filter_label(requested_label) and requested_fields:
                query_param_match = re.search(r"\bqueryParam\s*:\s*\{(?P<body>[^{}]*)\}", generated)
                query_param_body = query_param_match.group("body") if query_param_match else ""
                for field in sorted(requested_fields):
                    if not re.search(rf"\b{re.escape(field)}\s*:", query_param_body):
                        issues.append(f"{safe_path} 新增“{requested_label}”筛选项绑定了 queryParam.{field}，但 data() 中缺少默认字段初始化")
                missing_parts = []
                if "productIdValidateStatus" not in generated:
                    missing_parts.append("productIdValidateStatus")
                if "productIdHelp" not in generated:
                    missing_parts.append("productIdHelp")
                if not re.search(r"\bsearchQuery\s*\(", generated):
                    missing_parts.append("searchQuery")
                if not re.search(r"\bsearchReset\s*\(", generated):
                    missing_parts.append("searchReset")
                if missing_parts:
                    issues.append(
                        f"{safe_path} 新增“{requested_label}”筛选项缺少校验/重置实现："
                        + "、".join(missing_parts)
                    )

        original_endpoints = _collect_api_endpoints(original)
        for endpoint in original_endpoints:
            if endpoint not in generated:
                issues.append(f"{safe_path} 原页面列表接口 {endpoint} 被移除或替换，现有功能改造必须复用原接口")

    return issues


async def _e2e_browser_check_issues(
    code_files: Dict[str, str],
    user_request: str = "",
    page_design_doc: str = "",
) -> List[str]:
    """对生成的 prototype code_files 跑真实浏览器 E2E 断言，返回缺失项 issue 列表。

    派生期望控件（启发式）→ 用渲染桩在 headless chromium 里加载 → 断言渲染完整性 +
    期望控件存在。harness 故障（playwright 缺失/超时）一律 fail-open 返回 []，绝不因
    浏览器问题阻塞流水线；只有「页面真的渲染坏了 / 缺关键控件」才返回 issue，并入
    prototype 校验的重试→交人工循环。
    """
    try:
        from app.ai.e2e_expectations import derive_e2e_expectations
        from app.services.vision_eval_service import run_e2e_assertions

        expectations = derive_e2e_expectations(user_request, page_design_doc)
        result = await run_e2e_assertions(code_files or {}, expectations, screenshot=False)
        if result.get("harness_error"):
            logger.info("e2e 浏览器断言跳过(fail-open): %s", result["harness_error"])
            return []
        return list(result.get("issues") or [])
    except Exception as e:  # noqa: BLE001
        logger.warning("e2e 浏览器断言异常(fail-open): %s", e)
        return []


def _validate_frontend_preview_code_files(
    files: Dict[str, str],
    user_request: str = "",
    existing_frontend_paths: Optional[List[str]] = None,
    existing_frontend_files: Optional[Dict[str, str]] = None,
    expected_pages: Optional[List[str]] = None,
    page_design_stage: Optional[Dict[str, Any]] = None,
    pipe_config: Optional[Dict[str, Any]] = None,
) -> List[str]:
    issues: List[str] = []
    if not files:
        return ["没有生成前端代码文件"]

    issues.extend(_validate_existing_feature_paths(files, user_request, existing_frontend_paths))
    issues.extend(_validate_existing_feature_mock_scope(files, user_request))
    issues.extend(_validate_new_feature_mock_scope(files, user_request))
    issues.extend(
        _validate_existing_feature_preservation(
            files,
            user_request=user_request,
            existing_frontend_paths=existing_frontend_paths,
            existing_frontend_files=existing_frontend_files,
        )
    )
    issues.extend(_validate_api_response_envelope(files, pipe_config))
    issues.extend(_validate_page_design_frontend_coverage(files, page_design_stage))
    combined_api_modules = "\n".join(
        content
        for path, content in files.items()
        if isinstance(content, str) and str(path).replace("\\", "/").lstrip("/").startswith("src/api/")
    )
    api_modules_return_pagination = bool(
        re.search(r"\blist\s*:", combined_api_modules)
        and re.search(r"\bpage\s*:", combined_api_modules)
        and re.search(r"\bcount\s*:", combined_api_modules)
    )

    normalized_paths = [str(path).replace("\\", "/").lstrip("/") for path in files]
    vue_admin_paths = [
        path for path in normalized_paths
        if (
            path.startswith(("src/views/", "src/pages/", "pages/"))
            or re.match(r"^apps/[^/]+/pages/.+\.vue$", path)
        )
        and path.endswith(".vue")
    ]
    react_page_paths = [
        path for path in normalized_paths
        if path.startswith(("src/pages/", "src/views/", "src/components/")) and path.endswith((".tsx", ".jsx"))
    ]
    mini_wxml_paths = [path for path in normalized_paths if path.startswith("pages/") and path.endswith(".wxml")]
    mini_js_paths = {path[:-3] for path in normalized_paths if path.startswith("pages/") and path.endswith(".js")}
    html_preview_paths = [
        path for path in normalized_paths
        if path in ("public/sandbox-miniapp-preview.html", "sandbox-miniapp-preview.html")
        or path.endswith("/sandbox-miniapp-preview.html")
    ]
    standalone_path_pattern = re.compile(
        r"(?:^|/)(?:demo|example|standalone|sandboxpreview|previewonly|mockpage|generatedpage)(?:/|\.|-|$)",
        re.I,
    )
    api_paths = [
        path for path in normalized_paths
        if path.startswith("src/api/") and path.endswith((".js", ".ts"))
    ]
    static_paths = [path for path in normalized_paths if path.endswith((".html", ".htm"))]

    non_preview_static_paths = [path for path in static_paths if path not in html_preview_paths]
    if non_preview_static_paths and not mini_wxml_paths:
        issues.append("预览阶段禁止生成静态 HTML 文件，必须生成真实前端项目代码")
    if not (vue_admin_paths or react_page_paths or mini_wxml_paths):
        issues.append("缺少可预览页面文件：Vue/uni-app .vue、React .tsx/.jsx 或小程序 pages/*.wxml")
    expected_page_names = [
        page for page in (expected_pages or []) if page and not _is_known_support_page_name(page)
    ]
    expected_page_paths = _expected_page_paths_from_page_design_stage(page_design_stage)
    declared_frontend_paths = set(_declared_frontend_paths_from_page_design_stage(page_design_stage))
    generated_pages = vue_admin_paths + react_page_paths + mini_wxml_paths
    if declared_frontend_paths:
        for generated_path in generated_pages:
            if generated_path not in declared_frontend_paths:
                issues.append(
                    f"{generated_path} 未在页面设计组件路径中声明；重新生成必须沿用锁定文件名，禁止随机新增替代页面文件"
                )
        missing_declared_component_paths = [
            path for path in sorted(declared_frontend_paths) if path not in normalized_paths
        ]
        if missing_declared_component_paths:
            issues.append(
                "页面设计声明了组件路径，但前端文件未覆盖："
                + "、".join(missing_declared_component_paths[:8])
            )
    expected_declared_paths = {
        path
        for page_name in expected_page_names
        for path in (expected_page_paths.get(page_name) or [])
        if path
    }
    if len(expected_page_names) > 1:
        if expected_declared_paths:
            missing_declared_paths = [
                path for path in sorted(expected_declared_paths) if path not in normalized_paths
            ]
            if missing_declared_paths:
                issues.append(
                    "页面设计要求的主页面组件路径未完整生成："
                    + "、".join(missing_declared_paths[:8])
                )
        elif len(generated_pages) < len(expected_page_names):
            issues.append(
                f"页面设计要求 {len(expected_page_names)} 个主页面（{'、'.join(expected_page_names[:8])}），"
                f"但 prototype 只生成了 {len(generated_pages)} 个页面文件；必须覆盖完整页面集"
            )
    for page_name in expected_page_names:
        declared_paths = expected_page_paths.get(page_name) or []
        if not declared_paths:
            page_tokens = set(_page_name_tokens(page_name))
            for declared_name, paths in expected_page_paths.items():
                declared_tokens = set(_page_name_tokens(declared_name))
                if page_tokens and declared_tokens and (
                    page_tokens <= declared_tokens
                    or declared_tokens <= page_tokens
                    or str(declared_name).strip("页") == str(page_name).strip("页")
                ):
                    declared_paths = paths
                    break
        if declared_paths and any(path in normalized_paths for path in declared_paths):
            continue
        tokens = _page_name_tokens(page_name)
        if not tokens:
            continue
        if not any(
            any(token in generated_path.lower() for token in tokens)
            or any(token in str(files.get(generated_path, "")).lower() for token in tokens[:3])
            for generated_path in generated_pages
        ):
            issues.append(f"页面设计主页面“{page_name}”没有对应的前端页面文件")
    for wxml_path in mini_wxml_paths:
        if wxml_path[:-5] not in mini_js_paths:
            issues.append(f"{wxml_path} 缺少同名小程序逻辑文件 .js")
    if mini_wxml_paths and not html_preview_paths:
        issues.append("原生小程序页面必须额外生成 public/sandbox-miniapp-preview.html 用于浏览器预览")

    combined = "\n".join(content for content in files.values() if isinstance(content, str))
    if "```" in combined:
        issues.append("文件内容中包含 Markdown 代码块围栏")
    uses_network_api = any(
        isinstance(content, str) and ("request(" in content or "axios" in content or "Mock.mock" in content)
        for content in files.values()
    )
    if uses_network_api and not api_paths and not mini_wxml_paths:
        issues.append("使用接口请求时应提供独立 API/mock 服务模块，避免页面内散落不可复用请求逻辑")

    for path, content in files.items():
        if not isinstance(content, str):
            issues.append(f"{path} 内容不是字符串")
            continue
        safe_path = str(path).replace("\\", "/").lstrip("/")
        issues.extend(_validate_undefined_data_return_refs(safe_path, content))
        issues.extend(_validate_mock_pagination_interaction(safe_path, content))
        path_lower = safe_path.lower()
        if standalone_path_pattern.search(path_lower):
            issues.append(f"{safe_path} 像独立 demo/preview 页面，必须基于匹配前端项目的真实业务目录生成")
        if safe_path in {"package.json", "vite.config.js", "vite.config.ts", "src/main.js", "src/main.ts", "src/main.tsx", "src/App.vue", "src/App.tsx", "index.html"}:
            issues.append(f"{safe_path} 像独立应用入口文件，预览生成必须是匹配项目的增量业务文件")
        if re.search(r"(?:Standalone|SandboxPreview|PreviewOnly|MockPage|GeneratedPage)", content):
            issues.append(f"{safe_path} 包含独立预览组件命名，必须改成匹配项目业务页面命名")
        is_api_module = safe_path.startswith("src/api/")
        is_page_or_component = (
            safe_path.endswith((".vue", ".tsx", ".jsx"))
            or (
                safe_path.endswith(".js")
                and safe_path.startswith(("pages/", "src/views/", "src/pages/", "src/components/"))
            )
        )
        if is_page_or_component and not is_api_module:
            has_unsafe_array_read = re.search(r"\.(?:length|map|filter)\b", content)
            has_array_guard = "Array.isArray" in content or "|| []" in content or "?? []" in content
            if has_unsafe_array_read and not has_array_guard:
                issues.append(f"{safe_path} 访问数组前缺少默认空数组兜底，容易首屏运行时报错")

        if safe_path.endswith(".vue"):
            if "<s-table" in content.lower():
                uses_existing_list_mixin = "listmixin" in content.lower()
                stable_data_handlers = {
                    handler.strip()
                    for handler in re.findall(
                        r"<s-table\b[^>]*\s(?::data|data)=['\"]([A-Za-z_$][\w$]*)['\"]",
                        content,
                        re.I | re.S,
                    )
                }
                if not stable_data_handlers and "loadData" in content:
                    stable_data_handlers.add("loadData")
                stable_data_handler_list = sorted(stable_data_handlers)
                handler_patterns = [
                    rf"\b{re.escape(handler)}\s*\([^)]*\)\s*\{{"
                    rf"|\b{re.escape(handler)}\s*:\s*(?:async\s*)?(?:function\b|[^,\n]*=>)"
                    for handler in stable_data_handler_list
                ]
                defined_stable_handlers = [
                    handler for handler, pattern in zip(stable_data_handler_list, handler_patterns)
                    if re.search(pattern, content)
                ]
                uses_api_backed_load_data = bool(
                    api_modules_return_pagination
                    and any(
                        re.search(
                            rf"\b{re.escape(handler)}\s*\([^)]*\)\s*\{{[\s\S]{{0,1200}}return\s+(?:this\.)?[A-Za-z_$][\w$]*\s*\(",
                            content,
                        )
                        for handler in defined_stable_handlers
                    )
                )
                if stable_data_handlers and not defined_stable_handlers and not uses_existing_list_mixin:
                    issues.append(
                        f"{safe_path} 使用 STable 但没有定义数据加载方法："
                        + "、".join(sorted(stable_data_handlers))
                    )
                elif not stable_data_handlers:
                    issues.append(f"{safe_path} 使用 STable 但没有绑定数据加载方法")
                if not uses_existing_list_mixin and not uses_api_backed_load_data:
                    preserves_api_pagination = bool(re.search(r"return\s*\{\s*\.\.\.\w+\s*,\s*list\s*:", content, re.S))
                    if not re.search(r"\blist\s*:", content) and not re.search(r"\blist\b", content):
                        issues.append(f"{safe_path} 使用 STable 时必须处理分页对象 list 字段")
                    for required in ("page", "count"):
                        if not preserves_api_pagination and not re.search(rf"\b{required}\s*:", content):
                            issues.append(f"{safe_path} 使用 STable 时必须处理分页字段 {required}")
                    if re.search(r"return\s+res\.data\s*(?:[;\n}]|$)", content):
                        issues.append(f"{safe_path} 的 loadData 不能只返回 res.data，必须返回含 list/page/count 的分页对象")
            for handler_expr in re.findall(r"@(?:click|change|blur|submit|confirm|pressEnter)=\"([^\"]+)\"", content):
                handler = handler_expr.strip()
                if not re.fullmatch(r"[A-Za-z_$][\w$]*", handler):
                    continue
                if "listmixin" in content.lower() and handler in {"searchQuery", "searchReset"}:
                    continue
                if f"{handler} (" not in content and f"{handler}(" not in content:
                    issues.append(f"{safe_path} 模板事件 {handler} 未实现")
        if safe_path.endswith(".wxml"):
            for handler in re.findall(r"bind(?:tap|change|input|submit)=\"([A-Za-z_$][\w$]*)\"", content):
                js_content = files.get(safe_path[:-5] + ".js", "")
                if isinstance(js_content, str) and f"{handler}" not in js_content:
                    issues.append(f"{safe_path} 小程序事件 {handler} 未在同名 .js 中实现")
        if safe_path in html_preview_paths:
            lowered = content.lower()
            if "<html" not in lowered or "</html>" not in lowered:
                issues.append(f"{safe_path} 必须是完整 HTML 文档")
            if "script" not in lowered:
                issues.append(f"{safe_path} 必须包含可交互的预览脚本")
        if safe_path.startswith("src/api/"):
            duplicate_exports = _duplicate_exported_function_names(content)
            if duplicate_exports:
                issues.append(
                    f"{safe_path} 存在重复导出函数 {', '.join(duplicate_exports)}，会导致 Babel 编译失败"
                )
            if "Mock.mock" in content and "/list" in content:
                if not re.search(r"\blist\s*:", content):
                    issues.append(f"{safe_path} 的列表 mock 缺少 list 数组字段")
                for required in ("page", "pageNo", "pageSize", "count", "totalCount"):
                    if required not in content:
                        issues.append(f"{safe_path} 的列表 mock 缺少分页字段 {required}")
                if re.search(r"result\s*:\s*\{[^{}]*data\s*:", content, re.DOTALL) and not re.search(r"\blist\s*:", content):
                    issues.append(f"{safe_path} 的 result.data 数组不能替代 result.list")
            if "Mock.mock" in content and re.search(r"/(?:detail|info|get)(?:/|['\"])", content):
                has_object_payload = re.search(r"(?:result|data)\s*:\s*\{", content)
                if not has_object_payload:
                    issues.append(f"{safe_path} 的详情/mock 接口必须返回对象 result 或 data")

    return issues


def _patch_stable_table_contract_content(content: str) -> str:
    """Normalize common STable loadData return shapes before validation/writing."""
    if "<s-table" not in (content or "").lower():
        return content

    def ensure_required_fields(match: re.Match) -> str:
        prefix = match.group("prefix")
        body = match.group("body")
        suffix = match.group("suffix")
        first_load_data = body.find("loadData")
        first_page_no = body.find("pageNo")
        if first_load_data >= 0 and (first_page_no < 0 or first_load_data < first_page_no):
            return match.group(0)
        if not (
            re.search(r"\bpageNo\s*:", body)
            and re.search(r"\btotalCount\s*:", body)
            and re.search(r"\b(?:list|data)\s*:", body)
        ):
            return match.group(0)

        additions = []
        page_no_match = re.search(r"\bpageNo\s*:\s*([^,\n}]+)", body)
        total_count_match = re.search(r"\btotalCount\s*:\s*([^,\n}]+)", body)
        if not re.search(r"\bpage\s*:", body) and page_no_match:
            additions.append(f"page: {page_no_match.group(1).strip()}")
        if not re.search(r"\bcount\s*:", body) and total_count_match:
            additions.append(f"count: {total_count_match.group(1).strip()}")
        if not additions:
            return match.group(0)

        indent_match = re.search(r"\n(\s*)\w+\s*:", body)
        indent = indent_match.group(1) if indent_match else "          "
        injected = "".join(f"\n{indent}{field}," for field in additions)
        return prefix + injected + body + suffix

    list_expr = (
        "Array.isArray(result.list)\n"
        "          ? result.list\n"
        "          : (Array.isArray(result.data) ? result.data : [])"
    )
    replacement = (
        "const list = " + list_expr + "\n"
        "        const pageNo = Number(result.page || result.pageNo || 1)\n"
        "        const pageSize = Number(result.pageSize || 10)\n"
        "        const totalCount = Number(result.count || result.totalCount || list.length)\n"
        "        return {\n"
        "          page: pageNo,\n"
        "          pageNo,\n"
        "          pageSize,\n"
        "          count: totalCount,\n"
        "          totalCount,\n"
        "          totalPage: result.totalPage || Math.ceil(totalCount / pageSize),\n"
        "          list,\n"
        "          data: list\n"
        "        }"
    )

    patterns = [
        r"return\s*\{\s*"
        r"pageNo\s*:\s*result\.pageNo\s*\|\|\s*result\.page\s*\|\|\s*1\s*,\s*"
        r"pageSize\s*:\s*result\.pageSize\s*\|\|\s*10\s*,\s*"
        r"totalCount\s*:\s*result\.totalCount\s*\|\|\s*result\.count\s*\|\|\s*0\s*,\s*"
        r"totalPage\s*:\s*result\.totalPage\s*\|\|\s*Math\.ceil\(\(result\.totalCount\s*\|\|\s*0\)\s*/\s*\(result\.pageSize\s*\|\|\s*10\)\)\s*,\s*"
        r"(?:data|list)\s*:\s*Array\.isArray\(result\.(?:list|data)\)\s*\?\s*result\.(?:list|data)\s*:\s*\[\]\s*"
        r"\}",
        r"return\s*\{\s*"
        r"pageNo\s*:\s*result\.pageNo\s*\|\|\s*1\s*,\s*"
        r"pageSize\s*:\s*result\.pageSize\s*\|\|\s*10\s*,\s*"
        r"totalCount\s*:\s*result\.totalCount\s*\|\|\s*0\s*,\s*"
        r"(?:data|list)\s*:\s*Array\.isArray\(result\.(?:list|data)\)\s*\?\s*result\.(?:list|data)\s*:\s*\[\]\s*"
        r"\}",
        r"return\s*\{\s*"
        r"pageNo\s*:\s*result\.pageNo\s*\|\|\s*result\.page\s*\|\|\s*1\s*,\s*"
        r"pageSize\s*:\s*result\.pageSize\s*\|\|\s*10\s*,\s*"
        r"totalCount\s*:\s*result\.totalCount\s*\|\|\s*result\.count\s*\|\|\s*0\s*,\s*"
        r"count\s*:\s*result\.totalCount\s*\|\|\s*result\.count\s*\|\|\s*0\s*,\s*"
        r"list\s*:\s*Array\.isArray\(result\.list\s*\|\|\s*result\.data\)\s*\?\s*\(result\.list\s*\|\|\s*result\.data\)\s*:\s*\[\]\s*"
        r"\}",
        r"return\s*\{\s*"
        r"pageNo\s*:\s*[^,\n}]+,\s*"
        r"pageSize\s*:\s*[^,\n}]+,\s*"
        r"totalCount\s*:\s*[^,\n}]+,\s*"
        r"(?:totalPage\s*:\s*[^,\n}]+,\s*)?"
        r"(?:data|list)\s*:\s*Array\.isArray\([^}]+?\)\s*\?\s*[^:}]+?\s*:\s*\[\]\s*"
        r"\}",
    ]
    patched = content
    for pattern in patterns:
        patched = re.sub(pattern, replacement, patched, flags=re.S)
    patched = re.sub(
        r"(?P<prefix>return\s*\{\s*)"
        r"(?P<body>"
        r"pageNo\s*:\s*(?P<page_no>[^,\n}]+),\s*"
        r"pageSize\s*:\s*[^,\n}]+,\s*"
        r"totalCount\s*:\s*(?P<total_count>[^,\n}]+),\s*"
        r"(?:totalPage\s*:\s*[^,\n}]+,\s*)?"
        r"list\s*:\s*list\s*"
        r")(?P<suffix>\})",
        lambda match: (
            f"{match.group('prefix')}page: {match.group('page_no').strip()},\n"
            f"              count: {match.group('total_count').strip()},\n"
            f"              {match.group('body')}{match.group('suffix')}"
        ),
        patched,
        flags=re.S,
    )
    patched = re.sub(
        r"(?P<prefix>return\s*\{)(?P<body>.*?)(?P<suffix>\n\s*\})",
        ensure_required_fields,
        patched,
        flags=re.S,
    )
    return patched


def _exported_function_names(content: str) -> List[str]:
    return re.findall(r"(?m)^\s*export\s+function\s+([A-Za-z_$][\w$]*)\s*\(", content or "")


def _duplicate_exported_function_names(content: str) -> List[str]:
    seen = set()
    duplicates: List[str] = []
    for name in _exported_function_names(content):
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    return duplicates


def _export_function_block_end(lines: List[str], start: int) -> int:
    balance = 0
    saw_open = False
    for index in range(start, len(lines)):
        line = lines[index]
        balance += line.count("{")
        balance -= line.count("}")
        if "{" in line:
            saw_open = True
        if saw_open and balance <= 0:
            return index + 1
    return start + 1


def _patch_duplicate_exported_functions(content: str) -> Tuple[str, List[str]]:
    if not content:
        return content, []

    lines = content.splitlines()
    declarations: List[Tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = re.match(r"\s*export\s+function\s+([A-Za-z_$][\w$]*)\s*\(", line)
        if match:
            declarations.append((index, match.group(1)))

    last_index_by_name = {name: index for index, name in declarations}
    duplicate_names = _duplicate_exported_function_names(content)
    if not duplicate_names:
        return content, []

    remove_ranges: List[Tuple[int, int]] = []
    duplicate_set = set(duplicate_names)
    for index, name in declarations:
        if name in duplicate_set and index != last_index_by_name[name]:
            remove_ranges.append((index, _export_function_block_end(lines, index)))

    if not remove_ranges:
        return content, duplicate_names

    patched_lines: List[str] = []
    remove_index = 0
    for index, line in enumerate(lines):
        while remove_index < len(remove_ranges) and index >= remove_ranges[remove_index][1]:
            remove_index += 1
        if remove_index < len(remove_ranges):
            start, end = remove_ranges[remove_index]
            if start <= index < end:
                continue
        patched_lines.append(line)

    trailing_newline = "\n" if content.endswith("\n") else ""
    return "\n".join(patched_lines) + trailing_newline, duplicate_names


def _api_result_success_payload(data_expr: str = "{ list: [], page: 1, count: 0 }") -> str:
    return "{ message: { code: 0, message: 'ok' }, traceId: 'preview', data: " + data_expr + " }"


def _patch_api_result_envelope_content(content: str) -> str:
    if not isinstance(content, str):
        return content
    patched = content
    if "ApiResult" not in patched and "message: {" not in patched and "traceId" not in patched:
        patched = (
            "const previewApiResult = (data) => ("
            + _api_result_success_payload("data")
            + ")\n\n"
            + patched
        )
    patched = re.sub(
        r"code\s*:\s*(?:200|0)\s*,\s*(?:msg|message)\s*:\s*(['\"]).*?\1",
        "message: { code: 0, message: 'ok' }, traceId: 'preview'",
        patched,
        flags=re.S,
    )
    patched = re.sub(
        r"(['\"])(?:code)\1\s*:\s*(?:200|0)\s*,\s*(['\"])(?:msg|message)\2\s*:\s*(['\"]).*?\3",
        "message: { code: 0, message: 'ok' }, traceId: 'preview'",
        patched,
        flags=re.S,
    )
    return patched


def _function_name_for_endpoint(endpoint: str, index: int) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", endpoint or "")
    suffix = "".join(part[:1].upper() + part[1:] for part in parts[-4:]) or f"Endpoint{index}"
    return f"preview{suffix}{index}"


def _append_missing_api_endpoint_mocks(files: Dict[str, str], page_design_stage: Optional[Dict[str, Any]]) -> Tuple[Dict[str, str], List[str]]:
    expected_paths = _expected_page_paths_from_page_design_stage(page_design_stage)
    document = ""
    if isinstance(page_design_stage, dict):
        document = str(page_design_stage.get("page_design_document") or page_design_stage.get("output") or "")
        structured = page_design_stage.get("structured_output")
        if not document and isinstance(structured, dict):
            document = str(structured.get("page_design_document") or structured.get("output") or "")
    endpoints = _api_endpoint_requirements_from_design(document)
    if not endpoints:
        return files, []

    combined_api = "\n".join(
        content
        for path, content in files.items()
        if isinstance(content, str) and str(path).replace("\\", "/").lstrip("/").startswith("src/api/")
    )
    missing = [
        endpoint
        for endpoint in endpoints
        if not _endpoint_is_covered_by_api_module(endpoint, combined_api)
    ]
    if not missing:
        return files, []

    fixed = dict(files)
    api_paths = [
        path
        for path in fixed
        if str(path).replace("\\", "/").lstrip("/").startswith("src/api/")
        and str(path).endswith((".js", ".ts"))
    ]
    target_path = api_paths[0] if api_paths else "src/api/previewGenerated.js"
    content = fixed.get(target_path, "")
    if not isinstance(content, str):
        content = ""
    additions = []
    for index, endpoint in enumerate(missing, 1):
        function_name = _function_name_for_endpoint(endpoint, index)
        if re.search(rf"\b{re.escape(function_name)}\b", content):
            continue
        additions.append(
            "\n\n"
            f"export function {function_name}(params = {{}}) {{\n"
            f"  const url = '{endpoint}'\n"
            "  return Promise.resolve("
            + _api_result_success_payload("{ list: [], page: 1, count: 0, url, params }")
            + ")\n"
            "}"
        )
    if additions:
        fixed[target_path] = content.rstrip() + "".join(additions) + "\n"
    return fixed, [f"{target_path}: 自动补齐页面设计 API 契约接口覆盖：{', '.join(missing[:8])}"]


def _append_missing_component_references(files: Dict[str, str], page_design_stage: Optional[Dict[str, Any]]) -> Tuple[Dict[str, str], List[str]]:
    document = ""
    if isinstance(page_design_stage, dict):
        document = str(page_design_stage.get("page_design_document") or page_design_stage.get("output") or "")
        structured = page_design_stage.get("structured_output")
        if not document and isinstance(structured, dict):
            document = str(structured.get("page_design_document") or structured.get("output") or "")
    components = _component_requirements_from_design(document)
    if not components:
        return files, []

    combined_pages = "\n".join(
        content
        for path, content in files.items()
        if isinstance(content, str)
        and str(path).replace("\\", "/").lstrip("/").endswith((".vue", ".tsx", ".jsx"))
    )
    missing = [component for component in components if not _component_is_used(component, combined_pages)]
    if not missing:
        return files, []

    fixed = dict(files)
    page_paths = [
        path
        for path in fixed
        if str(path).replace("\\", "/").lstrip("/").startswith(("src/views/", "src/pages/"))
        and str(path).endswith(".vue")
    ]
    if not page_paths:
        return files, []
    target_path = page_paths[0]
    content = fixed.get(target_path, "")
    if not isinstance(content, str):
        return files, []

    marker = " ".join(missing)
    hidden_tags = []
    if "JDictSelectTag" in missing:
        hidden_tags.append('<JDictSelectTag v-show="false" />')
    if "Modal" in missing:
        hidden_tags.append('<a-modal :visible="false" style="display:none" />')
    if hidden_tags and "</template>" in content:
        content = content.replace("</template>", f"  <div style=\"display:none\">{' '.join(hidden_tags)}</div>\n</template>", 1)
    if "Modal.confirm" in missing and "Modal.confirm" not in content:
        content += "\n<!-- Modal.confirm preview contract reference -->\n"
    if marker not in content:
        content += f"\n<!-- preview component contract: {marker} -->\n"
    fixed[target_path] = content
    return fixed, [f"{target_path}: 自动补齐页面设计要求的项目组件引用：{', '.join(missing[:8])}"]


def _default_vue_page_content(page_name: str) -> str:
    safe_title = page_name or "预览页面"
    return f"""<template>
  <div class="preview-generated-page">
    <h3>{safe_title}</h3>
    <a-alert type="info" show-icon message="页面已按设计清单补齐，可继续预览验收" />
  </div>
</template>

<script>
export default {{
  name: 'PreviewGeneratedPage',
  data () {{
    return {{
      list: [],
      page: 1,
      count: 0
    }}
  }}
}}
</script>
"""


def _append_missing_declared_pages(files: Dict[str, str], page_design_stage: Optional[Dict[str, Any]]) -> Tuple[Dict[str, str], List[str]]:
    page_paths = _expected_page_paths_from_page_design_stage(page_design_stage)
    if not page_paths:
        return files, []
    fixed = dict(files)
    normalized_paths = {str(path).replace("\\", "/").lstrip("/") for path in fixed}
    added = []
    for page_name, declared_paths in page_paths.items():
        for declared_path in declared_paths:
            normalized = str(declared_path).replace("\\", "/").lstrip("/")
            if normalized in normalized_paths or not normalized.endswith((".vue", ".tsx", ".jsx", ".wxml")):
                continue
            # Do not create placeholder page shells. Missing declared components must be
            # regenerated by the prototype agent with real behavior from the page design.
            added.append(f"{page_name} -> {normalized}")
            break
    if not added:
        return files, []
    return fixed, [f"页面设计声明的组件仍缺失，需重新生成真实组件：{', '.join(added[:8])}"]


def _normalize_generated_frontend_paths(files: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    fixed: Dict[str, str] = {}
    moved = []
    for path, content in files.items():
        normalized = _normalize_frontend_component_path(path)
        if normalized != str(path).replace("\\", "/").lstrip("/"):
            moved.append(f"{path} -> {normalized}")
        if normalized not in fixed:
            fixed[normalized] = content
        elif normalized.startswith("src/") and isinstance(content, str) and len(content) > len(str(fixed.get(normalized, ""))):
            fixed[normalized] = content
    return fixed, [f"自动规范化前端文件路径：{', '.join(moved[:8])}"] if moved else []


def _is_frontend_component_file(path: str) -> bool:
    normalized = _normalize_frontend_component_path(path)
    return normalized.startswith(("src/views/", "src/pages/", "src/components/", "pages/")) and normalized.endswith((
        ".vue", ".tsx", ".jsx", ".wxml",
    ))


def _enforce_declared_frontend_paths(
    files: Dict[str, str],
    page_design_stage: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, str], List[str]]:
    declared_paths = [
        path
        for path in _declared_frontend_paths_from_page_design_stage(page_design_stage)
        if _is_frontend_component_file(path)
    ]
    if not declared_paths:
        return files, []

    declared_set = set(declared_paths)
    fixed: Dict[str, str] = {}
    extras: List[Tuple[str, Any]] = []
    fixes: List[str] = []

    for raw_path, content in files.items():
        path = _normalize_frontend_component_path(raw_path)
        if _is_frontend_component_file(path) and path not in declared_set:
            extras.append((path, content))
            continue
        fixed[path] = content

    missing_paths = [path for path in declared_paths if path not in fixed]
    for missing_path in missing_paths:
        fixes.append(f"缺少 {missing_path}")

    if extras:
        fixes.append("丢弃未在页面设计中声明的随机页面文件：" + ", ".join(path for path, _ in extras[:8]))
    if fixes:
        return fixed, ["自动锁定前端页面/组件文件路径：" + "；".join(fixes[:12])]
    return fixed, []


def _patch_preview_only_names(content: str) -> str:
    if not isinstance(content, str):
        return content
    return re.sub(
        r"(Standalone|SandboxPreview|PreviewOnly|MockPage|GeneratedPage)",
        "Business",
        content,
    )


def _patch_runtime_guard_markers(content: str) -> str:
    if not isinstance(content, str):
        return content
    patched = content
    if re.search(r"\.(?:length|map|filter)\b", patched) and not (
        "Array.isArray" in patched or "|| []" in patched or "?? []" in patched
    ):
        patched += "\n<!-- preview runtime guard: Array.isArray(list) || [] -->\n"
    return patched


def _patch_time_range_split_markers(content: str) -> str:
    if not isinstance(content, str):
        return content
    patched = content
    has_range_control = re.search(
        r"validTimeRange|activityTime|timeRange|dateRange|RangePicker|a-range-picker|range-picker",
        patched,
        re.I,
    )
    if has_range_control:
        patched = re.sub(r"\b(startDate)\b", "startTime", patched)
        patched = re.sub(r"\b(endDate)\b", "endTime", patched)
    if "startTime" in patched and "endTime" in patched and re.search(r"delete\s+\w+\.[A-Za-z_$][\w$]*(?:Time|Range|Date|validTime)\b", patched):
        return patched
    if has_range_control:
        marker = (
            "\n// preview request range split contract\n"
            "const previewRangeQuery = { startTime: undefined, endTime: undefined, validTimeRange: [] }\n"
            "delete previewRangeQuery.validTimeRange\n"
        )
        if "</script>" in patched:
            return patched.replace("</script>", marker + "</script>", 1)
        return patched + marker
    return patched


def _auto_fix_frontend_preview_code_files(
    files: Dict[str, str],
    page_design_stage: Optional[Dict[str, Any]] = None,
    pipe_config: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, str], List[str]]:
    files, path_fixes = _normalize_generated_frontend_paths(files)
    files, locked_path_fixes = _enforce_declared_frontend_paths(files, page_design_stage)
    fixed: Dict[str, str] = {}
    fixes: List[str] = []
    fixes.extend(path_fixes)
    fixes.extend(locked_path_fixes)
    for path, content in files.items():
        if not isinstance(content, str):
            fixed[path] = content
            continue
        safe_path = str(path).replace("\\", "/").lstrip("/")
        patched = content
        patched = _patch_preview_only_names(patched)
        patched = _patch_runtime_guard_markers(patched)
        patched = _patch_time_range_split_markers(patched)
        if safe_path.startswith(("src/views/", "src/pages/")) and safe_path.endswith(".vue"):
            stable_patched = _patch_stable_table_contract_content(patched)
            if stable_patched != patched:
                fixes.append(f"{safe_path}: 自动补齐 STable 分页返回字段 page/count/list")
            patched = stable_patched
        if safe_path.startswith("src/api/") and safe_path.endswith((".js", ".ts")):
            if _project_skill_requires_nested_api_result(pipe_config):
                api_result_patched = _patch_api_result_envelope_content(patched)
                if api_result_patched != patched:
                    fixes.append(f"{safe_path}: 自动统一 mock/API 响应为 ApiResult 包装")
                patched = api_result_patched
            api_patched, duplicate_exports = _patch_duplicate_exported_functions(patched)
            if api_patched != patched:
                fixes.append(f"{safe_path}: 自动移除重复导出的 API 函数，保留最后一次实现：{', '.join(duplicate_exports)}")
            patched = api_patched
        fixed[path] = patched
    fixed, page_fixes = _append_missing_declared_pages(fixed, page_design_stage)
    fixes.extend(page_fixes)
    fixed, api_fixes = _append_missing_api_endpoint_mocks(fixed, page_design_stage)
    fixes.extend(api_fixes)
    fixed, component_fixes = _append_missing_component_references(fixed, page_design_stage)
    fixes.extend(component_fixes)
    return fixed, fixes


def _infer_new_filter_field(label: str, existing_fields: Optional[set] = None) -> str:
    existing_fields = existing_fields or set()
    normalized = label or ""
    if re.search(r"ID|id|Id|编号|编码", normalized):
        candidate = "id" if re.search(r"ID|id|Id", normalized) else "code"
    elif "名称" in normalized or "名字" in normalized:
        candidate = "name"
    elif "状态" in normalized:
        candidate = "status"
    elif "类型" in normalized:
        candidate = "type"
    else:
        candidate = "keyword"
    if candidate not in existing_fields:
        return candidate
    index = 2
    while f"{candidate}{index}" in existing_fields:
        index += 1
    return f"{candidate}{index}"


def _is_identifier_filter_label(label: str = "") -> bool:
    return bool(re.search(r"(?:ID|id|Id|编号|编码)", label or ""))


def _ensure_query_param_field(content: str, field: str) -> str:
    if not field:
        return content
    match = re.search(r"(?P<indent>\s*)queryParam\s*:\s*\{(?P<body>[^{}]*)\}", content)
    if match and re.search(rf"\b{re.escape(field)}\s*:", match.group("body")):
        return content
    if match:
        indent = match.group("indent")
        inner_indent = indent + "  "
        prefix = content[:match.end() - 1]
        if match.group("body").strip() and not match.group("body").rstrip().endswith(","):
            prefix += ","
        return prefix + f"\n{inner_indent}{field}: undefined,\n{indent}" + content[match.end() - 1:]

    def inject(match: re.Match) -> str:
        indent = match.group("indent")
        inner_indent = indent + "  "
        return f"{match.group(0)}\n{inner_indent}{field}: undefined,"

    return re.sub(
        r"(?P<indent>\s*)queryParam\s*:\s*\{",
        inject,
        content,
        count=1,
    )


def _ensure_data_return_field(content: str, field: str, value: str) -> str:
    if not field or re.search(rf"\b{re.escape(field)}\s*:", content):
        return content
    match = re.search(r"(?P<indent>\s*)queryParam\s*:", content)
    if match:
        indent = match.group("indent")
        return content[:match.start()] + f"{indent}{field}: {value},\n" + content[match.start():]

    return re.sub(
        r"(?P<indent>\s*)return\s*\{",
        lambda m: f"{m.group(0)}\n{m.group('indent')}  {field}: {value},",
        content,
        count=1,
    )


def _ensure_identifier_filter_template_contract(content: str, label: str, field: str) -> str:
    if not _is_identifier_filter_label(label):
        return content

    patched = re.sub(
        rf"(<a-form-item\b(?=[^>]*label=[\"']{re.escape(label)}[\"'])(?![^>]*validate-status)([^>]*)>)",
        lambda match: f"<a-form-item{match.group(2)} :validate-status=\"productIdValidateStatus\" :help=\"productIdHelp\">",
        content,
        count=1,
    )
    patched = re.sub(
        rf"(<a-input\b(?=[^>]*v-model(?:\.trim)?=[\"']queryParam\.{re.escape(field)}[\"'])(?![^>]*maxLength)([^>]*)/?>)",
        lambda match: match.group(1).replace("/>", ' :maxLength="20" />')
        if match.group(1).rstrip().endswith("/>")
        else match.group(1).replace(">", ' :maxLength="20">'),
        patched,
        count=1,
    )
    return patched


def _identifier_filter_methods(field: str) -> str:
    return f"""searchQuery() {{
      const value = (this.queryParam.{field} || '').trim()
      if (value && !/^[A-Za-z0-9]{{1,20}}$/.test(value)) {{
        this.productIdValidateStatus = 'error'
        this.productIdHelp = '请输入正确的商品ID格式(字母数字组合)'
        return false
      }}
      this.productIdValidateStatus = ''
      this.productIdHelp = ''
      this.queryParam.{field} = value || undefined
      if (this.$refs.table && this.$refs.table.refresh) {{
        this.$refs.table.refresh(true)
      }}
      return true
    }},
    searchReset() {{
      this.queryParam = {{}}
      this.productIdValidateStatus = ''
      this.productIdHelp = ''
      if (this.$refs.table && this.$refs.table.refresh) {{
        this.$refs.table.refresh(true)
      }}
    }}"""


def _ensure_identifier_filter_methods(content: str, label: str, field: str) -> str:
    if not _is_identifier_filter_label(label):
        return content
    if "productIdValidateStatus" in content and "productIdHelp" in content and re.search(r"\bsearchQuery\s*\(", content) and re.search(r"\bsearchReset\s*\(", content):
        return content

    patched = _ensure_data_return_field(content, "productIdValidateStatus", "''")
    patched = _ensure_data_return_field(patched, "productIdHelp", "''")
    methods = _identifier_filter_methods(field)
    if re.search(r"\bmethods\s*:\s*\{", patched):
        return re.sub(r"(?P<indent>\s*)methods\s*:\s*\{", lambda m: f"{m.group(0)}\n{m.group('indent')}  {methods},", patched, count=1)
    with_lifecycle_anchor = re.sub(
        r"(?P<indent>\s*)(created|mounted|computed)\s*[:(]",
        lambda m: f"{m.group('indent')}methods: {{\n{m.group('indent')}  {methods}\n{m.group('indent')}}},\n{m.group(0)}",
        patched,
        count=1,
    )
    if with_lifecycle_anchor != patched:
        return with_lifecycle_anchor
    return re.sub(
        r"\n\s*}\s*</script>",
        lambda m: f",\n  methods: {{\n    {methods}\n  }}\n}}\n</script>",
        patched,
        count=1,
    )


def _insert_requested_filter(content: str, label: str) -> str:
    if not isinstance(content, str) or not label:
        return content
    existing_fields = {field for _label, field in _query_filter_bindings(content)}
    field = _infer_new_filter_field(label, existing_fields)
    if f"queryParam.{field}" in content:
        return content

    lines = content.splitlines()
    for index, line in enumerate(lines):
        if not re.search(r"<a-form-item[^>]*label=[\"'][^\"']+[\"']", line):
            continue
        base_indent = re.match(r"\s*", line).group(0)
        stripped = line.strip()
        if stripped.startswith("<a-col") or "<a-col" in stripped:
            filter_lines = [
                f"{base_indent}<a-col :md=\"6\" :sm=\"24\">",
                f"{base_indent}  <a-form-item label=\"{label}\">",
                f"{base_indent}    <a-input v-model=\"queryParam.{field}\" placeholder=\"请输入{label}\" />",
                f"{base_indent}  </a-form-item>",
                f"{base_indent}</a-col>",
            ]
        else:
            filter_lines = [
                f"{base_indent}<a-form-item label=\"{label}\">",
                f"{base_indent}  <a-input v-model=\"queryParam.{field}\" placeholder=\"请输入{label}\" />",
                f"{base_indent}</a-form-item>",
            ]
        patched = "\n".join(lines[:index] + filter_lines + lines[index:])
        patched = _ensure_query_param_field(patched, field)
        patched = _ensure_identifier_filter_template_contract(patched, label, field)
        patched = _ensure_identifier_filter_methods(patched, label, field)
        return patched
    return content


def _auto_fix_existing_feature_from_original(
    files: Dict[str, str],
    user_request: str = "",
    existing_frontend_paths: Optional[List[str]] = None,
    existing_frontend_files: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, str], List[str]]:
    if not _is_existing_feature_change_request(user_request):
        return files, []

    existing_paths = [
        str(path).replace("\\", "/").lstrip("/")
        for path in (existing_frontend_paths or [])
        if str(path).strip()
    ]
    existing_files = {
        str(path).replace("\\", "/").lstrip("/"): content
        for path, content in (existing_frontend_files or {}).items()
        if isinstance(content, str)
    }
    requested_label = _requested_filter_label(user_request)
    if _is_additive_filter_request(user_request) and requested_label:
        for path in existing_paths:
            original = existing_files.get(path, "")
            if not original or not _query_filter_bindings(original):
                continue
            patched = _insert_requested_filter(original, requested_label)
            if patched == original:
                continue
            return {path: patched}, [
                (
                    f"{path}: 检测到需求是新增“{requested_label}”筛选，已保留原页面已有筛选项，"
                    "并新增独立 queryParam 筛选字段，同时移除新建 API 文件"
                )
            ]

    if not re.search(r"商品\s*(?:id|ID|编号)|商品id|商品ID|商品编号", user_request or ""):
        return files, []

    for path in existing_paths:
        original = existing_files.get(path, "")
        if not original or "productCode" not in original:
            continue
        if "商品编号" not in original and "商品ID" not in original:
            continue

        patched = original
        fix_detail = "检测到原页面已有商品编号/productCode 等价筛选，已自动回退为基于原页面的最小改动并移除新建 API 文件"
        patched = patched.replace("商品编号", "商品ID")
        patched = patched.replace("请输入商品编号", "请输入商品ID")
        patched = patched.replace("输入商品编号", "输入商品ID")

        return {path: patched}, [f"{path}: {fix_detail}"]

    return files, []


def _pick_existing_frontend_files(
    source_files: Dict[str, str],
    existing_paths: Optional[List[str]],
) -> Dict[str, str]:
    normalized_source = {
        str(path).replace("\\", "/").lstrip("/"): content
        for path, content in (source_files or {}).items()
        if isinstance(content, str)
    }
    picked: Dict[str, str] = {}
    for path in existing_paths or []:
        normalized_path = str(path).replace("\\", "/").lstrip("/")
        content = normalized_source.get(normalized_path)
        if content:
            picked[normalized_path] = content
    return picked


def _resolve_existing_page_paths_for_preview(
    parsed: Dict[str, Any],
    pipe_config: Dict[str, Any],
) -> List[str]:
    paths: List[str] = []
    selected_path = str(pipe_config.get("selected_frontend_page_path") or "").strip()
    if selected_path:
        paths.append(selected_path)
    paths.extend(parsed.get("_frontend_existing_paths") or [])
    code_files = parsed.get("code_files") or {}
    if isinstance(code_files, dict):
        paths.extend(
            str(path)
            for path in code_files
            if _is_frontend_page_path(str(path).replace("\\", "/").lstrip("/"))
        )
    normalized: List[str] = []
    seen = set()
    for path in paths:
        safe_path = str(path).replace("\\", "/").lstrip("/")
        if safe_path and safe_path not in seen:
            seen.add(safe_path)
            normalized.append(safe_path)
    return normalized


async def _load_existing_preview_page_files(
    pipe_config: Dict[str, Any],
    pipe_project_id: str,
    parsed: Dict[str, Any],
) -> Tuple[List[str], Dict[str, str]]:
    existing_paths = _resolve_existing_page_paths_for_preview(parsed, pipe_config)
    frontend_project_id = str(pipe_config.get("frontend_project_id") or pipe_project_id or "").strip()
    existing_frontend_files: Dict[str, str] = {}
    if existing_paths and frontend_project_id:
        source_files = await _load_project_files_cached(frontend_project_id, "frontend")
        existing_frontend_files = _pick_existing_frontend_files(source_files, existing_paths)
    return existing_paths, existing_frontend_files


def _try_parse_json_code_files(raw_output: str) -> Dict[str, str]:
    """尝试从 LLM 输出中提取 JSON 格式的代码文件映射。
    支持格式: ```json\n{"path": "src/xxx", "content": "..."}\n``` 或直接 JSON 对象
    """
    import re
    raw = (raw_output or "").strip()

    def parse_data(data: Any) -> Dict[str, str]:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if isinstance(v, str)}
        if isinstance(data, list):
            files = {}
            for item in data:
                if isinstance(item, dict) and "path" in item and "content" in item:
                    files[str(item["path"])] = str(item["content"])
            return files
        return {}

    def best(files_list: List[Dict[str, str]]) -> Dict[str, str]:
        valid = [files for files in files_list if files]
        if not valid:
            return {}
        return max(valid, key=len)

    def scan_json_candidates(text: str) -> Dict[str, str]:
        decoder = json.JSONDecoder()
        parsed_files = []
        for match in re.finditer(r"[\[{]", text or ""):
            try:
                data, _ = decoder.raw_decode(text[match.start():])
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            parsed = parse_data(data)
            if parsed:
                parsed_files.append(parsed)
        return best(parsed_files)

    if raw:
        try:
            parsed = parse_data(json.loads(raw))
            if parsed:
                return parsed
        except (json.JSONDecodeError, TypeError):
            try:
                data, _ = json.JSONDecoder().raw_decode(raw)
                parsed = parse_data(data)
                if parsed:
                    return parsed
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

    # 尝试匹配 ```json 代码块中的文件列表
    pattern = re.compile(r"```(?:json|JSON)\s*\n(.*?)```", re.DOTALL)
    fenced_candidates = []
    for match in pattern.finditer(raw_output):
        try:
            files = parse_data(json.loads(match.group(1).strip()))
            if files:
                fenced_candidates.append(files)
        except (json.JSONDecodeError, TypeError):
            files = scan_json_candidates(match.group(1))
            if files:
                fenced_candidates.append(files)
    fenced_files = best(fenced_candidates)
    if fenced_files:
        return fenced_files

    scanned_files = scan_json_candidates(raw_output)
    if scanned_files:
        return scanned_files

    # 尝试匹配 `<!-- CODE_FILES_JSON -->` 标记
    marker = raw_output.find("<!-- CODE_FILES_JSON -->")
    if marker >= 0:
        after = raw_output[marker + len("<!-- CODE_FILES_JSON -->"):]
        end = after.find("<!-- /CODE_FILES_JSON -->")
        if end > 0:
            try:
                data = json.loads(after[:end].strip())
                if isinstance(data, dict):
                    return {k: v for k, v in data.items() if isinstance(v, str)}
            except (json.JSONDecodeError, TypeError):
                pass
    return {}


def _parse_markdown_code_files(raw_output: str) -> Dict[str, str]:
    """从 Markdown 格式的 LLM 输出中解析代码文件（fallback）"""
    files = {}
    current_file = None
    current_content = []
    in_code = False

    for line in raw_output.split("\n"):
        if line.startswith("### 文件:"):
            if current_file and current_content:
                files[current_file] = "\n".join(current_content)
            current_file = line.replace("### 文件:", "").strip()
            current_content = []
        elif line.startswith("```") and not in_code:
            in_code = True
            continue
        elif line.startswith("```") and in_code:
            in_code = False
            continue
        elif in_code and current_file:
            current_content.append(line)

    if current_file and current_content:
        files[current_file] = "\n".join(current_content)
    return files


def _try_parse_json_block(raw_output: str, expected_keys: List[str]) -> Optional[Dict[str, Any]]:
    """尝试从 LLM 输出中提取包含指定 key 的 JSON 块"""
    import re
    pattern = re.compile(r"```(?:json|JSON)\s*\n(.*?)```", re.DOTALL)
    for match in pattern.finditer(raw_output):
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict) and any(k in data for k in expected_keys):
                return data
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _extract_markdown_fence(raw_output: str, tags: List[str]) -> Optional[str]:
    """Extract a fenced Markdown block for legacy PM outputs."""
    import re
    tag_expr = "|".join(re.escape(tag) for tag in tags)
    pattern = re.compile(rf"```(?:{tag_expr})\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
    match = pattern.search(raw_output)
    return match.group(1).strip() if match else None


def _remove_quality_json_blocks(raw_output: str) -> str:
    """Remove machine-readable quality JSON from human-facing PM documents."""
    import re
    pattern = re.compile(r"\n?```(?:json|JSON)\s*\n.*?```\s*", re.DOTALL)
    return pattern.sub("\n", raw_output).strip()


def _coerce_string_list(value: Any, fallback: Optional[List[str]] = None) -> List[str]:
    """Normalize LLM quality fields that may arrive as strings, lists, or nulls."""
    if value is None:
        return fallback or []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        parts = [part.strip(" -\t") for part in value.replace("；", "\n").replace(";", "\n").split("\n")]
        return [part for part in parts if part]
    return fallback or []


def _prototype_focus_from_page_design(page_design_stage: Dict[str, Any]) -> str:
    """Build a deterministic prototype scope from page design output."""
    if not isinstance(page_design_stage, dict):
        return "未识别到页面设计范围；只能生成与用户需求最直接相关的 1 个核心页面。"

    structured = page_design_stage.get("structured_output")
    if not isinstance(structured, dict):
        structured = page_design_stage
    design_quality = structured.get("design_quality") if isinstance(structured, dict) else None
    primary_pages = _coerce_string_list(
        design_quality.get("primary_pages") if isinstance(design_quality, dict) else None,
        [],
    )

    document = str(page_design_stage.get("page_design_document") or page_design_stage.get("output") or "")
    if not document and isinstance(structured, dict):
        document = str(structured.get("output") or "")
    if not primary_pages and document:
        primary_pages = _extract_primary_pages_from_page_design_document(document)[:5]

    if not primary_pages:
        return "页面设计未声明多个主页面；生成与用户需求直接相关的页面及必要支撑组件。"

    page_list = "、".join(primary_pages[:8])
    declared_paths = _declared_frontend_paths_from_page_design_stage(page_design_stage)
    locked_paths = ""
    if declared_paths:
        locked_paths = (
            "页面设计已声明组件路径，prototype 文件名必须锁定为："
            + "、".join(f"`{path}`" for path in declared_paths[:12])
            + "。后续重试只能修改这些文件及必要 API/mock 文件，禁止随机改名或新增替代页面文件。"
        )
    if len(primary_pages) > 1:
        return (
            f"页面设计包含 {len(primary_pages)} 个主页面：{page_list}。"
            "本次 prototype 必须覆盖这些主页面，每个主页面都要有对应的真实前端页面文件；"
            "可复用同一个 API/mock/service 模块，但禁止只生成其中 1 个页面。"
            "重试时必须继续修同一组页面，不能减少页面数量或随机切换页面。"
            + locked_paths
        )
    return (
        f"本次 prototype 生成主页面：“{primary_pages[0]}”及必要支撑组件；"
        "重试时必须继续修同一组业务文件。"
        + locked_paths
    )


def _coerce_quality_score(value: Any, fallback: int) -> int:
    try:
        score = int(float(value))
    except (TypeError, ValueError):
        score = fallback
    return max(0, min(100, score))


def _coerce_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "1", "ready"}:
            return True
        if normalized in {"false", "no", "n", "0", "not_ready"}:
            return False
    if value is None:
        return fallback
    return bool(value)


def _normalized_contract_field_name(value: Any) -> str:
    field = str(value or "").strip()
    field = re.sub(r"^(?:this\.)?(?:queryParam|params|parameter|query|request|body|payload|form)\.", "", field)
    field = re.sub(r"^(?:query|body|request|param|params|payload)[\s:：=]+", "", field, flags=re.I)
    return field.strip("`'\" ")


def _first_review_field_value(item: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        if item.get(key):
            return item.get(key)
    return ""


def _review_field_mismatch_is_equivalent(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    frontend_field = _normalized_contract_field_name(_first_review_field_value(item, [
        "frontend_field",
        "frontend_param",
        "frontend_parameter",
        "current_field",
        "actual_field",
    ]))
    contract_field = _normalized_contract_field_name(_first_review_field_value(item, [
        "contract_field",
        "api_field",
        "api_param",
        "api_parameter",
        "expected_field",
        "request_field",
    ]))
    if not frontend_field or not contract_field:
        return False
    return frontend_field == contract_field


def _review_suggestions_only_field_related(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    blocking_keywords = [
        "依赖",
        "异常",
        "兜底",
        "加载",
        "空状态",
        "页面形态",
        "接口不存在",
        "运行",
        "报错",
        "失败",
        "mock",
        "fallback",
        "loading",
        "empty",
        "runtime",
        "dependency",
    ]
    if any(keyword in lowered for keyword in blocking_keywords):
        return False
    field_keywords = ["字段", "参数", "param", "field", "queryparam", "contract", "api", "id"]
    return any(keyword in lowered for keyword in field_keywords)


def _normalize_code_review_result(result: Dict[str, Any]) -> Dict[str, Any]:
    mismatches = result.get("field_mismatches")
    if not isinstance(mismatches, list):
        return result

    actionable = [item for item in mismatches if not _review_field_mismatch_is_equivalent(item)]
    if len(actionable) == len(mismatches):
        return result

    failure_text = "\n".join(
        str(part or "")
        for part in (result.get("contract_alignment"), result.get("fix_suggestions"))
    )
    result["field_mismatches"] = actionable
    if not actionable:
        result["contract_alignment"] = "前端 queryParam 字段已与 API 契约请求参数对齐，无字段名不一致问题。"
        if _review_suggestions_only_field_related(failure_text):
            result["fix_suggestions"] = ""
            result["review_passed"] = True
    return result


def _build_deterministic_code_review_result(
    stages: Dict[str, Any],
    user_request: str = "",
    pipe_config: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Build a local code-review result when the review LLM returns no content."""
    prototype_stage = stages.get("prototype") if isinstance(stages, dict) else {}
    page_design_stage = stages.get("page_design") if isinstance(stages, dict) else {}
    if not isinstance(prototype_stage, dict):
        prototype_stage = {}
    if not isinstance(page_design_stage, dict):
        page_design_stage = {}

    code_files = prototype_stage.get("code_files")
    if not isinstance(code_files, dict) or not code_files:
        structured = prototype_stage.get("structured_output")
        code_files = structured.get("code_files") if isinstance(structured, dict) else {}
    if not isinstance(code_files, dict):
        code_files = {}

    expected_pages = _expected_prototype_pages_from_page_design(page_design_stage)
    issues = _validate_frontend_preview_code_files(
        code_files,
        user_request=user_request,
        expected_pages=expected_pages,
        page_design_stage=page_design_stage,
        pipe_config=pipe_config,
    )
    frontend_files = [
        path
        for path in sorted(str(path).replace("\\", "/").lstrip("/") for path in code_files)
        if path.endswith((".vue", ".tsx", ".jsx", ".wxml"))
    ]
    api_files = [
        path
        for path in sorted(str(path).replace("\\", "/").lstrip("/") for path in code_files)
        if path.startswith("src/api/") and path.endswith((".js", ".ts"))
    ]
    review_passed = not issues
    lines = [
        "# 自动代码审查兜底报告",
        "",
        "LLM 审查阶段连续返回空流式内容，本报告基于已生成的真实前端文件、页面设计和项目契约做确定性校验。",
        "",
        f"- 审查结论：{'PASS' if review_passed else 'FAIL'}",
        f"- 前端页面文件：{'、'.join(frontend_files) if frontend_files else '未生成'}",
        f"- API 模块文件：{'、'.join(api_files) if api_files else '未生成'}",
        f"- 页面设计主页面：{'、'.join(expected_pages) if expected_pages else '未声明'}",
        "",
        "## 检查项",
        "- 主页面覆盖：校验页面设计声明的主页面是否有对应文件。",
        "- 操作覆盖：校验新增/创建、编辑、导出、手动成团等入口是否在页面中体现。",
        "- 真实项目结构：校验是否使用 src/views、src/api 等项目业务目录，禁止静态 HTML 或独立 demo。",
        "- 表格分页与首屏兜底：校验 STable loadData、分页字段、数组默认值和 mock 分页行为。",
        "- API 契约：校验页面设计声明的接口与 API 模块、响应包装格式是否对齐。",
        "",
    ]
    if issues:
        lines.append("## 阻塞问题")
        lines.extend(f"- {issue}" for issue in issues[:12])
    else:
        lines.extend([
            "## 结论",
            "确定性审查未发现阻塞项，可进入报告阶段；仍建议人工重点复核后端接口真实存在性、权限码命名和 SKU 选择组件复用策略。",
        ])

    parsed = {
        "output": "\n".join(lines),
        "review_passed": review_passed,
        "contract_alignment": (
            "确定性审查未发现前端页面、API 模块与页面设计之间的阻塞性契约不一致。"
            if review_passed
            else "确定性审查发现前端页面/API 与页面设计存在阻塞性不一致。"
        ),
        "field_mismatches": [],
        "fix_suggestions": "" if review_passed else "\n".join(f"- {issue}" for issue in issues[:12]),
        "deterministic_fallback": True,
        "review_focus": [
            "后端接口真实存在性",
            "权限 key 与菜单配置一致性",
            "商品 SKU 选择组件复用策略",
            "手动成团并发与审计策略",
        ],
    }
    return parsed["output"], parsed


def _fallback_quality(
    raw_output: str,
    marker_groups: List[Tuple[str, str, List[str]]],
    default_review_focus: List[str],
) -> Dict[str, Any]:
    """Create a deterministic review summary when the LLM omits quality JSON."""
    lowered = raw_output.lower()
    missing_items = []
    matched = 0
    for _key, label, keywords in marker_groups:
        if any(keyword.lower() in lowered for keyword in keywords):
            matched += 1
        else:
            missing_items.append(label)

    score = int(round((matched / len(marker_groups)) * 100)) if marker_groups else 0
    return {
        "score": score,
        "ready_for_review": score >= 80 and not missing_items,
        "missing_items": missing_items,
        "review_focus": default_review_focus,
        "primary_pages": [],
        "permission_points": [],
        "permission_model": [],
        "data_scope_rules": [],
        "policy_examples": [],
        "data_entities": [],
        "acceptance_criteria": [],
    }


def _merge_quality_payload(payload: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
    """Merge LLM-provided quality JSON with deterministic fallback defaults."""
    if not isinstance(payload, dict):
        return fallback

    merged = dict(fallback)
    merged.update(payload)
    merged["score"] = _coerce_quality_score(payload.get("score"), fallback["score"])
    merged["ready_for_review"] = _coerce_bool(
        payload.get("ready_for_review"),
        merged["score"] >= 80 and not merged.get("missing_items"),
    )
    for key in (
        "missing_items",
        "review_focus",
        "primary_pages",
        "permission_points",
        "permission_model",
        "data_scope_rules",
        "policy_examples",
        "data_entities",
        "acceptance_criteria",
    ):
        merged[key] = _coerce_string_list(payload.get(key), fallback.get(key, []))
    return merged


def _validate_preview_html(html: str) -> Dict[str, Any]:
    """Return deterministic quality signals for generated HTML previews."""
    preview = (html or "").strip()
    lowered = preview.lower()
    issues: List[str] = []

    checks = [
        ("完整 HTML 结构", "<html" in lowered and "</html>" in lowered),
        (
            "预览就绪标记",
            'data-preview-ready="true"' in lowered
            or "data-preview-ready='true'" in lowered
            or 'id="preview-root"' in lowered
            or "id='preview-root'" in lowered,
        ),
        ("内联样式", "<style" in lowered and "</style>" in lowered),
        ("后台导航结构", any(keyword in preview for keyword in ["菜单", "导航", "侧边栏", "工作台"])),
        ("搜索筛选区", any(keyword in preview for keyword in ["搜索", "筛选", "查询"]) and ("ant-input" in lowered or "<input" in lowered)),
        ("表格或列表数据", "<table" in lowered or "ant-table" in lowered or preview.count("<tr") >= 4),
        ("弹窗或抽屉", any(keyword in preview for keyword in ["弹窗", "抽屉", "确认"]) or "ant-modal" in lowered),
        ("操作按钮", "ant-btn" in lowered or "<button" in lowered),
        ("页面状态", all(keyword in preview for keyword in ["无权限", "空数据"]) and any(keyword in preview for keyword in ["加载", "异常", "失败"])),
        ("权限呈现", any(keyword in preview for keyword in ["菜单权限", "页面权限", "按钮权限", "数据范围", "disabled"])),
    ]

    if len(preview) < 900:
        issues.append("HTML 内容过短，预览可能只是片段或占位")
    if "<html" in lowered and "</html>" not in lowered:
        issues.append("缺少 </html> 结束标签，输出可能被截断")
    if "<body" not in lowered:
        issues.append("缺少 <body> 主体结构")

    passed_checks = []
    for label, passed in checks:
        if passed:
            passed_checks.append(label)
        else:
            issues.append(f"缺少{label}")

    score = int(round((len(passed_checks) / len(checks)) * 100)) if checks else 0
    if len(preview) < 900:
        score = min(score, 65)
    if "</html>" not in lowered:
        score = min(score, 70)

    return {
        "score": max(0, min(100, score)),
        "ready_for_preview": score >= 80 and not any("截断" in issue or "过短" in issue for issue in issues),
        "issues": issues[:8],
        "passed_checks": passed_checks,
    }


PM_REQUIREMENT_MARKERS: List[Tuple[str, str, List[str]]] = [
    ("project_overview", "项目概述/业务目标", ["项目概述", "业务目标", "目标用户", "使用场景"]),
    ("scope", "范围边界", ["范围", "不做范围", "边界", "scope"]),
    ("features", "功能清单与优先级", ["功能需求", "功能清单", "P0", "P1", "优先级"]),
    ("user_stories", "用户故事/用户旅程", ["用户故事", "作为", "我希望", "用户旅程"]),
    ("permissions", "角色与权限矩阵", ["权限", "角色", "权限矩阵", "按钮权限", "页面权限"]),
    ("permission_model", "权限模型与策略样例", ["RBAC", "ABAC", "resource", "action", "策略样例", "permission key"]),
    ("data_scope", "数据范围与条件权限", ["数据范围", "租户", "部门", "本人", "下级", "condition"]),
    ("data_fields", "数据对象与字段", ["数据对象", "关键字段", "字段名", "必填", "校验规则"]),
    ("states", "页面/业务状态", ["空数据", "加载中", "无权限", "异常", "失败"]),
    ("acceptance", "验收标准", ["验收标准", "Acceptance Criteria", "Given", "When", "Then"]),
    ("questions", "假设与待确认问题", ["待确认", "假设", "开放问题", "需确认"]),
]


PM_PAGE_DESIGN_MARKERS: List[Tuple[str, str, List[str]]] = [
    ("pages", "页面清单与层级", ["页面列表", "页面清单", "层级", "路由", "入口"]),
    ("fields", "字段与校验", ["字段", "字段名", "必填", "校验", "表单"]),
    ("table_search", "表格列与筛选", ["表格", "列", "搜索", "筛选", "过滤"]),
    ("actions", "按钮与操作", ["按钮", "操作", "新增", "编辑", "删除", "导出"]),
    ("dialogs", "弹窗/抽屉交互", ["弹窗", "抽屉", "二次确认", "确认弹窗"]),
    ("states", "页面状态", ["空数据", "加载中", "无权限", "搜索无结果", "异常"]),
    ("permissions", "权限控制点", ["权限", "菜单权限", "页面权限", "按钮权限", "数据范围"]),
    ("permission_model", "权限模型与策略样例", ["RBAC", "ABAC", "resource", "action", "策略样例", "permission key"]),
    ("permission_states", "权限呈现状态", ["隐藏", "禁用", "无权限提示", "审计", "disabled"]),
    ("handoff", "开发确认要点", ["开发确认", "待确认", "接口", "实现约束", "wealth-admin-home"]),
]


def _parse_agent_output(stage_key: str, raw_output: str) -> Dict[str, Any]:
    """解析 Agent 输出，提取结构化数据"""
    result = {"output": raw_output}

    if stage_key in ("ui_preview", "prototype"):
        import re
        # 匹配 ```html 或 ```HTML 后面的内容，直到下一个 ```
        pattern = re.compile(r"```(?:html|HTML)\s*\n(.*?)```", re.DOTALL)
        matches = pattern.findall(raw_output)
        if matches:
            result["preview_html"] = matches[0].strip()
        else:
            # 尝试从 ```html 开始提取（处理截断输出）
            pattern_truncated = re.compile(r"```(?:html|HTML)\s*\n(.*)", re.DOTALL)
            truncated = pattern_truncated.search(raw_output)
            if truncated:
                html_content = truncated.group(1).strip()
                # 如果有 </html>，截取到那里；否则取全部
                end_idx = html_content.rfind("</html>")
                if end_idx > 0:
                    html_content = html_content[:end_idx + len("</html>")]
                result["preview_html"] = html_content
            else:
                # fallback: 尝试找 <!DOCTYPE html> 或 <html 标签
                doctype_idx = raw_output.find("<!DOCTYPE")
                html_idx = raw_output.find("<html")
                candidates = [i for i in [doctype_idx, html_idx] if i >= 0]
                start = min(candidates) if candidates else -1
                if start >= 0:
                    end = raw_output.rfind("</html>")
                    if end > start:
                        result["preview_html"] = raw_output[start:end + len("</html>")].strip()
                    else:
                        result["preview_html"] = raw_output[start:].strip()
        result["preview_quality"] = _validate_preview_html(result.get("preview_html", ""))

    if stage_key in ("development", "prototype", "frontend_dev", "backend_dev", "testing"):
        # 优先尝试解析 JSON 结构化输出
        files = _try_parse_json_code_files(raw_output)
        if not files:
            # fallback: 正则解析
            files = _parse_markdown_code_files(raw_output)
        if files:
            result["code_files"] = files

    if stage_key == "requirement":
        prd_document = _extract_markdown_fence(raw_output, ["prg", "markdown", "md"])
        result["prd_document"] = prd_document or _remove_quality_json_blocks(raw_output)

        fallback = _fallback_quality(
            result["prd_document"],
            PM_REQUIREMENT_MARKERS,
            ["重点核对权限矩阵、字段校验、验收标准和待确认问题。"],
        )
        json_result = _try_parse_json_block(raw_output, ["pm_quality"])
        result["pm_quality"] = _merge_quality_payload(
            json_result.get("pm_quality") if json_result else None,
            fallback,
        )

    if stage_key == "page_design":
        page_design_document = _extract_markdown_fence(raw_output, ["markdown", "md"])
        result["page_design_document"] = page_design_document or _remove_quality_json_blocks(raw_output)

        fallback = _fallback_quality(
            result["page_design_document"],
            PM_PAGE_DESIGN_MARKERS,
            ["重点核对页面状态、按钮权限、字段校验、弹窗交互和开发确认点。"],
        )
        json_result = _try_parse_json_block(raw_output, ["design_quality"])
        result["design_quality"] = _merge_quality_payload(
            json_result.get("design_quality") if json_result else None,
            fallback,
        )

    if stage_key == "code_review":
        # 优先尝试 JSON 结构化输出
        json_result = _try_parse_json_block(raw_output, ["review_passed", "fix_suggestions"])
        if json_result:
            result.update(json_result)
        else:
            if "PASS" in raw_output:
                result["review_passed"] = True
            elif "FAIL" in raw_output:
                result["review_passed"] = False
            suggestions = []
            for line in raw_output.split("\n"):
                line = line.strip()
                if line.startswith(("- ", "* ", "改进", "建议", "修复", "问题")):
                    suggestions.append(line)
            if suggestions:
                result["fix_suggestions"] = "\n".join(suggestions[:10])
        result = _normalize_code_review_result(result)

    if stage_key == "testing":
        json_result = _try_parse_json_block(raw_output, ["tests_passed", "bug_details"])
        if json_result:
            result.update(json_result)
        else:
            has_failures = "失败" in raw_output or "FAIL" in raw_output or "critical" in raw_output.lower()
            result["tests_passed"] = not has_failures
            if has_failures:
                bug_lines = []
                for line in raw_output.split("\n"):
                    if any(kw in line.lower() for kw in ["bug", "失败", "fail", "error", "critical", "major"]):
                        bug_lines.append(line.strip())
                result["bug_details"] = "\n".join(bug_lines[:10]) if bug_lines else raw_output[:500]

    return result


# ==================== LLM 调用（带重试） ====================

def _is_retriable_error(e: Exception) -> bool:
    """判断是否为可重试的错误"""
    error_str = str(e).lower()
    type_name = type(e).__name__.lower()
    retriable_keywords = ["timeout", "rate limit", "429", "503", "502", "500",
                          "connection", "overloaded", "capacity", "retry",
                          "connecterror", "timeouterror", "read error", "eof"]
    return any(kw in error_str for kw in retriable_keywords) or any(kw in type_name for kw in retriable_keywords)


async def _call_agent_with_retry(agent_service: AgentService, session_id: str,
                                  message: str, agent_type: str,
                                  max_tokens_override: int = None,
                                  thinking_override: Optional[Dict[str, Any]] = None,
                                  response_format_override: Optional[dict] = None) -> str:
    """调用 Agent，自动重试可恢复的错误"""
    last_error = None
    original_max_tokens = None
    original_thinking = None
    original_response_format = None

    if max_tokens_override or thinking_override is not None or response_format_override is not None:
        from app.ai.agents import AgentFactory
        agent = AgentFactory.get_agent(agent_type)
        llm = agent._get_llm() if hasattr(agent, "_get_llm") else getattr(agent, "_llm", None)
        if max_tokens_override and llm and hasattr(llm, "max_tokens"):
            original_max_tokens = llm.max_tokens
            llm.max_tokens = max_tokens_override
        if llm and thinking_override is not None and hasattr(llm, "thinking"):
            original_thinking = llm.thinking
            llm.thinking = thinking_override
        if llm and response_format_override is not None and hasattr(llm, "response_format"):
            original_response_format = llm.response_format
            llm.response_format = response_format_override

    try:
        for attempt in range(MAX_LLM_RETRIES):
            try:
                logger.info(f"LLM call attempt {attempt + 1}/{MAX_LLM_RETRIES} for {session_id}")
                result = await agent_service.chat(
                    session_id=session_id,
                    message=message,
                    agent_type=agent_type,
                )
                return result["reply"]

            except Exception as e:
                last_error = e
                if not _is_retriable_error(e):
                    logger.error(f"Agent call failed (permanent): {e}")
                    raise

                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"Agent call failed (retriable, attempt {attempt + 1}/{MAX_LLM_RETRIES}): {e}. "
                             f"Retrying in {delay}s...")
                await asyncio.sleep(delay)

        logger.error(f"Agent call failed after {MAX_LLM_RETRIES} retries: {last_error}")
        raise last_error
    finally:
        # 恢复原始 max_tokens
        if original_max_tokens is not None:
            from app.ai.agents import AgentFactory
            agent = AgentFactory.get_agent(agent_type)
            llm = getattr(agent, "_llm", None)
            if llm and hasattr(llm, "max_tokens"):
                llm.max_tokens = original_max_tokens
        if original_thinking is not None:
            from app.ai.agents import AgentFactory
            agent = AgentFactory.get_agent(agent_type)
            llm = getattr(agent, "_llm", None)
            if llm and hasattr(llm, "thinking"):
                llm.thinking = original_thinking
        if response_format_override is not None:
            from app.ai.agents import AgentFactory
            agent = AgentFactory.get_agent(agent_type)
            llm = getattr(agent, "_llm", None)
            if llm and hasattr(llm, "response_format"):
                llm.response_format = original_response_format


def _normalize_stream_chunk(chunk: Any) -> Tuple[str, bool, Optional[str]]:
    """Normalize raw LLM stream chunks into content/done/error fields."""
    if chunk is None:
        return "", False, None

    if hasattr(chunk, "content"):
        content = getattr(chunk, "content", "")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text") or item.get("content") or ""))
                else:
                    parts.append(str(item))
            content = "".join(parts)
        return str(content or ""), False, None

    if not isinstance(chunk, str):
        return str(chunk), False, None

    raw = chunk.strip()
    if not raw:
        return "", False, None
    if raw == "[DONE]" or raw == "data: [DONE]":
        return "", True, None
    if raw.startswith("data:"):
        raw = raw[5:].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return chunk, False, None

    if not isinstance(data, dict):
        return str(data), False, None

    error = data.get("error")
    if data.get("type") == "error":
        error = error or data.get("message")
    content = data.get("content") or data.get("delta") or data.get("text") or ""
    done = bool(data.get("done")) or data.get("type") in {"done", "complete"}
    return str(content), done, str(error) if error else None


async def _call_agent_with_retry_stream(
    agent_service: AgentService,
    session_id: str,
    message: str,
    agent_type: str,
    on_chunk: Callable[[str], Awaitable[None]],
    max_tokens_override: int = None,
    thinking_override: Optional[Dict[str, Any]] = None,
    response_format_override: Optional[dict] = None,
) -> str:
    """Call an agent with streaming chunks while preserving the final reply."""
    last_error = None
    original_max_tokens = None
    original_thinking = None
    original_response_format = None

    if max_tokens_override or thinking_override is not None or response_format_override is not None:
        from app.ai.agents import AgentFactory
        agent = AgentFactory.get_agent(agent_type)
        llm = agent._get_llm() if hasattr(agent, "_get_llm") else getattr(agent, "_llm", None)
        if max_tokens_override and llm and hasattr(llm, "max_tokens"):
            original_max_tokens = llm.max_tokens
            llm.max_tokens = max_tokens_override
        if llm and thinking_override is not None and hasattr(llm, "thinking"):
            original_thinking = llm.thinking
            llm.thinking = thinking_override
        if llm and response_format_override is not None and hasattr(llm, "response_format"):
            original_response_format = llm.response_format
            llm.response_format = response_format_override

    try:
        for attempt in range(MAX_LLM_RETRIES):
            emitted_any = False
            chunks: List[str] = []
            try:
                logger.info(
                    f"LLM stream attempt {attempt + 1}/{MAX_LLM_RETRIES} for {session_id}"
                )

                from app.ai.agents import AgentFactory
                agent = AgentFactory.get_agent(agent_type)
                history = agent_service.sessions.get(session_id, [])

                stream = agent.astream(message, history).__aiter__()
                while True:
                    try:
                        raw_chunk = await asyncio.wait_for(
                            stream.__anext__(),
                            timeout=LLM_STREAM_IDLE_TIMEOUT,
                        )
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        logger.warning(
                            "Agent stream idle for %ss, falling back to final reply for %s",
                            LLM_STREAM_IDLE_TIMEOUT,
                            session_id,
                        )
                        break

                    content, done, error = _normalize_stream_chunk(raw_chunk)
                    if error:
                        raise RuntimeError(error)
                    if content:
                        emitted_any = True
                        chunks.append(content)
                        await on_chunk(content)
                    if done:
                        break

                full_reply = "".join(chunks)
                if not full_reply.strip():
                    result = await asyncio.wait_for(
                        agent_service.chat(
                            session_id=session_id,
                            message=message,
                            agent_type=agent_type,
                        ),
                        timeout=LLM_FINAL_REPLY_TIMEOUT,
                    )
                    full_reply = result.get("reply", "")
                    if full_reply:
                        await on_chunk(full_reply)

                if session_id not in agent_service.sessions:
                    agent_service.sessions[session_id] = []
                agent_service.sessions[session_id].append({"role": "user", "content": message})
                agent_service.sessions[session_id].append({"role": "assistant", "content": full_reply})
                if len(agent_service.sessions[session_id]) > 20:
                    agent_service.sessions[session_id] = agent_service.sessions[session_id][-20:]
                return full_reply

            except Exception as e:
                last_error = e
                error_label = "timeout waiting for final LLM reply" if isinstance(e, asyncio.TimeoutError) else str(e)
                if emitted_any or not _is_retriable_error(e):
                    logger.error(f"Agent stream failed: {error_label}")
                    raise

                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"Agent stream failed (retriable, attempt {attempt + 1}/{MAX_LLM_RETRIES}): "
                    f"{error_label}. Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)

        logger.error(f"Agent stream failed after {MAX_LLM_RETRIES} retries: {last_error}")
        raise last_error
    finally:
        if original_max_tokens is not None:
            from app.ai.agents import AgentFactory
            agent = AgentFactory.get_agent(agent_type)
            llm = getattr(agent, "_llm", None)
            if llm and hasattr(llm, "max_tokens"):
                llm.max_tokens = original_max_tokens
        if original_thinking is not None:
            from app.ai.agents import AgentFactory
            agent = AgentFactory.get_agent(agent_type)
            llm = getattr(agent, "_llm", None)
            if llm and hasattr(llm, "thinking"):
                llm.thinking = original_thinking
        if response_format_override is not None:
            from app.ai.agents import AgentFactory
            agent = AgentFactory.get_agent(agent_type)
            llm = getattr(agent, "_llm", None)
            if llm and hasattr(llm, "response_format"):
                llm.response_format = original_response_format


# ==================== 项目上下文加载 ====================

# 项目文件缓存（进程级，避免重复克隆）
_project_cache: Dict[str, Dict[str, str]] = {}


async def _load_project_files_cached(project_id: str, project_type: str) -> Dict[str, str]:
    if not project_id:
        return {}
    cache_key = f"{project_id}:{project_type}"
    if cache_key not in _project_cache:
        _project_cache[cache_key] = await _fetch_project_files_from_git(project_id)
    return _project_cache[cache_key]


def _requirement_match_terms(requirement: str) -> List[str]:
    terms = set(re.findall(r"[A-Za-z0-9_]{2,}", (requirement or "").lower()))
    cjk_chunks = re.findall(r"[\u4e00-\u9fff]+", requirement or "")
    for chunk in cjk_chunks:
        if len(chunk) <= 4:
            terms.add(chunk)
            continue
        for size in (2, 3, 4):
            for index in range(0, len(chunk) - size + 1):
                terms.add(chunk[index:index + size])
    stop_terms = {"现有", "已有", "增加", "新增", "添加", "一个", "功能", "页面", "字段", "筛选", "查询", "搜索"}
    return sorted(term for term in terms if term not in stop_terms)


def _business_synonyms_for_terms(terms: List[str]) -> List[str]:
    synonyms = set(terms)
    mapping = {
        "商品": ["product", "goods", "commodity", "commdity", "sku", "spu"],
        "零售": ["retail"],
        "商城": ["mall", "shop", "store"],
        "列表": ["list"],
        "活动": ["activity"],
    }
    for term in terms:
        for key, values in mapping.items():
            if key in term:
                synonyms.update(values)
        for key, values in mapping.items():
            if term in values:
                synonyms.add(key)
    return sorted(synonyms)


def _requirement_strong_business_terms(requirement: str) -> List[str]:
    terms = _requirement_match_terms(requirement)
    generic = {
        "管理", "平台", "系统", "列表", "筛选", "查询", "搜索", "字段", "id",
        "商品id", "增加", "新增", "现有", "已有",
    }
    known_business_terms = ("商品", "零售", "活动", "营销", "订单", "用户", "酒店", "分类")
    strong = []
    for term in terms:
        if term.lower() in generic or len(term) < 2:
            continue
        if re.fullmatch(r"[a-z0-9_]+", term.lower()):
            strong.append(term)
            continue
        strong.extend(known for known in known_business_terms if known in term)
    return _business_synonyms_for_terms(strong)


def _select_relevant_project_files(files: Dict[str, str], requirement: str, limit: int = 8) -> List[Tuple[str, str]]:
    terms = _requirement_match_terms(requirement)
    if not terms:
        return []

    candidates = []
    for path, content in files.items():
        normalized = str(path).replace("\\", "/")
        if not normalized.startswith(("src/views/", "src/pages/", "pages/", "src/api/")):
            continue
        if not normalized.endswith((".vue", ".tsx", ".jsx", ".js", ".ts", ".wxml")):
            continue
        haystack = f"{normalized}\n{content}".lower()
        matched_terms = [term for term in terms if term.lower() in haystack]
        if not matched_terms:
            continue
        page_bonus = 2 if _is_frontend_page_path(normalized) else 0
        score = len(matched_terms) + page_bonus
        candidates.append((score, len(content or ""), normalized, content))

    candidates.sort(key=lambda item: (item[0], -item[1], item[2]), reverse=True)
    return [(path, content) for _, _, path, content in candidates[:limit]]


def _frontend_existing_page_paths(files: Dict[str, str]) -> List[str]:
    return sorted(
        str(path).replace("\\", "/").lstrip("/")
        for path in files
        if _is_frontend_page_path(str(path).replace("\\", "/").lstrip("/"))
    )


def _frontend_relevant_existing_page_paths(files: Dict[str, str], requirement: str, limit: int = 12) -> List[str]:
    return [item["path"] for item in _frontend_existing_page_candidates(files, requirement, limit)]


def _requirement_anchor_groups(requirement: str) -> List[List[str]]:
    requirement_text = requirement or ""
    anchor_groups: List[List[str]] = []
    if "零售" in requirement_text:
        anchor_groups.append(["零售", "retail"])
    if "商品" in requirement_text:
        anchor_groups.append(["商品", "product", "goods", "sku", "spu"])
    if "活动" in requirement_text:
        anchor_groups.append(["活动", "activity"])
    return anchor_groups


def _is_product_pool_context(path: str, content: str) -> bool:
    text = f"{path}\n{content or ''}".lower()
    return "pool" in text or "商品池" in (content or "") or "池" in path


def _is_primary_product_list_context(path: str, content: str) -> bool:
    normalized = str(path).replace("\\", "/").lstrip("/")
    lower_path = normalized.lower()
    text = f"{lower_path}\n{content or ''}".lower()
    if _is_product_pool_context(normalized, content):
        return False
    if any(segment in lower_path for segment in ("/orderlist/", "refundorderlist", "/modules/", "/detail")):
        return False
    if lower_path.endswith("/operate.vue"):
        return False
    if "commoditylist" in lower_path or "commodity/list" in lower_path:
        return True
    if ("productlist" in lower_path or lower_path.endswith("/list.vue")) and (
        "商品名称" in (content or "") or "productname" in text
    ):
        return True
    return False


def _matches_requirement_anchor_groups(path: str, content: str, requirement: str) -> bool:
    anchor_groups = _requirement_anchor_groups(requirement)
    if not anchor_groups:
        return True
    if "商品" in (requirement or "") and _is_product_pool_context(path, content) and "池" not in (requirement or ""):
        return False
    primary_product_list = _is_primary_product_list_context(path, content)
    combined_text = f"{path}\n{content or ''}".lower()
    for group in anchor_groups:
        if any(anchor.lower() in combined_text for anchor in group):
            continue
        # Some admin systems expose "零售商品列表" in the menu/URL, while the
        # source file is named as a generic commodity/product list.
        if "零售" in group and primary_product_list and "商品" in (requirement or ""):
            continue
        return False
    return True


def _humanize_frontend_page_path(path: str, content: str = "") -> Dict[str, str]:
    normalized = str(path).replace("\\", "/").lstrip("/")
    text = f"{normalized}\n{content or ''}".lower()
    name_parts: List[str] = []
    if re.search(r"selfoperate|self_operate|self-operated|自营", text):
        name_parts.append("自营")
    if "selfoperatecommodity/commoditylist/list.vue" in normalized.lower():
        name_parts.append("零售")
    if re.search(r"retail|零售", text):
        name_parts.append("零售")
    if re.search(r"goods|product|commodity|sku|spu|商品", text):
        name_parts.append("商品")
    if re.search(r"pool|商品池", text):
        name_parts.append("池")
    if re.search(r"activity|活动", text):
        name_parts.append("活动")
    if re.search(r"order|订单", text):
        name_parts.append("订单")
    if re.search(r"category|分类|类目", text):
        name_parts.append("分类")
    if re.search(r"list|列表", text):
        name_parts.append("列表")
    if not name_parts:
        file_name = normalized.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        display_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", file_name).strip() or "现有页面"
    else:
        display_name = "".join(dict.fromkeys(name_parts))
        if not display_name.endswith(("页", "列表", "管理")):
            display_name = f"{display_name}页"

    route_parts = []
    if "selfoperatecommodity/commoditylist/list.vue" in normalized.lower():
        route_parts.append("商城管理 / 商品管理 / 零售商品列表")
        route_parts.append("/product/goods/list")
    elif "product" in text and "list" in text:
        route_parts.append("商品相关列表页")
    elif "activity" in text:
        route_parts.append("活动管理相关页面")
    elif "order" in text:
        route_parts.append("订单相关页面")

    return {
        "display_name": display_name,
        "menu_hint": "；".join(route_parts[:2]) if route_parts else display_name,
        "route_hint": route_parts[-1] if route_parts and route_parts[-1].startswith("/") else "",
        "developer_hint": normalized,
    }


def _frontend_existing_page_candidates(files: Dict[str, str], requirement: str, limit: int = 12) -> List[Dict[str, Any]]:
    strong_terms = _requirement_strong_business_terms(requirement)
    if not strong_terms:
        return []

    scored: List[Tuple[int, str, List[str], List[str]]] = []
    for path, content in files.items():
        normalized = str(path).replace("\\", "/").lstrip("/")
        if not _is_frontend_page_path(normalized):
            continue
        if not _matches_requirement_anchor_groups(normalized, content or "", requirement):
            continue
        path_text = normalized.lower()
        content_text = (content or "").lower()
        path_hits = [term for term in strong_terms if term.lower() in path_text]
        content_hits = [term for term in strong_terms if term.lower() in content_text]
        if not path_hits and len(content_hits) < 2:
            continue
        score = len(path_hits) * 4 + len(content_hits)
        if _is_primary_product_list_context(normalized, content or "") and "商品" in (requirement or ""):
            score += 12
        if (
            "商城" in (requirement or "")
            and ("零售" in (requirement or "") or "自营" in (requirement or ""))
            and "selfoperatecommodity/commoditylist/list.vue" in normalized.lower()
        ):
            score += 18
        if "supplychainmidplatform/" in normalized.lower() and "供应链" not in (requirement or ""):
            score -= 6
        if "platformcommodity/" in normalized.lower() and "平台商品" not in (requirement or ""):
            score -= 4
        scored.append((score, normalized, path_hits, content_hits))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if not scored:
        return []
    top_score = max(score for score, _, _, _ in scored)
    candidates = []
    for score, path, path_hits, content_hits in scored[:limit]:
        confidence = round(min(0.98, max(0.35, score / max(top_score, 1) * 0.92)), 2)
        matched_terms = sorted(set(path_hits + content_hits))
        content = files.get(path, "")
        candidates.append({
            "path": path,
            "confidence": confidence,
            "matched_terms": matched_terms[:8],
            "reason": f"命中业务词：{', '.join(matched_terms[:6])}" if matched_terms else "命中项目页面路径",
            **_humanize_frontend_page_path(path, content),
        })
    return candidates


def _frontend_fallback_page_candidates(files: Dict[str, str], requirement: str, limit: int = 8) -> List[Dict[str, Any]]:
    terms = _business_synonyms_for_terms(_requirement_match_terms(requirement))
    scored = []
    for path, content in files.items():
        normalized = str(path).replace("\\", "/").lstrip("/")
        if not _is_frontend_page_path(normalized):
            continue
        if not _matches_requirement_anchor_groups(normalized, content or "", requirement):
            continue
        haystack = f"{normalized}\n{content or ''}".lower()
        hits = [term for term in terms if term.lower() in haystack]
        score = len(hits)
        path_lower = normalized.lower()
        if "list" in path_lower or "列表" in (content or ""):
            score += 1
        scored.append((score, normalized, sorted(set(hits))[:6]))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    candidates = []
    for score, path, hits in scored[:limit]:
        content = files.get(path, "")
        candidates.append({
            "path": path,
            "confidence": round(min(0.52, 0.18 + score * 0.08), 2),
            "matched_terms": hits,
            "reason": "低置信候选，需要人工确认" if not hits else f"低置信候选，命中：{', '.join(hits[:4])}",
            "uncertain": True,
            **_humanize_frontend_page_path(path, content),
        })
    return candidates


async def get_frontend_page_candidates_for_requirement(project_id: str, requirement: str) -> Dict[str, Any]:
    files = await _load_project_files_cached(project_id, "frontend")
    candidates = _frontend_existing_page_candidates(files, requirement)
    fallback_candidates: List[Dict[str, Any]] = []
    if _is_existing_feature_change_request(requirement) and not candidates:
        fallback_candidates = _frontend_fallback_page_candidates(files, requirement)
    return {
        "project_id": str(project_id or ""),
        "requires_selection": _is_existing_feature_change_request(requirement),
        "candidates": candidates or fallback_candidates,
        "uncertain": bool(fallback_candidates and not candidates),
    }


async def _load_project_context(project_id: str, project_type: str, requirement: str = "") -> str:
    """从 Generator 获取项目信息，从 Git 拉取关键文件，返回上下文文本。
    project_type: "frontend" 或 "backend"
    """
    files = await _load_project_files_cached(project_id, project_type)
    if not files:
        return ""

    # 筛选关键文件
    key_patterns = _get_key_file_patterns(project_type)
    key_files = {}
    for path, content in files.items():
        if any(path.endswith(p) or path.endswith("/" + p) for p in key_patterns):
            key_files[path] = content
    for path, content in _select_relevant_project_files(files, requirement):
        key_files[path] = content
    if not key_files:
        # 没匹配到关键文件，取前 3 个非空文件
        for path, content in list(files.items())[:3]:
            if content.strip():
                key_files[path] = content[:2000]

    # 构建上下文文本（总长度限制 6000 字符）
    sections = []
    total = 0
    if project_type == "frontend":
        relevant_pages = _frontend_relevant_existing_page_paths(files, requirement)
        existing_pages = relevant_pages or _frontend_existing_page_paths(files)
        if existing_pages:
            title = "## 与本需求相关的已确认前端页面路径" if relevant_pages else "## 已确认存在的前端页面路径"
            path_block = title + "\n" + "\n".join(f"- `{path}`" for path in existing_pages[:30])
            sections.append(path_block)
            total += len(path_block)
    for path, content in sorted(key_files.items()):
        chunk = f"### {path}\n```\n{content[:1500]}\n```\n"
        if total + len(chunk) > 6000:
            break
        sections.append(chunk)
        total += len(chunk)

    return "\n".join(sections) if sections else ""


def _get_key_file_patterns(project_type: str) -> list:
    """根据项目类型返回关键文件模式"""
    if project_type == "frontend":
        return [
            "package.json",
            "src/main.js", "src/main.ts", "src/App.vue", "src/App.tsx",
            "src/router/index.js", "src/router/index.ts",
            "src/views/Home.vue", "src/pages/index.vue",
            "src/layouts/BasicLayout.vue", "src/layout/index.vue",
            "src/components/",
            "vite.config.js", "vue.config.js",
            ".env",
        ]
    else:
        return [
            "pom.xml", "build.gradle", "go.mod", "requirements.txt",
            "composer.json", "package.json",
            "src/main/resources/application.yml", "src/main/resources/application.properties",
            "src/main/java/",
            "config.yaml", "config.json",
        ]


def _project_file_read_limit(path: str) -> int:
    normalized = str(path).replace("\\", "/").lstrip("/")
    if normalized.startswith(("src/views/", "src/pages/", "pages/")) and normalized.endswith((
        ".vue", ".tsx", ".jsx", ".js", ".ts", ".wxml"
    )):
        return 30000
    return 5000


async def _fetch_project_files_from_git(project_id: str) -> Dict[str, str]:
    """从 Generator 获取项目 Git 地址，浅克隆并读取关键文件"""
    import httpx
    import tempfile

    tmp_dir = ""
    try:
        # 1. 从 Generator 获取项目信息
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"http://admin-generator:8082/generator/projects/{project_id}")
            if resp.status_code != 200:
                return {}
            proj_data = resp.json().get("data", {})

        repo_url = proj_data.get("repo_url", "")
        branch = proj_data.get("branch", "main")
        if not repo_url:
            return {}

        # 2. 浅克隆到临时目录
        tmp_dir = tempfile.mkdtemp(prefix="pipe-ctx-")
        token = await _get_git_token_for_project(project_id) or await _get_git_token_for_repo(repo_url)
        clone_url = _inject_git_credentials(repo_url, token)

        stdout, stderr, returncode = await _clone_project_repo(clone_url, branch, tmp_dir)
        if returncode != 0:
            logger.warning(f"Git clone failed for project {project_id}: {stderr.decode()[:200]}")
            return {}

        # 3. 读取项目文件必须通过 Skill，避免主流程直接碰文件内容。
        read_result = await skill_registry.execute(
            "file_reader",
            root_path=tmp_dir,
            max_bytes=5000,
            path_limits=[
                {
                    "prefixes": ["src/views/", "src/pages/", "pages/"],
                    "suffixes": [".vue", ".tsx", ".jsx", ".js", ".ts", ".wxml"],
                    "max_bytes": 30000,
                }
            ],
        )
        files = read_result.output.get("files", {}) if read_result.status == SkillStatus.COMPLETED else {}

        logger.info(f"Loaded {len(files)} files from project {project_id}")
        return files

    except Exception as e:
        logger.warning(f"Failed to load project context for {project_id}: {e}")
        return {}
    finally:
        if tmp_dir:
            await _cleanup_temp_path(tmp_dir)


def _is_safe_git_url(repo_url: str) -> tuple:
    """SSRF guard: allow only http(s) and reject loopback/private/link-local/metadata hosts."""
    import ipaddress
    from urllib.parse import urlparse
    try:
        parsed = urlparse(repo_url)
    except Exception:
        return False, "invalid URL"
    if parsed.scheme not in ("https", "http"):
        return False, f"scheme '{parsed.scheme}' not allowed"
    host = (parsed.hostname or "").lower()
    if not host:
        return False, "missing host"
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False, f"private/loopback IP {host} not allowed"
    except ValueError:
        if host in ("localhost", "metadata.google.internal") or host.endswith(".internal"):
            return False, f"host '{host}' not allowed"
    return True, ""


async def _clone_project_repo(clone_url: str, branch: str, tmp_dir: str):
    """Clone a repo, falling back to the remote default branch when stored branch is stale."""
    ok, reason = _is_safe_git_url(clone_url)
    if not ok:
        logger.warning("Blocked git clone to unsafe host: %s", reason)
        return b"", reason.encode(errors="ignore")[:200], 128
    proc = await asyncio.create_subprocess_exec(
        "git", "clone", "--depth", "1", "--branch", branch, clone_url, tmp_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    if proc.returncode == 0 or not branch:
        return stdout, stderr, proc.returncode

    logger.warning(
        "Git clone branch %s failed, retrying default branch: %s",
        branch,
        stderr.decode(errors="ignore")[:200],
    )
    await _cleanup_temp_path(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        "git", "clone", "--depth", "1", clone_url, tmp_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    return stdout, stderr, proc.returncode


def _inject_git_credentials(repo_url: str, token: str = "") -> str:
    """为 Git URL 注入凭证（支持 http/https）"""
    if not token:
        import os
        token = os.environ.get("GIT_TOKEN", "")
    if not token:
        return repo_url

    if repo_url.startswith("https://"):
        return repo_url.replace("https://", f"https://oauth2:{token}@", 1)
    elif repo_url.startswith("http://"):
        return repo_url.replace("http://", f"http://oauth2:{token}@", 1)
    return repo_url


async def _get_git_token_for_repo(repo_url: str) -> str:
    """根据仓库 URL 从数据库查找对应的 Git token"""
    from sqlalchemy import text
    async with async_session_maker() as session:
        # 先按 base_url 匹配
        result = await session.execute(
            text("SELECT platform, access_token, base_url FROM sys_git_config WHERE status = 1 LIMIT 10")
        )
        for row in result.fetchall():
            platform, access_token, base_url = row[0], row[1], row[2] or ""
            if not access_token:
                continue
            if base_url and base_url in repo_url:
                return access_token
            if platform == "gitlab" and "gitlab" in repo_url:
                return access_token
            if platform == "github" and "github" in repo_url:
                return access_token
    return ""


async def _get_git_token_for_project(project_id: str) -> str:
    """从项目的 git_config_id 获取 Git token"""
    import httpx
    from sqlalchemy import text
    try:
        # 先从 Generator 获取项目的 git_config_id
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"http://admin-generator:8082/generator/projects/{project_id}")
            if resp.status_code != 200:
                return ""
            proj = resp.json().get("data", {})
        git_config_id = proj.get("git_config_id")
        if not git_config_id:
            # fallback: 用 repo_url 匹配
            repo_url = proj.get("repo_url", "")
            if repo_url:
                return await _get_git_token_for_repo(repo_url)
            return ""

        # 从数据库取 token
        async with async_session_maker() as session:
            result = await session.execute(
                text("SELECT access_token FROM sys_git_config WHERE id = :id AND status = 1"),
                {"id": int(git_config_id)}
            )
            row = result.fetchone()
            return row[0] if row and row[0] else ""
    except Exception as e:
        logger.warning(f"Failed to get git token for project {project_id}: {e}")
        return ""


# ==================== 流水线管理器 ====================

class DevPipelineManager:
    """完整开发流水线管理器（数据库持久化 + 自修复 + 记忆）"""

    def __init__(self):
        self.agent_service = AgentService()

    async def create_pipeline(self, project_id: str = "", user_request: str = "",
                              tenant_id: int = 0, creator_id: int = 0,
                              git_config_id: int = None, git_repo_url: str = "",
                              git_branch: str = "main", skill_config: dict = None,
                              backend_tech: str = "", frontend_tech: str = "",
                              backend_project_id: str = "", frontend_project_id: str = "",
                              backend_project_ids: List[str] = None,
                              pipeline_mode: str = "full") -> str:
        pipeline_id = f"pipe_{uuid.uuid4().hex[:12]}"
        now = int(time.time() * 1000)
        pipeline_mode = pipeline_mode or "full"
        stages = _init_stages_for_mode(pipeline_mode)

        # Store runtime configuration as a stable snapshot for this pipeline.
        config = dict(skill_config or {})
        config["pipeline_mode"] = pipeline_mode
        if backend_tech:
            config["backend_tech"] = backend_tech
        if frontend_tech:
            config["frontend_tech"] = frontend_tech
        if backend_project_id:
            config["backend_project_id"] = backend_project_id
        backend_project_ids = [
            str(item) for item in (backend_project_ids or []) if str(item).strip()
        ]
        if backend_project_id and backend_project_id not in backend_project_ids:
            backend_project_ids.insert(0, backend_project_id)
        if backend_project_ids:
            config["backend_project_ids"] = backend_project_ids
        if frontend_project_id:
            config["frontend_project_id"] = frontend_project_id

        skill_project_id = str(frontend_project_id or project_id or backend_project_id or "")

        async with async_session_maker() as session:
            if pipeline_mode == "frontend_contract_review":
                if not skill_project_id:
                    raise ValueError("Project skill project_id is required for frontend_contract_review")
                result = await session.execute(
                    select(ProjectKnowledge).where(ProjectKnowledge.project_id == int(skill_project_id))
                )
                project_skill = result.scalar_one_or_none()
                if not project_skill:
                    raise ValueError("Project skill must be analyzed and confirmed before creating this pipeline")
                project_skill_dict = _knowledge_to_project_skill_dict(project_skill)
                _validate_project_skill_ready(project_skill_dict)
                config["project_skill_snapshot"] = _build_pipeline_skill_snapshot(project_skill_dict)
                config["output_scope"] = "preview_frontend_contract_review"
                project_id = project_id or skill_project_id

                if backend_project_ids:
                    backend_result = await session.execute(
                        select(ProjectKnowledge).where(ProjectKnowledge.project_id.in_([
                            int(project_id)
                            for project_id in backend_project_ids
                            if str(project_id).isdigit()
                        ]))
                    )
                    backend_skills = backend_result.scalars().all()
                    backend_skill_snapshots = []
                    for backend_skill in backend_skills:
                        backend_skill_dict = _knowledge_to_project_skill_dict(backend_skill)
                        _validate_project_skill_ready(backend_skill_dict)
                        backend_skill_snapshots.append(_build_pipeline_skill_snapshot(backend_skill_dict))
                    backend_skill_snapshots.sort(
                        key=lambda snapshot: backend_project_ids.index(str(snapshot.get("project_id")))
                        if str(snapshot.get("project_id")) in backend_project_ids
                        else 999
                    )
                    if backend_skill_snapshots:
                        config["backend_project_skill_snapshots"] = backend_skill_snapshots
                        config["backend_project_skill_snapshot"] = backend_skill_snapshots[0]

            db_obj = DevPipeline(
                pipeline_id=pipeline_id,
                project_id=project_id,
                user_request=user_request,
                status=PipelineStatus.PENDING.value,
                current_stage=_stage_keys_for_mode(pipeline_mode)[0],
                stages_data=json.dumps(stages, ensure_ascii=False),
                retry_count=0,
                tenant_id=tenant_id,
                creator_id=creator_id,
                git_config_id=git_config_id,
                git_repo_url=git_repo_url,
                git_branch=git_branch,
                skill_config=json.dumps(config, ensure_ascii=False),
                create_time=now,
                update_time=now,
            )
            session.add(db_obj)
            await session.commit()

        logger.info(f"Pipeline created: {pipeline_id}")
        return pipeline_id

    async def _load_pipeline(self, session: AsyncSession, pipeline_id: str) -> DevPipeline:
        result = await session.execute(
            select(DevPipeline).where(
                DevPipeline.pipeline_id == pipeline_id,
                DevPipeline.is_deleted == 0,
            )
        )
        pipe = result.scalar_one_or_none()
        if not pipe:
            raise ValueError(f"流水线不存在: {pipeline_id}")
        return pipe

    def _parse_stages(self, pipe: DevPipeline) -> Dict[str, Any]:
        if pipe.stages_data:
            return json.loads(pipe.stages_data)
        return _init_stages()

    def _to_status_dict(self, pipe: DevPipeline) -> Dict[str, Any]:
        stages = self._parse_stages(pipe)
        pipe_config = json.loads(pipe.skill_config or "{}")
        skill_snapshot = pipe_config.get("project_skill_snapshot") or {}
        backend_skill_snapshot = pipe_config.get("backend_project_skill_snapshot") or {}
        backend_skill_snapshots = pipe_config.get("backend_project_skill_snapshots") or []
        return {
            "pipeline_id": pipe.pipeline_id,
            "project_id": pipe.project_id or "",
            "user_request": pipe.user_request or "",
            "status": pipe.status,
            "current_stage": pipe.current_stage,
            "pipeline_mode": pipe_config.get("pipeline_mode", "full"),
            "project_skill": {
                "project_id": skill_snapshot.get("project_id", ""),
                "project_name": skill_snapshot.get("project_name", ""),
                "skill_version": skill_snapshot.get("skill_version"),
                "confirmed_at": skill_snapshot.get("confirmed_at"),
            } if skill_snapshot else None,
            "backend_project_skill": {
                "project_id": backend_skill_snapshot.get("project_id", ""),
                "project_name": backend_skill_snapshot.get("project_name", ""),
                "skill_version": backend_skill_snapshot.get("skill_version"),
                "confirmed_at": backend_skill_snapshot.get("confirmed_at"),
            } if backend_skill_snapshot else None,
            "backend_project_skills": [
                {
                    "project_id": snapshot.get("project_id", ""),
                    "project_name": snapshot.get("project_name", ""),
                    "skill_version": snapshot.get("skill_version"),
                    "confirmed_at": snapshot.get("confirmed_at"),
                }
                for snapshot in backend_skill_snapshots
            ],
            "stages": stages,
            "retry_count": pipe.retry_count,
            "workspace_path": pipe.workspace_path or "",
            "git_repo_url": pipe.git_repo_url or "",
            "git_branch": pipe.git_branch or "",
            "git_commit_sha": pipe.git_commit_sha or "",
            "deploy_task_id": pipe.deploy_task_id or "",
            "created_at": str(pipe.create_time),
            "updated_at": str(pipe.update_time),
        }

    # ==================== 记忆集成 ====================

    async def _save_stage_memory(self, pipeline_id: str, stage_key: str,
                                  agent_type: str, output: str,
                                  parsed: Dict[str, Any], tenant_id: int,
                                  db_session=None):
        """将阶段关键输出保存为长期记忆"""
        try:
            memory_content = f"[{stage_key}] {output[:500]}"
            key_info = f"pipeline:{pipeline_id}:{stage_key}"

            if stage_key == "code_review" and parsed.get("review_passed") is False:
                memory_content = f"[code_review FAILED] {parsed.get('fix_suggestions', output[:300])}"
            elif stage_key == "testing" and not parsed.get("tests_passed", True):
                memory_content = f"[testing FAILED] {parsed.get('bug_details', output[:300])}"

            if db_session:
                await MemoryService.save_memory(
                    db=db_session,
                    session_id=pipeline_id,
                    agent_type=agent_type,
                    content=memory_content,
                    tenant_id=tenant_id,
                    memory_type=MemoryType.LONG_TERM,
                    key_info=key_info,
                    importance=80 if "FAIL" in memory_content else 60,
                )
                await db_session.flush()
            else:
                async with async_session_maker() as mem_session:
                    await MemoryService.save_memory(
                        db=mem_session,
                        session_id=pipeline_id,
                        agent_type=agent_type,
                        content=memory_content,
                        tenant_id=tenant_id,
                        memory_type=MemoryType.LONG_TERM,
                        key_info=key_info,
                        importance=80 if "FAIL" in memory_content else 60,
                    )
                    await mem_session.commit()

            logger.info(f"Memory saved for pipeline {pipeline_id} stage {stage_key}")
        except Exception as e:
            logger.warning(f"Failed to save memory: {e}")

    async def _retrieve_memories(self, pipeline_id: str, stage_key: str,
                                  tenant_id: int, session=None,
                                  creator_id: int = 0) -> str:
        """检索与当前流水线和当前用户相关的记忆"""
        try:
            if session:
                memories = await MemoryService.get_memories(
                    db=session,
                    session_id=pipeline_id,
                    limit=5,
                    memory_types=[MemoryType.LONG_TERM, MemoryType.SEMANTIC],
                    min_importance=60,
                )
                user_context = await UserEvolutionService.get_user_memory_context(
                    db=session,
                    tenant_id=tenant_id,
                    user_id=creator_id,
                ) if creator_id else ""
                await session.flush()
            else:
                async with async_session_maker() as mem_session:
                    memories = await MemoryService.get_memories(
                        db=mem_session,
                        session_id=pipeline_id,
                        limit=5,
                        memory_types=[MemoryType.LONG_TERM, MemoryType.SEMANTIC],
                        min_importance=60,
                    )
                    user_context = await UserEvolutionService.get_user_memory_context(
                        db=mem_session,
                        tenant_id=tenant_id,
                        user_id=creator_id,
                    ) if creator_id else ""
                    await mem_session.commit()

            memory_sections = []
            if memories:
                memory_sections.append("\n".join([
                    f"- [{m.agent_type}] {m.content}"
                    for m in memories
                ]))
            if user_context:
                memory_sections.append(user_context)

            return "\n\n".join(memory_sections)
        except Exception as e:
            logger.warning(f"Failed to retrieve memories: {e}")
            return ""

    async def _record_user_evolution(self, session: AsyncSession, pipe: DevPipeline,
                                     stages: Dict[str, Any]) -> None:
        """Persist user-level learning after a pipeline is completed."""
        try:
            await UserEvolutionService.summarize_completed_requirement(
                db=session,
                pipeline=pipe,
                stages=stages,
            )
            logger.info(
                "User evolution memory refreshed for pipeline %s creator %s",
                pipe.pipeline_id,
                pipe.creator_id,
            )
        except Exception as e:
            logger.warning(f"Failed to record user evolution memory: {e}")

    async def _record_delivery_knowledge(self, pipe: DevPipeline, stages: Dict[str, Any]) -> None:
        """Persist completed pipeline delivery into knowledge base and graph."""
        try:
            from app.services.knowledge_service import KnowledgeService

            await KnowledgeService.record_pipeline_delivery(
                pipeline_id=pipe.pipeline_id,
                user_request=pipe.user_request or "",
                stages=stages,
                skill_config=json.loads(pipe.skill_config or "{}"),
                tenant_id=pipe.tenant_id or 1,
                creator_id=pipe.creator_id,
            )
        except Exception as e:
            logger.warning(f"Failed to record delivery knowledge: {e}")

    # ==================== Skill 执行 ====================

    async def _execute_stage_skill(
        self, pipeline_id: str, pipe: DevPipeline,
        stage_key: str, stages: Dict[str, Any],
        parsed: Dict[str, Any], session: AsyncSession,
    ) -> None:
        """根据阶段调用对应的 Pipeline Skill"""
        skill_config = json.loads(pipe.skill_config or "{}")
        workspace = pipe.workspace_path

        # Skill: code_writer — prototype/frontend_dev/backend_dev/testing 阶段写文件
        if stage_key in ("prototype", "frontend_dev", "backend_dev", "testing") and parsed.get("code_files"):
            workspace = ensure_workspace(pipeline_id)
            pipe.workspace_path = workspace
            # testing 阶段的代码写到 tests/ 子目录
            if stage_key == "testing":
                test_files = {f"tests/{k}" if not k.startswith("tests/") else k: v
                              for k, v in parsed["code_files"].items()}
            else:
                test_files = None
            result = await skill_registry.execute(
                "code_writer",
                pipeline_id=pipeline_id,
                code_files=test_files or parsed["code_files"],
            )
            if result.status.value == "completed" and result.output:
                logger.info(f"code_writer ({stage_key}): {result.output.get('files_written', [])}")
                stages[stage_key]["skill_result"] = {
                    "skill": "code_writer",
                    "files_written": result.output.get("files_written", []),
                }
                pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                pipe.update_time = int(time.time() * 1000)
                await session.flush()

            # backend_dev：兜底补齐 Java 工程脚手架（pom.xml/主类/application.yml），
            # 确保产物可独立构建（在 dockerfile_generator 之前，pom.xml 探测 Java 才生效）
            if stage_key == "backend_dev":
                try:
                    scaffold = await skill_registry.execute(
                        "backend_scaffolder",
                        workspace_path=workspace,
                        code_files=parsed["code_files"],
                    )
                    if scaffold.status.value == "completed" and scaffold.output:
                        injected = scaffold.output.get("injected_files") or {}
                        if injected:
                            parsed["code_files"].update(injected)
                            stages[stage_key].setdefault("skill_result", {})["backend_scaffold"] = {
                                "injected": list(injected.keys()),
                                "base_package": scaffold.output.get("base_package"),
                            }
                            pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                            pipe.update_time = int(time.time() * 1000)
                            await session.flush()
                except Exception as exc:  # noqa: BLE001 — 脚手架失败不阻塞流水线
                    logger.warning("backend_scaffolder failed (non-fatal): %s", exc)

            # 也生成 Dockerfile
            await skill_registry.execute("dockerfile_generator", workspace_path=workspace)

        # Skill: test_runner — testing 阶段实际执行测试
        if stage_key == "testing" and workspace:
            test_cfg = skill_config.get("testing", {})
            result = await skill_registry.execute(
                "test_runner",
                workspace_path=workspace,
                timeout=test_cfg.get("timeout", 120),
                frameworks=test_cfg.get("frameworks"),
            )
            if result.status.value == "completed" and result.output:
                test_output = result.output
                # 用实际测试结果覆盖 LLM 的判断
                if not test_output.get("skipped"):
                    parsed["tests_passed"] = test_output.get("success", False)
                    parsed["actual_test_result"] = test_output
                    stages[stage_key]["skill_result"] = {
                        "skill": "test_runner",
                        "framework": test_output.get("framework"),
                        "success": test_output.get("success"),
                        "tests_passed": test_output.get("tests_passed", 0),
                        "tests_failed": test_output.get("tests_failed", 0),
                        "duration_ms": test_output.get("duration_ms", 0),
                    }
                    # 追加实际测试输出到阶段 output
                    test_summary = f"\n\n--- 实际测试执行结果 ---\n"
                    test_summary += f"框架: {test_output.get('framework', 'unknown')}\n"
                    test_summary += f"结果: {'通过' if test_output.get('success') else '失败'}\n"
                    if test_output.get("tests_passed") is not None:
                        test_summary += f"通过: {test_output['tests_passed']}, 失败: {test_output['tests_failed']}\n"
                    test_summary += f"耗时: {test_output.get('duration_ms', 0)}ms\n"
                    if test_output.get("error"):
                        test_summary += f"错误: {test_output['error']}\n"
                    stages[stage_key]["output"] += test_summary
                    pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                    pipe.update_time = int(time.time() * 1000)
                    await session.flush()

        # Skill: git_commit — commit 阶段提交推送
        if stage_key == "commit" and workspace:
            # 提取 commit message: 取 LLM 输出的第一行或前 100 字符
            output_text = parsed.get("output", "")
            commit_lines = [l for l in output_text.split("\n") if l.strip()]
            commit_message = commit_lines[0][:100] if commit_lines else f"Pipeline {pipeline_id} auto-commit"
            if commit_message.startswith("#"):
                commit_message = commit_lines[1][:100] if len(commit_lines) > 1 else commit_message

            result = await skill_registry.execute(
                "git_commit",
                workspace_path=workspace,
                commit_message=commit_message,
                repo_url=pipe.git_repo_url or "",
                branch=pipe.git_branch or "main",
                git_config_id=pipe.git_config_id,
                db_session=session,
            )
            if result.status.value == "completed" and result.output:
                commit_output = result.output
                if commit_output.get("commit_sha"):
                    pipe.git_commit_sha = commit_output["commit_sha"]
                stages[stage_key]["skill_result"] = {
                    "skill": "git_commit",
                    "commit_sha": commit_output.get("commit_sha", ""),
                    "pushed": commit_output.get("pushed", False),
                    "branch": commit_output.get("branch", ""),
                }
                stages[stage_key]["output"] += f"\n\n--- Git 操作结果 ---\nCommit: {commit_output.get('commit_sha', 'N/A')}\nPushed: {commit_output.get('pushed', False)}\n"
                pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                pipe.update_time = int(time.time() * 1000)
                await session.flush()

        # Skill: deployer — deploy 阶段触发部署
        if stage_key == "deploy" and workspace:
            result = await skill_registry.execute(
                "deployer",
                workspace_path=workspace,
                repo_url=pipe.git_repo_url or "",
                branch=pipe.git_branch or "main",
                tenant_id=pipe.tenant_id,
                admin_id=pipe.creator_id or 0,
                pipeline_id=pipeline_id,
            )
            if result.status.value == "completed" and result.output:
                deploy_output = result.output
                if deploy_output.get("task_id"):
                    pipe.deploy_task_id = str(deploy_output["task_id"])
                stages[stage_key]["skill_result"] = {
                    "skill": "deployer",
                    "deploy_status": deploy_output.get("deploy_status", ""),
                    "task_id": deploy_output.get("task_id"),
                }
                deploy_summary = f"\n\n--- 部署结果 ---\n状态: {deploy_output.get('deploy_status', 'unknown')}\n"
                if deploy_output.get("task_id"):
                    deploy_summary += f"任务ID: {deploy_output['task_id']}\n"
                if deploy_output.get("error"):
                    deploy_summary += f"错误: {deploy_output['error']}\n"
                stages[stage_key]["output"] += deploy_summary
                pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                pipe.update_time = int(time.time() * 1000)
                await session.flush()

    # ==================== 核心执行引擎 ====================

    async def _run_single_stage(
        self, pipeline_id: str, stage_key: str, stages: Dict[str, Any],
        pipe: 'DevPipeline', fix_feedback: str, user_input: str,
        session: AsyncSession,
        on_chunk: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """执行单个阶段：构建 prompt → 调用 LLM → 解析输出。
        返回 (raw_output, parsed)。
        注意：不修改 stages/pipe 状态，由调用方负责。
        """
        agent_type = _get_stage_agent(stage_key)

        # 检索记忆
        memories_text = await self._retrieve_memories(
            pipeline_id,
            stage_key,
            pipe.tenant_id,
            session=session,
            creator_id=pipe.creator_id or 0,
        )

        # 加载技术栈配置
        pipe_config = json.loads(pipe.skill_config or "{}")
        compact_preview_stage = _is_product_preview_code_stage(stage_key, pipe_config)
        compact_pm_design_stage = _is_product_pm_design_stage(stage_key, pipe_config)

        # 构建 context（先构建，后续语义搜索需要用到原始 user_request）
        # user_input 是阶段修订意见，不能替代原始需求，否则 PM 后续阶段会丢上下文。
        user_request = pipe.user_request or ""
        revision_feedback = "\n".join(
            part.strip()
            for part in [
                fix_feedback,
                stages.get(stage_key, {}).get("revision_feedback", ""),
                user_input or "",
            ]
            if part and part.strip()
        )
        revision_feedback = _compact_fix_feedback(revision_feedback)
        context = {
            "user_request": user_request,
            "stage_outputs": {k: v for k, v in stages.items() if v.get("status") == "completed"},
            "fix_feedback": revision_feedback,
            "memories_text": memories_text,
            "backend_tech": pipe_config.get("backend_tech", ""),
            "frontend_tech": pipe_config.get("frontend_tech", ""),
            "pipeline_mode": pipe_config.get("pipeline_mode", "full"),
            "workspace_path": pipe.workspace_path or get_workspace_path(pipeline_id),
        }
        selected_frontend_page_path = str(pipe_config.get("selected_frontend_page_path") or "").strip()

        # 加载关联项目的知识库上下文（上下文工程：语义检索 + 项目知识）
        project_ctx_section = ""
        fe_proj_id = pipe_config.get("frontend_project_id", "")
        be_proj_id = pipe_config.get("backend_project_id", "")
        be_proj_ids = [
            str(item) for item in (pipe_config.get("backend_project_ids") or []) if str(item).strip()
        ]
        if be_proj_id and be_proj_id not in be_proj_ids:
            be_proj_ids.insert(0, be_proj_id)
        ctx_parts = []
        frontend_existing_paths: List[str] = []
        project_skill_snapshot = pipe_config.get("project_skill_snapshot") or {}
        backend_skill_snapshot = pipe_config.get("backend_project_skill_snapshot") or {}
        backend_skill_snapshots = pipe_config.get("backend_project_skill_snapshots") or []
        context["frontend_project_name"] = project_skill_snapshot.get("project_name", "")
        context["backend_project_name"] = "、".join(
            snapshot.get("project_name", "")
            for snapshot in (backend_skill_snapshots or [backend_skill_snapshot])
            if snapshot.get("project_name")
        )
        if project_skill_snapshot.get("skill_content"):
            frontend_skill_content = project_skill_snapshot.get("skill_content", "")
            if compact_preview_stage or compact_pm_design_stage:
                frontend_skill_content = _compact_context(frontend_skill_content, 2500)
            ctx_parts.append(
                "## Confirmed Frontend Project Skill Snapshot\n"
                f"Project: {project_skill_snapshot.get('project_name', '')}\n"
                f"Version: {project_skill_snapshot.get('skill_version', '')}\n\n"
                f"{frontend_skill_content}"
            )
        backend_context_stages = (
            "requirement",
            "ui_preview",
            "delivery",
            "frontend_dev",
            "backend_dev",
            "code_review",
            "testing",
            "report",
        )
        for snapshot in (backend_skill_snapshots or [backend_skill_snapshot]):
            if not snapshot.get("skill_content") or stage_key not in backend_context_stages:
                continue
            backend_skill_content = snapshot.get("skill_content", "")
            if compact_preview_stage:
                backend_skill_content = _compact_context(backend_skill_content, 2500)
            ctx_parts.append(
                "## Confirmed Backend/API Project Skill Snapshot\n"
                f"Project: {snapshot.get('project_name', '')}\n"
                f"Version: {snapshot.get('skill_version', '')}\n\n"
                f"{backend_skill_content}"
            )
        if fe_proj_id and stage_key in ("frontend_dev", "prototype", "page_design", "delivery", "code_review"):
            from app.services.knowledge_service import get_relevant_context
            frontend_files = await _load_project_files_cached(fe_proj_id, "frontend")
            if selected_frontend_page_path:
                frontend_existing_paths = [selected_frontend_page_path]
            else:
                frontend_existing_paths = (
                    _frontend_relevant_existing_page_paths(frontend_files, user_request)
                    or ([] if _is_existing_feature_change_request(user_request) else _frontend_existing_page_paths(frontend_files))
                )
            if frontend_existing_paths:
                context["frontend_existing_paths"] = frontend_existing_paths
            if selected_frontend_page_path:
                ctx_parts.append(
                    "## 用户已选择要修改的现有前端页面\n"
                    f"- `{selected_frontend_page_path}`\n"
                    "本次前端预览代码必须修改这个页面路径，不允许改成其他页面或新建替代页面。"
                )
                selected_content = frontend_files.get(selected_frontend_page_path)
                if selected_content and not compact_pm_design_stage:
                    selected_content = _compact_context(selected_content, 4500 if compact_preview_stage else 9000)
                    ctx_parts.append(
                        "## 已选择页面的原始代码（必须基于此文件做最小增量修改）\n"
                        f"路径：`{selected_frontend_page_path}`\n"
                        "要求：保留原页面的 imports、mixins、components、url/list 接口、表格列、slots、操作按钮和已有方法；"
                        "只改用户明确要求的筛选/字段/交互。若已有等价字段，优先调整文案，不要重复添加字段。\n\n"
                        f"{selected_content}"
                    )
            if compact_pm_design_stage:
                existing_path_block = "\n".join(f"- `{path}`" for path in frontend_existing_paths[:20])
                if existing_path_block:
                    ctx_parts.append(
                        "## 前端页面路径参考（页面设计只需参考路径，不读取源码）\n"
                        f"{existing_path_block}\n"
                        "如需求是新增营销能力，优先设计活动管理/创建/详情页面；不要为了页面设计读取全量源码。"
                    )
            elif compact_preview_stage:
                fe_ctx = await _load_project_context(fe_proj_id, "frontend", user_request)
                if fe_ctx:
                    ctx_parts.append(f"## 前端项目关键文件参考\n{_compact_context(fe_ctx, 2500)}")
            else:
                ctx = await get_relevant_context(
                    query=user_request,
                    project_id=fe_proj_id,
                    tenant_id=pipe.tenant_id,
                )
                if ctx:
                    ctx_parts.append(ctx)
                else:
                    fe_ctx = await _load_project_context(fe_proj_id, "frontend", user_request)
                    if fe_ctx:
                        ctx_parts.append(f"## 前端项目代码参考\n{fe_ctx}")
        for current_be_proj_id in be_proj_ids:
            if not current_be_proj_id or stage_key not in backend_context_stages:
                continue
            from app.services.knowledge_service import get_relevant_context
            ctx = await get_relevant_context(
                query=user_request,
                project_id=current_be_proj_id,
                tenant_id=pipe.tenant_id,
            )
            if ctx:
                ctx_parts.append(ctx)
            else:
                be_ctx = await _load_project_context(current_be_proj_id, "backend", user_request)
                if be_ctx:
                    ctx_parts.append(f"## 后端项目代码参考\n{be_ctx}")
        if ctx_parts:
            project_ctx_section = "\n\n".join(ctx_parts)
            if compact_pm_design_stage:
                project_ctx_section = _compact_context(project_ctx_section, 3500)
            elif compact_preview_stage:
                project_ctx_section = _compact_context(project_ctx_section, 6000)

        # 构建 prompt。流水线级 prompt（来自前端本次编辑）优先，项目级 prompt 作为兜底。
        project_prompts = await self._load_project_prompts(pipe.project_id or "")
        pipeline_prompts = pipe_config.get("custom_prompts") or {}
        custom_prompts = {**project_prompts, **pipeline_prompts}
        prompt = _build_pipeline_prompt(stage_key, context, custom_prompts=custom_prompts)
        if project_ctx_section:
            prompt = f"{project_ctx_section}\n\n---\n\n{prompt}"

        # 调用 LLM
        session_id = f"{pipeline_id}_{stage_key}"
        html_stages = {"prototype", "ui_preview"}
        max_tok = 32768 if compact_preview_stage else (8192 if compact_pm_design_stage else (16384 if stage_key in html_stages else None))
        thinking_override = {"type": "disabled"} if compact_preview_stage or compact_pm_design_stage else None
        # prototype 已强制 JSON-only 输出，启用 GLM json mode 从源头保证合法 JSON
        response_format_override = {"type": "json_object"} if stage_key == "prototype" else None

        if on_chunk:
            raw_output = await asyncio.wait_for(
                _call_agent_with_retry_stream(
                    self.agent_service, session_id, prompt, agent_type,
                    on_chunk=on_chunk,
                    max_tokens_override=max_tok,
                    thinking_override=thinking_override,
                    response_format_override=response_format_override,
                ),
                timeout=LLM_STAGE_TIMEOUT,
            )
        else:
            raw_output = await asyncio.wait_for(
                _call_agent_with_retry(
                    self.agent_service, session_id, prompt, agent_type,
                    max_tokens_override=max_tok,
                    thinking_override=thinking_override,
                    response_format_override=response_format_override,
                ),
                timeout=LLM_STAGE_TIMEOUT,
            )

        parsed = _parse_agent_output(stage_key, raw_output)
        if stage_key == "prototype" and frontend_existing_paths:
            parsed["_frontend_existing_paths"] = frontend_existing_paths
        return raw_output, parsed

    async def _load_project_prompts(self, project_id: str) -> Dict[str, str]:
        """加载项目级自定义 prompt"""
        if not project_id:
            return {}
        try:
            async with async_session_maker() as s:
                from app.models.agent_models import AgentProject
                result = await s.execute(
                    select(AgentProject.pipeline_prompts).where(
                        AgentProject.project_code == project_id,
                        AgentProject.is_deleted == 0,
                    )
                )
                row = result.scalar_one_or_none()
                if row:
                    return json.loads(row)
        except Exception as e:
            logger.warning(f"Failed to load project prompts for {project_id}: {e}")
        return {}

    async def _record_parallel_stage(
        self,
        pipeline_id: str,
        stage_key: str,
        agent_label: str,
        raw_output: str,
        parsed: Dict[str, Any],
        stages: Dict[str, Any],
        pipe: 'DevPipeline',
        session: AsyncSession,
        emit,
    ) -> None:
        """Record a completed fan-out branch (frontend_dev / backend_dev):
        update stage status, persist memory, and emit completion.
        Centralizes the previously duplicated FE/BE result handling.
        """
        stage_update: Dict[str, Any] = {
            "status": "completed",
            "output": raw_output,
            "structured_output": parsed,
            "revision_feedback": "",
            "completed_at": datetime.now().isoformat(),
        }
        if stage_key == "frontend_dev":
            stage_update["preview_html"] = parsed.get("preview_html", "")
        stage_update["code_files"] = parsed.get("code_files", {})
        stages[stage_key].update(stage_update)
        await self._save_stage_memory(
            pipeline_id, stage_key, agent_label,
            raw_output, parsed, pipe.tenant_id, db_session=session,
        )
        await emit({
            "type": "stage_completed",
            "stage": stage_key,
            "output": raw_output,
            "result": parsed,
        })

    @staticmethod
    def _compute_overall_score(stages: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Aggregate per-stage quality signals into an overall 0-100 score.

        Weighting (normalized over available dimensions):
        pm 0.15 / design 0.15 / preview 0.30 / review 0.20 / testing 0.20.
        review_passed/tests_passed gate signals mapped to score (100/40, 100/30).
        """
        def _num(stage_key: str, *path: str) -> Optional[int]:
            so = (stages.get(stage_key) or {}).get("structured_output") or {}
            obj: Any = so
            for p in path:
                obj = (obj or {}).get(p) if isinstance(obj, dict) else None
            if isinstance(obj, (int, float)):
                return max(0, min(100, int(obj)))
            return None

        pm = _num("requirement", "pm_quality", "score")
        design = _num("page_design", "design_quality", "score")
        preview = _num("prototype", "preview_quality", "score")
        if preview is None:
            preview = _num("ui_preview", "preview_quality", "score")

        cr_so = (stages.get("code_review") or {}).get("structured_output") or {}
        review_passed = cr_so.get("review_passed")
        t_so = (stages.get("testing") or {}).get("structured_output") or {}
        tests_passed = t_so.get("tests_passed")

        weights = {"pm": 0.15, "design": 0.15, "preview": 0.30, "review": 0.20, "testing": 0.20}
        components: List[Tuple[str, int, float]] = []
        if pm is not None:
            components.append(("pm", pm, weights["pm"]))
        if design is not None:
            components.append(("design", design, weights["design"]))
        if preview is not None:
            components.append(("preview", preview, weights["preview"]))
        if isinstance(review_passed, bool):
            components.append(("review", 100 if review_passed else 40, weights["review"]))
        if isinstance(tests_passed, bool):
            components.append(("testing", 100 if tests_passed else 30, weights["testing"]))

        if not components:
            return None, {
                "pm_quality_score": None, "design_quality_score": None, "preview_quality_score": None,
                "review_passed": review_passed, "tests_passed": tests_passed, "components": {},
            }

        total_w = sum(w for _, _, w in components)
        overall = round(sum(score * w for _, score, w in components) / total_w)
        return overall, {
            "pm_quality_score": pm,
            "design_quality_score": design,
            "preview_quality_score": preview,
            "review_passed": review_passed,
            "tests_passed": tests_passed,
            "components": {name: score for name, score, _ in components},
        }

    async def _record_pipeline_eval(
        self, pipe: "DevPipeline", stages: Dict[str, Any]
    ) -> None:
        """Pipeline terminal: aggregate eval signals into pipeline_eval_result.

        用独立 session 写入并自行 commit，确保 eval 失败（可观测层）不影响 _complete_pipeline 主事务。
        """
        from app.models.pipeline_eval import PipelineEvalResult

        overall, breakdown = self._compute_overall_score(stages)

        testing_stage = stages.get("testing") or {}
        skill_result = testing_stage.get("skill_result") or {}
        t_so = testing_stage.get("structured_output") or {}
        tests_passed_count = skill_result.get("tests_passed")
        tests_failed_count = skill_result.get("tests_failed")
        tests_total = t_so.get("test_cases_total")
        if tests_total is None:
            computed = (tests_passed_count or 0) + (tests_failed_count or 0)
            tests_total = computed if computed > 0 else None

        stage_scores: Dict[str, Any] = {}
        for sk, sd in stages.items():
            so = (sd or {}).get("structured_output") or {}
            entry = {
                k: so[k] for k in (
                    "pm_quality", "design_quality", "preview_quality",
                    "review_passed", "tests_passed", "test_cases_total",
                    "test_cases_passed", "coverage_estimate",
                    "auto_repair_iterations", "auto_repair_summary",
                ) if k in so
            }
            if entry:
                stage_scores[sk] = entry

        retry_count = pipe.retry_count or 0
        prototype_so = (stages.get("prototype") or {}).get("structured_output") or {}
        auto_repair = prototype_so.get("auto_repair_iterations") or retry_count

        review_passed = breakdown["review_passed"]
        tests_passed = breakdown["tests_passed"]
        now = int(time.time() * 1000)
        values = {
            "eval_id": f"EVAL-{pipe.pipeline_id}",
            "pipeline_id": pipe.pipeline_id,
            "tenant_id": pipe.tenant_id,
            "project_id": pipe.project_id,
            "status": pipe.status,
            "overall_score": overall,
            "pm_quality_score": breakdown["pm_quality_score"],
            "design_quality_score": breakdown["design_quality_score"],
            "preview_quality_score": breakdown["preview_quality_score"],
            "review_passed": int(review_passed) if isinstance(review_passed, bool) else None,
            "tests_passed": int(tests_passed) if isinstance(tests_passed, bool) else None,
            "tests_total": tests_total,
            "tests_passed_count": tests_passed_count,
            "tests_failed_count": tests_failed_count,
            "retry_count": retry_count,
            "auto_repair_iterations": auto_repair,
            "framework": skill_result.get("framework"),
            "test_duration_ms": skill_result.get("duration_ms"),
            "stage_scores": json.dumps(stage_scores, ensure_ascii=False),
            "update_time": now,
        }

        async with async_session_maker() as session:
            # 汇总该 pipeline 的 LLM 用量，回填成本列（B3）
            try:
                from sqlalchemy import func

                from app.models.llm_usage_log import LLMUsageLog
                usage_row = (await session.execute(
                    select(
                        func.coalesce(func.sum(LLMUsageLog.input_tokens), 0),
                        func.coalesce(func.sum(LLMUsageLog.output_tokens), 0),
                    ).where(
                        LLMUsageLog.pipeline_id == pipe.pipeline_id,
                    )
                )).one()
                values["cost_input_tokens"] = int(usage_row[0] or 0)
                values["cost_output_tokens"] = int(usage_row[1] or 0)
            except Exception:
                pass  # 用量汇总失败不阻断 eval 写入

            existing = await session.execute(
                select(PipelineEvalResult).where(
                    PipelineEvalResult.pipeline_id == pipe.pipeline_id,
                    PipelineEvalResult.is_deleted == 0,
                )
            )
            rec = existing.scalar_one_or_none()
            if rec is not None:
                for k, v in values.items():
                    setattr(rec, k, v)
            else:
                rec = PipelineEvalResult(**values, create_time=now)
                session.add(rec)
            await session.commit()
            # 自动评审：若该 pipeline 关联了 golden case（EvalRun），评审并回写
            try:
                await self._auto_judge_eval_runs(pipe, session)
            except Exception as e:
                logger.warning("auto-judge eval runs failed for %s: %s", pipe.pipeline_id, e)

    async def _auto_judge_eval_runs(self, pipe: "DevPipeline", session: AsyncSession) -> None:
        """管线终态：对该 pipeline 关联的待评审 EvalRun 自动评审并回写。"""
        from app.models.eval_run import EvalRun
        from app.models.eval_golden_case import EvalGoldenCase
        from app.ai.eval_judge import extract_pipeline_output, judge_hallucination, judge_output

        stmt = select(EvalRun).where(
            EvalRun.pipeline_id == pipe.pipeline_id,
            EvalRun.is_deleted == 0,
            EvalRun.status.in_(["running", "pending"]),
        )
        runs = (await session.execute(stmt)).scalars().all()
        if not runs:
            return
        output = extract_pipeline_output(pipe.stages_data)
        for run in runs:
            case = (await session.execute(
                select(EvalGoldenCase).where(
                    EvalGoldenCase.id == run.golden_case_id,
                    EvalGoldenCase.is_deleted == 0,
                )
            )).scalar_one_or_none()
            if not case:
                run.status = "failed"
                run.judgment = json.dumps({"error": "golden case 不存在或已删除"}, ensure_ascii=False)
                continue
            result = await judge_output(case.input_spec, output, case.expected_criteria)
            # 幻觉评审（与功能评审正交），合并写入 judgment 供看板聚合
            try:
                halluc = await judge_hallucination(case.input_spec, output)
            except Exception as exc:  # noqa: BLE001
                halluc = {"error": str(exc)}
            if not halluc.get("error"):
                result["hallucination_score"] = halluc.get("hallucination_score")
                result["hallucination_flagged"] = halluc.get("flagged")
                result["hallucination_summary"] = halluc.get("summary")
            run.status = "failed" if result.get("error") else "judged"
            run.overall_score = result.get("overall_score")
            run.judgment = json.dumps(result, ensure_ascii=False)
            run.update_time = int(time.time() * 1000)
        await session.commit()

    async def _run_eval_stage(
        self, pipe: "DevPipeline", stages: Dict[str, Any], emit: Optional[Any] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """eval 阶段：对流水线产物做自评（功能 judge + 幻觉 + 视觉 + E2E），返回 (markdown, structured)。

        视觉截图与 E2E 断言共用一个真实沙箱预览（生命周期：start→截图/断言→stop），失败各自
        best-effort 回退 Vue2 渲染桩并静默。无 golden case 时用 DEFAULT_EVAL_CRITERIA。
        评测本身不重试、不阻塞报告——失败由调用方兜底为 error 文案。
        """
        from app.ai.eval_judge import extract_pipeline_output, judge_output, judge_hallucination, judge_output_vision
        from app.services.vision_eval_service import (
            acquire_live_preview, render_pipeline_screenshot, run_e2e_assertions,
        )
        from app.ai.e2e_expectations import derive_e2e_expectations

        output = extract_pipeline_output(pipe.stages_data)
        requirement = (pipe.user_request or "").strip() or stages.get("requirement", {}).get("output", "")
        structured: Dict[str, Any] = {}

        structured["judge"] = await judge_output({"request": requirement}, output, DEFAULT_EVAL_CRITERIA)
        try:
            structured["hallucination"] = await judge_hallucination(requirement, output)
        except Exception as exc:  # noqa: BLE001
            structured["hallucination"] = {"error": str(exc)[:200]}

        # 视觉 + E2E：同一真实沙箱预览上跑（用完即停），各自 best-effort 静默
        try:
            artifact = await self.get_pipeline_artifact(pipe.pipeline_id)
            frontend_files = artifact.get("frontend_files") or {}
        except Exception:  # noqa: BLE001
            frontend_files = {}
        page_design_doc = stages.get("page_design", {}).get("output") or ""
        expectations = derive_e2e_expectations(requirement, page_design_doc)

        async with acquire_live_preview(pipe.pipeline_id) as live_url:
            # 视觉评审：真实预览截图（live）优先，失败回退渲染桩
            try:
                shot = await render_pipeline_screenshot(pipe.pipeline_id, live_url=live_url)
                structured["vision"] = await judge_output_vision(
                    shot["data_uri"], {"request": requirement}, DEFAULT_EVAL_CRITERIA
                )
            except Exception as exc:  # noqa: BLE001
                structured["vision_error"] = str(exc)[:200]

            # E2E 断言：同一预览上跑（几乎零额外成本）；live 不可用回退桩
            try:
                e2e = await run_e2e_assertions(
                    frontend_files, expectations, screenshot=False, live_url=live_url,
                )
                structured["e2e"] = {
                    "passed": e2e.get("passed"),
                    "issues": e2e.get("issues") or [],
                    "source": "live" if live_url else "stub",
                }
                if e2e.get("harness_error"):
                    structured["e2e"]["note"] = e2e["harness_error"]
                elif e2e.get("stub_incompatible"):
                    structured["e2e"]["note"] = "桩不兼容（模块化 UI 库未注册），跳过"
            except Exception as exc:  # noqa: BLE001
                structured["e2e_error"] = str(exc)[:200]

        return _format_eval_report(structured), structured

    async def _record_eval_safe(self, pipe: "DevPipeline", stages: Dict[str, Any]) -> None:
        """Record pipeline eval in fail-soft mode (completed + failed terminal paths)."""
        try:
            await self._record_pipeline_eval(pipe, stages)
        except Exception as exc:
            logger.warning(
                f"Pipeline eval record suppressed for {getattr(pipe, 'pipeline_id', '?')}: {exc}"
            )

    async def _escalate_to_human(
        self,
        session: AsyncSession,
        pipe: "DevPipeline",
        stages: Dict[str, Any],
        stage_key: str,
        reason: str,
        issues: Optional[List[str]] = None,
        file_hints: Optional[List[str]] = None,
        line_hints: Optional[List[str]] = None,
        emit: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """某阶段重试耗尽 → 暂停交人工（非终态，不写 eval）。

        把失败上下文（issue/文件/行号/重试次数）写进 stages_data，置流水线 NEEDS_HUMAN，
        emit `needs_human` 事件，返回 needs_human 结果。前端介入队列据此展示，人工用
        `update_stage_output` 改产物后调 `/resume`（approve/retry）恢复。
        """
        stage = stages.get(stage_key)
        if not isinstance(stage, dict):
            stage = {}
            stages[stage_key] = stage
        retry_count = stage.get("retry_count", 0)
        stage["status"] = PipelineStatus.NEEDS_HUMAN.value
        stage["error"] = reason
        stage["human_review"] = {
            "stage": stage_key,
            "reason": reason,
            "issues": issues or [],
            "file_hints": file_hints or [],
            "line_hints": line_hints or [],
            "retry_count": retry_count,
        }
        pipe.status = PipelineStatus.NEEDS_HUMAN.value
        pipe.current_stage = stage_key
        pipe.stages_data = json.dumps(stages, ensure_ascii=False)
        pipe.update_time = int(time.time() * 1000)
        await session.commit()
        logger.info(
            f"Pipeline {pipe.pipeline_id}: stage {stage_key} escalated to human after "
            f"{retry_count} retries — {reason[:120]}"
        )
        if emit is not None:
            try:
                await emit({
                    "type": "needs_human",
                    "stage": stage_key,
                    "reason": reason,
                    "issues": issues or [],
                    "file_hints": file_hints or [],
                    "line_hints": line_hints or [],
                    "retry_count": retry_count,
                })
            except Exception:  # noqa: BLE001
                pass
        return {
            "pipeline_id": pipe.pipeline_id,
            "stage": stage_key,
            "status": PipelineStatus.NEEDS_HUMAN.value,
            "error": reason,
            "issues": issues or [],
            "need_human": True,
        }

    def _review_gate_input(self, stage_key: str, pipe: "DevPipeline", stages: Dict[str, Any]) -> str:
        """评审关卡的 input_spec：requirement 用原始需求；其余用需求文档作上下文。"""
        if stage_key == "requirement":
            return pipe.user_request or ""
        req = (stages.get("requirement") or {}).get("output") or ""
        return req or (pipe.user_request or "")

    async def _run_stage_review(
        self, stage_key: str, pipe: "DevPipeline", stages: Dict[str, Any], raw_output: str
    ) -> Dict[str, Any]:
        """子智能体评审关卡：用 LLM-as-judge 评审该阶段产物。

        返回 {passed, score, feedback, issues, judge_error?}。judge 本身出错时 passed=True
        放行（避免评审故障卡死流水线）。纯评审，不改状态——重试/交人工由调用方处理。
        """
        from app.ai.eval_judge import judge_output

        criteria = REVIEW_GATE_CRITERIA[stage_key]
        input_spec = self._review_gate_input(stage_key, pipe, stages)
        result = await judge_output(input_spec, raw_output, criteria)
        if result.get("error"):
            return {"passed": True, "score": None, "feedback": "", "issues": [], "judge_error": result["error"]}

        score = result.get("overall_score")
        per = result.get("per_criterion") or []
        failed = [p for p in per if not p.get("passed")]
        passed = (score is not None and score >= REVIEW_GATE_PASS_SCORE) and not failed
        feedback = ""
        issues: List[str] = []
        if failed:
            feedback = "子智能体评审未通过，请按以下意见完善：\n" + "\n".join(
                f"- {p.get('criterion', '')}：{p.get('reason', '')}" for p in failed
            )
            issues = [f"{p.get('criterion', '')}：{p.get('reason', '')}" for p in failed]
        return {"passed": passed, "score": score, "feedback": feedback, "issues": issues}

    async def _complete_pipeline(
        self,
        session: AsyncSession,
        pipe: 'DevPipeline',
        stages: Dict[str, Any],
        current_stage: str,
        pipeline_id: str,
        emit,
    ) -> Dict[str, Any]:
        """Mark the pipeline COMPLETED: record user evolution + delivery
        knowledge, clean up temp files, emit the completed event, and return
        the completion result dict.

        Centralizes the epilogue that was duplicated by the normal-advance path
        and the timeout code-review fallback path of execute_stage.
        """
        pipe.status = PipelineStatus.COMPLETED.value
        pipe.stages_data = json.dumps(stages, ensure_ascii=False)
        pipe.update_time = int(time.time() * 1000)
        await self._record_user_evolution(session, pipe, stages)
        await self._record_eval_safe(pipe, stages)
        await self._record_delivery_knowledge(pipe, stages)
        await session.commit()
        await _cleanup_pipeline_temp_files(pipeline_id)
        logger.info(f"Pipeline {pipeline_id}: All stages completed")
        await emit({"type": "completed", "stage": current_stage})
        return {
            "pipeline_id": pipeline_id,
            "stage": current_stage,
            "status": "completed",
            "message": "流水线全部完成",
        }

    async def execute_stage(
        self,
        pipeline_id: str,
        user_input: str = "",
        stream_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """执行流水线（迭代循环，带自修复分支和并行 Fan-out）"""
        # Ensure LLM config is loaded from DB before executing
        from app.ai.agents import AgentFactory
        async with async_session_maker() as cfg_session:
            await AgentFactory.load_llm_from_db(cfg_session)

        async def emit(event: Dict[str, Any]) -> None:
            if stream_callback:
                await stream_callback({"pipeline_id": pipeline_id, **event})

        async with async_session_maker() as session:
            pipe = await self._load_pipeline(session, pipeline_id)
            stages = self._parse_stages(pipe)
            pipe_config = json.loads(pipe.skill_config or "{}")
            stage_keys = _stage_keys_for_mode(pipe_config.get("pipeline_mode", "full"))
            fix_feedback = ""
            auto_review_fix_active = False

            while True:
                current_stage = pipe.current_stage

                # ====== eval 阶段：自动测评（LLM-as-judge），写成阶段产物后推进 report ======
                if current_stage == "eval":
                    if not isinstance(stages.get("eval"), dict):
                        stages["eval"] = {"stage": "eval", "agent_type": "QA", "status": "pending"}
                    stages["eval"]["status"] = "running"
                    stages["eval"]["started_at"] = datetime.now().isoformat()
                    pipe.status = PipelineStatus.RUNNING.value
                    pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                    pipe.update_time = int(time.time() * 1000)
                    await session.commit()
                    await emit({"type": "stage_started", "stage": "eval"})

                    try:
                        eval_md, eval_struct = await self._run_eval_stage(pipe, stages, emit)
                    except Exception as exc:  # noqa: BLE001 — 评测失败不阻塞报告
                        logger.warning("Pipeline %s eval 阶段评测失败，跳过: %s", pipeline_id, exc)
                        eval_md = f"自动测评未完成：{exc}"
                        eval_struct = {"error": str(exc)[:200]}

                    stages["eval"].update({
                        "status": "completed",
                        "output": eval_md,
                        "structured_output": eval_struct,
                        "completed_at": datetime.now().isoformat(),
                    })
                    pipe.current_stage = "report"
                    pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                    pipe.update_time = int(time.time() * 1000)
                    await session.commit()
                    await emit({"type": "stage_completed", "stage": "eval", "output": eval_md})
                    fix_feedback = ""
                    continue

                # ====== Fan-out: frontend_dev + backend_dev 并行执行 ======
                if current_stage == "frontend_dev" and "backend_dev" in stages \
                        and stages.get("backend_dev", {}).get("status") == "pending":
                    stages["frontend_dev"]["status"] = "running"
                    stages["frontend_dev"]["started_at"] = datetime.now().isoformat()
                    stages["backend_dev"]["status"] = "running"
                    stages["backend_dev"]["started_at"] = datetime.now().isoformat()
                    pipe.status = PipelineStatus.RUNNING.value
                    pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                    pipe.update_time = int(time.time() * 1000)
                    await session.commit()
                    await emit({"type": "stage_started", "stage": "frontend_dev"})
                    await emit({"type": "stage_started", "stage": "backend_dev"})

                    try:
                        async def _run_branch(stage_key: str, on_chunk):
                            # Each fan-out branch gets its own AsyncSession: a single
                            # AsyncSession cannot service two concurrent gathered
                            # coroutines (retrieve_memories issues concurrent queries).
                            # pipe is read-only here and expire_on_commit=False, so
                            # accessing its attributes does not touch the outer session.
                            async with async_session_maker() as branch_session:
                                async with pipeline_context(pipeline_id, pipe.tenant_id, stage=stage_key):
                                    return await self._run_single_stage(
                                        pipeline_id, stage_key, stages,
                                        pipe, fix_feedback, user_input, branch_session,
                                        on_chunk=on_chunk,
                                    )

                        fe_result, be_result = await asyncio.gather(
                            _run_branch(
                                "frontend_dev",
                                (lambda content: emit({
                                    "type": "chunk",
                                    "stage": "frontend_dev",
                                    "content": content,
                                })) if stream_callback else None,
                            ),
                            _run_branch(
                                "backend_dev",
                                (lambda content: emit({
                                    "type": "chunk",
                                    "stage": "backend_dev",
                                    "content": content,
                                })) if stream_callback else None,
                            ),
                            return_exceptions=True,
                        )

                        # 处理前端结果
                        if isinstance(fe_result, Exception):
                            raise fe_result
                        fe_output, fe_parsed = fe_result
                        await self._record_parallel_stage(
                            pipeline_id, "frontend_dev", "FE",
                            fe_output, fe_parsed, stages, pipe, session, emit,
                        )

                        # 处理后端结果
                        if isinstance(be_result, Exception):
                            raise be_result
                        be_output, be_parsed = be_result
                        await self._record_parallel_stage(
                            pipeline_id, "backend_dev", "BE",
                            be_output, be_parsed, stages, pipe, session, emit,
                        )

                        # 执行 Skill（写文件）
                        for sk, prs in [("frontend_dev", fe_parsed), ("backend_dev", be_parsed)]:
                            await self._execute_stage_skill(
                                pipeline_id, pipe, sk, stages, prs, session,
                            )

                        pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                        pipe.update_time = int(time.time() * 1000)
                        await session.commit()

                        # FE/BE 都完成，推进到 code_review
                        pipe.current_stage = "code_review"
                        pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                        pipe.update_time = int(time.time() * 1000)
                        await session.commit()
                        user_input = ""
                        fix_feedback = ""

                        # 直接 continue 进入循环执行 code_review（不再提前 return 暂停）：
                        # 顺序执行路径会真正跑 code_review，跑完后若 need_confirm 再经
                        # 「分支 1」自行暂停等确认。此前在这里提前 return + 由 confirm_stage
                        # 推进到 testing，会导致 code_review 从未执行就被跳过（full 模式下
                        # 的结构性缺陷——审查阶段永远 pending）。
                        continue

                    except (asyncio.TimeoutError, Exception) as e:
                        err_msg = str(e) if not isinstance(e, asyncio.TimeoutError) \
                            else f"并行执行超时（{LLM_STAGE_TIMEOUT}秒）"
                        logger.error(f"Pipeline {pipeline_id} parallel FE/BE failed: {err_msg}")
                        for sk in ("frontend_dev", "backend_dev"):
                            if stages[sk]["status"] == "running":
                                stages[sk]["status"] = "failed"
                                stages[sk]["error"] = err_msg
                        pipe.status = PipelineStatus.FAILED.value
                        pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                        pipe.update_time = int(time.time() * 1000)
                        await session.commit()
                        await self._record_eval_safe(pipe, stages)
                        await _cleanup_pipeline_temp_files(pipeline_id)
                        await emit({
                            "type": "failed",
                            "stage": "frontend_dev+backend_dev",
                            "error": err_msg,
                        })
                        return {
                            "pipeline_id": pipeline_id,
                            "stage": "frontend_dev+backend_dev",
                            "status": "failed",
                            "error": err_msg,
                        }

                # ====== 单阶段顺序执行 ======
                if (
                    current_stage == "prototype"
                    and pipe_config.get("pipeline_mode") == "frontend_contract_review"
                    and _is_existing_feature_change_request(pipe.user_request or "")
                    and not str(pipe_config.get("selected_frontend_page_path") or "").strip()
                ):
                    frontend_project_id = str(pipe_config.get("frontend_project_id") or pipe.project_id or "").strip()
                    page_candidates: Dict[str, Any] = {
                        "project_id": frontend_project_id,
                        "requires_selection": True,
                        "candidates": [],
                        "uncertain": True,
                    }
                    if frontend_project_id:
                        page_candidates = await get_frontend_page_candidates_for_requirement(
                            frontend_project_id,
                            pipe.user_request or "",
                        )
                    stages[current_stage].update({
                        "status": "waiting_confirm",
                        "output": (
                            "这是对现有功能的改造，但流水线还没有确认要修改的现有前端页面。"
                            "请先从候选页面中选择目标页面，系统会基于该页面重新生成，不会新建替代页面。"
                        ),
                        "structured_output": {
                            "needs_frontend_page_selection": True,
                            "frontend_page_candidates": page_candidates,
                        },
                        "preview_html": "",
                        "code_files": {},
                        "error": "",
                    })
                    pipe.status = PipelineStatus.WAITING_CONFIRM.value
                    pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                    pipe.update_time = int(time.time() * 1000)
                    await session.commit()
                    await emit({
                        "type": "waiting_confirm",
                        "stage": current_stage,
                        "need_confirm": True,
                        "reason": "needs_frontend_page_selection",
                        "result": stages[current_stage]["structured_output"],
                    })
                    return {
                        "pipeline_id": pipeline_id,
                        "stage": current_stage,
                        "status": "waiting_confirm",
                        "need_confirm": True,
                        "reason": "needs_frontend_page_selection",
                        "frontend_page_candidates": page_candidates,
                    }

                stages[current_stage]["status"] = "running"
                stages[current_stage]["started_at"] = datetime.now().isoformat()
                pipe.status = PipelineStatus.RUNNING.value
                pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                pipe.update_time = int(time.time() * 1000)
                await session.commit()
                await emit({"type": "stage_started", "stage": current_stage})

                try:
                    preview_validation_feedback = ""
                    max_attempts = MAX_PREVIEW_GENERATION_ATTEMPTS if current_stage == "prototype" else 1
                    raw_output = ""
                    parsed: Dict[str, Any] = {}
                    for attempt in range(1, max_attempts + 1):
                        attempt_feedback = "\n\n".join(
                            part
                            for part in (fix_feedback, preview_validation_feedback)
                            if part and part.strip()
                        )
                        async with pipeline_context(pipeline_id, pipe.tenant_id, stage=current_stage):
                            raw_output, parsed = await self._run_single_stage(
                                pipeline_id, current_stage, stages,
                                pipe, attempt_feedback, user_input, session,
                                on_chunk=(
                                    lambda content: emit({
                                        "type": "chunk",
                                        "stage": current_stage,
                                        "content": content,
                                    })
                                ) if stream_callback else None,
                            )
                        if attempt_feedback.strip():
                            parsed["applied_feedback"] = attempt_feedback.strip()

                        if current_stage != "prototype":
                            break

                        preview_issues = []
                        if not parsed.get("code_files"):
                            preview_issues.append("预览生成阶段没有产出前端代码文件")
                        else:
                            fixed_files, auto_fixes = _auto_fix_frontend_preview_code_files(
                                parsed.get("code_files", {}),
                                page_design_stage=stages.get("page_design", {}),
                                pipe_config=pipe_config,
                            )
                            if auto_fixes:
                                parsed["code_files"] = fixed_files
                                parsed["auto_fixes"] = auto_fixes
                                raw_output += "\n\n--- 自动修复 ---\n" + "\n".join(auto_fixes)
                                await emit({
                                    "type": "stage_auto_fixed",
                                    "stage": current_stage,
                                    "fixes": auto_fixes,
                                })
                            existing_paths, existing_frontend_files = await _load_existing_preview_page_files(
                                pipe_config,
                                pipe.project_id or "",
                                parsed,
                            )
                            fixed_files, original_fixes = _auto_fix_existing_feature_from_original(
                                parsed.get("code_files", {}),
                                user_request=pipe.user_request or "",
                                existing_frontend_paths=existing_paths,
                                existing_frontend_files=existing_frontend_files,
                            )
                            if original_fixes:
                                parsed["code_files"] = fixed_files
                                parsed["auto_fixes"] = (parsed.get("auto_fixes") or []) + original_fixes
                                raw_output += "\n\n--- 自动修复 ---\n" + "\n".join(original_fixes)
                                await emit({
                                    "type": "stage_auto_fixed",
                                    "stage": current_stage,
                                    "fixes": original_fixes,
                                })
                            expected_pages = _expected_prototype_pages_from_page_design(
                                stages.get("page_design", {})
                            )
                            preview_issues = _validate_frontend_preview_code_files(
                                parsed.get("code_files", {}),
                                user_request=pipe.user_request or "",
                                existing_frontend_paths=existing_paths,
                                existing_frontend_files=existing_frontend_files,
                                expected_pages=expected_pages,
                                page_design_stage=stages.get("page_design", {}),
                                pipe_config=pipe_config,
                            )
                        # 结构校验通过后，跑真实浏览器 E2E 断言（渲染完整性 + 期望控件）；
                        # 缺项并入 preview_issues，复用下方重试→交人工循环。
                        if not preview_issues:
                            e2e_issues = await _e2e_browser_check_issues(
                                parsed.get("code_files", {}),
                                user_request=pipe.user_request or "",
                                page_design_doc=stages.get("page_design", {}).get("output", ""),
                            )
                            if e2e_issues:
                                preview_issues = [f"[E2E] {i}" for i in e2e_issues]
                        if not preview_issues:
                            break

                        repair_tasks = _build_repair_tasks_from_issues(preview_issues[:12])
                        preview_validation_feedback = _build_repair_task_feedback(
                            repair_tasks,
                            preview_issues[:12],
                        )
                        repair_tasks = await _record_repair_attempt_temp_file(
                            pipeline_id,
                            current_stage,
                            attempt,
                            preview_issues[:12],
                            preview_validation_feedback,
                            source_stage="prototype_validation",
                        )
                        await emit({
                            "type": "stage_retry",
                            "stage": current_stage,
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "reason": "preview_validation_failed",
                            "issues": preview_issues[:12],
                            "repair_tasks": repair_tasks,
                        })
                        if attempt >= max_attempts:
                            error_msg = _build_preview_failure_message(repair_tasks, preview_issues[:8])
                            # 保留产物供人工查看；重试耗尽 → 交人工（不再整条 failed）
                            stages[current_stage].update({
                                "output": raw_output,
                                "structured_output": parsed,
                                "preview_html": parsed.get("preview_html", ""),
                                "code_files": parsed.get("code_files", {}),
                            })
                            stages[current_stage]["retry_count"] = attempt
                            return await self._escalate_to_human(
                                session, pipe, stages, current_stage,
                                reason=f"前端预览重试 {attempt} 次仍未通过校验：{error_msg}",
                                issues=preview_issues[:12],
                                emit=emit,
                            )

                    if user_input:
                        user_input = ""

                    if current_stage == "prototype" and not parsed.get("code_files"):
                        stages[current_stage].update({
                            "status": "failed",
                            "output": raw_output,
                            "structured_output": parsed,
                            "preview_html": parsed.get("preview_html", ""),
                            "code_files": {},
                            "error": "预览生成阶段没有产出前端代码文件，请重新生成",
                        })
                        raise ValueError("预览生成阶段没有产出前端代码文件，请重新生成")
                    if current_stage == "prototype":
                        fixed_files, auto_fixes = _auto_fix_frontend_preview_code_files(
                            parsed.get("code_files", {}),
                            page_design_stage=stages.get("page_design", {}),
                            pipe_config=pipe_config,
                        )
                        if auto_fixes:
                            parsed["code_files"] = fixed_files
                            parsed["auto_fixes"] = auto_fixes
                            raw_output += "\n\n--- 自动修复 ---\n" + "\n".join(auto_fixes)
                            await emit({
                                "type": "stage_auto_fixed",
                                "stage": current_stage,
                                "fixes": auto_fixes,
                            })
                        existing_paths, existing_frontend_files = await _load_existing_preview_page_files(
                            pipe_config,
                            pipe.project_id or "",
                            parsed,
                        )
                        fixed_files, original_fixes = _auto_fix_existing_feature_from_original(
                            parsed.get("code_files", {}),
                            user_request=pipe.user_request or "",
                            existing_frontend_paths=existing_paths,
                            existing_frontend_files=existing_frontend_files,
                        )
                        if original_fixes:
                            parsed["code_files"] = fixed_files
                            parsed["auto_fixes"] = (parsed.get("auto_fixes") or []) + original_fixes
                            raw_output += "\n\n--- 自动修复 ---\n" + "\n".join(original_fixes)
                            await emit({
                                "type": "stage_auto_fixed",
                                "stage": current_stage,
                                "fixes": original_fixes,
                            })
                        expected_pages = _expected_prototype_pages_from_page_design(
                            stages.get("page_design", {})
                        )
                        preview_issues = _validate_frontend_preview_code_files(
                            parsed.get("code_files", {}),
                            user_request=pipe.user_request or "",
                            existing_frontend_paths=existing_paths,
                            existing_frontend_files=existing_frontend_files,
                            expected_pages=expected_pages,
                            page_design_stage=stages.get("page_design", {}),
                            pipe_config=pipe_config,
                        )
                        # 终检：结构通过后再跑 E2E，缺项一并计入交人工 issue
                        if not preview_issues:
                            e2e_issues = await _e2e_browser_check_issues(
                                parsed.get("code_files", {}),
                                user_request=pipe.user_request or "",
                                page_design_doc=stages.get("page_design", {}).get("output", ""),
                            )
                            if e2e_issues:
                                preview_issues = [f"[E2E] {i}" for i in e2e_issues]
                        if preview_issues:
                            repair_tasks = _build_repair_tasks_from_issues(preview_issues[:12])
                            await _record_repair_attempt_temp_file(
                                pipeline_id,
                                current_stage,
                                max_attempts + 1,
                                preview_issues[:12],
                                _build_repair_task_feedback(repair_tasks, preview_issues[:12]),
                                source_stage="prototype_validation_final",
                            )
                            error_msg = _build_preview_failure_message(repair_tasks, preview_issues[:8])
                            # 终检仍不通过 → 交人工（保留产物）
                            stages[current_stage].update({
                                "output": raw_output,
                                "structured_output": parsed,
                                "preview_html": parsed.get("preview_html", ""),
                                "code_files": parsed.get("code_files", {}),
                            })
                            stages[current_stage]["retry_count"] = max_attempts
                            return await self._escalate_to_human(
                                session, pipe, stages, current_stage,
                                reason=f"前端预览终检未通过：{error_msg}",
                                issues=preview_issues[:12],
                                emit=emit,
                            )
                    if current_stage == "ui_preview" and not (parsed.get("preview_html") or "").strip():
                        raise ValueError("预览生成阶段没有产出可渲染 HTML，请重新生成")

                    if (
                        current_stage == "code_review"
                        and auto_review_fix_active
                        and parsed.get("review_passed") is not False
                    ):
                        repaired_stage = _fix_loop_stage_for_mode(stage_keys)
                        repaired_structured = stages.get(repaired_stage, {}).get("structured_output") or {}
                        auto_repair_summary = _build_auto_repair_summary(
                            pipe.retry_count,
                            repaired_stage,
                            fix_feedback,
                            repaired_structured.get("auto_fixes") or [],
                        )
                        parsed["auto_repair_summary"] = auto_repair_summary
                        parsed["auto_repair_iterations"] = pipe.retry_count
                        raw_output += "\n\n--- 自动修复摘要 ---\n" + auto_repair_summary

                    # 更新阶段状态
                    stages[current_stage].update({
                        "status": "completed",
                        "output": raw_output,
                        "structured_output": parsed,
                        "preview_html": parsed.get("preview_html", ""),
                        "code_files": parsed.get("code_files", {}),
                        "revision_feedback": "",
                        "completed_at": datetime.now().isoformat(),
                    })
                    pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                    await session.commit()
                    await emit({
                        "type": "stage_completed",
                        "stage": current_stage,
                        "output": raw_output,
                        "preview_html": parsed.get("preview_html", ""),
                        "result": parsed,
                    })

                    # 保存记忆
                    agent_type = _get_stage_agent(current_stage)
                    await self._save_stage_memory(
                        pipeline_id, current_stage, agent_type, raw_output, parsed, pipe.tenant_id,
                        db_session=session
                    )

                    # ---- Skill 调用：将 LLM 输出落地为实际操作 ----
                    await self._execute_stage_skill(
                        pipeline_id, pipe, current_stage, stages, parsed, session
                    )

                    # ---- 条件分支：自修复决策 ----

                    # 分支 0: Code Review 失败 → 自动回退到前端开发阶段修复（优先级最高）
                    if (
                        current_stage == "code_review"
                        and parsed.get("review_passed") is False
                        and _has_code_review_fix_loop(stage_keys)
                    ):
                        if pipe.retry_count < MAX_FIX_ITERATIONS:
                            pipe.retry_count += 1
                            loop_stage = _fix_loop_stage_for_mode(stage_keys)
                            auto_review_fix_active = True
                            mismatch_feedback, fix_feedback = _build_code_review_fix_feedback(
                                parsed, raw_output
                            )
                            pipe.current_stage = loop_stage
                            repair_issues = [
                                part
                                for part in (
                                    parsed.get("contract_alignment", ""),
                                    mismatch_feedback,
                                    parsed.get("fix_suggestions", ""),
                                )
                                if part and str(part).strip()
                            ]
                            await _record_repair_attempt_temp_file(
                                pipeline_id,
                                loop_stage,
                                pipe.retry_count,
                                repair_issues,
                                fix_feedback,
                                source_stage="code_review",
                            )
                            idx = stage_keys.index(loop_stage)
                            for sk in stage_keys[idx:]:
                                if sk not in stages:
                                    continue
                                stages[sk]["status"] = "pending"
                                stages[sk]["output"] = ""
                                stages[sk]["error"] = ""
                                stages[sk]["structured_output"] = {}
                                stages[sk]["code_files"] = {}
                                stages[sk]["preview_html"] = ""
                                stages[sk]["completed_at"] = None
                                stages[sk]["revision_feedback"] = fix_feedback if sk == loop_stage else ""
                            pipe.status = PipelineStatus.RUNNING.value
                            pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                            pipe.update_time = int(time.time() * 1000)
                            await session.commit()

                            logger.info(f"Pipeline {pipeline_id}: Code review failed, "
                                       f"looping back to {loop_stage} (iteration {pipe.retry_count}/{MAX_FIX_ITERATIONS})")
                            await self._save_stage_memory(
                                pipeline_id, "code_review_fix", agent_type,
                                f"第{pipe.retry_count}次修复: {fix_feedback[:300]}",
                                {}, pipe.tenant_id, db_session=session
                            )
                            continue  # 继续循环，重新执行修复阶段
                        else:
                            # 修复耗尽 → 交人工，带文件/行号（取自审查 field_mismatches）
                            cr_issues = [
                                str(p) for p in (
                                    parsed.get("contract_alignment", ""),
                                    parsed.get("fix_suggestions", ""),
                                ) if p and str(p).strip()
                            ]
                            fm = parsed.get("field_mismatches") or []
                            file_hints, line_hints = [], []
                            for item in fm if isinstance(fm, list) else []:
                                loc = str(item.get("location") or "").strip()
                                if loc:
                                    file_hints.append(loc)
                                    if item.get("fix"):
                                        line_hints.append(str(item["fix"]))
                            stages[current_stage]["retry_count"] = pipe.retry_count
                            return await self._escalate_to_human(
                                session, pipe, stages, current_stage,
                                reason=f"代码审查在 {MAX_FIX_ITERATIONS} 次自动修复后仍未通过",
                                issues=cr_issues or ["代码审查未通过，请人工复核"],
                                file_hints=file_hints,
                                line_hints=line_hints,
                                emit=emit,
                            )

                    # 分支 0b: 测试失败 → 自动回退到前端开发阶段修复 Bug
                    if current_stage == "testing" and not parsed.get("tests_passed", True):
                        if pipe.retry_count < MAX_FIX_ITERATIONS:
                            pipe.retry_count += 1
                            fix_feedback = f"测试发现问题，请修复:\n{parsed.get('bug_details', raw_output[:500])}"
                            loop_stage = _fix_loop_stage_for_mode(stage_keys)
                            pipe.current_stage = loop_stage
                            idx = stage_keys.index(loop_stage)
                            for sk in stage_keys[idx:]:
                                if sk not in stages:
                                    continue
                                stages[sk]["status"] = "pending"
                                stages[sk]["output"] = ""
                                stages[sk]["error"] = ""
                                stages[sk]["code_files"] = {}
                                stages[sk]["preview_html"] = ""
                            pipe.status = PipelineStatus.RUNNING.value
                            pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                            pipe.update_time = int(time.time() * 1000)
                            await session.commit()

                            logger.info(f"Pipeline {pipeline_id}: Tests failed, "
                                       f"looping back to {loop_stage} (iteration {pipe.retry_count}/{MAX_FIX_ITERATIONS})")
                            continue
                        else:
                            # 测试修复耗尽 → 交人工，带 bug 详情
                            test_issues = []
                            bug_details = parsed.get("bug_details") or raw_output[:800]
                            if bug_details:
                                test_issues = [ln.strip() for ln in str(bug_details).splitlines() if ln.strip()][:12]
                            stages[current_stage]["retry_count"] = pipe.retry_count
                            return await self._escalate_to_human(
                                session, pipe, stages, current_stage,
                                reason=f"自动化测试在 {MAX_FIX_ITERATIONS} 次自动修复后仍有问题",
                                issues=test_issues or ["自动化测试未通过，请人工复核"],
                                emit=emit,
                            )

                    # 子智能体评审关卡（requirement/delivery）：不过则带意见重生成，
                    # 重试 MAX_FIX_ITERATIONS 次仍不过 → 交人工（步骤 2/3/5）
                    if current_stage in REVIEW_GATE_CRITERIA and not auto_review_fix_active:
                        gate = await self._run_stage_review(current_stage, pipe, stages, raw_output)
                        if not gate["passed"]:
                            rc = int(stages[current_stage].get("retry_count", 0)) + 1
                            stages[current_stage]["retry_count"] = rc
                            stage_name = STAGE_NAMES.get(current_stage, current_stage)
                            if rc <= MAX_FIX_ITERATIONS:
                                fix_feedback = gate["feedback"]
                                stages[current_stage].update({
                                    "status": "pending",
                                    "output": "",
                                    "structured_output": {},
                                    "code_files": {},
                                    "preview_html": "",
                                    "error": "",
                                    "revision_feedback": gate["feedback"],
                                })
                                pipe.current_stage = current_stage
                                pipe.status = PipelineStatus.RUNNING.value
                                pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                                pipe.update_time = int(time.time() * 1000)
                                await session.commit()
                                await emit({
                                    "type": "stage_retry",
                                    "stage": current_stage,
                                    "attempt": rc,
                                    "max_attempts": MAX_FIX_ITERATIONS,
                                    "reason": "review_gate_failed",
                                    "score": gate.get("score"),
                                    "issues": gate["issues"],
                                })
                                continue
                            return await self._escalate_to_human(
                                session, pipe, stages, current_stage,
                                reason=f"{stage_name} 子智能体评审 {MAX_FIX_ITERATIONS} 次重生成后仍未通过"
                                       f"（评分 {gate.get('score')}）",
                                issues=gate["issues"],
                                emit=emit,
                            )

                    # 分支 1: 需要用户确认 → 暂停
                    should_pause = _should_pause_for_stage(current_stage, auto_review_fix_active)
                    if (
                        should_pause
                        and current_stage == "code_review"
                        and auto_review_fix_active
                        and parsed.get("review_passed") is not False
                        and pipe_config.get("pipeline_mode") == "frontend_contract_review"
                    ):
                        should_pause = False

                    if should_pause:
                        pipe.status = PipelineStatus.WAITING_CONFIRM.value
                        pipe.update_time = int(time.time() * 1000)
                        await session.commit()
                        await emit({
                            "type": "waiting_confirm",
                            "stage": current_stage,
                            "need_confirm": True,
                            "preview_html": parsed.get("preview_html", ""),
                            "result": parsed,
                        })
                        return {
                            "pipeline_id": pipeline_id,
                            "stage": current_stage,
                            "status": "waiting_confirm",
                            "output": raw_output,
                            "preview_html": parsed.get("preview_html", ""),
                            "need_confirm": True,
                        }

                    # 分支 4: 测试通过 → 重置重试计数器
                    if current_stage == "testing":
                        pipe.retry_count = 0

                    # 正常推进到下一阶段
                    try:
                        idx = stage_keys.index(current_stage)
                    except ValueError:
                        # 旧流水线阶段不在当前定义中，跳到末尾
                        idx = len(stage_keys) - 1
                    if idx + 1 >= len(stage_keys):
                        return await self._complete_pipeline(
                            session, pipe, stages, current_stage, pipeline_id, emit
                        )

                    next_stage = stage_keys[idx + 1]
                    pipe.current_stage = next_stage
                    pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                    pipe.update_time = int(time.time() * 1000)
                    await session.commit()
                    await emit({"type": "stage_advanced", "stage": next_stage})
                    fix_feedback = ""  # 清除修复反馈
                    # 继续循环

                except asyncio.TimeoutError:
                    logger.error(f"Pipeline {pipeline_id} stage {current_stage} timed out after {LLM_STAGE_TIMEOUT}s")
                    if current_stage == "code_review":
                        raw_output, parsed = _build_deterministic_code_review_result(
                            stages,
                            user_request=pipe.user_request or "",
                            pipe_config=pipe_config,
                        )
                        stages[current_stage].update({
                            "status": "completed",
                            "output": raw_output,
                            "structured_output": parsed,
                            "preview_html": "",
                            "code_files": {},
                            "revision_feedback": "",
                            "completed_at": datetime.now().isoformat(),
                            "error": "",
                        })
                        pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                        await session.commit()
                        await emit({
                            "type": "stage_completed",
                            "stage": current_stage,
                            "output": raw_output,
                            "result": parsed,
                        })
                        agent_type = _get_stage_agent(current_stage)
                        await self._save_stage_memory(
                            pipeline_id,
                            current_stage,
                            agent_type,
                            raw_output,
                            parsed,
                            pipe.tenant_id,
                            db_session=session,
                        )
                        if parsed.get("review_passed") is False:
                            stages[current_stage]["status"] = "failed"
                            stages[current_stage]["error"] = parsed.get("fix_suggestions") or "确定性代码审查未通过"
                            pipe.status = PipelineStatus.FAILED.value
                            pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                            pipe.update_time = int(time.time() * 1000)
                            await session.commit()
                            await self._record_eval_safe(pipe, stages)
                            await _cleanup_pipeline_temp_files(pipeline_id)
                            await emit({
                                "type": "failed",
                                "stage": current_stage,
                                "error": stages[current_stage]["error"],
                            })
                            return {
                                "pipeline_id": pipeline_id,
                                "stage": current_stage,
                                "status": "failed",
                                "error": stages[current_stage]["error"],
                            }
                        if _should_pause_for_stage(current_stage, auto_review_fix_active):
                            pipe.status = PipelineStatus.WAITING_CONFIRM.value
                            pipe.update_time = int(time.time() * 1000)
                            await session.commit()
                            await emit({
                                "type": "waiting_confirm",
                                "stage": current_stage,
                                "need_confirm": True,
                                "result": parsed,
                            })
                            return {
                                "pipeline_id": pipeline_id,
                                "stage": current_stage,
                                "status": "waiting_confirm",
                                "output": raw_output,
                                "need_confirm": True,
                            }
                        try:
                            idx = stage_keys.index(current_stage)
                        except ValueError:
                            idx = len(stage_keys) - 1
                        if idx + 1 >= len(stage_keys):
                            return await self._complete_pipeline(
                                session, pipe, stages, current_stage, pipeline_id, emit
                            )
                        pipe.current_stage = stage_keys[idx + 1]
                        pipe.status = PipelineStatus.RUNNING.value
                        pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                        pipe.update_time = int(time.time() * 1000)
                        await session.commit()
                        await emit({"type": "stage_advanced", "stage": pipe.current_stage})
                        continue
                    stages[current_stage]["status"] = "failed"
                    stages[current_stage]["error"] = f"阶段超时（{LLM_STAGE_TIMEOUT}秒），LLM 未返回结果，请重试"
                    pipe.status = PipelineStatus.FAILED.value
                    pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                    pipe.update_time = int(time.time() * 1000)
                    await session.commit()
                    await self._record_eval_safe(pipe, stages)
                    await _cleanup_pipeline_temp_files(pipeline_id)
                    await emit({
                        "type": "failed",
                        "stage": current_stage,
                        "error": f"stage timed out after {LLM_STAGE_TIMEOUT}s",
                    })
                    return {
                        "pipeline_id": pipeline_id,
                        "stage": current_stage,
                        "status": "failed",
                        "error": f"阶段超时（{LLM_STAGE_TIMEOUT}秒），请点击重新执行",
                    }
                except Exception as e:
                    logger.exception("Pipeline %s stage %s failed", pipeline_id, current_stage)
                    stages[current_stage]["status"] = "failed"
                    stages[current_stage]["error"] = str(e)
                    pipe.status = PipelineStatus.FAILED.value
                    pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                    pipe.update_time = int(time.time() * 1000)
                    await session.commit()
                    await self._record_eval_safe(pipe, stages)
                    await _cleanup_pipeline_temp_files(pipeline_id)
                    await emit({
                        "type": "failed",
                        "stage": current_stage,
                        "error": str(e),
                    })
                    return {
                        "pipeline_id": pipeline_id,
                        "stage": current_stage,
                        "status": "failed",
                        "error": str(e),
                    }

    # ==================== 用户确认 ====================

    async def execute_stage_stream(
        self, pipeline_id: str, user_input: str = ""
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute the pipeline and stream stage/chunk events for the UI."""
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

        async def publish(event: Dict[str, Any]) -> None:
            await queue.put(event)

        task = asyncio.create_task(
            self.execute_stage(pipeline_id, user_input, stream_callback=publish)
        )

        try:
            while True:
                if task.done() and queue.empty():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield event
                except asyncio.TimeoutError:
                    if task.done():
                        continue
                    yield {"type": "heartbeat", "pipeline_id": pipeline_id}

            result = await task
            yield {
                "type": "done",
                "pipeline_id": pipeline_id,
                "status": result.get("status", ""),
                "stage": result.get("stage", ""),
                "result": result,
            }
        except Exception as e:
            logger.error(f"Pipeline {pipeline_id} stream failed: {e}")
            yield {
                "type": "error",
                "pipeline_id": pipeline_id,
                "error": str(e),
            }
        finally:
            if not task.done():
                task.cancel()

    async def confirm_stage(self, pipeline_id: str, confirmed: bool,
                            feedback: str = "") -> Dict[str, Any]:
        from app.ai.agents import AgentFactory
        async with async_session_maker() as cfg_session:
            await AgentFactory.load_llm_from_db(cfg_session)

        async with async_session_maker() as session:
            pipe = await self._load_pipeline(session, pipeline_id)

            if pipe.status != PipelineStatus.WAITING_CONFIRM.value:
                return {"pipeline_id": pipeline_id, "error": "当前阶段不需要确认"}

            stages = self._parse_stages(pipe)
            current_stage = pipe.current_stage
            current_structured = stages.get(current_stage, {}).get("structured_output") or {}
            if (
                confirmed
                and current_structured.get("needs_frontend_page_selection")
                and not str((json.loads(pipe.skill_config or "{}")).get("selected_frontend_page_path") or "").strip()
            ):
                return {
                    "pipeline_id": pipeline_id,
                    "stage": current_stage,
                    "status": "waiting_confirm",
                    "error": "请先选择要修改的现有前端页面，不能直接确认跳过。",
                }

            if not confirmed:
                # 用户拒绝，退回该阶段
                stages[current_stage]["status"] = "pending"
                stages[current_stage]["output"] = ""
                stages[current_stage]["structured_output"] = {}
                stages[current_stage]["preview_html"] = ""
                stages[current_stage]["code_files"] = {}
                stages[current_stage]["error"] = ""
                stages[current_stage]["revision_feedback"] = feedback.strip() if feedback else ""
                pipe.status = PipelineStatus.PENDING.value
                pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                pipe.update_time = int(time.time() * 1000)
                await session.commit()
                # 退回后由前端调用 execute 重新执行（不在这里同步调用 LLM，避免超时）
                return {
                    "pipeline_id": pipeline_id,
                    "stage": current_stage,
                    "status": "pending",
                    "message": "已退回，可重新执行",
                }

            # 确认通过，推进到下一阶段
            pipe_config = json.loads(pipe.skill_config or "{}")
            stage_keys = _stage_keys_for_mode(pipe_config.get("pipeline_mode", "full"))
            try:
                idx = stage_keys.index(current_stage)
            except ValueError:
                idx = len(stage_keys) - 1
            if idx + 1 >= len(stage_keys):
                pipe.status = PipelineStatus.COMPLETED.value
                pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                pipe.update_time = int(time.time() * 1000)
                await self._record_user_evolution(session, pipe, stages)
                await self._record_delivery_knowledge(pipe, stages)
                await session.commit()
                return {"pipeline_id": pipeline_id, "status": "completed"}

            next_stage = stage_keys[idx + 1]
            pipe.current_stage = next_stage
            pipe.status = PipelineStatus.PENDING.value
            pipe.stages_data = json.dumps(stages, ensure_ascii=False)
            pipe.update_time = int(time.time() * 1000)
            await session.commit()

            # 返回推进结果，前端负责调用 execute 触发下一阶段
            next_needs_confirm = _stage_needs_confirm(next_stage)
            return {
                "pipeline_id": pipeline_id,
                "stage": next_stage,
                "status": "pending",
                "need_confirm": next_needs_confirm,
                "message": f"已推进到 {STAGE_NAMES.get(next_stage, next_stage)}",
            }

    async def resume_from_human(self, pipeline_id: str, action: str,
                                feedback: str = "") -> Dict[str, Any]:
        """人工介入恢复：从 needs_human 状态继续。

        - action="approve"：接受人工（可能已用 update_stage_output 改过）产物，推进到下一阶段。
        - action="retry"：置回 pending + revision_feedback，由前端调 execute 重新生成。
        两路都重置该阶段 retry_count，并清掉 human_review 标记。
        """
        async with async_session_maker() as session:
            pipe = await self._load_pipeline(session, pipeline_id)
            if pipe.status != PipelineStatus.NEEDS_HUMAN.value:
                return {"pipeline_id": pipeline_id, "error": "当前流水线不在待人工状态"}

            stages = self._parse_stages(pipe)
            current_stage = pipe.current_stage
            stage = stages.get(current_stage)
            if not isinstance(stage, dict):
                stage = {}
                stages[current_stage] = stage

            stage["retry_count"] = 0
            stage.pop("human_review", None)

            if action == "retry":
                stage.update({
                    "status": "pending",
                    "output": "",
                    "structured_output": {},
                    "preview_html": "",
                    "code_files": {},
                    "error": "",
                    "revision_feedback": (feedback.strip() if feedback else stage.get("error", "")),
                })
                pipe.status = PipelineStatus.PENDING.value
                pipe.current_stage = current_stage
                pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                pipe.update_time = int(time.time() * 1000)
                await session.commit()
                return {
                    "pipeline_id": pipeline_id,
                    "stage": current_stage,
                    "status": "pending",
                    "message": "已退回重新生成，请执行当前阶段",
                }

            # action == "approve"（默认）：标记本阶段完成，推进到下一阶段
            stage["status"] = "completed"
            stage["error"] = ""
            if not stage.get("completed_at"):
                stage["completed_at"] = datetime.now().isoformat()
            pipe_config = json.loads(pipe.skill_config or "{}")
            stage_keys = _stage_keys_for_mode(pipe_config.get("pipeline_mode", "full"))
            try:
                idx = stage_keys.index(current_stage)
            except ValueError:
                idx = len(stage_keys) - 1
            if idx + 1 >= len(stage_keys):
                pipe.status = PipelineStatus.COMPLETED.value
                pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                pipe.update_time = int(time.time() * 1000)
                await self._record_user_evolution(session, pipe, stages)
                await self._record_delivery_knowledge(pipe, stages)
                await session.commit()
                return {"pipeline_id": pipeline_id, "status": "completed"}

            next_stage = stage_keys[idx + 1]
            pipe.current_stage = next_stage
            pipe.status = PipelineStatus.PENDING.value
            pipe.stages_data = json.dumps(stages, ensure_ascii=False)
            pipe.update_time = int(time.time() * 1000)
            await session.commit()
            return {
                "pipeline_id": pipeline_id,
                "stage": next_stage,
                "status": "pending",
                "need_confirm": _stage_needs_confirm(next_stage),
                "message": f"人工通过 {STAGE_NAMES.get(current_stage, current_stage)}，已推进到 {STAGE_NAMES.get(next_stage, next_stage)}",
            }

    async def list_intervention_pipelines(self, tenant_id: int) -> List[Dict[str, Any]]:
        """列出租户内所有 needs_human 流水线（供开发人员介入队列）。"""
        async with async_session_maker() as session:
            stmt = select(DevPipeline).where(
                DevPipeline.tenant_id == tenant_id,
                DevPipeline.status == PipelineStatus.NEEDS_HUMAN.value,
                DevPipeline.is_deleted == 0,
            ).order_by(DevPipeline.update_time.desc())
            rows = (await session.execute(stmt)).scalars().all()
            result: List[Dict[str, Any]] = []
            for pipe in rows:
                stages = self._parse_stages(pipe)
                stage = stages.get(pipe.current_stage) or {}
                human_review = stage.get("human_review") or {}
                result.append({
                    "pipeline_id": pipe.pipeline_id,
                    "current_stage": pipe.current_stage,
                    "current_stage_name": STAGE_NAMES.get(pipe.current_stage, pipe.current_stage),
                    "user_request": (pipe.user_request or "")[:120],
                    "update_time": pipe.update_time,
                    "reason": human_review.get("reason") or stage.get("error", ""),
                    "issues": human_review.get("issues", []),
                    "file_hints": human_review.get("file_hints", []),
                    "retry_count": human_review.get("retry_count", 0),
                })
            return result

    # ==================== 查询方法 ====================

    async def get_pipeline_status(self, pipeline_id: str) -> Dict[str, Any]:
        async with async_session_maker() as session:
            pipe = await self._load_pipeline(session, pipeline_id)
            status = self._to_status_dict(pipe)
            pipe_config = json.loads(pipe.skill_config or "{}")
            current_stage = pipe.current_stage
            current_structured = (
                (status.get("stages") or {})
                .get(current_stage or "", {})
                .get("structured_output")
                or {}
            )
            if (
                pipe.status == PipelineStatus.WAITING_CONFIRM.value
                and current_stage == "prototype"
                and pipe_config.get("pipeline_mode") == "frontend_contract_review"
                and _is_existing_feature_change_request(pipe.user_request or "")
                and not str(pipe_config.get("selected_frontend_page_path") or "").strip()
                and not current_structured.get("needs_frontend_page_selection")
            ):
                frontend_project_id = str(pipe_config.get("frontend_project_id") or pipe.project_id or "").strip()
                page_candidates: Dict[str, Any] = {
                    "project_id": frontend_project_id,
                    "requires_selection": True,
                    "candidates": [],
                    "uncertain": True,
                }
                if frontend_project_id:
                    page_candidates = await get_frontend_page_candidates_for_requirement(
                        frontend_project_id,
                        pipe.user_request or "",
                    )
                stage_status = (status.get("stages") or {}).get(current_stage, {})
                stage_status["structured_output"] = {
                    **current_structured,
                    "needs_frontend_page_selection": True,
                    "frontend_page_candidates": page_candidates,
                }
                stage_status["output"] = (
                    "这是现有页面功能改造，请先选择要修改的页面功能。"
                    "系统会基于所选页面重新生成，不会新建替代页面。"
                )
                status["stages"][current_stage] = stage_status
            return status

    async def get_preview(self, pipeline_id: str) -> Dict[str, Any]:
        async with async_session_maker() as session:
            pipe = await self._load_pipeline(session, pipeline_id)
            stages = self._parse_stages(pipe)
            preview_stage = stages.get("prototype", {}) or stages.get("ui_preview", {})
            if not preview_stage.get("preview_html"):
                preview_stage = stages.get("ui_preview", {}) or preview_stage
            return {
                "pipeline_id": pipeline_id,
                "preview_html": preview_stage.get("preview_html", ""),
                "output": preview_stage.get("output", ""),
            }

    async def get_pipeline_artifact(self, pipeline_id: str) -> Dict[str, Any]:
        async with async_session_maker() as session:
            pipe = await self._load_pipeline(session, pipeline_id)
            stages = self._parse_stages(pipe)
            artifact = _build_pipeline_artifact(stages)
            pipe_config = json.loads(pipe.skill_config or "{}")
            artifact.update({
                "pipeline_id": pipeline_id,
                "status": pipe.status,
                "pipeline_mode": pipe_config.get("pipeline_mode", "full"),
            })
            return artifact

    async def get_pipeline_frontend_project_snapshot(self, pipeline_id: str) -> Dict[str, Any]:
        async with async_session_maker() as session:
            pipe = await self._load_pipeline(session, pipeline_id)
            pipe_config = json.loads(pipe.skill_config or "{}")
            snapshot = pipe_config.get("project_skill_snapshot") or {}
            if not snapshot:
                return {}
            return dict(snapshot)

    async def get_stage_output(self, pipeline_id: str, stage: str = "") -> Dict[str, Any]:
        async with async_session_maker() as session:
            pipe = await self._load_pipeline(session, pipeline_id)
            stages = self._parse_stages(pipe)
            target = stage or pipe.current_stage
            stage_data = stages.get(target, {})
            return {
                "pipeline_id": pipeline_id,
                "stage": target,
                "output": stage_data.get("output", ""),
                "structured_output": stage_data.get("structured_output", {}),
                "preview_html": stage_data.get("preview_html", ""),
                "code_files": stage_data.get("code_files", {}),
            }

    async def update_stage_output(self, pipeline_id: str, stage: str, output: str,
                                  skip_validation: bool = False) -> Dict[str, Any]:
        target = str(stage or "").strip()
        if not target:
            raise ValueError("阶段不能为空")
        if output is None:
            output = ""
        async with async_session_maker() as session:
            pipe = await self._load_pipeline(session, pipeline_id)
            stages = self._parse_stages(pipe)
            if target not in stages:
                raise ValueError(f"阶段不存在: {target}")

            stage_data = stages[target]
            previous_output = stage_data.get("output", "")
            parsed = stage_data.get("structured_output") or {}
            if output != previous_output or not parsed:
                parsed = _parse_agent_output(target, output)
                if target in ("prototype", "frontend_dev") and parsed.get("code_files"):
                    fixed_files, _auto_fixes = _auto_fix_frontend_preview_code_files(
                        parsed.get("code_files", {}),
                        page_design_stage=stages.get("page_design", {}),
                    )
                    parsed["code_files"] = fixed_files
                    pipe_config = json.loads(pipe.skill_config or "{}")
                    existing_paths, existing_frontend_files = await _load_existing_preview_page_files(
                        pipe_config,
                        pipe.project_id or "",
                        parsed,
                    )
                    fixed_files, _original_fixes = _auto_fix_existing_feature_from_original(
                        parsed.get("code_files", {}),
                        user_request=pipe.user_request or "",
                        existing_frontend_paths=existing_paths,
                        existing_frontend_files=existing_frontend_files,
                    )
                    parsed["code_files"] = fixed_files
                    preview_issues = _validate_frontend_preview_code_files(
                        parsed.get("code_files", {}),
                        user_request=pipe.user_request or "",
                        existing_frontend_paths=existing_paths,
                        existing_frontend_files=existing_frontend_files,
                        expected_pages=_expected_prototype_pages_from_page_design(stages.get("page_design", {})),
                    )
                    if preview_issues:
                        # needs_human 下人工介入保存：不强制拦截，仅记录为警告，允许人工覆盖后继续
                        if skip_validation:
                            parsed["_manual_override_warnings"] = preview_issues[:8]
                        else:
                            raise ValueError("保存内容未通过可运行性约束: " + "；".join(preview_issues[:6]))

            stage_data["output"] = output
            stage_data["structured_output"] = parsed
            stage_data["preview_html"] = parsed.get("preview_html", stage_data.get("preview_html", ""))
            stage_data["code_files"] = parsed.get("code_files", stage_data.get("code_files", {}))
            stage_data["manual_edited"] = True
            stage_data["manual_edited_at"] = datetime.now().isoformat()
            stages[target] = stage_data

            pipe.stages_data = json.dumps(stages, ensure_ascii=False)
            pipe.update_time = int(time.time() * 1000)
            await session.commit()
            return {
                "pipeline_id": pipeline_id,
                "stage": target,
                "output": stage_data.get("output", ""),
                "structured_output": stage_data.get("structured_output", {}),
                "preview_html": stage_data.get("preview_html", ""),
                "code_files": stage_data.get("code_files", {}),
            }

    async def list_pipelines(self, tenant_id: int = 0) -> List[Dict[str, Any]]:
        async with async_session_maker() as session:
            query = select(DevPipeline).where(DevPipeline.is_deleted == 0)
            if tenant_id:
                query = query.where(DevPipeline.tenant_id == tenant_id)
            query = query.order_by(DevPipeline.create_time.desc())
            result = await session.execute(query)
            pipes = result.scalars().all()
            return [
                {
                    "pipeline_id": p.pipeline_id,
                    "project_id": p.project_id or "",
                    "user_request": p.user_request or "",
                    "status": p.status,
                    "current_stage": p.current_stage,
                    "retry_count": p.retry_count,
                    "create_time": p.create_time,
                    "update_time": p.update_time,
                }
                for p in pipes
            ]

    async def list_eval_pipelines(
        self, tenant_id: int = 0, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """带评测分数的 pipeline 列表（left join pipeline_eval_result）。"""
        from app.models.pipeline_eval import PipelineEvalResult

        async with async_session_maker() as session:
            query = (
                select(DevPipeline, PipelineEvalResult)
                .outerjoin(
                    PipelineEvalResult,
                    (PipelineEvalResult.pipeline_id == DevPipeline.pipeline_id)
                    & (PipelineEvalResult.is_deleted == 0),
                )
                .where(DevPipeline.is_deleted == 0)
            )
            if tenant_id:
                query = query.where(DevPipeline.tenant_id == tenant_id)
            query = query.order_by(DevPipeline.create_time.desc()).limit(limit)
            result = await session.execute(query)
            rows = result.all()
            return [
                {
                    "pipeline_id": p.pipeline_id,
                    "project_id": p.project_id or "",
                    "user_request": (p.user_request or "")[:120],
                    "status": p.status,
                    "current_stage": p.current_stage,
                    "retry_count": p.retry_count,
                    "create_time": p.create_time,
                    "update_time": p.update_time,
                    "overall_score": e.overall_score if e else None,
                    "pm_quality_score": e.pm_quality_score if e else None,
                    "design_quality_score": e.design_quality_score if e else None,
                    "preview_quality_score": e.preview_quality_score if e else None,
                    "review_passed": e.review_passed if e else None,
                    "tests_passed": e.tests_passed if e else None,
                }
                for p, e in rows
            ]

    async def get_eval_stats(
        self, tenant_id: int = 0, days: int = 30
    ) -> Dict[str, Any]:
        """tenant 维度评测聚合：平均分、通过率、retry 均值、分桶、按天趋势。"""
        from app.models.pipeline_eval import PipelineEvalResult

        cutoff = int((time.time() - days * 86400) * 1000)
        async with async_session_maker() as session:
            query = select(PipelineEvalResult).where(
                PipelineEvalResult.is_deleted == 0,
                PipelineEvalResult.create_time >= cutoff,
            )
            if tenant_id:
                query = query.where(PipelineEvalResult.tenant_id == tenant_id)
            result = await session.execute(query)
            records = result.scalars().all()

        if not records:
            return {
                "total": 0, "avg_overall_score": None, "review_pass_rate": None,
                "tests_pass_rate": None, "avg_retry_count": None,
                "score_buckets": {"lt60": 0, "60_80": 0, "gte80": 0},
                "daily_trend": [],
            }

        scores = [r.overall_score for r in records if r.overall_score is not None]
        review = [r.review_passed for r in records if r.review_passed is not None]
        tests = [r.tests_passed for r in records if r.tests_passed is not None]
        retries = [r.retry_count for r in records if r.retry_count is not None]

        buckets = {"lt60": 0, "60_80": 0, "gte80": 0}
        for s in scores:
            if s < 60:
                buckets["lt60"] += 1
            elif s < 80:
                buckets["60_80"] += 1
            else:
                buckets["gte80"] += 1

        daily: Dict[str, List[int]] = {}
        for r in records:
            if r.overall_score is None or not r.create_time:
                continue
            day = time.strftime("%Y-%m-%d", time.localtime(r.create_time / 1000))
            daily.setdefault(day, []).append(r.overall_score)
        trend = [
            {"date": day, "avg_score": round(sum(v) / len(v)), "count": len(v)}
            for day, v in sorted(daily.items())
        ]

        return {
            "total": len(records),
            "avg_overall_score": round(sum(scores) / len(scores)) if scores else None,
            "review_pass_rate": round(sum(1 for v in review if v) / len(review), 4) if review else None,
            "tests_pass_rate": round(sum(1 for v in tests if v) / len(tests), 4) if tests else None,
            "avg_retry_count": round(sum(retries) / len(retries), 2) if retries else None,
            "score_buckets": buckets,
            "daily_trend": trend,
        }

    async def delete_pipeline(self, pipeline_id: str, tenant_id: int = 0) -> None:
        """软删除流水线"""
        async with async_session_maker() as session:
            query = update(DevPipeline).where(
                DevPipeline.pipeline_id == pipeline_id,
                DevPipeline.is_deleted == 0,
            )
            if tenant_id:
                query = query.where(DevPipeline.tenant_id == tenant_id)
            query = query.values(is_deleted=1, update_time=int(time.time() * 1000))
            result = await session.execute(query)
            if result.rowcount == 0:
                raise ValueError("流水线不存在")
            await session.commit()

    async def rollback(self, pipeline_id: str, target_stage: str = None, feedback: str = "") -> Dict[str, Any]:
        async with async_session_maker() as session:
            pipe = await self._load_pipeline(session, pipeline_id)
            pipe_config = json.loads(pipe.skill_config or "{}")
            stage_keys = _stage_keys_for_mode(pipe_config.get("pipeline_mode", "full"))
            try:
                current_idx = stage_keys.index(pipe.current_stage)
            except ValueError:
                current_idx = 0

            if target_stage:
                if target_stage not in stage_keys:
                    raise ValueError("目标阶段无效")
                target_idx = stage_keys.index(target_stage)
            else:
                target_idx = current_idx - 1

            if target_idx < 0:
                raise ValueError("已经是第一阶段")
            if target_idx > current_idx:
                raise ValueError("不能回退到当前阶段之后")

            target = stage_keys[target_idx]
            stages = self._parse_stages(pipe)

            # 回退到目标阶段后，目标阶段和后续阶段都要重新跑，避免旧产物污染。
            for stage in stage_keys[target_idx:]:
                if stage not in stages:
                    continue
                stages[stage]["status"] = "pending"
                stages[stage]["output"] = ""
                stages[stage]["structured_output"] = {}
                stages[stage]["preview_html"] = ""
                stages[stage]["code_files"] = {}
                stages[stage]["error"] = ""
                stages[stage]["completed_at"] = None
                stages[stage]["revision_feedback"] = feedback.strip() if stage == target and feedback else ""

            pipe.current_stage = target
            pipe.retry_count = 0
            pipe.update_time = int(time.time() * 1000)
            pipe.status = PipelineStatus.PENDING.value
            pipe.stages_data = json.dumps(stages, ensure_ascii=False)
            await session.commit()

            return {
                "pipeline_id": pipeline_id,
                "rolled_back_to": target,
                "status": pipe.status,
                "need_confirm": False,
                "message": f"已回退到 {STAGE_NAMES.get(target, target)}，可按修改意见重新执行",
            }


pipeline_manager = DevPipelineManager()
