"""GLM LLM Provider - 统一版本，支持流式和非流式响应

支持的模型: GLM-4, GLM-4-Plus, GLM-4-Flash, GLM-5
"""
import json
import logging
from typing import AsyncGenerator, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

GLM_API_URL = "https://open.bigmodel.cn/api/paas/v4"

# 模型配置: model_name -> (max_tokens_default, supports_tools, is_reasoning)
MODEL_CONFIG = {
    "glm-4": (4096, False, False),
    "glm-4-plus": (4096, True, False),
    "glm-4-flash": (4096, True, False),
    "glm-4-long": (16384, False, False),
    "glm-5": (4096, True, False),
    "glm-5.1": (16384, True, True),
}

# 推理模型需要更多 token（reasoning tokens 计入 max_tokens）
REASONING_MODEL_PREFIXES = ("glm-5",)


def _is_reasoning_model(model: str) -> bool:
    """检测推理模型（reasoning tokens 消耗 max_tokens 预算）"""
    return any(model.startswith(p) for p in REASONING_MODEL_PREFIXES)


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
        self._client: Optional[httpx.AsyncClient] = None

        if not self.api_key:
            raise ValueError("GLM API Key 未配置")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            # 推理模型需要更长时间
            timeout = 600.0 if _is_reasoning_model(self.model) else 300.0
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

        return {
            "model": self.model,
            "messages": glm_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": stream,
        }

    async def ainvoke(self, messages: list) -> GLMMessage:
        """异步非流式调用"""
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
                return await self.ainvoke(messages)

        return GLMMessage(content=content, usage=usage)

    async def astream(self, messages: list) -> AsyncGenerator[str, None]:
        """异步流式调用，yield SSE 格式的 JSON 字符串"""
        client = await self._get_client()
        payload = self._build_payload(messages, stream=True)

        full_content = ""

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
                        full_content += chunk
                        yield json.dumps({
                            "type": "chunk",
                            "content": chunk,
                            "done": False,
                        }, ensure_ascii=False)
                except json.JSONDecodeError:
                    continue

        yield json.dumps({
            "type": "done",
            "content": full_content,
            "done": True,
        }, ensure_ascii=False)

    def invoke(self, messages: list) -> GLMMessage:
        """同步调用（阻塞，仅用于简单场景）"""
        import asyncio
        return asyncio.run(self.ainvoke(messages))
