"""GLM LLM Provider - 统一版本，支持流式和非流式响应

支持的模型: GLM-4, GLM-4-Plus, GLM-4-Flash, GLM-5
"""
import json
import logging
import time
from contextvars import ContextVar
from typing import AsyncGenerator, Optional

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = logging.getLogger(__name__)

# 当前 LLM 调用来源/阶段（chat/vision/judge/requirement/prototype…），供延迟指标归因。
# flow_manager 执行某阶段前 bind_call_stage(stage_key)，glm_provider 记录时读取。
_call_stage_ctx: ContextVar = ContextVar("llm_call_stage", default=None)


def bind_call_stage(stage: Optional[str]):
    """设置当前调用阶段；返回 token，用 reset_call_stage(token) 复位。"""
    return _call_stage_ctx.set(stage)


def reset_call_stage(token):
    try:
        _call_stage_ctx.reset(token)
    except (LookupError, ValueError):
        pass


def _safe_record_usage(model: str, input_tokens: int, output_tokens: int,
                       latency_ms: Optional[int], ttft_ms: Optional[int],
                       success: bool, error: Optional[str], stage: Optional[str]) -> None:
    """集中记录单次 LLM 调用的用量+延迟+成功指标。永不抛异常（不影响业务调用）。"""
    try:
        from app.ai.model_router import model_router
        model_router.record_usage(
            model=model, input_tokens=input_tokens, output_tokens=output_tokens,
            latency_ms=latency_ms, ttft_ms=ttft_ms, success=success,
            error=error, stage=stage or _call_stage_ctx.get(),
        )
    except Exception:  # noqa: BLE001
        logger.debug("record_usage failed (ignored)", exc_info=True)

GLM_API_URL = "https://open.bigmodel.cn/api/paas/v4"

# 模型配置: model_name -> (max_tokens_default, supports_tools, is_reasoning)
MODEL_CONFIG = {
    "glm-4": (4096, False, False),
    "glm-4-plus": (4096, True, False),
    "glm-4-flash": (4096, True, False),
    "glm-4-long": (16384, False, False),
    "glm-5": (4096, True, False),
    "glm-5.1": (16384, True, True),
    # 视觉模型（多模态，OpenAI 兼容 content-array）
    # NOTE: GLM-4V 系列 max_tokens 上限 2048（>2048 报 1210「max_tokens参数非法」），故首位置 2048。
    "glm-4v": (2048, False, False),
    "glm-4v-plus": (2048, False, False),
    "glm-4v-flash": (2048, False, False),
}

# 模型输入上下文窗口（token）——供 token_budget.trim_message_for_window 防超窗。
# GLM-4 系列 128k；glm-4-long 1M；glm-4v 系列 8k（视觉模型窗口小，需注意图片+文本别超）；glm-5/5.1 128k。
MODEL_INPUT_WINDOWS = {
    "glm-4": 128000, "glm-4-plus": 128000, "glm-4-flash": 128000, "glm-4-long": 1_000_000,
    "glm-5": 128000, "glm-5.1": 128000,
    "glm-4v": 8192, "glm-4v-plus": 8192, "glm-4v-flash": 8192,
}

# 推理模型需要更多 token（reasoning tokens 计入 max_tokens）
REASONING_MODEL_PREFIXES = ("glm-5",)


def _is_reasoning_model(model: str) -> bool:
    """检测推理模型（reasoning tokens 消耗 max_tokens 预算）"""
    return any(model.startswith(p) for p in REASONING_MODEL_PREFIXES)


def _is_retryable_http(exc: BaseException) -> bool:
    """HTTP 重试判定：429、5xx 或网络层错误才重试，其余 4xx 立即失败。"""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    return isinstance(exc, httpx.RequestError)


def _parse_content(raw) -> str:
    """统一处理 content 字段（字符串或 content blocks 数组）"""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts = []
        for item in raw:
            if isinstance(item, dict):
                parts.append(item.get("text", str(item)))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(raw) if raw is not None else ""


def build_vision_messages(
    prompt: str, image_data_urls: list[str], system: Optional[str] = None
) -> list[dict]:
    """构造 GLM-4V（OpenAI 兼容）多模态消息：文本 + 若干图像。

    image_data_urls 元素为 data URI（``data:image/png;base64,...``）或可公网访问的图片 URL。
    返回可直接传给 ``ChatGLM(model=settings.zai_vision_model).ainvoke`` 的 messages 列表。
    """
    content: list = [{"type": "text", "text": prompt}]
    for url in image_data_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": content})
    return messages


class GLMMessage:
    """GLM 响应消息，兼容 LangChain 接口"""

    def __init__(self, content: str, usage: Optional[dict] = None):
        self._content = content
        self.usage = usage or {}

    @property
    def content(self) -> str:
        return self._content

    @content.setter
    def content(self, value: str):
        self._content = value


