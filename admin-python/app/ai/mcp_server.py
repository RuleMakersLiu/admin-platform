"""MCP (Model Context Protocol) Server

将平台的 Skills 和知识库作为 MCP Tools 暴露，供任何 MCP 兼容客户端调用。

启动方式:
  python -m app.ai.mcp_server          # stdio transport
  或集成到 FastAPI 使用 SSE transport

MCP Tools:
  - list_skills: 列出所有可用技能
  - execute_skill: 执行指定技能
  - search_knowledge: 搜索知识库
  - get_knowledge: 获取知识详情
  - get_knowledge_graph: 获取知识图谱
  - get_pipeline_status: 获取流水线状态
  - create_pipeline: 创建开发流水线
"""
import asyncio
import json
import logging
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
)

logger = logging.getLogger(__name__)

server = Server("admin-platform")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """列出所有 MCP Tools"""
    return [
        Tool(
            name="list_skills",
            description="列出平台所有可用的 AI Agent 技能",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "按分类过滤: analysis, development, testing, deployment, knowledge",
                    },
                    "agent_type": {
                        "type": "string",
                        "description": "按Agent类型过滤: PM, PJM, BE, FE, QA, RPT, SYSTEM",
                    },
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
                    "skill_id": {
                        "type": "string",
                        "description": "技能ID，如 requirement_analysis, backend_development",
                    },
                    "params": {
                        "type": "object",
                        "description": "技能参数",
                    },
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
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """执行 MCP Tool 调用"""
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
            result = await skill_registry.execute(skill_id, **params)
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
            import json as _json
            return [TextContent(type="text", text=json.dumps({
                "knowledge_id": knowledge.knowledge_id,
                "title": knowledge.title,
                "content": knowledge.content,
                "category": knowledge.category,
                "tags": _json.loads(knowledge.tags) if knowledge.tags else [],
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

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"MCP tool error: {name} - {e}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


async def run_mcp_server():
    """启动 MCP Server (stdio transport)"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_mcp_server())
