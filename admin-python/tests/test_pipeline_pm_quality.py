from app.ai.flow_manager import _build_pipeline_prompt, _parse_agent_output


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
