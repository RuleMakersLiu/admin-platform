"""知识库服务 - 知识CRUD、搜索、图谱维护"""
import time
import uuid
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.agent_models import AgentKnowledge, KnowledgeEdge, ProjectKnowledge

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
                    "tags": json.loads(r.tags) if r.tags else [],
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
                    tags_list = json.loads(tags_str)
                    all_tags.update(tags_list)
                except (json.JSONDecodeError, TypeError):
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
            # Fetch nodes
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
                .limit(max_nodes)
            )
            nodes = nodes_result.scalars().all()
            node_ids = {n.knowledge_id for n in nodes}

            # Fetch edges between these nodes
            edges_result = await session.execute(
                select(KnowledgeEdge).where(
                    KnowledgeEdge.is_deleted == 0,
                    KnowledgeEdge.tenant_id == tenant_id,
                    KnowledgeEdge.source_id.in_(node_ids),
                    KnowledgeEdge.target_id.in_(node_ids),
                )
            )
            edges = edges_result.scalars().all()

            return {
                "nodes": [
                    {
                        "id": n.knowledge_id,
                        "title": n.title,
                        "category": n.category,
                        "tags": json.loads(n.tags) if n.tags else [],
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
                ],
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

            source_tags = (
                set(json.loads(source.tags)) if source.tags else set()
            )
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
                cand_tags = (
                    set(json.loads(candidate.tags))
                    if candidate.tags
                    else set()
                )
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
  "key_files": ["关键文件路径1", "关键文件路径2"]
}}"""


async def analyze_project(project_id: str, force: bool = False) -> Optional[Dict]:
    """分析项目并存储到知识库。后台任务，不阻塞调用方。"""
    import httpx

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
            k.raw_files = files_text[:8000]
            k.analysis_status = "done"
            next_skill_version = (k.skill_version or 0) + 1 if k.skill_content else 1
            k.skill_content = _build_project_skill_content(k)
            k.skill_status = "draft"
            k.skill_version = next_skill_version
            k.confirmed_by = None
            k.confirmed_at = None
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
        "analysis_status": k.analysis_status or "",
        "skill_content": k.skill_content or "",
        "skill_status": k.skill_status or "",
        "skill_version": k.skill_version or 1,
        "confirmed_by": k.confirmed_by,
        "confirmed_at": k.confirmed_at,
        "analysis_error": k.analysis_error or "",
    }


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
        return _knowledge_to_dict(k)


async def match_project_skill_for_requirement(requirement: str, tenant_id: int = 0) -> Optional[Dict]:
    """Match a product requirement to one confirmed Project Skill."""
    requirement = (requirement or "").strip()
    if not requirement:
        return None

    async with async_session_maker() as session:
        conditions = [
            ProjectKnowledge.skill_status == "confirmed",
            ProjectKnowledge.skill_content.isnot(None),
        ]
        if tenant_id > 0:
            # Keep tenant isolation while still allowing old project_knowledge rows
            # that were created before tenant_id was consistently populated.
            conditions.append(ProjectKnowledge.tenant_id.in_([tenant_id, 0]))
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


async def match_frontend_project_skill_for_requirement(requirement: str, tenant_id: int = 0) -> Optional[Dict]:
    """Match a product requirement to a confirmed frontend Project Skill."""
    requirement = (requirement or "").strip()
    if not requirement:
        return None

    async with async_session_maker() as session:
        conditions = [
            ProjectKnowledge.skill_status == "confirmed",
            ProjectKnowledge.skill_content.isnot(None),
        ]
        if tenant_id > 0:
            conditions.append(ProjectKnowledge.tenant_id.in_([tenant_id, 0]))

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
        if tenant_id > 0:
            conditions.append(ProjectKnowledge.tenant_id.in_([tenant_id, 0]))
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
    return select_project_skill_match(requirement, skills)


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
        return _knowledge_to_dict(k)


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
        return _knowledge_to_dict(k)


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
            "tags": json.loads(record.tags) if record.tags else [],
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
