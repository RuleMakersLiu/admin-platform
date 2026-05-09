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
import time
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents import AgentService
from app.ai.pipeline_skills import ensure_workspace, get_workspace_path
from app.ai.skills import skill_registry
from app.models.agent_models import DevPipeline
from app.services.memory_service import MemoryService, MemoryType
from app.core.database import async_session_maker

logger = logging.getLogger(__name__)

MAX_FIX_ITERATIONS = 3
MAX_LLM_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_CONFIRM = "waiting_confirm"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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

STAGE_KEYS = [s["key"] for s in STAGE_DEFINITIONS]


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


# ==================== 默认 Prompt 模板 ====================
# 可通过 API /flow/prompts/defaults 读取，支持项目级自定义覆盖

DEFAULT_STAGE_PROMPTS: Dict[str, str] = {
    "requirement": """请根据以下用户需求，生成一份完整的需求文档(PRD)。

用户需求:
{{user_request}}

请直接输出 Markdown 格式的 PRD 文档（不要用代码块包裹），包含:
1. 项目概述
2. 功能需求列表（含优先级 P0/P1/P2/P3）
3. 用户故事
4. 非功能需求
5. 验收标准""",

    "ui_preview": """根据需求文档，生成一个 Vue 2 + antd-vue 1.x 的管理后台页面预览。

## 需求文档
{{requirement_output}}

## 输出格式
只输出一个 ```html 代码块，不要在代码块前后写任何文字说明。

## 技术要求
1. 使用 Vue 2 + antd-vue 1.x CDN：
   - `<script src="https://cdn.jsdelivr.net/npm/vue@2.7.16/dist/vue.min.js"></script>`
   - `<script src="https://cdn.jsdelivr.net/npm/moment@2.29.4/min/moment.min.js"></script>`
   - `<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/ant-design-vue@1.7.8/dist/antd.min.css">`
   - `<script src="https://cdn.jsdelivr.net/npm/ant-design-vue@1.7.8/dist/antd.min.js"></script>`
2. 使用 antd-vue 组件：a-layout(a-layout-sider + a-layout-header + a-layout-content)、a-table、a-form、a-modal、a-card、a-button、a-input、a-select、a-tag、a-pagination、a-dropdown、a-menu、a-badge、a-avatar、a-icon
3. Vue 实例通过 `new Vue({el: '#app', ...})` 挂载，使用 `antd` 全局注册
4. 包含完整的 CRUD 交互（列表、搜索、新增弹窗、编辑、删除确认）
5. 表格至少 5 条 mock 数据
6. 页面精致美观，有合理间距、阴影、圆角
7. 所有文字使用中文""",

    "development": """基于以下需求文档和 UI 设计，生成完整的前后端代码。

需求文档:
{{requirement_output}}

UI 设计参考:
{{ui_preview_output}}

## 系统架构（PHP 转发到 Java）

本系统采用 PHP + Java 双层架构：
- PHP (Laravel 8 + Swoole) 对外提供 API，负责认证、参数校验、数据转发
- Java (Spring Boot 1.4.3 + Dubbo 3.x) 提供核心业务服务
- PHP 通过 Curl 调用 Java 的 HTTP 接口（非 Dubbo 直连），使用 app.java_api_url 配置的服务地址
- 请求/响应格式统一：{ "message": { "code": 0, "message": "success" }, "data": {...} }

### PHP 层 (Laravel 8 + Swoole/LaravelS)
- 版本：PHP 7.4+, Laravel 8.83, Swoole/LaravelS
- 分层：Controller → Service → DAO (Http\Models) → Model
- HTTP 客户端：使用 Ixudra/Curl 封装，通过 app(Http::class)->postHttp() / getHttp() 调用 Java
- 签名机制：appkey + timestamp + signcode (MD5)
- 多租户：tenant_id 字段隔离
- 控制器路径：app/Http/Controllers/Api/{Feature}Controller.php
- 服务层路径：app/Http/Services/{Feature}Service.php
- DAO层路径：app/Http/Dao/{Feature}Dao.php (直接操作数据库)
- 模型路径：app/Http/Models/{Feature}.php

### Java 层 (Spring Boot 1.4.3 + Dubbo 3.x)
- 版本：Java 1.8, Spring Boot 1.4.3.RELEASE, Dubbo 3.2.16
- 模块结构：
  - wealth-glsw-core: 接口定义 (model/dto/service/枚举)
  - wealth-glsw-service: Dubbo 服务实现
  - wealth-admin-home: Web 层 (Controller + DubboReference 调用)
- 控制器：@RestController + @RequestMapping + @DubboReference 注入服务
- 返回值：统一使用 ApiResult 封装
- ORM：无 MyBatis，使用 Dubbo 服务接口操作数据
- 包结构：com.gemantic.wealth.{模块}.controller/service/model/dto

## 前端技术栈
- Vue 2.6.10 + antd-vue 1.7.2 (vue-antd-pro 脚手架)
- 路由：vue-router 3.x，配置在 src/router/
- 状态管理：Vuex 3.x + vue-ls 持久化
- 网络请求：axios，封装在 src/utils/request.js，baseURL 通过环境变量配置
- 列表页使用 s-table 组件（封装了 a-table + 分页 + 加载）
- 表单使用 a-form (layout="inline" 搜索, 垂直布局编辑)
- 弹窗使用 a-modal
- 权限指令：v-action:xxx
- 样式：Less 预处理器，scoped 样式

请输出以下内容:
1. PHP Controller（用 ```php 包裹）
2. PHP Service（用 ```php 包裹）
3. PHP DAO（如果需要直接数据库操作）（用 ```php 包裹）
4. Java Controller（用 ```java 包裹）
5. Java Service 接口 + 实现（用 ```java 包裹）
6. Java Model/DTO（用 ```java 包裹）
7. 前端列表页 .vue（用 ```vue 包裹）
8. 前端表单页 .vue（用 ```vue 包裹）
9. 前端 API 服务（用 ```js 包裹）
10. 数据库建表 SQL（用 ```sql 包裹）

每个代码块前用 `### 文件: 路径/文件名` 标注。""",

    "code_review": """请审查以下代码，检查代码质量、安全性和最佳实践。

代码:
{{development_output}}

请输出:
1. 代码评分 (A/B/C/D/F)
2. 发现的问题列表（含严重程度: critical/major/minor）
3. 改进建议（每个问题给出具体的修复方案）
4. 是否通过审查 (PASS/FAIL)

如果发现 critical 或 major 问题，标记为 FAIL 并给出详细修复指导。""",

    "testing": """基于以下需求和代码，设计测试用例并验证。

需求文档:
{{requirement_output}}

代码:
{{development_output}}

代码审查结果:
{{code_review_output}}

请输出:
1. 测试用例列表
2. 测试结果（通过/失败）
3. 覆盖率评估
4. 发现的 Bug 列表（标注严重程度: critical/major/minor）""",

    "commit": """请整理以下代码，生成提交信息并准备提交。

代码:
{{development_output}}

测试结果:
{{testing_output}}

请输出:
1. Git commit message（Conventional Commits 格式）
2. 变更文件列表
3. 代码打包说明""",

    "deploy": """请根据以下信息，生成部署方案。

提交信息:
{{commit_output}}

请输出:
1. 部署环境配置
2. 部署步骤
3. 健康检查方案
4. 回滚方案""",

    "report": """请生成整个项目的总结报告。

需求:
{{requirement_output_short}}

代码审查:
{{code_review_output_short}}

测试:
{{testing_output_short}}

请输出:
1. 项目概况
2. 完成功能列表
3. 技术栈总结
4. 已知问题
5. 后续计划""",
}


