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
- 菜单权限、页面权限、按钮权限、数据范围权限

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
    assert '"pm_quality"' in custom_prompt
    assert "生成 wealth-admin-home 用户权限页面" in custom_prompt
