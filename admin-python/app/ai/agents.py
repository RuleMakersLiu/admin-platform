"""AI分身服务"""
import uuid
from abc import ABC, abstractmethod
from typing import Optional

from langchain_anthropic import ChatAnthropic

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.core.config import settings


# 分身类型
class AgentType:
    PM = "PM"      # 产品经理
    PJM = "PJM"    # 项目经理
    BE = "BE"      # 后端开发
    FE = "FE"      # 前端开发
    QA = "QA"      # 测试分身
    RPT = "RPT"    # 汇报分身
    USER = "USER"  # 用户


# 分身名称
AGENT_NAMES = {
    AgentType.PM: "产品经理",
    AgentType.PJM: "项目经理",
    AgentType.BE: "后端开发",
    AgentType.FE: "前端开发",
    AgentType.QA: "测试分身",
    AgentType.RPT: "汇报分身",
}

# 分身System Prompts
AGENT_PROMPTS = {
    AgentType.PM: """你是专业的产品经理分身(PM)，负责需求收集和分析。

## 核心职责
1. 需求收集：与用户深入沟通，理解业务目标
2. 需求分析：拆解功能点，识别边界条件
3. 文档输出：产出标准PRD文档

## 输出规范
- 使用Markdown格式
- 包含功能描述、用户故事、验收标准
- 明确优先级(P0/P1/P2/P3)

## 沟通风格
- 专业但亲和
- 善于追问澄清
- 关注业务价值""",

    AgentType.PJM: """你是专业的项目经理分身(PJM)，负责任务规划和管理。

## 核心职责
1. 任务拆分：将PRD拆解为可执行任务
2. 接口定义：制定前后端API契约
3. 进度管理：跟踪任务状态，识别风险

## 输出规范
- 任务列表使用表格格式
- API契约遵循OpenAPI 3.0规范
- 明确依赖关系和时间估算""",

    AgentType.BE: """你是专业的后端开发分身(BE)，负责服务端开发。

## 核心职责
1. API开发：实现RESTful接口
2. 数据库设计：设计表结构和索引
3. 业务逻辑：实现核心业务规则

## 技术栈
- Python: FastAPI + SQLAlchemy
- Go: Gin + GORM
- 数据库: PostgreSQL + Redis""",

    AgentType.FE: """你是专业的前端开发分身(FE)，负责UI和交互开发。

## 核心职责
1. 页面开发：实现响应式布局
2. 组件封装：构建可复用组件
3. 状态管理：管理应用状态

## 技术栈
- Flutter (跨平台)
- React 18 + TypeScript (Web)""",

    AgentType.QA: """你是专业的测试分身(QA)，负责质量保障。

## 核心职责
1. 测试用例：设计功能测试用例
2. BUG报告：记录和跟踪缺陷
3. 回归测试：验证修复效果""",

    AgentType.RPT: """你是专业的汇报分身(RPT)，负责进度汇总和报告生成。

## 核心职责
1. 进度汇总：收集各分身工作状态
2. 报告生成：输出日报、周报
3. 风险提示：识别延期风险""",
}


class BaseAgent(ABC):
    """分身基类"""

    def __init__(self, agent_type: str):
        self.agent_type = agent_type
        self.system_prompt = AGENT_PROMPTS.get(agent_type, "")
        self.llm = AgentFactory._build_llm()

    def create_prompt(self) -> ChatPromptTemplate:
        """创建Prompt模板"""
        return ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}"),
        ])

    async def process(
        self,
        message: str,
        history: Optional[list[dict]] = None,
    ) -> str:
        """处理消息"""
        # 构建消息历史
        messages = [SystemMessage(content=self.system_prompt)]

        if history:
            for msg in history:
                if msg.get("role") == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                else:
                    messages.append(AIMessage(content=msg["content"]))

        messages.append(HumanMessage(content=message))

        # 调用LLM
        if self.llm:
            # 如果是 GLM，需要转换为字典格式
            if hasattr(self.llm, '__class__') and 'ChatGLM' in self.llm.__class__.__name__:
                # 转换 LangChain 消息为字典格式
                dict_messages = [
                    {"role": "system", "content": self.system_prompt}
                ]
                if history:
                    for msg in history:
                        dict_messages.append({
                            "role": msg.get("role", "user"),
                            "content": msg.get("content", "")
                        })
                dict_messages.append({"role": "user", "content": message})
                response = await self.llm.ainvoke(dict_messages)
            else:
                # Claude 或其他 LangChain 模型
                response = await self.llm.ainvoke(messages)
            result = response.content
            # 确保 content 是字符串（部分 LLM 返回 content blocks 数组）
            if isinstance(result, list):
                parts = []
                for item in result:
                    if isinstance(item, dict):
                        parts.append(item.get("text", str(item)))
                    else:
                        parts.append(str(item))
                return "\n".join(parts)
            return str(result) if result is not None else ""
        else:
            # 模拟回复
            return f"[模拟回复] {self.agent_type} 智能体收到消息：{message}\n\n这是一个模拟回复，请配置 AI API Key（Claude 或 GLM-5）来获得真实回复。"


