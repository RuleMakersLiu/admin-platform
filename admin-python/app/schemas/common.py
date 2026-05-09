"""Pydantic Schemas"""
from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

# 泛型类型变量
T = TypeVar('T')


class PaginatedResult(BaseModel, Generic[T]):
    """通用分页结果"""
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int

    class Config:
        arbitrary_types_allowed = True


# ==================== 通用响应 ====================

class Response(BaseModel):
    """通用响应"""
    code: int = 200
    message: str = "success"
    data: Optional[Any] = None
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


# ==================== 认证相关 ====================

class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    tenant_id: Optional[int] = Field(None, alias="tenantId")

    class Config:
        populate_by_name = True


class LoginResponse(BaseModel):
    """登录响应"""
    token: str
    admin_id: int = Field(alias="adminId")
    username: str
    real_name: str = Field(alias="realName")
    tenant_id: int = Field(alias="tenantId")

    class Config:
        populate_by_name = True


class UserInfo(BaseModel):
    """用户信息"""
    admin_id: int = Field(alias="adminId")
    username: str
    real_name: str = Field(alias="realName")
    phone: Optional[str] = None
    email: Optional[str] = None
    status: int = 1
    admin_group_id: int = Field(alias="adminGroupId")
    tenant_id: int = Field(alias="tenantId")

    class Config:
        populate_by_name = True


# ==================== AI分身相关 ====================

class AgentType:
    """分身类型"""
    PM = "PM"      # 产品经理
    PJM = "PJM"    # 项目经理
    BE = "BE"      # 后端开发
    FE = "FE"      # 前端开发
    QA = "QA"      # 测试
    RPT = "RPT"    # 汇报
    USER = "USER"  # 用户


AGENT_TYPE_NAMES = {
    AgentType.PM: "产品经理",
    AgentType.PJM: "项目经理",
    AgentType.BE: "后端开发",
    AgentType.FE: "前端开发",
    AgentType.QA: "测试分身",
    AgentType.RPT: "汇报分身",
}


class ChatRequest(BaseModel):
    """对话请求"""
    session_id: str = Field(..., alias="sessionId")
    project_id: Optional[str] = Field(None, alias="projectId")
    message: str = Field(..., min_length=1, max_length=10000)
    agent_type: Optional[str] = Field(None, alias="agentType")

    class Config:
        populate_by_name = True


class ChatResponse(BaseModel):
    """对话响应"""
    session_id: str = Field(alias="sessionId")
    msg_id: str = Field(alias="msgId")
    agent_type: str = Field(alias="agentType")
    reply: str
    msg_type: str = Field(default="chat", alias="msgType")

    class Config:
        populate_by_name = True


class SessionItem(BaseModel):
    """会话项"""
    session_id: str = Field(alias="sessionId")
    title: Optional[str] = None
    current_agent: Optional[str] = Field(None, alias="currentAgent")
    workflow_stage: Optional[str] = Field(None, alias="workflowStage")
    status: str = "active"
    message_count: int = Field(default=0, alias="messageCount")
    last_message_time: Optional[int] = Field(None, alias="lastMessageTime")
    create_time: int = Field(alias="createTime")

    class Config:
        populate_by_name = True


class SessionListResponse(BaseModel):
    """会话列表响应"""
    total: int
    list: list[SessionItem]


class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    project_id: Optional[str] = Field(None, alias="projectId")
    title: Optional[str] = None

    class Config:
        populate_by_name = True


# ==================== 项目相关 ====================

class ProjectItem(BaseModel):
    """项目项"""
    id: int
    project_code: str = Field(alias="projectCode")
    project_name: str = Field(alias="projectName")
    description: Optional[str] = None
    status: str
    priority: str
    create_time: int = Field(alias="createTime")

    class Config:
        populate_by_name = True


class CreateProjectRequest(BaseModel):
    """创建项目请求"""
    project_name: str = Field(..., alias="projectName", min_length=2, max_length=255)
    description: Optional[str] = None
    priority: Optional[str] = "P2"

    class Config:
        populate_by_name = True


# ==================== 任务相关 ====================

class TaskItem(BaseModel):
    """任务项"""
    id: int
    project_id: int = Field(alias="projectId")
    title: str
    description: Optional[str] = None
    status: str
    priority: str
    assignee: Optional[str] = None
    progress: int = 0
    acceptance_criteria: Optional[str] = Field(None, alias="acceptanceCriteria")
    due_time: Optional[int] = Field(None, alias="dueTime")
    create_time: int = Field(alias="createTime")

    class Config:
        populate_by_name = True


class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    project_id: int = Field(..., alias="projectId")
    title: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    priority: Optional[str] = "P2"
    assignee: Optional[str] = None
    acceptance_criteria: Optional[str] = Field(None, alias="acceptanceCriteria")
    due_time: Optional[int] = Field(None, alias="dueTime")

    class Config:
        populate_by_name = True


# ==================== BUG相关 ====================

class BugItem(BaseModel):
    """BUG项"""
    id: int
    project_id: int = Field(alias="projectId")
    title: str
    description: Optional[str] = None
    severity: str
    status: str
    steps_to_reproduce: Optional[str] = Field(None, alias="stepsToReproduce")
    expected_behavior: Optional[str] = Field(None, alias="expectedBehavior")
    actual_behavior: Optional[str] = Field(None, alias="actualBehavior")
    resolution: Optional[str] = None
    assignee: Optional[str] = None
    create_time: int = Field(alias="createTime")

    class Config:
        populate_by_name = True


class CreateBugRequest(BaseModel):
    """创建BUG请求"""
    project_id: int = Field(..., alias="projectId")
    title: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    severity: Optional[str] = "medium"
    steps_to_reproduce: Optional[str] = Field(None, alias="stepsToReproduce")
    expected_behavior: Optional[str] = Field(None, alias="expectedBehavior")
    actual_behavior: Optional[str] = Field(None, alias="actualBehavior")
    assignee: Optional[str] = None

    class Config:
        populate_by_name = True


# ==================== 通用更新请求 ====================

class UpdateStatusRequest(BaseModel):
    """更新状态请求"""
    status: str
    note: Optional[str] = None

    class Config:
        populate_by_name = True
