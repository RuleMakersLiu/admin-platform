"""LLM 输出解析 + 代码审查结果归一化。

从 flow_manager 拆出。把 LLM 流式/块输出解析成代码文件 dict 或 page spec；把代码审查
结果归一化成统一结构（评分/问题/suggestions）。全部纯函数（json + re），不碰 DB/运行时。
"""
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from app.ai.pipeline_helpers import _coerce_string_list
from app.ai.pipeline_page_design import (
    _declared_frontend_paths_from_page_design_stage,
    _extract_primary_pages_from_page_design_document,
)


def _try_parse_page_spec(raw_output: str) -> Optional[Dict[str, Any]]:
    """尝试从 LLM 输出中解析页面规格 JSON（Spec→模板渲染模式）。

    Spec 格式：{"pages": [{path, title, components: [...]}], "api_modules": [...], "pm_quality": {...}}
    如果输出不含 "pages" 键 → 返回 None（fallback 到原 [{path, content}] 解析）。
    """
    text = (raw_output or "").strip()
    # 去掉 ```json ... ``` 包裹
    fence = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    for candidate in (text, text[text.index("{"):text.rindex("}") + 1] if "{" in text and "}" in text else ""):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "pages" in parsed:
                return parsed
        except (json.JSONDecodeError, ValueError):
            continue
    return None


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

    def best(files_list: List[Dict[str, str]]) -> Dict[str, str]:
        valid = [files for files in files_list if files]
        if not valid:
            return {}
        return max(valid, key=len)

    def scan_json_candidates(text: str) -> Dict[str, str]:
        decoder = json.JSONDecoder()
        parsed_files = []
        for match in re.finditer(r"[\[{]", text or ""):
            try:
                data, _ = decoder.raw_decode(text[match.start():])
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            parsed = parse_data(data)
            if parsed:
                parsed_files.append(parsed)
        return best(parsed_files)

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
    fenced_candidates = []
    for match in pattern.finditer(raw_output):
        try:
            files = parse_data(json.loads(match.group(1).strip()))
            if files:
                fenced_candidates.append(files)
        except (json.JSONDecodeError, TypeError):
            files = scan_json_candidates(match.group(1))
            if files:
                fenced_candidates.append(files)
    fenced_files = best(fenced_candidates)
    if fenced_files:
        return fenced_files

    scanned_files = scan_json_candidates(raw_output)
    if scanned_files:
        return scanned_files

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


def _prototype_focus_from_page_design(page_design_stage: Dict[str, Any]) -> str:
    """Build a deterministic prototype scope from page design output."""
    if not isinstance(page_design_stage, dict):
        return "未识别到页面设计范围；只能生成与用户需求最直接相关的 1 个核心页面。"

    structured = page_design_stage.get("structured_output")
    if not isinstance(structured, dict):
        structured = page_design_stage
    design_quality = structured.get("design_quality") if isinstance(structured, dict) else None
    primary_pages = _coerce_string_list(
        design_quality.get("primary_pages") if isinstance(design_quality, dict) else None,
        [],
    )

    document = str(page_design_stage.get("page_design_document") or page_design_stage.get("output") or "")
    if not document and isinstance(structured, dict):
        document = str(structured.get("output") or "")
    if not primary_pages and document:
        primary_pages = _extract_primary_pages_from_page_design_document(document)[:5]

    if not primary_pages:
        return "页面设计未声明多个主页面；生成与用户需求直接相关的页面及必要支撑组件。"

    page_list = "、".join(primary_pages[:8])
    declared_paths = _declared_frontend_paths_from_page_design_stage(page_design_stage)
    locked_paths = ""
    if declared_paths:
        locked_paths = (
            "页面设计已声明组件路径，prototype 文件名必须锁定为："
            + "、".join(f"`{path}`" for path in declared_paths[:12])
            + "。后续重试只能修改这些文件及必要 API/mock 文件，禁止随机改名或新增替代页面文件。"
        )
    if len(primary_pages) > 1:
        return (
            f"页面设计包含 {len(primary_pages)} 个主页面：{page_list}。"
            "本次 prototype 必须覆盖这些主页面，每个主页面都要有对应的真实前端页面文件；"
            "可复用同一个 API/mock/service 模块，但禁止只生成其中 1 个页面。"
            "重试时必须继续修同一组页面，不能减少页面数量或随机切换页面。"
            + locked_paths
        )
    return (
        f'本次 prototype 生成主页面：「{primary_pages[0]}」及必要支撑组件；'
        "重试时必须继续修同一组业务文件。"
        + locked_paths
    )


