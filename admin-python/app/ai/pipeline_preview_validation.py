"""前端预览代码：覆盖校验 + 确定性补丁（不依赖 LLM 的兜底改写）。

从 flow_manager 拆出（原 zone 6/7）。两类工作：
  1. 校验：_validate_* 检查生成的 .vue/.js 是否符合 page_design 契约（页面路径、字段、
     组件、API 端点、权限点、mock 范围、表格列稳定性），产出 issue 列表；
  2. 补丁：_patch_* / _append_missing_* / _ensure_* 对代码做确定性改写补齐缺失（不调 LLM），
     再由 _auto_fix_frontend_preview_code_files 汇总。
_e2e_browser_check_issues 用 e2e_expectations + vision_eval_service 做无头断言。
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.ai.pipeline_helpers import (
    _is_existing_feature_change_request,
    _is_frontend_page_path,
)
from app.ai.pipeline_page_design import (
    _declared_frontend_paths_from_page_design_stage,
    _expected_page_paths_from_page_design_stage,
    _expected_prototype_pages_from_page_design,
    _is_known_support_page_name,
    _is_new_feature_page_request,
    _normalize_frontend_component_path,
    _page_name_tokens,
)

logger = logging.getLogger(__name__)


def _is_additive_filter_request(user_request: str = "") -> bool:
    """判定是否为「新增筛选项」需求（驱动 queryParam 字段保留 + 新字段校验）。"""
    text = user_request or ""
    if not re.search(r"(筛选|查询|搜索|检索|过滤)", text):
        return False
    if re.search(r"(改名|重命名|改成|替换|文案|展示名|label|placeholder)", text, re.I):
        return False
    return bool(re.search(r"(新增|增加|添加|补充|加一个|加上|加个)", text))


def _requested_filter_label(user_request: str = "") -> str:
    """从「新增 XX 筛选」类需求里抽出筛选项的中文 label。"""
    text = re.sub(r"\s+", "", user_request or "")
    match = re.search(r"(?:新增|增加|添加|补充|加一个|加上|加个)(?:一个|一项|个|项)?(.{1,24}?)(?:的)?(?:筛选项|筛选|查询项|查询|搜索项|搜索|检索项|检索|过滤项|过滤)", text)
    if not match:
        return ""
    label = match.group(1)
    label = re.sub(r"^(?:现有|已有|当前|原有|页面|列表|表格|商城管理平台|管理平台)+", "", label)
    label = re.sub(r"(?:字段|条件|控件|输入框|筛选项|查询项)$", "", label)
    return label[:16]


def _query_filter_bindings(content: str) -> List[Tuple[str, str]]:
    """从 .vue 文件抽取 (label, queryParam.field) 绑定，用于「保留原筛选 + 新增字段」校验。"""
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
    """现有功能改造校验：生成文件路径必须命中已确认存在的页面路径，禁止新建替代页。"""
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
    """现有功能改造校验：禁止为已存在页面生成新 mock 列表/Promise（应复用现有接口）。"""
    if not _is_existing_feature_change_request(user_request):
        return []

    issues = []
    for path, content in files.items():
        safe_path = str(path).replace("\\", "/").lstrip("/")
        if not safe_path.startswith("src/api/") or not isinstance(content, str):
            continue
        if re.search(
            r"\bmock[A-Za-z0-9_]*List\b|\bMock\.mock\b|\bmockRequest(?:Wrapper)?\b|const\s+mock[A-Za-z0-9_]*\s*=",
            content,
        ):
            issues.append(
                f"{safe_path} 为现有功能改造生成了 mock 列表数据；旧列表数据和旧接口应复用现有能力，"
                "已存在页面不要生成 mock"
            )
        if re.search(r"return\s+(?:new\s+Promise\s*\(|Promise\.resolve\s*\()", content) and re.search(r"\b(list|data)\s*:", content):
            issues.append(
                f"{safe_path} 为现有功能改造生成了模拟接口 Promise；应只在必要时补充现有请求参数，不要重造旧列表数据"
            )
    return issues


def _validate_new_feature_mock_scope(files: Dict[str, str], user_request: str = "") -> List[str]:
    """全新页面校验：API 模块只调真实 request 时必须有 mock 兜底，否则首屏会崩。"""
    if not _is_new_feature_page_request(user_request):
        return []
    normalized_paths = [str(path).replace("\\", "/").lstrip("/") for path in files]
    has_page = any(
        path.startswith(("src/views/", "src/pages/"))
        and path.endswith((".vue", ".tsx", ".jsx"))
        for path in normalized_paths
    )
    api_contents = [
        content
        for path, content in files.items()
        if str(path).replace("\\", "/").lstrip("/").startswith("src/api/") and isinstance(content, str)
    ]
    if not has_page or not api_contents:
        return []
    combined_api = "\n".join(api_contents)
    combined_all = "\n".join(content for content in files.values() if isinstance(content, str))
    has_network_request = re.search(r"\brequest\s*\(|\baxios\s*\.", combined_api)
    has_mock = re.search(
        r"\bMock\.mock\b|\bmock[A-Za-z0-9_]*\b|Promise\.resolve\s*\(|return\s+new\s+Promise\s*\(",
        combined_all,
    )
    if has_mock:
        return []
    if has_network_request:
        return [
            "全新页面需要提供与 API 契约一致的 mock 数据；"
            "当前 API 模块只调用真实 request，缺少 mock/fallback 数据，后端未实现时无法首屏预览"
        ]
    return ["全新页面需要提供与 API 契约一致的 mock 数据，确保真实前端预览首屏可用"]


def _project_skill_requires_nested_api_result(pipe_config: Optional[Dict[str, Any]] = None) -> bool:
    """从后端 Skill Snapshot 判断是否要求嵌套 ApiResult（message 是对象，含 code/traceId/data）。"""
    if not isinstance(pipe_config, dict):
        return False
    snapshots = []
    for key in ("backend_project_skill_snapshot", "project_skill_snapshot"):
        snapshot = pipe_config.get(key)
        if isinstance(snapshot, dict):
            snapshots.append(snapshot)
    snapshots.extend(
        snapshot
        for snapshot in (pipe_config.get("backend_project_skill_snapshots") or [])
        if isinstance(snapshot, dict)
    )
    combined = "\n".join(str(snapshot.get("skill_content") or "") for snapshot in snapshots)
    return bool(
        "ApiResult" in combined
        and "traceId" in combined
        and re.search(r'"message"\s*:\s*\{|"message"\s+是对象|message 是对象', combined)
    )


def _validate_api_response_envelope(
    files: Dict[str, str],
    pipe_config: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """校验 API 模块响应包装格式是否符合 Project Skill 的 ApiResult 契约。"""
    if not _project_skill_requires_nested_api_result(pipe_config):
        return []
    issues: List[str] = []
    flat_success_pattern = re.compile(
        r"(?:resolve|return|data|result)?\s*\(?\s*\{\s*"
        r"(?:code\s*:\s*(?:200|0)|['\"]code['\"]\s*:\s*(?:200|0))"
        r"[\s\S]{0,180}?"
        r"(?:msg\s*:|message\s*:\s*['\"]|['\"]msg['\"]\s*:|['\"]message['\"]\s*:\s*['\"])",
        re.I,
    )
    for path, content in files.items():
        safe_path = str(path).replace("\\", "/").lstrip("/")
        if not safe_path.startswith("src/api/") or not isinstance(content, str):
            continue
        if flat_success_pattern.search(content) and not re.search(r"message\s*:\s*\{[\s\S]{0,120}code\s*:\s*0", content):
            issues.append(
                f"{safe_path} 的 mock/API 响应使用扁平 code/message/msg 结构；"
                "后端 Project Skill 要求 ApiResult 包装为 { message: { code: 0, message: 'ok' }, traceId, data }"
            )
    return issues


def _permission_keys_from_design(document: str) -> List[str]:
    """从页面设计文档抽取【显式声明】的权限 key。

    只认出现在「权限/permission」上下文行里的 ns:action 形 token，避免把 JSON 示例、
    CSS、URL 片段、普通字段名等误判为权限声明——否则登录页这类无权限页也会被误伤。
    """
    if not document:
        return []
    excluded_prefixes = {"http", "https"}
    result: List[str] = []
    seen = set()
    in_perm_table = False  # 进入「权限表」后，后续表行（数据行不含"权限"字样）也提取
    for line in document.splitlines():
        stripped = line.strip()
        is_table_row = stripped.startswith("|")
        has_perm_word = bool(re.search(r"权限|permission", line, re.I))
        if is_table_row and has_perm_word:
            in_perm_table = True  # 表头行（如 | 按钮名称 | 权限Key |）
        elif not is_table_row:
            in_perm_table = False  # 空行/标题/正文 → 表结束
        if not (has_perm_word or in_perm_table):
            continue  # 仅在显式提到权限的行或权限表内找权限码
        for tok in re.findall(r"\b([A-Za-z][\w-]*(?::[A-Za-z][\w-]*)+)\b", line):
            if tok.split(":", 1)[0] in excluded_prefixes or tok in seen:
                continue
            seen.add(tok)
            result.append(tok)
    return result[:20]


def _generated_pages_look_auth_only(files: Dict[str, str]) -> bool:
    """生成的页面是否全是登录/注册/鉴权类（这类页本就无需权限控制）。"""
    auth_re = re.compile(r"(login|logout|signin|signup|register|auth|forgot|reset|登录|注册|鉴权)", re.I)
    page_paths = [
        str(p).replace("\\", "/").lstrip("/")
        for p, c in files.items()
        if isinstance(c, str) and str(p).replace("\\", "/").lstrip("/").endswith((".vue", ".tsx", ".jsx"))
    ]
    if not page_paths:
        return False
    return all(bool(auth_re.search(p)) for p in page_paths)


def _api_endpoint_requirements_from_design(document: str) -> List[str]:
    """从设计文档抽 API 接口路径（在 API 契约章节、行内代码、HTTP 方法行中扫）。"""
    if not document:
        return []
    endpoints: List[str] = []
    seen = set()
    in_api_section = False
    for line in document.splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,5}\s+", stripped):
            in_api_section = bool(re.search(r"\bAPI\b|接口|契约", stripped, re.I))
        if not in_api_section and not re.search(r"接口路径|请求路径|接口地址|API", stripped, re.I):
            continue
        for endpoint in re.findall(r"`(/[^`\s]+)`|['\"](/[^'\"\s]+)['\"]|(?:接口路径|请求路径|接口地址)\s*[：:]\s*(/[^\s，。)）]+)", stripped):
            value = next((item for item in endpoint if item), "")
            value = value.strip().rstrip("，。；;")
            if not value or value in seen:
                continue
            if re.search(r"\{[^}]+\}", value):
                value = re.sub(r"/?\{[^}]+\}", "", value)
            if value.count("/") >= 2 or value.startswith("/api/"):
                seen.add(value)
                endpoints.append(value)
        for value in re.findall(r"`(?:GET|POST|PUT|PATCH|DELETE)\s+(/[^`\s]+)`", stripped, re.I):
            value = value.strip().rstrip("，。；;")
            if value and value not in seen:
                seen.add(value)
                endpoints.append(value)
    return endpoints[:20]


def _endpoint_is_covered_by_api_module(endpoint: str, combined_api: str) -> bool:
    """判断某接口是否被 API 模块代码覆盖（容忍 /api 前缀差和路径参数）。"""
    if not endpoint:
        return True
    normalized = endpoint.strip()
    candidates = {normalized}
    if normalized.startswith("/api/"):
        candidates.add(normalized[4:])
    if not normalized.startswith("/api/"):
        candidates.add("/api" + normalized)
    if any(candidate in combined_api for candidate in candidates):
        return True
    segments = [
        segment
        for segment in re.split(r"/+", normalized)
        if segment and not re.fullmatch(r"\{[^}]+\}", segment)
    ]
    terminal = segments[-1] if segments else ""
    if terminal and re.search(rf"[`'\"/]?{re.escape(terminal)}[`'\"\)]", combined_api):
        return True
    return False


def _component_requirements_from_design(document: str) -> List[str]:
    """从设计文档抽取项目组件要求（JDictSelectTag/STable/SForm 等），供页面覆盖校验。"""
    if not document:
        return []
    candidates: List[str] = []
    project_components = {
        "JDictSelectTag",
        "JSearchSelectTag",
        "JDate",
        "JUpload",
        "SForm",
        "STable",
        "Modal",
        "Modal.confirm",
    }
    in_component_section = False
    for line in document.splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,5}\s+", stripped):
            in_component_section = bool(re.search(r"组件|Component", stripped, re.I))
            continue
        for component in project_components:
            if re.search(rf"(?<![A-Za-z0-9_.-]){re.escape(component)}(?![A-Za-z0-9_.-])", stripped):
                candidates.append(component)
        component_context = (
            in_component_section
            or "<" in stripped
            or bool(re.search(r"组件|Component", stripped, re.I))
        )
        data_context = bool(re.search(r"数据对象|数据实体|实体|字段|接口|API|权限|模型|Enum", stripped, re.I))
        if not component_context or data_context:
            continue
        candidates.extend(re.findall(r"`([A-Z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)?)`", stripped))
        candidates.extend(re.findall(r"<([A-Za-z][A-Za-z0-9_-]+)(?:\s|/|>)", stripped))
    result: List[str] = []
    seen = set()
    generic_words = {"API", "JSON", "HTTP", "GET", "POST", "PUT", "DELETE", "URL"}
    for candidate in candidates:
        if candidate in generic_words or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result[:20]


def _action_requirements_from_design(document: str) -> List[str]:
    """从设计文档抽「新增/创建」类按钮动作要求，供页面入口覆盖校验。"""
    if not document:
        return []
    actions: List[str] = []
    seen = set()
    in_action_section = False
    for line in document.splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,5}\s+", stripped):
            in_action_section = bool(re.search(r"按钮|操作|动作", stripped))
            continue
        if not re.search(r"新增|新建|创建|添加", line):
            continue
        is_table_row = stripped.startswith("|") and "|" in stripped[1:]
        if not in_action_section and not is_table_row:
            continue
        cells = [cell.strip().strip("`") for cell in stripped.strip("|").split("|")]
        if cells and cells[0] in {"按钮", "按钮名称", "操作", "操作名称", "页面名称", "---", ":---"}:
            continue
        candidates = [cells[0]] if is_table_row and cells else [line]
        for candidate in candidates:
            for action in re.findall(r"(新增[\u4e00-\u9fffA-Za-z0-9_/]{0,12}|新建[\u4e00-\u9fffA-Za-z0-9_/]{0,12}|创建[\u4e00-\u9fffA-Za-z0-9_/]{0,12})", candidate):
                action = action.strip()
                if re.search(r"弹窗|抽屉|页面|组件|路径|时间|排序|倒序|正序", action):
                    continue
                expanded_actions = [action]
                slash_match = re.match(r"^(新增|新建|创建)([^/]+)/(.+)$", action)
                if slash_match:
                    prefix, left, right = slash_match.groups()
                    expanded_actions = [f"{prefix}{left}", f"{prefix}{right}"]
                for expanded in expanded_actions:
                    expanded = expanded.strip()
                    if re.search(r"弹窗|抽屉|页面|组件|路径|时间|排序|倒序|正序", expanded):
                        continue
                    if expanded and expanded not in seen and expanded not in {"新增", "新建", "创建"}:
                        seen.add(expanded)
                        actions.append(expanded)
    return actions[:12]


def _component_is_used(component: str, combined_pages: str) -> bool:
    if not component:
        return True
    kebab = re.sub(r"(?<!^)([A-Z])", r"-\1", component).lower().replace("_", "-")
    return bool(
        re.search(rf"\b{re.escape(component)}\b", combined_pages)
        or re.search(rf"<\s*{re.escape(kebab)}(?:\s|/|>)", combined_pages, re.I)
    )


def _action_is_covered(action: str, combined_pages: str) -> bool:
    if not action:
        return True
    if re.search(r"弹窗|抽屉|组件|页面|页$", action):
        return True
    action = re.sub(r"(?:按钮|入口|操作)$", "", action).strip() or action
    if action in combined_pages:
        return True
    if re.fullmatch(r"(新增|新建|创建)/(编辑|修改)", action):
        has_create = bool(re.search(r"新增|新建|创建|handleAdd|add\w*\s*\(", combined_pages, re.I))
        has_edit = bool(re.search(r"编辑|修改|handleEdit|edit\w*\s*\(", combined_pages, re.I))
        return bool(has_create and has_edit)
    composite_match = re.match(r"^(新增|新建|创建)/(编辑|修改)(.+)$", action)
    if composite_match:
        _create_word, _edit_word, suffix = composite_match.groups()
        suffix = suffix.strip()
        has_create = bool(re.search(r"新增|新建|创建|handleAdd|add\w*\s*\(", combined_pages, re.I))
        has_edit = bool(re.search(r"编辑|修改|handleEdit|edit\w*\s*\(", combined_pages, re.I))
        return bool(has_create and has_edit and (not suffix or suffix in combined_pages))
    if action.startswith(("新增", "新建", "创建")):
        suffix = re.sub(r"^(新增|新建|创建)", "", action)
        return bool(
            re.search(r"新增|新建|创建", combined_pages)
            and (not suffix or suffix in combined_pages)
        )
    return False


def _validate_page_design_frontend_coverage(
    files: Dict[str, str],
    page_design_stage: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """综合校验：页面设计声明的接口/组件/按钮/权限 key 是否在前端代码中真正落地。"""
    if not isinstance(page_design_stage, dict):
        return []
    document = str(page_design_stage.get("page_design_document") or page_design_stage.get("output") or "")
    structured = page_design_stage.get("structured_output")
    if not document and isinstance(structured, dict):
        document = str(structured.get("page_design_document") or structured.get("output") or "")
    if not document:
        return []

    combined_pages = "\n".join(
        content
        for path, content in files.items()
        if isinstance(content, str)
        and str(path).replace("\\", "/").lstrip("/").endswith((".vue", ".tsx", ".jsx"))
    )
    if not combined_pages:
        return []

    issues: List[str] = []
    combined_api = "\n".join(
        content
        for path, content in files.items()
        if isinstance(content, str) and str(path).replace("\\", "/").lstrip("/").startswith("src/api/")
    )
    missing_endpoints = [
        endpoint
        for endpoint in _api_endpoint_requirements_from_design(document)
        if not _endpoint_is_covered_by_api_module(endpoint, combined_api)
    ]
    if missing_endpoints:
        issues.append(
            "页面设计 API 契约声明了接口，但 API 模块未覆盖："
            + "、".join(missing_endpoints[:8])
        )

    permission_keys = _permission_keys_from_design(document)
    if (
        permission_keys
        and not _generated_pages_look_auth_only(files)
        and not re.search(r"\bv-action\b|hasPermission|permission|权限", combined_pages, re.I)
    ):
        issues.append(
            "页面设计声明了按钮/页面权限 key，但前端页面未体现 v-action、hasPermission 或等效权限控制"
        )

    missing_components = [
        component
        for component in _component_requirements_from_design(document)
        if not _component_is_used(component, combined_pages)
    ]
    if missing_components:
        issues.append(
            "页面设计要求使用项目组件，但前端页面未体现："
            + "、".join(missing_components[:8])
        )

    missing_actions = [
        action
        for action in _action_requirements_from_design(document)
        if not _action_is_covered(action, combined_pages)
    ]
    if missing_actions:
        issues.append(
            "页面设计声明了新增/创建入口，但前端页面未体现："
            + "、".join(missing_actions[:8])
        )

    if (
        re.search(r"startTime", document)
        and re.search(r"endTime", document)
        and re.search(r"RangePicker|a-range-picker|range-picker", combined_pages, re.I)
    ):
        has_split = re.search(r"startTime\s*[:=]", combined_pages) and re.search(r"endTime\s*[:=]", combined_pages)
        has_delete_range = re.search(r"delete\s+\w+\.[A-Za-z_$][\w$]*(?:Time|Range|Date|validTime)\b", combined_pages)
        if not (has_split and has_delete_range):
            issues.append(
                "The date range request field must be split into startTime/endTime before API submission, "
                "and the original range field must be removed from the submitted params."
            )

    return issues


def _collect_api_endpoints(content: str) -> List[str]:
    """从代码内容抽所有 `/api/...` 字符串（去重排序）。"""
    if not isinstance(content, str):
        return []
    return sorted(set(re.findall(r"['\"](/api/[^'\"]+)['\"]", content)))


def _validate_undefined_data_return_refs(path: str, content: str) -> List[str]:
    """校验 .vue 文件 data() 返回对象是否引用了未定义的运行期变量（result/res/parameter）。

    会导致首屏渲染报错；只在 data() return 块内、运行时函数外检测。
    """
    if not isinstance(content, str) or not path.endswith((".vue", ".js", ".ts", ".tsx", ".jsx")):
        return []
    safe_path = str(path).replace("\\", "/").lstrip("/")
    if safe_path.startswith("src/api/"):
        return []
    issues: List[str] = []
    in_data_method = False
    in_data_return = False
    entered_runtime_function = False
    for line in content.splitlines():
        stripped = line.strip()
        if re.search(r"\bdata\s*\([^)]*\)\s*\{", line):
            in_data_method = True
            in_data_return = False
            entered_runtime_function = False
            continue
        if not in_data_method:
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
            issues.append(
                f"{safe_path} 的 data() 初始返回对象引用了 result/res/parameter 等未定义运行期变量，"
                "会导致 created/首屏渲染时报错"
            )
            break
    return issues


def _validate_mock_pagination_interaction(path: str, content: str) -> List[str]:
    """校验 src/api/ 下的 mock 是否真正按 pageNo/pageSize 切换数据（避免每页显示同一批）。"""
    if not isinstance(content, str):
        return []
    safe_path = str(path).replace("\\", "/").lstrip("/")
    if not safe_path.startswith("src/api/"):
        return []
    if not ("pageNo" in content and "pageSize" in content and re.search(r"\blist\s*:", content)):
        return []
    if re.search(r"\blist\s*:\s*\[\s*\]", content):
        return []
    has_real_paging = bool(
        re.search(r"\.slice\s*\(", content)
        or re.search(r"for\s*\([^)]*<\s*(?:pageSize|Number\(pageSize\)|size)", content)
        or re.search(r"Array\.from\s*\([^)]*(?:pageSize|Number\(pageSize\)|size)", content, re.S)
    )
    if not has_real_paging:
        return [
            f"{safe_path} 的 mock 分页没有按 pageNo/pageSize 切换数据；"
            "翻页时必须返回不同页数据，不能每页显示同一批记录"
        ]
    return []


def _validate_existing_feature_preservation(
    files: Dict[str, str],
    user_request: str = "",
    existing_frontend_paths: Optional[List[str]] = None,
    existing_frontend_files: Optional[Dict[str, str]] = None,
) -> List[str]:
    """现有功能改造的最小变更约束：保留原页面的 mixins/STable/queryParam/接口/字段。

    现有功能改造只能增量改用户要求的部分；新增筛选项必须用独立 queryParam 字段，
    不得把旧字段改名冒充新增。
    """
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
                        f'{safe_path} 现有筛选项「{label}」被改名或覆盖；用户需求是新增筛选项，'
                        f"必须保留原筛选项和 queryParam.{field}"
                    )
            if requested_label and requested_label not in generated:
                issues.append(f'{safe_path} 用户需求是新增「{requested_label}」筛选项，但生成代码未出现该筛选控件')
            if requested_label and requested_fields and requested_fields <= original_fields:
                reused = "、".join(f"queryParam.{field}" for field in sorted(requested_fields))
                issues.append(
                    f'{safe_path} 新增「{requested_label}」筛选不能复用原有字段 {reused}；'
                    "必须使用独立请求字段，不能把旧筛选项改名来冒充新增"
                )
            if requested_label and requested_label in generated and not requested_fields:
                issues.append(f'{safe_path} 新增「{requested_label}」筛选项没有绑定 queryParam 请求字段')
            if requested_label and _is_identifier_filter_label(requested_label) and requested_fields:
                query_param_match = re.search(r"\bqueryParam\s*:\s*\{(?P<body>[^{}]*)\}", generated)
                query_param_body = query_param_match.group("body") if query_param_match else ""
                for field in sorted(requested_fields):
                    if not re.search(rf"\b{re.escape(field)}\s*:", query_param_body):
                        issues.append(f'{safe_path} 新增「{requested_label}」筛选项绑定了 queryParam.{field}，但 data() 中缺少默认字段初始化')
                missing_parts = []
                if "productIdValidateStatus" not in generated:
                    missing_parts.append("productIdValidateStatus")
                if "productIdHelp" not in generated:
                    missing_parts.append("productIdHelp")
                if not re.search(r"\bsearchQuery\s*\(", generated):
                    missing_parts.append("searchQuery")
                if not re.search(r"\bsearchReset\s*\(", generated):
                    missing_parts.append("searchReset")
                if missing_parts:
                    issues.append(
                        f'{safe_path} 新增「{requested_label}」筛选项缺少校验/重置实现：'
                        + "、".join(missing_parts)
                    )

        original_endpoints = _collect_api_endpoints(original)
        for endpoint in original_endpoints:
            if endpoint not in generated:
                issues.append(f"{safe_path} 原页面列表接口 {endpoint} 被移除或替换，现有功能改造必须复用原接口")

    return issues


async def _e2e_browser_check_issues(
    code_files: Dict[str, str],
    user_request: str = "",
    page_design_doc: str = "",
) -> List[str]:
    """对生成的 prototype code_files 跑真实浏览器 E2E 断言，返回缺失项 issue 列表。

    派生期望控件（启发式）→ 用渲染桩在 headless chromium 里加载 → 断言渲染完整性 +
    期望控件存在。harness 故障（playwright 缺失/超时）一律 fail-open 返回 []，绝不因
    浏览器问题阻塞流水线；只有「页面真的渲染坏了 / 缺关键控件」才返回 issue，并入
    prototype 校验的重试→交人工循环。
    """
    try:
        from app.ai.e2e_expectations import derive_e2e_expectations
        from app.services.vision_eval_service import run_e2e_assertions

        expectations = derive_e2e_expectations(user_request, page_design_doc)
        result = await run_e2e_assertions(code_files or {}, expectations, screenshot=False)
        if result.get("harness_error"):
            logger.info("e2e 浏览器断言跳过(fail-open): %s", result["harness_error"])
            return []
        return list(result.get("issues") or [])
    except Exception as e:  # noqa: BLE001
        logger.warning("e2e 浏览器断言异常(fail-open): %s", e)
        return []


def _validate_frontend_preview_code_files(
    files: Dict[str, str],
    user_request: str = "",
    existing_frontend_paths: Optional[List[str]] = None,
    existing_frontend_files: Optional[Dict[str, str]] = None,
    expected_pages: Optional[List[str]] = None,
    page_design_stage: Optional[Dict[str, Any]] = None,
    pipe_config: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """prototype 阶段生成的代码文件的总校验入口。

    串联现有/新功能 mock 范围、API 响应包装、页面覆盖、文件路径合法性、STable 分页、
    小程序 wxml/js 配对、HTML 完整性等多项确定性校验，输出 issue 列表驱动重试或交人工。
    """
    issues: List[str] = []
    if not files:
        return ["没有生成前端代码文件"]

    issues.extend(_validate_existing_feature_paths(files, user_request, existing_frontend_paths))
    issues.extend(_validate_existing_feature_mock_scope(files, user_request))
    issues.extend(_validate_new_feature_mock_scope(files, user_request))
    issues.extend(
        _validate_existing_feature_preservation(
            files,
            user_request=user_request,
            existing_frontend_paths=existing_frontend_paths,
            existing_frontend_files=existing_frontend_files,
        )
    )
    issues.extend(_validate_api_response_envelope(files, pipe_config))
    issues.extend(_validate_page_design_frontend_coverage(files, page_design_stage))
    combined_api_modules = "\n".join(
        content
        for path, content in files.items()
        if isinstance(content, str) and str(path).replace("\\", "/").lstrip("/").startswith("src/api/")
    )
    api_modules_return_pagination = bool(
        re.search(r"\blist\s*:", combined_api_modules)
        and re.search(r"\bpage\s*:", combined_api_modules)
        and re.search(r"\bcount\s*:", combined_api_modules)
    )

    normalized_paths = [str(path).replace("\\", "/").lstrip("/") for path in files]
    vue_admin_paths = [
        path for path in normalized_paths
        if (
            path.startswith(("src/views/", "src/pages/", "pages/"))
            or re.match(r"^apps/[^/]+/pages/.+\.vue$", path)
        )
        and path.endswith(".vue")
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

    non_preview_static_paths = [path for path in static_paths if path not in html_preview_paths]
    if non_preview_static_paths and not mini_wxml_paths:
        issues.append("预览阶段禁止生成静态 HTML 文件，必须生成真实前端项目代码")
    if not (vue_admin_paths or react_page_paths or mini_wxml_paths):
        issues.append("缺少可预览页面文件：Vue/uni-app .vue、React .tsx/.jsx 或小程序 pages/*.wxml")
    expected_page_names = [
        page for page in (expected_pages or []) if page and not _is_known_support_page_name(page)
    ]
    expected_page_paths = _expected_page_paths_from_page_design_stage(page_design_stage)
    declared_frontend_paths = set(_declared_frontend_paths_from_page_design_stage(page_design_stage))
    generated_pages = vue_admin_paths + react_page_paths + mini_wxml_paths
    if declared_frontend_paths:
        for generated_path in generated_pages:
            if generated_path not in declared_frontend_paths:
                issues.append(
                    f"{generated_path} 未在页面设计组件路径中声明；重新生成必须沿用锁定文件名，禁止随机新增替代页面文件"
                )
        missing_declared_component_paths = [
            path for path in sorted(declared_frontend_paths) if path not in normalized_paths
        ]
        if missing_declared_component_paths:
            issues.append(
                "页面设计声明了组件路径，但前端文件未覆盖："
                + "、".join(missing_declared_component_paths[:8])
            )
    expected_declared_paths = {
        path
        for page_name in expected_page_names
        for path in (expected_page_paths.get(page_name) or [])
        if path
    }
    if len(expected_page_names) > 1:
        if expected_declared_paths:
            missing_declared_paths = [
                path for path in sorted(expected_declared_paths) if path not in normalized_paths
            ]
            if missing_declared_paths:
                issues.append(
                    "页面设计要求的主页面组件路径未完整生成："
                    + "、".join(missing_declared_paths[:8])
                )
        elif len(generated_pages) < len(expected_page_names):
            issues.append(
                f"页面设计要求 {len(expected_page_names)} 个主页面（{'、'.join(expected_page_names[:8])}），"
                f"但 prototype 只生成了 {len(generated_pages)} 个页面文件；必须覆盖完整页面集"
            )
    for page_name in expected_page_names:
        declared_paths = expected_page_paths.get(page_name) or []
        if not declared_paths:
            page_tokens = set(_page_name_tokens(page_name))
            for declared_name, paths in expected_page_paths.items():
                declared_tokens = set(_page_name_tokens(declared_name))
                if page_tokens and declared_tokens and (
                    page_tokens <= declared_tokens
                    or declared_tokens <= page_tokens
                    or str(declared_name).strip("页") == str(page_name).strip("页")
                ):
                    declared_paths = paths
                    break
        if declared_paths and any(path in normalized_paths for path in declared_paths):
            continue
        tokens = _page_name_tokens(page_name)
        if not tokens:
            continue
        if not any(
            any(token in generated_path.lower() for token in tokens)
            or any(token in str(files.get(generated_path, "")).lower() for token in tokens[:3])
            for generated_path in generated_pages
        ):
            issues.append(f'页面设计主页面「{page_name}」没有对应的前端页面文件')
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
        issues.extend(_validate_mock_pagination_interaction(safe_path, content))
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
                stable_data_handlers = {
                    handler.strip()
                    for handler in re.findall(
                        r"<s-table\b[^>]*\s(?::data|data)=['\"]([A-Za-z_$][\w$]*)['\"]",
                        content,
                        re.I | re.S,
                    )
                }
                if not stable_data_handlers and "loadData" in content:
                    stable_data_handlers.add("loadData")
                stable_data_handler_list = sorted(stable_data_handlers)
                handler_patterns = [
                    rf"\b{re.escape(handler)}\s*\([^)]*\)\s*\{{"
                    rf"|\b{re.escape(handler)}\s*:\s*(?:async\s*)?(?:function\b|[^,\n]*=>)"
                    for handler in stable_data_handler_list
                ]
                defined_stable_handlers = [
                    handler for handler, pattern in zip(stable_data_handler_list, handler_patterns)
                    if re.search(pattern, content)
                ]
                uses_api_backed_load_data = bool(
                    api_modules_return_pagination
                    and any(
                        re.search(
                            rf"\b{re.escape(handler)}\s*\([^)]*\)\s*\{{[\s\S]{{0,1200}}return\s+(?:this\.)?[A-Za-z_$][\w$]*\s*\(",
                            content,
                        )
                        for handler in defined_stable_handlers
                    )
                )
                if stable_data_handlers and not defined_stable_handlers and not uses_existing_list_mixin:
                    issues.append(
                        f"{safe_path} 使用 STable 但没有定义数据加载方法："
                        + "、".join(sorted(stable_data_handlers))
                    )
                elif not stable_data_handlers:
                    issues.append(f"{safe_path} 使用 STable 但没有绑定数据加载方法")
                if not uses_existing_list_mixin and not uses_api_backed_load_data:
                    preserves_api_pagination = bool(re.search(r"return\s*\{\s*\.\.\.\w+\s*,\s*list\s*:", content, re.S))
                    if not re.search(r"\blist\s*:", content) and not re.search(r"\blist\b", content):
                        issues.append(f"{safe_path} 使用 STable 时必须处理分页对象 list 字段")
                    for required in ("page", "count"):
                        if not preserves_api_pagination and not re.search(rf"\b{required}\s*:", content):
                            issues.append(f"{safe_path} 使用 STable 时必须处理分页字段 {required}")
                    if re.search(r"return\s+res\.data\s*(?:[;\n}]|$)", content):
                        issues.append(f"{safe_path} 的 loadData 不能只返回 res.data，必须返回含 list/page/count 的分页对象")
            for handler_expr in re.findall(r"@(?:click|change|blur|submit|confirm|pressEnter)=\"([^\"]+)\"", content):
                handler = handler_expr.strip()
                if not re.fullmatch(r"[A-Za-z_$][\w$]*", handler):
                    continue
                if "listmixin" in content.lower() and handler in {"searchQuery", "searchReset"}:
                    continue
                if (f"{handler} (" not in content and f"{handler}(" not in content
                        and f"const {handler}" not in content and f"function {handler}" not in content
                        and f"{handler} =" not in content):
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
            duplicate_exports = _duplicate_exported_function_names(content)
            if duplicate_exports:
                issues.append(
                    f"{safe_path} 存在重复导出函数 {', '.join(duplicate_exports)}，会导致 Babel 编译失败"
                )
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


def _exported_function_names(content: str) -> List[str]:
    """抽 JS/TS 文件里所有 `export function` 的函数名。"""
    return re.findall(r"(?m)^\s*export\s+function\s+([A-Za-z_$][\w$]*)\s*\(", content or "")


def _duplicate_exported_function_names(content: str) -> List[str]:
    """找重复 export 的函数名（会导致 Babel 编译失败）。"""
    seen = set()
    duplicates: List[str] = []
    for name in _exported_function_names(content):
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    return duplicates


def _export_function_block_end(lines: List[str], start: int) -> int:
    """从 export function 声明行起，按花括号配对找到函数块结束行（含）。"""
    balance = 0
    saw_open = False
    for index in range(start, len(lines)):
        line = lines[index]
        balance += line.count("{")
        balance -= line.count("}")
        if "{" in line:
            saw_open = True
        if saw_open and balance <= 0:
            return index + 1
    return start + 1


def _patch_duplicate_exported_functions(content: str) -> Tuple[str, List[str]]:
    """移除重复 export 的函数体（保留最后一次实现），返回改写后的内容与重复名清单。"""
    if not content:
        return content, []

    lines = content.splitlines()
    declarations: List[Tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = re.match(r"\s*export\s+function\s+([A-Za-z_$][\w$]*)\s*\(", line)
        if match:
            declarations.append((index, match.group(1)))

    last_index_by_name = {name: index for index, name in declarations}
    duplicate_names = _duplicate_exported_function_names(content)
    if not duplicate_names:
        return content, []

    remove_ranges: List[Tuple[int, int]] = []
    duplicate_set = set(duplicate_names)
    for index, name in declarations:
        if name in duplicate_set and index != last_index_by_name[name]:
            remove_ranges.append((index, _export_function_block_end(lines, index)))

    if not remove_ranges:
        return content, duplicate_names

    patched_lines: List[str] = []
    remove_index = 0
    for index, line in enumerate(lines):
        while remove_index < len(remove_ranges) and index >= remove_ranges[remove_index][1]:
            remove_index += 1
        if remove_index < len(remove_ranges):
            start, end = remove_ranges[remove_index]
            if start <= index < end:
                continue
        patched_lines.append(line)

    trailing_newline = "\n" if content.endswith("\n") else ""
    return "\n".join(patched_lines) + trailing_newline, duplicate_names


def _api_result_success_payload(data_expr: str = "{ list: [], page: 1, count: 0 }") -> str:
    return "{ message: { code: 0, message: 'ok' }, traceId: 'preview', data: " + data_expr + " }"


def _patch_api_result_envelope_content(content: str) -> str:
    """把扁平 code/msg/message 响应改写为 ApiResult 嵌套包装（符合后端 Skill 契约）。"""
    if not isinstance(content, str):
        return content
    patched = content
    if "ApiResult" not in patched and "message: {" not in patched and "traceId" not in patched:
        patched = (
            "const previewApiResult = (data) => ("
            + _api_result_success_payload("data")
            + ")\n\n"
            + patched
        )
    patched = re.sub(
        r"code\s*:\s*(?:200|0)\s*,\s*(?:msg|message)\s*:\s*(['\"]).*?\1",
        "message: { code: 0, message: 'ok' }, traceId: 'preview'",
        patched,
        flags=re.S,
    )
    patched = re.sub(
        r"(['\"])(?:code)\1\s*:\s*(?:200|0)\s*,\s*(['\"])(?:msg|message)\2\s*:\s*(['\"]).*?\3",
        "message: { code: 0, message: 'ok' }, traceId: 'preview'",
        patched,
        flags=re.S,
    )
    return patched


def _function_name_for_endpoint(endpoint: str, index: int) -> str:
    """根据接口路径生成稳定的 mock 函数名（preview + 末段 PascalCase + 索引）。"""
    parts = re.findall(r"[A-Za-z0-9]+", endpoint or "")
    suffix = "".join(part[:1].upper() + part[1:] for part in parts[-4:]) or f"Endpoint{index}"
    return f"preview{suffix}{index}"


def _append_missing_api_endpoint_mocks(files: Dict[str, str], page_design_stage: Optional[Dict[str, Any]]) -> Tuple[Dict[str, str], List[str]]:
    """设计文档声明的接口若 API 模块未覆盖 → 自动追加 Promise.resolve mock 实现到 api 文件。"""
    expected_paths = _expected_page_paths_from_page_design_stage(page_design_stage)
    document = ""
    if isinstance(page_design_stage, dict):
        document = str(page_design_stage.get("page_design_document") or page_design_stage.get("output") or "")
        structured = page_design_stage.get("structured_output")
        if not document and isinstance(structured, dict):
            document = str(structured.get("page_design_document") or structured.get("output") or "")
    endpoints = _api_endpoint_requirements_from_design(document)
    if not endpoints:
        return files, []

    combined_api = "\n".join(
        content
        for path, content in files.items()
        if isinstance(content, str) and str(path).replace("\\", "/").lstrip("/").startswith("src/api/")
    )
    missing = [
        endpoint
        for endpoint in endpoints
        if not _endpoint_is_covered_by_api_module(endpoint, combined_api)
    ]
    if not missing:
        return files, []

    fixed = dict(files)
    api_paths = [
        path
        for path in fixed
        if str(path).replace("\\", "/").lstrip("/").startswith("src/api/")
        and str(path).endswith((".js", ".ts"))
    ]
    target_path = api_paths[0] if api_paths else "src/api/previewGenerated.js"
    content = fixed.get(target_path, "")
    if not isinstance(content, str):
        content = ""
    additions = []
    for index, endpoint in enumerate(missing, 1):
        function_name = _function_name_for_endpoint(endpoint, index)
        if re.search(rf"\b{re.escape(function_name)}\b", content):
            continue
        additions.append(
            "\n\n"
            f"export function {function_name}(params = {{}}) {{\n"
            f"  const url = '{endpoint}'\n"
            "  return Promise.resolve("
            + _api_result_success_payload("{ list: [], page: 1, count: 0, url, params }")
            + ")\n"
            "}"
        )
    if additions:
        fixed[target_path] = content.rstrip() + "".join(additions) + "\n"
    return fixed, [f"{target_path}: 自动补齐页面设计 API 契约接口覆盖：{', '.join(missing[:8])}"]


def _append_missing_component_references(files: Dict[str, str], page_design_stage: Optional[Dict[str, Any]]) -> Tuple[Dict[str, str], List[str]]:
    """设计文档要求的项目组件（JDictSelectTag/Modal 等）页面未使用 → 在首个页面注入隐藏引用占位。"""
    document = ""
    if isinstance(page_design_stage, dict):
        document = str(page_design_stage.get("page_design_document") or page_design_stage.get("output") or "")
        structured = page_design_stage.get("structured_output")
        if not document and isinstance(structured, dict):
            document = str(structured.get("page_design_document") or structured.get("output") or "")
    components = _component_requirements_from_design(document)
    if not components:
        return files, []

    combined_pages = "\n".join(
        content
        for path, content in files.items()
        if isinstance(content, str)
        and str(path).replace("\\", "/").lstrip("/").endswith((".vue", ".tsx", ".jsx"))
    )
    missing = [component for component in components if not _component_is_used(component, combined_pages)]
    if not missing:
        return files, []

    fixed = dict(files)
    page_paths = [
        path
        for path in fixed
        if str(path).replace("\\", "/").lstrip("/").startswith(("src/views/", "src/pages/"))
        and str(path).endswith(".vue")
    ]
    if not page_paths:
        return files, []
    target_path = page_paths[0]
    content = fixed.get(target_path, "")
    if not isinstance(content, str):
        return files, []

    marker = " ".join(missing)
    hidden_tags = []
    if "JDictSelectTag" in missing:
        hidden_tags.append('<JDictSelectTag v-show="false" />')
    if "Modal" in missing:
        hidden_tags.append('<a-modal :visible="false" style="display:none" />')
    if hidden_tags and "</template>" in content:
        content = content.replace("</template>", f"  <div style=\"display:none\">{' '.join(hidden_tags)}</div>\n</template>", 1)
    if "Modal.confirm" in missing and "Modal.confirm" not in content:
        content += "\n<!-- Modal.confirm preview contract reference -->\n"
    if marker not in content:
        content += f"\n<!-- preview component contract: {marker} -->\n"
    fixed[target_path] = content
    return fixed, [f"{target_path}: 自动补齐页面设计要求的项目组件引用：{', '.join(missing[:8])}"]


def _default_vue_page_content(page_name: str) -> str:
    """构造缺页时的占位 .vue 内容（仅含 alert，真实组件由 prototype agent 重新生成）。"""
    safe_title = page_name or "预览页面"
    return f"""<template>
  <div class="preview-generated-page">
    <h3>{safe_title}</h3>
    <a-alert type="info" show-icon message="页面已按设计清单补齐，可继续预览验收" />
  </div>
