"""LLM 调用：带重试 + 流式 + 超时 + 上下文裁剪的 agent 调用封装。

从 flow_manager 拆出。_call_agent_with_retry（非流式）与 _call_agent_with_retry_stream
（流式）都含：指数退避重试、上下文超长检测+裁剪重试、熔断感知。AgentFactory/
token_budget 在函数内 lazy import（随函数体搬走）。
"""
import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from app.ai.agents import AgentService

logger = logging.getLogger(__name__)

LLM_FINAL_REPLY_TIMEOUT = 90
LLM_STREAM_IDLE_TIMEOUT = 45
MAX_LLM_RETRIES = 3
RETRY_BASE_DELAY = 2

# 输入超长错误关键词（GLM 1301 / context length exceeded）——_is_context_length_error 用
_CONTEXT_LENGTH_KEYWORDS = ("context length", "maximum context", "too long", "输入过长", "超出上下文", "1301")


def _is_retriable_error(e: Exception) -> bool:
    """判断是否为可重试的错误"""
    error_str = str(e).lower()
    type_name = type(e).__name__.lower()
    retriable_keywords = ["timeout", "rate limit", "429", "503", "502", "500",
                          "connection", "overloaded", "capacity", "retry",
                          "connecterror", "timeouterror", "read error", "eof"]
    return any(kw in error_str for kw in retriable_keywords) or any(kw in type_name for kw in retriable_keywords)


def _is_context_length_error(e: Exception) -> bool:
    """判断是否为「输入超长」错误（GLM 1301 / context length exceeded）。"""
    s = str(e).lower()
    return any(kw in s for kw in _CONTEXT_LENGTH_KEYWORDS)


def _agent_model_name(agent_type: str) -> str:
    """取某 agent 类型当前用的 LLM 模型名（供 token 预算按模型窗口裁剪）。"""
    try:
        from app.ai.agents import AgentFactory
        agent = AgentFactory.get_agent(agent_type)
        llm = agent._get_llm() if hasattr(agent, "_get_llm") else getattr(agent, "_llm", None)
        return getattr(llm, "model", "") or ""
    except Exception:  # noqa: BLE001
        return ""


async def _call_agent_with_retry(agent_service: AgentService, session_id: str,
                                  message: str, agent_type: str,
                                  max_tokens_override: int = None,
                                  thinking_override: Optional[Dict[str, Any]] = None,
                                  response_format_override: Optional[dict] = None,
                                  attachments: list = None) -> str:
    """调用 Agent，自动重试可恢复的错误。

    上下文超长错误 → 截断 message（保尾部核心）后重试，避免直接失败；
    其他可重试错误（timeout/rate limit/5xx）→ 指数退避重试 MAX_LLM_RETRIES 次。
    """
    last_error = None
    original_max_tokens = None
    original_thinking = None
    original_response_format = None

    if max_tokens_override or thinking_override is not None or response_format_override is not None:
        from app.ai.agents import AgentFactory
        agent = AgentFactory.get_agent(agent_type)
        llm = agent._get_llm() if hasattr(agent, "_get_llm") else getattr(agent, "_llm", None)
        if max_tokens_override and llm and hasattr(llm, "max_tokens"):
            original_max_tokens = llm.max_tokens
            llm.max_tokens = max_tokens_override
        if llm and thinking_override is not None and hasattr(llm, "thinking"):
            original_thinking = llm.thinking
            llm.thinking = thinking_override
        if llm and response_format_override is not None and hasattr(llm, "response_format"):
            original_response_format = llm.response_format
            llm.response_format = response_format_override

    try:
        for attempt in range(MAX_LLM_RETRIES):
            try:
                logger.info(f"LLM call attempt {attempt + 1}/{MAX_LLM_RETRIES} for {session_id}")
                result = await agent_service.chat(
                    session_id=session_id,
                    message=message,
                    agent_type=agent_type,
                    attachments=attachments,
                )
                return result["reply"]

            except Exception as e:
                last_error = e
                if _is_context_length_error(e):
                    # 输入超长：截断 message（保尾部核心，丢头部上下文）后重试，而非直接失败
                    from app.ai.token_budget import trim_message_for_window
                    trimmed = trim_message_for_window(message, _agent_model_name(agent_type))
                    if trimmed != message:
                        logger.warning("Agent call context-length exceeded; trimming message and retrying (attempt %s/%s)",
                                       attempt + 1, MAX_LLM_RETRIES)
                        message = trimmed
                        continue
                    logger.error("Agent call context-length exceeded but message already minimal: %s", e)
                    raise
                if not _is_retriable_error(e):
                    logger.error(f"Agent call failed (permanent): {e}")
                    raise

                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"Agent call failed (retriable, attempt {attempt + 1}/{MAX_LLM_RETRIES}): {e}. "
                             f"Retrying in {delay}s...")
                await asyncio.sleep(delay)

        logger.error(f"Agent call failed after {MAX_LLM_RETRIES} retries: {last_error}")
        raise last_error
    finally:
        # 恢复原始 max_tokens
        if original_max_tokens is not None:
            from app.ai.agents import AgentFactory
            agent = AgentFactory.get_agent(agent_type)
            llm = getattr(agent, "_llm", None)
            if llm and hasattr(llm, "max_tokens"):
                llm.max_tokens = original_max_tokens
        if original_thinking is not None:
            from app.ai.agents import AgentFactory
            agent = AgentFactory.get_agent(agent_type)
            llm = getattr(agent, "_llm", None)
            if llm and hasattr(llm, "thinking"):
                llm.thinking = original_thinking
        if response_format_override is not None:
            from app.ai.agents import AgentFactory
            agent = AgentFactory.get_agent(agent_type)
            llm = getattr(agent, "_llm", None)
            if llm and hasattr(llm, "response_format"):
                llm.response_format = original_response_format