def _coerce_quality_score(value: Any, fallback: int) -> int:
    """把任意 LLM 质量分值规整为 0-100 整数。"""
    try:
        score = int(float(value))
    except (TypeError, ValueError):
        score = fallback
    return max(0, min(100, score))


def _coerce_bool(value: Any, fallback: bool) -> bool:
    """把字符串/布尔/null 规整成布尔（处理 true/yes/1/ready 等多种写法）。"""
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


def _normalized_contract_field_name(value: Any) -> str:
    """归一化契约字段名：去 queryParam./params. 等前缀和引号，便于跨端比对。"""
    field = str(value or "").strip()
    field = re.sub(r"^(?:this\.)?(?:queryParam|params|parameter|query|request|body|payload|form)\.", "", field)
    field = re.sub(r"^(?:query|body|request|param|params|payload)[\s:：=]+", "", field, flags=re.I)
    return field.strip("`'\" ")


def _first_review_field_value(item: Dict[str, Any], keys: List[str]) -> Any:
    """从 review item 中按多 key 候选取首个非空值（LLM 输出 key 命名不稳定）。"""
    for key in keys:
        if item.get(key):
            return item.get(key)
    return ""


def _review_field_mismatch_is_equivalent(item: Any) -> bool:
    """判断 field_mismatch 是否其实是「等价字段」（queryParam.id 与契约 id 是同一字段）。"""
    if not isinstance(item, dict):
        return False
    frontend_field = _normalized_contract_field_name(_first_review_field_value(item, [
        "frontend_field",
        "frontend_param",
        "frontend_parameter",
        "current_field",
        "actual_field",
    ]))
    contract_field = _normalized_contract_field_name(_first_review_field_value(item, [
        "contract_field",
        "api_field",
        "api_param",
        "api_parameter",
        "expected_field",
        "request_field",
    ]))
    if not frontend_field or not contract_field:
        return False
    return frontend_field == contract_field


def _review_suggestions_only_field_related(value: Any) -> bool:
    """判断审查建议是否只跟字段相关（用于过滤掉等价字段差异后清空 fix_suggestions）。"""
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    blocking_keywords = [
        "依赖",
        "异常",
        "兜底",
        "加载",
        "空状态",
        "页面形态",
        "接口不存在",
        "运行",
        "报错",
        "失败",
        "mock",
        "fallback",
        "loading",
        "empty",
        "runtime",
        "dependency",
    ]
    if any(keyword in lowered for keyword in blocking_keywords):
        return False
    field_keywords = ["字段", "参数", "param", "field", "queryparam", "contract", "api", "id"]
    return any(keyword in lowered for keyword in field_keywords)


def _normalize_code_review_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """规整 code_review 结果：过滤等价字段差异；若全部差异等价则判 PASS。"""
    mismatches = result.get("field_mismatches")
    if not isinstance(mismatches, list):
        return result

    actionable = [item for item in mismatches if not _review_field_mismatch_is_equivalent(item)]
    if len(actionable) == len(mismatches):
        return result

    failure_text = "\n".join(
        str(part or "")
        for part in (result.get("contract_alignment"), result.get("fix_suggestions"))
    )
    result["field_mismatches"] = actionable
    if not actionable:
        result["contract_alignment"] = "前端 queryParam 字段已与 API 契约请求参数对齐，无字段名不一致问题。"
        if _review_suggestions_only_field_related(failure_text):
            result["fix_suggestions"] = ""
            result["review_passed"] = True
    return result


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
