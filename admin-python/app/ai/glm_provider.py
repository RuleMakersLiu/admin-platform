"""GLM LLM Provider（支持 GLM-4 和 GLM-5）"""
from typing import Optional
import httpx
import json

from app.core.config import settings


class GLMChatMessage:
    """GLM 聊天消息"""
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content
    
    def to_dict(self):
        return {"role": self.role, "content": self.content}


class GLMChatCompletion:
    """GLM 聊天补全"""
    
    API_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
    
    def __init__(
        self,
        model: str = "glm-4",
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ):
        self.model = model
        self.api_key = api_key or settings.glm_api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        if not self.api_key:
            raise ValueError("GLM API Key 未配置")
    
    async def ainvoke(self, messages: list) -> "GLMMessage":
        """异步调用 GLM API"""
        # 转换消息格式
        glm_messages = [
            GLMChatMessage(msg.get("role", "user"), msg.get("content", "")).to_dict()
            for msg in messages
        ]
        
        # 准备请求
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": glm_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False
        }
        
        # 发送请求（增加超时时间到120秒）
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.API_URL}/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
        
        # 提取响应（content 可能是字符串或 content blocks 数组）
        content = result["choices"][0]["message"]["content"]
        if isinstance(content, list):
            # GLM 多模态格式: [{"type": "text", "text": "..."}]
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(item.get("text", str(item)))
                else:
                    parts.append(str(item))
            content = "\n".join(parts)
        elif not isinstance(content, str):
            content = str(content)
        return GLMMessage(content)
    
    def invoke(self, messages: list) -> "GLMMessage":
        """同步调用 GLM API"""
        import asyncio
        return asyncio.run(self.ainvoke(messages))


class GLMMessage:
    """GLM 响应消息"""
    def __init__(self, content: str):
        self.content = content
    
    @property
    def content(self) -> str:
        return self._content
    
    @content.setter
    def content(self, value: str):
        self._content = value


class ChatGLM:
    """GLM 聊天类（兼容 LangChain 接口）"""
    
    def __init__(
        self,
        model: str = "glm-5",
        max_tokens: int = 4096,
        api_key: Optional[str] = None,
        temperature: float = 0.7,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.temperature = temperature
        self._client = None
    
    async def ainvoke(self, messages: list) -> GLMMessage:
        """异步调用"""
        if self._client is None:
            self._client = GLMChatCompletion(
                model=self.model,
                api_key=self.api_key,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
        return await self._client.ainvoke(messages)
    
    def invoke(self, messages: list) -> GLMMessage:
        """同步调用"""
        import asyncio
        return asyncio.run(self.ainvoke(messages))
