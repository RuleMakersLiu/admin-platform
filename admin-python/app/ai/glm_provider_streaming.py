"""GLM LLM Provider（支持 GLM-4 和 GLM-5）- 增强版，支持流式响应"""
from typing import Optional, AsyncGenerator
import httpx
import json
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class GLMChatMessage:
    """GLM 聊天消息"""
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content
    
    def to_dict(self):
        return {"role": self.role, "content": self.content}


class GLMChatCompletion:
    """GLM 聊天补全（支持流式和非流式）"""
    
    API_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
    
    def __init__(
        self,
        model: str = "glm-4",
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ):
        self.model = model
        self.api_key = api_key or settings.zai_api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        if not self.api_key:
            raise ValueError("GLM API Key 未配置")
    
    async def ainvoke(self, messages: list) -> "GLMMessage":
        """异步调用 GLM API（非流式）"""
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
        
        # 提取响应
        content = result["choices"][0]["message"]["content"]
        return GLMMessage(content)
    
    async def astream(
        self, 
        messages: list,
        chunk_size: int = 20,
    ) -> AsyncGenerator[str, None]:
        """
        异步流式调用 GLM API
        
        Args:
            messages: 消息列表
            chunk_size: 每次发送的字符数（用于模拟流式效果）
        
        Yields:
            str: SSE格式的数据流
        """
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
            "stream": True  # 启用流式
        }
        
        full_content = ""
        
        try:
            # 使用流式请求
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.API_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if not line or line == "data: [DONE]":
                            continue
                        
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])  # 去掉 "data: " 前缀
                                
                                if "choices" in data and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    content = delta.get("content", "")
                                    
                                    if content:
                                        full_content += content
                                        
                                        # 发送SSE格式数据
                                        sse_data = json.dumps({
                                            "type": "chunk",
                                            "content": content,
                                            "done": False,
                                        }, ensure_ascii=False)
                                        yield f"data: {sse_data}\n\n"
                                        
                            except json.JSONDecodeError:
                                continue
            
            # 发送完成标记
            done_data = json.dumps({
                "type": "done",
                "content": full_content,
                "done": True,
            }, ensure_ascii=False)
            yield f"data: {done_data}\n\n"
            
        except Exception as e:
            logger.error(f"❌ 流式调用失败: {e}")
            error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {error_data}\n\n"
    
    def invoke(self, messages: list) -> "GLMMessage":
        """同步调用 GLM API"""
        import asyncio
        return asyncio.run(self.ainvoke(messages))


class GLMMessage:
    """GLM 响应消息"""
    def __init__(self, content: str):
        self._content = content
    
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
    
    @property
    def client(self) -> GLMChatCompletion:
        """获取GLM客户端"""
        if self._client is None:
            self._client = GLMChatCompletion(
                model=self.model,
                api_key=self.api_key,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
        return self._client
    
    async def ainvoke(self, messages: list) -> GLMMessage:
        """异步调用"""
        return await self.client.ainvoke(messages)
    
    async def astream(self, messages: list) -> AsyncGenerator[str, None]:
        """异步流式调用"""
        async for chunk in self.client.astream(messages):
            yield chunk
    
    def invoke(self, messages: list) -> GLMMessage:
        """同步调用"""
        import asyncio
        return asyncio.run(self.ainvoke(messages))
