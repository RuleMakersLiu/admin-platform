"""任务管理模型 - 扩展版本"""
import time
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import (
    BigInteger, Integer, Numeric, String, Text, Boolean,
    ForeignKey, Enum as SQLEnum, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from enum import Enum

from app.core.database import Base


class TaskStatus(str, Enum):
    """任务状态枚举"""
    TODO = "todo"               # 待办
    IN_PROGRESS = "in_progress" # 进行中
    IN_REVIEW = "in_review"     # 代码审查
    TESTING = "testing"         # 测试中
    DONE = "done"               # 已完成
    BLOCKED = "blocked"         # 阻塞
    CANCELLED = "cancelled"     # 已取消


class TaskPriority(str, Enum):
    """任务优先级"""
    P0 = "P0"  # 紧急
    P1 = "P1"  # 高
    P2 = "P2"  # 中
    P3 = "P3"  # 低


class TaskType(str, Enum):
    """任务类型"""
    FEATURE = "feature"     # 功能开发
    BUG_FIX = "bug_fix"     # Bug修复
    REFACTOR = "refactor"   # 重构
    TEST = "test"           # 测试
    DOC = "doc"             # 文档
    DESIGN = "design"       # 设计
    DEPLOY = "deploy"       # 部署


class KanbanTask(Base):
    """看板任务模型 - 用于看板展示的任务"""
    __tablename__ = "kanban_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    
    # 关联
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("agent_project.id"), index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    parent_task_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # 基本信息
    task_code: Mapped[Optional[str]] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # 分类
    task_type: Mapped[str] = mapped_column(String(32), default=TaskType.FEATURE.value)
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.TODO.value, index=True)
    priority: Mapped[str] = mapped_column(String(16), default=TaskPriority.P2.value)
    
    # 看板列
    column_id: Mapped[str] = mapped_column(String(32), default="todo", index=True)
    swimlane_id: Mapped[Optional[str]] = mapped_column(String(32))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # 分配
    assignee: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    reporter: Mapped[Optional[str]] = mapped_column(String(32))
    
    # 时间相关
    estimated_hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 1))
    actual_hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 1))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    
    start_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    due_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    end_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    
    # 依赖和标签
    dependencies: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of task_ids
    tags: Mapped[Optional[str]] = mapped_column(String(500))
    
    # 验收标准
    acceptance_criteria: Mapped[Optional[str]] = mapped_column(Text)
    
    # 统计
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    attachment_count: Mapped[int] = mapped_column(Integer, default=0)
    subtask_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # 多租户
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    
    # 审计
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000), onupdate=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index('idx_kanban_project_status', 'project_id', 'status'),
        Index('idx_kanban_project_column', 'project_id', 'column_id'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "taskId": self.task_id,
            "projectId": self.project_id,
            "taskCode": self.task_code,
            "title": self.title,
            "description": self.description,
            "taskType": self.task_type,
            "status": self.status,
            "priority": self.priority,
            "columnId": self.column_id,
            "swimlaneId": self.swimlane_id,
            "sortOrder": self.sort_order,
            "assignee": self.assignee,
            "reporter": self.reporter,
            "estimatedHours": float(self.estimated_hours) if self.estimated_hours else None,
            "actualHours": float(self.actual_hours) if self.actual_hours else None,
            "progress": self.progress,
            "startTime": self.start_time,
            "dueTime": self.due_time,
            "endTime": self.end_time,
            "dependencies": self.dependencies,
            "tags": self.tags.split(",") if self.tags else [],
            "acceptanceCriteria": self.acceptance_criteria,
            "commentCount": self.comment_count,
            "attachmentCount": self.attachment_count,
            "subtaskCount": self.subtask_count,
            "createTime": self.create_time,
            "updateTime": self.update_time,
        }


class KanbanColumn(Base):
    """看板列模型"""
    __tablename__ = "kanban_column"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    column_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("agent_project.id"), index=True)
    
    # 列配置
    name: Mapped[str] = mapped_column(String(64))
    color: Mapped[Optional[str]] = mapped_column(String(16))
    icon: Mapped[Optional[str]] = mapped_column(String(32))
    
    # 状态映射
    status: Mapped[str] = mapped_column(String(32))
    wip_limit: Mapped[Optional[int]] = mapped_column(Integer)  # Work In Progress 限制
    
    # 排序
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # 是否系统列（不可删除）
    is_system: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "columnId": self.column_id,
            "projectId": self.project_id,
            "name": self.name,
            "color": self.color,
            "icon": self.icon,
            "status": self.status,
            "wipLimit": self.wip_limit,
            "sortOrder": self.sort_order,
            "isSystem": bool(self.is_system),
            "isActive": bool(self.is_active),
        }


class TaskComment(Base):
    """任务评论模型"""
    __tablename__ = "task_comment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    comment_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    project_id: Mapped[int] = mapped_column(BigInteger, index=True)
    
    # 评论内容
    content: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(32))
    author_type: Mapped[str] = mapped_column(String(32))  # user, agent
    
    # 回复
    parent_comment_id: Mapped[Optional[str]] = mapped_column(String(64))
    reply_to: Mapped[Optional[str]] = mapped_column(String(32))  # 被回复者
    
    # 附件
    attachments: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "commentId": self.comment_id,
            "taskId": self.task_id,
            "content": self.content,
            "author": self.author,
            "authorType": self.author_type,
            "parentCommentId": self.parent_comment_id,
            "replyTo": self.reply_to,
            "attachments": self.attachments,
            "createTime": self.create_time,
        }


class TaskActivity(Base):
    """任务活动日志"""
    __tablename__ = "task_activity"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    activity_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    project_id: Mapped[int] = mapped_column(BigInteger, index=True)
    
    # 活动类型
    activity_type: Mapped[str] = mapped_column(String(32))  # created, updated, status_changed, assigned, commented
    actor: Mapped[str] = mapped_column(String(32))
    actor_type: Mapped[str] = mapped_column(String(32))  # user, agent
    
    # 变更详情
    field_name: Mapped[Optional[str]] = mapped_column(String(64))
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    
    # 关联
    related_id: Mapped[Optional[str]] = mapped_column(String(64))  # 关联的 comment_id 等
    
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "activityId": self.activity_id,
            "taskId": self.task_id,
            "activityType": self.activity_type,
            "actor": self.actor,
            "actorType": self.actor_type,
            "fieldName": self.field_name,
            "oldValue": self.old_value,
            "newValue": self.new_value,
            "relatedId": self.related_id,
            "createTime": self.create_time,
        }
