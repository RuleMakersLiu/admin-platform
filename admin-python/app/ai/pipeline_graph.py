"""基于 LangGraph 的开发流水线引擎

特性:
  - StateGraph 编排 8 个阶段
  - 并行 BE + FE 开发
  - 条件边：Code Review FAIL → 回退修复，Test FAIL → 回退修复
  - Human-in-the-loop：需求/UI 预览使用 interrupt() 等待确认
  - LLM 调用自动重试（指数退避）
  - AgentMemory 记忆集成
  - DevPipeline 数据库持久化
"""
import asyncio
import json
import logging
import operator
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command, Send, RetryPolicy

from app.ai.agents import AgentService, AgentType
from app.models.agent_models import DevPipeline
from app.services.memory_service import MemoryService, MemoryType
from app.services.memory_manager import memory_manager
from app.services.builtin_memory_provider import BuiltinMemoryProvider
from app.core.database import async_session_maker

# Initialize memory manager with built-in provider
_builtin_memory = BuiltinMemoryProvider()
_builtin_memory.initialize(session_id="", tenant_id=1)
memory_manager.add_provider(_builtin_memory)

logger = logging.getLogger(__name__)

MAX_FIX_ITERATIONS = 3
MAX_LLM_RETRIES = 3
RETRY_BASE_DELAY = 2

STAGE_DEFINITIONS = [
    {"key": "requirement",  "name": "需求分析",   "agent": "PM",  "need_confirm": True},
    {"key": "ui_preview",   "name": "UI预览",     "agent": "FE",  "need_confirm": True},
    {"key": "development",  "name": "代码生成",   "agent": "BE",  "need_confirm": False},
    {"key": "code_review",  "name": "代码审查",   "agent": "QA",  "need_confirm": False},
    {"key": "testing",      "name": "自动化测试", "agent": "QA",  "need_confirm": False},
    {"key": "commit",       "name": "代码提交",   "agent": "PJM", "need_confirm": False},
    {"key": "deploy",       "name": "部署发布",   "agent": "PJM", "need_confirm": False},
    {"key": "report",       "name": "总结报告",   "agent": "RPT", "need_confirm": False},
]


# ==================== State 定义 ====================

class PipelineState(TypedDict, total=False):
    """流水线状态（LangGraph 共享状态）"""
    # 元信息
    pipeline_id: str
    project_id: str
    user_request: str
    tenant_id: int
    current_stage: str
    status: str
    retry_count: int
    fix_feedback: str

    # 阶段输出（每个阶段写入自己的 key）
    stages: Dict[str, Any]

    # 并行开发结果
    be_output: str
    fe_output: str

    # 条件分支标志
    review_passed: bool
    tests_passed: bool

    # 消息累积
    messages: Annotated[list, operator.add]

    # 中断控制
    confirmed: Optional[bool]
    feedback: str


def _init_stages() -> Dict[str, Any]:
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
    }


# ==================== LLM 重试 ====================

def _is_retriable(e: Exception) -> bool:
    s = str(e).lower()
    return any(kw in s for kw in ["timeout", "rate limit", "429", "503", "502", "connection"])


async def _call_agent(agent_service: AgentService, session_id: str,
                       message: str, agent_type: str) -> str:
    last_error = None
    for attempt in range(MAX_LLM_RETRIES):
        try:
            result = await agent_service.chat(session_id=session_id, message=message, agent_type=agent_type)
            return result["reply"]
        except Exception as e:
            last_error = e
            if not _is_retriable(e):
                raise
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(f"Agent retry {attempt + 1}/{MAX_LLM_RETRIES}: {e}, waiting {delay}s")
            await asyncio.sleep(delay)
    raise last_error


# ==================== 记忆 ====================

