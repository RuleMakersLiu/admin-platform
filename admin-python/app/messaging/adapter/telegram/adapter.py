"""Telegram Bot API 适配器实现

使用 python-telegram-bot 库或直接 HTTP API 与 Telegram 交互。
支持文本、图片、文件、位置等消息类型的收发。
"""
import hashlib
import hmac
import logging
from typing import Any, Optional

import httpx

from app.messaging.adapter.base import MessageAdapter
from app.messaging.schemas import (
    ChannelType,
    ChannelConfig,
    UnifiedMessage,
    UnifiedAttachment,
    UnifiedLocation,
    UnifiedContact,
    MessageType,
    MessageStatus,
    SendMessageRequest,
    SendMessageResponse,
    WebhookPayload,
)

logger = logging.getLogger(__name__)

# Telegram API 基础 URL
TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramAdapter(MessageAdapter):
    """Telegram Bot API 适配器

    支持的功能：
    - 接收/发送文本消息
    - 接收/发送图片、文件、视频
    - 接收/发送位置信息
    - 接收/发送联系人
    - 内联键盘交互
    """

    def __init__(self, config: ChannelConfig):
        super().__init__(config)
        self.bot_token = config.extra.get("bot_token", "")
        self.http_client: Optional[httpx.AsyncClient] = None

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.TELEGRAM

    async def initialize(self) -> bool:
        """初始化 Telegram 适配器

        验证 Bot Token 是否有效。
        """
        if not self.bot_token:
            logger.error("[Telegram] Bot Token 未配置")
            return False

        self.http_client = httpx.AsyncClient(timeout=30.0)

        try:
            # 验证 Bot Token
            result = await self._call_api("getMe")
            if result and result.get("ok"):
                bot_info = result.get("result", {})
                logger.info(f"[Telegram] Bot 初始化成功: @{bot_info.get('username', 'unknown')}")
                self._is_initialized = True
                return True
            else:
                logger.error(f"[Telegram] Bot Token 验证失败: {result}")
                return False
        except Exception as e:
            logger.error(f"[Telegram] 初始化异常: {e}")
            return False

    async def shutdown(self) -> None:
        """关闭适配器"""
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None
        self._is_initialized = False
        logger.info("[Telegram] 适配器已关闭")

    async def send_message(self, request: SendMessageRequest) -> SendMessageResponse:
        """发送消息到 Telegram"""
        if not self._is_initialized:
            return SendMessageResponse(success=False, error="适配器未初始化")

        try:
            # 确定 chat_id
            chat_id = request.receiver_id or request.channel_id

            if request.message_type == MessageType.TEXT:
                result = await self._send_text_message(chat_id, request.content, request.reply_to)
            elif request.message_type == MessageType.IMAGE:
                result = await self._send_photo(chat_id, request)
            elif request.message_type == MessageType.LOCATION:
                result = await self._send_location(chat_id, request)
            else:
                # 默认作为文本发送
                result = await self._send_text_message(chat_id, request.content, request.reply_to)

            if result and result.get("ok"):
                msg = result.get("result", {})
                return SendMessageResponse(
                    success=True,
                    message_id=f"telegram_{msg.get('message_id', '')}",
                    original_id=str(msg.get("message_id", "")),
                )
            else:
                return SendMessageResponse(
                    success=False,
                    error=result.get("description", "发送失败") if result else "未知错误"
                )
        except Exception as e:
            logger.error(f"[Telegram] 发送消息异常: {e}")
            return SendMessageResponse(success=False, error=str(e))

    async def parse_webhook(self, payload: WebhookPayload) -> Optional[UnifiedMessage]:
        """解析 Telegram Webhook 回调"""
        try:
            data = payload.raw_data

            # 提取消息对象
            message = data.get("message") or data.get("edited_message") or data.get("channel_post")
            if not message:
                return None

            # 解析消息类型和内容
            message_type, content, attachments = self._parse_message_content(message)

            # 构建统一消息
            from_user = message.get("from", {})
            chat = message.get("chat", {})

            return UnifiedMessage(
                message_id=f"telegram_{message.get('message_id', '')}",
                original_id=str(message.get("message_id", "")),
                channel_type=ChannelType.TELEGRAM,
                channel_id=str(chat.get("id", "")),
                sender_id=str(from_user.get("id", "")),
                sender_name=self._get_full_name(from_user),
                sender_avatar=None,  # Telegram 不在消息中提供头像
                sender_type="bot" if from_user.get("is_bot") else "user",
                message_type=message_type,
                content=content,
                raw_content=message,
                attachments=attachments,
                location=self._parse_location(message),
                reply_to=str(message.get("reply_to_message", {}).get("message_id", "")) if message.get("reply_to_message") else None,
                status=MessageStatus.DELIVERED,
                timestamp=message.get("date", 0) * 1000,
                metadata={
                    "chat_type": chat.get("type"),
                    "username": from_user.get("username"),
                    "language_code": from_user.get("language_code"),
                }
            )
        except Exception as e:
            logger.error(f"[Telegram] 解析 Webhook 异常: {e}")
            return None

    def verify_signature(self, payload: WebhookPayload) -> bool:
        """验证 Telegram Webhook 签名

        Telegram 使用 X-Telegram-Bot-Api-Secret-Token 头验证
        """
        # Telegram Webhook 签名验证需要在配置中设置 secret_token
        expected_token = self.config.extra.get("secret_token")
        if not expected_token:
            # 未配置验证 token，跳过验证
            return True

        # 从 metadata 获取实际 token（需要在 Webhook 请求头中提取）
        actual_token = payload.metadata.get("secret_token") if payload.metadata else None
        return expected_token == actual_token

    async def get_user_info(self, user_id: str) -> Optional[dict[str, Any]]:
        """获取 Telegram 用户信息"""
        try:
            # 获取用户头像
            photos = await self._call_api("getUserProfilePhotos", {"user_id": user_id})
            avatar_url = None
            if photos and photos.get("ok"):
                photos_data = photos.get("result", {}).get("photos", [])
                if photos_data:
                    # 获取第一张照片的文件路径
                    file_id = photos_data[0][0].get("file_id")
                    if file_id:
                        avatar_url = await self._get_file_url(file_id)

            return {
                "user_id": user_id,
                "avatar_url": avatar_url,
            }
        except Exception as e:
            logger.error(f"[Telegram] 获取用户信息异常: {e}")
            return None

    async def get_channel_info(self, channel_id: str) -> Optional[dict[str, Any]]:
        """获取 Telegram 聊天/频道信息"""
        try:
            result = await self._call_api("getChat", {"chat_id": channel_id})
            if result and result.get("ok"):
                chat = result.get("result", {})
                return {
                    "id": str(chat.get("id")),
                    "type": chat.get("type"),
                    "title": chat.get("title"),
                    "username": chat.get("username"),
                    "description": chat.get("description"),
                    "member_count": chat.get("member_count"),
                }
            return None
        except Exception as e:
            logger.error(f"[Telegram] 获取频道信息异常: {e}")
            return None

    # ==================== 私有方法 ====================

    async def _call_api(self, method: str, params: Optional[dict] = None) -> Optional[dict]:
        """调用 Telegram Bot API"""
        if not self.http_client:
            return None

        url = TELEGRAM_API_BASE.format(token=self.bot_token, method=method)
        try:
            response = await self.http_client.post(url, json=params or {})
            return response.json()
        except Exception as e:
            logger.error(f"[Telegram] API 调用异常 [{method}]: {e}")
            return None

    async def _send_text_message(
        self, chat_id: str, text: str, reply_to: Optional[str] = None
    ) -> Optional[dict]:
        """发送文本消息"""
        params = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if reply_to:
            params["reply_to_message_id"] = reply_to
        return await self._call_api("sendMessage", params)

    async def _send_photo(self, chat_id: str, request: SendMessageRequest) -> Optional[dict]:
        """发送图片"""
        if not request.attachments:
            return await self._send_text_message(chat_id, request.content, request.reply_to)

        attachment = request.attachments[0]
        params = {
            "chat_id": chat_id,
            "photo": attachment.url or attachment.file_id,
            "caption": request.content,
            "parse_mode": "HTML",
        }
        if request.reply_to:
            params["reply_to_message_id"] = request.reply_to
        return await self._call_api("sendPhoto", params)

    async def _send_location(self, chat_id: str, request: SendMessageRequest) -> Optional[dict]:
        """发送位置"""
        # 位置信息应该从 metadata 中获取
        loc_data = request.metadata.get("location", {})
        if not loc_data:
            return await self._send_text_message(chat_id, request.content, request.reply_to)

        params = {
            "chat_id": chat_id,
            "latitude": loc_data.get("latitude"),
            "longitude": loc_data.get("longitude"),
        }
        return await self._call_api("sendLocation", params)

    def _parse_message_content(self, message: dict) -> tuple[MessageType, str, list]:
        """解析消息内容"""
        attachments = []

        # 检查文本消息
        if message.get("text"):
            return MessageType.TEXT, message["text"], attachments

        # 检查图片
        if message.get("photo"):
            photos = message["photo"]
            # 取最大尺寸的图片
            largest = max(photos, key=lambda x: x.get("file_size", 0))
            attachments.append(UnifiedAttachment(
                file_id=largest.get("file_id"),
                file_type="image/jpeg",
                file_size=largest.get("file_size"),
            ))
            caption = message.get("caption", "")
            return MessageType.IMAGE, caption, attachments

        # 检查视频
        if message.get("video"):
            video = message["video"]
            attachments.append(UnifiedAttachment(
                file_id=video.get("file_id"),
                file_name=video.get("file_name"),
                file_type=video.get("mime_type", "video/mp4"),
                file_size=video.get("file_size"),
            ))
            return MessageType.VIDEO, message.get("caption", ""), attachments

        # 检查音频
        if message.get("audio"):
            audio = message["audio"]
            attachments.append(UnifiedAttachment(
                file_id=audio.get("file_id"),
                file_name=audio.get("file_name"),
                file_type=audio.get("mime_type", "audio/mpeg"),
                file_size=audio.get("file_size"),
            ))
            return MessageType.AUDIO, message.get("caption", ""), attachments

        # 检查文件
        if message.get("document"):
            doc = message["document"]
            attachments.append(UnifiedAttachment(
                file_id=doc.get("file_id"),
                file_name=doc.get("file_name"),
                file_type=doc.get("mime_type", "application/octet-stream"),
                file_size=doc.get("file_size"),
            ))
            return MessageType.FILE, message.get("caption", ""), attachments

        # 检查贴纸
        if message.get("sticker"):
            sticker = message["sticker"]
            attachments.append(UnifiedAttachment(
                file_id=sticker.get("file_id"),
                file_type="image/webp",
            ))
            return MessageType.STICKER, sticker.get("emoji", ""), attachments

        # 检查联系人
        if message.get("contact"):
            contact = message["contact"]
            return MessageType.CONTACT, f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip(), attachments

        # 检查位置
        if message.get("location"):
            return MessageType.LOCATION, "Shared location", attachments

        # 默认
        return MessageType.TEXT, "", attachments

    def _parse_location(self, message: dict) -> Optional[UnifiedLocation]:
        """解析位置信息"""
        loc = message.get("location")
        if not loc:
            return None
        return UnifiedLocation(
            latitude=loc.get("latitude", 0),
            longitude=loc.get("longitude", 0),
        )

    def _get_full_name(self, user: dict) -> str:
        """获取用户全名"""
        parts = [user.get("first_name", ""), user.get("last_name", "")]
        return " ".join(filter(None, parts))

    async def _get_file_url(self, file_id: str) -> Optional[str]:
        """获取文件下载 URL"""
        result = await self._call_api("getFile", {"file_id": file_id})
        if result and result.get("ok"):
            file_path = result.get("result", {}).get("file_path")
            if file_path:
                return f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
        return None
