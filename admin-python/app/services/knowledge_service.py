"""知识库服务 - 知识CRUD、搜索、图谱维护"""
import time
import uuid
import json
import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.agent_models import AgentKnowledge, KnowledgeEdge, ProjectKnowledge
from app.models.models import ProjectTenantScope, SysAdmin, SysAdminGroup, SysAdminTenant, SysTenant

logger = logging.getLogger(__name__)


PROJECT_SKILL_HEADER = "Project Skill"
PROJECT_SKILL_MATCH_PROMPT = """你是需求入口的项目 Skill 路由器。请根据产品需求，从候选项目中选择最适合执行该需求的一个已确认 Project Skill。

要求：
1. 只能选择候选列表里的 project_id。
2. 优先匹配业务领域、页面/模块、API/权限/组件模式，而不是只看技术栈。
3. 如果多个候选都可用，选择业务语义最接近的项目。
4. 只输出 JSON，不要输出 markdown。

产品需求：
{requirement}

候选项目：
{candidates}

输出格式：
{{"project_id": 123, "confidence": 0.82, "match_reason": "选择原因，简明说明匹配到的业务关键词和 Skill 能力"}}
"""


def _parse_knowledge_tags(raw_tags: Any) -> List[str]:
    """Parse legacy tag payloads without letting bad data break search."""
    if raw_tags is None:
        return []

    if isinstance(raw_tags, list):
        values = raw_tags
    else:
        text = str(raw_tags).strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            parsed = [
                part.strip()
                for part in re.split(r"[,，;；\s]+", text)
                if part.strip()
            ]
        values = parsed if isinstance(parsed, list) else [parsed]
    return [str(item).strip() for item in values if str(item).strip()]


def _knowledge_graph_dedupe_key(record: AgentKnowledge) -> str:
    """Collapse recurring operational snapshots that otherwise flood the graph."""
    title = (record.title or "").strip()
    source = (record.source or "").strip()
    category = (record.category or "").strip()
    tags = _parse_knowledge_tags(record.tags)
    project_tag = next((tag for tag in tags if tag.startswith("project:")), "")

    if category == "ai_upgrade":
        return f"category:{category}:source:{source or 'auto_upgrade'}"
    if category == "project_analysis":
        normalized_title = re.sub(r"\s+", " ", title)
        return f"category:{category}:title:{normalized_title}"
    if category == "pipeline_delivery" and project_tag:
        request_tag = next((tag for tag in tags if tag.startswith("request:")), "")
        return f"category:{category}:{project_tag}:{request_tag}"
    if source:
        return f"source:{source}"
    return f"id:{record.knowledge_id}"


def _knowledge_graph_inferred_edges(nodes: List[AgentKnowledge], existing_edges: List[KnowledgeEdge]) -> List[Dict[str, Any]]:
    """Infer lightweight view-only graph edges from project ids and tags."""
    existing_pairs = {
        tuple(sorted((edge.source_id, edge.target_id)))
        for edge in existing_edges
    }
    generic_tags = {
        "ai", "upgrade", "frontier", "daily", "auto-analysis", "unknown",
        "pipeline_delivery", "project_profile", "project_knowledge", "skill",
    }
    inferred: List[Dict[str, Any]] = []
    per_node_count: Dict[str, int] = {}

    def tags_for(item: AgentKnowledge) -> set[str]:
        return {
            tag
            for tag in _parse_knowledge_tags(item.tags)
            if tag and tag not in generic_tags and not tag.startswith("stage:")
        }

    node_tags = {item.knowledge_id: tags_for(item) for item in nodes}

    for index, source in enumerate(nodes):
        source_tags = node_tags[source.knowledge_id]
        scored: List[tuple[float, AgentKnowledge, str]] = []
        for target in nodes[index + 1:]:
            pair = tuple(sorted((source.knowledge_id, target.knowledge_id)))
            if pair in existing_pairs:
                continue

            target_tags = node_tags[target.knowledge_id]
            shared_tags = source_tags & target_tags
            score = 0.0
            reason = "标签相关"

            if source.project_id and source.project_id == target.project_id:
                score += 0.5
                reason = "同项目"
            project_tags = {tag for tag in source_tags if tag.startswith("project:")} & {
                tag for tag in target_tags if tag.startswith("project:")
            }
            if project_tags:
                score += 0.45
                reason = "同项目"
            if shared_tags:
                score += min(0.45, len(shared_tags) * 0.12)
                reason = "共享标签"
            if source.category == target.category and source.category not in {"ai_upgrade"}:
                score += 0.12

            if score < 0.45:
                continue
            scored.append((min(score, 0.95), target, reason))

        for score, target, reason in sorted(scored, key=lambda item: item[0], reverse=True):
            if per_node_count.get(source.knowledge_id, 0) >= 3 or per_node_count.get(target.knowledge_id, 0) >= 3:
                continue
            inferred.append({
                "id": f"INFER-{source.knowledge_id}-{target.knowledge_id}",
                "source": source.knowledge_id,
                "target": target.knowledge_id,
                "relation": "related_to",
                "weight": round(score, 2),
                "description": f"Inferred: {reason}",
                "inferred": True,
            })
            per_node_count[source.knowledge_id] = per_node_count.get(source.knowledge_id, 0) + 1
            per_node_count[target.knowledge_id] = per_node_count.get(target.knowledge_id, 0) + 1

    return inferred


def _project_graph_role(project: ProjectKnowledge) -> str:
    name = (project.project_name or "").lower()
    if name.startswith("web-") or name.startswith("web_"):
        return "frontend"
    if "core" in name:
        return "core"
    if "service" in name:
        return "service"
    if name.endswith("-home") or name.endswith("_home") or "admin-home" in name:
        return "api"

    text = " ".join([
        project.project_name or "",
        project.project_brief or "",
        project.tech_summary or "",
        project.architecture or "",
    ]).lower()
    if any(term in text for term in ("core层", "model", "数据模型", "-core", "core")):
        return "core"
    if any(term in text for term in ("service层", "service layer", "-service", "service")):
        return "service"
    if any(term in text for term in ("controller", "接口", "api", "admin-home", "-home")):
        return "api"
    if any(term in text for term in ("前端", "frontend", "vue", "react", "web-")):
        return "frontend"
    return "project"


def _project_graph_edge(source: ProjectKnowledge, target: ProjectKnowledge, relation: str, weight: float, reason: str) -> Dict[str, Any]:
    return {
        "id": f"PROJECT-{source.project_id}-{relation}-{target.project_id}",
        "source": f"PROJECT-{source.project_id}",
        "target": f"PROJECT-{target.project_id}",
        "relation": relation,
        "weight": weight,
        "description": reason,
        "inferred": True,
    }


async def resolve_project_skill_tenant_scope(admin_id: int, tenant_id: int) -> Dict:
    """Resolve which tenant-scoped projects may participate in generation."""
    tenant_id = int(tenant_id or 0)
    admin_id = int(admin_id or 0)
    if not admin_id:
        return {"scope_type": "developer", "allowed_tenant_ids": [tenant_id] if tenant_id else []}

    async with async_session_maker() as session:
        result = await session.execute(select(SysAdmin).where(SysAdmin.id == admin_id, SysAdmin.is_deleted == 0))
        admin = result.scalar_one_or_none()
        if not admin:
            return {"scope_type": "developer", "allowed_tenant_ids": [tenant_id] if tenant_id else []}

        group = None
        if admin.admin_group_id:
            group_result = await session.execute(
                select(SysAdminGroup).where(SysAdminGroup.id == admin.admin_group_id, SysAdminGroup.status == 1)
            )
            group = group_result.scalar_one_or_none()

        if group and group.is_super == 1:
            tenant_result = await session.execute(
                select(SysTenant.id).where(SysTenant.status == 1, SysTenant.is_deleted == 0).order_by(SysTenant.id)
            )
            return {
                "scope_type": "system_admin",
                "allowed_tenant_ids": [int(row[0]) for row in tenant_result.all()],
            }

        tenant_result = await session.execute(
            select(SysAdminTenant.tenant_id).where(SysAdminTenant.admin_id == admin.id)
        )
        tenant_ids = [int(row[0]) for row in tenant_result.all()]
        if admin.tenant_id and int(admin.tenant_id) not in tenant_ids:
            tenant_ids.insert(0, int(admin.tenant_id))

    return {
        "scope_type": "project_admin" if len(tenant_ids) > 1 else "developer",
        "allowed_tenant_ids": sorted(set(tenant_ids or ([tenant_id] if tenant_id else []))),
    }


def _stringify_list(value: Any) -> List[str]:
    """Normalize DB JSON/text fields into a short string list."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
        return [part.strip() for part in value.splitlines() if part.strip()]
    return [str(value)]


def _json_contract_text(value: Any) -> str:
    """Store structured project-analysis contracts as stable JSON text."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        try:
            parsed = json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            return stripped
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    return json.dumps(value, ensure_ascii=False, indent=2)


def _format_contract_block(value: Any, fallback: str) -> str:
    text = _json_contract_text(value)
    return text or fallback


def _classify_requirement_for_knowledge(text: str) -> str:
    """Classify delivery knowledge for search/graph context without routing a live pipeline."""
    normalized = (text or "").strip()
    if not normalized:
        return "unknown"
    explicit_existing = bool(
        re.search(r"(现有|已有|原有|既有)(?:的)?(?:页面|列表|详情|表单|功能)", normalized)
        or re.search(r"当前(?:页面|列表|详情|表单|功能)", normalized)
    )
    page_creation_signal = any(
        marker in normalized
        for marker in ("页面位置建议", "页面位置", "页面功能", "菜单入口", "路由路径", "默认落点")
    )
    if page_creation_signal and not explicit_existing:
        return "new_page"
    if explicit_existing:
        return "existing_page_change"
    if re.search(r"(新增|新建|创建|搭建|生成|做一个|开发一个).{0,80}(页面|列表|详情|表单|管理|配置|功能|工作台|看板)", normalized):
        return "new_page"
    if re.search(r"(增加|添加|新增|补充|优化|调整|修改).{0,40}(筛选|查询|搜索|字段|按钮|表格|列)", normalized):
        return "existing_page_change"
    return "unknown"


def _attr(obj: Any, name: str, default: Any = "") -> Any:
    """Read object or dict values with one small helper for testability."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _build_project_skill_content(project: Any) -> str:
    """Build the human-editable project-level context skill."""
    project_name = _attr(project, "project_name") or _attr(project, "name") or "Unnamed Project"
    repo_url = _attr(project, "repo_url") or ""
    language = _attr(project, "language") or "unknown"
    framework = _attr(project, "framework") or "unknown"
    project_brief = (
        _attr(project, "project_brief")
        or _attr(project, "description")
        or f"{project_name} project from {repo_url or 'an unconfigured repository'} ({language}/{framework})."
    )
    key_files = _stringify_list(_attr(project, "key_files"))
    key_file_lines = "\n".join(f"- `{path}`" for path in key_files[:12]) or "- No key files detected"

    return f"""# {PROJECT_SKILL_HEADER}: {project_name}

## Project Brief
{project_brief}

## Repository
- URL: {repo_url or "N/A"}
- Language: {language}
- Framework: {framework}

## Technical Summary
{_attr(project, "tech_summary") or "No technical summary available."}

## Architecture
{_attr(project, "architecture") or "No architecture summary available."}

## UI And Component Patterns
{_attr(project, "component_patterns") or "No component patterns detected."}

## API Contract Patterns
{_attr(project, "api_patterns") or "No API patterns detected."}

## Permission Model
{_attr(project, "permission_model") or "No permission model detected."}

## Coding Style
{_attr(project, "coding_style") or "Follow the existing repository style."}

## Key Files
{key_file_lines}

## Structured Project Analysis Schema
{_format_contract_block(_attr(project, "project_analysis_schema"), "No structured analysis schema captured.")}

## Structured Generation Contract
{_format_contract_block(_attr(project, "generation_contract"), "No structured generation contract captured.")}

## Structured Verification Contract
{_format_contract_block(_attr(project, "verification_contract"), "No structured verification contract captured.")}

## Pipeline Execution Contract
Use this section as the source of truth when requirement, page design, prototype, delivery, code review, and report stages run.