async def _save_memory(pipeline_id: str, stage_key: str, agent_type: str,
                        content: str, tenant_id: int):
    try:
        async with async_session_maker() as session:
            await MemoryService.save_memory(
                db=session, session_id=pipeline_id, agent_type=agent_type,
                content=f"[{stage_key}] {content[:500]}", tenant_id=tenant_id,
                memory_type=MemoryType.LONG_TERM,
                key_info=f"pipeline:{pipeline_id}:{stage_key}",
                importance=80 if "FAIL" in content else 60,
            )
            await session.commit()
    except Exception as e:
        logger.warning(f"Memory save failed: {e}")


async def _get_memories(pipeline_id: str, tenant_id: int) -> str:
    try:
        async with async_session_maker() as session:
            memories = await MemoryService.get_memories(
                db=session, session_id=pipeline_id, limit=5,
                memory_types=[MemoryType.LONG_TERM, MemoryType.SEMANTIC],
                min_importance=60,
            )
            await session.commit()
        return "\n".join([f"- [{m.agent_type}] {m.content}" for m in memories]) if memories else ""
    except Exception:
        return ""


# ==================== Prompt 构建 ====================

def _build_prompt(stage_key: str, state: PipelineState) -> str:
    prev = state.get("stages", {})
    fix = state.get("fix_feedback", "")
    memories = state.get("messages", [])
    memories_text = "\n".join([m for m in memories if isinstance(m, str) and m.startswith("-")]) if memories else ""

    parts = []

    if memories_text:
        parts.append(f"## 历史经验\n{memories_text}\n请参考以上经验，避免重复犯错。\n")

    if fix:
        parts.append(f"## 修复要求\n上一次执行发现问题，请根据以下反馈修复：\n{fix}\n")

    base = {
        "requirement": f"""请根据以下用户需求，生成完整的需求文档(PRD)。

用户需求:
{state.get('user_request', '')}

请输出 Markdown 格式的 PRD 文档，包含:
1. 项目概述  2. 功能需求列表（P0/P1/P2/P3）  3. 用户故事  4. 非功能需求  5. 验收标准

用 ```prg 开始和 ``` 结束包裹整个 PRD 文档。""",

        "ui_preview": f"""基于以下需求文档，设计并生成 UI 界面预览。

需求文档:
{prev.get('requirement', {}).get('output', '未提供')}

请输出完整的 HTML 页面（用 ```html 包裹），使用 Ant Design CDN 样式，内联 CSS，包含交互元素和响应式布局。""",

        "development_be": f"""基于以下需求和 UI 设计，生成后端代码。

需求文档:
{prev.get('requirement', {}).get('output', '未提供')}

UI 设计:
{prev.get('ui_preview', {}).get('output', '未提供')}

请输出:
1. 后端 API 代码（用 ```python 或 ```go 包裹）
2. 数据库建表 SQL（用 ```sql 包裹）
3. API 接口文档（用 ```json 包裹 OpenAPI 格式）

每个代码块前用 `### 文件: 路径/文件名` 标注。""",

        "development_fe": f"""基于以下需求和 UI 设计，生成前端代码。

需求文档:
{prev.get('requirement', {}).get('output', '未提供')}

UI 设计:
{prev.get('ui_preview', {}).get('output', '未提供')}

请输出:
1. 前端页面代码（用 ```tsx 包裹）
2. 组件代码

每个代码块前用 `### 文件: 路径/文件名` 标注。""",

        "code_review": f"""请审查以下代码，检查质量、安全性和最佳实践。

后端代码:
{state.get('be_output', prev.get('development', {}).get('output', '未提供'))}

前端代码:
{state.get('fe_output', '')}

请输出:
1. 代码评分 (A/B/C/D/F)
2. 问题列表（含严重程度: critical/major/minor）
3. 改进建议（每个问题给出具体修复方案）
4. 是否通过审查 (PASS/FAIL)

critical/major 问题标记为 FAIL 并给出详细修复指导。""",

        "testing": f"""基于以下需求和代码，设计测试用例并验证。

需求:
{prev.get('requirement', {}).get('output', '未提供')[:500]}

代码审查:
{prev.get('code_review', {}).get('output', '未提供')[:500]}

请输出:
1. 测试用例列表  2. 测试结果（通过/失败）  3. 覆盖率评估  4. Bug 列表（标注严重程度）""",

        "commit": f"""请整理代码，生成提交信息。

代码审查:
{prev.get('code_review', {}).get('output', '未提供')[:300]}

测试结果:
{prev.get('testing', {}).get('output', '未提供')[:300]}

请输出:
1. Git commit message（Conventional Commits 格式）  2. 变更文件列表  3. 打包说明""",

        "deploy": f"""请生成部署方案。

提交信息:
{prev.get('commit', {}).get('output', '未提供')[:300]}

请输出: 1. 部署环境配置  2. 部署步骤  3. 健康检查方案  4. 回滚方案""",

        "report": f"""请生成项目总结报告。

需求: {prev.get('requirement', {}).get('output', '未提供')[:300]}
代码审查: {prev.get('code_review', {}).get('output', '未提供')[:300]}
测试: {prev.get('testing', {}).get('output', '未提供')[:300]}

请输出: 1. 项目概况  2. 完成功能  3. 技术栈  4. 已知问题  5. 后续计划""",
    }

    parts.append(base.get(stage_key, f"请处理 {stage_key} 阶段的任务。"))
    return "\n".join(parts)


# ==================== 输出解析 ====================

def _parse_output(stage_key: str, raw: str) -> Dict[str, Any]:
    result = {"output": raw}

    if stage_key == "ui_preview":
        html_blocks = []
        for part in raw.split("```html")[1:]:
            end = part.find("```")
            if end > 0:
                html_blocks.append(part[:end].strip())
        if html_blocks:
            result["preview_html"] = html_blocks[0]

    if stage_key in ("development_be", "development_fe", "development"):
        files = {}
        cur_file = None
        cur_content = []
        in_code = False
        for line in raw.split("\n"):
            if line.startswith("### 文件:"):
                if cur_file and cur_content:
                    files[cur_file] = "\n".join(cur_content)
                cur_file = line.replace("### 文件:", "").strip()
                cur_content = []
            elif line.startswith("```") and not in_code:
                in_code = True
            elif line.startswith("```") and in_code:
                in_code = False
            elif in_code and cur_file:
                cur_content.append(line)
        if cur_file and cur_content:
            files[cur_file] = "\n".join(cur_content)
        if files:
            result["code_files"] = files

    if stage_key == "requirement":
        for part in raw.split("```prg")[1:]:
            end = part.find("```")
            if end > 0:
                result["prd_document"] = part[:end].strip()

    if stage_key == "code_review":
        result["review_passed"] = "PASS" in raw and "FAIL" not in raw
        suggestions = [l.strip() for l in raw.split("\n")
                       if l.strip().startswith(("- ", "* ", "改进", "建议", "修复", "问题"))][:10]
        if suggestions:
            result["fix_suggestions"] = "\n".join(suggestions)

    if stage_key == "testing":
        has_fail = "失败" in raw or "FAIL" in raw or "critical" in raw.lower()
        result["tests_passed"] = not has_fail
        if has_fail:
            bugs = [l.strip() for l in raw.split("\n")
                    if any(kw in l.lower() for kw in ["bug", "失败", "fail", "error", "critical", "major"])][:10]
            result["bug_details"] = "\n".join(bugs) if bugs else raw[:500]

    return result


# ==================== Node 函数 ====================

_agent_service = AgentService()


def _update_stage(stages: Dict, key: str, **kwargs) -> Dict:
    stages = dict(stages)
    stages[key] = {**stages.get(key, {}), **kwargs}
    return stages


