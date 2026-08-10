"""质量审查契约 + 评审关卡标准。"""

from typing import Dict, List

REVIEW_GATE_PASS_SCORE = 60

REVIEW_GATE_CRITERIA: Dict[str, List[str]] = {
    "requirement": [
        "需求描述清晰、可执行，无歧义",
        "覆盖了用户提出的核心功能点",
        "无明显矛盾、遗漏或不合理假设"
    ],
    "delivery": [
        "API 契约完整：每个接口含路径、方法、请求字段、响应字段",
        "前后端字段命名与类型对齐",
        "覆盖需求中的核心交互与数据流"
    ]
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
