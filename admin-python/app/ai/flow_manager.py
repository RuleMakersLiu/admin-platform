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
from app.ai.pipeline_skills import ensure_workspace, get_workspace_path
from app.ai.skills import skill_registry
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


def _fix_loop_stage_for_mode(stage_keys: List[str]) -> str:
    if "frontend_dev" in stage_keys:
        return "frontend_dev"
    if "prototype" in stage_keys:
        return "prototype"
    return stage_keys[0] if stage_keys else ""


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


PIPELINE_GLOBAL_PROMPT_CONTRACT = """

## 全局执行契约（所有阶段必须遵守）
1. 事实边界：只能基于用户需求、已匹配 Project Skill、项目代码参考、上游阶段产物和明确修复反馈推理；不确定的信息必须写入“假设/待确认”，禁止伪造接口、字段、组件、权限或外部事实。
2. 范围边界：只处理当前阶段职责，不提前替代后续阶段，也不遗漏当前阶段必须交付的内容；如果当前阶段输出格式有特殊要求，以当前阶段“输出格式/输出要求”为最高优先级。
3. 逻辑边界：每个结论都要能追溯到业务目标、页面行为、数据字段、权限策略或接口契约；前端字段、mock 字段、API 字段、后端字段必须保持同名同义同类型。
4. 异常边界：必须覆盖空数据、加载中、无权限、接口失败、重复提交、并发操作、数据越权、输入非法、分页越界、状态流转非法等边界。
5. 项目边界：优先复用匹配项目的目录结构、组件、API 封装、权限约定、响应模型和命名风格；不知道是否存在的组件/工具不要引用。
6. 输出边界：不要寒暄，不要解释自己如何工作；不要输出与当前阶段无关的散文。Markdown 阶段直接输出文档；JSON 阶段必须输出可解析 JSON；代码阶段必须给完整文件内容。
7. 自检要求：输出前检查是否满足当前阶段清单、是否存在字段不一致、是否遗漏权限/异常/验收标准、是否有不可执行或不可验证内容。
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
如果需求可以落成多个页面，也优先交付 1 个最核心、最能验收业务价值的完整页面；不要为了覆盖过多页面导致每个页面都不可用。

## 实现要求
1. 根据目标技术栈生成真实项目代码，不要再输出纯静态 HTML mock。
2. 根据匹配项目的真实技术栈生成文件：Vue 后台通常生成 `src/views/**/*.vue` + `src/api/*.js`；React 后台通常生成 `src/pages/**/*.tsx|jsx` + service/api 文件；uni-app/小程序项目按项目现有 `pages/**`、`*.vue` 或 `*.wxml/*.js/*.json/*.wxss` 结构生成。不要把所有项目都当 Vue 后台。
   - 文件路径必须像目标项目里的真实业务模块路径，优先沿用 Project Skill 或代码参考里的目录命名。
   - 如果用户需求表达的是“现有/已有/当前/原有页面或功能上增加、修改、优化、补充筛选/字段/按钮/查询”，必须修改「与本需求相关的已确认前端页面路径」中的现有页面；禁止凭语义新建 `src/views/**/List.vue` 或 `src/pages/**/List.vue` 来冒充改造，禁止选择活动管理、营销活动等无关业务页面。
   - 现有功能改造必须做最小增量：旧表格列、旧列表数据、旧查询接口、旧 mixin、旧组件、旧操作列都是既有能力，不要重写整页架构，不要重新生成整页 mock 数据或新建一套列表 API。比如“给现有零售商品列表增加商品ID筛选项”，只需要在现有页面新增查询控件、queryParam 和请求参数传递；除非需求明确要求新增接口/新增数据源，否则不要输出 `mockProductList`、`Mock.mock` 或完整假数据。
   - 如果用户说“新增/增加/添加某个筛选项”，这是新增筛选项，不是把已有筛选项改名。必须保留原页面已有筛选控件及其 `queryParam` 字段，再为新增筛选项绑定 API 契约确认的独立请求字段。例如新增“商品ID”时，保留原“商品编号”及 `queryParam.productCode`，再新增“商品ID”及 `queryParam.id`。只有用户明确说“改名/调整文案/重命名”时，才允许修改旧 label/placeholder。
   - 修改现有 Vue 列表页时必须保留原页面的 `ListMixin`/`mixins`、`<s-table :data="loadData">`、`url.list` 接口、已有 columns/slots/操作按钮和已有导入；除非用户明确要求删除，否则不要用本地 `data()`、新 API 文件或新接口替代原列表加载方式。
   - 如果找不到与现有功能对应的已确认页面路径，本阶段不要编造新页面，应输出空 JSON 数组让系统失败并在修复反馈中暴露“缺少真实页面路径”。
   - 禁止生成 `Demo`、`Example`、`Standalone`、`SandboxPreview`、`PreviewOnly`、`MockPage`、`GeneratedPage` 这类独立演示路径或组件名。
   - 禁止生成新的 `package.json`、`vite.config.*`、`main.*`、`App.*`、`index.html` 来伪造一个独立应用。
3. 第一屏必须匹配需求页面类型：列表页要有搜索筛选、表格和批量/行操作；详情页要有分区详情、状态标签、返回/编辑/启停等操作；表单页要有校验、提交、取消和异常提示；配置/看板页要有对应业务控件和状态。
4. 所有按钮必须有真实前端交互，不允许出现未定义函数、空 onclick、只展示不响应的控件。
5. 可以使用 mock API 数据，但文件结构要能在真实项目中运行预览；小程序项目必须同时给出浏览器 HTML/H5 等效预览文件。
6. 代码要短而完整：页面组件控制在 260 行以内，API/mock 服务模块控制在 120 行以内。
7. 只生成与本需求相关的新增/修改文件，不要输出说明文字。
8. 代码必须体现页面设计中的权限、状态和边界；不要只做 happy path。
9. API/service 文件中的 mock 数据必须与页面字段、交付 API 契约候选字段完全一致。
10. 不允许用“占位按钮”“待实现方法”“console.log 替代业务逻辑”来冒充完成。

## 可预览硬约束
1. 先判断页面类型，不要把详情页/表单页/配置页强行写成列表页；列表契约只适用于列表或表格页面。
2. 如果使用项目 `STable` 组件，`loadData` 必须返回分页对象：`{ page, pageNo, pageSize, count, totalCount, list }`，其中 `list` 必须是数组；禁止只返回数组、`result.data` 数组或没有 `list` 的对象。
3. API/mock 服务模块里的列表接口必须返回同一分页对象，可包在 `result` 或 `data` 中，但对象内必须同时提供 `list/page/count/pageNo/totalCount`。
4. 详情/编辑/配置接口必须返回对象，可包在 `result` 或 `data` 中；页面读取前必须有默认空对象，禁止直接对可能为 undefined 的对象取深层字段。
5. 接口函数必须兼容真实接口和 mock 接口，推荐写法：列表 `then(res => res.result || res.data || res)`，详情 `then(res => res.result || res.data || {})`。
6. 小程序/uni-app 页面必须遵循项目路由和页面生命周期：原生小程序至少成对生成 `pages/.../*.wxml` 和 `pages/.../*.js`，需要样式/配置时补 `*.wxss/*.json`；uni-app 使用 `pages/.../*.vue`，不要引用 Web-only 组件。
7. 原生小程序必须额外生成 `public/sandbox-miniapp-preview.html`，作为浏览器可打开的 H5 等效预览。该 HTML 必须自包含 CSS/JS/mock 数据，并真实呈现小程序页面的布局、状态和交互；它是验收预览，不替代小程序源码。
8. 禁止引用项目中未确认存在的组件、指令或工具；如果不确定，直接使用目标项目基础组件和本文件内方法。
9. 所有模板事件引用的方法必须实现；表格列的 `scopedSlots` 必须有对应 slot。
10. 代码必须能在首屏无运行时报错：不得访问可能为 undefined 的 `.length`、`.map`、`.filter`，除非先做 `Array.isArray` 或默认空数组。
11. 数组兜底重点在页面组件里完成：例如 `const rows = Array.isArray(payload.list) ? payload.list : []`，模板和渲染逻辑只读取 `rows`；API/mock 服务模块只要返回契约正确的列表对象，不要因为参数处理中的 `.map/.filter/.length` 影响页面可用性。

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
- 后台 Web 页面通常只输出 2 个文件：页面组件 + API/mock 服务模块
- 原生小程序必须输出小程序页面文件 + `public/sandbox-miniapp-preview.html`
- 禁止输出 ```json 或任何 Markdown 包裹
- 输出前必须自检 JSON 合法性、文件路径合理性、方法完整性、字段一致性和首屏运行安全性

示例:
[
  {"path": "src/views/Marketing/FlashSaleList.vue", "content": "完整文件内容"},
  {"path": "src/api/marketing.js", "content": "完整文件内容"}
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

请输出:
1. 项目概况：需求目标、范围边界、参考项目、执行模式。
2. 完成功能列表：按阶段说明已完成内容和关键产物。
3. 技术栈总结：前端、后端/API、权限、测试、部署相关信息。
4. 契约与字段对齐结论：接口、字段、权限、mock 与真实数据的一致性。
5. 验证结果：测试、构建、审查、预览或部署验证的结论。
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
4. Field-level alignment between frontend code, mock data, API contract, and backend/project skill conventions.
5. Code reasonableness: state handling, loading/empty/error states, undefined guards, event handlers, permissions, and maintainability.

Return FAIL with actionable feedback when any of these three checks is incomplete.
"""
    return memory_section + fix_section + PIPELINE_GLOBAL_PROMPT_CONTRACT + prompt


