"""流水线共享纯函数：前端页面路径 / 需求类型启发式判定。

被 flow_manager 与 pipeline_project_context（及其它后续拆出的校验模块）共同复用，
独立成模块以避免循环 import。全部为纯函数（仅依赖 re + typing）。
"""
import re
from typing import Any, List, Optional


def _has_new_page_structure_signal(text: str) -> bool:
    """检测需求文本是否含新页面结构信号（路由/菜单/落点等）且未提及「现有」。"""
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
    """启发式判定：需求是改造现有页面/功能（而非全新页面）。

    驱动 prototype 校验：现有功能改造必须改原页面路径、保留原接口/查询/表格列，
    不得另起 mock 或新建替代页面。
    """
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


def _is_frontend_page_path(path: str) -> bool:
    """判断路径是否为可预览的前端页面文件（views/pages 下 + vue/tsx/jsx/wxml）。"""
    return (
        path.startswith(("src/views/", "src/pages/", "pages/"))
        and path.endswith((".vue", ".tsx", ".jsx", ".wxml"))
    )


def _coerce_string_list(value: Any, fallback: Optional[List[str]] = None) -> List[str]:
    """把 LLM 输出的字符串/列表/null 统一规整成字符串列表（处理中英文分号/换行）。"""
    """Normalize LLM quality fields that may arrive as strings, lists, or nulls."""
    if value is None:
        return fallback or []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        parts = [part.strip(" -\t") for part in value.replace("；", "\n").replace(";", "\n").split("\n")]
        return [part for part in parts if part]
    return fallback or []
