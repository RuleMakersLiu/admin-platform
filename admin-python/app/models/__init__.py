"""数据模型"""
# 从 database 导入 Base
from app.core.database import Base
from app.models.agent import (
    AgentCapability,
    AgentHeartbeat,
    AgentInfo,
    AgentStatus,
    AgentWorkLog,
    AgentWorkStatus,
)
from app.models.agent_models import (
    AgentBug,
    AgentConfig,
    AgentKnowledge,
    AgentMemory,
    AgentMessage,
    AgentProject,
    AgentSession,
    AgentTask,
    DevPipeline,
    KnowledgeEdge,
)
from app.models.collaboration import (
    AgentHandoff,
    AgentReview,
    CollaborationMetrics,
    CollaborationRecord,
    CollaborationStatus,
    CollaborationType,
)
from app.models.eval_golden_case import EvalGoldenCase
from app.models.eval_run import EvalRun
from app.models.llm_usage_log import LLMUsageLog
from app.models.models import (
    SysAdmin,
    SysAdminGroup,
    SysMenu,
    SysTenant,
)
from app.models.pipeline_eval import PipelineEvalResult

# 新增模型
from app.models.task import (
    KanbanColumn,
    KanbanTask,
    TaskActivity,
    TaskComment,
    TaskPriority,
    TaskStatus,
    TaskType,
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
    # Eval 评测
    "PipelineEvalResult",
    "EvalGoldenCase",
    "EvalRun",
    "LLMUsageLog",
]
