"""项目服务 - 核心业务逻辑"""
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent_models import AgentProject, AgentSession, AgentTask
from app.schemas.common import PaginatedResult


class ProjectStatus:
    """项目状态枚举"""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProjectPriority:
    """项目优先级枚举"""
    P0 = "P0"  # 紧急
    P1 = "P1"  # 高
    P2 = "P2"  # 中
    P3 = "P3"  # 低


class ProjectService:
    """项目服务

    负责项目的 CRUD 操作和状态管理。
    遵循多租户隔离原则，所有查询都带 tenant_id 条件。
    """

    # 状态流转规则
    # pending -> active, cancelled
    # active -> completed, cancelled
    # completed -> 终态不可变
    # cancelled -> 终态不可变
    VALID_TRANSITIONS = {
        ProjectStatus.PENDING: [ProjectStatus.ACTIVE, ProjectStatus.CANCELLED],
        ProjectStatus.ACTIVE: [ProjectStatus.COMPLETED, ProjectStatus.CANCELLED],
        ProjectStatus.COMPLETED: [],
        ProjectStatus.CANCELLED: [],
    }

    @staticmethod
    def _generate_project_code() -> str:
        """生成项目编码 PRJ-YYYYMMDD-XXX"""
        date_str = datetime.now().strftime("%Y%m%d")
        short_uuid = uuid.uuid4().hex[:6].upper()
        return f"PRJ-{date_str}-{short_uuid}"

    @staticmethod
    async def create_project(
        db: AsyncSession,
        admin_id: int,
        tenant_id: int,
        data: Dict[str, Any]
    ) -> AgentProject:
        """创建项目

        Args:
            db: 数据库会话
            admin_id: 创建者ID
            tenant_id: 租户ID
            data: 项目数据字典

        Returns:
            创建的项目实体
        """
        now = int(time.time() * 1000)

        project = AgentProject(
            project_code=ProjectService._generate_project_code(),
            project_name=data.get("project_name"),
            description=data.get("description"),
            status=ProjectStatus.PENDING,
            priority=data.get("priority", ProjectPriority.P2),
            tenant_id=tenant_id,
            creator_id=admin_id,
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            create_time=now,
            update_time=now,
            is_deleted=0,
        )

        db.add(project)
        await db.flush()
        await db.refresh(project)

        return project

    @staticmethod
    async def get_project(
        db: AsyncSession,
        project_id: int,
        tenant_id: Optional[int] = None
    ) -> Optional[AgentProject]:
        """获取单个项目

        Args:
            db: 数据库会话
            project_id: 项目ID
            tenant_id: 租户ID（用于权限校验）

        Returns:
            项目实体或 None
        """
        stmt = select(AgentProject).where(
            AgentProject.id == project_id,
            AgentProject.is_deleted == 0
        )

        if tenant_id:
            stmt = stmt.where(AgentProject.tenant_id == tenant_id)

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_project_by_code(
        db: AsyncSession,
        project_code: str,
        tenant_id: Optional[int] = None
    ) -> Optional[AgentProject]:
        """根据项目编码获取项目"""
        stmt = select(AgentProject).where(
            AgentProject.project_code == project_code,
            AgentProject.is_deleted == 0
        )

        if tenant_id:
            stmt = stmt.where(AgentProject.tenant_id == tenant_id)

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_projects(
        db: AsyncSession,
        tenant_id: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20
    ) -> PaginatedResult:
        """分页查询项目列表

        Args:
            db: 数据库会话
            tenant_id: 租户ID（None 时不过滤租户，超管使用）
            filters: 过滤条件
            page: 页码
            page_size: 每页数量

        Returns:
            分页结果
        """
        filters = filters or {}

        # 基础查询条件
        conditions = [AgentProject.is_deleted == 0]
        if tenant_id:
            conditions.append(AgentProject.tenant_id == tenant_id)

        # 状态过滤
        if filters.get("status"):
            conditions.append(AgentProject.status == filters["status"])

        # 优先级过滤
        if filters.get("priority"):
            conditions.append(AgentProject.priority == filters["priority"])

        # 创建者过滤
        if filters.get("creator_id"):
            conditions.append(AgentProject.creator_id == filters["creator_id"])

        # 关键词搜索
        if filters.get("keyword"):
            keyword = f"%{filters['keyword']}%"
            conditions.append(
                or_(
                    AgentProject.project_name.ilike(keyword),
                    AgentProject.project_code.ilike(keyword)
                )
            )

        # 查询总数
        count_stmt = select(func.count()).select_from(AgentProject).where(*conditions)
        total_result = await db.execute(count_stmt)
        total = total_result.scalar()

        # 分页查询
        stmt = (
            select(AgentProject)
            .where(*conditions)
            .order_by(desc(AgentProject.create_time))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await db.execute(stmt)
        items = result.scalars().all()

        return PaginatedResult(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total > 0 else 0
        )

    @staticmethod
    async def update_project(
        db: AsyncSession,
        project_id: int,
        tenant_id: Optional[int] = None,
        data: Dict[str, Any] = None
    ) -> Optional[AgentProject]:
        """更新项目

        Args:
            db: 数据库会话
            project_id: 项目ID
            tenant_id: 租户ID
            data: 更新数据

        Returns:
            更新后的项目实体
        """
        project = await ProjectService.get_project(db, project_id, tenant_id)

        if not project:
            return None

        # 更新允许修改的字段
        updatable_fields = [
            "project_name", "description", "priority",
            "start_time", "end_time", "status"
        ]

        for field in updatable_fields:
            if field in data and data[field] is not None:
                setattr(project, field, data[field])

        project.update_time = int(time.time() * 1000)

        await db.flush()
        await db.refresh(project)

        return project

    @staticmethod
    async def update_project_status(
        db: AsyncSession,
        project_id: int,
        tenant_id: Optional[int] = None,
        new_status: str = None
    ) -> Optional[AgentProject]:
        """更新项目状态

        状态流转规则:
        - pending -> active, cancelled
        - active -> completed, cancelled
        - completed -> (终态，不可变更)
        - cancelled -> (终态，不可变更)
        """
        project = await ProjectService.get_project(db, project_id, tenant_id)

        if not project:
            return None

        current_status = project.status

        # 验证状态流转是否合法（使用类属性）
        if new_status not in ProjectService.VALID_TRANSITIONS.get(current_status, []):
            raise ValueError(
                f"Invalid status transition from '{current_status}' to '{new_status}'"
            )

        project.status = new_status
        project.update_time = int(time.time() * 1000)

        await db.flush()
        await db.refresh(project)

        return project

    @staticmethod
    async def delete_project(
        db: AsyncSession,
        project_id: int,
        tenant_id: Optional[int] = None
    ) -> bool:
        """软删除项目

        Args:
            db: 数据库会话
            project_id: 项目ID
            tenant_id: 租户ID

        Returns:
            是否删除成功
        """
        project = await ProjectService.get_project(db, project_id, tenant_id)

        if not project:
            return False

        # 只有 pending 或 cancelled 状态的项目才能删除
        if project.status not in [ProjectStatus.PENDING, ProjectStatus.CANCELLED]:
            raise ValueError(
                f"Cannot delete project with status '{project.status}'"
            )

        project.is_deleted = 1
        project.update_time = int(time.time() * 1000)

        await db.flush()

        return True

    @staticmethod
    async def get_project_statistics(
        db: AsyncSession,
        project_id: int,
        tenant_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取项目统计信息

        包括任务数量、完成进度、Bug数量等
        """
        project = await ProjectService.get_project(db, project_id, tenant_id)

        if not project:
            return {}

        # 统计任务数量
        task_stmt = select(
            AgentTask.status,
            func.count(AgentTask.id).label("count")
        ).where(
            AgentTask.project_id == project_id,
            AgentTask.is_deleted == 0
        ).group_by(AgentTask.status)

        task_result = await db.execute(task_stmt)
        task_stats = {row.status: row.count for row in task_result}

        # 计算总任务数和完成率
        total_tasks = sum(task_stats.values())
        completed_tasks = task_stats.get("completed", 0)
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        return {
            "project_id": project_id,
            "project_status": project.status,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "pending_tasks": task_stats.get("pending", 0),
            "in_progress_tasks": task_stats.get("in_progress", 0),
            "blocked_tasks": task_stats.get("blocked", 0),
            "completion_rate": round(completion_rate, 2),
        }
