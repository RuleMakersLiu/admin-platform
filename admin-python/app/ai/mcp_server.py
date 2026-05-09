"""MCP (Model Context Protocol) Server

支持两种 transport:
  - stdio: 命令行模式 `python -m app.ai.mcp_server`
  - SSE: HTTP 长连接，可挂载到 FastAPI

MCP Tools:
  - list_skills / execute_skill / execute_skill_stream
  - search_knowledge / get_knowledge / get_knowledge_graph
  - get_pipeline_status / create_pipeline
  - stream_chat: 流式对话
  - get_usage_stats: Token 使用统计
"""
import asyncio
import json
import logging
import sys
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent, CallToolResult

logger = logging.getLogger(__name__)

server = Server("admin-platform")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_skills",
            description="列出平台所有可用的 AI Agent 技能",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "按分类过滤: analysis, development, testing, deployment, knowledge"},
                    "agent_type": {"type": "string", "description": "按Agent类型过滤: PM, PJM, BE, FE, QA, RPT, SYSTEM"},
                },
            },
        ),
        Tool(
            name="execute_skill",
            description="执行指定的 AI Agent 技能",
            inputSchema={
                "type": "object",
                "required": ["skill_id"],
                "properties": {
                    "skill_id": {"type": "string", "description": "技能ID"},
                    "params": {"type": "object", "description": "技能参数"},
                    "timeout": {"type": "integer", "description": "超时秒数", "default": 120},
                },
            },
        ),
        Tool(
            name="search_knowledge",
            description="搜索本地知识库",
            inputSchema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "category": {"type": "string", "description": "知识分类"},
                    "limit": {"type": "integer", "description": "返回数量", "default": 10},
                },
            },
        ),
        Tool(
            name="get_knowledge",
            description="获取知识条目详情",
            inputSchema={
                "type": "object",
                "required": ["knowledge_id"],
                "properties": {
                    "knowledge_id": {"type": "string", "description": "知识ID"},
                },
            },
        ),
        Tool(
            name="get_knowledge_graph",
            description="获取知识图谱（节点和关系）",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "按分类过滤"},
                    "max_nodes": {"type": "integer", "description": "最大节点数", "default": 50},
                },
            },
        ),
        Tool(
            name="create_pipeline",
            description="创建开发流水线（需求→开发→测试→部署）",
            inputSchema={
                "type": "object",
                "required": ["user_request"],
                "properties": {
                    "user_request": {"type": "string", "description": "用户需求描述"},
                    "project_id": {"type": "string", "description": "项目ID"},
                },
            },
        ),
        Tool(
            name="get_pipeline_status",
            description="获取流水线执行状态",
            inputSchema={
                "type": "object",
                "required": ["pipeline_id"],
                "properties": {
                    "pipeline_id": {"type": "string", "description": "流水线ID"},
                },
            },
        ),
        Tool(
            name="ai_upgrade_check",
            description="检查最新AI技术趋势并进行系统升级分析",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="stream_chat",
            description="与指定类型的 AI Agent 进行流式对话",
            inputSchema={
                "type": "object",
                "required": ["message"],
                "properties": {
                    "message": {"type": "string", "description": "用户消息"},
                    "agent_type": {"type": "string", "description": "Agent类型", "default": "PM"},
                    "session_id": {"type": "string", "description": "会话ID"},
                },
            },
        ),
        Tool(
            name="get_usage_stats",
            description="获取 Token 使用统计",
            inputSchema={
                "type": "object",
                "properties": {
                    "hours": {"type": "integer", "description": "统计最近N小时", "default": 24},
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "list_skills":
            from app.ai.skills import skill_registry
            skills = skill_registry.list_skills(
                category=arguments.get("category"),
                agent_type=arguments.get("agent_type"),
            )
            result = [
                {
                    "skill_id": s.skill_id,
                    "name": s.name,
                    "description": s.description,
                    "category": s.category,
                    "agent_type": s.agent_type,
                }
                for s in skills
            ]
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "execute_skill":
            from app.ai.skills import skill_registry
            skill_id = arguments["skill_id"]
            params = arguments.get("params", {})
            timeout = arguments.get("timeout", 120)
            result = await skill_registry.execute(skill_id, timeout_seconds=timeout, **params)
            return [TextContent(
                type="text",
                text=json.dumps({
                    "execution_id": result.execution_id,
                    "status": result.status,
                    "output": result.output,
                    "error": result.error,
                    "execution_time_ms": result.execution_time_ms,
                }, ensure_ascii=False, indent=2),
            )]

        elif name == "search_knowledge":
            from app.services.knowledge_service import knowledge_service
            results = await knowledge_service.search_knowledge(
                query=arguments["query"],
                category=arguments.get("category"),
                limit=arguments.get("limit", 10),
            )
            return [TextContent(type="text", text=json.dumps(results, ensure_ascii=False, indent=2))]

        elif name == "get_knowledge":
            from app.services.knowledge_service import knowledge_service
            knowledge = await knowledge_service.get_knowledge(arguments["knowledge_id"])
            if not knowledge:
                return [TextContent(type="text", text="Knowledge not found")]
            return [TextContent(type="text", text=json.dumps({
                "knowledge_id": knowledge.knowledge_id,
                "title": knowledge.title,
                "content": knowledge.content,
                "category": knowledge.category,
                "tags": json.loads(knowledge.tags) if knowledge.tags else [],
            }, ensure_ascii=False, indent=2))]

        elif name == "get_knowledge_graph":
            from app.services.knowledge_service import knowledge_service
            graph = await knowledge_service.get_graph(
                category=arguments.get("category"),
                max_nodes=arguments.get("max_nodes", 50),
            )
            return [TextContent(type="text", text=json.dumps(graph, ensure_ascii=False, indent=2))]

        elif name == "create_pipeline":
            from app.ai.pipeline_graph import pipeline_manager
            pipeline_id = await pipeline_manager.create_pipeline(
                user_request=arguments["user_request"],
                project_id=arguments.get("project_id", ""),
            )
            return [TextContent(type="text", text=json.dumps({
                "pipeline_id": pipeline_id,
                "status": "created",
            }, ensure_ascii=False, indent=2))]

        elif name == "get_pipeline_status":
            from app.ai.pipeline_graph import pipeline_manager
            status = await pipeline_manager.get_pipeline_status(arguments["pipeline_id"])
            return [TextContent(type="text", text=json.dumps(status, ensure_ascii=False, indent=2))]

        elif name == "ai_upgrade_check":
            from app.services.ai_upgrade_service import ai_upgrade_service
            result = await ai_upgrade_service.run_daily_upgrade()
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "stream_chat":
            from app.ai.agents import AgentService, AgentType
            agent_service = AgentService()
            session_id = arguments.get("session_id", "")
            if not session_id:
                session_id = agent_service.create_session()
            agent_type = arguments.get("agent_type", "PM")
            message = arguments["message"]

            full_reply = ""
            async for chunk in agent_service.chat_stream(session_id, message, agent_type):
                full_reply += chunk

            return [TextContent(type="text", text=json.dumps({
                "session_id": session_id,
                "agent_type": agent_type,
                "reply": full_reply,
            }, ensure_ascii=False, indent=2))]

        elif name == "get_usage_stats":
            from app.ai.model_router import model_router
            hours = arguments.get("hours", 24)
            stats = model_router.get_usage_stats(hours=hours)
            return [TextContent(type="text", text=json.dumps(stats, ensure_ascii=False, indent=2))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"MCP tool error: {name} - {e}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


# ==================== Transport ====================

async def run_mcp_server():
    """启动 MCP Server (stdio transport)"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def create_sse_app():
    """创建 SSE transport 的 Starlette app，可挂载到 FastAPI"""
    sse = SseServerTransport("/mcp/messages")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send,
        ) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )

    from starlette.applications import Starlette
    from starlette.routing import Route

    app = Starlette(
        routes=[
            Route("/mcp/sse", endpoint=handle_sse),
            Route("/mcp/messages", endpoint=sse.handle_post_message, methods=["POST"]),
        ],
    )
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_mcp_server())