def _render_prompt_template(template: str, context: Dict[str, Any]) -> str:
    """渲染 prompt 模板，替换变量占位符"""
    user_request = context.get("user_request", "")
    prev_outputs = context.get("stage_outputs", {})

    replacements = {
        "{{user_request}}": user_request[:2000],
        "{{requirement_output}}": prev_outputs.get("requirement", {}).get("output", "未提供")[:3000],
        "{{ui_preview_output}}": prev_outputs.get("ui_preview", {}).get("output", "未提供")[:3000],
        "{{development_output}}": prev_outputs.get("development", {}).get("output", "未提供")[:3000],
        "{{code_review_output}}": prev_outputs.get("code_review", {}).get("output", "未提供")[:2000],
        "{{testing_output}}": prev_outputs.get("testing", {}).get("output", "未提供")[:2000],
        "{{commit_output}}": prev_outputs.get("commit", {}).get("output", "未提供")[:1000],
        # 截断版本（report 阶段用）
        "{{requirement_output_short}}": (prev_outputs.get("requirement", {}).get("output", "未提供") or "")[:500],
        "{{code_review_output_short}}": (prev_outputs.get("code_review", {}).get("output", "未提供") or "")[:500],
        "{{testing_output_short}}": (prev_outputs.get("testing", {}).get("output", "未提供") or "")[:500],
    }

    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)
    return result


