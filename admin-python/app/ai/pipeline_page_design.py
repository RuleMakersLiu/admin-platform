"""页面设计解析：从 page_design 产物/文档抽取期望页面路径、组件、API 端点需求。

从 flow_manager 拆出。全部为纯函数（仅 re + typing + helpers 的 _coerce_string_list），
被 _parse_agent_output / 校验逻辑 / prototype_focus 共同复用。
"""
import re
from typing import Any, Dict, List, Optional

from app.ai.pipeline_helpers import (
    _is_frontend_page_path,
    _has_new_page_structure_signal,
    _is_existing_feature_change_request,
    _coerce_string_list,
)


def _is_new_feature_page_request(user_request: str) -> bool:
    """启发式判定：需求是新建页面/功能（驱动 mock 范围校验，全新页必须有 mock 兜底）。"""
    text = (user_request or "").strip()
    if not text or _is_existing_feature_change_request(text):
        return False
    if _has_new_page_structure_signal(text):
        return True
    return bool(re.search(r"(?:新增|新建|创建|搭建|生成|做一个|开发一个).*(?:页面|列表|详情|表单|管理|功能|工作台|看板)", text))


def _is_known_support_page_name(name: str) -> bool:
    return bool(re.search(r"(弹窗|抽屉|modal|drawer|dialog)", name or "", re.I))


def _page_name_tokens(name: str) -> List[str]:
    original = re.sub(r"[`'\"""『』（）()\[\]【】]", "", name or "")
    text = original
    text = re.sub(r"(页面|页|列表|详情|表单|管理|配置|审核|创建|新建|编辑)", " ", text)
    tokens = [
        token.strip().lower()
        for token in re.split(r"[^A-Za-z0-9\u4e00-\u9fff]+", text)
        if token.strip()
    ]
    semantic_tokens: List[str] = []
    semantic_map = {
        "首页": ["index", "home", "main"],
        "主页": ["index", "home", "main"],
        "钱包": ["wallet"],
        "交易": ["transaction", "trade"],
        "明细": ["detail", "record", "transaction"],
        "流水": ["record", "transaction"],
        "充值": ["recharge"],
        "提现": ["withdraw"],
        "拼团": ["group"],
        "团购": ["group"],
        "团单": ["团单", "team", "groupteam", "order"],
        "活动": ["activity"],
        "创建": ["create", "edit", "form"],
        "新建": ["create", "edit", "form"],
        "编辑": ["edit", "form"],
        "详情": ["detail"],
        "列表": ["list"],
    }
    for keyword, aliases in semantic_map.items():
        if keyword in original:
            semantic_tokens.extend(aliases)
    result: List[str] = []
    seen = set()
    for token in [*tokens, *semantic_tokens]:
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def _expected_prototype_pages_from_page_design(page_design_stage: Dict[str, Any]) -> List[str]:
    """从页面设计阶段产物抽取期望的主页面清单（供 prototype 校验覆盖完整性）。"""
    if not isinstance(page_design_stage, dict):
        return []
    structured = page_design_stage.get("structured_output")
    if not isinstance(structured, dict):
        structured = page_design_stage
    design_quality = structured.get("design_quality") if isinstance(structured, dict) else None
    primary_pages = _coerce_string_list(
        design_quality.get("primary_pages") if isinstance(design_quality, dict) else None,
        [],
    )
    if not primary_pages:
        document = str(page_design_stage.get("page_design_document") or page_design_stage.get("output") or "")
        if not document and isinstance(structured, dict):
            document = str(structured.get("page_design_document") or structured.get("output") or "")
        primary_pages = _extract_primary_pages_from_page_design_document(document)
    return [
        page
        for page in primary_pages
        if page and not _is_known_support_page_name(page)
    ][:8]


def _extract_primary_pages_from_page_design_document(document: str) -> List[str]:
    """从 markdown 设计文档抽取主页面名（优先读表格，fallback 解析标题/表格首列）。"""
    if not document:
        return []
    table_pages = _primary_pages_from_page_design_table(document)
    if table_pages:
        return table_pages
    pages: List[str] = []
    seen = set()

    def add_page(name: str) -> None:
        cleaned = re.sub(r"[`*#]+", "", name or "").strip()
        cleaned = re.sub(r"^\d+(?:\.\d+)*\s*", "", cleaned).strip()
        cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", cleaned).strip()
        if (
            not cleaned
            or cleaned in seen
            or _is_known_support_page_name(cleaned)
            or any(skip in cleaned for skip in ("页面清单", "页面布局", "字段定义", "查询与筛选", "按钮和操作", "页面状态", "权限控制", "API 契约", "开发确认"))
        ):
            return
        if any(keyword in cleaned for keyword in ("页", "列表", "详情", "表单", "编辑", "新增", "创建", "管理")):
            seen.add(cleaned)
            pages.append(cleaned)

    for line in document.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        table_match = re.match(r"^\|\s*([^|]+?)\s*\|", stripped)
        if table_match and "|" in stripped:
            first_cell = table_match.group(1).strip()
            if first_cell not in {"页面名称", "---", "页面/组件", "资源", "按钮名称", "展示名"}:
                add_page(first_cell)
        heading_match = re.match(r"^#{2,4}\s+(.+)$", stripped)
        if heading_match:
            add_page(heading_match.group(1))
        if len(pages) >= 8:
            break
    return pages


