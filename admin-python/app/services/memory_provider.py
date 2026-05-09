"""Memory Provider abstract base class.

Defines the lifecycle interface for memory providers.
Following the Hermes Agent MemoryProvider pattern.
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemoryProvider(ABC):
    """Abstract base class for memory providers.

    Lifecycle:
      initialize()          -- connect, warm up
      prefetch(query)       -- background recall before each turn
      sync_turn(user, asst) -- persist after each turn
      get_tool_schemas()    -- tool schemas to expose
      handle_tool_call()    -- dispatch a tool call
      shutdown()            -- clean exit

    Optional hooks:
      on_turn_start(turn, message, **kwargs)
      on_session_end(messages)
      on_pre_compress(messages) -> str
      on_memory_write(action, target, content)
      on_delegation(task, result, **kwargs)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier (e.g. 'builtin', 'external')."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider is ready."""

    @abstractmethod
    def initialize(self, session_id: str, **kwargs) -> None:
        """Initialize for a session."""

    def system_prompt_block(self) -> str:
        """Return text to include in the system prompt."""
        return ""

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Recall relevant context for the upcoming turn."""
        return ""

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        """Persist a completed turn."""

    @abstractmethod
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return tool schemas this provider exposes (OpenAI function calling format)."""
        return []

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        """Handle a tool call."""
        raise NotImplementedError

    def shutdown(self) -> None:
        """Clean shutdown."""

    def on_turn_start(self, turn_number: int, message: str, **kwargs) -> None:
        """Called at the start of each turn."""

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Called when a session ends."""

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        """Called before context compression. Return text to preserve."""
        return ""

    def on_memory_write(self, action: str, target: str, content: str) -> None:
        """Called when memory is written."""

    def on_delegation(self, task: str, result: str, **kwargs) -> None:
        """Called when a subagent completes."""