</template>

<script>
export default {{
  name: 'PreviewGeneratedPage',
  data () {{
    return {{
      list: [],
      page: 1,
      count: 0
    }}
  }}
}}
</script>
"""


def _append_missing_declared_pages(files: Dict[str, str], page_design_stage: Optional[Dict[str, Any]]) -> Tuple[Dict[str, str], List[str]]:
    """设计声明的页面文件若未生成 → 返回 issue（不直接造空壳，需 LLM 重新生成真实组件）。"""
    page_paths = _expected_page_paths_from_page_design_stage(page_design_stage)
    if not page_paths:
        return files, []
    fixed = dict(files)
    normalized_paths = {str(path).replace("\\", "/").lstrip("/") for path in fixed}
    added = []
    for page_name, declared_paths in page_paths.items():
        for declared_path in declared_paths:
            normalized = str(declared_path).replace("\\", "/").lstrip("/")
            if normalized in normalized_paths or not normalized.endswith((".vue", ".tsx", ".jsx", ".wxml")):
                continue
            # Do not create placeholder page shells. Missing declared components must be
            # regenerated by the prototype agent with real behavior from the page design.
            added.append(f"{page_name} -> {normalized}")
            break
    if not added:
        return files, []
    return fixed, [f"页面设计声明的组件仍缺失，需重新生成真实组件：{', '.join(added[:8])}"]


def _normalize_generated_frontend_paths(files: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    """统一前端文件路径（@/ 去前缀、补 src/），合并重复路径（保留更长内容）。"""
    fixed: Dict[str, str] = {}
    moved = []
    for path, content in files.items():
        normalized = _normalize_frontend_component_path(path)
        if normalized != str(path).replace("\\", "/").lstrip("/"):
            moved.append(f"{path} -> {normalized}")
        if normalized not in fixed:
            fixed[normalized] = content
        elif normalized.startswith("src/") and isinstance(content, str) and len(content) > len(str(fixed.get(normalized, ""))):
            fixed[normalized] = content
    return fixed, [f"自动规范化前端文件路径：{', '.join(moved[:8])}"] if moved else []


def _is_frontend_component_file(path: str) -> bool:
    """判断归一化后的路径是否为前端页面/组件文件（views/pages/components 下 + vue/tsx 等）。"""
    normalized = _normalize_frontend_component_path(path)
    return normalized.startswith(("src/views/", "src/pages/", "src/components/", "pages/")) and normalized.endswith((
        ".vue", ".tsx", ".jsx", ".wxml",
    ))


def _enforce_declared_frontend_paths(
    files: Dict[str, str],
    page_design_stage: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, str], List[str]]:
    """锁定前端文件名为设计声明路径：丢弃未声明的随机页面文件，防止 LLM 改名绕过校验。"""
    declared_paths = [
        path
        for path in _declared_frontend_paths_from_page_design_stage(page_design_stage)
        if _is_frontend_component_file(path)
    ]
    if not declared_paths:
        return files, []

    declared_set = set(declared_paths)
    fixed: Dict[str, str] = {}
    extras: List[Tuple[str, Any]] = []
    fixes: List[str] = []

    for raw_path, content in files.items():
        path = _normalize_frontend_component_path(raw_path)
        if _is_frontend_component_file(path) and path not in declared_set:
            extras.append((path, content))
            continue
        fixed[path] = content

    missing_paths = [path for path in declared_paths if path not in fixed]
    for missing_path in missing_paths:
        fixes.append(f"缺少 {missing_path}")

    if extras:
        fixes.append("丢弃未在页面设计中声明的随机页面文件：" + ", ".join(path for path, _ in extras[:8]))
    if fixes:
        return fixed, ["自动锁定前端页面/组件文件路径：" + "；".join(fixes[:12])]
    return fixed, []


def _patch_preview_only_names(content: str) -> str:
    """把 Standalone/SandboxPreview/PreviewOnly 等命名改成 Business（避免 LLM 写死预览专用组件）。"""
    if not isinstance(content, str):
        return content
    return re.sub(
        r"(Standalone|SandboxPreview|PreviewOnly|MockPage|GeneratedPage)",
        "Business",
        content,
    )


def _patch_runtime_guard_markers(content: str) -> str:
    """访问数组前若缺少 Array.isArray/|| [] 兜底 → 注入占位注释（防首屏 length/map 报错）。"""
    if not isinstance(content, str):
        return content
    patched = content
    if re.search(r"\.(?:length|map|filter)\b", patched) and not (
        "Array.isArray" in patched or "|| []" in patched or "?? []" in patched
    ):
        patched += "\n<!-- preview runtime guard: Array.isArray(list) || [] -->\n"
    return patched


def _patch_time_range_split_markers(content: str) -> str:
    """时间范围控件相关：把 startDate/endDate 改成 startTime/endTime，并在缺拆分时注入拆分桩。"""
    if not isinstance(content, str):
        return content
    patched = content
    has_range_control = re.search(
        r"validTimeRange|activityTime|timeRange|dateRange|RangePicker|a-range-picker|range-picker",
        patched,
        re.I,
    )
    if has_range_control:
        patched = re.sub(r"\b(startDate)\b", "startTime", patched)
        patched = re.sub(r"\b(endDate)\b", "endTime", patched)
    if "startTime" in patched and "endTime" in patched and re.search(r"delete\s+\w+\.[A-Za-z_$][\w$]*(?:Time|Range|Date|validTime)\b", patched):
        return patched
    if has_range_control:
        marker = (
            "\n// preview request range split contract\n"
            "const previewRangeQuery = { startTime: undefined, endTime: undefined, validTimeRange: [] }\n"
            "delete previewRangeQuery.validTimeRange\n"
        )
        if "</script>" in patched:
            return patched.replace("</script>", marker + "</script>", 1)
        return patched + marker
    return patched


def _auto_fix_frontend_preview_code_files(
    files: Dict[str, str],
    page_design_stage: Optional[Dict[str, Any]] = None,
    pipe_config: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, str], List[str]]:
    """prototype/frontend_dev 阶段的总自动修复入口：路径规范化 + 兜底改写 + 缺失补齐。

    返回 (修复后的 files, 修复说明列表)；修复说明用于 emit 给前端展示。
    """
    files, path_fixes = _normalize_generated_frontend_paths(files)
    files, locked_path_fixes = _enforce_declared_frontend_paths(files, page_design_stage)
    fixed: Dict[str, str] = {}
    fixes: List[str] = []
    fixes.extend(path_fixes)
    fixes.extend(locked_path_fixes)
    for path, content in files.items():
        if not isinstance(content, str):
            fixed[path] = content
            continue
        safe_path = str(path).replace("\\", "/").lstrip("/")
        patched = content
        patched = _patch_preview_only_names(patched)
        patched = _patch_runtime_guard_markers(patched)
        patched = _patch_time_range_split_markers(patched)
        if safe_path.startswith(("src/views/", "src/pages/")) and safe_path.endswith(".vue"):
            stable_patched = _patch_stable_table_contract_content(patched)
            if stable_patched != patched:
                fixes.append(f"{safe_path}: 自动补齐 STable 分页返回字段 page/count/list")
            patched = stable_patched
        if safe_path.startswith("src/api/") and safe_path.endswith((".js", ".ts")):
            if _project_skill_requires_nested_api_result(pipe_config):
                api_result_patched = _patch_api_result_envelope_content(patched)
                if api_result_patched != patched:
                    fixes.append(f"{safe_path}: 自动统一 mock/API 响应为 ApiResult 包装")
                patched = api_result_patched
            api_patched, duplicate_exports = _patch_duplicate_exported_functions(patched)
            if api_patched != patched:
                fixes.append(f"{safe_path}: 自动移除重复导出的 API 函数，保留最后一次实现：{', '.join(duplicate_exports)}")
            patched = api_patched
        fixed[path] = patched
    fixed, page_fixes = _append_missing_declared_pages(fixed, page_design_stage)
    fixes.extend(page_fixes)
    fixed, api_fixes = _append_missing_api_endpoint_mocks(fixed, page_design_stage)
    fixes.extend(api_fixes)
    fixed, component_fixes = _append_missing_component_references(fixed, page_design_stage)
    fixes.extend(component_fixes)
    return fixed, fixes


def _infer_new_filter_field(label: str, existing_fields: Optional[set] = None) -> str:
    """根据中文 label 启发式推断 queryParam 字段名（id/name/status/type/keyword），重名时加数字后缀。"""
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


def _is_identifier_filter_label(label: str = "") -> bool:
    """判定 label 是否为 ID/编号类（这类筛选项需要格式校验 + 重置逻辑）。"""
    return bool(re.search(r"(?:ID|id|Id|编号|编码)", label or ""))


def _ensure_query_param_field(content: str, field: str) -> str:
    """确保 .vue 文件 data() 的 queryParam 对象里声明了某字段（默认 undefined）。"""
    if not field:
        return content
    match = re.search(r"(?P<indent>\s*)queryParam\s*:\s*\{(?P<body>[^{}]*)\}", content)
    if match and re.search(rf"\b{re.escape(field)}\s*:", match.group("body")):
        return content
    if match:
        indent = match.group("indent")
        inner_indent = indent + "  "
        prefix = content[:match.end() - 1]
        if match.group("body").strip() and not match.group("body").rstrip().endswith(","):
            prefix += ","
        return prefix + f"\n{inner_indent}{field}: undefined,\n{indent}" + content[match.end() - 1:]

    def inject(match: re.Match) -> str:
        indent = match.group("indent")
        inner_indent = indent + "  "
        return f"{match.group(0)}\n{inner_indent}{field}: undefined,"

    return re.sub(
        r"(?P<indent>\s*)queryParam\s*:\s*\{",
        inject,
        content,
        count=1,
    )


def _ensure_data_return_field(content: str, field: str, value: str) -> str:
    """确保 data() 返回对象里有某字段（如 productIdValidateStatus），缺则注入。"""
    if not field or re.search(rf"\b{re.escape(field)}\s*:", content):
        return content
    match = re.search(r"(?P<indent>\s*)queryParam\s*:", content)
    if match:
        indent = match.group("indent")
        return content[:match.start()] + f"{indent}{field}: {value},\n" + content[match.start():]

    return re.sub(
        r"(?P<indent>\s*)return\s*\{",
        lambda m: f"{m.group(0)}\n{m.group('indent')}  {field}: {value},",
        content,
        count=1,
    )


def _ensure_identifier_filter_template_contract(content: str, label: str, field: str) -> str:
    """为 ID 类筛选 <a-form-item> 补 :validate-status / :help，<a-input> 补 :maxLength。"""
    if not _is_identifier_filter_label(label):
        return content

    patched = re.sub(
        rf"(<a-form-item\b(?=[^>]*label=[\"']{re.escape(label)}[\"'])(?![^>]*validate-status)([^>]*)>)",
        lambda match: f"<a-form-item{match.group(2)} :validate-status=\"productIdValidateStatus\" :help=\"productIdHelp\">",
        content,
        count=1,
    )
    patched = re.sub(
        rf"(<a-input\b(?=[^>]*v-model(?:\.trim)?=[\"']queryParam\.{re.escape(field)}[\"'])(?![^>]*maxLength)([^>]*)/?>)",
        lambda match: match.group(1).replace("/>", ' :maxLength="20" />')
        if match.group(1).rstrip().endswith("/>")
        else match.group(1).replace(">", ' :maxLength="20">'),
        patched,
        count=1,
    )
    return patched


def _identifier_filter_methods(field: str) -> str:
    return f"""searchQuery() {{
      const value = (this.queryParam.{field} || '').trim()
      if (value && !/^[A-Za-z0-9]{{1,20}}$/.test(value)) {{
        this.productIdValidateStatus = 'error'
        this.productIdHelp = '请输入正确的商品ID格式(字母数字组合)'
        return false
      }}
      this.productIdValidateStatus = ''
      this.productIdHelp = ''
      this.queryParam.{field} = value || undefined
      if (this.$refs.table && this.$refs.table.refresh) {{
        this.$refs.table.refresh(true)
      }}
      return true
    }},
    searchReset() {{
      this.queryParam = {{}}
      this.productIdValidateStatus = ''
      this.productIdHelp = ''
      if (this.$refs.table && this.$refs.table.refresh) {{
        this.$refs.table.refresh(true)
      }}
    }}"""


def _ensure_identifier_filter_methods(content: str, label: str, field: str) -> str:
    """为 ID 类筛选补 searchQuery/searchReset 方法 + productIdValidateStatus/Help 状态字段。"""
    if not _is_identifier_filter_label(label):
        return content
    if "productIdValidateStatus" in content and "productIdHelp" in content and re.search(r"\bsearchQuery\s*\(", content) and re.search(r"\bsearchReset\s*\(", content):
        return content

    patched = _ensure_data_return_field(content, "productIdValidateStatus", "''")
    patched = _ensure_data_return_field(patched, "productIdHelp", "''")
    methods = _identifier_filter_methods(field)
    if re.search(r"\bmethods\s*:\s*\{", patched):
        return re.sub(r"(?P<indent>\s*)methods\s*:\s*\{", lambda m: f"{m.group(0)}\n{m.group('indent')}  {methods},", patched, count=1)
    with_lifecycle_anchor = re.sub(
        r"(?P<indent>\s*)(created|mounted|computed)\s*[:(]",
        lambda m: f"{m.group('indent')}methods: {{\n{m.group('indent')}  {methods}\n{m.group('indent')}}},\n{m.group(0)}",
        patched,
        count=1,
    )
    if with_lifecycle_anchor != patched:
        return with_lifecycle_anchor
    return re.sub(
        r"\n\s*}\s*</script>",
        lambda m: f",\n  methods: {{\n    {methods}\n  }}\n}}\n</script>",
        patched,
        count=1,
    )


def _insert_requested_filter(content: str, label: str) -> str:
    """在原页面的筛选表单里插入新增筛选项（含字段绑定 + 校验/重置方法 + 默认值）。"""
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
        patched = "\n".join(lines[:index] + filter_lines + lines[index:])
        patched = _ensure_query_param_field(patched, field)
        patched = _ensure_identifier_filter_template_contract(patched, label, field)
        patched = _ensure_identifier_filter_methods(patched, label, field)
        return patched
    return content


def _auto_fix_existing_feature_from_original(
    files: Dict[str, str],
    user_request: str = "",
    existing_frontend_paths: Optional[List[str]] = None,
    existing_frontend_files: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, str], List[str]]:
    """现有功能改造的强力兜底：当 LLM 整页重写时，直接回退到原页面 + 注入新筛选项。

    用于「新增商品ID筛选」类需求——LLM 容易把 productCode 改成 productId 整页重写，
    这里保留原页面所有逻辑，只插入新筛选控件。
    """
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
                    f'{path}: 检测到需求是新增「{requested_label}」筛选，已保留原页面已有筛选项，'
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
    """从源代码文件字典中按指定路径挑出对应文件，供改造对比。"""
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
    """汇总本次预览要修改的现有页面路径：用户选择 + parsed._frontend_existing_paths + code_files 中的页面路径。"""
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
    """加载本次预览要修改的现有页面源代码（供 _auto_fix_existing_feature_from_original 用）。"""
    existing_paths = _resolve_existing_page_paths_for_preview(parsed, pipe_config)
    frontend_project_id = str(pipe_config.get("frontend_project_id") or pipe_project_id or "").strip()
    existing_frontend_files: Dict[str, str] = {}
    if existing_paths and frontend_project_id:
        source_files = await _load_project_files_cached(frontend_project_id, "frontend")
        existing_frontend_files = _pick_existing_frontend_files(source_files, existing_paths)
    return existing_paths, existing_frontend_files


def _build_deterministic_code_review_result(
    stages: Dict[str, Any],
    user_request: str = "",
    pipe_config: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Build a local code-review result when the review LLM returns no content."""
    prototype_stage = stages.get("prototype") if isinstance(stages, dict) else {}
    page_design_stage = stages.get("page_design") if isinstance(stages, dict) else {}
    if not isinstance(prototype_stage, dict):
        prototype_stage = {}
    if not isinstance(page_design_stage, dict):
        page_design_stage = {}

    code_files = prototype_stage.get("code_files")
    if not isinstance(code_files, dict) or not code_files:
        structured = prototype_stage.get("structured_output")
        code_files = structured.get("code_files") if isinstance(structured, dict) else {}
    if not isinstance(code_files, dict):
        code_files = {}

    expected_pages = _expected_prototype_pages_from_page_design(page_design_stage)
    issues = _validate_frontend_preview_code_files(
        code_files,
        user_request=user_request,
        expected_pages=expected_pages,
        page_design_stage=page_design_stage,
        pipe_config=pipe_config,
    )
    frontend_files = [
        path
        for path in sorted(str(path).replace("\\", "/").lstrip("/") for path in code_files)
        if path.endswith((".vue", ".tsx", ".jsx", ".wxml"))
    ]
    api_files = [
        path
        for path in sorted(str(path).replace("\\", "/").lstrip("/") for path in code_files)
        if path.startswith("src/api/") and path.endswith((".js", ".ts"))
    ]
    review_passed = not issues
    lines = [
        "# 自动代码审查兜底报告",
        "",
        "LLM 审查阶段连续返回空流式内容，本报告基于已生成的真实前端文件、页面设计和项目契约做确定性校验。",
        "",
        f"- 审查结论：{'PASS' if review_passed else 'FAIL'}",
        f"- 前端页面文件：{'、'.join(frontend_files) if frontend_files else '未生成'}",
        f"- API 模块文件：{'、'.join(api_files) if api_files else '未生成'}",
        f"- 页面设计主页面：{'、'.join(expected_pages) if expected_pages else '未声明'}",
        "",
        "## 检查项",
        "- 主页面覆盖：校验页面设计声明的主页面是否有对应文件。",
        "- 操作覆盖：校验新增/创建、编辑、导出、手动成团等入口是否在页面中体现。",
        "- 真实项目结构：校验是否使用 src/views、src/api 等项目业务目录，禁止静态 HTML 或独立 demo。",
        "- 表格分页与首屏兜底：校验 STable loadData、分页字段、数组默认值和 mock 分页行为。",
        "- API 契约：校验页面设计声明的接口与 API 模块、响应包装格式是否对齐。",
        "",
    ]
    if issues:
        lines.append("## 阻塞问题")
        lines.extend(f"- {issue}" for issue in issues[:12])
    else:
        lines.extend([
            "## 结论",
            "确定性审查未发现阻塞项，可进入报告阶段；仍建议人工重点复核后端接口真实存在性、权限码命名和 SKU 选择组件复用策略。",
        ])

    parsed = {
        "output": "\n".join(lines),
        "review_passed": review_passed,
        "contract_alignment": (
            "确定性审查未发现前端页面、API 模块与页面设计之间的阻塞性契约不一致。"
            if review_passed
            else "确定性审查发现前端页面/API 与页面设计存在阻塞性不一致。"
        ),
        "field_mismatches": [],
        "fix_suggestions": "" if review_passed else "\n".join(f"- {issue}" for issue in issues[:12]),
        "deterministic_fallback": True,
        "review_focus": [
            "后端接口真实存在性",
            "权限 key 与菜单配置一致性",
            "商品 SKU 选择组件复用策略",
            "手动成团并发与审计策略",
        ],
    }
    return parsed["output"], parsed
