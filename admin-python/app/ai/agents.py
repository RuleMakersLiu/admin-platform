"""AI Agent 服务 - 统一版本

特性:
  - 模型路由：根据 agent_type 自动选择最优模型
  - 流式响应：支持 astream() 用于前端实时渲染
  - 上下文管理：自动截断历史消息以适应模型窗口
  - Token 统计：记录每次调用的 token 使用量
"""
import uuid
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional

from app.ai.model_router import model_router
from app.core.config import settings


class AgentType:
    PM = "PM"
    PJM = "PJM"
    BE = "BE"
    FE = "FE"
    QA = "QA"
    RPT = "RPT"
    USER = "USER"


AGENT_NAMES = {
    AgentType.PM: "产品经理",
    AgentType.PJM: "项目经理",
    AgentType.BE: "后端开发",
    AgentType.FE: "前端开发",
    AgentType.QA: "测试分身",
    AgentType.RPT: "汇报分身",
}

AGENT_PROMPTS = {
    AgentType.PM: """你是专业的产品经理(PM)，负责需求收集和分析。

## 核心职责
1. 需求收集：与用户深入沟通，理解业务目标
2. 需求分析：拆解功能点，识别边界条件
3. 文档输出：产出标准PRD文档

## 输出规范
- 使用Markdown格式
- 包含功能描述、用户故事、验收标准
- 明确优先级(P0/P1/P2/P3)

## 沟通风格
- 专业但亲和，善于追问澄清，关注业务价值""",

    AgentType.PJM: """你是专业的项目经理(PJM)，负责任务规划和管理。

## 核心职责
1. 任务拆分：将PRD拆解为可执行任务
2. 接口定义：制定前后端API契约
3. 进度管理：跟踪任务状态，识别风险

## 输出规范
- 任务列表使用表格格式
- API契约遵循OpenAPI 3.0规范
- 明确依赖关系和时间估算""",

    AgentType.BE: """你是专业的后端开发(BE)，负责服务端开发。

## 核心职责
1. API开发：实现RESTful接口
2. 数据库设计：设计表结构和索引
3. 业务逻辑：实现核心业务规则

## 技术架构
PHP + Java 双层架构：
- PHP (Laravel 8 + Swoole) 对外提供 API，通过 Curl 转发到 Java
- Java (Spring Boot 1.4.3 + Dubbo 3.x) 提供核心业务服务
- Java 版本：1.8
- PHP 通过 app(Http::class)->postHttp('/wealth/xxx/') 调用 Java 接口
- 统一响应格式：{ "message": { "code": 0, "message": "success" }, "data": {...} }

## PHP 层 (Laravel 8)
- Controller → Service → DAO → Model
- 多租户：tenant_id 字段
- 签名：appkey + timestamp + signcode

## Java 层
- @RestController + @DubboReference 注入
- 包：com.gemantic.wealth.{模块}
- ApiResult 统一返回""",

    AgentType.FE: """你是专业的前端开发(FE)，负责UI和交互开发。

## 核心职责
1. 页面开发：实现响应式布局
2. 组件封装：构建可复用组件
3. 状态管理：管理应用状态

## 技术栈
- Vue 2.6.10 + antd-vue 1.7.2 (vue-antd-pro 脚手架)
- vue-router 3.x + Vuex 3.x + vue-ls 持久化
- axios 封装在 src/utils/request.js
- 列表页使用 s-table 组件（封装 a-table + 分页 + 远程加载）
- 搜索栏：a-form layout="inline"
- 弹窗：a-modal
- 权限指令：v-action:模块_操作
- 样式：Less 预处理器，scoped
- .vue 单文件组件：template + script (Options API) + style scoped""",

    AgentType.QA: """你是专业的测试工程师(QA)，负责质量保障。

## 核心职责
1. 测试用例：设计功能测试用例
2. BUG报告：记录和跟踪缺陷
3. 代码审查：检查代码质量、安全性和最佳实践""",

    AgentType.RPT: """你是专业的报告工程师(RPT)，负责进度汇总和报告生成。

## 核心职责
1. 进度汇总：收集各分身工作状态
2. 报告生成：输出日报、周报
3. 风险提示：识别延期风险""",
}

MAX_HISTORY_TOKENS = 3000
CHARS_PER_TOKEN = 2  # 粗略估算


def _estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def _truncate_history(history: list[dict], max_tokens: int = MAX_HISTORY_TOKENS) -> list[dict]:
    """截断历史消息以适应上下文窗口"""
    if not history:
        return history

    total = sum(_estimate_tokens(m.get("content", "")) for m in history)
    if total <= max_tokens:
        return history

    truncated = list(history)
    while truncated and total > max_tokens:
        removed = truncated.pop(0)
        total -= _estimate_tokens(removed.get("content", ""))
    return truncated


class BaseAgent(ABC):
    """Agent 基类"""

    def __init__(self, agent_type: str):
        self.agent_type = agent_type
        self.system_prompt = AGENT_PROMPTS.get(agent_type, "")
        self._llm = None

    def _get_llm(self):
        """延迟创建 LLM 实例"""
        if self._llm is not None:
            return self._llm

        self._llm = AgentFactory.build_llm(self.agent_type)
        return self._llm

    def _build_messages(self, message: str, history: Optional[list[dict]] = None) -> list[dict]:
        """构建消息列表"""
        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            for msg in _truncate_history(history):
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                })
        messages.append({"role": "user", "content": message})
        return messages

    async def process(self, message: str, history: Optional[list[dict]] = None) -> str:
        """处理消息（非流式，用于 pipeline）"""
        llm = self._get_llm()
        if not llm:
            return f"[模拟回复] {self.agent_type} 收到消息：{message}\n\n请配置 AI API Key 来获得真实回复。"

        messages = self._build_messages(message, history)
        response = await llm.ainvoke(messages)

        usage = getattr(response, "usage", {})
        if usage:
            model_router.record_usage(
                model=llm.model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            )

        content = response.content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(item.get("text", str(item)))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content) if content is not None else ""

    async def astream(self, message: str, history: Optional[list[dict]] = None) -> AsyncGenerator[str, None]:
        """流式处理消息（用于前端实时渲染）"""
        llm = self._get_llm()
        if not llm:
            yield f"[模拟回复] {self.agent_type} 收到消息：{message}"
            return

        if not hasattr(llm, "astream"):
            result = await self.process(message, history)
            yield result
            return

        messages = self._build_messages(message, history)
        async for chunk in llm.astream(messages):
            yield chunk


