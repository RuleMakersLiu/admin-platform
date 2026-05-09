"""飞书机器人 API 适配器实现

使用飞书开放平台 API 与飞书交互。
支持文本、富文本、卡片消息、文件等。
"""
import base64
import hashlib
import hmac
import logging
import time
from typing import Any, Optional

import httpx

from app.messaging.adapter.base import MessageAdapter
from app.messaging.schemas import (
    ChannelType,
    ChannelConfig,
    UnifiedMessage,
    UnifiedAttachment,
    MessageType,
    MessageStatus,
    SendMessageRequest,
    SendMessageResponse,
    WebhookPayload,
)

logger = logging.getLogger(__name__)

# 飞书 API 基础 URL
FEISHU_API_BASE = "https://open.feishu.cn/open-apis"


class FeishuAdapter(MessageAdapter):
    """飞书机器人 API 适配器

    支持的功能：
    - 接收/发送文本消息
    - 接收/发送富文本消息
    - 接收/发送卡片消息
    - 文件上传
    - 交互式卡片
    """

    def __init__(self, config: ChannelConfig):
        super().__init__(config)
        self.app_id = config.extra.get("app_id", "")
        self.app_secret = config.extra.get("app_secret", "")
        self.encrypt_key = config.extra.get("encrypt_key", "")  # 用于消息加密
        self.verification_token = config.extra.get("verification_token", "")
        self.http_client: Optional[httpx.AsyncClient] = None
        self._tenant_access_token: Optional[str] = None
        self._token_expire_time: int = 0

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.FEISHU

    async def initialize(self) -> bool:
        """初始化飞书适配器

        获取 tenant_access_token。
        """
        if not self.app_id or not self.app_secret:
            logger.error("[Feishu] App ID 或 App Secret 未配置")
            return False

        self.http_client = httpx.AsyncClient(timeout=30.0)

        try:
            # 获取 tenant_access_token
            token = await self._get_tenant_access_token()
            if token:
                logger.info("[Feishu] Bot 初始化成功")
                self._is_initialized = True
                return True
            else:
                logger.error("[Feishu] 获取 access_token 失败")
                return False
        except Exception as e:
            logger.error(f"[Feishu] 初始化异常: {e}")
            return False

    async def shutdown(self) -> None:
        """关闭适配器"""
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None
        self._is_initialized = False
        self._tenant_access_token = None
        logger.info("[Feishu] 适配器已关闭")

    async def send_message(self, request: SendMessageRequest) -> SendMessageResponse:
        """发送消息到飞书"""
        if not self._is_initialized:
            return SendMessageResponse(success=False, error="适配器未初始化")

        try:
            # 确保 token 有效
            await self._ensure_token_valid()

            # 构建消息体
            receive_id = request.receiver_id or request.channel_id
            message_body = self._build_message_body(request)

            params = {
                "receive_id": receive_id,
                "msg_type": self._get_feishu_msg_type(request.message_type),
                "content": message_body,
            }

            result = await self._call_api("POST", "/im/v1/messages", params)

            if result and result.get("code") == 0:
                data = result.get("data", {})
                return SendMessageResponse(
                    success=True,
                    message_id=f"feishu_{data.get('message_id', '')}",
                    original_id=data.get("message_id"),
                )
            else:
                return SendMessageResponse(
                    success=False,
                    error=result.get("msg", "发送失败") if result else "未知错误"
                )
        except Exception as e:
            logger.error(f"[Feishu] 发送消息异常: {e}")
            return SendMessageResponse(success=False, error=str(e))

    async def parse_webhook(self, payload: WebhookPayload) -> Optional[UnifiedMessage]:
        """解析飞书 Webhook 回调"""
        try:
            data = payload.raw_data

            # 处理 URL 验证挑战
            if data.get("type") == "url_verification":
                logger.info("[Feishu] 收到 URL 验证挑战")
                return None

            # 处理事件回调
            if data.get("type") == "event_callback":
                event = data.get("event", {})
                return self._parse_event(event, data)

            # 处理卡片回调
            if data.get("type") == "card":
                return self._parse_card_callback(data)

            return None
        except Exception as e:
            logger.error(f"[Feishu] 解析 Webhook 异常: {e}")
            return None

    def verify_signature(self, payload: WebhookPayload) -> bool:
        """验证飞书 Webhook 签名

        飞书使用 HMAC-SHA256 签名验证请求
        """
        if not self.verification_token:
            return True

        timestamp = payload.metadata.get("timestamp", "") if payload.metadata else ""
        nonce = payload.metadata.get("nonce", "") if payload.metadata else ""
        signature = payload.signature

        if not timestamp or not signature:
            return False

        # 防止重放攻击（1小时内有效）
        try:
            request_time = int(timestamp)
            if abs(time.time() - request_time) > 3600:
                logger.warning("[Feishu] 请求时间戳过期")
                return False
        except ValueError:
            return False

        # 计算签名
        import json
        body = json.dumps(payload.raw_data, separators=(',', ':'), ensure_ascii=False)
        base_string = f"{timestamp}{nonce}{body}"
        computed_signature = hmac.new(
            self.verification_token.encode(),
            base_string.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, computed_signature)

    async def get_user_info(self, user_id: str) -> Optional[dict[str, Any]]:
        """获取飞书用户信息"""
        if not self._is_initialized:
            return None

        try:
            await self._ensure_token_valid()
            result = await self._call_api("GET", f"/contact/v3/users/{user_id}")

            if result and result.get("code") == 0:
                user = result.get("data", {}).get("user", {})
                return {
                    "user_id": user.get("user_id"),
                    "name": user.get("name"),
                    "en_name": user.get("en_name"),
                    "avatar": user.get("avatar", {}).get("avatar_origin"),
                    "email": user.get("email"),
                    "mobile": user.get("mobile"),
                    "department_ids": user.get("department_ids", []),
                    "position": user.get("position"),
                }
            return None
        except Exception as e:
            logger.error(f"[Feishu] 获取用户信息异常: {e}")
            return None

    async def get_channel_info(self, channel_id: str) -> Optional[dict[str, Any]]:
        """获取飞书群组信息"""
        if not self._is_initialized:
            return None

        try:
            await self._ensure_token_valid()
            result = await self._call_api("GET", f"/im/v1/chats/{channel_id}")

            if result and result.get("code") == 0:
                chat = result.get("data", {})
                return {
                    "id": chat.get("chat_id"),
                    "name": chat.get("name"),
                    "description": chat.get("description"),
                    "owner_id": chat.get("owner_id"),
                    "user_count": chat.get("user_count"),
                }
            return None
        except Exception as e:
            logger.error(f"[Feishu] 获取群组信息异常: {e}")
            return None

    # ==================== 私有方法 ====================

    async def _get_tenant_access_token(self) -> Optional[str]:
        """获取 tenant_access_token"""
        try:
            url = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"
            response = await self.http_client.post(url, json={
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            })
            result = response.json()

            if result.get("code") == 0:
                self._tenant_access_token = result.get("tenant_access_token")
                self._token_expire_time = int(time.time()) + result.get("expire", 7200) - 300
                return self._tenant_access_token
            else:
                logger.error(f"[Feishu] 获取 token 失败: {result.get('msg')}")
                return None
        except Exception as e:
            logger.error(f"[Feishu] 获取 token 异常: {e}")
            return None

    async def _ensure_token_valid(self) -> None:
        """确保 token 有效"""
        if time.time() >= self._token_expire_time:
            await self._get_tenant_access_token()

    async def _call_api(
        self, method: str, endpoint: str, data: Optional[dict] = None
    ) -> Optional[dict]:
        """调用飞书 API"""
        if not self.http_client or not self._tenant_access_token:
            return None

        url = f"{FEISHU_API_BASE}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self._tenant_access_token}",
            "Content-Type": "application/json",
        }

        try:
            if method == "GET":
                response = await self.http_client.get(url, headers=headers, params=data)
            elif method == "POST":
                response = await self.http_client.post(url, headers=headers, json=data)
            else:
                return None

            return response.json()
        except Exception as e:
            logger.error(f"[Feishu] API 调用异常 [{method} {endpoint}]: {e}")
            return None

    def _get_feishu_msg_type(self, message_type: MessageType) -> str:
        """转换为飞书消息类型"""
        mapping = {
            MessageType.TEXT: "text",
            MessageType.IMAGE: "image",
            MessageType.VIDEO: "media",
            MessageType.AUDIO: "media",
            MessageType.FILE: "file",
            MessageType.LOCATION: "location",
            MessageType.STICKER: "sticker",
            MessageType.INTERACTIVE: "interactive",
        }
        return mapping.get(message_type, "text")

    def _build_message_body(self, request: SendMessageRequest) -> dict:
        """构建飞书消息体"""
        import json

        if request.message_type == MessageType.TEXT:
            return {"text": request.content}

        elif request.message_type == MessageType.IMAGE:
            if request.attachments:
                return {"image_key": request.attachments[0].file_id}
            return {"text": request.content}

        elif request.message_type == MessageType.FILE:
            if request.attachments:
                return {
                    "file_key": request.attachments[0].file_id,
                    "file_name": request.attachments[0].file_name,
                }
            return {"text": request.content}

        elif request.message_type == MessageType.INTERACTIVE:
            # 飞书卡片消息
            card = request.metadata.get("card")
            if card:
                return card
            return {"text": request.content}

        else:
            return {"text": request.content}

    def _parse_event(self, event: dict, raw_data: dict) -> UnifiedMessage:
        """解析飞书事件"""
        event_type = event.get("type")

        if event_type == "message":
            return self._parse_message_event(event, raw_data)
        elif event_type in ["im.message.receive_v1"]:
            return self._parse_message_event_v1(event, raw_data)
        else:
            # 其他事件类型
            return UnifiedMessage(
                message_id=f"feishu_event_{event_type}_{event.get('event_id', '')}",
                original_id=event.get("event_id", ""),
                channel_type=ChannelType.FEISHU,
                channel_id=event.get("chat_id", ""),
                sender_id=event.get("sender", {}).get("sender_id", {}).get("open_id", ""),
                sender_name="",
                message_type=MessageType.SYSTEM,
                content=f"Event: {event_type}",
                raw_content=event,
                status=MessageStatus.DELIVERED,
                timestamp=event.get("created_at", 0) * 1000,
                metadata={"event_type": event_type},
            )

    def _parse_message_event(self, event: dict, raw_data: dict) -> UnifiedMessage:
        """解析飞书消息事件（旧版）"""
        message = event.get("message", {})
        sender = event.get("sender", {})

        message_type = self._map_message_type(message.get("msg_type", "text"))
        attachments = []

        # 解析消息内容
        content = message.get("content", "{}")
        if isinstance(content, str):
            import json
            try:
                content = json.loads(content)
            except:
                content = {"text": content}

        text_content = content.get("text", "")

        # 处理附件
        if message.get("msg_type") == "image":
            attachments.append(UnifiedAttachment(
                file_id=content.get("image_key"),
                file_type="image",
            ))
        elif message.get("msg_type") == "file":
            attachments.append(UnifiedAttachment(
                file_id=content.get("file_key"),
                file_name=content.get("file_name"),
                file_type="application/octet-stream",
            ))

        return UnifiedMessage(
            message_id=f"feishu_{message.get('message_id', '')}",
            original_id=message.get("message_id", ""),
            channel_type=ChannelType.FEISHU,
            channel_id=event.get("chat_id", ""),
            sender_id=sender.get("sender_id", {}).get("open_id", ""),
            sender_name=sender.get("sender_id", {}).get("user_id", ""),
            sender_type="app" if sender.get("sender_id", {}).get("union_id") else "user",
            message_type=message_type,
            content=text_content,
            raw_content=event,
            attachments=attachments,
            reply_to=message.get("parent_id"),
            status=MessageStatus.DELIVERED,
            timestamp=message.get("create_time", 0) * 1000,
            metadata={
                "msg_type": message.get("msg_type"),
                "tenant_key": raw_data.get("tenant_key"),
            }
        )

    def _parse_message_event_v1(self, event: dict, raw_data: dict) -> UnifiedMessage:
        """解析飞书消息事件（新版 v1）"""
        message = event.get("message", {})
        sender = event.get("sender", {})

        message_type = self._map_message_type(message.get("message_type", "text"))
        attachments = []

        # 解析消息内容
        content = message.get("content", "{}")
        if isinstance(content, str):
            import json
            try:
                content = json.loads(content)
            except:
                content = {"text": content}

        text_content = content.get("text", "")

        return UnifiedMessage(
            message_id=f"feishu_{message.get('message_id', '')}",
            original_id=message.get("message_id", ""),
            channel_type=ChannelType.FEISHU,
            channel_id=message.get("chat_id", ""),
            sender_id=sender.get("sender_id", {}).get("open_id", ""),
            sender_name="",
            sender_type="app" if sender.get("sender_type") == "app" else "user",
            message_type=message_type,
            content=text_content,
            raw_content=event,
            attachments=attachments,
            status=MessageStatus.DELIVERED,
            timestamp=int(message.get("create_time", 0) * 1000),
            metadata={
                "message_type": message.get("message_type"),
                "tenant_key": raw_data.get("tenant_key"),
            }
        )

    def _parse_card_callback(self, data: dict) -> UnifiedMessage:
        """解析飞书卡片回调"""
        action = data.get("action", {})
        user = data.get("context", {}).get("open_id", "")

        content = action.get("value", {})
        if isinstance(content, dict):
            content = str(content)

        return UnifiedMessage(
            message_id=f"feishu_card_{data.get('token', '')}",
            original_id=data.get("token", ""),
            channel_type=ChannelType.FEISHU,
            channel_id=data.get("context", {}).get("chat_id", ""),
            sender_id=user,
            sender_name="",
            sender_type="user",
            message_type=MessageType.INTERACTIVE,
            content=content,
            raw_content=data,
            status=MessageStatus.DELIVERED,
            timestamp=int(time.time() * 1000),
            metadata={
                "action": action.get("tag"),
                "open_message_id": data.get("context", {}).get("open_message_id"),
            }
        )

    def _map_message_type(self, feishu_type: str) -> MessageType:
        """映射飞书消息类型到统一类型"""
        mapping = {
            "text": MessageType.TEXT,
            "post": MessageType.TEXT,  # 富文本
            "image": MessageType.IMAGE,
            "media": MessageType.VIDEO,
            "file": MessageType.FILE,
            "audio": MessageType.AUDIO,
            "location": MessageType.LOCATION,
            "sticker": MessageType.STICKER,
            "interactive": MessageType.INTERACTIVE,
        }
        return mapping.get(feishu_type, MessageType.TEXT)
