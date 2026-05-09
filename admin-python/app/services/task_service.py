"""任务服务 - 核心业务逻辑"""
import json
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_models import AgentProject, AgentTask
from app.schemas.common import PaginatedResult


class TaskStatus:
    """任务状态枚举"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TaskType:
    """任务类型枚举"""
    API = "api"           # 后端接口开发
    FRONTEND = "frontend"  # 前端开发
    TEST = "test"         # 测试
    DOC = "doc"           # 文档
    CONFIG = "config"     # 配置


class TaskPriority:
    """任务优先级"""
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class AgentType:
    """分身类型枚举"""
    PM = "PM"    # 产品经理
    PJM = "PJM"  # 项目经理
    BE = "BE"    # 后端开发
    FE = "FE"    # 前端开发
    QA = "QA"    # 测试
    RPT = "RPT"  # 汇报


class TaskService:
    """任务服务

    负责任务的 CRUD 操作、状态流转和分配管理。
    支持任务依赖关系管理。
    """

    # 任务类型与分身的映射关系
    TASK_TYPE_TO_AGENT = {
        TaskType.API: AgentType.BE,
        TaskType.FRONTEND: AgentType.FE,
        TaskType.TEST: AgentType.QA,
        TaskType.DOC: AgentType.PM,
        TaskType.CONFIG: AgentType.BE,
    }

    # 合法的状态流转
    VALID_TRANSITIONS = {
        TaskStatus.PENDING: [TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED],
        TaskStatus.IN_PROGRESS: [TaskStatus.COMPLETED, TaskStatus.BLOCKED, TaskStatus.CANCELLED],
        TaskStatus.BLOCKED: [TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED],
        TaskStatus.COMPLETED: [],  # 终态
        TaskStatus.CANCELLED: [],  # 终态
    }

    @staticmethod
    def _generate_task_id() -> str:
        """生成任务ID"""
        return f"TASK-{uuid.uuid4().hex[:12].upper()}"

    @staticmethod
    def _generate_task_code(project_code: str, seq: int) -> str:
        """生成任务编码"""
        return f"{project_code}-T{seq:03d}"

    @staticmethod
    async def _get_next_task_sequence(db: AsyncSession, project_id: int) -> int:
        """获取项目的下一个任务序号"""
        stmt = select(func.count(AgentTask.id)).where(
            AgentTask.project_id == project_id,
            AgentTask.is_deleted == 0
        )
        result = await db.execute(stmt)
        count = result.scalar() or 0
        return count + 1

    @staticmethod
    async def create_task(
        db: AsyncSession,
        project_id: int,
        data: Dict[str, Any]
    ) -> AgentTask:
        """创建任务

        Args:
            db: 数据库会话
            project_id: 项目ID
            data: 任务数据
                - task_name: 任务名称
                - description: 描述
                - task_type: 任务类型
                - assignee: 指派人
                - priority: 优先级
                - estimated_hours: 预估工时
                - dependencies: 依赖任务ID列表
                - tags: 标签

        Returns:
            创建的任务实体
        """
        now = int(time.time() * 1000)

        # 获取项目信息用于生成编码
        project_stmt = select(AgentProject).where(AgentProject.id == project_id)
        project_result = await db.execute(project_stmt)
        project = project_result.scalar_one_or_none()

        if not project:
            raise ValueError(f"Project {project_id} not found")

        # 获取下一个序号
        seq = await TaskService._get_next_task_sequence(db, project_id)

        # 处理依赖关系
        dependencies = data.get("dependencies")
        if isinstance(dependencies, list):
            dependencies = json.dumps(dependencies)

        task = AgentTask(
            task_id=TaskService._generate_task_id(),
            project_id=project_id,
            session_id=data.get("session_id"),
            parent_task_id=data.get("parent_task_id"),
            task_code=TaskService._generate_task_code(project.project_code, seq),
            task_name=data.get("task_name"),
            description=data.get("description"),
            task_type=data.get("task_type", TaskType.API),
            assignee=data.get("assignee"),
            status=TaskStatus.PENDING,
            priority=data.get("priority", TaskPriority.P2),
            estimated_hours=Decimal(str(data["estimated_hours"])) if data.get("estimated_hours") else None,
            progress=0,
            dependencies=dependencies,
            tags=data.get("tags"),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            create_time=now,
            update_time=now,
            is_deleted=0,
        )

        db.add(task)
        await db.flush()
        await db.refresh(task)

        return task

    @staticmethod
    async def get_task(
        db: AsyncSession,
        task_id: str
    ) -> Optional[AgentTask]:
        """获取单个任务"""
        stmt = select(AgentTask).where(
            AgentTask.task_id == task_id,
            AgentTask.is_deleted == 0
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_task_by_id(
        db: AsyncSession,
        id: int
    ) -> Optional[AgentTask]:
        """根据主键ID获取任务"""
        stmt = select(AgentTask).where(
            AgentTask.id == id,
            AgentTask.is_deleted == 0
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_tasks(
        db: AsyncSession,
        project_id: int,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 50
    ) -> PaginatedResult:
        """分页查询任务列表

        Args:
            db: 数据库会话
            project_id: 项目ID
            filters: 过滤条件
                - status: 任务状态
                - task_type: 任务类型
                - assignee: 指派人
                - priority: 优先级
                - keyword: 关键词搜索
            page: 页码
            page_size: 每页数量

        Returns:
            分页结果
        """
        filters = filters or {}

        # 基础条件
        conditions = [
            AgentTask.project_id == project_id,
            AgentTask.is_deleted == 0
        ]

        # 状态过滤
        if filters.get("status"):
            conditions.append(AgentTask.status == filters["status"])

        # 类型过滤
        if filters.get("task_type"):
            conditions.append(AgentTask.task_type == filters["task_type"])

        # 指派人过滤
        if filters.get("assignee"):
            conditions.append(AgentTask.assignee == filters["assignee"])

        # 优先级过滤
        if filters.get("priority"):
            conditions.append(AgentTask.priority == filters["priority"])

        # 关键词搜索
        if filters.get("keyword"):
            keyword = f"%{filters['keyword']}%"
            conditions.append(
                or_(
                    AgentTask.task_name.ilike(keyword),
                    AgentTask.task_code.ilike(keyword)
                )
            )

        # 查询总数
        count_stmt = select(func.count()).select_from(AgentTask).where(*conditions)
        total_result = await db.execute(count_stmt)
        total = total_result.scalar()

        # 分页查询，按优先级和创建时间排序
        priority_order = {
            TaskPriority.P0: 0,
            TaskPriority.P1: 1,
            TaskPriority.P2: 2,
            TaskPriority.P3: 3,
        }

        stmt = (
            select(AgentTask)
            .where(*conditions)
            .order_by(desc(AgentTask.create_time))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await db.execute(stmt)
        items = result.scalars().all()

        # 手动排序按优先级
        items = sorted(
            items,
            key=lambda x: (
                priority_order.get(x.priority, 99),
                -x.create_time  # 负号表示降序
            )
        )

        return PaginatedResult(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total > 0 else 0
        )

    @staticmethod
    async def update_task(
        db: AsyncSession,
        task_id: str,
        data: Dict[str, Any]
    ) -> Optional[AgentTask]:
        """更新任务信息"""
        task = await TaskService.get_task(db, task_id)

        if not task:
            return None

        # 允许更新的字段
        updatable_fields = [
            "task_name", "description", "assignee",
            "priority", "estimated_hours", "actual_hours",
            "progress", "tags", "start_time", "end_time"
        ]

        for field in updatable_fields:
            if field in data and data[field] is not None:
                # 处理 Decimal 类型
                if field in ["estimated_hours", "actual_hours"]:
                    setattr(task, field, Decimal(str(data[field])))
                else:
                    setattr(task, field, data[field])

        task.update_time = int(time.time() * 1000)

        await db.flush()
        await db.refresh(task)

        return task

    @staticmethod
    async def update_task_status(
        db: AsyncSession,
        task_id: str,
        new_status: str,
        note: Optional[str] = None
    ) -> Optional[AgentTask]:
        """更新任务状态

        状态流转规则:
        - pending -> in_progress, cancelled
        - in_progress -> completed, blocked, cancelled
        - blocked -> in_progress, cancelled
        - completed/cancelled -> 终态不可变
        """
        task = await TaskService.get_task(db, task_id)

        if not task:
            return None

        current_status = task.status

        # 验证状态流转
        if new_status not in TaskService.VALID_TRANSITIONS.get(current_status, []):
            raise ValueError(
                f"Invalid status transition from '{current_status}' to '{new_status}'"
            )

        # 如果任务有依赖，检查依赖是否都已完成
        if new_status == TaskStatus.IN_PROGRESS and task.dependencies:
            try:
                dep_ids = json.loads(task.dependencies)
                if dep_ids:
                    # 检查所有依赖任务是否完成
                    dep_stmt = select(AgentTask.status).where(
                        AgentTask.task_id.in_(dep_ids),
                        AgentTask.is_deleted == 0
                    )
                    dep_result = await db.execute(dep_stmt)
                    dep_statuses = [row.status for row in dep_result]

                    incomplete = [s for s in dep_statuses if s != TaskStatus.COMPLETED]
                    if incomplete:
                        raise ValueError(
                            f"Cannot start task: {len(incomplete)} dependencies not completed"
                        )
            except json.JSONDecodeError:
                pass  # 忽略解析错误

        # 更新状态
        task.status = new_status
        task.update_time = int(time.time() * 1000)

        # 如果完成，设置进度为100%
        if new_status == TaskStatus.COMPLETED:
            task.progress = 100
            task.end_time = int(time.time() * 1000)

        # 如果开始进行，记录开始时间
        if new_status == TaskStatus.IN_PROGRESS and not task.start_time:
            task.start_time = int(time.time() * 1000)

        await db.flush()
        await db.refresh(task)

        return task

    @staticmethod
    async def assign_task(
        db: AsyncSession,
        task_id: str,
        agent_type: str
    ) -> Optional[AgentTask]:
        """指派任务给分身

        Args:
            db: 数据库会话
            task_id: 任务ID
            agent_type: 分身类型 (BE/FE/QA/PM/PJM/RPT)

        Returns:
            更新后的任务
        """
        valid_agents = [
            AgentType.BE, AgentType.FE, AgentType.QA,
            AgentType.PM, AgentType.PJM, AgentType.RPT
        ]

        if agent_type not in valid_agents:
            raise ValueError(f"Invalid agent type: {agent_type}")

        task = await TaskService.get_task(db, task_id)

        if not task:
            return None

        task.assignee = agent_type
        task.update_time = int(time.time() * 1000)

        await db.flush()
        await db.refresh(task)

        return task

    @staticmethod
    async def update_task_progress(
        db: AsyncSession,
        task_id: str,
        progress: int
    ) -> Optional[AgentTask]:
        """更新任务进度

        Args:
            progress: 进度百分比 (0-100)
        """
        if not 0 <= progress <= 100:
            raise ValueError("Progress must be between 0 and 100")

        task = await TaskService.get_task(db, task_id)

        if not task:
            return None

        task.progress = progress
        task.update_time = int(time.time() * 1000)

        # 如果进度为100，自动更新状态为完成
        if progress == 100 and task.status != TaskStatus.COMPLETED:
            task.status = TaskStatus.COMPLETED
            task.end_time = int(time.time() * 1000)

        await db.flush()
        await db.refresh(task)

        return task

    @staticmethod
    async def delete_task(
        db: AsyncSession,
        task_id: str
    ) -> bool:
        """软删除任务"""
        task = await TaskService.get_task(db, task_id)

        if not task:
            return False

        # 只有 pending 状态的任务才能删除
        if task.status not in [TaskStatus.PENDING, TaskStatus.CANCELLED]:
            raise ValueError(
                f"Cannot delete task with status '{task.status}'"
            )

        task.is_deleted = 1
        task.update_time = int(time.time() * 1000)

        await db.flush()

        return True

    @staticmethod
    async def get_tasks_by_assignee(
        db: AsyncSession,
        project_id: int,
        assignee: str
    ) -> List[AgentTask]:
        """获取指派给某个分身的所有任务"""
        stmt = (
            select(AgentTask)
            .where(
                AgentTask.project_id == project_id,
                AgentTask.assignee == assignee,
                AgentTask.is_deleted == 0,
                AgentTask.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED])
            )
            .order_by(AgentTask.priority, desc(AgentTask.create_time))
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def batch_create_tasks(
        db: AsyncSession,
        project_id: int,
        tasks_data: List[Dict[str, Any]]
    ) -> List[AgentTask]:
        """批量创建任务

        用于项目经理分身一次性创建多个任务
        """
        created_tasks = []

        for task_data in tasks_data:
            task = await TaskService.create_task(db, project_id, task_data)
            created_tasks.append(task)

        return created_tasks