class ChatGLM:
    """GLM 聊天类（兼容 LangChain 接口），统一支持流式和非流式"""

    def __init__(
        self,
        model: str = "glm-4-flash",
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        thinking: Optional[dict] = None,
    ):
        self.model = model
        self.api_key = api_key or settings.zai_api_key
        config = MODEL_CONFIG.get(model, (4096, False, False))
        default_max = config[0]
        self.max_tokens = max_tokens or default_max

        # 推理模型的 reasoning tokens 消耗 max_tokens 预算，需要 4x 余量
        if _is_reasoning_model(model) and self.max_tokens < 8192:
            self.max_tokens = max(self.max_tokens * 4, 16384)
        self.temperature = temperature
        self.thinking = thinking
        # response_format（如 {"type": "json_object"}），由 flow_manager override 机制注入
        self.response_format: Optional[dict] = None
        self._client: Optional[httpx.AsyncClient] = None

        if not self.api_key:
            raise ValueError("GLM API Key 未配置")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            # 推理模型需要更长时间
            timeout = 900.0  # 匹配 LLM_STAGE_TIMEOUT，防 httpx 先于 stage 超时放弃 GLM 调用
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _build_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, messages: list, stream: bool = False) -> dict:
        glm_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                glm_messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                })
            elif hasattr(msg, "role") and hasattr(msg, "content"):
                glm_messages.append({"role": msg.role, "content": msg.content})
            else:
                glm_messages.append({"role": "user", "content": str(msg)})

        payload = {
            "model": self.model,
            "messages": glm_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": stream,
        }
        if self.thinking:
            payload["thinking"] = self.thinking
        if self.response_format:
            payload["response_format"] = self.response_format
        return payload

    async def ainvoke(self, messages: list) -> GLMMessage:
        """异步非流式调用（含延迟/成功指标采集，每条逻辑调用记录一次）。"""
        t0 = time.monotonic()
        try:
            content, usage = await self._do_invoke(messages)
        except Exception as exc:
            _safe_record_usage(
                self.model, 0, 0,
                latency_ms=int((time.monotonic() - t0) * 1000), ttft_ms=None,
                success=False, error=str(exc), stage=None,
            )
            raise
        _safe_record_usage(
            self.model,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            latency_ms=int((time.monotonic() - t0) * 1000), ttft_ms=None,
            success=True, error=None, stage=None,
        )
        return GLMMessage(content=content, usage=usage)

    async def _do_invoke(self, messages: list) -> tuple[str, dict]:
        """实际非流式调用 + 推理模型 max_tokens 自适应重试（不记录指标，避免重复计数）。"""
        client = await self._get_client()
        payload = self._build_payload(messages, stream=False)

        response = await client.post(
            f"{GLM_API_URL}/chat/completions",
            headers=self._build_headers(),
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

        content = _parse_content(result["choices"][0]["message"]["content"])
        usage = result.get("usage", {})

        # 推理模型可能用光 max_tokens 做 reasoning，导致 content 为空
        # 自动增大 max_tokens 重试一次
        if not content and _is_reasoning_model(self.model):
            reasoning_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
            total_tokens = usage.get("completion_tokens", 0)
            if reasoning_tokens > 0 and total_tokens >= self.max_tokens * 0.9:
                old_max = self.max_tokens
                self.max_tokens = max(self.max_tokens * 2, 32768)
                logger.warning(
                    f"Reasoning model used {reasoning_tokens}/{old_max} tokens for thinking, "
                    f"retrying with max_tokens={self.max_tokens}"
                )
                return await self._do_invoke(messages)

        return content, usage

    async def astream(self, messages: list) -> AsyncGenerator[str, None]:
        """异步流式调用，yield SSE 格式的 JSON 字符串（含首字延迟/总延迟采集）。"""
        client = await self._get_client()
        payload = self._build_payload(messages, stream=True)

        full_content = ""
        t0 = time.monotonic()
        tfirst: Optional[float] = None

        try:
            async with client.stream(
                "POST",
                f"{GLM_API_URL}/chat/completions",
                headers=self._build_headers(),
                json=payload,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or line == "data: [DONE]":
                        continue
                    if not line.startswith("data: "):
                        continue

                    try:
                        data = json.loads(line[6:])
                        choices = data.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})
                        chunk = delta.get("content", "")
                        if chunk:
                            if tfirst is None:
                                tfirst = time.monotonic()
                            full_content += chunk
                            yield json.dumps({
                                "type": "chunk",
                                "content": chunk,
                                "done": False,
                            }, ensure_ascii=False)
                    except json.JSONDecodeError:
                        continue
        except Exception as exc:
            _safe_record_usage(
                self.model, 0, max(1, len(full_content) // 3),
                latency_ms=int((time.monotonic() - t0) * 1000),
                ttft_ms=int((tfirst - t0) * 1000) if tfirst else None,
                success=False, error=str(exc), stage=None,
            )
            raise

        latency_ms = int((time.monotonic() - t0) * 1000)
        ttft_ms = int((tfirst - t0) * 1000) if tfirst else None
        _safe_record_usage(
            self.model, 0, max(1, len(full_content) // 3),
            latency_ms=latency_ms, ttft_ms=ttft_ms,
            success=True, error=None, stage=None,
        )

        yield json.dumps({
            "type": "done",
            "content": full_content,
            "done": True,
        }, ensure_ascii=False)

    async def aembed(self, inputs: list[str], model: Optional[str] = None) -> list[list[float]]:
        """异步批量 embedding，返回与 inputs 顺序一致的向量列表。

        复用 chat 的 httpx client / api_key，端点 {GLM_API_URL}/embeddings。
        模型默认取 settings.zai_embedding_model（GLM embedding-3, 1024 维）。
        """
        if not inputs:
            return []
        client = await self._get_client()
        embed_model = model or settings.zai_embedding_model or "embedding-3"
        payload = {
            "model": embed_model,
            "input": inputs,
            "dimensions": settings.zai_embedding_dimensions,
        }

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception(_is_retryable_http),
            reraise=True,
        )
        async def _call() -> list[list[float]]:
            response = await client.post(
                f"{GLM_API_URL}/embeddings",
                headers=self._build_headers(),
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            data = result.get("data", []) or []
            if len(data) != len(inputs):
                raise RuntimeError(
                    f"embedding response count mismatch: got {len(data)}, expected {len(inputs)}"
                )
            return [item["embedding"] for item in data]

        return await _call()
