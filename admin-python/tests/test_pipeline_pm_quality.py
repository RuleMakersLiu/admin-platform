from pathlib import Path

from app.ai.flow_manager import (
    _auto_fix_frontend_preview_code_files,
    _build_preview_failure_message,
    _build_repair_tasks_from_issues,
    _build_repair_task_feedback,
    _build_pipeline_prompt,
    _build_deterministic_code_review_result,
    _compact_fix_feedback,
    _declared_frontend_paths_from_page_design_stage,
    _expected_prototype_pages_from_page_design,
    _parse_agent_output,
    _prototype_focus_from_page_design,
    _validate_frontend_preview_code_files,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
GROUP_BUY_PM_DELIVERY = ROOT_DIR / "docs/reports/pm-group-buying-delivery-2026-06-10.md"


def test_group_buy_pm_delivery_document_is_product_manager_ready():
    document = GROUP_BUY_PM_DELIVERY.read_text(encoding="utf-8")

    assert "## 需求分析执行记录" in document
    assert "输入盘点" in document
    assert "业务目标拆解" in document
    assert "流程建模" in document
    assert "验收标准落地" in document
    assert "## PRD" in document
    assert "## 页面设计" in document
    assert "## 测试计划" in document
    assert "## 产品经理交付检查清单" in document
    assert "marketing:groupBuy:create" in document
    assert "/api/marketing/group-buy/page" in document


def test_group_buy_pm_outputs_pass_requirement_and_design_quality_gates():
    requirement = """
# 拼团活动管理 PRD

## 项目概述
目标用户：运营、客服、财务和系统管理员。业务目标：通过拼团活动提升商品转化。

## 范围边界
本次做活动列表、创建编辑、详情、启停、团单处理；不做 C 端分享页和支付通道。

## 功能需求列表
- P0 活动列表查询：输入活动名称、状态、时间范围，输出分页列表。
- P0 创建拼团活动：输入商品 SKU、团购价、成团人数、活动时间，输出待上线活动。
- P1 数据导出：按查询条件异步导出。

## 角色与权限矩阵
- 运营：marketing:groupBuy:create、marketing:groupBuy:update。
- 财务：marketing:groupBuy:export。

## 权限模型与策略样例
- RBAC: role=运营主管, resource=groupBuyActivity, action=publish。
- ABAC: condition=同租户且活动所属部门在用户授权部门内。

## 数据范围与条件权限
- tenantId 来自登录上下文，按授权部门过滤。

## 数据对象与字段
- activityName string 必填。
- groupPrice decimal 必填，必须低于 salePrice。
- groupSize int 必填，2-99。

## 页面/业务状态
- 空数据、加载中、无权限、接口失败、重复提交、库存不足、状态非法。

## 验收标准
- QA 创建合法活动后，列表可查询到待上线活动。
- 无上线权限时按钮隐藏，API 返回 403。

## 假设与待确认问题
- 真实商品选择接口和退款策略待确认。

```json
{
  "pm_quality": {
    "score": 96,
    "ready_for_review": true,
    "missing_items": [],
    "primary_pages": ["拼团活动列表页", "拼团活动创建/编辑页", "拼团活动详情页"],
    "permission_points": ["marketing:groupBuy:create", "marketing:groupBuy:update", "marketing:groupBuy:export"],
    "permission_model": ["RBAC role/resource/action", "ABAC tenant/department condition"],
    "data_scope_rules": ["同租户", "授权部门"],
    "policy_examples": ["role=运营主管, resource=groupBuyActivity, action=publish, condition=同租户"],
    "data_entities": ["group_buy_activity", "group_buy_sku", "group_buy_team"],
    "acceptance_criteria": ["创建合法活动后列表可查询", "无权限 API 返回 403"]
  }
}
```
"""

    design = GROUP_BUY_PM_DELIVERY.read_text(encoding="utf-8")
    parsed_requirement = _parse_agent_output("requirement", requirement)
    parsed_design = _parse_agent_output(
        "page_design",
        design
        + """

```json
{
  "design_quality": {
    "score": 95,
    "ready_for_review": true,
    "missing_items": [],
    "primary_pages": ["拼团活动列表页", "拼团活动创建/编辑页", "拼团活动详情页"],
    "permission_points": ["marketing:groupBuy:view", "marketing:groupBuy:create", "marketing:groupBuy:team:manualSuccess"],
    "data_entities": ["group_buy_activity", "group_buy_sku", "group_buy_team"],
    "acceptance_criteria": ["prototype 必须覆盖列表、创建编辑和详情"]
  }
}
```
""",
    )

    assert parsed_requirement["pm_quality"]["ready_for_review"] is True
    assert parsed_requirement["pm_quality"]["score"] >= 90
    assert "marketing:groupBuy:create" in parsed_requirement["pm_quality"]["permission_points"]
    assert parsed_design["design_quality"]["ready_for_review"] is True
    assert _expected_prototype_pages_from_page_design({
        "output": parsed_design["page_design_document"],
        "structured_output": parsed_design,
    }) == ["拼团活动列表页", "拼团活动创建/编辑页", "拼团活动详情页"]


def test_group_buy_delivery_can_drive_complete_preview_validation():
    document = GROUP_BUY_PM_DELIVERY.read_text(encoding="utf-8")
    page_design_stage = {
        "output": document,
        "structured_output": {
            "design_quality": {
                "primary_pages": ["拼团活动列表页", "拼团活动创建/编辑页", "拼团活动详情页"],
            }
        },
    }
    page_content = """
<template>
  <div>
    <div v-action="'marketing:groupBuy:create'">新增 编辑 复制 上线 下线 导出 手动成团 详情</div>
    <div>拼团活动列表页 拼团活动创建/编辑页 拼团活动详情页 ProductSelectorModal</div>
    <s-table :data="loadData" />
  </div>
</template>
<script>
export default {
  data () {
    return {
      queryParam: { activityName: '', skuId: '', activityStatus: '', startTime: '', endTime: '', pageNo: 1, pageSize: 20 },
      loadData: parameter => getGroupBuyPage({ ...this.queryParam, ...parameter }).then(res => ({
        list: Array.isArray(res.list) ? res.list : [],
        page: res.page || 1,
        count: res.count || 0
      }))
    }
  },
  methods: {
    searchQuery () {},
    searchReset () {},
    handleAdd () {},
    handleEdit () {},
    handleDetail () {},
    handleExport () {},
    handleManualSuccess () {}
  }
}
</script>
"""
    files = {
        "src/views/marketing/groupBuy/GroupBuyList.vue": page_content,
        "src/views/marketing/groupBuy/GroupBuyEdit.vue": page_content,
        "src/views/marketing/groupBuy/GroupBuyDetail.vue": page_content,
        "src/api/groupBuy.js": """
export function getGroupBuyPage () { return Promise.resolve({ list: [], page: 1, count: 0 }) }
export function getGroupBuyDetail () { return Promise.resolve({ activity: {}, skuList: [], teamSummary: {}, logs: [] }) }
export function createGroupBuy () { return Promise.resolve({ id: 1 }) }
export function updateGroupBuy () { return Promise.resolve({ success: true }) }
export function changeGroupBuyStatus () { return Promise.resolve({ success: true }) }
export function getGroupBuyTeamPage () { return Promise.resolve({ list: [], page: 1, count: 0 }) }
export function getProductSkuPage () { return Promise.resolve({ list: [], page: 1, count: 0 }) }
// /api/marketing/group-buy/page
// /api/marketing/group-buy/detail
// /api/marketing/group-buy/create
// /api/marketing/group-buy/update
// /api/marketing/group-buy/status
// /api/marketing/group-buy/team/page
// /api/product/sku/page
""",
    }

    issues = _validate_frontend_preview_code_files(
        files,
        user_request="做一个拼团团购活动管理功能",
        expected_pages=_expected_prototype_pages_from_page_design(page_design_stage),
        page_design_stage=page_design_stage,
    )

    assert issues == []


def test_preview_repair_issues_are_split_into_small_tasks():
    tasks = _build_repair_tasks_from_issues([
        "页面设计 API 契约声明了接口，但 API 模块未覆盖：/api/product/sku/page、/api/activity/group-buy/**",
        "页面设计要求使用项目组件，但前端页面未体现：Modal、JDictSelectTag",
        "页面设计主页面“拼团活动列表页”没有对应的前端页面文件",
        "src/components/ProductSelectorModal.vue 使用 STable 时必须处理分页字段 page",
    ])

    assert [task["category"] for task in tasks] == [
        "api_contract",
        "api_contract",
        "component_usage",
        "component_usage",
        "page_file",
        "table_pagination",
    ]
    assert any(task["target"] == "/api/product/sku/page" for task in tasks)
    assert any(task["target"] == "JDictSelectTag" for task in tasks)
    assert any(task["target"] == "拼团活动列表页" for task in tasks)


def test_preview_repair_feedback_is_task_oriented_and_product_readable():
    issues = [
        "src/api/activityManage.js 的 mock/API 响应使用扁平 code/message/msg 结构；后端 Project Skill 要求 ApiResult 包装为 { message: { code: 0, message: 'ok' }, traceId, data }",
        "页面设计 API 契约声明了接口，但 API 模块未覆盖：/api/product/sku/page、/api/activity/group-buy/**",
        "src/views/activityManage/ActivityManageList.vue 访问数组前缺少默认空数组兜底，容易首屏运行时报错",
        "src/views/activityManage/ActivityManageList.vue 使用 STable 时必须处理分页对象 list 字段",
    ]
    tasks = _build_repair_tasks_from_issues(issues)
    feedback = _build_repair_task_feedback(tasks, issues)
    message = _build_preview_failure_message(tasks, issues)

    assert [task["category"] for task in tasks] == [
        "api_response_envelope",
        "api_contract",
        "api_contract",
        "runtime_guard",
        "table_pagination",
    ]
    assert "## 修复任务清单" in feedback
    assert "禁止扁平" in feedback
    assert "当前剩余 5 个修复点" in message
    assert "接口响应格式" in message
    assert "首屏运行兜底" in message


def test_preview_auto_fix_fills_contract_pages_api_components_and_api_result():
    page_design_stage = {
        "output": """# 页面设计

## 页面清单
| 页面名称 | 路由 | 组件路径 |
| --- | --- | --- |
| 拼团活动列表页 | `/marketing/activity-group-list` | `src/views/activityManage/GroupBuyList.vue` |
| 秒杀活动列表页 | `/marketing/activity-flash-list` | `src/views/activityManage/FlashSaleList.vue` |

## API 契约
- 商品 SKU 分页：`GET /api/product/sku/page`
- 拼团活动：`GET /api/activity/group-buy/**`
- 秒杀活动：`GET /api/activity/flash-sale/**`

## 组件要求
- 使用 `Modal`
- 使用 `JDictSelectTag`
- 删除操作使用 `Modal.confirm`
"""
    }
    pipe_config = {
        "backend_project_skill_snapshot": {
            "skill_content": (
                "ApiResult response contains traceId and message is object: "
                "{\"message\":{\"code\":0,\"message\":\"ok\"},\"traceId\":\"\",\"data\":{}}"
            )
        }
    }
    files = {
        "src/views/activityManage/ActivityManageList.vue": (
            "<template><div>活动管理</div></template>\n"
            "<script>export default { data () { return { list: [] } } }</script>"
        ),
        "src/api/activityManage.js": (
            "export function listActivity () { return Promise.resolve({ code: 200, message: 'ok', data: [] }) }"
        ),
    }

    fixed, fixes = _auto_fix_frontend_preview_code_files(
        files,
        page_design_stage=page_design_stage,
        pipe_config=pipe_config,
    )
    issues = _validate_frontend_preview_code_files(
        fixed,
        user_request="新增拼团和秒杀活动管理",
        expected_pages=["拼团活动列表页", "秒杀活动列表页"],
        page_design_stage=page_design_stage,
        pipe_config=pipe_config,
    )

    assert any("ApiResult" in fix for fix in fixes)
    assert "src/views/activityManage/GroupBuyList.vue" not in fixed
    assert "src/views/activityManage/FlashSaleList.vue" not in fixed
    assert any("页面设计声明了组件路径" in issue for issue in issues)
    assert not any("扁平 code/message/msg" in issue for issue in issues)
    assert not any("API 模块未覆盖" in issue for issue in issues)
    assert not any("前端页面未体现" in issue for issue in issues)


def test_preview_validation_matches_primary_page_to_at_alias_declared_component_path():
    page_design_stage = {
        "output": """# 页面设计
| 页面名称 | 路由路径 | 组件路径 |
| :--- | :--- | :--- |
| 拼团活动列表 | `/activity/group-buy-list` | `@/views/activityManage/ActivityManageList.vue` |
| 秒杀活动列表 | `/activity/flash-sale-list` | `@/views/activityManage/ActivityManageList.vue` |
""",
        "structured_output": {
            "design_quality": {
                "primary_pages": ["拼团活动列表页", "秒杀活动列表页"]
            }
        },
    }

    issues = _validate_frontend_preview_code_files(
        {
            "src/views/activityManage/ActivityManageList.vue": (
                "<template><div>拼团活动列表 秒杀活动列表</div></template>"
                "<script>export default { data () { return { list: [] } } }</script>"
            ),
        },
        expected_pages=["拼团活动列表页", "秒杀活动列表页"],
        page_design_stage=page_design_stage,
    )

    assert not any("没有对应的前端页面文件" in issue for issue in issues)


def test_preview_auto_fix_locks_generated_files_to_declared_component_paths():
    page_design_stage = {
        "output": """# 页面设计
| 页面名称 | 路由路径 | 组件路径 |
| :--- | :--- | :--- |
| 拼团活动列表 | `/activity/group-buy-list` | `@/views/activityManage/ActivityManageList.vue` |
| 秒杀活动列表 | `/activity/flash-sale-list` | `@/views/activityManage/ActivityManageList.vue` |
| 新增/编辑活动 | - | `@/views/activityManage/ActivityManageEdit.vue` |
""",
    }
    files = {
        "views/activityManage/ActivityManageList.vue": "<template><div>活动列表</div></template>",
        "src/views/activityManage/GroupBuyList.vue": "<template><div>拼团活动列表</div></template>",
        "src/views/activityManage/FlashSaleList.vue": "<template><div>秒杀活动列表</div></template>",
        "src/api/activityManage.js": "export function list () { return Promise.resolve({ data: [] }) }",
    }

    fixed, fixes = _auto_fix_frontend_preview_code_files(files, page_design_stage=page_design_stage)
    issues = _validate_frontend_preview_code_files(
        fixed,
        expected_pages=["拼团活动列表页", "秒杀活动列表页"],
        page_design_stage=page_design_stage,
    )

    assert "src/views/activityManage/ActivityManageList.vue" in fixed
    assert "src/views/activityManage/ActivityManageEdit.vue" not in fixed
    assert "src/views/activityManage/GroupBuyList.vue" not in fixed
    assert "src/views/activityManage/FlashSaleList.vue" not in fixed
    assert any("自动锁定前端页面/组件文件路径" in fix for fix in fixes)
    assert any("ActivityManageEdit.vue" in issue for issue in issues)


def test_page_design_table_distinguishes_menu_pages_from_modal_components():
    page_design_stage = {
        "output": """# 页面设计
| 页面名称 | 菜单层级 | 路由路径 | 组件路径 | 默认落点 | 面包屑 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 拼团活动列表 | 二级菜单 | `/activity/group-buy-list` | `@/views/activityManage/ActivityManageList.vue` | 列表首屏 | 营销管理 / 拼团活动 |
| 新增/编辑拼团 | 页面内弹窗 | - | `@/views/activityManage/ActivityManageEdit.vue` | - | - |
| 秒杀活动列表 | 二级菜单 | `/activity/flash-sale-list` | `@/views/activityManage/ActivityManageList.vue` (通过props区分) | 列表首屏 | 营销管理 / 秒杀活动 |
| 新增/编辑秒杀 | 页面内弹窗 | - | `@/views/activityManage/ActivityManageEdit.vue` (通过props区分) | - | - |
| 活动商品选择器 | 通用弹窗 | - | `@/components/ProductSelectorModal.vue` | - | - |
"""
    }

    assert _expected_prototype_pages_from_page_design(page_design_stage) == [
        "拼团活动列表",
        "秒杀活动列表",
    ]
    assert _declared_frontend_paths_from_page_design_stage(page_design_stage) == [
        "src/views/activityManage/ActivityManageList.vue",
        "src/views/activityManage/ActivityManageEdit.vue",
        "src/components/ProductSelectorModal.vue",
    ]


def test_shared_component_path_can_cover_multiple_primary_menu_pages():
    page_design_stage = {
        "output": """# 页面设计
| 页面名称 | 菜单层级 | 路由路径 | 组件路径 | 默认落点 | 面包屑 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 拼团活动列表 | 二级菜单 | `/activity/group-buy-list` | `@/views/activityManage/ActivityManageList.vue` | 列表首屏 | 营销管理 / 拼团活动 |
| 新增/编辑拼团 | 页面内弹窗 | - | `@/views/activityManage/ActivityManageEdit.vue` | - | - |
| 秒杀活动列表 | 二级菜单 | `/activity/flash-sale-list` | `@/views/activityManage/ActivityManageList.vue` (通过props区分) | 列表首屏 | 营销管理 / 秒杀活动 |
| 新增/编辑秒杀 | 页面内弹窗 | - | `@/views/activityManage/ActivityManageEdit.vue` (通过props区分) | - | - |
| 活动商品选择器 | 通用弹窗 | - | `@/components/ProductSelectorModal.vue` | - | - |
"""
    }
    files = {
        "src/views/activityManage/ActivityManageList.vue": (
            "<template><div>拼团活动 秒杀活动 <a-button @click=\"handleAdd\">新增</a-button>"
            "<a @click=\"handleEdit(record)\">编辑</a></div></template>"
            "<script>export default { props: { activityType: String }, data () { return { list: [] } }, methods: { handleAdd () {}, handleEdit () {} } }</script>"
        ),
        "src/views/activityManage/ActivityManageEdit.vue": (
            "<template><a-modal :visible=\"visible\"><div>拼团 秒杀</div></a-modal></template>"
            "<script>export default { props: { activityType: String }, data () { return { visible: false } } }</script>"
        ),
        "src/components/ProductSelectorModal.vue": (
            "<template><a-modal :visible=\"visible\"><s-table :data=\"loadData\" /></a-modal></template>"
            "<script>export default { data () { return { visible: false } }, methods: { loadData (parameter) { return Promise.resolve({ list: [], page: parameter.pageNo || 1, count: 0 }) } } }</script>"
        ),
    }

    issues = _validate_frontend_preview_code_files(
        files,
        expected_pages=_expected_prototype_pages_from_page_design(page_design_stage),
        page_design_stage=page_design_stage,
    )

    assert not any("只生成了" in issue for issue in issues)
    assert not any("没有对应的前端页面文件" in issue for issue in issues)


def test_preview_validation_accepts_api_backed_stable_pagination_and_api_data_param():
    files = {
        "src/views/activityManage/ActivityManageList.vue": (
            "<template><s-table ref=\"table\" :columns=\"columns\" :data=\"loadData\" /></template>"
            "<script>import { getActivityList } from '@/api/activityManage'\n"
            "export default { methods: { loadData (parameter) { return getActivityList(parameter, this.activityType) } } }</script>"
        ),
        "src/components/ProductSelectorModal.vue": (
            "<template><s-table ref=\"table\" :columns=\"columns\" :data=\"loadData\" /></template>"
            "<script>import { getProductList } from '@/api/activityManage'\n"
            "export default { methods: { loadData (parameter) { return getProductList(parameter) } } }</script>"
        ),
        "src/api/activityManage.js": (
            "export function saveActivity (data, activityType) { return request({ url: '/x', method: 'post', data: data }) }\n"
            "export function getActivityList (parameter, activityType) { return Promise.resolve({ list: [], page: parameter.pageNo || 1, count: 0 }) }\n"
            "export function getProductList (parameter) { return Promise.resolve({ list: [], page: parameter.pageNo || 1, count: 0 }) }"
        ),
    }

    issues = _validate_frontend_preview_code_files(files)

    assert not any("data() 初始返回对象引用了" in issue for issue in issues)
    assert not any("使用 STable 时必须处理分页对象 list 字段" in issue for issue in issues)
    assert not any("使用 STable 时必须处理分页字段 page" in issue for issue in issues)
    assert not any("使用 STable 时必须处理分页字段 count" in issue for issue in issues)


def test_preview_validation_accepts_custom_stable_data_handler_names():
    files = {
        "src/views/activityGroup/ActivityGroupEdit.vue": (
            "<template><s-table ref=\"skuTable\" :columns=\"columns\" :data=\"loadSkuData\" /></template>"
            "<script>import { getSkuList } from '@/api/groupActivity'\n"
            "export default { methods: { loadSkuData (parameter) { return getSkuList(parameter) } } }</script>"
        ),
        "src/api/groupActivity.js": (
            "export function getSkuList (parameter) { "
            "return Promise.resolve({ list: [], page: parameter.pageNo || 1, count: 0 }) }"
        ),
    }

    issues = _validate_frontend_preview_code_files(files)

    assert not any("使用 STable 但没有定义 loadData" in issue for issue in issues)
    assert not any("使用 STable 但没有定义数据加载方法" in issue for issue in issues)
    assert not any("使用 STable 时必须处理分页字段" in issue for issue in issues)


def test_preview_validation_does_not_treat_method_return_as_data_initial_value():
    files = {
        "src/views/activityManage/ActivityManageList.vue": (
            "<template><s-table ref=\"table\" :columns=\"columns\" :data=\"loadActivityData\" /></template>"
            "<script>import { getActivityList } from '@/api/activityManage'\n"
            "export default { data () { return { queryParam: {}, columns: [] } }, "
            "methods: { loadActivityData (parameter) { return getActivityList(parameter).then(res => ({ "
            "pageNo: res.pageNo || 1, page: res.page || 1, count: res.count || 0, list: Array.isArray(res.list) ? res.list : [] "
            "})) } } }</script>"
        ),
        "src/api/activityManage.js": (
            "export function getActivityList (parameter) { "
            "return Promise.resolve({ list: [], page: parameter.pageNo || 1, count: 0 }) }"
        ),
    }

    issues = _validate_frontend_preview_code_files(files)

    assert not any("data() 初始返回对象引用了" in issue for issue in issues)


def test_preview_validation_checks_page_design_create_buttons_and_real_mock_pagination():
    page_design_stage = {
        "output": """# 页面设计
## 按钮和操作
| 按钮 | 行为 |
| :--- | :--- |
| 新增拼团/秒杀 | 打开新增弹窗 |
"""
    }
    files = {
        "src/views/activityManage/ActivityManageList.vue": (
            "<template><div><a-button>新增</a-button><s-table :data=\"loadData\" /></div></template>"
            "<script>import { getActivityList } from '@/api/activityManage'\n"
            "export default { methods: { loadData (parameter) { return getActivityList(parameter) } } }</script>"
        ),
        "src/api/activityManage.js": (
            "const rows = [{ id: 1 }, { id: 2 }]\n"
            "export function getActivityList (parameter) { const pageNo = parameter.pageNo || 1; const pageSize = parameter.pageSize || 10; return Promise.resolve({ list: rows, page: pageNo, count: rows.length, pageNo, pageSize }) }"
        ),
    }

    issues = _validate_frontend_preview_code_files(files, page_design_stage=page_design_stage)

    assert any("新增拼团" in issue for issue in issues)
    assert any("新增秒杀" in issue for issue in issues)
    assert any("翻页时必须返回不同页数据" in issue for issue in issues)


def test_page_design_action_requirements_only_use_button_operation_rows():
    from app.ai.flow_manager import _action_requirements_from_design

    document = """# 页面设计

## 页面清单
| 页面名称 | 组件路径 |
| :--- | :--- |
| 新增/编辑拼团/秒杀活动弹窗 | `@/views/activityManage/ActivityManageEdit.vue` |

## 查询与筛选
- 排序：创建时间倒序。

## 按钮和操作
| 按钮 | 行为 |
| :--- | :--- |
| 新增拼团/秒杀 | 打开新增弹窗 |
"""

    assert _action_requirements_from_design(document) == ["新增拼团", "新增秒杀"]


def test_preview_validation_accepts_dynamic_create_button_label_from_page_state():
    page_design_stage = {
        "output": """# 页面设计
## 按钮和操作
| 按钮 | 行为 |
| :--- | :--- |
| 新增拼团/秒杀 | 打开新增弹窗 |
"""
    }
    files = {
        "src/views/activityManage/ActivityManageList.vue": (
            "<template><a-button>新增{{ activityTypeLabel }}</a-button></template>"
            "<script>export default { computed: { activityTypeLabel () { return this.activityType === 'groupBuy' ? '拼团' : '秒杀' } } }</script>"
        )
    }

    issues = _validate_frontend_preview_code_files(files, page_design_stage=page_design_stage)

    assert not any("新增/创建入口" in issue for issue in issues)


def test_preview_validation_accepts_combined_create_edit_action_when_controls_exist():
    page_design_stage = {
        "output": """# 页面设计
## 按钮和操作
| 按钮 | 行为 |
| :--- | :--- |
| 新增/编辑拼团 | 新增按钮和编辑行操作打开表单 |
| 新增/编辑秒杀 | 新增按钮和编辑行操作打开表单 |
"""
    }
    files = {
        "src/views/activityManage/ActivityManageList.vue": (
            "<template><div>"
            "<a-button @click=\"handleAdd\">新增</a-button>"
            "<a @click=\"handleEdit(record)\">编辑</a>"
            "<span>拼团</span><span>秒杀</span>"
            "</div></template>"
            "<script>export default { methods: { handleAdd () {}, handleEdit () {} } }</script>"
        )
    }

    issues = _validate_frontend_preview_code_files(files, page_design_stage=page_design_stage)

    assert not any("新增/创建入口" in issue for issue in issues)


def test_preview_auto_fix_modal_reference_does_not_create_undefined_vue_state():
    page_design_stage = {
        "output": """# 页面设计
## 组件要求
- 使用 `Modal`
- 使用 `JDictSelectTag`
"""
    }
    files = {
        "src/views/activityManage/ActivityManageList.vue": (
            "<template><div>活动列表</div></template>"
            "<script>export default { data () { return { list: [] } } }</script>"
        )
    }

    fixed, fixes = _auto_fix_frontend_preview_code_files(files, page_design_stage=page_design_stage)
    content = fixed["src/views/activityManage/ActivityManageList.vue"]

    assert any("项目组件引用" in fix for fix in fixes)
    assert "__previewHiddenModalVisible" not in content
    assert ':visible="false"' in content


def test_requirement_parser_keeps_plain_markdown_and_quality_json():
    raw = """# 项目概述
业务目标：提升后台用户管理效率。

## 功能需求
- P0 用户列表

## 角色与权限矩阵
- 管理员：页面权限、按钮权限

## 数据对象与字段
- username，string，必填，唯一校验

## 验收标准
- QA 可以按条件搜索用户

```json
{
  "pm_quality": {
    "score": 88,
    "ready_for_review": true,
    "missing_items": [],
    "review_focus": ["权限矩阵", "字段校验"],
    "primary_pages": ["用户列表"],
    "permission_points": ["user:list"],
    "data_entities": ["User"],
    "acceptance_criteria": ["可以搜索用户"]
  }
}
```
"""

    parsed = _parse_agent_output("requirement", raw)

    assert parsed["prd_document"].startswith("# 项目概述")
    assert "```json" not in parsed["prd_document"]
    assert parsed["pm_quality"]["score"] == 88
    assert parsed["pm_quality"]["ready_for_review"] is True
    assert parsed["pm_quality"]["permission_points"] == ["user:list"]


def test_prototype_prompt_requires_all_primary_pages_from_page_design():
    page_design_stage = {
        "structured_output": {
            "design_quality": {
                "primary_pages": [
                    "拼团活动列表页",
                    "秒杀活动列表页",
                    "活动审核列表页",
                ]
            }
        },
        "output": "# 页面设计",
    }

    focus = _prototype_focus_from_page_design(page_design_stage)

    assert "页面设计包含 3 个主页面" in focus
    assert "拼团活动列表页" in focus
    assert "秒杀活动列表页" in focus
    assert "每个主页面都要有对应的真实前端页面文件" in focus


def test_prototype_prompt_includes_locked_page_scope():
    prompt = _build_pipeline_prompt(
        "prototype",
        {
            "user_request": "新增拼团秒杀活动管理",
            "stage_outputs": {
                "requirement": {"output": "需求"},
                "page_design": {
                    "output": "页面设计",
                    "structured_output": {
                        "design_quality": {
                            "primary_pages": ["拼团活动列表页", "秒杀活动列表页"]
                        }
                    },
                },
            },
            "frontend_tech": "vue2",
        },
    )

    assert "## 本次预览页面范围" in prompt
    assert "页面设计包含 2 个主页面" in prompt
    assert "必须覆盖这些主页面" in prompt
    assert "禁止只生成其中 1 个页面" in prompt


def test_prototype_validation_fails_when_primary_pages_are_missing():
    issues = _validate_frontend_preview_code_files(
        {
            "src/views/Marketing/GroupBuyList.vue": "<template><div>拼团活动</div></template>",
            "src/api/marketing.js": "export function list () { return Promise.resolve({ list: [], page: 1, count: 0 }) }",
        },
        user_request="我想在商品管理平台做拼团和秒杀活动",
        expected_pages=["拼团活动列表页", "秒杀活动列表页"],
    )

    assert any("只生成了 1 个页面文件" in issue for issue in issues)


def test_prototype_validation_extracts_primary_pages_from_design_document():
    page_design_stage = {
        "output": """# 营销活动管理页面设计

## 1. 页面清单及层级关系
| 页面名称 | 路由 Path | 组件路径 |
| --- | --- | --- |
| 活动列表 | `/activity/list` | `src/views/activityManage/ActivityManageList.vue` |
| 活动编辑/新增 | `/activity/edit` | `src/views/activityManage/ActivityManageEdit.vue` |
| 活动详情 | `/activity/detail` | `src/views/activityManage/ActivityManageDetail.vue` |
"""
    }

    focus = _prototype_focus_from_page_design(page_design_stage)
    issues = _validate_frontend_preview_code_files(
        {
            "src/views/activityManage/ActivityManageList.vue": "<template><div>活动列表</div></template>",
            "src/api/activityManage.js": "export function getActivityList () { return Promise.resolve({ result: { list: [], page: 1, count: 0 } }) }",
        },
        user_request="我想在商品管理平台做拼团和秒杀活动",
        expected_pages=["活动列表", "活动编辑/新增", "活动详情"],
        page_design_stage=page_design_stage,
    )

    assert "页面设计包含 3 个主页面" in focus
    assert any("主页面组件路径未完整生成" in issue for issue in issues)
    assert any("ActivityManageEdit.vue" in issue for issue in issues)


def test_prototype_validation_accepts_group_buy_semantic_page_names_and_create_edit_action():
    page_design_stage = {
        "output": """# 拼团活动页面设计

## 页面清单
| 页面名称 | 路由 Path |
| --- | --- |
| 拼团活动列表 | `/activity/group/list` |
| 拼团活动创建/编辑 | `/activity/group/edit` |
| 拼团团单列表 | `/activity/group/team` |

## 按钮和操作
| 操作名称 | 触发入口 |
| --- | --- |
| 创建/编辑 | 列表新增、列表编辑 |
"""
    }

    issues = _validate_frontend_preview_code_files(
        {
            "src/views/groupActivity/GroupActivityList.vue": (
                "<template><div><a-button @click=\"handleAdd\">新增</a-button>"
                "<a @click=\"handleEdit\">编辑</a></div></template>"
                "<script>export default { methods: { handleAdd () {}, handleEdit () {} } }</script>"
            ),
            "src/views/groupActivity/GroupActivityEdit.vue": (
                "<template><div>商品SKU 团购价 活动库存 保存草稿 提交上线</div></template>"
                "<script>export default { name: 'GroupActivityEdit' }</script>"
            ),
            "src/views/groupActivity/GroupTeamList.vue": (
                "<template><div>拼团团单列表 团单ID 手动成团</div></template>"
                "<script>export default { name: 'GroupTeamList' }</script>"
            ),
        },
        user_request="做一个拼团/团购活动管理功能，这是新功能页面，不是现有页面加字段。",
        expected_pages=["拼团活动列表", "拼团活动创建/编辑", "拼团团单列表"],
        page_design_stage=page_design_stage,
    )

    assert not any("创建/编辑" in issue for issue in issues)
    assert not any("拼团团单列表" in issue for issue in issues)


def test_prototype_validation_blocks_flat_api_result_for_nested_project_contract():
    pipe_config = {
        "backend_project_skill_snapshot": {
            "skill_content": (
                "统一响应模型使用 ApiResult<T>，JSON 顶层结构必须为 "
                "{\"message\":{\"message\":\"ok\",\"code\":0},\"traceId\":\"\",\"data\":...}。"
                "message 是对象，内部包含 int code 和 string message。"
            )
        }
    }

    issues = _validate_frontend_preview_code_files(
        {
            "src/views/activityManage/ActivityManageList.vue": "<template><div>活动列表</div></template>",
            "src/api/activityManage.js": "export function updateActivityStatus () { return Promise.resolve({ code: 200, message: '操作成功' }) }",
        },
        user_request="新增活动管理页面",
        pipe_config=pipe_config,
    )

    assert any("扁平 code/message/msg 结构" in issue for issue in issues)
    assert any("ApiResult" in issue for issue in issues)


def test_prototype_validation_checks_page_design_contract_coverage():
    page_design_stage = {
        "output": """# 活动管理页面设计

## 3. 查询与筛选
- 活动类型和活动状态必须使用 `JDictSelectTag`。
- 活动时间范围拆分为 `startTime` 和 `endTime`。

## 5. 按钮和操作
| 按钮名称 | 权限Key |
| --- | --- |
| 新增 | `activity:add` |
| 编辑 | `activity:edit` |

## 9. API 契约草案
- 保存活动：`POST /api/activity/save`
- 活动详情查询：`GET /api/activity/detail/{activityId}`
"""
    }

    issues = _validate_frontend_preview_code_files(
        {
            "src/views/activityManage/ActivityManageList.vue": (
                "<template><div>"
                "<a-range-picker v-model=\"queryParam.activityTime\" />"
                "<a-select v-model=\"queryParam.activityType\" />"
                "<a-button @click=\"handleEdit\">编辑</a-button>"
                "</div></template><script>export default { data () { return { queryParam: { activityTime: [] } } }, methods: { handleEdit () {} } }</script>"
            ),
            "src/api/activityManage.js": "export function getActivityList () { return Promise.resolve({ result: { list: [], page: 1, count: 0 } }) }",
        },
        user_request="新增活动管理页面",
        page_design_stage=page_design_stage,
    )

    assert any("/api/activity/save" in issue for issue in issues)
    assert any("/api/activity/detail" in issue for issue in issues)
    assert any("未体现 v-action" in issue for issue in issues)
    assert any("JDictSelectTag" in issue for issue in issues)
    assert any("startTime/endTime" in issue for issue in issues)


def test_prototype_validation_does_not_false_positive_generated_activity_pages():
    page_design_stage = {
        "output": """# 页面设计

## 1. 页面清单
| 页面名称 | 路由 | 组件路径 |
| --- | --- | --- |
| 拼团活动列表页 | `/marketing/activity-group-list` | `src/views/activityManage/GroupBuyList.vue` |
| 秒杀活动列表页 | `/marketing/activity-flash-list` | `src/views/activityManage/FlashSaleList.vue` |

## 3. 查询与筛选
- 活动状态必须使用 `JDictSelectTag`。
- 活动时间范围拆分为 `startTime` 和 `endTime`。
"""
    }
    group_page = """<template>
  <s-table ref="table" :data="loadData"></s-table>
</template>
<script>
export default {
  data () {
    return {
      queryParam: {},
      loadData: parameter => {
        const params = { ...parameter, ...this.queryParam, activityType: 1 }
        if (params.validTime && params.validTime.length === 2) {
          params.startTime = params.validTime[0].format('YYYY-MM-DD HH:mm')
          params.endTime = params.validTime[1].format('YYYY-MM-DD HH:mm')
          delete params.validTime
        }
        return getActivityListMock(params).then(res => {
          const list = Array.isArray(res.list) ? res.list : []
          return { ...res, list: list }
        })
      }
    }
  }
}
</script>"""
    flash_page = group_page.replace("activityType: 1", "activityType: 2")

    issues = _validate_frontend_preview_code_files(
        {
            "src/views/activityManage/GroupBuyList.vue": group_page,
            "src/views/activityManage/FlashSaleList.vue": flash_page,
            "src/api/activityManage.js": "function buildPageResult () { return { list: [], page: 1, count: 0, pageNo: 1, totalCount: 0 } }",
        },
        user_request="我想在商品管理平台做拼团和秒杀活动",
        expected_pages=["拼团活动列表页", "秒杀活动列表页"],
        page_design_stage=page_design_stage,
    )

    assert not any("没有对应的前端页面文件" in issue for issue in issues)
    assert not any("分页字段 page" in issue for issue in issues)
    assert not any("分页字段 count" in issue for issue in issues)
    assert not any("startTime/endTime" in issue for issue in issues)
    assert any("JDictSelectTag" in issue for issue in issues)


def test_new_page_validation_requires_mock_fallback_for_real_request_api():
    issues = _validate_frontend_preview_code_files(
        {
            "src/views/Marketing/GroupBuyList.vue": "<template><s-table :data=\"loadData\" /></template><script>export default { data () { return { loadData: () => getList().then(res => ({ page: 1, count: 0, list: [] })) } } }</script>",
            "src/api/marketing.js": "import request from '@/utils/request'\nexport function getList () { return request({ url: '/marketing/list', method: 'get' }) }",
        },
        user_request="新增拼团活动管理页面",
        expected_pages=["拼团活动列表页"],
    )

    assert any("缺少 mock/fallback 数据" in issue for issue in issues)


def test_parse_agent_output_extracts_valid_json_file_array_after_bad_prefix():
    raw_output = """```json
[{ "path": "broken", "content": "unterminated }
```
```json
[
  {
    "path": "src/api/groupActivity.js",
    "content": "export function getList () { return Promise.resolve({ list: [] }) }"
  },
  {
    "path": "src/views/activityManage/ActivityGroupList.vue",
    "content": "<template><s-table :data=\\"loadData\\" /></template><script>export default { data () { return { loadData: () => Promise.resolve({ list: [], page: 1, count: 0 }) } } }</script>"
  }
]
```"""

    parsed = _parse_agent_output("prototype", raw_output)

    assert sorted(parsed["code_files"]) == [
        "src/api/groupActivity.js",
        "src/views/activityManage/ActivityGroupList.vue",
    ]


def test_product_prototype_prompt_injects_real_frontend_preview_skill():
    prompt = _build_pipeline_prompt(
        "prototype",
        {
            "pipeline_mode": "frontend_contract_review",
            "user_request": "在现有商品列表增加商品ID筛选项",
            "stage_outputs": {
                "requirement": {"output": "需求"},
                "page_design": {"output": "页面设计"},
            },
            "frontend_tech": "vue2",
        },
    )

    assert "## Real Frontend Preview Skill Contract" in prompt
    assert "Existing-Page Changes" in prompt
    assert "Only new or changed fields may use mock examples" in prompt
    assert "New pages must include mock data" in prompt
    assert "If no confirmed path exists, output `[]`" in prompt
    assert "## Backoffice Page Scaffold Skill Contract" in prompt
    assert "List Page Contract" in prompt
    assert "Detail Page Contract" in prompt
    assert "Create/Edit Contract" in prompt
    assert "Selector Modal Contract" in prompt
    assert "Every required action must have a visible control and a defined handler" in prompt


def test_requirement_parser_keeps_permission_model_fields():
    raw = """# 项目概述
业务目标：提升后台权限配置效率。

## 功能需求
- P0 角色授权

## 角色与权限矩阵
- 运营主管：订单导出

## 权限模型与策略样例
- RBAC: subject=运营主管, resource=order, action=export
- ABAC: condition=同租户且同部门数据

## 数据范围与条件权限
- 租户隔离、部门数据、本人/下级数据

## 数据对象与字段
- role_id，number，必填

## 页面/业务状态
- 无权限、空数据、加载中、异常

## 验收标准
- QA 可以验证无权限按钮禁用

## 假设与待确认问题
- 权限 key 命名待确认

```json
{
  "pm_quality": {
    "score": 96,
    "ready_for_review": true,
    "permission_model": ["RBAC subject/role/resource/action", "ABAC tenant/department condition"],
    "data_scope_rules": ["同租户", "同部门"],
    "policy_examples": ["role=运营主管, resource=order, action=export, condition=同部门数据"]
  }
}
```
"""

    parsed = _parse_agent_output("requirement", raw)

    assert parsed["pm_quality"]["permission_model"] == [
        "RBAC subject/role/resource/action",
        "ABAC tenant/department condition",
    ]
    assert parsed["pm_quality"]["data_scope_rules"] == ["同租户", "同部门"]
    assert "condition=同部门数据" in parsed["pm_quality"]["policy_examples"][0]


def test_requirement_parser_scores_missing_items_without_quality_json():
    raw = """# 项目概述
目标用户：运营管理员

## 功能清单
- P0 列表查询

## 验收标准
- 查询条件为空时展示全部数据
"""

    parsed = _parse_agent_output("requirement", raw)

    assert parsed["prd_document"] == raw.strip()
    assert parsed["pm_quality"]["score"] < 80
    assert "角色与权限矩阵" in parsed["pm_quality"]["missing_items"]
    assert "数据对象与字段" in parsed["pm_quality"]["missing_items"]


def test_page_design_parser_adds_design_quality_fallback():
    raw = """# 页面列表
- 用户列表，路由 /users

## 字段定义
- username，必填，长度 2-20

## 按钮和操作
- 新增、编辑、删除、导出

## 搜索/筛选条件
- 用户名、状态

## 弹窗交互
- 新增弹窗、编辑弹窗、删除二次确认

## 页面状态
- 空数据、加载中、无权限、搜索无结果、异常

## 权限控制点
- 菜单权限、页面权限、按钮权限、数据范围权限、API 权限
- RBAC: subject=运营, resource=user, action=edit；ABAC: condition=同租户
- permission key: user:edit；无权限提示、禁用、隐藏、审计

## 开发确认要点
- wealth-admin-home 入口和接口路径待确认
"""

    parsed = _parse_agent_output("page_design", raw)

    assert parsed["page_design_document"] == raw.strip()
    assert parsed["design_quality"]["score"] == 100
    assert parsed["design_quality"]["ready_for_review"] is True


def test_pm_prompt_contract_is_appended_to_default_and_custom_prompts():
    context = {
        "user_request": "生成 wealth-admin-home 用户权限页面",
        "stage_outputs": {},
    }

    default_prompt = _build_pipeline_prompt("requirement", context)
    custom_prompt = _build_pipeline_prompt(
        "requirement",
        context,
        custom_prompts={"requirement": "只处理：{{user_request}}"},
    )

    assert '"pm_quality"' in default_prompt
    assert "角色与权限矩阵" in default_prompt
    assert "RBAC" in default_prompt
    assert "ABAC" in default_prompt
    assert "resource=order" in default_prompt
    assert "数据范围" in default_prompt
    assert '"pm_quality"' in custom_prompt
    assert "生成 wealth-admin-home 用户权限页面" in custom_prompt


def test_page_design_prompt_requires_permission_policy_details():
    context = {
        "user_request": "生成 wealth-admin-home 订单管理页面",
        "stage_outputs": {
            "requirement": {
                "output": "需要订单列表、导出和角色授权。",
            },
        },
    }

    prompt = _build_pipeline_prompt("page_design", context)

    assert '"design_quality"' in prompt
    assert "API 权限" in prompt
    assert "permission key" in prompt
    assert "禁用/隐藏/无权限提示" in prompt
    assert "RBAC" in prompt
    assert "ABAC" in prompt


def test_code_review_prompt_requires_real_frontend_api_contract_alignment():
    context = {
        "user_request": "生成商品详情页面",
        "pipeline_mode": "frontend_contract_review",
        "stage_outputs": {
            "requirement": {"output": "商品详情需要展示 productId、productName、price。"},
            "page_design": {"output": "详情字段：productId、productName、price；接口 /product/detail。"},
            "prototype": {
                "output": '[{"path":"src/views/Product/Detail.vue","content":"读取 productName"}]',
            },
            "delivery": {"output": "GET /product/detail 响应 data.productName。"},
        },
    }

    prompt = _build_pipeline_prompt("code_review", context)

    assert "真实前端代码" in prompt
    assert "API 契约对齐" in prompt
    assert "字段一致性" in prompt
    assert "frontend_field" in prompt
    assert "contract_field" in prompt
    assert "Mock 与真实契约一致性" in prompt
    assert "小程序" in prompt
    assert "前端读取的响应字段与 API 契约不一致" in prompt
    assert "`queryParam.id`、`params.id`、`parameter.id` 与 API 契约请求参数 `id` 是同一字段" in prompt


def test_code_review_prompt_uses_file_manifest_instead_of_code_body():
    context = {
        "user_request": "给列表增加商品ID筛选",
        "pipeline_mode": "frontend_contract_review",
        "workspace_path": "/tmp/pipelines/pipe-001",
        "stage_outputs": {
            "prototype": {
                "output": "<template>截断内容",
                "code_files": {
                    "src/views/List.vue": "<template></template>\n<script>\nexport default { data () { return { productIdValidateStatus: '', productIdHelp: '' } }, methods: { searchQuery () {}, searchReset () {} } }\n</script>",
                },
            },
            "delivery": {"output": "请求参数 id"},
        },
    }

    prompt = _build_pipeline_prompt("code_review", context)

    assert "真实生成文件清单，不包含文件正文" in prompt
    assert "workspace_path: /tmp/pipelines/pipe-001" in prompt
    assert "`src/views/List.vue`" in prompt
    assert "productIdValidateStatus" in prompt
    assert "searchReset" in prompt
    assert "export default" not in prompt
    assert "通过文件搜索/文件读取能力查看真实文件内容" in prompt


def test_global_prompt_requires_file_skills_and_context_compression():
    prompt = _build_pipeline_prompt("code_review", {
        "pipeline_mode": "frontend_contract_review",
        "stage_outputs": {},
    })

    assert "优先按 workspace_path 和相对路径使用文件搜索/文件读取 skill" in prompt
    assert "多轮修复边界" in prompt
    assert "防止上下文膨胀造成误判" in prompt


def test_fix_feedback_is_compressed_for_multi_round_regeneration():
    feedback = "\n".join([
        "普通长日志 " + ("x" * 2000),
        "审查结论：字段需要对齐",
        "critical src/views/List.vue 当前: queryParam.productCode 应为: queryParam.id",
        "修复建议：只修目标路径",
    ])

    compacted = _compact_fix_feedback(feedback, limit=220)

    assert len(compacted) < len(feedback)
    assert "审查结论" in compacted
    assert "critical" in compacted
    assert "fix feedback compressed" in compacted


def test_code_review_parser_treats_query_param_prefix_as_same_contract_field():
    raw = """自动审查未通过，需要先调整。

```json
{
  "review_passed": false,
  "backend_score": "A",
  "frontend_score": "B",
  "contract_alignment": "前端 queryParam.id 与 API 契约请求参数 id 字段名不一致",
  "field_mismatches": [
    {
      "severity": "major",
      "location": "src/views/selfOperateCommodity/commodityList/List.vue",
      "frontend_field": "queryParam.id",
      "contract_field": "id",
      "fix": "改成 id"
    }
  ],
  "fix_suggestions": "调整字段名"
}
```"""

    parsed = _parse_agent_output("code_review", raw)

    assert parsed["review_passed"] is True
    assert parsed["field_mismatches"] == []
    assert parsed["fix_suggestions"] == ""
    assert "无字段名不一致问题" in parsed["contract_alignment"]


def test_deterministic_code_review_fallback_passes_generated_group_buy_files():
    stages = {
        "page_design": {
            "output": """# 拼团活动页面设计
| 页面名称 | 路由 Path |
| --- | --- |
| 拼团活动列表 | `/activity/group/list` |
| 拼团活动创建/编辑 | `/activity/group/edit` |
| 拼团团单列表 | `/activity/group/team/list` |

## 按钮和操作
| 操作名称 | 触发入口 |
| --- | --- |
| 创建/编辑 | 列表新增、列表编辑 |
"""
        },
        "prototype": {
            "code_files": {
                "src/api/groupActivity.js": (
                    "export function getActivityList(parameter) { "
                    "const list = []; return Promise.resolve({ list: list.slice(0, parameter.pageSize), page: 1, count: list.length }) }"
                ),
                "src/views/activityGroup/ActivityGroupList.vue": (
                    "<template><s-table :data=\"loadData\"><a-button @click=\"handleCreate\">新增</a-button>"
                    "<a @click=\"handleEdit\">编辑</a><a @click=\"handleExport\">导出</a></s-table></template>"
                    "<script>export default { methods: { loadData (parameter) { return getActivityList(parameter).then(res => { "
                    "return { list: Array.isArray(res.list) ? res.list : [], page: res.page || 1, count: res.count || 0 } }) }, "
                    "handleCreate () {}, handleEdit () {}, handleExport () {} } }</script>"
                ),
                "src/views/activityGroup/ActivityGroupEdit.vue": (
                    "<template><div>商品SKU 团购价 活动库存 成团人数 保存草稿 提交上线</div></template>"
                    "<script>export default { name: 'ActivityGroupEdit' }</script>"
                ),
                "src/views/activityGroup/ActivityGroupTeamList.vue": (
                    "<template><div>拼团团单列表 团单ID 手动成团</div></template>"
                    "<script>export default { name: 'ActivityGroupTeamList' }</script>"
                ),
            }
        },
    }

    output, parsed = _build_deterministic_code_review_result(
        stages,
        user_request="做一个拼团/团购活动管理功能，这是新功能页面，不是现有页面加字段。",
    )

    assert parsed["review_passed"] is True
    assert parsed["deterministic_fallback"] is True
    assert "自动代码审查兜底报告" in output
    assert "ActivityGroupTeamList.vue" in output


def test_code_review_parser_keeps_failure_when_non_field_issue_remains():
    raw = """```json
{
  "review_passed": false,
  "contract_alignment": "前端 queryParam.id 与 API 契约请求参数 id 字段名不一致",
  "field_mismatches": [
    {
      "severity": "major",
      "location": "src/views/List.vue",
      "frontend_field": "queryParam.id",
      "contract_field": "id",
      "fix": "改成 id"
    }
  ],
  "fix_suggestions": "缺少加载态和接口异常兜底，运行失败时页面没有提示。"
}
```"""

    parsed = _parse_agent_output("code_review", raw)

    assert parsed["review_passed"] is False
    assert parsed["field_mismatches"] == []
    assert "加载态" in parsed["fix_suggestions"]
    assert "无字段名不一致问题" in parsed["contract_alignment"]


def test_code_review_parser_normalizes_field_aliases():
    raw = """```json
{
  "review_passed": false,
  "contract_alignment": "前端 current_field 与 API 字段不一致",
  "field_mismatches": [
    {
      "severity": "major",
      "location": "src/views/List.vue",
      "current_field": "queryParam.id",
      "api_field": "id",
      "fix": "改成 id"
    }
  ],
  "fix_suggestions": "调整字段名"
}
```"""

    parsed = _parse_agent_output("code_review", raw)

    assert parsed["review_passed"] is True
    assert parsed["field_mismatches"] == []
    assert parsed["fix_suggestions"] == ""


def test_preview_parser_scores_complete_admin_preview():
    raw = """```html
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8" />
<style>
body { margin: 0; font-family: Arial, sans-serif; }
.layout { display: flex; min-height: 100vh; }
.side { width: 220px; background: #0f172a; color: white; }
.content { flex: 1; padding: 24px; }
.ant-table { width: 100%; border-collapse: collapse; }
.ant-modal { display: none; }
</style>
</head>
<body data-preview-ready="true">
<div id="preview-root" class="layout">
  <aside class="side">菜单 导航 工作台 菜单权限 页面权限</aside>
  <main class="content">
    <h1>订单管理工作台</h1>
    <section><input class="ant-input" placeholder="搜索订单" /><button class="ant-btn">查询</button><button class="ant-btn" disabled>无权限导出</button><span>按钮权限 disabled，数据范围：同部门</span></section>
    <table class="ant-table">
      <tr><th>订单号</th><th>客户</th><th>状态</th></tr>
      <tr><td>O-001</td><td>张三</td><td>待处理</td></tr>
      <tr><td>O-002</td><td>李四</td><td>已完成</td></tr>
      <tr><td>O-003</td><td>王五</td><td>异常</td></tr>
      <tr><td>O-004</td><td>赵六</td><td>加载完成</td></tr>
    </table>
    <div class="ant-modal">编辑弹窗 确认 删除</div>
    <div>无权限：请联系管理员</div>
    <div>空数据：暂无数据</div>
    <div>加载中...</div>
    <div>接口异常，请重试</div>
  </main>
</div>
</body>
</html>
```"""

    parsed = _parse_agent_output("prototype", raw)

    assert parsed["preview_quality"]["ready_for_preview"] is True
    assert parsed["preview_quality"]["score"] >= 80
    assert "权限呈现" in parsed["preview_quality"]["passed_checks"]


def test_preview_parser_flags_truncated_preview():
    raw = """```html
<html><body><div>只有一个占位预览
"""

    parsed = _parse_agent_output("prototype", raw)

    assert parsed["preview_quality"]["ready_for_preview"] is False
    assert parsed["preview_quality"]["score"] < 80
    assert any("截断" in item or "过短" in item for item in parsed["preview_quality"]["issues"])
