"""记忆服务 - 核心业务逻辑"""
import time
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_models import AgentMemory
from app.schemas.common import PaginatedResult


class MemoryType:
    """记忆类型枚举"""
    SHORT_TERM = "short_term"   # 短期记忆：当前对话上下文
    LONG_TERM = "long_term"     # 长期记忆：持久化的重要信息
    EPISODIC = "episodic"       # 情景记忆：特定事件
    SEMANTIC = "semantic"       # 语义记忆：知识点


class AgentType:
    """分身类型"""
    PM = "PM"
    PJM = "PJM"
    BE = "BE"
    FE = "FE"
    QA = "QA"
    RPT = "RPT"


class MemoryService:
    """记忆服务

    负责分身的记忆管理，包括：
    - 存储和检索记忆
    - 记忆重要性管理
    - 记忆过期清理
    - 跨会话记忆搜索

    记忆系统支持分身的上下文感知和持续学习能力。
    """

    # 记忆类型的默认过期时间（毫秒）
    DEFAULT_EXPIRY = {
        MemoryType.SHORT_TERM: 24 * 60 * 60 * 1000,  # 1天
        MemoryType.LONG_TERM: None,                   # 永不过期
        MemoryType.EPISODIC: 30 * 24 * 60 * 60 * 1000,  # 30天
        MemoryType.SEMANTIC: None,                    # 永不过期
    }

    # 记忆类型的默认重要性
    DEFAULT_IMPORTANCE = {
        MemoryType.SHORT_TERM: 30,
        MemoryType.LONG_TERM: 80,
        MemoryType.EPISODIC: 60,
        MemoryType.SEMANTIC: 70,
    }

    @staticmethod
    def _generate_memory_id() -> str:
        """生成记忆ID"""
        return f"MEM-{uuid.uuid4().hex[:12].upper()}"

    @staticmethod
    async def save_memory(
        db: AsyncSession,
        session_id: str,
        agent_type: str,
        content: str,
        tenant_id: int,
        memory_type: str = MemoryType.SHORT_TERM,
        key_info: Optional[str] = None,
        project_id: Optional[int] = None,
        importance: Optional[int] = None,
        expire_hours: Optional[int] = None
    ) -> AgentMemory:
        """保存记忆

        Args:
            db: 数据库会话
            session_id: 会话ID
            agent_type: 分身类型
            content: 记忆内容
            tenant_id: 租户ID
            memory_type: 记忆类型
            key_info: 关键信息（用于检索）
            project_id: 项目ID
            importance: 重要性 (0-100)
            expire_hours: 过期时间（小时），None表示使用默认值

        Returns:
            创建的记忆实体
        """
        now = int(time.time() * 1000)

        # 如果未指定关键信息，从内容中提取
        if not key_info:
            # 简单提取：取前100个字符作为关键信息
            key_info = content[:100] if len(content) > 100 else content

        # 如果未指定重要性，使用默认值
        if importance is None:
            importance = MemoryService.DEFAULT_IMPORTANCE.get(memory_type, 50)

        # 计算过期时间
        expire_time = None
        if expire_hours is not None:
            expire_time = now + expire_hours * 60 * 60 * 1000
        else:
            default_expiry = MemoryService.DEFAULT_EXPIRY.get(memory_type)
            if default_expiry:
                expire_time = now + default_expiry

        memory = AgentMemory(
            memory_id=MemoryService._generate_memory_id(),
            session_id=session_id,
            project_id=project_id,
            agent_type=agent_type,
            memory_type=memory_type,
            key_info=key_info,
            content=content,
            importance=importance,
            access_count=0,
            last_access_time=now,
            expire_time=expire_time,
            tenant_id=tenant_id,
            create_time=now,
            update_time=now,
            is_deleted=0,
        )

        db.add(memory)
        await db.flush()
        await db.refresh(memory)

        return memory

    @staticmethod
    async def get_memory(
        db: AsyncSession,
        memory_id: str
    ) -> Optional[AgentMemory]:
        """获取单个记忆"""
        stmt = select(AgentMemory).where(
            AgentMemory.memory_id == memory_id,
            AgentMemory.is_deleted == 0
        )
        result = await db.execute(stmt)
        memory = result.scalar_one_or_none()

        # 更新访问信息
        if memory:
            memory.access_count += 1
            memory.last_access_time = int(time.time() * 1000)
            await db.flush()

        return memory

    @staticmethod
    async def get_memories(
        db: AsyncSession,
        session_id: str,
        limit: int = 20,
        memory_types: Optional[List[str]] = None,
        min_importance: Optional[int] = None
    ) -> List[AgentMemory]:
        """获取会话的记忆列表

        Args:
            db: 数据库会话
            session_id: 会话ID
            limit: 返回数量限制
            memory_types: 记忆类型过滤
            min_importance: 最小重要性过滤

        Returns:
            记忆列表，按重要性和访问时间排序
        """
        now = int(time.time() * 1000)

        conditions = [
            AgentMemory.session_id == session_id,
            AgentMemory.is_deleted == 0,
            or_(
                AgentMemory.expire_time.is_(None),
                AgentMemory.expire_time > now
            )
        ]

        if memory_types:
            conditions.append(AgentMemory.memory_type.in_(memory_types))

        if min_importance is not None:
            conditions.append(AgentMemory.importance >= min_importance)

        stmt = (
            select(AgentMemory)
            .where(*conditions)
            .order_by(
                desc(AgentMemory.importance),
                desc(AgentMemory.last_access_time)
            )
            .limit(limit)
        )

        result = await db.execute(stmt)
        memories = list(result.scalars().all())

        # 更新访问计数
        for memory in memories:
            memory.access_count += 1
            memory.last_access_time = now

        await db.flush()

        return memories

    @staticmethod
    async def search_memories(
        db: AsyncSession,
        project_id: int,
        query: str,
        tenant_id: Optional[int] = None,
        agent_type: Optional[str] = None,
        limit: int = 20
    ) -> List[AgentMemory]:
        """搜索记忆

        全文搜索项目的相关记忆，用于分身回顾历史信息

        Args:
            db: 数据库会话
            project_id: 项目ID
            query: 搜索关键词
            tenant_id: 租户ID（可选，用于权限校验）
            agent_type: 限定分身类型
            limit: 返回数量限制

        Returns:
            匹配的记忆列表
        """
        now = int(time.time() * 1000)
        search_pattern = f"%{query}%"

        conditions = [
            AgentMemory.project_id == project_id,
            AgentMemory.is_deleted == 0,
            or_(
                AgentMemory.expire_time.is_(None),
                AgentMemory.expire_time > now
            ),
            or_(
                AgentMemory.key_info.ilike(search_pattern),
                AgentMemory.content.ilike(search_pattern)
            )
        ]

        if tenant_id:
            conditions.append(AgentMemory.tenant_id == tenant_id)

        if agent_type:
            conditions.append(AgentMemory.agent_type == agent_type)

        stmt = (
            select(AgentMemory)
            .where(*conditions)
            .order_by(
                desc(AgentMemory.importance),
                desc(AgentMemory.last_access_time)
            )
            .limit(limit)
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_important_memories(
        db: AsyncSession,
        project_id: int,
        min_importance: int = 70,
        limit: int = 50
    ) -> List[AgentMemory]:
        """获取项目的重要记忆

        用于分身回顾项目的关键信息

        Args:
            db: 数据库会话
            project_id: 项目ID
            min_importance: 最小重要性阈值
            limit: 返回数量限制

        Returns:
            重要记忆列表
        """
        now = int(time.time() * 1000)

        stmt = (
            select(AgentMemory)
            .where(
                AgentMemory.project_id == project_id,
                AgentMemory.is_deleted == 0,
                AgentMemory.importance >= min_importance,
                or_(
                    AgentMemory.expire_time.is_(None),
                    AgentMemory.expire_time > now
                )
            )
            .order_by(desc(AgentMemory.importance), desc(AgentMemory.create_time))
            .limit(limit)
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_memory_importance(
        db: AsyncSession,
        memory_id: str,
        importance: int
    ) -> Optional[AgentMemory]:
        """更新记忆重要性

        分身可以根据实际情况调整记忆的重要性，
        重要度高的记忆会优先被检索和使用

        Args:
            db: 数据库会话
            memory_id: 记忆ID
            importance: 新的重要性值 (0-100)

        Returns:
            更新后的记忆
        """
        if not 0 <= importance <= 100:
            raise ValueError("Importance must be between 0 and 100")

        memory = await MemoryService.get_memory(db, memory_id)

        if not memory:
            return None

        memory.importance = importance
        memory.update_time = int(time.time() * 1000)

        # 高重要性记忆自动转为长期记忆
        if importance >= 80 and memory.memory_type == MemoryType.SHORT_TERM:
            memory.memory_type = MemoryType.LONG_TERM
            memory.expire_time = None  # 取消过期时间

        await db.flush()
        await db.refresh(memory)

        return memory

    @staticmethod
    async def extend_memory_expiry(
        db: AsyncSession,
        memory_id: str,
        extend_hours: int = 24
    ) -> Optional[AgentMemory]:
        """延长记忆过期时间

        Args:
            db: 数据库会话
            memory_id: 记忆ID
            extend_hours: 延长的小时数

        Returns:
            更新后的记忆
        """
        memory = await MemoryService.get_memory(db, memory_id)

        if not memory:
            return None

        now = int(time.time() * 1000)
        current_expiry = memory.expire_time or now
        memory.expire_time = current_expiry + extend_hours * 60 * 60 * 1000
        memory.update_time = now

        await db.flush()
        await db.refresh(memory)

        return memory

    @staticmethod
    async def convert_to_long_term(
        db: AsyncSession,
        memory_id: str
    ) -> Optional[AgentMemory]:
        """将记忆转换为长期记忆

        重要的短期记忆可以转换为长期记忆永久保存
        """
        memory = await MemoryService.get_memory(db, memory_id)

        if not memory:
            return None

        memory.memory_type = MemoryType.LONG_TERM
        memory.expire_time = None  # 永不过期
        memory.importance = max(memory.importance, 70)  # 确保足够重要
        memory.update_time = int(time.time() * 1000)

        await db.flush()
        await db.refresh(memory)

        return memory

    @staticmethod
    async def delete_memory(
        db: AsyncSession,
        memory_id: str
    ) -> bool:
        """软删除记忆"""
        stmt = select(AgentMemory).where(
            AgentMemory.memory_id == memory_id,
            AgentMemory.is_deleted == 0
        )
        result = await db.execute(stmt)
        memory = result.scalar_one_or_none()

        if not memory:
            return False

        memory.is_deleted = 1
        memory.update_time = int(time.time() * 1000)

        await db.flush()

        return True

    @staticmethod
    async def cleanup_expired_memories(
        db: AsyncSession,
        batch_size: int = 100
    ) -> int:
        """清理过期记忆

        定时任务调用，清理已过期的短期记忆

        Args:
            db: 数据库会话
            batch_size: 每批清理数量

        Returns:
            清理的记忆数量
        """
        now = int(time.time() * 1000)

        # 查找过期的记忆
        stmt = (
            select(AgentMemory)
            .where(
                AgentMemory.is_deleted == 0,
                AgentMemory.expire_time.isnot(None),
                AgentMemory.expire_time <= now
            )
            .limit(batch_size)
        )

        result = await db.execute(stmt)
        expired_memories = list(result.scalars().all())

        # 软删除
        for memory in expired_memories:
            memory.is_deleted = 1
            memory.update_time = now

        await db.flush()

        return len(expired_memories)

    @staticmethod
    async def get_memory_context(
        db: AsyncSession,
        session_id: str,
        project_id: Optional[int] = None,
        max_tokens: int = 4000
    ) -> str:
        """获取会话的记忆上下文

        将相关记忆整理成上下文字符串，供分身参考

        Args:
            db: 数据库会话
            session_id: 会话ID
            project_id: 项目ID（可选，用于补充项目级记忆）
            max_tokens: 最大token数估算

        Returns:
            格式化的记忆上下文字符串
        """
        context_parts = []

        # 获取会话级记忆
        session_memories = await MemoryService.get_memories(
            db, session_id, limit=20, min_importance=40
        )

        if session_memories:
            context_parts.append("=== Session Memories ===")
            for m in session_memories:
                context_parts.append(f"[{m.agent_type}] {m.key_info}")
                if len(m.content) <= 200:
                    context_parts.append(f"  {m.content}")

        # 如果有项目ID，补充项目级重要记忆
        if project_id:
            project_memories = await MemoryService.get_important_memories(
                db, project_id, min_importance=70, limit=10
            )

            if project_memories:
                context_parts.append("\n=== Project Context ===")
                for m in project_memories:
                    context_parts.append(f"[{m.memory_type}] {m.key_info}")

        return "\n".join(context_parts)

    @staticmethod
    async def batch_save_memories(
        db: AsyncSession,
        memories_data: List[Dict[str, Any]],
        session_id: str,
        tenant_id: int
    ) -> List[AgentMemory]:
        """批量保存记忆

        用于一次性保存多条记忆
        """
        created_memories = []

        for data in memories_data:
            memory = await MemoryService.save_memory(
                db=db,
                session_id=session_id,
                agent_type=data.get("agent_type"),
                content=data.get("content"),
                tenant_id=tenant_id,
                memory_type=data.get("memory_type", MemoryType.SHORT_TERM),
                key_info=data.get("key_info"),
                project_id=data.get("project_id"),
                importance=data.get("importance"),
                expire_hours=data.get("expire_hours")
            )
            created_memories.append(memory)

        return created_memories
