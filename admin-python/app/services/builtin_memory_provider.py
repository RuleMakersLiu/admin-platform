"""Built-in memory provider wrapping MemoryService."""
import json
import logging
from typing import Any, Dict, List, Optional

from app.services.memory_provider import MemoryProvider
from app.services.memory_service import MemoryService, MemoryType
from app.core.database import async_session_maker

logger = logging.getLogger(__name__)


class BuiltinMemoryProvider(MemoryProvider):
    """Built-in memory provider using MemoryService (SQLAlchemy)."""

    def __init__(self):
        self._session_id: str = ""
        self._project_id: Optional[int] = None
        self._tenant_id: int = 1

    @property
    def name(self) -> str:
        return "builtin"

    def is_available(self) -> bool:
        return True

    def initialize(self, session_id: str, **kwargs) -> None:
        self._session_id = session_id
        self._project_id = kwargs.get("project_id")
        self._tenant_id = kwargs.get("tenant_id", 1)

    def system_prompt_block(self) -> str:
        return (
            "You have persistent memory across sessions. "
            "Save important facts, user preferences, and project conventions. "
            "Use the memory tools to add, search, and retrieve memories."
        )

    async def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Retrieve relevant memories for context injection."""
        sid = session_id or self._session_id
        async with async_session_maker() as session:
            context = await MemoryService.get_memory_context(
                session,
                session_id=sid,
                project_id=self._project_id,
            )
        return context

    async def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        """Optionally extract and save key facts from the turn."""
        # Auto-save is handled by the pipeline, not here
        pass

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "memory_add",
                "description": "Save information to persistent memory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Content to save",
                        },
                        "memory_type": {
                            "type": "string",
                            "enum": ["short_term", "long_term", "semantic"],
                        },
                        "importance": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                        },
                    },
                    "required": ["content"],
                },
            },
            {
                "name": "memory_search",
                "description": "Search persistent memory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            },
        ]

    async def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        """Handle memory tool calls."""
        try:
            async with async_session_maker() as session:
                if tool_name == "memory_add":
                    memory_type = args.get("memory_type", MemoryType.LONG_TERM)
                    memory = await MemoryService.save_memory(
                        session,
                        session_id=self._session_id,
                        agent_type=kwargs.get("agent_type", "SYSTEM"),
                        content=args["content"],
                        tenant_id=self._tenant_id,
                        memory_type=memory_type,
                        importance=args.get("importance"),
                        project_id=self._project_id,
                    )
                    await session.commit()
                    return json.dumps({"success": True, "memory_id": memory.memory_id})

                elif tool_name == "memory_search":
                    results = await MemoryService.search_memories(
                        session,
                        project_id=self._project_id or 0,
                        query=args["query"],
                        tenant_id=self._tenant_id,
                        limit=args.get("limit", 10),
                    )
                    return json.dumps({
                        "results": [
                            {
                                "memory_id": m.memory_id,
                                "key_info": m.key_info,
                                "importance": m.importance,
                            }
                            for m in results
                        ]
                    })

                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            logger.error("BuiltinMemoryProvider tool call '%s' failed: %s", tool_name, e)
            return json.dumps({"error": str(e)})
