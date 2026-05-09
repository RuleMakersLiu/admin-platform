"""知识库服务 - 知识CRUD、搜索、图谱维护"""
import time
import uuid
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.agent_models import AgentKnowledge, KnowledgeEdge

logger = logging.getLogger(__name__)


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