# ==================== 输出解析 ====================

def _is_existing_feature_change_request(user_request: str) -> bool:
    text = (user_request or "").strip()
    if not text:
        return False
    existing_markers = ("现有", "已有", "当前", "原有", "既有")
    change_markers = ("增加", "添加", "新增", "补充", "改造", "优化", "调整", "修改")
    target_markers = ("列表", "页面", "功能", "筛选", "查询", "搜索", "字段", "按钮", "表格")
    if any(marker in text for marker in existing_markers):
        return any(marker in text for marker in target_markers)
    return any(marker in text for marker in change_markers) and any(marker in text for marker in ("筛选", "查询", "搜索", "字段"))


def _is_frontend_page_path(path: str) -> bool:
    return (
        path.startswith(("src/views/", "src/pages/", "pages/"))
        and path.endswith((".vue", ".tsx", ".jsx", ".wxml"))
    )


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
    if re.search(r"(mock|假数据|模拟数据|预览数据|新接口|新增接口|新增数据源)", user_request or "", re.I):
        return []

    issues = []
    for path, content in files.items():
        safe_path = str(path).replace("\\", "/").lstrip("/")
        if not safe_path.startswith("src/api/") or not isinstance(content, str):
            continue
        if re.search(r"\bmock[A-Za-z0-9_]*List\b|\bMock\.mock\b|const\s+mock[A-Za-z0-9_]*\s*=", content):
            issues.append(
                f"{safe_path} 为现有功能改造生成了 mock 列表数据；旧列表数据和旧接口应复用现有能力，"
                "除非需求明确要求新增接口或 mock 数据"
            )
        if re.search(r"return\s+new\s+Promise\s*\(", content) and re.search(r"\b(list|data)\s*:", content):
            issues.append(
                f"{safe_path} 为现有功能改造生成了模拟接口 Promise；应只在必要时补充现有请求参数，不要重造旧列表数据"
            )
    return issues


