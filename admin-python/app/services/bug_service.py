"""Bug服务 - 核心业务逻辑"""
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_models import AgentBug, AgentProject, AgentTask
from app.schemas.common import PaginatedResult


class BugStatus:
    """Bug状态枚举"""
    OPEN = "open"             # 新建
    IN_PROGRESS = "in_progress"  # 处理中
    FIXED = "fixed"           # 已修复
    VERIFIED = "verified"     # 已验证
    CLOSED = "closed"         # 已关闭
    WONTFIX = "wontfix"       # 不修复


class BugSeverity:
    """Bug严重程度枚举"""
    CRITICAL = "critical"  # 致命：系统崩溃、数据丢失
    MAJOR = "major"        # 严重：主要功能不可用
    MINOR = "minor"        # 一般：次要功能问题
    TRIVIAL = "trivial"    # 轻微：UI问题、优化建议


class BugPriority:
    """Bug优先级"""
    P0 = "P0"  # 立即修复
    P1 = "P1"  # 本迭代修复
    P2 = "P2"  # 下迭代修复
    P3 = "P3"  # 低优先级


class BugService:
    """Bug服务

    负责 Bug 的 CRUD 操作、状态流转和解决管理。
    支持完整的 Bug 生命周期管理。
    """

    # 合法的状态流转
    # open -> in_progress -> fixed -> verified -> closed
    #      \-> wontfix
    VALID_TRANSITIONS = {
        BugStatus.OPEN: [BugStatus.IN_PROGRESS, BugStatus.WONTFIX],
        BugStatus.IN_PROGRESS: [BugStatus.FIXED, BugStatus.OPEN],
        BugStatus.FIXED: [BugStatus.VERIFIED, BugStatus.IN_PROGRESS],
        BugStatus.VERIFIED: [BugStatus.CLOSED, BugStatus.FIXED],
        BugStatus.CLOSED: [],      # 终态
        BugStatus.WONTFIX: [],     # 终态
    }

    # 严重程度与默认优先级的映射
    SEVERITY_TO_PRIORITY = {
        BugSeverity.CRITICAL: BugPriority.P0,
        BugSeverity.MAJOR: BugPriority.P1,
        BugSeverity.MINOR: BugPriority.P2,
        BugSeverity.TRIVIAL: BugPriority.P3,
    }

    @staticmethod
    def _generate_bug_id() -> str:
        """生成Bug ID"""
        return f"BUG-{uuid.uuid4().hex[:12].upper()}"

    @staticmethod
    def _generate_bug_code(project_code: str, seq: int) -> str:
        """生成Bug编码"""
        return f"{project_code}-B{seq:03d}"

    @staticmethod
    async def _get_next_bug_sequence(db: AsyncSession, project_id: int) -> int:
        """获取项目的下一个Bug序号"""
        stmt = select(func.count(AgentBug.id)).where(
            AgentBug.project_id == project_id,
            AgentBug.is_deleted == 0
        )
        result = await db.execute(stmt)
        count = result.scalar() or 0
        return count + 1

    @staticmethod
    async def create_bug(
        db: AsyncSession,
        project_id: int,
        data: Dict[str, Any]
    ) -> AgentBug:
        """创建Bug

        Args:
            db: 数据库会话
            project_id: 项目ID
            data: Bug数据
                - bug_title: Bug标题
                - description: 描述
                - severity: 严重程度
                - priority: 优先级（可选，默认根据严重程度推断）
                - task_id: 关联任务ID
                - session_id: 会话ID
                - reporter: 报告人
                - environment: 环境信息
                - reproduce_steps: 复现步骤
                - expected_result: 预期结果
                - actual_result: 实际结果
                - attachments: 附件列表

        Returns:
            创建的Bug实体
        """
        now = int(time.time() * 1000)

        # 获取项目信息
        project_stmt = select(AgentProject).where(AgentProject.id == project_id)
        project_result = await db.execute(project_stmt)
        project = project_result.scalar_one_or_none()

        if not project:
            raise ValueError(f"Project {project_id} not found")

        # 获取下一个序号
        seq = await BugService._get_next_bug_sequence(db, project_id)

        # 严重程度
        severity = data.get("severity", BugSeverity.MINOR)

        # 优先级：如果未指定，根据严重程度推断
        priority = data.get("priority")
        if not priority:
            priority = BugService.SEVERITY_TO_PRIORITY.get(severity, BugPriority.P2)

        # 处理附件列表
        attachments = data.get("attachments")
        if isinstance(attachments, list):
            attachments = json.dumps(attachments)

        bug = AgentBug(
            bug_id=BugService._generate_bug_id(),
            project_id=project_id,
            task_id=data.get("task_id"),
            session_id=data.get("session_id"),
            bug_code=BugService._generate_bug_code(project.project_code, seq),
            bug_title=data.get("bug_title"),
            description=data.get("description"),
            severity=severity,
            priority=priority,
            status=BugStatus.OPEN,
            reporter=data.get("reporter"),
            assignee=data.get("assignee"),
            environment=data.get("environment"),
            reproduce_steps=data.get("reproduce_steps"),
            expected_result=data.get("expected_result"),
            actual_result=data.get("actual_result"),
            attachments=attachments,
            create_time=now,
            update_time=now,
            is_deleted=0,
        )

        db.add(bug)
        await db.flush()
        await db.refresh(bug)

        return bug

    @staticmethod
    async def get_bug(
        db: AsyncSession,
        bug_id: str
    ) -> Optional[AgentBug]:
        """获取单个Bug"""
        stmt = select(AgentBug).where(
            AgentBug.bug_id == bug_id,
            AgentBug.is_deleted == 0
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_bug_by_id(
        db: AsyncSession,
        id: int
    ) -> Optional[AgentBug]:
        """根据主键ID获取Bug"""
        stmt = select(AgentBug).where(
            AgentBug.id == id,
            AgentBug.is_deleted == 0
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_bugs(
        db: AsyncSession,
        project_id: int,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 50
    ) -> PaginatedResult:
        """分页查询Bug列表

        Args:
            db: 数据库会话
            project_id: 项目ID
            filters: 过滤条件
                - status: Bug状态
                - severity: 严重程度
                - priority: 优先级
                - assignee: 指派人
                - reporter: 报告人
                - keyword: 关键词搜索
            page: 页码
            page_size: 每页数量

        Returns:
            分页结果
        """
        filters = filters or {}

        # 基础条件
        conditions = [
            AgentBug.project_id == project_id,
            AgentBug.is_deleted == 0
        ]

        # 状态过滤
        if filters.get("status"):
            # 支持多状态查询
            statuses = filters["status"]
            if isinstance(statuses, list):
                conditions.append(AgentBug.status.in_(statuses))
            else:
                conditions.append(AgentBug.status == statuses)

        # 严重程度过滤
        if filters.get("severity"):
            severities = filters["severity"]
            if isinstance(severities, list):
                conditions.append(AgentBug.severity.in_(severities))
            else:
                conditions.append(AgentBug.severity == severities)

        # 优先级过滤
        if filters.get("priority"):
            conditions.append(AgentBug.priority == filters["priority"])

        # 指派人过滤
        if filters.get("assignee"):
            conditions.append(AgentBug.assignee == filters["assignee"])

        # 报告人过滤
        if filters.get("reporter"):
            conditions.append(AgentBug.reporter == filters["reporter"])

        # 关键词搜索
        if filters.get("keyword"):
            keyword = f"%{filters['keyword']}%"
            conditions.append(
                or_(
                    AgentBug.bug_title.ilike(keyword),
                    AgentBug.bug_code.ilike(keyword),
                    AgentBug.description.ilike(keyword)
                )
            )

        # 查询总数
        count_stmt = select(func.count()).select_from(AgentBug).where(*conditions)
        total_result = await db.execute(count_stmt)
        total = total_result.scalar()

        # 排序优先级定义
        severity_order = {
            BugSeverity.CRITICAL: 0,
            BugSeverity.MAJOR: 1,
            BugSeverity.MINOR: 2,
            BugSeverity.TRIVIAL: 3,
        }

        priority_order = {
            BugPriority.P0: 0,
            BugPriority.P1: 1,
            BugPriority.P2: 2,
            BugPriority.P3: 3,
        }

        # 分页查询
        stmt = (
            select(AgentBug)
            .where(*conditions)
            .order_by(desc(AgentBug.create_time))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await db.execute(stmt)
        items = result.scalars().all()

        # 手动排序：先按严重程度，再按优先级
        items = sorted(
            items,
            key=lambda x: (
                severity_order.get(x.severity, 99),
                priority_order.get(x.priority, 99),
                -x.create_time
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
    async def update_bug(
        db: AsyncSession,
        bug_id: str,
        data: Dict[str, Any]
    ) -> Optional[AgentBug]:
        """更新Bug信息"""
        bug = await BugService.get_bug(db, bug_id)

        if not bug:
            return None

        # 允许更新的字段
        updatable_fields = [
            "bug_title", "description", "severity", "priority",
            "assignee", "environment", "reproduce_steps",
            "expected_result", "actual_result", "attachments"
        ]

        for field in updatable_fields:
            if field in data and data[field] is not None:
                # 处理 JSON 字段
                if field == "attachments" and isinstance(data[field], list):
                    setattr(bug, field, json.dumps(data[field]))
                else:
                    setattr(bug, field, data[field])

        bug.update_time = int(time.time() * 1000)

        await db.flush()
        await db.refresh(bug)

        return bug

    @staticmethod
    async def update_bug_status(
        db: AsyncSession,
        bug_id: str,
        new_status: str,
        note: Optional[str] = None
    ) -> Optional[AgentBug]:
        """更新Bug状态

        状态流转规则:
        - open -> in_progress, wontfix
        - in_progress -> fixed, open
        - fixed -> verified, in_progress
        - verified -> closed, fixed
        - closed/wontfix -> 终态不可变
        """
        bug = await BugService.get_bug(db, bug_id)

        if not bug:
            return None

        current_status = bug.status

        # 验证状态流转
        if new_status not in BugService.VALID_TRANSITIONS.get(current_status, []):
            raise ValueError(
                f"Invalid status transition from '{current_status}' to '{new_status}'"
            )

        bug.status = new_status
        bug.update_time = int(time.time() * 1000)

        # 记录状态变更备注
        if note:
            existing_note = bug.fix_note or ""
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            bug.fix_note = f"{existing_note}\n[{timestamp}] Status->{new_status}: {note}".strip()

        await db.flush()
        await db.refresh(bug)

        return bug

    @staticmethod
    async def resolve_bug(
        db: AsyncSession,
        bug_id: str,
        resolution: str,
        fix_note: Optional[str] = None
    ) -> Optional[AgentBug]:
        """解决Bug

        将Bug状态更新为fixed，并记录解决方案

        Args:
            db: 数据库会话
            bug_id: Bug ID
            resolution: 解决方案描述
            fix_note: 修复备注

        Returns:
            更新后的Bug
        """
        bug = await BugService.get_bug(db, bug_id)

        if not bug:
            return None

        # 只有 open 或 in_progress 的 Bug 可以修复
        if bug.status not in [BugStatus.OPEN, BugStatus.IN_PROGRESS]:
            raise ValueError(
                f"Cannot resolve bug with status '{bug.status}'"
            )

        bug.status = BugStatus.FIXED
        bug.update_time = int(time.time() * 1000)

        # 记录解决方案
        if resolution or fix_note:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            existing_note = bug.fix_note or ""
            new_note = f"[{timestamp}] Resolution: {resolution}"
            if fix_note:
                new_note += f"\n{fix_note}"
            bug.fix_note = f"{existing_note}\n{new_note}".strip()

        await db.flush()
        await db.refresh(bug)

        return bug

    @staticmethod
    async def verify_bug(
        db: AsyncSession,
        bug_id: str,
        passed: bool,
        note: Optional[str] = None
    ) -> Optional[AgentBug]:
        """验证Bug

        QA分身验证Bug是否已真正修复

        Args:
            db: 数据库会话
            bug_id: Bug ID
            passed: 是否通过验证
            note: 验证备注

        Returns:
            更新后的Bug
        """
        bug = await BugService.get_bug(db, bug_id)

        if not bug:
            return None

        if bug.status != BugStatus.FIXED:
            raise ValueError(
                f"Can only verify bugs with status 'fixed', current: '{bug.status}'"
            )

        bug.status = BugStatus.VERIFIED if passed else BugStatus.IN_PROGRESS
        bug.update_time = int(time.time() * 1000)

        if note:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            result = "PASSED" if passed else "FAILED"
            existing_note = bug.fix_note or ""
            bug.fix_note = f"{existing_note}\n[{timestamp}] Verification {result}: {note}".strip()

        await db.flush()
        await db.refresh(bug)

        return bug

    @staticmethod
    async def close_bug(
        db: AsyncSession,
        bug_id: str,
        note: Optional[str] = None
    ) -> Optional[AgentBug]:
        """关闭Bug"""
        bug = await BugService.get_bug(db, bug_id)

        if not bug:
            return None

        if bug.status != BugStatus.VERIFIED:
            raise ValueError(
                f"Can only close verified bugs, current: '{bug.status}'"
            )

        bug.status = BugStatus.CLOSED
        bug.update_time = int(time.time() * 1000)

        if note:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            existing_note = bug.fix_note or ""
            bug.fix_note = f"{existing_note}\n[{timestamp}] Closed: {note}".strip()

        await db.flush()
        await db.refresh(bug)

        return bug

    @staticmethod
    async def assign_bug(
        db: AsyncSession,
        bug_id: str,
        assignee: str
    ) -> Optional[AgentBug]:
        """指派Bug给分身"""
        valid_assignees = ["BE", "FE", "QA"]

        if assignee not in valid_assignees:
            raise ValueError(f"Invalid assignee: {assignee}")

        bug = await BugService.get_bug(db, bug_id)

        if not bug:
            return None

        bug.assignee = assignee
        bug.update_time = int(time.time() * 1000)

        # 如果Bug是open状态，自动变为in_progress
        if bug.status == BugStatus.OPEN:
            bug.status = BugStatus.IN_PROGRESS

        await db.flush()
        await db.refresh(bug)

        return bug

    @staticmethod
    async def delete_bug(
        db: AsyncSession,
        bug_id: str
    ) -> bool:
        """软删除Bug"""
        bug = await BugService.get_bug(db, bug_id)

        if not bug:
            return False

        # 只有 open 或 wontfix 状态的Bug才能删除
        if bug.status not in [BugStatus.OPEN, BugStatus.WONTFIX]:
            raise ValueError(
                f"Cannot delete bug with status '{bug.status}'"
            )

        bug.is_deleted = 1
        bug.update_time = int(time.time() * 1000)

        await db.flush()

        return True

    @staticmethod
    async def get_bug_statistics(
        db: AsyncSession,
        project_id: int
    ) -> Dict[str, Any]:
        """获取项目Bug统计"""
        # 按状态统计
        status_stmt = select(
            AgentBug.status,
            func.count(AgentBug.id).label("count")
        ).where(
            AgentBug.project_id == project_id,
            AgentBug.is_deleted == 0
        ).group_by(AgentBug.status)

        status_result = await db.execute(status_stmt)
        status_stats = {row.status: row.count for row in status_result}

        # 按严重程度统计
        severity_stmt = select(
            AgentBug.severity,
            func.count(AgentBug.id).label("count")
        ).where(
            AgentBug.project_id == project_id,
            AgentBug.is_deleted == 0
        ).group_by(AgentBug.severity)

        severity_result = await db.execute(severity_stmt)
        severity_stats = {row.severity: row.count for row in severity_result}

        total = sum(status_stats.values())
        open_bugs = status_stats.get(BugStatus.OPEN, 0) + status_stats.get(BugStatus.IN_PROGRESS, 0)
        fixed_bugs = status_stats.get(BugStatus.FIXED, 0)
        closed_bugs = status_stats.get(BugStatus.CLOSED, 0)

        return {
            "project_id": project_id,
            "total": total,
            "open": open_bugs,
            "fixed": fixed_bugs,
            "closed": closed_bugs,
            "by_status": status_stats,
            "by_severity": severity_stats,
            "fix_rate": round(closed_bugs / total * 100, 2) if total > 0 else 0,
        }
