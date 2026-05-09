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

# 模型配置: model_name -> (max_tokens_default, supports_tools)
MODEL_CONFIG = {
    "glm-4": (4096, False),
    "glm-4-plus": (4096, True),
    "glm-4-flash": (4096, True),
    "glm-4-long": (16384, False),
    "glm-5": (4096, True),
}


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
        config = MODEL_CONFIG.get(model, (4096, False))
        self.max_tokens = max_tokens or config[0]
        self.temperature = temperature
        self._client: Optional[httpx.AsyncClient] = None

        if not self.api_key:
            raise ValueError("GLM API Key 未配置")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=120.0)
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