def _collect_api_endpoints(content: str) -> List[str]:
    if not isinstance(content, str):
        return []
    return sorted(set(re.findall(r"['\"](/api/[^'\"]+)['\"]", content)))


def _validate_undefined_data_return_refs(path: str, content: str) -> List[str]:
    if not isinstance(content, str) or not path.endswith((".vue", ".js", ".ts", ".tsx", ".jsx")):
        return []
    issues: List[str] = []
    in_data_return = False
    entered_runtime_function = False
    for line in content.splitlines():
        stripped = line.strip()
        if re.search(r"\bdata\s*\([^)]*\)\s*\{", line):
            in_data_return = False
            entered_runtime_function = False
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
            safe_path = str(path).replace("\\", "/").lstrip("/")
            issues.append(
                f"{safe_path} 的 data() 初始返回对象引用了 result/res/parameter 等未定义运行期变量，"
                "会导致 created/首屏渲染时报错"
            )
            break
    return issues


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

        original_endpoints = _collect_api_endpoints(original)
        for endpoint in original_endpoints:
            if endpoint not in generated:
                issues.append(f"{safe_path} 原页面列表接口 {endpoint} 被移除或替换，现有功能改造必须复用原接口")

    return issues


def _validate_frontend_preview_code_files(
    files: Dict[str, str],
    user_request: str = "",
    existing_frontend_paths: Optional[List[str]] = None,
    existing_frontend_files: Optional[Dict[str, str]] = None,
) -> List[str]:
    issues: List[str] = []
    if not files:
        return ["没有生成前端代码文件"]

    issues.extend(_validate_existing_feature_paths(files, user_request, existing_frontend_paths))
    issues.extend(_validate_existing_feature_mock_scope(files, user_request))
    issues.extend(
        _validate_existing_feature_preservation(
            files,
            user_request=user_request,
            existing_frontend_paths=existing_frontend_paths,
            existing_frontend_files=existing_frontend_files,
        )
    )

    normalized_paths = [str(path).replace("\\", "/").lstrip("/") for path in files]
    vue_admin_paths = [
        path for path in normalized_paths
        if path.startswith(("src/views/", "src/pages/", "pages/")) and path.endswith(".vue")
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

    if static_paths and not mini_wxml_paths:
        issues.append("预览阶段禁止生成静态 HTML 文件，必须生成真实前端项目代码")
    if not (vue_admin_paths or react_page_paths or mini_wxml_paths):
        issues.append("缺少可预览页面文件：Vue/uni-app .vue、React .tsx/.jsx 或小程序 pages/*.wxml")
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
                if "loadData" not in content:
                    issues.append(f"{safe_path} 使用 STable 但没有定义 loadData")
                if not uses_existing_list_mixin:
                    if not re.search(r"\blist\s*:", content) and not re.search(r"\blist\b", content):
                        issues.append(f"{safe_path} 使用 STable 时必须处理分页对象 list 字段")
                    for required in ("page", "count"):
                        if not re.search(rf"\b{required}\s*:", content):
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


def _auto_fix_frontend_preview_code_files(files: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    fixed: Dict[str, str] = {}
    fixes: List[str] = []
    for path, content in files.items():
        if not isinstance(content, str):
            fixed[path] = content
            continue
        safe_path = str(path).replace("\\", "/").lstrip("/")
        patched = content
        if safe_path.startswith(("src/views/", "src/pages/")) and safe_path.endswith(".vue"):
            patched = _patch_stable_table_contract_content(patched)
        if patched != content:
            fixes.append(f"{safe_path}: 自动补齐 STable 分页返回字段 page/count/list")
        fixed[path] = patched
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
        return "\n".join(lines[:index] + filter_lines + lines[index:])
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
                        content = f.read(_project_file_read_limit(rel_path))
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


def _project_file_read_limit(rel_path: str) -> int:
    normalized = str(rel_path).replace("\\", "/").lstrip("/")
    if normalized.startswith(("src/views/", "src/pages/", "pages/")) and normalized.endswith((
        ".vue", ".tsx", ".jsx", ".js", ".ts", ".wxml",
    )):
        return 30000
    return 5000


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
                if selected_content:
                    selected_content = _compact_context(selected_content, 4500 if compact_preview_stage else 9000)
                    ctx_parts.append(
                        "## 已选择页面的原始代码（必须基于此文件做最小增量修改）\n"
                        f"路径：`{selected_frontend_page_path}`\n"
                        "要求：保留原页面的 imports、mixins、components、url/list 接口、表格列、slots、操作按钮和已有方法；"
                        "只改用户明确要求的筛选/字段/交互。若已有等价字段，优先调整文案，不要重复添加字段。\n\n"
                        f"{selected_content}"
                    )
            if compact_preview_stage:
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
                            fixed_files, auto_fixes = _auto_fix_frontend_preview_code_files(parsed.get("code_files", {}))
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
                            preview_issues = _validate_frontend_preview_code_files(
                                parsed.get("code_files", {}),
                                user_request=pipe.user_request or "",
                                existing_frontend_paths=existing_paths,
                                existing_frontend_files=existing_frontend_files,
                            )
                        if not preview_issues:
                            break

                        preview_validation_feedback = (
                            "上一版前端预览代码未通过可运行性约束，请重新生成完整 JSON 文件数组，"
                            "不要解释，只修代码。必须修复以下问题：\n"
                            + "\n".join(f"- {issue}" for issue in preview_issues[:12])
                        )
                        await emit({
                            "type": "stage_retry",
                            "stage": current_stage,
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "reason": "preview_validation_failed",
                            "issues": preview_issues[:12],
                        })
                        if attempt >= max_attempts:
                            error_msg = "预览生成代码未通过可运行性约束: " + "；".join(preview_issues[:8])
                            stages[current_stage].update({
                                "status": "failed",
                                "output": raw_output,
                                "structured_output": parsed,
                                "preview_html": parsed.get("preview_html", ""),
                                "code_files": parsed.get("code_files", {}),
                                "error": error_msg,
                            })
                            raise ValueError(error_msg)

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
                        fixed_files, auto_fixes = _auto_fix_frontend_preview_code_files(parsed.get("code_files", {}))
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
                        preview_issues = _validate_frontend_preview_code_files(
                            parsed.get("code_files", {}),
                            user_request=pipe.user_request or "",
                            existing_frontend_paths=existing_paths,
                            existing_frontend_files=existing_frontend_files,
                        )
                        if preview_issues:
                            error_msg = "预览生成代码未通过可运行性约束: " + "；".join(preview_issues[:8])
                            stages[current_stage].update({
                                "status": "failed",
                                "output": raw_output,
                                "structured_output": parsed,
                                "preview_html": parsed.get("preview_html", ""),
                                "code_files": parsed.get("code_files", {}),
                                "error": error_msg,
                            })
                            raise ValueError(error_msg)
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
                    if (
                        current_stage == "code_review"
                        and parsed.get("review_passed") is False
                        and "frontend_dev" in stage_keys
                    ):
                        if pipe.retry_count < MAX_FIX_ITERATIONS:
                            pipe.retry_count += 1
                            fix_feedback = parsed.get("fix_suggestions", raw_output[:500])
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

                            logger.info(f"Pipeline {pipeline_id}: Code review failed, "
                                       f"looping back to {loop_stage} (iteration {pipe.retry_count}/{MAX_FIX_ITERATIONS})")
                            await self._save_stage_memory(
                                pipeline_id, "code_review_fix", agent_type,
                                f"第{pipe.retry_count}次修复: {fix_feedback[:300]}",
                                {}, pipe.tenant_id, db_session=session
                            )
                            continue  # 继续循环，重新执行修复阶段
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

    async def update_stage_output(self, pipeline_id: str, stage: str, output: str) -> Dict[str, Any]:
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
                    fixed_files, _auto_fixes = _auto_fix_frontend_preview_code_files(parsed.get("code_files", {}))
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
                    )
                    if preview_issues:
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
