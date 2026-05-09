"""Memory Manager -- orchestrates memory providers.

Central integration point. Delegates to registered providers.
Built-in provider (MemoryService) is always first.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.services.memory_provider import MemoryProvider

logger = logging.getLogger(__name__)

_FENCE_TAG_RE = re.compile(r'</?\s*memory-context\s*>', re.IGNORECASE)
_INTERNAL_CONTEXT_RE = re.compile(
    r'<\s*memory-context\s*>[\s\S]*?</\s*memory-context\s*>',
    re.IGNORECASE,
)


def sanitize_context(text: str) -> str:
    """Strip fence tags from provider output."""
    text = _INTERNAL_CONTEXT_RE.sub('', text)
    text = _FENCE_TAG_RE.sub('', text)
    return text


def build_memory_context_block(raw_context: str) -> str:
    """Wrap prefetched memory in a fenced block."""
    if not raw_context or not raw_context.strip():
        return ""
    clean = sanitize_context(raw_context)
    return (
        "<memory-context>\n"
        "[System note: Recalled memory context, NOT new user input.]\n\n"
        f"{clean}\n"
        "</memory-context>"
    )


class MemoryManager:
    """Orchestrates memory providers.

    Built-in provider is always first. Only one external provider allowed.
    """

    def __init__(self):
        self._providers: List[MemoryProvider] = []
        self._tool_to_provider: Dict[str, MemoryProvider] = {}
        self._has_external = False

    def add_provider(self, provider: MemoryProvider) -> None:
        """Register a memory provider."""
        is_builtin = provider.name == "builtin"
        if not is_builtin:
            if self._has_external:
                logger.warning(
                    "Rejected external provider '%s' -- one already registered.",
                    provider.name,
                )
                return
            self._has_external = True

        self._providers.append(provider)
        for schema in provider.get_tool_schemas():
            tool_name = schema.get("name", "")
            if tool_name and tool_name not in self._tool_to_provider:
                self._tool_to_provider[tool_name] = provider
        logger.info(
            "Memory provider '%s' registered (%d tools)",
            provider.name,
            len(provider.get_tool_schemas()),
        )

    @property
    def providers(self) -> List[MemoryProvider]:
        return list(self._providers)

    def build_system_prompt(self) -> str:
        """Collect system prompt blocks from all providers."""
        blocks = []
        for p in self._providers:
            try:
                block = p.system_prompt_block()
                if block and block.strip():
                    blocks.append(block)
            except Exception as e:
                logger.warning("Provider '%s' system_prompt_block failed: %s", p.name, e)
        return "\n\n".join(blocks)

    def prefetch_all(self, query: str, *, session_id: str = "") -> str:
        """Collect prefetch context from all providers."""
        parts = []
        for p in self._providers:
            try:
                result = p.prefetch(query, session_id=session_id)
                if result and result.strip():
                    parts.append(result)
            except Exception as e:
                logger.debug("Provider '%s' prefetch failed: %s", p.name, e)
        return "\n\n".join(parts)

    def sync_all(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        """Sync a completed turn to all providers."""
        for p in self._providers:
            try:
                p.sync_turn(user_content, assistant_content, session_id=session_id)
            except Exception as e:
                logger.warning("Provider '%s' sync_turn failed: %s", p.name, e)

    def get_all_tool_schemas(self) -> List[Dict[str, Any]]:
        """Collect tool schemas from all providers."""
        schemas = []
        seen = set()
        for p in self._providers:
            try:
                for schema in p.get_tool_schemas():
                    name = schema.get("name", "")
                    if name and name not in seen:
                        schemas.append(schema)
                        seen.add(name)
            except Exception as e:
                logger.warning("Provider '%s' get_tool_schemas failed: %s", p.name, e)
        return schemas

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        """Route a tool call to the correct provider."""
        provider = self._tool_to_provider.get(tool_name)
        if provider is None:
            return json.dumps({"error": f"No provider handles tool '{tool_name}'"})
        try:
            return provider.handle_tool_call(tool_name, args, **kwargs)
        except Exception as e:
            return json.dumps({"error": f"Memory tool '{tool_name}' failed: {e}"})

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        for p in self._providers:
            try:
                p.on_session_end(messages)
            except Exception as e:
                logger.debug("Provider '%s' on_session_end failed: %s", p.name, e)

    def shutdown_all(self) -> None:
        for p in reversed(self._providers):
            try:
                p.shutdown()
            except Exception as e:
                logger.warning("Provider '%s' shutdown failed: %s", p.name, e)


# Global singleton
memory_manager = MemoryManager()
