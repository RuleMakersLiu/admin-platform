"""数据模型"""
# 从 database 导入 Base
from app.core.database import Base

from app.models.models import (
    SysAdmin,
    SysAdminGroup,
    SysMenu,
    SysTenant,
)
from app.models.agent_models import (
    AgentProject,
    AgentSession,
    AgentMessage,
    AgentConfig,
    AgentTask,
    AgentBug,
    AgentMemory,
    AgentKnowledge,
    KnowledgeEdge,
    DevPipeline,
)

# 新增模型
from app.models.task import (
    KanbanTask,
    KanbanColumn,
    TaskComment,
    TaskActivity,
    TaskStatus,
    TaskPriority,
    TaskType,
)
from app.models.agent import (
    AgentInfo,
    AgentStatus,
    AgentHeartbeat,
    AgentWorkLog,
    AgentWorkStatus,
    AgentCapability,
)
from app.models.collaboration import (
    CollaborationRecord,
    AgentHandoff,
    AgentReview,
    CollaborationMetrics,
    CollaborationType,
    CollaborationStatus,
)

__all__ = [
    # Base
    "Base",
    # 系统模型
    "SysAdmin",
    "SysAdminGroup",
    "SysMenu",
    "SysTenant",
    # 原有Agent模型
    "AgentProject",
    "AgentSession",
    "AgentMessage",
    "AgentConfig",
    "AgentTask",
    "AgentBug",
    "AgentMemory",
    "AgentKnowledge",
    "KnowledgeEdge",
    "DevPipeline",
    # 看板任务模型
    "KanbanTask",
    "KanbanColumn",
    "TaskComment",
    "TaskActivity",
    "TaskStatus",
    "TaskPriority",
    "TaskType",
    # 智能体模型
    "AgentInfo",
    "AgentStatus",
    "AgentHeartbeat",
    "AgentWorkLog",
    "AgentWorkStatus",
    "AgentCapability",
    # 协作模型
    "CollaborationRecord",
    "AgentHandoff",
    "AgentReview",
    "CollaborationMetrics",
    "CollaborationType",
    "CollaborationStatus",
]