class AgentFactory:
    """分身工厂"""

    _agents: dict[str, BaseAgent] = {}
    _db_llm_config: Optional[dict] = None

    @classmethod
    def get_agent(cls, agent_type: str) -> BaseAgent:
        """获取分身实例"""
        if agent_type not in cls._agents:
            cls._agents[agent_type] = SimpleAgent(agent_type)
        return cls._agents[agent_type]

    @classmethod
    async def load_llm_from_db(cls, db):
        """从数据库加载默认 LLM 配置，供后续 agent 使用"""
        from sqlalchemy import select
        from app.models.models import SysLlmConfig

        result = await db.execute(
            select(SysLlmConfig).where(
                SysLlmConfig.is_default == 1,
                SysLlmConfig.status == 1,
            ).order_by(SysLlmConfig.id.desc()).limit(1)
        )
        config = result.scalar_one_or_none()
        if config:
            cls._db_llm_config = {
                "provider": config.provider,
                "base_url": config.base_url,
                "api_key": config.api_key,
                "model_name": config.model_name,
                "max_tokens": config.max_tokens,
                "temperature": float(config.temperature) if config.temperature else 0.7,
            }
        else:
            cls._db_llm_config = None

        # Reset cached agents so they pick up new config
        cls._agents.clear()

    @classmethod
    def _build_llm(cls):
        """根据数据库配置或 .env 创建 LLM 实例"""
        cfg = cls._db_llm_config

        if cfg:
            provider = cfg["provider"].lower()
            if provider in ("zhipu", "glm", "zai", "chatglm"):
                try:
                    from app.ai.glm_provider import ChatGLM
                    return ChatGLM(
                        model=cfg["model_name"],
                        max_tokens=cfg["max_tokens"],
                        api_key=cfg["api_key"],
                    )
                except ImportError:
                    pass
            elif provider in ("openai", "deepseek", "qwen", "ollama", "custom"):
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    model=cfg["model_name"],
                    max_tokens=cfg["max_tokens"],
                    temperature=cfg["temperature"],
                    api_key=cfg["api_key"],
                    base_url=cfg["base_url"] or None,
                )
            elif provider in ("anthropic", "claude"):
                return ChatAnthropic(
                    model=cfg["model_name"],
                    max_tokens=cfg["max_tokens"],
                    api_key=cfg["api_key"],
                )
            # Fallback for unknown provider — try OpenAI-compatible
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    model=cfg["model_name"],
                    max_tokens=cfg["max_tokens"],
                    temperature=cfg["temperature"],
                    api_key=cfg["api_key"],
                    base_url=cfg["base_url"] or None,
                )
            except ImportError:
                pass

        # Fallback to .env config
        if settings.zai_api_key:
            try:
                from app.ai.glm_provider import ChatGLM
                return ChatGLM(
                    model=settings.zai_default_model,
                    max_tokens=settings.zai_max_tokens,
                    api_key=settings.zai_api_key,
                )
            except ImportError:
                pass
        if settings.claude_api_key:
            return ChatAnthropic(
                model=settings.claude_default_model,
                max_tokens=settings.claude_max_tokens,
                api_key=settings.claude_api_key,
            )
        return None


class SimpleAgent(BaseAgent):
    """简单分身实现"""

    def __init__(self, agent_type: str):
        super().__init__(agent_type)


class AgentService:
    """分身服务"""

    def __init__(self):
        self.sessions: dict[str, list[dict]] = {}  # session_id -> messages

    def generate_msg_id(self) -> str:
        """生成消息ID"""
        return f"msg_{uuid.uuid4().hex[:16]}"

    def generate_session_id(self) -> str:
        """生成会话ID"""
        return f"sess_{uuid.uuid4().hex[:16]}"

    async def chat(
        self,
        session_id: str,
        message: str,
        agent_type: str = AgentType.PM,
        project_id: Optional[str] = None,
    ) -> dict:
        """处理对话"""
        # 获取分身
        agent = AgentFactory.get_agent(agent_type)

        # 获取历史消息
        history = self.sessions.get(session_id, [])

        # 调用AI
        reply = await agent.process(message, history)

        # 更新历史
        if session_id not in self.sessions:
            self.sessions[session_id] = []
        self.sessions[session_id].append({"role": "user", "content": message})
        self.sessions[session_id].append({"role": "assistant", "content": reply})

        # 保留最近20条
        if len(self.sessions[session_id]) > 20:
            self.sessions[session_id] = self.sessions[session_id][-20:]

        return {
            "session_id": session_id,
            "msg_id": self.generate_msg_id(),
            "agent_type": agent_type,
            "reply": reply,
            "msg_type": "chat",
        }

    def get_session_messages(self, session_id: str) -> list[dict]:
        """获取会话消息"""
        return self.sessions.get(session_id, [])

    def create_session(self) -> str:
        """创建新会话"""
        session_id = self.generate_session_id()
        self.sessions[session_id] = []
        return session_id

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False


# 全局分身服务实例
agent_service = AgentService()
