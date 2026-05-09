"""AI 前沿技术自动升级服务

每日自动搜索 Top 10 AI 前沿技术，分析是否可应用于本项目，
生成升级建议，并保存到知识库供流水线 Agent 参考。
"""
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents import AgentService, AgentType
from app.models.agent_models import AgentKnowledge
from app.services.memory_service import MemoryService, MemoryType
from app.core.database import async_session_maker

logger = logging.getLogger(__name__)

# 搜索关键词（覆盖 AI Agent、LLM、开发工具等方向）
SEARCH_QUERIES = [
    "AI agent framework 2026",
    "multi-agent collaboration system",
    "LLM code generation latest",
    "AI automated testing framework",
    "AI DevOps automation",
    "LangChain LangGraph latest release",
    "Claude API new features",
    "GLM-5 ChatGLM update",
    "AI self-healing code system",
    "AI workflow orchestration new",
]


class AIUpgradeService:
    """AI 前沿技术升级服务"""

    def __init__(self):
        self.agent_service = AgentService()

    async def search_ai_news(self) -> List[Dict[str, Any]]:
        """搜索 AI 前沿技术新闻

        使用 WebSearch 搜索，如果不可用则使用内置知识库。
        """
        news_items = []

        try:
            # 尝试通过 httpx 调用外部搜索 API
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                for query in SEARCH_QUERIES:
                    try:
                        # 使用 DuckDuckGo 或类似无 Key 搜索
                        resp = await client.get(
                            "https://api.duckduckgo.com/",
                            params={"q": query, "format": "json", "no_redirect": 1},
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get("AbstractText"):
                                news_items.append({
                                    "query": query,
                                    "title": data.get("Heading", query),
                                    "summary": data.get("AbstractText", ""),
                                    "url": data.get("AbstractURL", ""),
                                    "source": "duckduckgo",
                                })
                            # 解析 RelatedTopics
                            for topic in data.get("RelatedTopics", [])[:3]:
                                if isinstance(topic, dict) and topic.get("Text"):
                                    news_items.append({
                                        "query": query,
                                        "title": topic.get("Text", "")[:80],
                                        "summary": topic.get("Text", ""),
                                        "url": topic.get("FirstURL", ""),
                                        "source": "duckduckgo",
                                    })
                    except Exception as e:
                        logger.warning(f"Search failed for '{query}': {e}")
                        continue

        except ImportError:
            logger.warning("httpx not available, using knowledge base only")

        # 如果搜索结果不足，补充内置热点
        if len(news_items) < 10:
            news_items.extend(self._get_builtin_trends())

        return news_items[:20]  # 最多保留 20 条

    def _get_builtin_trends(self) -> List[Dict[str, Any]]:
        """内置 AI 前沿趋势（当外部搜索不可用时的降级方案）"""
        now = datetime.now().strftime("%Y-%m-%d")
        return [
            {
                "query": "AI agent trend",
                "title": "Multi-Agent Orchestration: 从顺序执行到并行协作",
                "summary": "最新研究表明，多智能体系统正在从简单的顺序管道演变为"
                          "并行协作模式。关键技术：Agent 间共享工作记忆、"
                          "动态任务分配、冲突解决机制。可应用于优化当前 PM→BE/FE→QA 流程。",
                "url": "",
                "source": "builtin",
                "date": now,
            },
            {
                "query": "self-healing code",
                "title": "AI Self-Healing Code: 代码自动修复最新进展",
                "summary": "自动化代码修复系统已能处理 70%+ 的常见 Bug。"
                          "关键技术：基于 AST 的代码分析、错误模式匹配、"
                          "增量修复（只修改问题部分而非重写）。建议集成到 code_review 阶段。",
                "url": "",
                "source": "builtin",
                "date": now,
            },
            {
                "query": "LLM testing",
                "title": "LLM 驱动的自动化测试生成",
                "summary": "基于 LLM 的测试用例生成工具可在几秒内生成覆盖率达到 80%+ 的测试。"
                          "新技术：Property-based testing + LLM、Mutation testing、"
                          "Contract testing 自动化。可优化 QA Agent 的测试能力。",
                "url": "",
                "source": "builtin",
                "date": now,
            },
            {
                "query": "AI workflow",
                "title": "AI 工作流引擎：从固定流水线到自适应工作流",
                "summary": "新一代工作流引擎支持运行时动态调整阶段顺序、"
                          "条件分支、并行执行。关键：DAG 编排、状态机、"
                          "事件驱动架构。建议将 flow_manager 升级为 DAG 模式。",
                "url": "",
                "source": "builtin",
                "date": now,
            },
            {
                "query": "prompt optimization",
                "title": "Prompt 自动优化技术：DSPy 与 OPRO",
                "summary": "DSPy 框架可通过自动调优提升 Prompt 效果 30%+。"
                          "OPRO (Optimization by PROmpting) 使用 LLM 自身来优化 Prompt。"
                          "建议集成到 Agent 配置管理中。",
                "url": "",
                "source": "builtin",
                "date": now,
            },
            {
                "query": "RAG technology",
                "title": "RAG 2.0: 检索增强生成的最新突破",
                "summary": "RAG 2.0 结合了查询重写、混合检索、重排序、"
                          "自适应 chunk 等技术。建议升级知识库系统，"
                          "使用向量数据库 + 语义搜索替代当前的 LIKE 搜索。",
                "url": "",
                "source": "builtin",
                "date": now,
            },
            {
                "query": "AI CI/CD",
                "title": "AI 驱动的 CI/CD: 智能化部署Pipeline",
                "summary": "AI 可以预测构建失败风险、自动选择最优部署策略、"
                          "实时监控异常并回滚。建议将部署阶段升级为 AI 决策驱动。",
                "url": "",
                "source": "builtin",
                "date": now,
            },
            {
                "query": "AI code review",
                "title": "AI Code Review 2.0: 从规则检查到深度理解",
                "summary": "新一代 AI Code Review 能理解业务逻辑、"
                          "检测安全漏洞、建议架构改进。"
                          "关键：AST + LLM 联合分析、上下文感知。可增强 QA Agent。",
                "url": "",
                "source": "builtin",
                "date": now,
            },
            {
                "query": "agent memory",
                "title": "Agent 记忆系统：从短期上下文到长期知识",
                "summary": "新一代 Agent 记忆架构包含：工作记忆（当前任务）、"
                          "情景记忆（历史经验）、语义记忆（领域知识）。"
                          "建议将 MemoryService 升级为分层记忆架构。",
                "url": "",
                "source": "builtin",
                "date": now,
            },
            {
                "query": "evaluation metrics",
                "title": "AI Agent 评估框架：如何衡量 Agent 质量",
                "summary": "新的 Agent 评估指标包括：任务完成率、"
                          "代码质量分数、修复迭代次数、端到端延迟。"
                          "建议为流水线添加质量仪表盘和 KPI 追踪。",
                "url": "",
                "source": "builtin",
                "date": now,
            },
        ]

    async def analyze_with_agent(self, news_items: List[Dict[str, Any]],
                                  tenant_id: int = 0) -> Dict[str, Any]:
        """使用 PM Agent 分析 AI 新闻，生成升级建议"""
        news_text = "\n\n".join([
            f"### {i+1}. {item['title']}\n{item['summary']}"
            for i, item in enumerate(news_items[:10])
        ])

        prompt = f"""你是一个技术架构师，请分析以下 AI 前沿技术趋势，
评估哪些可以应用到我们的开发流水线系统中。

当前系统架构：
- 多智能体协作：PM → PJM → BE/FE → QA → RPT
- 技术栈：Python FastAPI + Go Gin + React + PostgreSQL
- 已有功能：代码生成、Code Review、自动测试、部署
- 已有基础设施：AgentMemory、知识库、WebSocket

## 今日 AI 前沿技术 Top 10

{news_text}

请输出 JSON 格式的分析报告（用 ```json 包裹），包含：
1. "top_picks": 选择 3-5 个最值得集成的技术，每个包含 "title", "reason", "priority"(高/中/低), "implementation_effort"(小/中/大)
2. "upgrade_plan": 具体的升级计划，按优先级排列
3. "risk_assessment": 升级风险评估
4. "expected_improvement": 预期提升效果"""

        try:
            result = await self.agent_service.chat(
                session_id=f"ai_upgrade_{datetime.now().strftime('%Y%m%d')}",
                message=prompt,
                agent_type=AgentType.PM,
            )
            return {
                "analysis": result["reply"],
                "news_count": len(news_items),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Agent analysis failed: {e}")
            return {
                "analysis": f"分析失败: {e}",
                "news_count": len(news_items),
                "timestamp": datetime.now().isoformat(),
            }

    async def save_to_knowledge(self, analysis_result: Dict[str, Any],
                                 tenant_id: int = 1) -> str:
        """将升级分析保存到知识库，供流水线 Agent 参考"""
        async with async_session_maker() as session:
            now = int(time.time() * 1000)
            knowledge_id = f"KN{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"

            knowledge = AgentKnowledge(
                knowledge_id=knowledge_id,
                tenant_id=tenant_id,
                title=f"AI前沿技术升级报告 - {datetime.now().strftime('%Y-%m-%d')}",
                content=analysis_result.get("analysis", ""),
                category="ai_upgrade",
                tags="ai,upgrade,frontier,daily",
                source="auto_upgrade",
                version=1,
                view_count=0,
                embedding_status="pending",
                create_time=now,
                update_time=now,
                is_deleted=0,
            )

            session.add(knowledge)

            # 同时保存为长期记忆
            await MemoryService.save_memory(
                db=session,
                session_id="ai_upgrade_daily",
                agent_type="PM",
                content=f"[AI升级报告 {datetime.now().strftime('%Y-%m-%d')}] "
                        f"分析了 {analysis_result.get('news_count', 0)} 条 AI 前沿技术",
                tenant_id=tenant_id,
                memory_type=MemoryType.LONG_TERM,
                key_info=f"ai_upgrade:{datetime.now().strftime('%Y-%m-%d')}",
                importance=90,
            )

            await session.commit()

        logger.info(f"AI upgrade report saved: {knowledge_id}")
        return knowledge_id

    async def run_daily_upgrade(self, tenant_id: int = 1) -> Dict[str, Any]:
        """执行每日 AI 升级流程（入口方法）"""
        logger.info("Starting daily AI upgrade analysis...")

        # Step 1: 搜索 AI 前沿新闻
        news_items = await self.search_ai_news()
        logger.info(f"Found {len(news_items)} AI news items")

        # Step 2: 使用 Agent 分析
        analysis = await self.analyze_with_agent(news_items, tenant_id)
        logger.info("Agent analysis completed")

        # Step 3: 保存到知识库
        knowledge_id = await self.save_to_knowledge(analysis, tenant_id)
        logger.info(f"Saved to knowledge base: {knowledge_id}")

        return {
            "status": "success",
            "news_count": len(news_items),
            "knowledge_id": knowledge_id,
            "analysis_preview": analysis.get("analysis", "")[:200],
            "timestamp": datetime.now().isoformat(),
        }


# 全局服务实例
ai_upgrade_service = AIUpgradeService()