def _normalize_stream_chunk(chunk: Any) -> Tuple[str, bool, Optional[str]]:
    """Normalize raw LLM stream chunks into content/done/error fields."""
    if chunk is None:
        return "", False, None

    if hasattr(chunk, "content"):
        content = getattr(chunk, "content", "")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text") or item.get("content") or ""))
                else:
                    parts.append(str(item))
            content = "".join(parts)
        return str(content or ""), False, None

    if not isinstance(chunk, str):
        return str(chunk), False, None

    raw = chunk.strip()
    if not raw:
        return "", False, None
    if raw == "[DONE]" or raw == "data: [DONE]":
        return "", True, None
    if raw.startswith("data:"):
        raw = raw[5:].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return chunk, False, None

    if not isinstance(data, dict):
        return str(data), False, None

    error = data.get("error")
    if data.get("type") == "error":
        error = error or data.get("message")
    content = data.get("content") or data.get("delta") or data.get("text") or ""
    done = bool(data.get("done")) or data.get("type") in {"done", "complete"}
    return str(content), done, str(error) if error else None


async def _call_agent_with_retry_stream(
    agent_service: AgentService,
    session_id: str,
    message: str,
    agent_type: str,
    on_chunk: Callable[[str], Awaitable[None]],
    max_tokens_override: int = None,
    thinking_override: Optional[Dict[str, Any]] = None,
    response_format_override: Optional[dict] = None,
    attachments: list = None,
) -> str:
    """Call an agent with streaming chunks while preserving the final reply."""
    last_error = None
    original_max_tokens = None
    original_thinking = None
    original_response_format = None

    if max_tokens_override or thinking_override is not None or response_format_override is not None:
        from app.ai.agents import AgentFactory
        agent = AgentFactory.get_agent(agent_type)
        llm = agent._get_llm() if hasattr(agent, "_get_llm") else getattr(agent, "_llm", None)
        if max_tokens_override and llm and hasattr(llm, "max_tokens"):
            original_max_tokens = llm.max_tokens
            llm.max_tokens = max_tokens_override
        if llm and thinking_override is not None and hasattr(llm, "thinking"):
            original_thinking = llm.thinking
            llm.thinking = thinking_override
        if llm and response_format_override is not None and hasattr(llm, "response_format"):
            original_response_format = llm.response_format
            llm.response_format = response_format_override

    try:
        for attempt in range(MAX_LLM_RETRIES):
            emitted_any = False
            chunks: List[str] = []
            try:
                logger.info(
                    f"LLM stream attempt {attempt + 1}/{MAX_LLM_RETRIES} for {session_id}"
                )

                from app.ai.agents import AgentFactory
                agent = AgentFactory.get_agent(agent_type)
                history = agent_service.sessions.get(session_id, [])

                stream = agent.astream(message, history, attachments).__aiter__()
                while True:
                    try:
                        raw_chunk = await asyncio.wait_for(
                            stream.__anext__(),
                            timeout=LLM_STREAM_IDLE_TIMEOUT,
                        )
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        logger.warning(
                            "Agent stream idle for %ss, falling back to final reply for %s",
                            LLM_STREAM_IDLE_TIMEOUT,
                            session_id,
                        )
                        break

                    content, done, error = _normalize_stream_chunk(raw_chunk)
                    if error:
                        raise RuntimeError(error)
                    if content:
                        emitted_any = True
                        chunks.append(content)
                        await on_chunk(content)
                    if done:
                        break

                full_reply = "".join(chunks)
                if not full_reply.strip():
                    result = await asyncio.wait_for(
                        agent_service.chat(
                            session_id=session_id,
                            message=message,
                            agent_type=agent_type,
                            attachments=attachments,
                        ),
                        timeout=LLM_FINAL_REPLY_TIMEOUT,
                    )
                    full_reply = result.get("reply", "")
                    if full_reply:
                        await on_chunk(full_reply)

                if session_id not in agent_service.sessions:
                    agent_service.sessions[session_id] = []
                agent_service.sessions[session_id].append({"role": "user", "content": message})
                agent_service.sessions[session_id].append({"role": "assistant", "content": full_reply})
                if len(agent_service.sessions[session_id]) > 20:
                    agent_service.sessions[session_id] = agent_service.sessions[session_id][-20:]
                return full_reply

            except Exception as e:
                last_error = e
                error_label = "timeout waiting for final LLM reply" if isinstance(e, asyncio.TimeoutError) else str(e)
                if _is_context_length_error(e) and not emitted_any:
                    # 输入超长：截断 message（保尾部核心）后重试，而非直接失败
                    from app.ai.token_budget import trim_message_for_window
                    trimmed = trim_message_for_window(message, _agent_model_name(agent_type))
                    if trimmed != message:
                        logger.warning("Agent stream context-length exceeded; trimming and retrying (attempt %s/%s)",
                                       attempt + 1, MAX_LLM_RETRIES)
                        message = trimmed
                        continue
                    logger.error("Agent stream context-length exceeded but message already minimal: %s", e)
                    raise
                if emitted_any or not _is_retriable_error(e):
                    logger.error(f"Agent stream failed: {error_label}")
                    raise

                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"Agent stream failed (retriable, attempt {attempt + 1}/{MAX_LLM_RETRIES}): "
                    f"{error_label}. Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)

        logger.error(f"Agent stream failed after {MAX_LLM_RETRIES} retries: {last_error}")
        raise last_error
    finally:
        if original_max_tokens is not None:
            from app.ai.agents import AgentFactory
            agent = AgentFactory.get_agent(agent_type)
            llm = getattr(agent, "_llm", None)
            if llm and hasattr(llm, "max_tokens"):
                llm.max_tokens = original_max_tokens
        if original_thinking is not None:
            from app.ai.agents import AgentFactory
            agent = AgentFactory.get_agent(agent_type)
            llm = getattr(agent, "_llm", None)
            if llm and hasattr(llm, "thinking"):
                llm.thinking = original_thinking
        if response_format_override is not None:
            from app.ai.agents import AgentFactory
            agent = AgentFactory.get_agent(agent_type)
            llm = getattr(agent, "_llm", None)
            if llm and hasattr(llm, "response_format"):
                llm.response_format = original_response_format
