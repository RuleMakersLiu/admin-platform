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
import time
from datetime import datetime
from enum import Enum
from typing import Awaitable, Callable, AsyncGenerator, Dict, List, Optional, Any, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents import AgentService
from app.ai.pipeline_skills import ensure_workspace, get_workspace_path
from app.ai.skills import skill_registry
from app.models.agent_models import DevPipeline, ProjectKnowledge
from app.services.memory_service import MemoryService, MemoryType
from app.services.user_evolution_service import UserEvolutionService
from app.core.database import async_session_maker

logger = logging.getLogger(__name__)

MAX_FIX_ITERATIONS = 3
MAX_LLM_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds
LLM_STAGE_TIMEOUT = 600  # 单阶段 LLM 调用最大超时（秒）
LLM_STREAM_IDLE_TIMEOUT = 45  # seconds without stream chunks before fallback


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_CONFIRM = "waiting_confirm"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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


def _stage_keys_for_mode(pipeline_mode: str = "full") -> List[str]:
    return PIPELINE_MODE_STAGES.get(pipeline_mode or "full", STAGE_KEYS)


def _is_product_preview_code_stage(stage_key: str, pipe_config: Dict[str, Any]) -> bool:
    return stage_key == "prototype" and pipe_config.get("pipeline_mode") == "frontend_contract_review"


def _compact_context(text: str, limit: int = 4000) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[context truncated]"


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
        "skill_status": project_skill.skill_status or "",
        "skill_version": project_skill.skill_version or 1,
        "confirmed_at": project_skill.confirmed_at,
    }