def _markdown_table_rows(document: str) -> List[Dict[str, str]]:
    """把 markdown 表格解析成 dict 行列表（按表头做 key）。"""
    rows: List[Dict[str, str]] = []
    headers: List[str] = []
    for line in (document or "").splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and "|" in stripped[1:]):
            headers = []
            continue
        cells = [cell.strip().strip("`") for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        if not headers:
            headers = cells
            continue
        if all(re.fullmatch(r":?-{2,}:?", cell or "") for cell in cells):
            continue
        if len(cells) < len(headers):
            cells.extend([""] * (len(headers) - len(cells)))
        rows.append({headers[index]: cells[index] for index in range(min(len(headers), len(cells)))})
    return rows


def _is_support_page_design_row(row: Dict[str, str]) -> bool:
    name = str(row.get("页面名称") or row.get("页面/组件") or "").strip()
    menu = str(row.get("菜单层级") or row.get("层级") or "").strip()
    route = str(row.get("路由路径") or row.get("路由 Path") or row.get("路由") or "").strip()
    default_landing = str(row.get("默认落点") or "").strip()
    text = f"{name} {menu} {route} {default_landing}"
    if re.search(r"页面内弹窗|通用弹窗|弹窗|抽屉|Modal|Drawer|选择器|组件", text, re.I):
        return True
    if route in {"", "-", "—"} and default_landing in {"", "-", "—"} and re.search(r"新增|编辑|新建|创建|选择", name):
        return True
    return False


def _is_primary_page_design_row(row: Dict[str, str]) -> bool:
    name = str(row.get("页面名称") or row.get("页面/组件") or "").strip()
    if not name or name in {"页面名称", "---", ":---"}:
        return False
    if _is_support_page_design_row(row):
        return False
    route = str(row.get("路由路径") or row.get("路由 Path") or row.get("路由") or "").strip()
    menu = str(row.get("菜单层级") or row.get("层级") or "").strip()
    default_landing = str(row.get("默认落点") or "").strip()
    if route and route not in {"-", "—"}:
        return True
    if menu and not re.search(r"弹窗|组件|通用", menu):
        return True
    if default_landing and default_landing not in {"-", "—"}:
        return True
    return False


def _primary_pages_from_page_design_table(document: str) -> List[str]:
    pages: List[str] = []
    seen = set()
    for row in _markdown_table_rows(document):
        if "页面名称" not in row and "页面/组件" not in row:
            continue
        if not _is_primary_page_design_row(row):
            continue
        name = str(row.get("页面名称") or row.get("页面/组件") or "").strip()
        if name and name not in seen:
            seen.add(name)
            pages.append(name)
    return pages[:8]


def _expected_page_paths_from_page_design_document(document: str) -> Dict[str, List[str]]:
    """从设计文档表格抽取「主页面 → 组件路径」映射（路径锁定用于校验生成文件）。"""
    if not document:
        return {}
    page_paths: Dict[str, List[str]] = {}
    for line in document.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and "|" in stripped):
            continue
        cells = [cell.strip().strip("`") for cell in stripped.strip("|").split("|")]
        if not cells or cells[0] in {"页面名称", "---", "页面/组件"}:
            continue
        paths = [
            _normalize_frontend_component_path(path)
            for path in re.findall(r"(?:@/)?(?:src/)?(?:pages|views|components)/[A-Za-z0-9_./-]+\.(?:vue|tsx|jsx|wxml)", stripped)
        ]
        if not paths:
            continue
        page_paths.setdefault(cells[0], [])
        for path in paths:
            if path not in page_paths[cells[0]]:
                page_paths[cells[0]].append(path)
    return page_paths


def _normalize_frontend_component_path(path: str) -> str:
    """归一化前端组件路径：去 @/ 前缀、补 src/、统一正斜杠。"""
    normalized = str(path or "").replace("\\", "/").strip().strip("`").lstrip("/")
    if normalized.startswith("@/"):
        normalized = normalized[2:]
    if normalized.startswith("views/"):
        normalized = "src/" + normalized
    if normalized.startswith("components/"):
        normalized = "src/" + normalized
    return normalized.lstrip("/")


def _expected_page_paths_from_page_design_stage(page_design_stage: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    if not isinstance(page_design_stage, dict):
        return {}
    structured = page_design_stage.get("structured_output")
    document = str(page_design_stage.get("page_design_document") or page_design_stage.get("output") or "")
    if not document and isinstance(structured, dict):
        document = str(structured.get("page_design_document") or structured.get("output") or "")
    return _expected_page_paths_from_page_design_document(document)


def _declared_frontend_paths_from_page_design_stage(page_design_stage: Optional[Dict[str, Any]]) -> List[str]:
    page_paths = _expected_page_paths_from_page_design_stage(page_design_stage)
    paths: List[str] = []
    seen = set()
    for declared_paths in page_paths.values():
        for path in declared_paths:
            normalized = _normalize_frontend_component_path(path)
            if normalized and normalized not in seen:
                seen.add(normalized)
                paths.append(normalized)
    return paths