# ==================== Prompt 构建 ====================

def _build_pipeline_prompt(stage_key: str, context: Dict[str, Any],
                            custom_prompts: Dict[str, str] = None) -> str:
    """根据阶段构建 Agent 的 prompt，注入记忆和修复反馈。支持自定义 prompt 覆盖。"""
    fix_feedback = context.get("fix_feedback", "")
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
    return memory_section + fix_section + prompt


# ==================== 输出解析 ====================

def _parse_agent_output(stage_key: str, raw_output: str) -> Dict[str, Any]:
    """解析 Agent 输出，提取结构化数据"""
    result = {"output": raw_output}

    if stage_key == "ui_preview":
        html_blocks = []
        import re
        # 匹配 ```html 或 ```HTML 后面的内容，直到下一个 ```
        pattern = re.compile(r"```(?:html|HTML)\s*\n(.*?)```", re.DOTALL)
        matches = pattern.findall(raw_output)
        if matches:
            result["preview_html"] = matches[0].strip()
        else:
            # fallback: 尝试找 <!DOCTYPE html> 或 <html 标签
            doctype_idx = raw_output.find("<!DOCTYPE")
            html_idx = raw_output.find("<html")
            start = min(i for i in [doctype_idx, html_idx] if i >= 0) if any(i >= 0 for i in [doctype_idx, html_idx]) else -1
            if start >= 0:
                end = raw_output.rfind("</html>")
                if end > start:
                    result["preview_html"] = raw_output[start:end + len("</html>")].strip()

    if stage_key == "development":
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
        if files:
            result["code_files"] = files

    if stage_key == "requirement":
        # Try extracting from code block wrappers (prg, markdown, md)
        for tag in ["```prg", "```markdown", "```md"]:
            parts = raw_output.split(tag)
            for part in parts[1:]:
                end = part.find("```")
                if end > 0:
                    result["prd_document"] = part[:end].strip()
                    break
            if result.get("prd_document"):
                break

    if stage_key == "code_review":
        if "PASS" in raw_output:
            result["review_passed"] = True
        elif "FAIL" in raw_output:
            result["review_passed"] = False
        # 提取改进建议作为修复指导
        suggestions = []
        for line in raw_output.split("\n"):
            line = line.strip()
            if line.startswith(("- ", "* ", "改进", "建议", "修复", "问题")):
                suggestions.append(line)
        if suggestions:
            result["fix_suggestions"] = "\n".join(suggestions[:10])

    if stage_key == "testing":
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
    retriable_keywords = ["timeout", "rate limit", "429", "503", "502", "connection",
                          "overloaded", "capacity", "retry"]
    return any(kw in error_str for kw in retriable_keywords)


async def _call_agent_with_retry(agent_service: AgentService, session_id: str,
                                  message: str, agent_type: str) -> str:
    """调用 Agent，自动重试可恢复的错误"""
    last_error = None

    for attempt in range(MAX_LLM_RETRIES):
        try:
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


# ==================== 流水线管理器 ====================