async def _run_stage(state: PipelineState, stage_key: str, agent_type: str) -> Dict:
    """通用阶段执行函数"""
    pipeline_id = state["pipeline_id"]
    session_id = f"{pipeline_id}_{stage_key}_{state.get('retry_count', 0)}"
    prompt = _build_prompt(stage_key, state)

    raw = await _call_agent(_agent_service, session_id, prompt, agent_type)
    parsed = _parse_output(stage_key, raw)

    now = datetime.now().isoformat()
    stages = _update_stage(
        state.get("stages", _init_stages()), stage_key,
        status="completed", output=raw, structured_output=parsed,
        preview_html=parsed.get("preview_html", ""),
        code_files=parsed.get("code_files", {}),
        completed_at=now, started_at=now,
    )

    await _save_memory(pipeline_id, stage_key, agent_type, raw[:300], state.get("tenant_id", 0))

    return {
        "current_stage": stage_key,
        "stages": stages,
        "messages": [f"[{stage_key}] completed"],
    }


def requirement_node(state: PipelineState) -> Dict:
    """需求分析节点（使用 interrupt 等待确认）"""
    pipeline_id = state["pipeline_id"]

    # 检查是否已有输出（从 checkpoint 恢复）
    stages = state.get("stages", _init_stages())
    req_stage = stages.get("requirement", {})
    if req_stage.get("status") == "completed" and state.get("confirmed") is None:
        # 首次完成，等待用户确认
        decision = interrupt({
            "stage": "requirement",
            "message": "需求文档已生成，请确认",
            "output": req_stage.get("output", ""),
            "need_confirm": True,
        })
        return {"confirmed": decision.get("confirmed", True), "feedback": decision.get("feedback", "")}

    # 如果已确认，直接推进
    if state.get("confirmed") is True:
        return {"current_stage": "requirement", "status": "confirmed"}

    # 否则执行 Agent
    import asyncio
    raw = asyncio.get_event_loop().run_until_complete(
        _call_agent(_agent_service, f"{pipeline_id}_requirement", _build_prompt("requirement", state), AgentType.PM)
    )
    parsed = _parse_output("requirement", raw)
    stages = _update_stage(stages, "requirement",
                           status="completed", output=raw, structured_output=parsed, completed_at=datetime.now().isoformat())

    # 等待用户确认
    decision = interrupt({
        "stage": "requirement",
        "message": "需求文档已生成，请确认",
        "output": raw,
        "need_confirm": True,
    })

    return {
        "stages": stages,
        "confirmed": decision.get("confirmed", True),
        "feedback": decision.get("feedback", ""),
        "current_stage": "requirement",
    }


# 由于 LangGraph nodes 不支持直接 async（部分版本），用 sync wrapper
def _make_sync_node(stage_key: str, agent_type: str, check_interrupt: bool = False):
    """创建同步 node 函数"""
    def node(state: PipelineState) -> Dict:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_run_stage(state, stage_key, agent_type))
        finally:
            loop.close()

        if check_interrupt:
            decision = interrupt({
                "stage": stage_key,
                "message": f"{stage_key} 已完成，请确认",
                "output": result.get("stages", {}).get(stage_key, {}).get("output", ""),
                "need_confirm": True,
            })
            result["confirmed"] = decision.get("confirmed", True)
            result["feedback"] = decision.get("feedback", "")

        return result
    return node


# ==================== 条件边 ====================

def after_requirement(state: PipelineState) -> str:
    if state.get("confirmed") is False:
        return END
    return "ui_preview"


def after_ui_preview(state: PipelineState) -> list:
    """UI 预览确认后，并行启动 BE 和 FE 开发"""
    if state.get("confirmed") is False:
        return [END]
    return [Send("development_be", state), Send("development_fe", state)]


def after_code_review(state: PipelineState) -> str:
    stages = state.get("stages", {})
    review = stages.get("code_review", {})
    structured = review.get("structured_output", {})

    if not structured.get("review_passed", True):
        retry = state.get("retry_count", 0)
        if retry < MAX_FIX_ITERATIONS:
            return "start_dev"
        return END
    return "testing"


def after_testing(state: PipelineState) -> str:
    stages = state.get("stages", {})
    testing = stages.get("testing", {})
    structured = testing.get("structured_output", {})

    if not structured.get("tests_passed", True):
        retry = state.get("retry_count", 0)
        if retry < MAX_FIX_ITERATIONS:
            return "start_dev"
        return END
    return "commit"