### Project Analysis Checklist
- Identify whether the request is a new page, an existing-page change, or a shared component/API change before designing pages.
- Treat "页面位置建议", "页面功能", new menu placement, route/default-landing suggestions, and new management/configuration capability requests as new-page signals unless the user explicitly says an existing page must be changed.
- Existing page candidates are target files only for explicit existing/current/original page changes. For new pages, existing list/detail/form pages are style references only and must not be auto-selected as the implementation target.
- For ordinary admin/configuration CRUD pages, classify create/edit as a modal, drawer, or shared form component by default. Do not turn "新增/编辑" wording into separate primary create and edit route pages unless the requirement explicitly asks for independent routes, breadcrumbs, or multi-step forms.
- In action matrices, record user-visible commands only. Do not make drawer/modal/component names such as "新建/编辑抽屉" or "编辑弹窗" required button labels; those are support containers opened by visible commands like "新建批次" and row-level "编辑".
- Map business terms to repository terms: route names, menu names, component names, API module names, permission keys, and domain model names.
- Inspect existing examples for list pages, create/edit pages, detail pages, selector modals, export flows, and status actions before generating a new pattern.
- Record the exact response envelope, pagination fields, error-code shape, and auth/tenant headers used by this project.
- Record the command set needed to verify generated work: unit tests, lint/build, preview server, Playwright/e2e path, and known sandbox caveats.

### Frontend Generation Contract
- Follow existing route and directory conventions; do not invent unrelated `src/views/**/List.vue` or `src/pages/**/index.tsx` paths when a matching module already exists.
- Existing-page changes must preserve the original API flow, table columns, query params, mixins/hooks, permissions, and state handling unless the requirement explicitly asks to replace them.
- New page requests must create project-appropriate page paths from the requested menu/route/module semantics. Do not reuse an unrelated order/product/activity list page merely because it has similar CRUD controls.
- New admin/configuration CRUD pages should usually generate one list page plus create/edit modal/drawer support. A combined "新增/编辑" action is covered by one shared form component unless independent create/edit pages are explicitly required.
- Visible actions must use command labels, not container labels. Implement "新建/编辑抽屉" as a drawer/modal opened by "新建" and "编辑" controls instead of requiring a literal "新建/编辑抽屉" button.
- New pages must include preview-safe mock/fallback data in service/API files, but the mock shape must match the project API contract exactly.
- Every primary page from page design must have a corresponding page file. Support components, selector modals, and shared services may be reused across pages.
- List pages must follow the project table contract, including pagination input/output field names, empty list fallback, loading state, error state, and refresh behavior.
- Create/edit pages must define validation, submit loading, duplicate-submit protection, cancel/return path, and edit-mode data hydration.
- Detail pages must define missing-id handling, loading/error states, field fallback rendering, and links back to the source list.
- Selector modals must use real project component patterns, search/reset behavior, row selection, confirm/cancel behavior, and safe empty data.

### API And Data Contract
- Never relax the project response envelope into a generic `{{code, msg, data}}` or `{{code, message, data}}` unless that exact shape is confirmed in this skill.
- Page, list, count, total, records, current, size, and tenant/auth header names must match project conventions.
- Every page field used in UI must map to request/response/API-contract fields; equivalent aliases must be documented instead of silently invented.
- API modules must cover every page action declared in page design, including list/detail/save/update/status/export/manual actions.
- Mock data must include success, empty, and failure-safe examples that preserve the same field names as real responses.

### Permission And State Contract
- Map menu, route, button, row action, API, and data-scope permissions separately.
- Generated UI must use the project permission directive/helper exactly as existing pages do.
- For each status action, document visible/enabled/disabled rules, confirm copy, request payload, success refresh scope, and failure message.
- Do not hide missing permissions by removing actions from the design; record them as explicit permission requirements.

### Review Gates
- Requirement analysis must name the matched frontend and backend projects and list assumptions that affect design or development.
- Page design must include route/menu/default landing, primary-page list, support components, field tables, action matrix, state matrix, and API draft.
- Prototype must parse as structured file output and pass deterministic checks before human review.
- Code review must verify project conventions, field alignment, API coverage, permission coverage, page coverage, mock boundaries, and runnable preview assumptions.

## AGENTS.md Handoff Notes
- Keep this project skill concise enough to inject into prompts, but concrete enough that an agent can generate code without rereading the whole repository.
- If an agent discovers a repeated convention while fixing a pipeline failure, update the project analysis fields or this skill before rerunning future pipelines.
- Prefer adding deterministic validation for durable project rules instead of only adding prose to prompts.

