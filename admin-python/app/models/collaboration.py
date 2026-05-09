"""协作记录模型"""
import time
from typing import Optional
from enum import Enum

from sqlalchemy import (
    BigInteger, Integer, String, Text, Boolean,
    Float, ForeignKey, Index
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CollaborationType(str, Enum):
    """协作类型"""
    HANDOFF = "handoff"         # 交接
    REVIEW = "review"           # 代码审查
    CONSULTATION = "consultation"  # 咨询
    DELEGATION = "delegation"   # 委派
    ASSISTANCE = "assistance"   # 协助
    APPROVAL = "approval"       # 审批


class CollaborationStatus(str, Enum):
    """协作状态"""
    PENDING = "pending"         # 待处理
    ACCEPTED = "accepted"       # 已接受
    REJECTED = "rejected"       # 已拒绝
    COMPLETED = "completed"     # 已完成
    CANCELLED = "cancelled"     # 已取消
    TIMEOUT = "timeout"         # 超时


class CollaborationRecord(Base):
    """协作记录模型"""
    __tablename__ = "collaboration_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    collab_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    
    # 关联
    project_id: Mapped[int] = mapped_column(BigInteger, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    
    # 发起方
    from_agent_id: Mapped[str] = mapped_column(String(64), index=True)
    from_agent_type: Mapped[str] = mapped_column(String(32))
    
    # 接收方
    to_agent_id: Mapped[str] = mapped_column(String(64), index=True)
    to_agent_type: Mapped[str] = mapped_column(String(32))
    
    # 协作信息
    collab_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default=CollaborationStatus.PENDING.value, index=True)
    
    # 内容
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    request_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON - 请求附加数据
    response_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON - 响应附加数据
    
    # 优先级和截止时间
    priority: Mapped[str] = mapped_column(String(16), default="P2")
    due_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    
    # 时间跟踪
    start_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    end_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    
    # 结果
    result: Mapped[Optional[str]] = mapped_column(Text)
    result_status: Mapped[Optional[str]] = mapped_column(String(32))  # success, failure, partial
    
    # 反馈
    feedback: Mapped[Optional[str]] = mapped_column(Text)
    rating: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5 评分
    
    # 重试
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index('idx_collab_project_status', 'project_id', 'status'),
        Index('idx_collab_from_agent', 'from_agent_id', 'create_time'),
        Index('idx_collab_to_agent', 'to_agent_id', 'status'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "collabId": self.collab_id,
            "projectId": self.project_id,
            "sessionId": self.session_id,
            "taskId": self.task_id,
            "fromAgentId": self.from_agent_id,
            "fromAgentType": self.from_agent_type,
            "toAgentId": self.to_agent_id,
            "toAgentType": self.to_agent_type,
            "collabType": self.collab_type,
            "status": self.status,
            "title": self.title,
            "description": self.description,
            "requestData": self.request_data,
            "responseData": self.response_data,
            "priority": self.priority,
            "dueTime": self.due_time,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "durationMs": self.duration_ms,
            "result": self.result,
            "resultStatus": self.result_status,
            "feedback": self.feedback,
            "rating": self.rating,
            "retryCount": self.retry_count,
            "maxRetries": self.max_retries,
            "createTime": self.create_time,
            "updateTime": self.update_time,
        }


class AgentHandoff(Base):
    """智能体交接模型"""
    __tablename__ = "agent_handoff"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    handoff_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    
    # 关联
    project_id: Mapped[int] = mapped_column(BigInteger, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    collab_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    
    # 交接方
    from_agent_id: Mapped[str] = mapped_column(String(64), index=True)
    from_agent_type: Mapped[str] = mapped_column(String(32))
    
    # 接收方
    to_agent_id: Mapped[str] = mapped_column(String(64), index=True)
    to_agent_type: Mapped[str] = mapped_column(String(32))
    
    # 工作流阶段
    from_stage: Mapped[str] = mapped_column(String(32))
    to_stage: Mapped[str] = mapped_column(String(32))
    
    # 交接内容
    context: Mapped[Optional[str]] = mapped_column(Text)  # JSON - 上下文信息
    deliverables: Mapped[Optional[str]] = mapped_column(Text)  # JSON - 交付物
    notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # 状态
    status: Mapped[str] = mapped_column(String(32), default="pending")
    accepted_at: Mapped[Optional[int]] = mapped_column(BigInteger)
    
    # 时间
    handoff_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    complete_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "handoffId": self.handoff_id,
            "projectId": self.project_id,
            "sessionId": self.session_id,
            "collabId": self.collab_id,
            "fromAgentId": self.from_agent_id,
            "fromAgentType": self.from_agent_type,
            "toAgentId": self.to_agent_id,
            "toAgentType": self.to_agent_type,
            "fromStage": self.from_stage,
            "toStage": self.to_stage,
            "context": self.context,
            "deliverables": self.deliverables,
            "notes": self.notes,
            "status": self.status,
            "acceptedAt": self.accepted_at,
            "handoffTime": self.handoff_time,
            "completeTime": self.complete_time,
            "createTime": self.create_time,
            "updateTime": self.update_time,
        }


class AgentReview(Base):
    """智能体审查模型"""
    __tablename__ = "agent_review"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    review_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    
    # 关联
    project_id: Mapped[int] = mapped_column(BigInteger, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    collab_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    
    # 审查者
    reviewer_agent_id: Mapped[str] = mapped_column(String(64), index=True)
    reviewer_agent_type: Mapped[str] = mapped_column(String(32))
    
    # 被审查者
    reviewee_agent_id: Mapped[str] = mapped_column(String(64), index=True)
    reviewee_agent_type: Mapped[str] = mapped_column(String(32))
    
    # 审查类型
    review_type: Mapped[str] = mapped_column(String(32))  # code, design, test, document
    
    # 审查内容
    target_id: Mapped[str] = mapped_column(String(64))  # 审查对象ID（如代码PR、文档ID等）
    target_type: Mapped[str] = mapped_column(String(32))
    target_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # 审查结果
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, approved, changes_requested, rejected
    comments: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of comments
    
    # 评分
    quality_score: Mapped[Optional[int]] = mapped_column(Integer)
    security_score: Mapped[Optional[int]] = mapped_column(Integer)
    performance_score: Mapped[Optional[int]] = mapped_column(Integer)
    maintainability_score: Mapped[Optional[int]] = mapped_column(Integer)
    
    # 时间
    requested_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    started_at: Mapped[Optional[int]] = mapped_column(BigInteger)
    completed_at: Mapped[Optional[int]] = mapped_column(BigInteger)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index('idx_review_project_status', 'project_id', 'status'),
        Index('idx_review_reviewer', 'reviewer_agent_id', 'create_time'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "reviewId": self.review_id,
            "projectId": self.project_id,
            "sessionId": self.session_id,
            "taskId": self.task_id,
            "collabId": self.collab_id,
            "reviewerAgentId": self.reviewer_agent_id,
            "reviewerAgentType": self.reviewer_agent_type,
            "revieweeAgentId": self.reviewee_agent_id,
            "revieweeAgentType": self.reviewee_agent_type,
            "reviewType": self.review_type,
            "targetId": self.target_id,
            "targetType": self.target_type,
            "targetUrl": self.target_url,
            "status": self.status,
            "comments": self.comments,
            "qualityScore": self.quality_score,
            "securityScore": self.security_score,
            "performanceScore": self.performance_score,
            "maintainabilityScore": self.maintainability_score,
            "requestedAt": self.requested_at,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "durationMs": self.duration_ms,
            "createTime": self.create_time,
            "updateTime": self.update_time,
        }


class CollaborationMetrics(Base):
    """协作指标模型"""
    __tablename__ = "collaboration_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    metric_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    
    # 时间维度
    date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    hour: Mapped[Optional[int]] = mapped_column(Integer)
    
    # 项目维度
    project_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)
    
    # 协作统计
    total_collaborations: Mapped[int] = mapped_column(Integer, default=0)
    successful_collaborations: Mapped[int] = mapped_column(Integer, default=0)
    failed_collaborations: Mapped[int] = mapped_column(Integer, default=0)
    
    # 响应时间
    avg_response_time_ms: Mapped[Optional[float]] = mapped_column(Float)
    max_response_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    min_response_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    
    # 按类型统计
    handoff_count: Mapped[int] = mapped_column(Integer, default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    consultation_count: Mapped[int] = mapped_column(Integer, default=0)
    delegation_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # 智能体对统计
    agent_pair: Mapped[Optional[str]] = mapped_column(String(128))  # "PM->BE"
    pair_count: Mapped[int] = mapped_column(Integer, default=0)
    pair_success_rate: Mapped[Optional[float]] = mapped_column(Float)
    
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "metricId": self.metric_id,
            "date": self.date,
            "hour": self.hour,
            "projectId": self.project_id,
            "totalCollaborations": self.total_collaborations,
            "successfulCollaborations": self.successful_collaborations,
            "failedCollaborations": self.failed_collaborations,
            "avgResponseTimeMs": self.avg_response_time_ms,
            "maxResponseTimeMs": self.max_response_time_ms,
            "minResponseTimeMs": self.min_response_time_ms,
            "handoffCount": self.handoff_count,
            "reviewCount": self.review_count,
            "consultationCount": self.consultation_count,
            "delegationCount": self.delegation_count,
            "agentPair": self.agent_pair,
            "pairCount": self.pair_count,
            "pairSuccessRate": self.pair_success_rate,
            "createTime": self.create_time,
            "updateTime": self.update_time,
        }
