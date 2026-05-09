"""激活体验服务"""
import asyncio
import json
import logging
import time
from typing import AsyncGenerator, Dict, List, Optional
from datetime import datetime
import uuid

from app.ai.glm_provider import ChatGLM
from app.core.config import settings
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)


class ActivationSession:
    """激活会话"""
    def __init__(
        self,
        activation_id: str,
        user_id: int,
        tenant_id: int,
        user_name: Optional[str] = None,
    ):
        self.activation_id = activation_id
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.user_name = user_name or "新用户"
        self.status = "ready"
        self.message_count = 0
        self.started_at = int(time.time() * 1000)
        self.last_activity = self.started_at
        self.messages: List[Dict] = []
    
    def to_dict(self) -> dict:
        return {
            "activationId": self.activation_id,
            "userId": self.user_id,
            "tenantId": self.tenant_id,
            "userName": self.user_name,
            "status": self.status,
            "messageCount": self.message_count,
            "startedAt": self.started_at,
            "lastActivity": self.last_activity,
        }


class ActivationService:
    """激活体验服务"""
    
    # 缓存键前缀
    CACHE_PREFIX = "activation:"
    SESSION_TTL = 1800  # 30分钟
    
    # 演示模板
    DEMO_TEMPLATES = [
        {
            "id": "task-create",
            "title": "创建任务",
            "description": "帮我创建一个新的开发任务",
            "prompt": "帮我创建一个任务：实现用户登录功能",
            "category": "任务管理",
            "icon": "📋",
        },
        {
            "id": "bug-report",
            "title": "报告Bug",
            "description": "报告一个系统Bug",
            "prompt": "发现一个Bug：登录页面验证码不显示",
            "category": "Bug管理",
            "icon": "🐛",
        },
        {
            "id": "project-overview",
            "title": "项目概览",
            "description": "查看当前项目状态",
            "prompt": "介绍一下当前项目的整体情况",
            "category": "项目管理",
            "icon": "📊",
        },
        {
            "id": "ai-assistant",
            "title": "AI助手",
            "description": "与AI助手对话，体验智能功能",
            "prompt": "你好，我想了解一下这个系统有什么功能？",
            "category": "AI对话",
            "icon": "🤖",
        },
        {
            "id": "report-generate",
            "title": "生成报告",
            "description": "生成项目进度报告",
            "prompt": "帮我生成本周的项目进度报告",
            "category": "报告生成",
            "icon": "📄",
        },
        {
            "id": "code-review",
            "title": "代码审查",
            "description": "AI辅助代码审查",
            "prompt": "帮我审查这段Python代码的质量",
            "category": "开发辅助",
            "icon": "💻",
        },
    ]
    
    def __init__(self):
        self._client: Optional[ChatGLM] = None
        self._sessions: Dict[str, ActivationSession] = {}
        self._warmup_done = False
    
    @property
    def client(self) -> ChatGLM:
        """获取GLM客户端（懒加载）"""
        if self._client is None:
            self._client = ChatGLM(
                model="glm-5",
                api_key=settings.zai_api_key,
                max_tokens=2048,
                temperature=0.7,
            )
        return self._client
    
    async def warmup(self) -> bool:
        """预热AI连接（减少首字延迟）"""
        if self._warmup_done:
            return True
        
        try:
            # 发送一个简单请求来预热连接
            start_time = time.time()
            _ = await self.client.ainvoke([
                {"role": "user", "content": "ping"}
            ])
            elapsed = time.time() - start_time
            logger.info(f"✅ AI连接预热完成，耗时: {elapsed:.2f}秒")
            self._warmup_done = True
            return True
        except Exception as e:
            logger.warning(f"⚠️ AI连接预热失败: {e}")
            return False
    
    def _get_system_prompt(self, user_name: str) -> str:
        """获取系统提示词"""
        return f"""你是{user_name}的AI助手，负责帮助用户快速了解和使用这个管理系统。

你的职责：
1. 热情欢迎新用户，引导他们完成首次体验
2. 简洁清晰地回答用户问题
3. 主动推荐系统功能和使用场景
4. 保持友好、专业的对话风格

回复要求：
- 简洁明了，避免冗长
- 使用Markdown格式提高可读性
- 可以使用表情符号增加亲和力
- 主动询问用户需求，引导对话

当前系统功能：
- 📋 任务管理：创建、分配、跟踪任务
- 🐛 Bug管理：报告、跟踪、解决Bug
- 📊 项目管理：查看项目状态和进度
- 🤖 AI助手：智能对话和代码审查
- 📄 报告生成：自动生成项目报告"""

    async def start_activation(
        self,
        user_id: int,
        tenant_id: int,
        user_name: Optional[str] = None,
    ) -> ActivationSession:
        """开始激活流程"""
        # 生成激活ID
        activation_id = f"act_{uuid.uuid4().hex[:12]}"
        
        # 创建会话
        session = ActivationSession(
            activation_id=activation_id,
            user_id=user_id,
            tenant_id=tenant_id,
            user_name=user_name,
        )
        
        # 缓存会话
        self._sessions[activation_id] = session
        
        # 并行预热AI连接
        asyncio.create_task(self.warmup())
        
        logger.info(f"🚀 激活流程启动: {activation_id}, 用户: {user_id}")
        return session
    
    def get_welcome_message(self, user_name: str) -> str:
        """获取欢迎消息"""
        return f"""👋 你好，{user_name}！

欢迎来到智能管理系统！我是你的AI助手，可以帮助你：

📋 **任务管理** - 创建、分配和跟踪任务  
🐛 **Bug管理** - 报告和追踪问题  
📊 **项目概览** - 查看项目进度和状态  
🤖 **智能对话** - 代码审查、文档生成等  

💡 **快速开始**：
- 点击下方模板快速体验
- 或直接输入你的问题

有什么我可以帮助你的吗？"""

    def get_suggested_prompts(self) -> List[str]:
        """获取建议的提示词"""
        return [
            "介绍一下系统的主要功能",
            "帮我创建第一个任务",
            "如何查看项目进度？",
            "AI能帮我做什么？",
        ]
    
    async def get_templates(self) -> tuple[List[dict], List[str]]:
        """获取演示模板"""
        templates = self.DEMO_TEMPLATES
        categories = list(set(t["category"] for t in templates))
        return templates, categories
    
    async def chat_stream(
        self,
        activation_id: str,
        message: str,
    ) -> AsyncGenerator[str, None]:
        """流式对话（SSE）"""
        session = self._sessions.get(activation_id)
        if not session:
            yield f"data: {json.dumps({'error': '会话不存在'})}\n\n"
            return
        
        # 更新会话状态
        session.status = "chatting"
        session.message_count += 1
        session.last_activity = int(time.time() * 1000)
        
        # 构建消息历史
        messages = [
            {"role": "system", "content": self._get_system_prompt(session.user_name)},
        ]
        
        # 添加历史消息（最近5轮）
        for msg in session.messages[-10:]:
            messages.append(msg)
        
        # 添加当前消息
        messages.append({"role": "user", "content": message})
        session.messages.append({"role": "user", "content": message})
        
        try:
            # 调用GLM-5（流式）
            start_time = time.time()
            full_content = ""
            
            # 使用真正的流式API
            async for chunk in self.client.astream(messages):
                if chunk.startswith("data: "):
                    try:
                        data = json.loads(chunk[6:].strip())
                        if data.get("type") == "chunk":
                            content = data.get("content", "")
                            full_content += content
                            yield chunk  # 直接转发SSE数据
                        elif data.get("type") == "done":
                            elapsed = time.time() - start_time
                            logger.info(f"⏱️ AI响应耗时: {elapsed:.2f}秒")
                            
                            # 保存AI回复
                            session.messages.append({"role": "assistant", "content": full_content})
                            
                            # 发送完成标记（带耗时信息）
                            done_data = json.dumps({
                                "type": "done",
                                "elapsed": elapsed,
                                "done": True,
                            }, ensure_ascii=False)
                            yield f"data: {done_data}\n\n"
                            break
                    except json.JSONDecodeError:
                        continue
            
        except Exception as e:
            logger.error(f"❌ AI对话失败: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        finally:
            session.status = "ready"
    
    async def complete_activation(
        self,
        activation_id: str,
        rating: Optional[int] = None,
        feedback: Optional[str] = None,
    ) -> dict:
        """完成激活流程"""
        session = self._sessions.get(activation_id)
        if not session:
            return {"status": "error", "message": "会话不存在"}
        
        session.status = "completed"
        
        # 记录激活数据
        activation_data = {
            "activationId": activation_id,
            "userId": session.user_id,
            "tenantId": session.tenant_id,
            "messageCount": session.message_count,
            "duration": int(time.time() * 1000) - session.started_at,
            "rating": rating,
            "feedback": feedback,
            "completedAt": int(time.time() * 1000),
        }
        
        logger.info(f"✅ 激活完成: {activation_id}, 消息数: {session.message_count}")
        
        # 清理会话
        del self._sessions[activation_id]
        
        return {
            "status": "completed",
            "message": "激活完成，欢迎使用系统！",
            "nextSteps": [
                "查看项目概览",
                "创建第一个任务",
                "探索更多AI功能",
            ],
        }
    
    def get_session(self, activation_id: str) -> Optional[ActivationSession]:
        """获取会话"""
        return self._sessions.get(activation_id)


# 全局服务实例
activation_service = ActivationService()