# ==================== 构建图 ====================

def build_pipeline_graph():
    """构建 LangGraph 流水线图"""
    builder = StateGraph(PipelineState)

    # 添加节点
    builder.add_node("requirement", _make_sync_node("requirement", "PM", check_interrupt=True))
    builder.add_node("ui_preview", _make_sync_node("ui_preview", "FE", check_interrupt=True))

    # 并行开发
    def start_dev(state: PipelineState) -> Dict:
        return {
            "retry_count": state.get("retry_count", 0) + 1,
            "fix_feedback": state.get("stages", {}).get("code_review", {}).get("structured_output", {}).get("fix_suggestions", "")
            or state.get("stages", {}).get("testing", {}).get("structured_output", {}).get("bug_details", ""),
            "be_output": "",
            "fe_output": "",
            "current_stage": "development",
        }

    builder.add_node("start_dev", start_dev)
    builder.add_node("development_be", _make_sync_node("development_be", "BE"))
    builder.add_node("development_fe", _make_sync_node("development_fe", "FE"))

    def merge_dev(state: PipelineState) -> Dict:
        be = state.get("be_output", "")
        fe = state.get("fe_output", "")
        combined = f"# 后端代码\n{be}\n\n# 前端代码\n{fe}"
        stages = _update_stage(
            state.get("stages", _init_stages()), "development",
            status="completed", output=combined,
            structured_output={"output": combined, "code_files": {}},
            completed_at=datetime.now().isoformat(),
        )
        return {"stages": stages, "current_stage": "development"}

    builder.add_node("merge_dev", merge_dev)

    # 后续阶段
    builder.add_node("code_review", _make_sync_node("code_review", "QA"))
    builder.add_node("testing", _make_sync_node("testing", "QA"))
    builder.add_node("commit", _make_sync_node("commit", "PJM"))
    builder.add_node("deploy", _make_sync_node("deploy", "PJM"))
    builder.add_node("report", _make_sync_node("report", "RPT"))

    # 添加边
    builder.add_edge(START, "requirement")
    builder.add_conditional_edges("requirement", after_requirement)
    builder.add_conditional_edges("ui_preview", after_ui_preview)
    builder.add_edge("development_be", "merge_dev")
    builder.add_edge("development_fe", "merge_dev")
    builder.add_conditional_edges("start_dev", lambda s: [Send("development_be", s), Send("development_fe", s)])
    builder.add_edge("merge_dev", "code_review")
    builder.add_conditional_edges("code_review", after_code_review)
    builder.add_conditional_edges("testing", after_testing)
    builder.add_edge("commit", "deploy")
    builder.add_edge("deploy", "report")
    builder.add_edge("report", END)

    return builder


# ==================== 持久化检查点 ====================

class PipelineCheckpointer:
    """将 LangGraph 状态同步到 DevPipeline 数据库模型"""

    @staticmethod
    async def save_to_db(state: PipelineState):
        async with async_session_maker() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(DevPipeline).where(DevPipeline.pipeline_id == state["pipeline_id"])
            )
            pipe = result.scalar_one_or_none()
            if pipe:
                pipe.status = state.get("status", "running")
                pipe.current_stage = state.get("current_stage", "")
                pipe.stages_data = json.dumps(state.get("stages", {}), ensure_ascii=False)
                pipe.retry_count = state.get("retry_count", 0)
                pipe.update_time = int(time.time() * 1000)
                await session.commit()

    @staticmethod
    async def load_from_db(pipeline_id: str) -> Optional[Dict]:
        async with async_session_maker() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(DevPipeline).where(
                    DevPipeline.pipeline_id == pipeline_id,
                    DevPipeline.is_deleted == 0,
                )
            )
            pipe = result.scalar_one_or_none()
            if not pipe:
                return None
            return {
                "pipeline_id": pipe.pipeline_id,
                "project_id": pipe.project_id or "",
                "user_request": pipe.user_request or "",
                "tenant_id": pipe.tenant_id,
                "current_stage": pipe.current_stage,
                "status": pipe.status,
                "retry_count": pipe.retry_count or 0,
                "stages": json.loads(pipe.stages_data) if pipe.stages_data else _init_stages(),
            }


