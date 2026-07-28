"""E2E 期望元素派生（启发式，确定性，无 LLM）。

prototype 阶段 E2E 浏览器校验需要「页面应当包含哪些控件」的检查清单。这里按
需求/页面设计的关键词，派生一组可机器断言的期望（密码框、提交按钮、表格、表单输入等）。

设计取舍：
- v1 用启发式（关键词→期望），确定性、零额外 LLM 调用、不引入新失败面。
- 结构上每条期望是 ``{"label", "kind", ...}``，kind 限定为 ``password / table /
  has_input / button_text``，由 vision_eval_service.run_e2e_assertions 在真实 DOM 上断言。
- 富期望（LLM 从页面设计抽字段级清单）留作后续插口：派生函数返回 list[dict]，将来
  可叠加一个 async LLM 版本，调用方无须改动。
"""
import re
from typing import Any, Dict, List

__all__ = ["derive_e2e_expectations", "E2E_EXPECTATION_KINDS"]

E2E_EXPECTATION_KINDS = ("password", "table", "has_input", "button_text")


def _has(text: str, *patterns: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def derive_e2e_expectations(user_request: str, page_design_doc: str = "") -> List[Dict[str, Any]]:
    """从需求 + 页面设计派生 E2E 期望控件清单（启发式）。

    返回去重后的期望列表；识别不出页面类型时返回空列表（调用方仍会做渲染完整性检查）。
    """
    text = f"{user_request or ''}\n{page_design_doc or ''}"
    if not text.strip():
        return []

    exps: List[Dict[str, Any]] = []

    if _has(text, r"登录|登陆|login|sign\s*in"):
        exps.append({"label": "密码输入框", "kind": "password"})
        exps.append({"label": "登录提交按钮", "kind": "button_text",
                     "texts": ["登录", "登 录", "登陆", "Login", "确定", "Sign in"]})

    if _has(text, r"注册|register|sign\s*up"):
        exps.append({"label": "密码输入框", "kind": "password"})
        exps.append({"label": "注册提交按钮", "kind": "button_text",
                     "texts": ["注册", "Register", "Sign up", "提交", "确定"]})

    if _has(text, r"列表|表格|查询|管理|list|table|search"):
        exps.append({"label": "数据表格", "kind": "table"})
        exps.append({"label": "查询/搜索按钮", "kind": "button_text",
                     "texts": ["查询", "搜索", "Search", "筛选", "查找"]})

    if _has(text, r"新增|添加|创建|新建|add|create"):
        exps.append({"label": "新增按钮", "kind": "button_text",
                     "texts": ["新增", "添加", "创建", "新建", "New", "Add", "Create"]})

    # 表单/配置类页面（团购配置、商品、订单、设置等）→ 期望有表单输入 + 提交/保存按钮
    if _has(text, r"团购|商品|订单|表单|配置|设置|form|config|product|order|group\s*buy"):
        exps.append({"label": "表单输入控件", "kind": "has_input"})
        exps.append({"label": "提交/保存按钮", "kind": "button_text",
                     "texts": ["提交", "保存", "确定", "Submit", "Save", "保存"]})

    # 去重（同 kind+label）
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for e in exps:
        key = (e.get("kind"), e.get("label"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped
