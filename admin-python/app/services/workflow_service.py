"""工作流服务 - 核心业务逻辑"""
import time
from enum import Enum
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_models import AgentMessage, AgentProject, AgentSession


class WorkflowStage(str, Enum):
    """工作流阶段枚举"""
    REQUIREMENT = "requirement"   # 需求阶段
    PLANNING = "planning"         # 规划阶段
    DEVELOPMENT = "development"   # 开发阶段
    TESTING = "testing"           # 测试阶段
    REPORT = "report"             # 汇报阶段


class MessageType(str, Enum):
    """消息类型枚举"""
    CHAT = "chat"                     # 普通对话
    REQUIREMENT_DOC = "requirement_doc"  # PRD文档
    TASK_LIST = "task_list"           # 任务列表
    API_CONTRACT = "api_contract"     # API契约
    CODE_REVIEW = "code_review"       # 代码审查
    BUG_REPORT = "bug_report"         # Bug报告
    TEST_REPORT = "test_report"       # 测试报告
    DAILY_REPORT = "daily_report"     # 日报
    HANDOFF = "handoff"               # 工作交接


class AgentType(str, Enum):
    """分身类型枚举"""
    USER = "USER"   # 用户
    PM = "PM"       # 产品经理
    PJM = "PJM"     # 项目经理
    BE = "BE"       # 后端开发
    FE = "FE"       # 前端开发
    QA = "QA"       # 测试
    RPT = "RPT"     # 汇报
    SYSTEM = "SYSTEM"  # 系统


class WorkflowService:
    """工作流服务

    管理分身协作的工作流，定义阶段流转规则和分身职责。
    工作流按以下顺序执行：
    1. requirement: PM与用户沟通，产出PRD
    2. planning: PJM拆解任务，定义API契约
    3. development: BE/FE并行开发
    4. testing: QA执行测试，报告Bug
    5. report: RPT汇总进度，生成报告
    """

    # 工作流阶段顺序
    STAGES = [
        WorkflowStage.REQUIREMENT,
        WorkflowStage.PLANNING,
        WorkflowStage.DEVELOPMENT,
        WorkflowStage.TESTING,
        WorkflowStage.REPORT,
    ]

    # 阶段与负责分身的映射
    STAGE_TO_AGENT = {
        WorkflowStage.REQUIREMENT: AgentType.PM,
        WorkflowStage.PLANNING: AgentType.PJM,
        WorkflowStage.DEVELOPMENT: [AgentType.BE, AgentType.FE],  # 并行
        WorkflowStage.TESTING: AgentType.QA,
        WorkflowStage.REPORT: AgentType.RPT,
    }

    # 消息类型与阶段的映射（用于自动推进工作流）
    MESSAGE_TYPE_TO_STAGE = {
        MessageType.REQUIREMENT_DOC: WorkflowStage.REQUIREMENT,
        MessageType.TASK_LIST: WorkflowStage.PLANNING,
        MessageType.API_CONTRACT: WorkflowStage.PLANNING,
        MessageType.CODE_REVIEW: WorkflowStage.DEVELOPMENT,
        MessageType.BUG_REPORT: WorkflowStage.TESTING,
        MessageType.TEST_REPORT: WorkflowStage.TESTING,
        MessageType.DAILY_REPORT: WorkflowStage.REPORT,
    }

    # 消息类型触发的下一阶段
    MESSAGE_TYPE_TRIGGERS_NEXT = {
        MessageType.REQUIREMENT_DOC: WorkflowStage.PLANNING,
        MessageType.TASK_LIST: WorkflowStage.DEVELOPMENT,
        MessageType.TEST_REPORT: WorkflowStage.REPORT,
    }

    @staticmethod
    def get_stage_index(stage: str) -> int:
        """获取阶段索引"""
        try:
            return WorkflowService.STAGES.index(WorkflowStage(stage))
        except (ValueError, KeyError):
            return -1

    @staticmethod
    def get_next_stage(current_stage: str) -> Optional[str]:
        """获取下一阶段

        Args:
            current_stage: 当前阶段

        Returns:
            下一阶段名称，如果是最后阶段则返回 None
        """
        current_index = WorkflowService.get_stage_index(current_stage)

        if current_index < 0:
            return None

        if current_index >= len(WorkflowService.STAGES) - 1:
            return None

        return WorkflowService.STAGES[current_index + 1].value

    @staticmethod
    def get_previous_stage(current_stage: str) -> Optional[str]:
        """获取上一阶段"""
        current_index = WorkflowService.get_stage_index(current_stage)

        if current_index <= 0:
            return None

        return WorkflowService.STAGES[current_index - 1].value

    @staticmethod
    def get_agent_for_stage(stage: str) -> List[str]:
        """获取阶段负责的分身

        Args:
            stage: 阶段名称

        Returns:
            负责的分身列表
        """
        try:
            stage_enum = WorkflowStage(stage)
            agent = WorkflowService.STAGE_TO_AGENT.get(stage_enum)

            if isinstance(agent, list):
                return [a.value for a in agent]
            elif agent:
                return [agent.value]
            return []
        except (ValueError, KeyError):
            return []

    @staticmethod
    def get_primary_agent_for_stage(stage: str) -> Optional[str]:
        """获取阶段的主要负责分身"""
        agents = WorkflowService.get_agent_for_stage(stage)
        return agents[0] if agents else None

    @staticmethod
    def can_transition_to(current_stage: str, target_stage: str) -> bool:
        """检查是否可以从当前阶段跳转到目标阶段

        规则：
        - 只能向后推进或停留在当前阶段
        - 不能跨阶段跳跃（必须按顺序）
        """
        current_idx = WorkflowService.get_stage_index(current_stage)
        target_idx = WorkflowService.get_stage_index(target_stage)

        if current_idx < 0 or target_idx < 0:
            return False

        # 只允许推进到下一阶段或保持当前阶段
        return target_idx <= current_idx + 1

    @staticmethod
    def transition_stage(
        current_stage: str,
        message_type: str
    ) -> Optional[str]:
        """根据消息类型判断是否需要推进工作流阶段

        Args:
            current_stage: 当前阶段
            message_type: 消息类型

        Returns:
            新的阶段名称，如果不需推进则返回 None
        """
        try:
            msg_type = MessageType(message_type)
        except ValueError:
            return None

        # 检查消息类型是否会触发阶段推进
        next_stage = WorkflowService.MESSAGE_TYPE_TRIGGERS_NEXT.get(msg_type)

        if not next_stage:
            return None

        # 验证是否可以推进
        if WorkflowService.can_transition_to(current_stage, next_stage.value):
            return next_stage.value

        return None

    @staticmethod
    async def get_session_workflow_state(
        db: AsyncSession,
        session_id: str
    ) -> Dict:
        """获取会话的工作流状态

        Args:
            db: 数据库会话
            session_id: 会话ID

        Returns:
            工作流状态信息
        """
        stmt = select(AgentSession).where(AgentSession.session_id == session_id)
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()

        if not session:
            return {}

        current_stage = session.workflow_stage or WorkflowStage.REQUIREMENT.value
        stage_idx = WorkflowService.get_stage_index(current_stage)

        return {
            "session_id": session_id,
            "current_stage": current_stage,
            "stage_index": stage_idx,
            "total_stages": len(WorkflowService.STAGES),
            "progress_percent": round((stage_idx + 1) / len(WorkflowService.STAGES) * 100, 1),
            "current_agent": session.current_agent,
            "active_agents": WorkflowService.get_agent_for_stage(current_stage),
            "next_stage": WorkflowService.get_next_stage(current_stage),
        }

    @staticmethod
    async def advance_workflow(
        db: AsyncSession,
        session_id: str,
        message_type: str
    ) -> Optional[str]:
        """推进工作流

        根据消息类型自动判断是否需要推进工作流，
        并更新会话的工作流阶段和当前分身

        Args:
            db: 数据库会话
            session_id: 会话ID
            message_type: 消息类型

        Returns:
            新的阶段名称，如果未推进则返回 None
        """
        stmt = select(AgentSession).where(AgentSession.session_id == session_id)
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()

        if not session:
            return None

        current_stage = session.workflow_stage or WorkflowStage.REQUIREMENT.value
        new_stage = WorkflowService.transition_stage(current_stage, message_type)

        if new_stage:
            session.workflow_stage = new_stage
            # 设置新阶段的主要负责分身
            primary_agent = WorkflowService.get_primary_agent_for_stage(new_stage)
            if primary_agent:
                session.current_agent = primary_agent
            session.update_time = int(time.time() * 1000)

            await db.flush()

        return new_stage

    @staticmethod
    async def set_workflow_stage(
        db: AsyncSession,
        session_id: str,
        stage: str,
        agent: Optional[str] = None
    ) -> bool:
        """手动设置工作流阶段

        用于特殊情况下的工作流调整

        Args:
            db: 数据库会话
            session_id: 会话ID
            stage: 目标阶段
            agent: 指定的当前分身

        Returns:
            是否设置成功
        """
        stmt = select(AgentSession).where(AgentSession.session_id == session_id)
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()

        if not session:
            return False

        current_stage = session.workflow_stage or WorkflowStage.REQUIREMENT.value

        # 验证阶段跳转是否合法
        if not WorkflowService.can_transition_to(current_stage, stage):
            return False

        session.workflow_stage = stage

        if agent:
            session.current_agent = agent
        else:
            primary_agent = WorkflowService.get_primary_agent_for_stage(stage)
            if primary_agent:
                session.current_agent = primary_agent

        session.update_time = int(time.time() * 1000)

        await db.flush()

        return True

    @staticmethod
    def get_stage_description(stage: str) -> str:
        """获取阶段描述"""
        descriptions = {
            WorkflowStage.REQUIREMENT.value: "需求阶段：PM分身与用户沟通，收集和分析需求，产出PRD文档",
            WorkflowStage.PLANNING.value: "规划阶段：PJM分身拆解任务，制定API契约，规划开发排期",
            WorkflowStage.DEVELOPMENT.value: "开发阶段：BE和FE分身并行开发，完成代码实现",
            WorkflowStage.TESTING.value: "测试阶段：QA分身执行功能测试，报告和跟踪Bug",
            WorkflowStage.REPORT.value: "汇报阶段：RPT分身汇总进度，生成日报和里程碑报告",
        }
        return descriptions.get(stage, "未知阶段")

    @staticmethod
    def get_stage_deliverables(stage: str) -> List[str]:
        """获取阶段产出物"""
        deliverables = {
            WorkflowStage.REQUIREMENT.value: ["PRD文档", "功能清单", "验收标准"],
            WorkflowStage.PLANNING.value: ["任务列表", "API契约", "开发排期"],
            WorkflowStage.DEVELOPMENT.value: ["后端代码", "前端代码", "代码审查报告"],
            WorkflowStage.TESTING.value: ["测试用例", "Bug报告", "测试报告"],
            WorkflowStage.REPORT.value: ["日报", "周报", "里程碑报告"],
        }
        return deliverables.get(stage, [])

    @staticmethod
    def get_workflow_overview() -> Dict:
        """获取工作流总览"""
        return {
            "stages": [
                {
                    "name": stage.value,
                    "index": idx,
                    "primary_agent": WorkflowService.get_primary_agent_for_stage(stage.value),
                    "agents": WorkflowService.get_agent_for_stage(stage.value),
                    "description": WorkflowService.get_stage_description(stage.value),
                    "deliverables": WorkflowService.get_stage_deliverables(stage.value),
                }
                for idx, stage in enumerate(WorkflowService.STAGES)
            ],
            "total_stages": len(WorkflowService.STAGES),
        }

    @staticmethod
    def determine_next_agent(
        current_stage: str,
        from_agent: str,
        message_type: str
    ) -> Optional[str]:
        """根据消息类型确定下一个接收消息的分身

        用于实现分身间的自动工作交接

        Args:
            current_stage: 当前阶段
            from_agent: 发送方分身
            message_type: 消息类型

        Returns:
            下一个分身类型
        """
        # 检查是否会触发阶段推进
        new_stage = WorkflowService.transition_stage(current_stage, message_type)

        if new_stage:
            # 阶段推进，返回新阶段的主要分身
            return WorkflowService.get_primary_agent_for_stage(new_stage)

        # 同阶段内的交接逻辑
        # PM 完成需求 -> 交给 PJM
        if from_agent == AgentType.PM.value and message_type == MessageType.REQUIREMENT_DOC.value:
            return AgentType.PJM.value

        # PJM 完成任务拆分 -> 交给 BE 和 FE
        if from_agent == AgentType.PJM.value and message_type == MessageType.TASK_LIST.value:
            return AgentType.BE.value  # 默认先交给后端

        # BE 完成开发 -> 交给 FE 或 QA
        if from_agent == AgentType.BE.value and message_type == MessageType.CODE_REVIEW.value:
            return AgentType.FE.value

        # FE 完成开发 -> 交给 QA
        if from_agent == AgentType.FE.value and message_type == MessageType.CODE_REVIEW.value:
            return AgentType.QA.value

        # QA 完成测试 -> 交给 RPT
        if from_agent == AgentType.QA.value and message_type == MessageType.TEST_REPORT.value:
            return AgentType.RPT.value

        # 默认返回当前用户
        return AgentType.USER.value

    @staticmethod
    def get_handoff_message(
        from_agent: str,
        to_agent: str,
        stage: str
    ) -> str:
        """生成交接消息模板"""
        templates = {
            (AgentType.PM.value, AgentType.PJM.value):
                "需求文档已完成，请进行任务拆分和API规划。",
            (AgentType.PJM.value, AgentType.BE.value):
                "任务列表和API契约已定义，请开始后端开发。",
            (AgentType.PJM.value, AgentType.FE.value):
                "任务列表和API契约已定义，请开始前端开发。",
            (AgentType.BE.value, AgentType.QA.value):
                "后端开发已完成，请进行接口测试。",
            (AgentType.FE.value, AgentType.QA.value):
                "前端开发已完成，请进行功能测试。",
            (AgentType.QA.value, AgentType.RPT.value):
                "测试已完成，请生成项目报告。",
        }

        key = (from_agent, to_agent)
        return templates.get(key, f"工作已从 {from_agent} 交接给 {to_agent}。")