class DevPipelineManager:
    """完整开发流水线管理器（数据库持久化 + 自修复 + 记忆）"""

    def __init__(self):
        self.agent_service = AgentService()

    async def create_pipeline(self, project_id: str = "", user_request: str = "",
                              tenant_id: int = 0, creator_id: int = 0,
                              git_config_id: int = None, git_repo_url: str = "",
                              git_branch: str = "main", skill_config: dict = None) -> str:
        pipeline_id = f"pipe_{uuid.uuid4().hex[:12]}"
        now = int(time.time() * 1000)
        stages = _init_stages()

        db_obj = DevPipeline(
            pipeline_id=pipeline_id,
            project_id=project_id,
            user_request=user_request,
            status=PipelineStatus.PENDING.value,
            current_stage="requirement",
            stages_data=json.dumps(stages, ensure_ascii=False),
            retry_count=0,
            tenant_id=tenant_id,
            creator_id=creator_id,
            git_config_id=git_config_id,
            git_repo_url=git_repo_url,
            git_branch=git_branch,
            skill_config=json.dumps(skill_config, ensure_ascii=False) if skill_config else None,
            create_time=now,
            update_time=now,
        )

        async with async_session_maker() as session:
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
        return {
            "pipeline_id": pipe.pipeline_id,
            "project_id": pipe.project_id or "",
            "user_request": pipe.user_request or "",
            "status": pipe.status,
            "current_stage": pipe.current_stage,
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
                                  tenant_id: int, session=None) -> str:
        """检索与当前流水线相关的记忆"""
        try:
            if session:
                memories = await MemoryService.get_memories(
                    db=session,
                    session_id=pipeline_id,
                    limit=5,
                    memory_types=[MemoryType.LONG_TERM, MemoryType.SEMANTIC],
                    min_importance=60,
                )
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
                    await mem_session.commit()

            if not memories:
                return ""

            return "\n".join([
                f"- [{m.agent_type}] {m.content}"
                for m in memories
            ])
        except Exception as e:
            logger.warning(f"Failed to retrieve memories: {e}")
            return ""

    # ==================== Skill 执行 ====================

    async def _execute_stage_skill(
        self, pipeline_id: str, pipe: DevPipeline,
        stage_key: str, stages: Dict[str, Any],
        parsed: Dict[str, Any], session: AsyncSession,
    ) -> None:
        """根据阶段调用对应的 Pipeline Skill"""
        skill_config = json.loads(pipe.skill_config or "{}")
        workspace = pipe.workspace_path

        # Skill: code_writer — development 阶段写文件
        if stage_key == "development" and parsed.get("code_files"):
            workspace = ensure_workspace(pipeline_id)
            pipe.workspace_path = workspace
            result = await skill_registry.execute(
                "code_writer",
                pipeline_id=pipeline_id,
                code_files=parsed["code_files"],
            )
            if result.status.value == "completed" and result.output:
                logger.info(f"code_writer: {result.output.get('files_written', [])}")
                stages[stage_key]["skill_result"] = {
                    "skill": "code_writer",
                    "files_written": result.output.get("files_written", []),
                }
                pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                pipe.update_time = int(time.time() * 1000)
                await session.flush()

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

    async def execute_stage(self, pipeline_id: str, user_input: str = "") -> Dict[str, Any]:
        """执行流水线（迭代循环，带自修复分支）"""
        # Ensure LLM config is loaded from DB before executing
        from app.ai.agents import AgentFactory
        async with async_session_maker() as cfg_session:
            await AgentFactory.load_llm_from_db(cfg_session)

        async with async_session_maker() as session:
            pipe = await self._load_pipeline(session, pipeline_id)
            stages = self._parse_stages(pipe)
            fix_feedback = ""

            while True:
                current_stage = pipe.current_stage
                agent_type = _get_stage_agent(current_stage)

                # 更新阶段状态
                stages[current_stage]["status"] = "running"
                stages[current_stage]["started_at"] = datetime.now().isoformat()
                pipe.status = PipelineStatus.RUNNING.value
                pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                pipe.update_time = int(time.time() * 1000)
                await session.commit()

                # 检索记忆
                memories_text = await self._retrieve_memories(
                    pipeline_id, current_stage, pipe.tenant_id, session
                )

                # 构建 prompt（加载项目级自定义 prompt）
                context = {
                    "user_request": user_input or pipe.user_request or "",
                    "stage_outputs": {k: v for k, v in stages.items() if v.get("status") == "completed"},
                    "fix_feedback": fix_feedback,
                    "memories_text": memories_text,
                }
                project_prompts = await self._load_project_prompts(pipe.project_id or "")
                prompt = _build_pipeline_prompt(current_stage, context,
                                                 custom_prompts=project_prompts)
                if user_input:
                    prompt = f"{user_input}\n\n{prompt}"
                    user_input = ""

                # 调用 Agent（带重试）
                session_id = f"{pipeline_id}_{current_stage}"
                try:
                    raw_output = await _call_agent_with_retry(
                        self.agent_service, session_id, prompt, agent_type
                    )

                    # 解析输出
                    parsed = _parse_agent_output(current_stage, raw_output)
                    stages[current_stage].update({
                        "status": "completed",
                        "output": raw_output,
                        "structured_output": parsed,
                        "preview_html": parsed.get("preview_html", ""),
                        "code_files": parsed.get("code_files", {}),
                        "completed_at": datetime.now().isoformat(),
                    })
                    pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                    await session.commit()

                    # 保存记忆
                    await self._save_stage_memory(
                        pipeline_id, current_stage, agent_type, raw_output, parsed, pipe.tenant_id,
                        db_session=session
                    )

                    # ---- Skill 调用：将 LLM 输出落地为实际操作 ----
                    await self._execute_stage_skill(
                        pipeline_id, pipe, current_stage, stages, parsed, session
                    )

                    # ---- 条件分支：自修复决策 ----

                    # 分支 1: 需要用户确认 → 暂停
                    if _stage_needs_confirm(current_stage):
                        pipe.status = PipelineStatus.WAITING_CONFIRM.value
                        pipe.update_time = int(time.time() * 1000)
                        await session.commit()
                        return {
                            "pipeline_id": pipeline_id,
                            "stage": current_stage,
                            "status": "waiting_confirm",
                            "output": raw_output,
                            "preview_html": parsed.get("preview_html", ""),
                            "need_confirm": True,
                        }

                    # 分支 2: Code Review 失败 → 回退到开发阶段修复
                    if current_stage == "code_review" and parsed.get("review_passed") is False:
                        if pipe.retry_count < MAX_FIX_ITERATIONS:
                            pipe.retry_count += 1
                            fix_feedback = parsed.get("fix_suggestions", raw_output[:500])
                            pipe.current_stage = "development"
                            stages["development"]["status"] = "pending"
                            pipe.status = PipelineStatus.RUNNING.value
                            pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                            pipe.update_time = int(time.time() * 1000)
                            await session.commit()

                            logger.info(f"Pipeline {pipeline_id}: Code review failed, "
                                       f"looping back to development (iteration {pipe.retry_count}/{MAX_FIX_ITERATIONS})")
                            # 保存修复记忆
                            await self._save_stage_memory(
                                pipeline_id, "code_review_fix", agent_type,
                                f"第{pipe.retry_count}次修复: {fix_feedback[:300]}",
                                {}, pipe.tenant_id,
                                db_session=session
                            )
                            continue  # 继续循环，重新执行 development
                        else:
                            pipe.status = PipelineStatus.FAILED.value
                            pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                            pipe.update_time = int(time.time() * 1000)
                            await session.commit()
                            return {
                                "pipeline_id": pipeline_id,
                                "stage": current_stage,
                                "status": "failed",
                                "error": f"代码审查在 {MAX_FIX_ITERATIONS} 次修复后仍未通过",
                                "retry_count": pipe.retry_count,
                            }

                    # 分支 3: 测试失败 → 回退到开发阶段修复 Bug
                    if current_stage == "testing" and not parsed.get("tests_passed", True):
                        if pipe.retry_count < MAX_FIX_ITERATIONS:
                            pipe.retry_count += 1
                            fix_feedback = f"测试发现问题，请修复:\n{parsed.get('bug_details', raw_output[:500])}"
                            pipe.current_stage = "development"
                            stages["development"]["status"] = "pending"
                            pipe.status = PipelineStatus.RUNNING.value
                            pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                            pipe.update_time = int(time.time() * 1000)
                            await session.commit()

                            logger.info(f"Pipeline {pipeline_id}: Tests failed, "
                                       f"looping back to development (iteration {pipe.retry_count}/{MAX_FIX_ITERATIONS})")
                            continue
                        else:
                            pipe.status = PipelineStatus.FAILED.value
                            pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                            pipe.update_time = int(time.time() * 1000)
                            await session.commit()
                            return {
                                "pipeline_id": pipeline_id,
                                "stage": current_stage,
                                "status": "failed",
                                "error": f"自动化测试在 {MAX_FIX_ITERATIONS} 次修复后仍有问题",
                                "retry_count": pipe.retry_count,
                            }

                    # 分支 4: 测试通过 → 重置重试计数器
                    if current_stage == "testing":
                        pipe.retry_count = 0

                    # 正常推进到下一阶段
                    idx = STAGE_KEYS.index(current_stage)
                    if idx + 1 >= len(STAGE_KEYS):
                        pipe.status = PipelineStatus.COMPLETED.value
                        pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                        pipe.update_time = int(time.time() * 1000)
                        await session.commit()
                        logger.info(f"Pipeline {pipeline_id}: All stages completed")
                        return {
                            "pipeline_id": pipeline_id,
                            "stage": current_stage,
                            "status": "completed",
                            "message": "流水线全部完成",
                        }

                    next_stage = STAGE_KEYS[idx + 1]
                    pipe.current_stage = next_stage
                    pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                    pipe.update_time = int(time.time() * 1000)
                    await session.commit()
                    fix_feedback = ""  # 清除修复反馈
                    # 继续循环

                except Exception as e:
                    logger.error(f"Pipeline {pipeline_id} stage {current_stage} failed: {e}")
                    stages[current_stage]["status"] = "failed"
                    stages[current_stage]["error"] = str(e)
                    pipe.status = PipelineStatus.FAILED.value
                    pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                    pipe.update_time = int(time.time() * 1000)
                    await session.commit()
                    return {
                        "pipeline_id": pipeline_id,
                        "stage": current_stage,
                        "status": "failed",
                        "error": str(e),
                    }

    # ==================== 用户确认 ====================

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

            if not confirmed:
                # 用户拒绝，退回该阶段并重新生成
                stages[current_stage]["status"] = "pending"
                stages[current_stage]["output"] = ""
                stages[current_stage]["structured_output"] = {}
                stages[current_stage]["preview_html"] = ""
                pipe.status = PipelineStatus.PENDING.value
                if feedback:
                    pipe.user_request = feedback
                pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                pipe.update_time = int(time.time() * 1000)
                await session.commit()
                # 自动重新执行该阶段（带 feedback 作为用户输入）
                return await self.execute_stage(pipeline_id, feedback)

            # 确认通过，推进到下一阶段
            idx = STAGE_KEYS.index(current_stage)
            if idx + 1 >= len(STAGE_KEYS):
                pipe.status = PipelineStatus.COMPLETED.value
                pipe.update_time = int(time.time() * 1000)
                await session.commit()
                return {"pipeline_id": pipeline_id, "status": "completed"}

            next_stage = STAGE_KEYS[idx + 1]
            pipe.current_stage = next_stage
            pipe.status = PipelineStatus.PENDING.value
            pipe.stages_data = json.dumps(stages, ensure_ascii=False)
            pipe.update_time = int(time.time() * 1000)
            await session.commit()

            # 自动执行下一阶段
            return await self.execute_stage(pipeline_id, feedback)

    # ==================== 查询方法 ====================

    async def get_pipeline_status(self, pipeline_id: str) -> Dict[str, Any]:
        async with async_session_maker() as session:
            pipe = await self._load_pipeline(session, pipeline_id)
            return self._to_status_dict(pipe)

    async def get_preview(self, pipeline_id: str) -> Dict[str, Any]:
        async with async_session_maker() as session:
            pipe = await self._load_pipeline(session, pipeline_id)
            stages = self._parse_stages(pipe)
            ui_stage = stages.get("ui_preview", {})
            return {
                "pipeline_id": pipeline_id,
                "preview_html": ui_stage.get("preview_html", ""),
                "output": ui_stage.get("output", ""),
            }

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
                    "status": p.status,
                    "current_stage": p.current_stage,
                    "retry_count": p.retry_count,
                    "created_at": str(p.create_time),
                }
                for p in pipes
            ]

    async def rollback(self, pipeline_id: str) -> Dict[str, Any]:
        async with async_session_maker() as session:
            pipe = await self._load_pipeline(session, pipeline_id)
            try:
                idx = STAGE_KEYS.index(pipe.current_stage)
            except ValueError:
                return {"error": "无效阶段"}

            if idx == 0:
                return {"error": "已经是第一阶段"}

            prev_stage = STAGE_KEYS[idx - 1]
            stages = self._parse_stages(pipe)

            # 重置当前阶段（清空输出）
            current_key = STAGE_KEYS[idx]
            stages[current_key]["status"] = "pending"
            stages[current_key]["output"] = ""
            stages[current_key]["structured_output"] = {}
            stages[current_key]["error"] = ""
            stages[current_key]["completed_at"] = None

            # 回退阶段：保留输出，允许用户编辑/确认
            stages[prev_stage]["status"] = "completed"
            stages[prev_stage]["error"] = ""

            pipe.current_stage = prev_stage
            pipe.retry_count = 0
            pipe.update_time = int(time.time() * 1000)

            # 如果回退到的阶段需要确认，设为 waiting_confirm
            if _stage_needs_confirm(prev_stage):
                pipe.status = PipelineStatus.WAITING_CONFIRM.value
            else:
                pipe.status = PipelineStatus.PENDING.value

            pipe.stages_data = json.dumps(stages, ensure_ascii=False)
            await session.commit()

            return {
                "pipeline_id": pipeline_id,
                "rolled_back_to": prev_stage,
                "status": pipe.status,
                "need_confirm": _stage_needs_confirm(prev_stage),
                "output": stages[prev_stage].get("output", ""),
                "preview_html": stages[prev_stage].get("preview_html", ""),
            }


pipeline_manager = DevPipelineManager()