class SimpleAgent(BaseAgent):
    """简单 Agent 实现"""

    def __init__(self, agent_type: str):
        super().__init__(agent_type)


class AgentFactory:
    """Agent 工厂"""

    _agents: dict[str, BaseAgent] = {}
    _db_llm_config: Optional[dict] = None

    @classmethod
    def get_agent(cls, agent_type: str) -> BaseAgent:
        if agent_type not in cls._agents:
            cls._agents[agent_type] = SimpleAgent(agent_type)
        return cls._agents[agent_type]

    @classmethod
    async def load_llm_from_db(cls, db):
        """从数据库加载默认 LLM 配置"""
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
        cls._agents.clear()

    @classmethod
    def build_llm(cls, agent_type: str = "PM"):
        """根据 agent_type 和配置创建 LLM 实例"""
        cfg = cls._db_llm_config
        route = model_router.get_model_for_agent(agent_type)

        if cfg:
            return cls._build_from_db_config(cfg)

        return cls._build_from_route(route)

    @classmethod
    def _build_from_db_config(cls, cfg: dict):
        """从数据库配置创建 LLM"""
        provider = cfg["provider"].lower()
        if provider in ("zhipu", "glm", "zai", "chatglm"):
            from app.ai.glm_provider import ChatGLM
            return ChatGLM(
                model=cfg["model_name"],
                max_tokens=cfg["max_tokens"],
                api_key=cfg["api_key"],
            )
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
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=cfg["model_name"],
                max_tokens=cfg["max_tokens"],
                api_key=cfg["api_key"],
            )
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
        return None

    @classmethod
    def _build_from_route(cls, route):
        """从模型路由配置创建 LLM"""
        if route.provider == "glm":
            if settings.zai_api_key:
                from app.ai.glm_provider import ChatGLM
                return ChatGLM(
                    model=route.model_name,
                    max_tokens=route.max_tokens,
                    api_key=settings.zai_api_key,
                    temperature=route.temperature,
                )
        elif route.provider == "anthropic":
            if settings.claude_api_key:
                from langchain_anthropic import ChatAnthropic
                return ChatAnthropic(
                    model=route.model_name,
                    max_tokens=route.max_tokens,
                    api_key=settings.claude_api_key,
                )
        # Fallback: 任何可用的 provider
        if settings.zai_api_key:
            from app.ai.glm_provider import ChatGLM
            return ChatGLM(
                model=settings.zai_default_model,
                max_tokens=settings.zai_max_tokens,
                api_key=settings.zai_api_key,
            )
        if settings.claude_api_key:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=settings.claude_default_model,
                max_tokens=settings.claude_max_tokens,
                api_key=settings.claude_api_key,
            )
        return None


class AgentService:
    """Agent 对话服务"""

    def __init__(self):
        self.sessions: dict[str, list[dict]] = {}

    def generate_msg_id(self) -> str:
        return f"msg_{uuid.uuid4().hex[:16]}"

    def generate_session_id(self) -> str:
        return f"sess_{uuid.uuid4().hex[:16]}"

    async def chat(
        self,
        session_id: str,
        message: str,
        agent_type: str = AgentType.PM,
        project_id: Optional[str] = None,
    ) -> dict:
        """处理对话（非流式）"""
        agent = AgentFactory.get_agent(agent_type)
        history = self.sessions.get(session_id, [])
        reply = await agent.process(message, history)

        if session_id not in self.sessions:
            self.sessions[session_id] = []
        self.sessions[session_id].append({"role": "user", "content": message})
        self.sessions[session_id].append({"role": "assistant", "content": reply})

        if len(self.sessions[session_id]) > 20:
            self.sessions[session_id] = self.sessions[session_id][-20:]

        return {
            "session_id": session_id,
            "msg_id": self.generate_msg_id(),
            "agent_type": agent_type,
            "reply": reply,
            "msg_type": "chat",
        }

    async def chat_stream(
        self,
        session_id: str,
        message: str,
        agent_type: str = AgentType.PM,
    ) -> AsyncGenerator[str, None]:
        """流式对话"""
        agent = AgentFactory.get_agent(agent_type)
        history = self.sessions.get(session_id, [])

        full_reply = ""
        async for chunk in agent.astream(message, history):
            full_reply += chunk
            yield chunk

        if session_id not in self.sessions:
            self.sessions[session_id] = []
        self.sessions[session_id].append({"role": "user", "content": message})
        self.sessions[session_id].append({"role": "assistant", "content": full_reply})

        if len(self.sessions[session_id]) > 20:
            self.sessions[session_id] = self.sessions[session_id][-20:]

    def get_session_messages(self, session_id: str) -> list[dict]:
        return self.sessions.get(session_id, [])

    def create_session(self) -> str:
        session_id = self.generate_session_id()
        self.sessions[session_id] = []
        return session_id

    def delete_session(self, session_id: str) -> bool:
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False


agent_service = AgentService()
