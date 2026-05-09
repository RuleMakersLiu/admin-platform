"""智能体状态模型"""
import time
from typing import Optional
from enum import Enum

from sqlalchemy import (
    BigInteger, Integer, String, Text, Boolean,
    Float, Index
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentWorkStatus(str, Enum):
    """智能体工作状态"""
    IDLE = "idle"               # 空闲
    WORKING = "working"         # 工作中
    WAITING = "waiting"         # 等待输入
    ERROR = "error"             # 错误
    OFFLINE = "offline"         # 离线


class AgentCapability(str, Enum):
    """智能体能力"""
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    REQUIREMENT_ANALYSIS = "requirement_analysis"
    PROJECT_MANAGEMENT = "project_management"
    DEPLOYMENT = "deployment"


class AgentInfo(Base):
    """智能体信息模型"""
    __tablename__ = "agent_info"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    
    # 基本信息
    agent_type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[Optional[str]] = mapped_column(Text)
    avatar: Mapped[Optional[str]] = mapped_column(String(255))
    
    # 状态
    status: Mapped[str] = mapped_column(String(32), default=AgentWorkStatus.OFFLINE.value, index=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    
    # 能力配置
    capabilities: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    model_config: Mapped[Optional[str]] = mapped_column(Text)  # JSON object
    tool_config: Mapped[Optional[str]] = mapped_column(Text)   # JSON object
    
    # 系统提示词
    system_prompt: Mapped[Optional[str]] = mapped_column(Text)
    
    # 性能指标
    total_tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    average_response_time: Mapped[Optional[float]] = mapped_column(Float)
    success_rate: Mapped[Optional[float]] = mapped_column(Float)
    
    # 资源限制
    max_concurrent_tasks: Mapped[int] = mapped_column(Integer, default=3)
    current_task_count: Mapped[int] = mapped_column(Integer, default=0)
    
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agentId": self.agent_id,
            "agentType": self.agent_type,
            "name": self.name,
            "description": self.description,
            "avatar": self.avatar,
            "status": self.status,
            "isActive": bool(self.is_active),
            "capabilities": self.capabilities,
            "modelConfig": self.model_config,
            "toolConfig": self.tool_config,
            "systemPrompt": self.system_prompt,
            "totalTasksCompleted": self.total_tasks_completed,
            "averageResponseTime": self.average_response_time,
            "successRate": self.success_rate,
            "maxConcurrentTasks": self.max_concurrent_tasks,
            "currentTaskCount": self.current_task_count,
            "createTime": self.create_time,
            "updateTime": self.update_time,
        }


class AgentStatus(Base):
    """智能体实时状态模型"""
    __tablename__ = "agent_status"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    status_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_type: Mapped[str] = mapped_column(String(32), index=True)
    project_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    
    # 工作状态
    work_status: Mapped[str] = mapped_column(String(32), default=AgentWorkStatus.IDLE.value, index=True)
    current_task_id: Mapped[Optional[str]] = mapped_column(String(64))
    current_action: Mapped[Optional[str]] = mapped_column(String(255))
    
    # 进度信息
    progress: Mapped[int] = mapped_column(Integer, default=0)
    progress_message: Mapped[Optional[str]] = mapped_column(String(255))
    estimated_remaining_time: Mapped[Optional[int]] = mapped_column(Integer)  # seconds
    
    # 资源使用
    cpu_usage: Mapped[Optional[float]] = mapped_column(Float)
    memory_usage: Mapped[Optional[float]] = mapped_column(Float)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # 心跳
    last_heartbeat: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    last_activity_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    
    # 错误信息
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    last_error_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))

    __table_args__ = (
        Index('idx_agent_status_type_status', 'agent_type', 'work_status'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "statusId": self.status_id,
            "agentId": self.agent_id,
            "agentType": self.agent_type,
            "projectId": self.project_id,
            "sessionId": self.session_id,
            "workStatus": self.work_status,
            "currentTaskId": self.current_task_id,
            "currentAction": self.current_action,
            "progress": self.progress,
            "progressMessage": self.progress_message,
            "estimatedRemainingTime": self.estimated_remaining_time,
            "cpuUsage": self.cpu_usage,
            "memoryUsage": self.memory_usage,
            "tokenCount": self.token_count,
            "lastHeartbeat": self.last_heartbeat,
            "lastActivityTime": self.last_activity_time,
            "errorCount": self.error_count,
            "lastError": self.last_error,
            "lastErrorTime": self.last_error_time,
            "createTime": self.create_time,
            "updateTime": self.update_time,
        }


class AgentHeartbeat(Base):
    """智能体心跳记录"""
    __tablename__ = "agent_heartbeat"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    heartbeat_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_type: Mapped[str] = mapped_column(String(32), index=True)
    
    # 心跳数据
    status: Mapped[str] = mapped_column(String(32))
    current_task_id: Mapped[Optional[str]] = mapped_column(String(64))
    cpu_usage: Mapped[Optional[float]] = mapped_column(Float)
    memory_usage: Mapped[Optional[float]] = mapped_column(Float)
    
    # 附加信息
    extra_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "heartbeatId": self.heartbeat_id,
            "agentId": self.agent_id,
            "agentType": self.agent_type,
            "status": self.status,
            "currentTaskId": self.current_task_id,
            "cpuUsage": self.cpu_usage,
            "memoryUsage": self.memory_usage,
            "extraData": self.extra_data,
            "createTime": self.create_time,
        }


class AgentWorkLog(Base):
    """智能体工作日志"""
    __tablename__ = "agent_work_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    log_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_type: Mapped[str] = mapped_column(String(32), index=True)
    project_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    
    # 日志内容
    action: Mapped[str] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(16), default="info")  # debug, info, warning, error
    message: Mapped[str] = mapped_column(Text)
    
    # 详细数据
    input_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    output_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    
    # 性能指标
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    model_used: Mapped[Optional[str]] = mapped_column(String(64))
    
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))

    __table_args__ = (
        Index('idx_work_log_agent_time', 'agent_id', 'create_time'),
        Index('idx_work_log_project_time', 'project_id', 'create_time'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "logId": self.log_id,
            "agentId": self.agent_id,
            "agentType": self.agent_type,
            "projectId": self.project_id,
            "sessionId": self.session_id,
            "taskId": self.task_id,
            "action": self.action,
            "level": self.level,
            "message": self.message,
            "inputData": self.input_data,
            "outputData": self.output_data,
            "durationMs": self.duration_ms,
            "tokenCount": self.token_count,
            "modelUsed": self.model_used,
            "createTime": self.create_time,
        }