DEFAULT_STAGE_PROMPTS: Dict[str, str] = {
    "requirement": """请根据以下用户需求，生成一份完整的需求文档(PRD)。

用户需求:
{{user_request}}

## 已识别项目
- 前端项目: {{frontend_project_name}}
- 前端技术栈: {{frontend_tech}}
- 后端项目: {{backend_project_name}}
- 后端技术栈: {{backend_tech}}

## 参考项目
如果上方有「Confirmed Frontend Project Skill Snapshot」「Confirmed Backend/API Project Skill Snapshot」「前端项目代码参考」或「后端项目代码参考」，请同时结合前端和后端项目的现有架构、字段、组件、接口规范来撰写需求，保持与项目一致的技术风格。

直接输出 Markdown 格式的 PRD 文档（不要用代码块包裹），不要写任何寒暄、开场白或解释，直接从标题开始。包含:
1. 项目概述（必须分别写明前端参考项目和后端参考项目）
2. 功能需求列表（含优先级 P0/P1/P2/P3）
3. 用户故事
4. 非功能需求
5. 验收标准""",

    "page_design": """基于以下需求文档，进行详细的页面设计。

## 已识别项目
- 前端项目: {{frontend_project_name}}
- 前端技术栈: {{frontend_tech}}
- 后端项目: {{backend_project_name}}
- 后端技术栈: {{backend_tech}}

## 需求文档
{{requirement_output}}

请直接输出 Markdown 格式的页面设计文档（不要用代码块包裹），包含:
1. 页面列表及层级关系
2. 每个页面的字段定义（字段名、类型、是否必填、校验规则）
3. 每个页面的按钮和操作（新增、编辑、删除、导出等）
4. 搜索/筛选条件
5. 弹窗交互说明（新增弹窗、编辑弹窗、确认弹窗）
6. 页面状态（空数据、加载中、无权限、搜索无结果、异常）
7. 权限控制点（页面级权限 + 按钮/操作级权限）
8. 开发确认要点（需要开发团队确认的技术问题）""",

    "prototype": """根据需求文档和页面设计，直接生成可写入匹配前端项目的前端预览代码。

## 需求文档
{{requirement_output}}

## 页面设计
{{page_design_output}}

## 前端技术栈
{{frontend_tech}}

## 用户需求
{{user_request}}

## 重要：参考项目
结合 Frontend Project Skill，优先复用现有项目的目录、组件库、路由、API 封装、权限判断、表格/表单模式和样式规范。不要展开解释。

## 生成目标
本阶段就是前端代码生成阶段，不再有后续单独的“前端开发”阶段。产物会直接覆盖到匹配前端项目的沙箱副本中，并通过该项目自己的 npm 脚本启动预览。

## 实现要求
1. 根据目标技术栈生成真实项目代码，不要再输出纯静态 HTML mock。
2. Vue 项目生成 1 个 `.vue` 页面组件和 1 个 API/mock 服务模块即可；不要生成大量文件。
3. 第一屏必须是成熟后台工作台：搜索筛选、表格、操作按钮、新增/编辑弹窗或抽屉、删除确认、权限态、空/加载/异常状态。
4. 所有按钮必须有真实前端交互，不允许出现未定义函数、空 onclick、只展示不响应的控件。
5. 可以使用 mock API 数据，但文件结构要能在真实项目中运行预览。
6. 代码要短而完整：页面组件控制在 260 行以内，API/mock 服务模块控制在 120 行以内。
7. 只生成与本需求相关的新增/修改文件，不要输出说明文字。

## 输出格式
只允许输出 JSON 文件数组，不要输出 Markdown，不要输出代码块围栏，不要输出解释文字。系统会直接解析这个 JSON 并写入前端项目。

JSON 格式如下:
[
  {"path": "src/views/Marketing/FlashSaleList.vue", "content": "完整文件内容"},
  {"path": "src/api/marketing.js", "content": "完整文件内容"}
]

要求：
- 必须是合法 JSON，最外层必须是数组
- 每项必须包含 path 和 content
- content 里放完整文件内容，换行用 JSON 字符串转义；必须完整闭合所有 JSON 字符串、对象和数组
- 只输出 2 个文件：页面组件 + API/mock 服务模块
- 禁止输出 ```json 或任何 Markdown 包裹

示例:
[
  {"path": "src/views/Marketing/FlashSaleList.vue", "content": "完整文件内容"},
  {"path": "src/api/marketing.js", "content": "完整文件内容"}
]""",

    "delivery": """基于需求分析、页面设计和前端预览代码，整理一份完整的交付文档包。

## 后端项目规范来源
- 后端项目: {{backend_project_name}}
- 后端技术栈: {{backend_tech}}

## 需求文档
{{requirement_output}}

## 页面设计
{{page_design_output}}

请直接输出 Markdown 格式的交付文档（不要用代码块包裹），包含:
1. PRD 摘要（功能清单、优先级、验收标准）
2. 页面设计规格（字段、按钮、交互、状态、权限）
3. 交互流程说明（主流程 + 异常流程）
4. 前端实现要点（组件选择、状态管理、路由规划）
5. API 接口草案（接口路径、请求方法、请求参数、响应格式）
   - 必须单独写明“参考后端项目：{{backend_project_name}}”
   - 必须按后端 Project Skill 的 API Contract Patterns 生成，不能凭空创造另一套规范
   - 必须体现后端鉴权、权限校验、错误响应、Swagger/接口文档规则
   - 响应格式必须逐字遵循后端 Project Skill 中的统一响应模型；如果后端 Skill 定义了 ApiResult/traceId/message/data 结构，所有接口响应示例都必须使用该结构，不允许改成扁平的 {code,message,data}
   - 如果后端项目是 BFF/API 转发层，要明确哪些接口是本层接收、鉴权和转发
6. Mock 数据示例（至少包含列表和详情的 mock 数据）
7. 权限规则表（角色 × 操作权限矩阵）
8. 测试验收标准（功能测试用例清单、边界条件、兼容性要求）""",

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

    "backend_dev": """基于以下需求文档和交付包，生成完整的后端代码。

需求文档:
{{requirement_output}}

交付包:
{{delivery_output}}

## 目标技术栈
{{backend_tech}}

请根据以上技术栈生成对应的后端代码。如果未指定技术栈，默认使用 Java Spring Boot + MyBatis-Plus。

**注意**: 如果前端层是 PHP 转发层（BFF），则后端需要提供完整的 RESTful API 供 PHP 层调用，接口需要考虑：
- 统一的响应格式（code/msg/data）
- 认证 token 的传递和校验
- 分页、排序等通用参数的标准化

输出要求:
- 每个代码块前用 `### 文件: 路径/文件名` 标注
- 用对应语言的代码块包裹（```java, ```php, ```go, ```python, ```sql 等）
- 包含 Controller、Service、Model/Entity、数据库建表 SQL
- 遵循该技术栈的最佳实践和常见分层架构

在所有代码之后，请用以下 JSON 格式汇总文件列表（方便自动化解析）:
```json
[
  {"path": "src/main/java/xxx/Controller.java", "content": "完整文件内容"},
  {"path": "src/main/java/xxx/Service.java", "content": "完整文件内容"}
]
```""",

    "frontend_dev": """基于以下需求文档、页面设计和原型预览，生成完整的前端代码。

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

在所有代码之后，请用以下 JSON 格式汇总文件列表:
```json
[
  {"path": "src/views/List.vue", "content": "完整文件内容"},
  {"path": "src/api/module.js", "content": "完整文件内容"}
]
```""",

    "code_review": """请审查以下前后端代码，检查代码质量、安全性和最佳实践。

后端代码:
{{backend_dev_output}}

前端代码:
{{frontend_dev_output}}

请输出:
1. 后端代码评分 (A/B/C/D/F)
2. 前端代码评分 (A/B/C/D/F)
3. 发现的问题列表（含严重程度: critical/major/minor，标注前后端）
4. 改进建议（每个问题给出具体的修复方案）
5. 是否通过审查 (PASS/FAIL)

如果发现 critical 或 major 问题，标记为 FAIL 并给出详细修复指导。

请在输出末尾附带结构化 JSON（方便自动化解析）:
```json
{
  "review_passed": true/false,
  "backend_score": "A/B/C/D/F",
  "frontend_score": "A/B/C/D/F",
  "fix_suggestions": "修复建议摘要"
}
```""",

    "testing": """基于以下需求和前后端代码，设计测试用例并生成可执行的测试脚本。

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
1. 测试用例列表（含优先级、预期结果）
2. 覆盖率评估
3. 发现的 Bug 列表（标注严重程度: critical/major/minor）

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

    "commit": """请整理以下前后端代码，生成提交信息并准备提交。

后端代码:
{{backend_dev_output}}

前端代码:
{{frontend_dev_output}}

测试结果:
{{testing_output}}

请输出:
1. 后端 Git commit message（Conventional Commits 格式）
2. 前端 Git commit message（Conventional Commits 格式）
3. 后端变更文件列表
4. 前端变更文件列表""",

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

    replacements = {
        "{{user_request}}": user_request[:2000],
        "{{requirement_output}}": prev_outputs.get("requirement", {}).get("output", "未提供")[:1800],
        "{{page_design_output}}": prev_outputs.get("page_design", {}).get("output", "未提供")[:2200],
        "{{prototype_output}}": prev_outputs.get("prototype", {}).get("output", "未提供")[:3000],
        "{{delivery_output}}": prev_outputs.get("delivery", {}).get("output", "未提供")[:3000],
        "{{ui_preview_output}}": prev_outputs.get("ui_preview", {}).get("output", "未提供")[:3000],
        "{{backend_dev_output}}": prev_outputs.get("backend_dev", {}).get("output", "未提供")[:3000],
        "{{frontend_dev_output}}": (
            prev_outputs.get("frontend_dev", {}).get("output")
            or prev_outputs.get("prototype", {}).get("output")
            or "未提供"
        )[:3000],
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
    if stage_key == "requirement" and "pm_quality" not in prompt:
        prompt += PM_REQUIREMENT_REVIEW_CONTRACT
    if stage_key == "page_design" and "design_quality" not in prompt:
        prompt += PM_PAGE_DESIGN_REVIEW_CONTRACT
    if stage_key == "code_review" and context.get("pipeline_mode") == "frontend_contract_review":
        prompt += """

## First-Version Review Scope
This pipeline delivers frontend preview code in the preview stage, API contract, and review results.
Do not require backend implementation, test execution, commit, or deployment in this mode.
Focus the review on:
1. Frontend code completeness and whether it can run inside the matched frontend project sandbox.
2. Frontend code consistency with the confirmed Project Skill.
3. API contract completeness: endpoints, methods, params, response shape, error cases, and permissions.

Return FAIL with actionable feedback when any of these three checks is incomplete.
"""
    return memory_section + fix_section + prompt


# ==================== 输出解析 ====================

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
    for match in pattern.finditer(raw_output):
        try:
            files = parse_data(json.loads(match.group(1).strip()))
            if files:
                return files
        except (json.JSONDecodeError, TypeError):
            continue

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
                                  thinking_override: Optional[Dict[str, Any]] = None) -> str:
    """调用 Agent，自动重试可恢复的错误"""
    last_error = None
    original_max_tokens = None
    original_thinking = None

    if max_tokens_override or thinking_override is not None:
        from app.ai.agents import AgentFactory
        agent = AgentFactory.get_agent(agent_type)
        llm = agent._get_llm() if hasattr(agent, "_get_llm") else getattr(agent, "_llm", None)
        if max_tokens_override and llm and hasattr(llm, "max_tokens"):
            original_max_tokens = llm.max_tokens
            llm.max_tokens = max_tokens_override
        if llm and thinking_override is not None and hasattr(llm, "thinking"):
            original_thinking = llm.thinking
            llm.thinking = thinking_override

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
) -> str:
    """Call an agent with streaming chunks while preserving the final reply."""
    last_error = None
    original_max_tokens = None
    original_thinking = None

    if max_tokens_override or thinking_override is not None:
        from app.ai.agents import AgentFactory
        agent = AgentFactory.get_agent(agent_type)
        llm = agent._get_llm() if hasattr(agent, "_get_llm") else getattr(agent, "_llm", None)
        if max_tokens_override and llm and hasattr(llm, "max_tokens"):
            original_max_tokens = llm.max_tokens
            llm.max_tokens = max_tokens_override
        if llm and thinking_override is not None and hasattr(llm, "thinking"):
            original_thinking = llm.thinking
            llm.thinking = thinking_override

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
                    result = await agent_service.chat(
                        session_id=session_id,
                        message=message,
                        agent_type=agent_type,
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
                if emitted_any or not _is_retriable_error(e):
                    logger.error(f"Agent stream failed: {e}")
                    raise

                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"Agent stream failed (retriable, attempt {attempt + 1}/{MAX_LLM_RETRIES}): "
                    f"{e}. Retrying in {delay}s..."
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


# ==================== 项目上下文加载 ====================

# 项目文件缓存（进程级，避免重复克隆）
_project_cache: Dict[str, Dict[str, str]] = {}


async def _load_project_context(project_id: str, project_type: str) -> str:
    """从 Generator 获取项目信息，从 Git 拉取关键文件，返回上下文文本。
    project_type: "frontend" 或 "backend"
    """
    if not project_id:
        return ""

    cache_key = f"{project_id}:{project_type}"
    if cache_key in _project_cache:
        files = _project_cache[cache_key]
    else:
        files = await _fetch_project_files_from_git(project_id)
        _project_cache[cache_key] = files

    if not files:
        return ""

    # 筛选关键文件
    key_patterns = _get_key_file_patterns(project_type)
    key_files = {}
    for path, content in files.items():
        if any(path.endswith(p) or path.endswith("/" + p) for p in key_patterns):
            key_files[path] = content
    if not key_files:
        # 没匹配到关键文件，取前 3 个非空文件
        for path, content in list(files.items())[:3]:
            if content.strip():
                key_files[path] = content[:2000]

    # 构建上下文文本（总长度限制 6000 字符）
    sections = []
    total = 0
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


async def _fetch_project_files_from_git(project_id: str) -> Dict[str, str]:
    """从 Generator 获取项目 Git 地址，浅克隆并读取关键文件"""
    import httpx
    import tempfile
    import os

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

        # 3. 读取关键文件
        files = {}
        for root, dirs, filenames in os.walk(tmp_dir):
            # 跳过 .git, node_modules, dist 等
            dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', 'dist', '.nuxt', '.next', '__pycache__', 'vendor', 'target', 'build'}]
            for fname in filenames:
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, tmp_dir)
                # 只读代码文件，跳过二进制
                if any(rel_path.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.eot', '.mp4', '.mp3', '.zip', '.tar', '.gz']):
                    continue
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(5000)
                    files[rel_path] = content
                except Exception:
                    pass

        # 清理临时目录
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

        logger.info(f"Loaded {len(files)} files from project {project_id}")
        return files

    except Exception as e:
        logger.warning(f"Failed to load project context for {project_id}: {e}")
        return {}


async def _clone_project_repo(clone_url: str, branch: str, tmp_dir: str):
    """Clone a repo, falling back to the remote default branch when stored branch is stale."""
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
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)
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
        context = {
            "user_request": user_request,
            "stage_outputs": {k: v for k, v in stages.items() if v.get("status") == "completed"},
            "fix_feedback": revision_feedback,
            "memories_text": memories_text,
            "backend_tech": pipe_config.get("backend_tech", ""),
            "frontend_tech": pipe_config.get("frontend_tech", ""),
            "pipeline_mode": pipe_config.get("pipeline_mode", "full"),
        }

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
            if compact_preview_stage:
                frontend_skill_content = _compact_context(frontend_skill_content, 2500)
            ctx_parts.append(
                "## Confirmed Frontend Project Skill Snapshot\n"
                f"Project: {project_skill_snapshot.get('project_name', '')}\n"
                f"Version: {project_skill_snapshot.get('skill_version', '')}\n\n"
                f"{frontend_skill_content}"
            )
        backend_context_stages = (
            "requirement",
            "page_design",
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
            ctx_parts.append(
                "## Confirmed Backend/API Project Skill Snapshot\n"
                f"Project: {snapshot.get('project_name', '')}\n"
                f"Version: {snapshot.get('skill_version', '')}\n\n"
                f"{snapshot.get('skill_content', '')}"
            )
        if fe_proj_id and stage_key in ("frontend_dev", "prototype", "page_design", "delivery", "code_review"):
            from app.services.knowledge_service import get_relevant_context
            if compact_preview_stage:
                fe_ctx = await _load_project_context(fe_proj_id, "frontend")
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
                    fe_ctx = await _load_project_context(fe_proj_id, "frontend")
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
                be_ctx = await _load_project_context(current_be_proj_id, "backend")
                if be_ctx:
                    ctx_parts.append(f"## 后端项目代码参考\n{be_ctx}")
        if ctx_parts:
            project_ctx_section = "\n\n".join(ctx_parts)
            if compact_preview_stage:
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
        max_tok = 32768 if compact_preview_stage else (16384 if stage_key in html_stages else None)
        thinking_override = {"type": "disabled"} if compact_preview_stage else None

        if on_chunk:
            raw_output = await asyncio.wait_for(
                _call_agent_with_retry_stream(
                    self.agent_service, session_id, prompt, agent_type,
                    on_chunk=on_chunk,
                    max_tokens_override=max_tok,
                    thinking_override=thinking_override,
                ),
                timeout=LLM_STAGE_TIMEOUT,
            )
        else:
            raw_output = await asyncio.wait_for(
                _call_agent_with_retry(
                    self.agent_service, session_id, prompt, agent_type,
                    max_tokens_override=max_tok,
                    thinking_override=thinking_override,
                ),
                timeout=LLM_STAGE_TIMEOUT,
            )

        parsed = _parse_agent_output(stage_key, raw_output)
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

            while True:
                current_stage = pipe.current_stage

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
                        fe_result, be_result = await asyncio.gather(
                            self._run_single_stage(
                                pipeline_id, "frontend_dev", stages,
                                pipe, fix_feedback, user_input, session,
                                on_chunk=(
                                    lambda content: emit({
                                        "type": "chunk",
                                        "stage": "frontend_dev",
                                        "content": content,
                                    })
                                ) if stream_callback else None,
                            ),
                            self._run_single_stage(
                                pipeline_id, "backend_dev", stages,
                                pipe, fix_feedback, user_input, session,
                                on_chunk=(
                                    lambda content: emit({
                                        "type": "chunk",
                                        "stage": "backend_dev",
                                        "content": content,
                                    })
                                ) if stream_callback else None,
                            ),
                            return_exceptions=True,
                        )

                        # 处理前端结果
                        if isinstance(fe_result, Exception):
                            raise fe_result
                        fe_output, fe_parsed = fe_result
                        stages["frontend_dev"].update({
                            "status": "completed",
                            "output": fe_output,
                            "structured_output": fe_parsed,
                            "preview_html": fe_parsed.get("preview_html", ""),
                            "code_files": fe_parsed.get("code_files", {}),
                            "revision_feedback": "",
                            "completed_at": datetime.now().isoformat(),
                        })
                        await self._save_stage_memory(
                            pipeline_id, "frontend_dev", "FE",
                            fe_output, fe_parsed, pipe.tenant_id, db_session=session,
                        )
                        await emit({
                            "type": "stage_completed",
                            "stage": "frontend_dev",
                            "output": fe_output,
                            "result": fe_parsed,
                        })

                        # 处理后端结果
                        if isinstance(be_result, Exception):
                            raise be_result
                        be_output, be_parsed = be_result
                        stages["backend_dev"].update({
                            "status": "completed",
                            "output": be_output,
                            "structured_output": be_parsed,
                            "code_files": be_parsed.get("code_files", {}),
                            "revision_feedback": "",
                            "completed_at": datetime.now().isoformat(),
                        })
                        await self._save_stage_memory(
                            pipeline_id, "backend_dev", "BE",
                            be_output, be_parsed, pipe.tenant_id, db_session=session,
                        )
                        await emit({
                            "type": "stage_completed",
                            "stage": "backend_dev",
                            "output": be_output,
                            "result": be_parsed,
                        })

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

                        # code_review need_confirm → 暂停
                        if _stage_needs_confirm("code_review"):
                            pipe.status = PipelineStatus.WAITING_CONFIRM.value
                            pipe.update_time = int(time.time() * 1000)
                            await session.commit()
                            await emit({
                                "type": "waiting_confirm",
                                "stage": "code_review",
                                "need_confirm": True,
                            })
                            return {
                                "pipeline_id": pipeline_id,
                                "stage": "frontend_dev+backend_dev",
                                "status": "waiting_confirm",
                                "output": fe_output[:500] + "\n---\n" + be_output[:500],
                                "need_confirm": True,
                                "parallel": True,
                            }
                        continue  # 不需要确认，继续循环执行 code_review

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
                stages[current_stage]["status"] = "running"
                stages[current_stage]["started_at"] = datetime.now().isoformat()
                pipe.status = PipelineStatus.RUNNING.value
                pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                pipe.update_time = int(time.time() * 1000)
                await session.commit()
                await emit({"type": "stage_started", "stage": current_stage})

                try:
                    raw_output, parsed = await self._run_single_stage(
                        pipeline_id, current_stage, stages,
                        pipe, fix_feedback, user_input, session,
                        on_chunk=(
                            lambda content: emit({
                                "type": "chunk",
                                "stage": current_stage,
                                "content": content,
                            })
                        ) if stream_callback else None,
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
                    if current_stage == "ui_preview" and not (parsed.get("preview_html") or "").strip():
                        raise ValueError("预览生成阶段没有产出可渲染 HTML，请重新生成")

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
                    if current_stage == "code_review" and parsed.get("review_passed") is False:
                        if pipe.retry_count < MAX_FIX_ITERATIONS:
                            pipe.retry_count += 1
                            fix_feedback = parsed.get("fix_suggestions", raw_output[:500])
                            pipe.current_stage = "frontend_dev"
                            idx = stage_keys.index("frontend_dev")
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

                            logger.info(f"Pipeline {pipeline_id}: Code review failed, "
                                       f"looping back to frontend_dev (iteration {pipe.retry_count}/{MAX_FIX_ITERATIONS})")
                            await self._save_stage_memory(
                                pipeline_id, "code_review_fix", agent_type,
                                f"第{pipe.retry_count}次修复: {fix_feedback[:300]}",
                                {}, pipe.tenant_id, db_session=session
                            )
                            continue  # 继续循环，重新执行 frontend_dev
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

                    # 分支 0b: 测试失败 → 自动回退到前端开发阶段修复 Bug
                    if current_stage == "testing" and not parsed.get("tests_passed", True):
                        if pipe.retry_count < MAX_FIX_ITERATIONS:
                            pipe.retry_count += 1
                            fix_feedback = f"测试发现问题，请修复:\n{parsed.get('bug_details', raw_output[:500])}"
                            pipe.current_stage = "frontend_dev"
                            idx = stage_keys.index("frontend_dev")
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
                                       f"looping back to frontend_dev (iteration {pipe.retry_count}/{MAX_FIX_ITERATIONS})")
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

                    # 分支 1: 需要用户确认 → 暂停
                    if _stage_needs_confirm(current_stage):
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
                        pipe.status = PipelineStatus.COMPLETED.value
                        pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                        pipe.update_time = int(time.time() * 1000)
                        await self._record_user_evolution(session, pipe, stages)
                        await session.commit()
                        logger.info(f"Pipeline {pipeline_id}: All stages completed")
                        await emit({"type": "completed", "stage": current_stage})
                        return {
                            "pipeline_id": pipeline_id,
                            "stage": current_stage,
                            "status": "completed",
                            "message": "流水线全部完成",
                        }

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
                    stages[current_stage]["status"] = "failed"
                    stages[current_stage]["error"] = f"阶段超时（{LLM_STAGE_TIMEOUT}秒），LLM 未返回结果，请重试"
                    pipe.status = PipelineStatus.FAILED.value
                    pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                    pipe.update_time = int(time.time() * 1000)
                    await session.commit()
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
                    logger.error(f"Pipeline {pipeline_id} stage {current_stage} failed: {e}")
                    stages[current_stage]["status"] = "failed"
                    stages[current_stage]["error"] = str(e)
                    pipe.status = PipelineStatus.FAILED.value
                    pipe.stages_data = json.dumps(stages, ensure_ascii=False)
                    pipe.update_time = int(time.time() * 1000)
                    await session.commit()
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

    # ==================== 查询方法 ====================

    async def get_pipeline_status(self, pipeline_id: str) -> Dict[str, Any]:
        async with async_session_maker() as session:
            pipe = await self._load_pipeline(session, pipeline_id)
            return self._to_status_dict(pipe)

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
                    "user_request": p.user_request or "",
                    "status": p.status,
                    "current_stage": p.current_stage,
                    "retry_count": p.retry_count,
                    "create_time": p.create_time,
                    "update_time": p.update_time,
                }
                for p in pipes
            ]

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