## Development Guardrails
- Generate preview HTML, frontend code, and API contract first.
- Do not generate backend implementation in the first-version pipeline.
- Keep generated frontend code aligned with the existing routing, service, state, and permission patterns.
- When uncertain, preserve the current repository conventions instead of inventing new abstractions.
"""


def _format_project_skill_context(project: Any) -> str:
    """Return prompt context only for developer-confirmed project skills."""
    if (_attr(project, "skill_status") or "").lower() != "confirmed":
        return ""
    content = (_attr(project, "skill_content") or "").strip()
    if not content:
        return ""
    project_name = _attr(project, "project_name") or "Project"
    version = _attr(project, "skill_version") or 1
    return f"## Confirmed Project Skill: {project_name} (v{version})\n{content}"


def _project_skill_to_dict(project: Any) -> Dict:
    """Return a stable dict for either ORM rows or test dictionaries."""
    if isinstance(project, dict):
        data = dict(project)
        data.setdefault("repo_url", "")
        data.setdefault("language", "")
        data.setdefault("framework", "")
        data.setdefault("project_brief", "")
        data.setdefault("tech_summary", "")
        data.setdefault("architecture", "")
        data.setdefault("component_patterns", "")
        data.setdefault("api_patterns", "")
        data.setdefault("permission_model", "")
        data.setdefault("coding_style", "")
        data.setdefault("key_files", [])
        data.setdefault("project_analysis_schema", "")
        data.setdefault("generation_contract", "")
        data.setdefault("verification_contract", "")
        data.setdefault("analysis_status", "")
        data.setdefault("skill_content", "")
        data.setdefault("skill_status", "")
        data.setdefault("skill_version", 1)
        data.setdefault("confirmed_by", None)
        data.setdefault("confirmed_at", None)
        data.setdefault("analysis_error", "")
        return data
    return _knowledge_to_dict(project)


def _extract_match_terms(text: str) -> List[str]:
    """Extract simple Latin tokens and CJK n-grams for deterministic matching."""
    import re

    normalized = (text or "").lower()
    terms = set(re.findall(r"[a-z0-9_]{2,}", normalized))
    cjk_chunks = re.findall(r"[\u4e00-\u9fff]+", normalized)
    for chunk in cjk_chunks:
        if len(chunk) <= 4:
            terms.add(chunk)
            continue
        for size in (2, 3, 4):
            for index in range(0, len(chunk) - size + 1):
                terms.add(chunk[index:index + size])
    stop_terms = {
        "新增", "增加", "页面", "功能", "需求", "包含", "需要", "支持", "进行",
        "以及", "一个", "用户", "管理", "后台", "列表", "表格",
    }
    return sorted(term for term in terms if term not in stop_terms)


def _project_skill_match_text(skill: Dict) -> str:
    fields = [
        "project_name",
        "language",
        "framework",
        "project_brief",
        "tech_summary",
        "architecture",
        "component_patterns",
        "api_patterns",
        "permission_model",
        "coding_style",
        "skill_content",
    ]
    parts = [str(skill.get(field) or "") for field in fields]
    parts.extend(_stringify_list(skill.get("key_files")))
    return "\n".join(parts).lower()


def select_project_skill_match(requirement: str, candidates: List[Any]) -> Optional[Dict]:
    """Select the most relevant confirmed Project Skill for a product requirement.

    The LLM-backed service uses this same output shape as a deterministic fallback,
    which keeps tests stable and makes the match reason explainable when LLM config
    is unavailable.
    """
    requirement = (requirement or "").strip()
    if not requirement:
        return None

    skills = [
        _project_skill_to_dict(candidate)
        for candidate in candidates
        if (_attr(candidate, "skill_status") or "").lower() == "confirmed"
        and (_attr(candidate, "skill_content") or "").strip()
    ]
    if not skills:
        return None

    terms = _extract_match_terms(requirement)
    scored = []
    for skill in skills:
        text = _project_skill_match_text(skill)
        matched_terms = [term for term in terms if term in text]
        score = 0.0
        for term in matched_terms:
            if term in str(skill.get("project_name") or "").lower():
                score += 2.5
            elif term in str(skill.get("project_brief") or "").lower():
                score += 2.0
            elif term in str(skill.get("skill_content") or "").lower():
                score += 1.5
            else:
                score += 1.0
        if requirement.lower() in text:
            score += 4.0
        score += min(float(skill.get("skill_version") or 1) * 0.01, 0.08)
        scored.append((score, len(matched_terms), skill, matched_terms))

    scored.sort(key=lambda item: (item[0], item[1], int(item[2].get("skill_version") or 0)), reverse=True)
    best_score, _, best_skill, matched_terms = scored[0]
    confidence = (
        0.12
        if best_score <= 0
        else min(0.95, round(0.25 + (best_score / (best_score + 12.0)) * 0.7, 2))
    )
    highlighted_terms = matched_terms[:8]
    match_reason = (
        f"规则兜底匹配到关键词：{', '.join(highlighted_terms)}"
        if highlighted_terms
        else "规则兜底未发现强业务关键词，选择最新的已确认 Project Skill"
    )

    return {
        "skill": best_skill,
        "confidence": confidence,
        "match_reason": match_reason,
        "match_source": "rule",
        "candidates_considered": len(skills),
    }


def select_backend_project_skill_match(requirement: str, candidates: List[Any]) -> Optional[Dict]:
    """Select a backend/API implementation Project Skill.

    Backend repos often split service/API code from core/model packages. Product
    feature requests should prefer the service/API layer over a model-only core
    package even when both share broad business keywords.
    """
    requirement = (requirement or "").strip()
    if not requirement:
        return None

    skills = [
        _project_skill_to_dict(candidate)
        for candidate in candidates
        if (_attr(candidate, "skill_status") or "").lower() == "confirmed"
        and (_attr(candidate, "skill_content") or "").strip()
    ]
    if not skills:
        return None

    terms = _extract_match_terms(requirement)
    feature_request = any(
        token in requirement
        for token in ("新增", "新建", "增加", "开发", "系统", "模块", "功能", "接口", "页面", "管理")
    )
    service_signals = (
        "service", "api", "controller", "mapper", "mybatis", "spring boot", "spring-boot",
        "dubbo", "rpc", "业务逻辑", "服务层", "service层", "dao", "rest", "接口",
    )
    core_only_signals = (
        "core", "model", "dto", "vo", "result", "基础核心", "纯后端服务基础核心模块",
        "数据模型定义", "model层", "core层", "实体", "pojo",
    )

    scored = []
    for skill in skills:
        text = _project_skill_match_text(skill)
        project_name = str(skill.get("project_name") or "").lower()
        project_brief = str(skill.get("project_brief") or "").lower()
        matched_terms = [term for term in terms if term in text]
        score = 0.0

        for term in matched_terms:
            if term in project_name:
                score += 2.5
            elif term in project_brief:
                score += 2.0
            elif term in str(skill.get("skill_content") or "").lower():
                score += 1.5
            else:
                score += 1.0

        service_hits = [signal for signal in service_signals if signal in text or signal in project_name]
        core_hits = [signal for signal in core_only_signals if signal in text or signal in project_name]

        if service_hits:
            score += min(5.0, 1.4 * len(service_hits))
        if feature_request and ("service" in project_name or "api" in project_name):
            score += 3.0
        if feature_request and ("core" in project_name or "model" in project_name):
            score -= 5.0
        if core_hits and not any(signal in project_name for signal in ("service", "api")):
            score -= min(4.0, 0.8 * len(core_hits))

        score += min(float(skill.get("skill_version") or 1) * 0.01, 0.08)
        scored.append((score, len(matched_terms), len(service_hits), skill, matched_terms, service_hits, core_hits))

    scored.sort(
        key=lambda item: (item[0], item[1], item[2], int(item[3].get("skill_version") or 0)),
        reverse=True,
    )
    best_score, _, _, best_skill, matched_terms, service_hits, core_hits = scored[0]
    confidence = (
        0.12
        if best_score <= 0
        else min(0.95, round(0.25 + (best_score / (best_score + 12.0)) * 0.7, 2))
    )
    reason_parts = []
    if matched_terms:
        reason_parts.append(f"业务关键词：{', '.join(matched_terms[:6])}")
    if service_hits:
        reason_parts.append(f"后端实现层信号：{', '.join(service_hits[:4])}")
    if core_hits:
        reason_parts.append("已降低 core/model-only 项目优先级")
    match_reason = "；".join(reason_parts) or "按后端项目角色和业务上下文选择最相关的已确认 Project Skill"

    return {
        "skill": best_skill,
        "confidence": confidence,
        "match_reason": match_reason,
        "match_source": "backend_role_rule",
        "candidates_considered": len(skills),
    }


def _backend_layer_rank(skill: Dict) -> int:
    text = _project_skill_match_text(skill)
    project_name = str(skill.get("project_name") or "").lower()
    if "controller" in text or "接口项目" in text or project_name.endswith("-home") or "admin-home" in project_name:
        return 0
    if "service" in project_name or "service层" in text or "业务逻辑" in text:
        return 1
    if "core" in project_name or "core层" in text or "model" in text or "数据模型定义" in text:
        return 2
    return 3


def _backend_business_terms(skill: Dict) -> set:
    text = f"{skill.get('project_name') or ''}\n{skill.get('project_brief') or ''}\n{skill.get('skill_content') or ''}"
    terms = set()
    for term in ("商品管理平台", "商城管理平台", "供应链中台", "酒店智能体管理平台", "管理平台"):
        if term in text:
            terms.add(term)
    for term in _extract_match_terms(str(skill.get("project_brief") or "")):
        if len(term) >= 3:
            terms.add(term)
    return terms


def select_backend_project_skill_matches(requirement: str, candidates: List[Any]) -> Optional[Dict]:
    """Select an associated backend project group for layered Dubbo systems."""
    base_match = select_backend_project_skill_match(requirement, candidates)
    if not base_match:
        return None

    skills = [
        _project_skill_to_dict(candidate)
        for candidate in candidates
        if (_attr(candidate, "skill_status") or "").lower() == "confirmed"
        and (_attr(candidate, "skill_content") or "").strip()
    ]
    best_skill = base_match["skill"]
    best_terms = _backend_business_terms(best_skill)
    requirement_terms = set(_extract_match_terms(requirement))

    associated = []
    for skill in skills:
        skill_terms = _backend_business_terms(skill)
        same_business = bool(best_terms and skill_terms and best_terms.intersection(skill_terms))
        skill_text = _project_skill_match_text(skill)
        requirement_related = any(term in skill_text for term in requirement_terms)
        if same_business or requirement_related or skill.get("project_id") == best_skill.get("project_id"):
            associated.append(skill)

    associated.sort(key=lambda skill: (_backend_layer_rank(skill), str(skill.get("project_name") or "")))
    unique = []
    seen = set()
    for skill in associated:
        project_id = skill.get("project_id")
        if project_id in seen:
            continue
        seen.add(project_id)
        unique.append(skill)

    layer_labels = ["controller/API层", "service层", "core/model层", "后端项目"]
    matches = []
    for skill in unique:
        layer_label = layer_labels[_backend_layer_rank(skill)]
        matches.append(
            {
                "skill": skill,
                "confidence": base_match["confidence"],
                "match_reason": f"后端项目组匹配：{skill.get('project_name')}（{layer_label}）",
                "match_source": "backend_project_group",
                "match_tags": ["Dubbo分层项目组", layer_label],
                "candidates_considered": base_match["candidates_considered"],
            }
        )
    return {
        **base_match,
        "skill": matches[0]["skill"],
        "match_reason": "识别到 Dubbo 分层后端项目组，已同时匹配 controller/API、service 和 core/model 关联项目。",
        "match_source": "backend_project_group",
        "match_tags": ["Dubbo分层项目组"],
        "matches": matches,
    }


def _build_match_candidate_prompt(skills: List[Dict]) -> str:
    brief_candidates = []
    for skill in skills[:20]:
        brief_candidates.append({
            "project_id": skill.get("project_id"),
            "project_name": skill.get("project_name"),
            "language": skill.get("language"),
            "framework": skill.get("framework"),
            "project_brief": (skill.get("project_brief") or "")[:300],
            "tech_summary": (skill.get("tech_summary") or "")[:240],
            "skill_excerpt": (skill.get("skill_content") or "")[:600],
        })
    return json.dumps(brief_candidates, ensure_ascii=False, indent=2)


def _parse_match_json(raw: str) -> Optional[Dict]:
    if not raw:
        return None
    text = str(raw).strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


async def _select_project_skill_match_with_llm(requirement: str, skills: List[Dict]) -> Optional[Dict]:
    try:
        from app.ai.agents import AgentFactory
        async with async_session_maker() as cfg_session:
            await AgentFactory.load_llm_from_db(cfg_session)
        agent = AgentFactory.get_agent("PM")
        if not agent:
            return None
        prompt = PROJECT_SKILL_MATCH_PROMPT.format(
            requirement=requirement,
            candidates=_build_match_candidate_prompt(skills),
        )
        raw_output = await agent.process(prompt, [])
        parsed = _parse_match_json(raw_output)
    except Exception as e:
        logger.warning(f"LLM project Skill match failed, using deterministic fallback: {e}")
        return None

    if not parsed:
        return None
    selected_id = str(parsed.get("project_id") or "")
    selected = next((skill for skill in skills if str(skill.get("project_id")) == selected_id), None)
    if not selected:
        return None
    try:
        confidence = float(parsed.get("confidence", 0.75))
    except (TypeError, ValueError):
        confidence = 0.75
    return {
        "skill": selected,
        "confidence": max(0.0, min(0.99, round(confidence, 2))),
        "match_reason": str(parsed.get("match_reason") or "LLM selected the closest confirmed Project Skill."),
        "match_source": "llm",
        "candidates_considered": len(skills),
    }


class KnowledgeService:
    """知识库服务

    负责知识条目的全生命周期管理，包括：
    - 知识CRUD（创建、读取、更新、删除）
    - 关键词搜索（ILIKE文本匹配，支持分类和标签过滤）
    - 知识图谱维护（边的创建、删除、遍历、图谱导出）
    - 自动关联（基于标签重叠和分类匹配自动建立边）
    - 统计信息（知识条目数、边数、分类分布）
    """

    # ---- CRUD ----

    @staticmethod
    async def get_project_graph(
        tenant_id: int = 1,
        max_nodes: int = 50,
    ) -> Dict[str, Any]:
        """获取项目关系图谱，不混入流水线交付或日报知识条目。"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(ProjectKnowledge)
                .where(ProjectKnowledge.tenant_id.in_([tenant_id, 0]))
                .order_by(ProjectKnowledge.update_time.desc())
                .limit(max_nodes)
            )
            projects = result.scalars().all()

        if not projects:
            return {"nodes": [], "edges": []}

        roles = {project.project_id: _project_graph_role(project) for project in projects}
        api_projects = [project for project in projects if roles[project.project_id] == "api"]
        service_projects = [project for project in projects if roles[project.project_id] == "service"]
        core_projects = [project for project in projects if roles[project.project_id] == "core"]
        frontend_projects = [project for project in projects if roles[project.project_id] == "frontend"]

        edges: List[Dict[str, Any]] = []
        seen_edges: set[tuple[int, int, str]] = set()

        def add_edge(source: ProjectKnowledge, target: ProjectKnowledge, relation: str, weight: float, reason: str) -> None:
            key = (source.project_id, target.project_id, relation)
            if source.project_id == target.project_id or key in seen_edges:
                return
            seen_edges.add(key)
            edges.append(_project_graph_edge(source, target, relation, weight, reason))

        for frontend in frontend_projects:
            for api_project in api_projects:
                add_edge(frontend, api_project, "uses_api", 0.9, "前端项目调用接口项目")

        for api_project in api_projects:
            for service in service_projects:
                add_edge(api_project, service, "depends_on", 0.9, "接口项目依赖服务层")

        for service in service_projects:
            for core in core_projects:
                add_edge(service, core, "depends_on", 0.9, "服务层依赖 core 层")

        ignored_tokens = {"web", "agent", "wealth", "glsw"}
        for left_index, left in enumerate(projects):
            left_tokens = {
                item
                for item in re.split(r"[-_\\s]+", (left.project_name or "").lower())
                if item and item not in ignored_tokens
            }
            for right in projects[left_index + 1:]:
                if any(
                    (left.project_id, right.project_id, relation) in seen_edges
                    or (right.project_id, left.project_id, relation) in seen_edges
                    for relation in ("uses_api", "depends_on", "related_to")
                ):
                    continue
                right_tokens = {
                    item
                    for item in re.split(r"[-_\\s]+", (right.project_name or "").lower())
                    if item and item not in ignored_tokens
                }
                if left_tokens & right_tokens:
                    add_edge(left, right, "related_to", 0.45, "项目名称或业务域相关")

        role_labels = {
            "frontend": "前端项目",
            "api": "接口项目",
            "service": "服务层项目",
            "core": "Core 项目",
            "project": "项目",
        }
        return {
            "nodes": [
                {
                    "id": f"PROJECT-{project.project_id}",
                    "title": project.project_name,
                    "category": roles[project.project_id],
                    "tags": [
                        role_labels.get(roles[project.project_id], "项目"),
                        project.language or "",
                        project.framework or "",
                        f"skill:{project.skill_status or 'draft'}",
                    ],
                    "project_id": project.project_id,
                }
                for project in projects
            ],
            "edges": edges,
        }

    @staticmethod
    def review_project_graph(graph: Dict[str, Any]) -> Dict[str, Any]:
        """Review project graph quality from multiple agent perspectives."""
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        node_ids = {node.get("id") for node in nodes}
        degree: Dict[str, int] = {str(node.get("id")): 0 for node in nodes}
        for edge in edges:
            if edge.get("source") in degree:
                degree[str(edge.get("source"))] += 1
            if edge.get("target") in degree:
                degree[str(edge.get("target"))] += 1

        roles: Dict[str, List[Dict[str, Any]]] = {}
        for node in nodes:
            roles.setdefault(str(node.get("category") or "project"), []).append(node)

        findings: List[Dict[str, str]] = []
        warnings: List[Dict[str, str]] = []

        def add(agent: str, message: str, severity: str = "blocker") -> None:
            target = warnings if severity == "warning" else findings
            target.append({"agent": agent, "message": message, "severity": severity})

        if not nodes:
            add("PM", "Project graph has no project nodes.")
        if any(not str(node.get("id", "")).startswith("PROJECT-") for node in nodes):
            add("Architect", "Project graph contains non-project nodes.")
        if len(node_ids) != len(nodes):
            add("Architect", "Project graph contains duplicate project node ids.")
        if nodes and not edges:
            add("Architect", "Project graph has project nodes but no relationships.")

        for node in nodes:
            if len(nodes) > 1 and degree.get(str(node.get("id")), 0) == 0:
                add("Architect", f"Project node is isolated: {node.get('title')}")
            if any(str(tag).startswith("skill:draft") for tag in (node.get("tags") or [])):
                add("PM", f"Project Skill is still draft: {node.get('title')}", severity="warning")

        frontend_ids = {node.get("id") for node in roles.get("frontend", [])}
        api_ids = {node.get("id") for node in roles.get("api", [])}
        service_ids = {node.get("id") for node in roles.get("service", [])}
        core_ids = {node.get("id") for node in roles.get("core", [])}

        for frontend_id in frontend_ids:
            if not any(edge.get("source") == frontend_id and edge.get("target") in api_ids for edge in edges):
                title = next((node.get("title") for node in nodes if node.get("id") == frontend_id), frontend_id)
                add("FE", f"Frontend project is not connected to an API project: {title}")

        for api_id in api_ids:
            if service_ids and not any(edge.get("source") == api_id and edge.get("target") in service_ids for edge in edges):
                title = next((node.get("title") for node in nodes if node.get("id") == api_id), api_id)
                add("BE", f"API project is not connected to a service project: {title}")

        for service_id in service_ids:
            if core_ids and not any(edge.get("source") == service_id and edge.get("target") in core_ids for edge in edges):
                title = next((node.get("title") for node in nodes if node.get("id") == service_id), service_id)
                add("BE", f"Service project is not connected to a core project: {title}")

        return {
            "passed": not findings,
            "findings": findings,
            "warnings": warnings,
            "summary": {
                "nodes": len(nodes),
                "edges": len(edges),
                "roles": {role: len(items) for role, items in roles.items()},
                "isolated": sum(1 for value in degree.values() if value == 0),
            },
        }

    @staticmethod
    async def record_project_graph_review(
        graph: Dict[str, Any],
        review: Dict[str, Any],
        tenant_id: int = 1,
    ) -> Optional[AgentKnowledge]:
        """Persist the latest project graph review into the knowledge base."""
        source = f"project_graph_review:{tenant_id}"
        now = int(time.time() * 1000)
        content = json.dumps(
            {
                "graph": graph,
                "review": review,
                "updated_at": now,
            },
            ensure_ascii=False,
            indent=2,
        )
        async with async_session_maker() as session:
            result = await session.execute(
                select(AgentKnowledge).where(
                    AgentKnowledge.source == source,
                    AgentKnowledge.tenant_id == tenant_id,
                    AgentKnowledge.is_deleted == 0,
                )
            )
            knowledge = result.scalar_one_or_none()
            if knowledge:
                knowledge.title = "项目关系图谱维护报告"
                knowledge.content = content
                knowledge.category = "project_graph"
                knowledge.tags = json.dumps(["project_graph", "project_relation", "multi_agent_review"], ensure_ascii=False)
                knowledge.update_time = now
                knowledge.version = (knowledge.version or 1) + 1
                knowledge.embedding_status = "pending"
            else:
                knowledge = AgentKnowledge(
                    knowledge_id=f"KN-{uuid.uuid4().hex[:12].upper()}",
                    title="项目关系图谱维护报告",
                    content=content,
                    category="project_graph",
                    tags=json.dumps(["project_graph", "project_relation", "multi_agent_review"], ensure_ascii=False),
                    source=source,
                    tenant_id=tenant_id,
                    version=1,
                    embedding_status="pending",
                    status=1,
                    create_time=now,
                    update_time=now,
                    is_deleted=0,
                )
                session.add(knowledge)
            await session.commit()
            await session.refresh(knowledge)
            return knowledge

    @staticmethod
    async def rebuild_project_graph_with_review(
        project_ids: Optional[List[int]] = None,
        tenant_id: int = 1,
        max_iterations: int = 3,
        force_analyze: bool = True,
    ) -> Dict[str, Any]:
        """Analyze projects, rebuild the project graph, and iterate review until clean."""
        if project_ids is None:
            project_ids = []
            try:
                import httpx
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get("http://admin-generator:8082/generator/projects", params={"page": 1, "page_size": 200})
                    if resp.status_code == 200:
                        payload = resp.json().get("data") or {}
                        if isinstance(payload, list):
                            items = payload
                        else:
                            items = payload.get("list") or payload.get("items") or []
                        project_ids = [
                            int(item.get("id"))
                            for item in items
                            if item.get("id") is not None and item.get("repo_url")
                        ]
            except Exception as exc:
                logger.warning("Failed to list generator projects for graph rebuild: %s", exc)

            if not project_ids:
                async with async_session_maker() as session:
                    result = await session.execute(
                        select(ProjectKnowledge.project_id).where(
                            ProjectKnowledge.tenant_id.in_([tenant_id, 0])
                        )
                    )
                    project_ids = [int(row[0]) for row in result.all()]

        analyzed: List[Dict[str, Any]] = []
        for project_id in project_ids:
            try:
                analyzed_item = await analyze_project(str(project_id), force=force_analyze)
                if analyzed_item:
                    analyzed.append(analyzed_item)
            except Exception as exc:
                logger.warning("Project graph rebuild analysis failed for project %s: %s", project_id, exc)

        iterations: List[Dict[str, Any]] = []
        graph: Dict[str, Any] = {"nodes": [], "edges": []}
        review: Dict[str, Any] = {"passed": False, "findings": [], "warnings": []}
        for iteration in range(1, max(1, max_iterations) + 1):
            graph = await KnowledgeService.get_project_graph(
                tenant_id=tenant_id,
                max_nodes=max(len(project_ids or []) + 10, 50),
            )
            review = KnowledgeService.review_project_graph(graph)
            iterations.append({
                "iteration": iteration,
                "passed": review["passed"],
                "findings": review.get("findings", []),
                "warnings": review.get("warnings", []),
                "summary": review.get("summary", {}),
            })
            if review["passed"]:
                break

        await KnowledgeService.record_project_graph_review(graph, review, tenant_id=tenant_id)
        return {
            "project_ids": project_ids,
            "analyzed_count": len(analyzed),
            "graph": graph,
            "review": review,
            "iterations": iterations,
        }

    @staticmethod
    async def create_knowledge(
        title: str,
        content: str,
        tenant_id: int = 1,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        source: Optional[str] = None,
        project_id: Optional[int] = None,
        status: int = 1,
    ) -> AgentKnowledge:
        """创建知识条目

        Args:
            title: 知识标题
            content: 知识正文内容
            tenant_id: 租户ID，默认为1
            category: 知识分类
            tags: 标签列表，存储为JSON字符串
            source: 来源标识
            project_id: 关联项目ID

        Returns:
            创建的知识实体
        """
        async with async_session_maker() as session:
            knowledge = AgentKnowledge(
                knowledge_id=f"KN-{uuid.uuid4().hex[:12].upper()}",
                title=title,
                content=content,
                category=category,
                tags=json.dumps(tags, ensure_ascii=False) if tags else None,
                source=source,
                project_id=project_id,
                tenant_id=tenant_id,
                version=1,
                embedding_status="pending",
                status=status,
            )
            session.add(knowledge)
            await session.commit()
            await session.refresh(knowledge)
            logger.info(f"创建知识条目: {knowledge.knowledge_id}, title={title}")
            return knowledge

    @staticmethod
    async def record_pipeline_delivery(
        pipeline_id: str,
        user_request: str,
        stages: Dict[str, Any],
        skill_config: Optional[Dict[str, Any]] = None,
        tenant_id: int = 1,
        creator_id: Optional[int] = None,
    ) -> Optional[AgentKnowledge]:
        """Create/update delivery knowledge and graph links for a completed pipeline.

        Pipeline delivery knowledge is evidence from one completed workflow. It
        should enrich search and graph context without overwriting confirmed
        Project Skill content.
        """
        pipeline_id = str(pipeline_id or "").strip()
        if not pipeline_id:
            return None

        skill_config = skill_config or {}
        project_snapshot = skill_config.get("project_skill_snapshot") or {}
        backend_snapshots = skill_config.get("backend_project_skill_snapshots") or []
        if not backend_snapshots and skill_config.get("backend_project_skill_snapshot"):
            backend_snapshots = [skill_config.get("backend_project_skill_snapshot") or {}]

        project_id_raw = (
            skill_config.get("frontend_project_id")
            or project_snapshot.get("project_id")
            or skill_config.get("project_id")
        )
        try:
            project_id = int(project_id_raw) if project_id_raw not in (None, "") else None
        except (TypeError, ValueError):
            project_id = None

        def clip(value: Any, limit: int = 1800) -> str:
            text = value if isinstance(value, str) else json.dumps(value or {}, ensure_ascii=False, indent=2)
            text = text.strip()
            return text if len(text) <= limit else text[:limit] + "\n...（已截断）"

        stage_sections: List[str] = []
        for stage in ("requirement", "page_design", "prototype", "delivery", "code_review", "report"):
            data = stages.get(stage) or {}
            output = str(data.get("output") or "").strip()
            structured = data.get("structured_output") or {}
            if not output and not structured:
                continue
            section = [
                f"## {stage}",
                f"status: {data.get('status') or ''}",
            ]
            if output:
                section.append(clip(output))
            if structured:
                keys = [key for key in ("files", "code_files", "review_passed", "fix_suggestions", "api_contract") if key in structured]
                if keys:
                    section.append("structured keys: " + ", ".join(keys))
            stage_sections.append("\n".join(section))

        frontend_files = (
            (stages.get("prototype") or {}).get("structured_output", {}).get("code_files")
            or (stages.get("prototype") or {}).get("code_files")
            or {}
        )
        file_paths = sorted(str(path) for path in (frontend_files or {}).keys())[:30]
        project_name = project_snapshot.get("project_name") or f"project-{project_id or 'unknown'}"
        source = f"pipeline_delivery:{pipeline_id}"
        title = f"流水线交付: {pipeline_id} - {clip(user_request, 60).replace(chr(10), ' ')}"
        request_classification = _classify_requirement_for_knowledge(user_request)
        tags = [
            "pipeline_delivery",
            f"pipeline:{pipeline_id}",
            f"project:{project_id}" if project_id else "project:unknown",
            f"request:{request_classification}",
            str(project_name),
        ]
        for stage in stages:
            tags.append(f"stage:{stage}")
        for snapshot in backend_snapshots[:5]:
            if snapshot.get("project_id"):
                tags.append(f"backend_project:{snapshot.get('project_id')}")
            if snapshot.get("project_name"):
                tags.append(str(snapshot.get("project_name")))
        tags = list(dict.fromkeys([tag for tag in tags if tag]))
        while tags and len(json.dumps(tags, ensure_ascii=False)) > 240:
            tags.pop()

        content_parts = [
            f"# 流水线交付知识\n",
            f"- pipeline_id: {pipeline_id}",
            f"- frontend_project: {project_name} ({project_id or '-'})",
            f"- request_classification: {request_classification}",
            f"- creator_id: {creator_id or '-'}",
            "",
            "## 原始需求",
            clip(user_request, 1200),
            "",
            "## 生成/修改文件",
            "\n".join(f"- {path}" for path in file_paths) if file_paths else "- 暂无前端文件",
            "",
            "## 阶段摘要",
            "\n\n".join(stage_sections) if stage_sections else "暂无阶段摘要",
        ]
        content = "\n".join(content_parts)

        async with async_session_maker() as session:
            existing_result = await session.execute(
                select(AgentKnowledge).where(
                    AgentKnowledge.source == source,
                    AgentKnowledge.tenant_id == tenant_id,
                    AgentKnowledge.is_deleted == 0,
                )
            )
            knowledge = existing_result.scalar_one_or_none()
            now = int(time.time() * 1000)
            if knowledge:
                knowledge.title = title
                knowledge.content = content
                knowledge.category = "pipeline_delivery"
                knowledge.tags = json.dumps(tags, ensure_ascii=False)
                knowledge.project_id = project_id
                knowledge.update_time = now
                knowledge.version = (knowledge.version or 1) + 1
                knowledge.embedding_status = "pending"
            else:
                knowledge = AgentKnowledge(
                    knowledge_id=f"KN-{uuid.uuid4().hex[:12].upper()}",
                    title=title,
                    content=content,
                    category="pipeline_delivery",
                    tags=json.dumps(tags, ensure_ascii=False),
                    source=source,
                    project_id=project_id,
                    tenant_id=tenant_id,
                    version=1,
                    embedding_status="pending",
                    status=1,
                )
                session.add(knowledge)
            await session.commit()
            await session.refresh(knowledge)

        await KnowledgeService._link_pipeline_delivery_knowledge(
            knowledge.knowledge_id,
            project_id=project_id,
            pipeline_id=pipeline_id,
            tenant_id=tenant_id,
        )
        try:
            await KnowledgeService.auto_link(knowledge.knowledge_id, tenant_id=tenant_id)
        except Exception as exc:
            logger.warning("Pipeline delivery auto_link failed for %s: %s", pipeline_id, exc)
        return knowledge

    @staticmethod
    async def _link_pipeline_delivery_knowledge(
        knowledge_id: str,
        project_id: Optional[int],
        pipeline_id: str,
        tenant_id: int,
    ) -> None:
        async with async_session_maker() as session:
            targets: List[tuple[str, str, float, str]] = []
            if project_id:
                project_result = await session.execute(
                    select(AgentKnowledge)
                    .where(
                        AgentKnowledge.is_deleted == 0,
                        AgentKnowledge.tenant_id == tenant_id,
                        AgentKnowledge.project_id == project_id,
                        AgentKnowledge.category == "project_analysis",
                    )
                    .order_by(AgentKnowledge.update_time.desc())
                    .limit(3)
                )
                for item in project_result.scalars().all():
                    targets.append((item.knowledge_id, "derived_from", 0.9, "交付知识来源于项目分析上下文"))

                history_result = await session.execute(
                    select(AgentKnowledge)
                    .where(
                        AgentKnowledge.is_deleted == 0,
                        AgentKnowledge.tenant_id == tenant_id,
                        AgentKnowledge.project_id == project_id,
                        AgentKnowledge.category == "pipeline_delivery",
                        AgentKnowledge.knowledge_id != knowledge_id,
                    )
                    .order_by(AgentKnowledge.update_time.desc())
                    .limit(8)
                )
                for item in history_result.scalars().all():
                    targets.append((item.knowledge_id, "related_to", 0.65, "同一项目的历史流水线交付"))

            for target_id, relation_type, weight, description in targets:
                existing = await session.execute(
                    select(KnowledgeEdge).where(
                        KnowledgeEdge.is_deleted == 0,
                        KnowledgeEdge.source_id == knowledge_id,
                        KnowledgeEdge.target_id == target_id,
                        KnowledgeEdge.relation_type == relation_type,
                    )
                )
                if existing.scalar_one_or_none():
                    continue
                session.add(KnowledgeEdge(
                    edge_id=f"KE-{uuid.uuid4().hex[:12].upper()}",
                    source_id=knowledge_id,
                    target_id=target_id,
                    relation_type=relation_type,
                    weight=weight,
                    description=description,
                    tenant_id=tenant_id,
                ))
            await session.commit()
            logger.info("Recorded delivery knowledge graph links for pipeline %s", pipeline_id)

    @staticmethod
    async def get_knowledge(knowledge_id: str) -> Optional[AgentKnowledge]:
        """获取单条知识

        每次获取会自动增加浏览计数。

        Args:
            knowledge_id: 知识条目业务ID（KN-xxx格式）

        Returns:
            知识实体，不存在返回None
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(AgentKnowledge).where(
                    AgentKnowledge.knowledge_id == knowledge_id,
                    AgentKnowledge.is_deleted == 0,
                )
            )
            knowledge = result.scalar_one_or_none()
            if knowledge:
                knowledge.view_count += 1
                await session.commit()
            return knowledge

    @staticmethod
    async def update_knowledge(
        knowledge_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        source: Optional[str] = None,
        status: Optional[int] = None,
    ) -> Optional[AgentKnowledge]:
        """更新知识条目

        仅更新传入的非None字段。内容变更会自动递增版本号
        并将嵌入状态重置为pending。

        Args:
            knowledge_id: 知识条目业务ID
            title: 新标题（可选）
            content: 新内容（可选，变更时自动版本+1）
            category: 新分类（可选）
            tags: 新标签列表（可选）
            source: 新来源（可选）

        Returns:
            更新后的知识实体，不存在返回None
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(AgentKnowledge).where(
                    AgentKnowledge.knowledge_id == knowledge_id,
                    AgentKnowledge.is_deleted == 0,
                )
            )
            knowledge = result.scalar_one_or_none()
            if not knowledge:
                return None
            if title is not None:
                knowledge.title = title
            if content is not None:
                knowledge.content = content
                knowledge.version += 1
                knowledge.embedding_status = "pending"
            if category is not None:
                knowledge.category = category
            if tags is not None:
                knowledge.tags = json.dumps(tags, ensure_ascii=False)
            if source is not None:
                knowledge.source = source
            if status is not None:
                knowledge.status = status
            knowledge.update_time = int(time.time() * 1000)
            await session.commit()
            await session.refresh(knowledge)
            logger.info(f"更新知识条目: {knowledge_id}, version={knowledge.version}")
            return knowledge

    @staticmethod
    async def delete_knowledge(knowledge_id: str) -> bool:
        """软删除知识条目

        Args:
            knowledge_id: 知识条目业务ID

        Returns:
            是否删除成功（True=已删除，False=未找到）
        """
        async with async_session_maker() as session:
            result = await session.execute(
                update(AgentKnowledge)
                .where(AgentKnowledge.knowledge_id == knowledge_id)
                .values(is_deleted=1, update_time=int(time.time() * 1000))
            )
            await session.commit()
            success = result.rowcount > 0
            if success:
                logger.info(f"删除知识条目: {knowledge_id}")
            return success

    # ---- Search ----

    @staticmethod
    async def search_knowledge(
        query: str,
        tenant_id: int = 1,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """搜索知识 - 支持关键词、分类、标签过滤

        使用ILIKE对标题、内容、标签进行模糊匹配，
        结果按更新时间倒序排列。

        Args:
            query: 搜索关键词
            tenant_id: 租户ID
            category: 分类过滤
            tags: 标签过滤（暂未使用，预留）
            limit: 分页大小
            offset: 分页偏移量

        Returns:
            包含total、items、limit、offset的字典
        """
        async with async_session_maker() as session:
            conditions = [
                AgentKnowledge.is_deleted == 0,
                AgentKnowledge.tenant_id == tenant_id,
            ]
            if query:
                conditions.append(
                    or_(
                        AgentKnowledge.title.ilike(f"%{query}%"),
                        AgentKnowledge.content.ilike(f"%{query}%"),
                        AgentKnowledge.tags.ilike(f"%{query}%"),
                    )
                )
            if category:
                conditions.append(AgentKnowledge.category == category)

            where_clause = and_(*conditions)

            # Count
            count_result = await session.execute(
                select(func.count()).select_from(AgentKnowledge).where(where_clause)
            )
            total = count_result.scalar() or 0

            # Query
            result = await session.execute(
                select(AgentKnowledge)
                .where(where_clause)
                .order_by(AgentKnowledge.update_time.desc())
                .offset(offset)
                .limit(limit)
            )
            records = result.scalars().all()

            items = []
            for r in records:
                item = {
                    "knowledge_id": r.knowledge_id,
                    "title": r.title,
                    "category": r.category,
                    "tags": _parse_knowledge_tags(r.tags),
                    "source": r.source,
                    "status": r.status,
                    "version": r.version,
                    "view_count": r.view_count,
                    "create_time": r.create_time,
                    "update_time": r.update_time,
                }
                # For list view, truncate content to preview
                item["content_preview"] = (
                    r.content[:200] + "..." if len(r.content) > 200 else r.content
                )
                items.append(item)

            return {"total": total, "items": items, "limit": limit, "offset": offset}

    @staticmethod
    async def list_categories(tenant_id: int = 1) -> List[str]:
        """列出所有知识分类

        Args:
            tenant_id: 租户ID

        Returns:
            去重后的分类名称列表
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(AgentKnowledge.category)
                .where(
                    AgentKnowledge.is_deleted == 0,
                    AgentKnowledge.tenant_id == tenant_id,
                    AgentKnowledge.category.isnot(None),
                )
                .distinct()
            )
            return [r[0] for r in result.all()]

    @staticmethod
    async def list_tags(tenant_id: int = 1) -> List[str]:
        """列出所有标签

        从所有知识条目的tags JSON字段中提取并去重。

        Args:
            tenant_id: 租户ID

        Returns:
            去重并排序后的标签列表
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(AgentKnowledge.tags)
                .where(
                    AgentKnowledge.is_deleted == 0,
                    AgentKnowledge.tenant_id == tenant_id,
                    AgentKnowledge.tags.isnot(None),
                )
            )
            all_tags = set()
            for (tags_str,) in result.all():
                try:
                    all_tags.update(_parse_knowledge_tags(tags_str))
                except TypeError:
                    pass
            return sorted(all_tags)

    # ---- Knowledge Graph ----

    @staticmethod
    async def create_edge(
        source_id: str,
        target_id: str,
        relation_type: str,
        tenant_id: int = 1,
        weight: float = 1.0,
        description: Optional[str] = None,
    ) -> KnowledgeEdge:
        """创建知识图谱边

        Args:
            source_id: 起点知识条目ID
            target_id: 终点知识条目ID
            relation_type: 关系类型（depends_on, related_to, derived_from, supersedes, references）
            tenant_id: 租户ID
            weight: 关系权重（0.00~1.00）
            description: 关系描述

        Returns:
            创建的边实体
        """
        async with async_session_maker() as session:
            edge = KnowledgeEdge(
                edge_id=f"KE-{uuid.uuid4().hex[:12].upper()}",
                source_id=source_id,
                target_id=target_id,
                relation_type=relation_type,
                weight=weight,
                description=description,
                tenant_id=tenant_id,
            )
            session.add(edge)
            await session.commit()
            await session.refresh(edge)
            logger.info(
                f"创建知识边: {edge.edge_id}, {source_id} -> {target_id} ({relation_type})"
            )
            return edge

    @staticmethod
    async def delete_edge(edge_id: str) -> bool:
        """删除知识图谱边（软删除）

        Args:
            edge_id: 边业务ID（KE-xxx格式）

        Returns:
            是否删除成功
        """
        async with async_session_maker() as session:
            result = await session.execute(
                update(KnowledgeEdge)
                .where(KnowledgeEdge.edge_id == edge_id)
                .values(is_deleted=1)
            )
            await session.commit()
            success = result.rowcount > 0
            if success:
                logger.info(f"删除知识边: {edge_id}")
            return success

    @staticmethod
    async def get_related(
        knowledge_id: str,
        relation_type: Optional[str] = None,
        direction: str = "both",  # "outgoing", "incoming", "both"
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """获取相关知识（图谱遍历）

        沿着知识图谱边遍历，获取与指定知识条目直接相邻的节点和边。

        Args:
            knowledge_id: 知识条目业务ID
            relation_type: 过滤关系类型（可选）
            direction: 遍历方向 - outgoing（出边）、incoming（入边）、both（双向）
            limit: 每个方向的最大返回数量

        Returns:
            相邻边信息列表，包含方向、关联节点ID、关系类型、权重
        """
        async with async_session_maker() as session:
            conditions = [KnowledgeEdge.is_deleted == 0]

            if direction in ("outgoing", "both"):
                conditions_out = conditions + [
                    KnowledgeEdge.source_id == knowledge_id
                ]
                if relation_type:
                    conditions_out.append(
                        KnowledgeEdge.relation_type == relation_type
                    )
                out_result = await session.execute(
                    select(KnowledgeEdge).where(*conditions_out).limit(limit)
                )
                outgoing = out_result.scalars().all()
            else:
                outgoing = []

            if direction in ("incoming", "both"):
                conditions_in = conditions + [
                    KnowledgeEdge.target_id == knowledge_id
                ]
                if relation_type:
                    conditions_in.append(
                        KnowledgeEdge.relation_type == relation_type
                    )
                in_result = await session.execute(
                    select(KnowledgeEdge).where(*conditions_in).limit(limit)
                )
                incoming = in_result.scalars().all()
            else:
                incoming = []

            edges = []
            for e in outgoing:
                edges.append(
                    {
                        "edge_id": e.edge_id,
                        "direction": "outgoing",
                        "target_id": e.target_id,
                        "relation_type": e.relation_type,
                        "weight": float(e.weight) if e.weight else 1.0,
                        "description": e.description,
                    }
                )
            for e in incoming:
                edges.append(
                    {
                        "edge_id": e.edge_id,
                        "direction": "incoming",
                        "source_id": e.source_id,
                        "relation_type": e.relation_type,
                        "weight": float(e.weight) if e.weight else 1.0,
                        "description": e.description,
                    }
                )
            return edges

    @staticmethod
    async def get_graph(
        tenant_id: int = 1,
        category: Optional[str] = None,
        max_nodes: int = 50,
    ) -> Dict[str, Any]:
        """获取知识图谱（节点+边）

        导出指定租户的知识图谱数据，包含节点和节点之间的边。
        用于前端可视化展示。

        Args:
            tenant_id: 租户ID
            category: 按分类过滤节点（可选）
            max_nodes: 最大节点数量

        Returns:
            包含nodes和edges列表的字典
        """
        async with async_session_maker() as session:
            # Fetch a wider candidate pool, then collapse recurring snapshots so
            # the graph reads as knowledge relationships instead of an activity feed.
            node_conditions = [
                AgentKnowledge.is_deleted == 0,
                AgentKnowledge.tenant_id == tenant_id,
            ]
            if category:
                node_conditions.append(AgentKnowledge.category == category)

            nodes_result = await session.execute(
                select(AgentKnowledge)
                .where(*node_conditions)
                .order_by(AgentKnowledge.update_time.desc())
                .limit(max(max_nodes * 4, 120))
            )
            candidates = nodes_result.scalars().all()
            if not candidates:
                return {"nodes": [], "edges": []}

            candidate_ids = {n.knowledge_id for n in candidates}
            all_edges_result = await session.execute(
                select(KnowledgeEdge).where(
                    KnowledgeEdge.is_deleted == 0,
                    KnowledgeEdge.tenant_id == tenant_id,
                    or_(
                        KnowledgeEdge.source_id.in_(candidate_ids),
                        KnowledgeEdge.target_id.in_(candidate_ids),
                    ),
                )
            )
            all_edges = all_edges_result.scalars().all()
            degree: Dict[str, int] = {}
            for edge in all_edges:
                degree[edge.source_id] = degree.get(edge.source_id, 0) + 1
                degree[edge.target_id] = degree.get(edge.target_id, 0) + 1

            deduped: Dict[str, AgentKnowledge] = {}
            for item in candidates:
                key = _knowledge_graph_dedupe_key(item)
                current = deduped.get(key)
                if not current:
                    deduped[key] = item
                    continue
                current_score = (degree.get(current.knowledge_id, 0), current.update_time or 0)
                item_score = (degree.get(item.knowledge_id, 0), item.update_time or 0)
                if item_score > current_score:
                    deduped[key] = item

            ranked_nodes = sorted(
                deduped.values(),
                key=lambda item: (
                    1 if degree.get(item.knowledge_id, 0) else 0,
                    degree.get(item.knowledge_id, 0),
                    item.update_time or 0,
                ),
                reverse=True,
            )
            connected = [item for item in ranked_nodes if degree.get(item.knowledge_id, 0) > 0]
            isolated = [item for item in ranked_nodes if degree.get(item.knowledge_id, 0) == 0]
            isolated_limit = max(3, max_nodes // 5)
            nodes = (connected + isolated[:isolated_limit])[:max_nodes]
            node_ids = {n.knowledge_id for n in nodes}
            edges = [
                edge
                for edge in all_edges
                if edge.source_id in node_ids and edge.target_id in node_ids
            ]
            inferred_edges = _knowledge_graph_inferred_edges(nodes, edges)

            return {
                "nodes": [
                    {
                        "id": n.knowledge_id,
                        "title": n.title,
                        "category": n.category,
                        "tags": _parse_knowledge_tags(n.tags),
                    }
                    for n in nodes
                ],
                "edges": [
                    {
                        "id": e.edge_id,
                        "source": e.source_id,
                        "target": e.target_id,
                        "relation": e.relation_type,
                        "weight": float(e.weight) if e.weight else 1.0,
                    }
                    for e in edges
                ] + inferred_edges,
            }

    @staticmethod
    async def auto_link(knowledge_id: str, tenant_id: int = 1) -> int:
        """自动关联知识 - 基于标签和分类自动创建 related_to 边

        算法逻辑：
        1. 获取源知识的标签集和分类
        2. 遍历同租户下的其他知识条目
        3. 计算标签重叠数和分类是否相同
        4. 满足条件（标签有交集或分类相同）则自动创建边
        5. 权重根据标签重叠度和分类匹配度计算

        Args:
            knowledge_id: 源知识条目业务ID
            tenant_id: 租户ID

        Returns:
            新创建的边数量
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(AgentKnowledge).where(
                    AgentKnowledge.knowledge_id == knowledge_id,
                    AgentKnowledge.is_deleted == 0,
                )
            )
            source = result.scalar_one_or_none()
            if not source:
                return 0

            source_tags = set(_parse_knowledge_tags(source.tags))
            created = 0

            # Find knowledge with overlapping tags or same category
            candidates = await session.execute(
                select(AgentKnowledge)
                .where(
                    AgentKnowledge.is_deleted == 0,
                    AgentKnowledge.tenant_id == tenant_id,
                    AgentKnowledge.knowledge_id != knowledge_id,
                )
                .limit(100)
            )
            for candidate in candidates.scalars().all():
                cand_tags = set(_parse_knowledge_tags(candidate.tags))
                overlap = source_tags & cand_tags
                same_category = (
                    source.category
                    and source.category == candidate.category
                )

                if overlap or same_category:
                    # Check if edge already exists in either direction
                    existing = await session.execute(
                        select(KnowledgeEdge).where(
                            KnowledgeEdge.is_deleted == 0,
                            KnowledgeEdge.source_id == knowledge_id,
                            KnowledgeEdge.target_id == candidate.knowledge_id,
                        )
                    )
                    if not existing.scalar_one_or_none():
                        # Weight based on tag overlap ratio, capped at 1.0
                        weight = min(len(overlap) / 5.0, 1.0) if overlap else 0.3
                        if same_category:
                            weight = min(weight + 0.3, 1.0)
                        edge = KnowledgeEdge(
                            edge_id=f"KE-{uuid.uuid4().hex[:12].upper()}",
                            source_id=knowledge_id,
                            target_id=candidate.knowledge_id,
                            relation_type="related_to",
                            weight=weight,
                            description=(
                                f"Auto-linked: {len(overlap)} shared tags"
                                if overlap
                                else "Auto-linked: same category"
                            ),
                            tenant_id=tenant_id,
                        )
                        session.add(edge)
                        created += 1

            await session.commit()
            logger.info(
                f"自动关联知识: {knowledge_id}, 新建 {created} 条边"
            )
            return created

    # ---- Statistics ----

    @staticmethod
    async def get_stats(tenant_id: int = 1) -> Dict[str, Any]:
        """知识库统计信息

        Args:
            tenant_id: 租户ID

        Returns:
            包含总条目数、总边数、分类分布的字典
        """
        async with async_session_maker() as session:
            # Total knowledge count
            k_count = await session.execute(
                select(func.count())
                .select_from(AgentKnowledge)
                .where(
                    AgentKnowledge.is_deleted == 0,
                    AgentKnowledge.tenant_id == tenant_id,
                )
            )
            total_knowledge = k_count.scalar() or 0

            # Category breakdown
            cat_result = await session.execute(
                select(AgentKnowledge.category, func.count())
                .where(
                    AgentKnowledge.is_deleted == 0,
                    AgentKnowledge.tenant_id == tenant_id,
                )
                .group_by(AgentKnowledge.category)
            )
            categories = {
                r[0] or "uncategorized": r[1] for r in cat_result.all()
            }

            # Edge count
            e_count = await session.execute(
                select(func.count())
                .select_from(KnowledgeEdge)
                .where(
                    KnowledgeEdge.is_deleted == 0,
                    KnowledgeEdge.tenant_id == tenant_id,
                )
            )
            total_edges = e_count.scalar() or 0

            return {
                "total_knowledge": total_knowledge,
                "total_edges": total_edges,
                "categories": categories,
            }


knowledge_service = KnowledgeService()


# ==================== 项目知识自动分析 ===================

ANALYSIS_PROMPT = """你是一个资深的技术架构分析师。请分析以下项目的源代码，提炼出结构化的知识。

## 项目信息
- 名称: {name}
- 语言: {language}
- 框架: {framework}

## 项目源码关键文件
{files_text}

## 分析要求

请特别注意识别以下架构模式：
1. **BFF/API 转发层**：如果项目是 PHP 且主要功能是接收请求后转发到 Java/Go 等后端服务，请在 architecture 中明确标注 "BFF/API转发层"
2. **纯后端 API**：如果项目只提供 API 接口，标注 "纯后端API服务"
3. **前后端一体**：如果项目包含模板渲染+API，标注 "前后端一体"
4. **纯前端**：如果项目只有前端代码，标注 "纯前端SPA"

## 请输出 JSON 格式的分析结果（不要用 markdown 代码块包裹，直接输出 JSON）

{{
  "tech_summary": "技术栈总结（3-5句话描述项目用了什么技术、什么版本、什么构建工具）",
  "architecture": "架构描述（必须包含架构角色：BFF/API转发层/纯后端API服务/前后端一体/纯前端SPA。然后描述目录结构、分层设计、模块划分、路由组织方式）",
  "component_patterns": "组件/模块模式（常用组件封装方式、表单处理、表格处理、弹窗处理、请求转发模式等代码模式）",
  "api_patterns": "接口规范（接口路径风格、请求/响应格式、错误码规范、认证方式、转发目标地址模式）",
  "permission_model": "权限模型（路由权限、按钮权限、角色体系的实现方式）",
  "coding_style": "编码风格（命名规范、注释风格、文件组织习惯、状态管理方式）",
  "key_files": ["关键文件路径1", "关键文件路径2"],
  "project_analysis_schema": {{
    "request_classification": ["Explain how to distinguish a new page request, an existing page modification, a shared component change, and an API/backend change."],
    "new_page_signals": ["List signals that indicate a new page or new capability, such as suggested menu location, page functions, route/default landing, or a new management/configuration feature."],
    "existing_page_selection_policy": ["Only select an existing page when the requirement explicitly says to modify an existing/current/original page. For a new page, use similar pages only as style/reference material, never as the target file."],
    "business_to_repo_mapping": ["Map business terms to directories, routes, menus, APIs, permissions, models, and naming conventions in this repository."],
    "negative_page_matches": ["List existing pages that may look semantically similar but must not be selected as target pages for new requirements."],
    "primary_artifacts": ["List files, folders, configs, API definitions, menu definitions, and permission definitions that downstream pipelines must read or reference."],
    "unknowns_to_confirm": ["List remaining unknowns from project onboarding that can affect generation or validation."]
  }},
  "generation_contract": {{
    "routing": ["Describe route, menu, lazy loading, breadcrumb, and default landing conventions."],
    "frontend_pages": ["Describe how to create list pages, detail pages, create/edit flows, modals/drawers, and support components."],
    "primary_page_policy": ["Define how primary pages are identified. Create/edit forms are support components by default unless the requirement explicitly asks for a standalone route."],
    "action_label_policy": ["For button/action matrices, include only user-visible commands. Do not treat drawer/modal/component names as buttons."],
    "api_and_data": ["Describe request wrappers, response envelopes, pagination fields, error handling, and mock/fallback boundaries."],
    "permissions": ["Describe menu, route, button, API, and data-scope permission conventions with repository-specific examples."],
    "state_handling": ["Describe loading, empty state, unauthorized state, API failure, submitting, and invalid state handling."]
  }},
  "verification_contract": {{
    "commands": ["List repository-specific verification commands, such as npm run build, pytest, Playwright, or framework-specific checks."],
    "preview_checks": ["List browser validation points for first screen, route access, buttons, lists, details, forms, and mock/fallback behavior."],
    "review_gates": ["List hard review gates that generated code must satisfy for this repository."],
    "sandbox_notes": ["Document local sandbox, port, container, network, and preview constraints."]
  }}
}}"""


async def analyze_project(project_id: str, force: bool = False) -> Optional[Dict]:
    """分析项目并存储到知识库。后台任务，不阻塞调用方。"""
    import httpx

    was_confirmed = False
    previous_confirmed_by: Optional[int] = None
    previous_confirmed_at: Optional[int] = None

    # 检查是否已分析过
    async with async_session_maker() as session:
        result = await session.execute(
            select(ProjectKnowledge).where(ProjectKnowledge.project_id == int(project_id))
        )
        existing = result.scalar_one_or_none()
        if existing and existing.analysis_status == "done" and existing.skill_content and not force:
            logger.info(f"Project {project_id} already analyzed")
            return _knowledge_to_dict(existing)
        if existing:
            was_confirmed = existing.skill_status == "confirmed"
            previous_confirmed_by = existing.confirmed_by
            previous_confirmed_at = existing.confirmed_at
            existing.analysis_status = "analyzing"
            existing.skill_status = "analyzing"
            existing.analysis_error = None
            existing.update_time = int(time.time() * 1000)
            await session.commit()

    # 获取项目信息
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"http://admin-generator:8082/generator/projects/{project_id}")
            if resp.status_code != 200:
                return None
            proj = resp.json().get("data", {})
    except Exception as e:
        logger.error(f"Failed to fetch project info: {e}")
        return None

    project_name = proj.get("name", "")
    language = proj.get("language", "")
    framework = proj.get("framework", "")
    project_brief = (
        proj.get("project_brief")
        or proj.get("brief")
        or proj.get("description")
        or f"{project_name} project from {proj.get('repo_url') or 'an unconfigured repository'} ({language or 'unknown'}/{framework or 'unknown'})."
    )

    # 创建或更新知识记录
    async with async_session_maker() as session:
        result = await session.execute(
            select(ProjectKnowledge).where(ProjectKnowledge.project_id == int(project_id))
        )
        knowledge = result.scalar_one_or_none()
        if not knowledge:
            knowledge = ProjectKnowledge(project_id=int(project_id))
            session.add(knowledge)
        knowledge.project_name = project_name
        knowledge.repo_url = proj.get("repo_url", "")
        knowledge.language = language
        knowledge.framework = framework
        knowledge.project_brief = project_brief
        knowledge.analysis_status = "analyzing"
        knowledge.skill_status = "analyzing"
        knowledge.analysis_error = None
        knowledge.tenant_id = proj.get("tenant_id", 0)
        knowledge.update_time = int(time.time() * 1000)
        await session.commit()

    # 拉取项目文件
    try:
        from app.ai.flow_manager import _fetch_project_files_from_git
        files = await _fetch_project_files_from_git(project_id)
    except Exception as e:
        logger.error(f"Failed to fetch files: {e}")
        files = {}

    if not files:
        async with async_session_maker() as session:
            result = await session.execute(
                select(ProjectKnowledge).where(ProjectKnowledge.project_id == int(project_id))
            )
            k = result.scalar_one_or_none()
            if k:
                k.tech_summary = f"{language}/{framework} project, no source files loaded"
                k.analysis_status = "failed"
                k.skill_status = "failed"
                k.analysis_error = "No source files were loaded from the Git project"
                k.update_time = int(time.time() * 1000)
                await session.commit()
                return _knowledge_to_dict(k)
        return None

    files_text = _select_key_files(files, language, framework)

    # 调用 LLM 分析
    prompt = ANALYSIS_PROMPT.format(
        name=project_name, language=language, framework=framework, files_text=files_text,
    )
    try:
        from app.ai.agents import AgentFactory
        async with async_session_maker() as cfg_session:
            await AgentFactory.load_llm_from_db(cfg_session)
        agent = AgentFactory.get_agent("PM")
        raw_output = await agent.process(prompt, [])
        analysis = _parse_analysis_json(raw_output)
    except Exception as e:
        logger.error(f"LLM analysis failed: {e}")
        analysis = {"tech_summary": f"分析失败: {e}", "architecture": "",
                     "component_patterns": "", "api_patterns": "",
                     "permission_model": "", "coding_style": "", "key_files": []}
    analysis = _enrich_api_patterns_from_source(analysis, files)

    # 存储
    async with async_session_maker() as session:
        result = await session.execute(
            select(ProjectKnowledge).where(ProjectKnowledge.project_id == int(project_id))
        )
        k = result.scalar_one_or_none()
        if k:
            k.tech_summary = analysis.get("tech_summary", "")
            k.architecture = analysis.get("architecture", "")
            k.component_patterns = analysis.get("component_patterns", "")
            k.api_patterns = analysis.get("api_patterns", "")
            k.permission_model = analysis.get("permission_model", "")
            k.coding_style = analysis.get("coding_style", "")
            k.key_files = json.dumps(analysis.get("key_files", []), ensure_ascii=False)
            k.project_analysis_schema = _json_contract_text(analysis.get("project_analysis_schema"))
            k.generation_contract = _json_contract_text(analysis.get("generation_contract"))
            k.verification_contract = _json_contract_text(analysis.get("verification_contract"))
            k.raw_files = files_text[:8000]
            k.analysis_status = "done"
            next_skill_version = (k.skill_version or 0) + 1 if k.skill_content else 1
            k.skill_content = _build_project_skill_content(k)
            k.skill_status = "confirmed" if was_confirmed else "draft"
            k.skill_version = next_skill_version
            k.confirmed_by = previous_confirmed_by if was_confirmed else None
            k.confirmed_at = previous_confirmed_at if was_confirmed else None
            k.analysis_error = None
            k.update_time = int(time.time() * 1000)
            await session.commit()
            await session.refresh(k)
            analysis = _knowledge_to_dict(k)

    # 同步到通用知识库（方便搜索）
    try:
        content = f"技术栈: {analysis.get('tech_summary', '')}\n"
        content += f"架构: {analysis.get('architecture', '')}\n"
        content += f"组件模式: {analysis.get('component_patterns', '')}\n"
        content += f"接口规范: {analysis.get('api_patterns', '')}\n"
        content += f"权限模型: {analysis.get('permission_model', '')}\n"
        content += f"编码风格: {analysis.get('coding_style', '')}"
        await KnowledgeService.create_knowledge(
            title=f"项目分析: {project_name}",
            content=content,
            category="project_analysis",
            tags=[language, framework, project_name, "auto-analysis"],
            source="project_auto_analysis",
            project_id=int(project_id),
        )
    except Exception as e:
        logger.warning(f"Failed to sync to general knowledge base: {e}")

    logger.info(f"Project {project_id} analysis completed")
    return analysis


async def get_project_knowledge_text(project_id: str) -> Optional[str]:
    """获取项目的知识库上下文文本，用于注入 pipeline prompt"""
    from app.models.agent_models import ProjectKnowledge

    if not project_id:
        return None

    async with async_session_maker() as session:
        result = await session.execute(
            select(ProjectKnowledge).where(ProjectKnowledge.project_id == int(project_id))
        )
        k = result.scalar_one_or_none()
        if not k or k.analysis_status != "done":
            return None
        confirmed_skill = _format_project_skill_context(k)
        if confirmed_skill:
            return confirmed_skill

    sections = []
    if k.tech_summary:
        sections.append(f"- 技术栈: {k.tech_summary}")
    if k.architecture:
        sections.append(f"- 架构: {k.architecture}")
    if k.component_patterns:
        sections.append(f"- 组件模式: {k.component_patterns}")
    if k.api_patterns:
        sections.append(f"- 接口规范: {k.api_patterns}")
    if k.permission_model:
        sections.append(f"- 权限模型: {k.permission_model}")
    if k.coding_style:
        sections.append(f"- 编码风格: {k.coding_style}")

    if not sections:
        return None

    return f"## 项目「{k.project_name}」知识库\n" + "\n".join(sections)


def _select_key_files(files: Dict, language: str, framework: str) -> str:
    """筛选关键文件"""
    import os as _os
    priority = [
        "resultmodel/ApiResult.java", "ApiResult.java", "Result.java", "Response.java",
        "GlobalException", "ExceptionHandler", "ErrorCode",
        "AccessAuthVerifyInterceptor.java", "AccessTokenVerifyInterceptor.java",
        "package.json", "pom.xml", "go.mod", "requirements.txt", "composer.json",
        "src/main.js", "src/main.ts", "src/App.vue", "src/App.tsx",
        "src/router/", "src/routes/", "src/views/", "src/api/",
        "src/store/", "src/stores/", "src/utils/request",
        "src/main/java/", "src/controller/", "src/service/",
        "config/", ".env", "vite.config", "vue.config",
        "src/components/", "src/layouts/",
    ]
    selected = {}
    total = 0
    for pattern in priority:
        for path, content in sorted(files.items()):
            if path in selected or not content.strip():
                continue
            if pattern in path:
                chunk = f"### {path}\n```\n{content[:2000]}\n```\n"
                if total + len(chunk) > 12000:
                    break
                selected[path] = chunk
                total += len(chunk)
        if total > 10000:
            break

    if total < 8000:
        for path, content in sorted(files.items()):
            if path in selected or not content.strip():
                continue
            ext = _os.path.splitext(path)[1]
            if ext in ('.vue', '.jsx', '.tsx', '.java', '.go', '.py', '.php'):
                chunk = f"### {path}\n```\n{content[:1500]}\n```\n"
                if total + len(chunk) > 12000:
                    break
                selected[path] = chunk
                total += len(chunk)

    return "\n".join(selected.values())


def _enrich_api_patterns_from_source(analysis: Dict, files: Dict) -> Dict:
    """Patch high-signal API conventions that are easy to miss in LLM summaries."""
    api_patterns = analysis.get("api_patterns", "") or ""
    key_files = list(analysis.get("key_files") or [])

    for path, content in files.items():
        normalized = path.replace("\\", "/")
        if "ApiResult.java" not in normalized:
            continue
        if all(token in content for token in ("traceId", "message", "data")):
            response_rule = (
                "统一响应模型使用 ApiResult<T>，JSON 顶层结构必须为 "
                '{"message":{"message":"ok","code":0},"traceId":"${traceId}","data":...}。'
                "message 是对象，内部包含 int code 和 string message；成功默认 code=0、message=ok；"
                "错误响应也必须使用同一结构，不允许生成 {code,message,data} 这种扁平格式。"
            )
            if "ApiResult<T>" not in api_patterns and "traceId" not in api_patterns:
                api_patterns = f"{api_patterns}\n{response_rule}".strip()
            if normalized not in key_files:
                key_files.insert(0, normalized)
            break

    analysis["api_patterns"] = api_patterns
    analysis["key_files"] = key_files[:20]
    return analysis


def _parse_analysis_json(raw: str) -> Dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return {"tech_summary": text[:500], "architecture": "", "component_patterns": "",
            "api_patterns": "", "permission_model": "", "coding_style": "", "key_files": []}


def _knowledge_to_dict(k) -> Dict:
    return {
        "project_id": k.project_id,
        "project_name": k.project_name,
        "repo_url": k.repo_url or "",
        "language": k.language or "",
        "framework": k.framework or "",
        "project_brief": k.project_brief or "",
        "tech_summary": k.tech_summary or "",
        "architecture": k.architecture or "",
        "component_patterns": k.component_patterns or "",
        "api_patterns": k.api_patterns or "",
        "permission_model": k.permission_model or "",
        "coding_style": k.coding_style or "",
        "key_files": json.loads(k.key_files or "[]"),
        "project_analysis_schema": k.project_analysis_schema or "",
        "generation_contract": k.generation_contract or "",
        "verification_contract": k.verification_contract or "",
        "analysis_status": k.analysis_status or "",
        "skill_content": k.skill_content or "",
        "skill_status": k.skill_status or "",
        "skill_version": k.skill_version or 1,
        "confirmed_by": k.confirmed_by,
        "confirmed_at": k.confirmed_at,
        "analysis_error": k.analysis_error or "",
        "tenant_id": k.tenant_id,
    }


def _project_scope_filter(allowed_tenant_ids: Optional[List[int]], fallback_tenant_id: int = 0):
    allowed = [int(item) for item in (allowed_tenant_ids or []) if int(item) > 0]
    if fallback_tenant_id > 0 and fallback_tenant_id not in allowed:
        allowed.append(int(fallback_tenant_id))
    scope_tenants = sorted(set([0, *allowed]))
    scoped_project_ids = select(ProjectTenantScope.project_id).where(
        ProjectTenantScope.enabled == 1,
        ProjectTenantScope.tenant_id.in_(scope_tenants),
    )
    return or_(
        ProjectKnowledge.project_id.in_(scoped_project_ids),
        ProjectKnowledge.tenant_id.in_(scope_tenants),
    )


async def get_project_skill(project_id: str) -> Optional[Dict]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(ProjectKnowledge).where(ProjectKnowledge.project_id == int(project_id))
        )
        k = result.scalar_one_or_none()
        if not k:
            return None
        if k.analysis_status == "done" and not k.skill_content:
            k.skill_content = _build_project_skill_content(k)
            k.skill_status = "draft"
            k.skill_version = k.skill_version or 1
            k.update_time = int(time.time() * 1000)
            await session.commit()
            await session.refresh(k)
        data = _knowledge_to_dict(k)
        scope_result = await session.execute(
            select(ProjectTenantScope.tenant_id).where(
                ProjectTenantScope.project_id == int(project_id),
                ProjectTenantScope.enabled == 1,
            )
        )
        data["tenant_scope_ids"] = [int(row[0]) for row in scope_result.all()]
        return data


async def update_project_tenant_scope(
    project_id: str,
    tenant_scope_ids: List[int],
    admin_id: int = 0,
) -> None:
    async with async_session_maker() as session:
        now = int(time.time() * 1000)
        await session.execute(delete(ProjectTenantScope).where(ProjectTenantScope.project_id == int(project_id)))
        for tenant_id in sorted(set(int(item) for item in tenant_scope_ids)):
            session.add(ProjectTenantScope(
                project_id=int(project_id),
                tenant_id=tenant_id,
                enabled=1,
                created_by=admin_id,
                create_time=now,
                update_time=now,
            ))
        await session.commit()


async def match_project_skill_for_requirement(
    requirement: str,
    tenant_id: int = 0,
    allowed_tenant_ids: Optional[List[int]] = None,
) -> Optional[Dict]:
    """Match a product requirement to one confirmed Project Skill."""
    requirement = (requirement or "").strip()
    if not requirement:
        return None

    async with async_session_maker() as session:
        conditions = [
            ProjectKnowledge.skill_status == "confirmed",
            ProjectKnowledge.skill_content.isnot(None),
        ]
        conditions.append(_project_scope_filter(allowed_tenant_ids, tenant_id))
        result = await session.execute(
            select(ProjectKnowledge)
            .where(and_(*conditions))
            .order_by(ProjectKnowledge.update_time.desc())
            .limit(50)
        )
        rows = result.scalars().all()

    skills = [_knowledge_to_dict(row) for row in rows if (row.skill_content or "").strip()]
    if not skills:
        return None

    llm_match = await _select_project_skill_match_with_llm(requirement, skills)
    if llm_match:
        return llm_match
    return select_project_skill_match(requirement, skills)


def _is_backend_project_skill(skill: Dict) -> bool:
    language = str(skill.get("language") or "").lower()
    framework = str(skill.get("framework") or "").lower()
    text = _project_skill_match_text(skill)

    backend_signals = (
        "spring", "spring-boot", "java", "go", "golang", "python", "django",
        "fastapi", "flask", "php", "laravel", "nest", "nestjs", "express",
        "backend", "后端", "api", "接口", "controller", "service", "mapper",
    )
    frontend_only_signals = (
        "vue", "react", "vite", "webpack", "element-plus", "antd", "ant design",
        "frontend", "前端", "页面", "组件", "router", "pinia", "redux",
    )
    if any(signal in language or signal in framework for signal in backend_signals):
        return True
    if any(signal in language or signal in framework for signal in frontend_only_signals):
        return False
    return any(signal in text for signal in backend_signals)


def _is_frontend_project_skill(skill: Dict) -> bool:
    language = str(skill.get("language") or "").lower()
    framework = str(skill.get("framework") or "").lower()
    text = _project_skill_match_text(skill)

    frontend_signals = (
        "javascript", "typescript", "vue", "react", "vite", "webpack",
        "element-plus", "element ui", "antd", "ant design", "frontend",
        "前端", "页面", "组件", "router", "pinia", "vuex", "redux",
    )
    backend_signals = (
        "spring", "spring-boot", "java", "go", "golang", "python", "django",
        "fastapi", "flask", "php", "laravel", "dubbo", "mybatis", "rocketmq",
        "service层", "service layer", "后端", "controller", "mapper",
    )
    if any(signal in language or signal in framework for signal in frontend_signals):
        return True
    if any(signal in language or signal in framework for signal in backend_signals):
        return False
    return any(signal in text for signal in frontend_signals) and not any(
        signal in text for signal in backend_signals
    )


async def match_frontend_project_skill_for_requirement(
    requirement: str,
    tenant_id: int = 0,
    allowed_tenant_ids: Optional[List[int]] = None,
) -> Optional[Dict]:
    """Match a product requirement to a confirmed frontend Project Skill."""
    requirement = (requirement or "").strip()
    if not requirement:
        return None

    async with async_session_maker() as session:
        conditions = [
            ProjectKnowledge.skill_status == "confirmed",
            ProjectKnowledge.skill_content.isnot(None),
        ]
        conditions.append(_project_scope_filter(allowed_tenant_ids, tenant_id))

        result = await session.execute(
            select(ProjectKnowledge)
            .where(and_(*conditions))
            .order_by(ProjectKnowledge.update_time.desc())
            .limit(50)
        )
        rows = result.scalars().all()

    skills = [
        _knowledge_to_dict(row)
        for row in rows
        if (row.skill_content or "").strip() and _is_frontend_project_skill(_knowledge_to_dict(row))
    ]
    if not skills:
        return None

    llm_match = await _select_project_skill_match_with_llm(requirement, skills)
    if llm_match:
        return llm_match
    return select_project_skill_match(requirement, skills)


async def match_backend_project_skill_for_requirement(
    requirement: str,
    tenant_id: int = 0,
    exclude_project_id: str = "",
    allowed_tenant_ids: Optional[List[int]] = None,
) -> Optional[Dict]:
    """Match a product requirement to a confirmed backend Project Skill."""
    requirement = (requirement or "").strip()
    if not requirement:
        return None

    async with async_session_maker() as session:
        conditions = [
            ProjectKnowledge.skill_status == "confirmed",
            ProjectKnowledge.skill_content.isnot(None),
        ]
        conditions.append(_project_scope_filter(allowed_tenant_ids, tenant_id))
        if str(exclude_project_id or "").isdigit():
            conditions.append(ProjectKnowledge.project_id != int(exclude_project_id))

        result = await session.execute(
            select(ProjectKnowledge)
            .where(and_(*conditions))
            .order_by(ProjectKnowledge.update_time.desc())
            .limit(50)
        )
        rows = result.scalars().all()

    skills = [
        _knowledge_to_dict(row)
        for row in rows
        if (row.skill_content or "").strip() and _is_backend_project_skill(_knowledge_to_dict(row))
    ]
    if not skills:
        return None

    # Backend pairing happens inside pipeline creation. Keep it deterministic so
    # product runs are not delayed by a second LLM router call after frontend matching.
    return select_backend_project_skill_matches(requirement, skills)


async def update_project_skill(
    project_id: str,
    skill_content: Optional[str] = None,
    project_brief: Optional[str] = None,
) -> Optional[Dict]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(ProjectKnowledge).where(ProjectKnowledge.project_id == int(project_id))
        )
        k = result.scalar_one_or_none()
        if not k:
            return None
        if project_brief is not None:
            k.project_brief = project_brief
        if skill_content is not None:
            k.skill_content = skill_content
            k.skill_status = "draft"
            k.skill_version = (k.skill_version or 0) + 1
            k.confirmed_by = None
            k.confirmed_at = None
        elif project_brief is not None:
            k.skill_content = _build_project_skill_content(k)
            k.skill_status = "draft"
            k.skill_version = (k.skill_version or 0) + 1
            k.confirmed_by = None
            k.confirmed_at = None
        k.update_time = int(time.time() * 1000)
        await session.commit()
        await session.refresh(k)
        data = _knowledge_to_dict(k)
        scope_result = await session.execute(
            select(ProjectTenantScope.tenant_id).where(
                ProjectTenantScope.project_id == int(project_id),
                ProjectTenantScope.enabled == 1,
            )
        )
        data["tenant_scope_ids"] = [int(row[0]) for row in scope_result.all()]
        return data


async def confirm_project_skill(project_id: str, confirmed_by: int = 0) -> Optional[Dict]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(ProjectKnowledge).where(ProjectKnowledge.project_id == int(project_id))
        )
        k = result.scalar_one_or_none()
        if not k:
            return None
        if k.analysis_status == "failed":
            raise ValueError(k.analysis_error or "Project analysis failed; re-run analysis before confirming the skill")
        if not (k.skill_content or "").strip():
            k.skill_content = _build_project_skill_content(k)
        k.skill_status = "confirmed"
        k.confirmed_by = confirmed_by or None
        k.confirmed_at = int(time.time() * 1000)
        k.update_time = k.confirmed_at
        await session.commit()
        await session.refresh(k)
        data = _knowledge_to_dict(k)
        scope_result = await session.execute(
            select(ProjectTenantScope.tenant_id).where(
                ProjectTenantScope.project_id == int(project_id),
                ProjectTenantScope.enabled == 1,
            )
        )
        data["tenant_scope_ids"] = [int(row[0]) for row in scope_result.all()]
        return data


# ==================== 上下文工程增强 ====================

async def semantic_search(query: str, tenant_id: int = 1, top_k: int = 5,
                          category: Optional[str] = None) -> List[Dict]:
    """语义搜索知识库：基于关键词 + 标签的多维匹配。
    当没有向量数据库时，使用 BM25 风格的 TF 匹配作为语义搜索的替代。

    Args:
        query: 搜索查询
        tenant_id: 租户ID
        top_k: 返回前 K 个结果
        category: 可选分类过滤

    Returns:
        匹配的知识条目列表，按相关度排序
    """
    if not query or not query.strip():
        return []

    # 分词（简单按空格/标点分割）
    import re
    query_terms = set(re.findall(r'[a-zA-Z0-9_一-鿿]+', query.lower()))
    if not query_terms:
        return []

    async with async_session_maker() as session:
        conditions = [
            AgentKnowledge.is_deleted == 0,
            AgentKnowledge.tenant_id == tenant_id,
        ]
        if category:
            conditions.append(AgentKnowledge.category == category)

        result = await session.execute(
            select(AgentKnowledge).where(and_(*conditions))
        )
        all_records = result.scalars().all()

    # 计算每条记录的相关度分数
    scored = []
    for record in all_records:
        text = f"{record.title} {record.content} {record.tags or ''}".lower()
        terms = set(re.findall(r'[a-zA-Z0-9_一-鿿]+', text))

        # Jaccard 相似度 + 关键词命中加权
        if not terms:
            continue
        intersection = query_terms & terms
        if not intersection:
            continue

        # BM25 简化：命中数 / 文档长度归一化
        tf = len(intersection) / len(terms)
        idf_weight = sum(1.0 / (1 + sum(1 for r2 in all_records
                                         if t in f"{r2.title} {r2.content}".lower()))
                         for t in intersection)
        score = tf * 0.4 + idf_weight * 0.6

        # 标题命中额外加权
        title_terms = set(re.findall(r'[a-zA-Z0-9_一-鿿]+', record.title.lower()))
        title_overlap = query_terms & title_terms
        if title_overlap:
            score += len(title_overlap) * 0.3

        scored.append((score, record))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, record in scored[:top_k]:
        results.append({
            "knowledge_id": record.knowledge_id,
            "title": record.title,
            "content": record.content[:500],
            "category": record.category,
            "score": round(score, 4),
            "tags": _parse_knowledge_tags(record.tags),
        })
    return results


async def generate_code_summary(code_files: Dict[str, str], project_name: str = "") -> str:
    """使用 LLM 生成代码摘要，用于上下文工程。
    对关键文件生成精简摘要，替代全量代码注入 prompt。

    Args:
        code_files: {path: content} 文件映射
        project_name: 项目名称

    Returns:
        精简的代码摘要文本
    """
    if not code_files:
        return ""

    # 筛选最关键的文件
    key_files = _select_key_files(code_files, "", "")
    if not key_files:
        key_files = "\n".join(f"### {p}\n```{c[:1500]}\n```"
                              for p, c in list(code_files.items())[:10])

    summary_prompt = f"""请对以下项目「{project_name}」的代码生成精简摘要。

要求：
1. 每个文件用 2-3 句话概括其功能、导出的核心函数/组件、依赖关系
2. 标注文件间的调用关系
3. 总结项目的整体架构模式
4. 总长度不超过 1500 字

代码文件：
{key_files[:8000]}
"""
    try:
        from app.ai.agents import AgentFactory
        agent = AgentFactory.get_agent("BE")
        if agent and hasattr(agent, 'llm') and agent.llm:
            result = await agent.llm.ainvoke(summary_prompt)
            content = result.content if hasattr(result, 'content') else str(result)
            return content.strip()
    except Exception as e:
        logger.warning(f"Failed to generate code summary via LLM: {e}")

    # fallback: 直接返回文件头 + 前几行
    lines = []
    for path, content in list(code_files.items())[:15]:
        first_lines = content.split("\n")[:5]
        lines.append(f"### {path}\n" + "\n".join(first_lines))
    return "\n\n".join(lines)


async def get_relevant_context(query: str, project_id: str = "",
                               tenant_id: int = 1, max_chars: int = 4000) -> str:
    """上下文工程入口：综合知识库 + 项目知识 + 语义搜索，生成最优 prompt 上下文。

    Args:
        query: 当前阶段的用户需求/任务描述
        project_id: 关联项目ID
        tenant_id: 租户ID
        max_chars: 上下文最大字符数

    Returns:
        精选的上下文文本
    """
    parts = []

    # 1. 项目知识库（如果有）
    if project_id:
        proj_knowledge = await get_project_knowledge_text(project_id)
        if proj_knowledge:
            parts.append(proj_knowledge)

    # 2. 语义搜索相关知识
    search_results = await semantic_search(query, tenant_id=tenant_id, top_k=3)
    if search_results:
        kb_section = "## 相关知识库条目\n"
        for r in search_results:
            kb_section += f"### {r['title']} (相关度: {r['score']})\n{r['content']}\n\n"
        parts.append(kb_section)

    if not parts:
        return ""

    context = "\n\n---\n\n".join(parts)
    if len(context) > max_chars:
        context = context[:max_chars] + "\n...(已截断)"
    return context