# ==================== 流水线管理器（对外接口） ====================

class DevPipelineManager:
    """流水线管理器（LangGraph 驱动）"""

    def __init__(self):
        self.graph = build_pipeline_graph().compile(
            checkpointer=MemorySaver(),
        )

    async def create_pipeline(self, project_id: str = "", user_request: str = "",
                              tenant_id: int = 0, creator_id: int = 0) -> str:
        pipeline_id = f"pipe_{uuid.uuid4().hex[:12]}"
        now = int(time.time() * 1000)

        db_obj = DevPipeline(
            pipeline_id=pipeline_id, project_id=project_id,
            user_request=user_request, status="pending",
            current_stage="requirement",
            stages_data=json.dumps(_init_stages(), ensure_ascii=False),
            retry_count=0, tenant_id=tenant_id, creator_id=creator_id,
            create_time=now, update_time=now,
        )
        async with async_session_maker() as session:
            session.add(db_obj)
            await session.commit()

        return pipeline_id

    async def execute_stage(self, pipeline_id: str, user_input: str = "") -> Dict[str, Any]:
        """执行流水线（运行 LangGraph）"""
        state = await PipelineCheckpointer.load_from_db(pipeline_id)
        if not state:
            raise ValueError(f"流水线不存在: {pipeline_id}")

        # 补充运行时状态
        state.update({
            "be_output": "", "fe_output": "",
            "review_passed": False, "tests_passed": False,
            "messages": [], "confirmed": None, "feedback": "",
            "fix_feedback": state.get("fix_feedback", ""),
        })
        if user_input:
            state["user_request"] = user_input

        config = {"configurable": {"thread_id": pipeline_id}}

        try:
            result = await self.graph.ainvoke(state, config)
            await PipelineCheckpointer.save_to_db(result)
            return self._format_result(result)
        except Exception as e:
            logger.error(f"Pipeline {pipeline_id} failed: {e}")
            # Persist failure status to DB
            state["status"] = "failed"
            stages = state.get("stages", {})
            current = state.get("current_stage", "")
            if current and current in stages:
                stages[current]["status"] = "failed"
                stages[current]["error"] = str(e)
            state["stages"] = stages
            await PipelineCheckpointer.save_to_db(state)
            return {
                "pipeline_id": pipeline_id,
                "status": "failed",
                "error": str(e),
            }

    async def confirm_stage(self, pipeline_id: str, confirmed: bool,
                            feedback: str = "") -> Dict[str, Any]:
        """用户确认当前阶段（通过 Command resume）"""
        config = {"configurable": {"thread_id": pipeline_id}}

        try:
            result = await self.graph.ainvoke(
                Command(resume={"confirmed": confirmed, "feedback": feedback}),
                config,
            )
            await PipelineCheckpointer.save_to_db(result)
            return self._format_result(result)
        except Exception as e:
            logger.error(f"Pipeline {pipeline_id} confirm failed: {e}")
            # Persist failure status to DB
            state = await PipelineCheckpointer.load_from_db(pipeline_id) or {}
            state["status"] = "failed"
            stages = state.get("stages", {})
            current = state.get("current_stage", "")
            if current and current in stages:
                stages[current]["status"] = "failed"
                stages[current]["error"] = str(e)
            state["stages"] = stages
            await PipelineCheckpointer.save_to_db(state)
            return {"pipeline_id": pipeline_id, "status": "failed", "error": str(e)}

    def _format_result(self, state: PipelineState) -> Dict[str, Any]:
        stages = state.get("stages", {})
        current = state.get("current_stage", "")
        stage_data = stages.get(current, {})

        return {
            "pipeline_id": state.get("pipeline_id", ""),
            "stage": current,
            "status": state.get("status", "running"),
            "output": stage_data.get("output", ""),
            "preview_html": stage_data.get("preview_html", ""),
            "structured_output": stage_data.get("structured_output", {}),
            "code_files": stage_data.get("code_files", {}),
            "retry_count": state.get("retry_count", 0),
            "need_confirm": state.get("status") == "waiting_confirm",
        }

    async def get_pipeline_status(self, pipeline_id: str) -> Dict[str, Any]:
        state = await PipelineCheckpointer.load_from_db(pipeline_id)
        if not state:
            raise ValueError(f"流水线不存在: {pipeline_id}")
        return {
            "pipeline_id": state["pipeline_id"],
            "project_id": state.get("project_id", ""),
            "user_request": state.get("user_request", ""),
            "status": state.get("status", ""),
            "current_stage": state.get("current_stage", ""),
            "stages": state.get("stages", {}),
            "retry_count": state.get("retry_count", 0),
            "created_at": str(state.get("created_at", "")),
            "updated_at": str(state.get("updated_at", "")),
        }

    async def get_preview(self, pipeline_id: str) -> Dict[str, Any]:
        state = await PipelineCheckpointer.load_from_db(pipeline_id)
        if not state:
            raise ValueError(f"流水线不存在: {pipeline_id}")
        ui_stage = state.get("stages", {}).get("ui_preview", {})
        return {
            "pipeline_id": pipeline_id,
            "preview_html": ui_stage.get("preview_html", ""),
            "output": ui_stage.get("output", ""),
        }

    async def get_stage_output(self, pipeline_id: str, stage: str = "") -> Dict[str, Any]:
        state = await PipelineCheckpointer.load_from_db(pipeline_id)
        if not state:
            raise ValueError(f"流水线不存在: {pipeline_id}")
        target = stage or state.get("current_stage", "")
        stage_data = state.get("stages", {}).get(target, {})
        return {
            "pipeline_id": pipeline_id, "stage": target,
            "output": stage_data.get("output", ""),
            "structured_output": stage_data.get("structured_output", {}),
            "preview_html": stage_data.get("preview_html", ""),
            "code_files": stage_data.get("code_files", {}),
        }

    async def list_pipelines(self, tenant_id: int = 0) -> List[Dict[str, Any]]:
        from sqlalchemy import select
        async with async_session_maker() as session:
            query = select(DevPipeline).where(DevPipeline.is_deleted == 0)
            if tenant_id:
                query = query.where(DevPipeline.tenant_id == tenant_id)
            query = query.order_by(DevPipeline.create_time.desc())
            result = await session.execute(query)
            return [
                {
                    "pipeline_id": p.pipeline_id,
                    "project_id": p.project_id or "",
                    "status": p.status,
                    "current_stage": p.current_stage,
                    "retry_count": p.retry_count or 0,
                    "created_at": str(p.create_time),
                }
                for p in result.scalars().all()
            ]

    async def rollback(self, pipeline_id: str) -> Dict[str, Any]:
        stage_keys = [s["key"] for s in STAGE_DEFINITIONS]
        async with async_session_maker() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(DevPipeline).where(DevPipeline.pipeline_id == pipeline_id)
            )
            pipe = result.scalar_one_or_none()
            if not pipe:
                return {"error": "流水线不存在"}

            idx = stage_keys.index(pipe.current_stage) if pipe.current_stage in stage_keys else -1
            if idx <= 0:
                return {"error": "已经是第一阶段"}

            prev = stage_keys[idx - 1]
            stages = json.loads(pipe.stages_data) if pipe.stages_data else _init_stages()
            stages[prev]["status"] = "pending"
            pipe.current_stage = prev
            pipe.status = "pending"
            pipe.retry_count = 0
            pipe.stages_data = json.dumps(stages, ensure_ascii=False)
            pipe.update_time = int(time.time() * 1000)
            await session.commit()

        return {"pipeline_id": pipeline_id, "rolled_back_to": prev, "status": "pending"}


pipeline_manager = DevPipelineManager()
