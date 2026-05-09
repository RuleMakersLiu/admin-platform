"""Slack Bot API 适配器实现

使用 Slack Web API 与 Slack 交互。
支持文本、富文本块、文件上传、交互式组件等。
"""
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

# Slack API 基础 URL
SLACK_API_BASE = "https://slack.com/api"


class SlackAdapter(MessageAdapter):
    """Slack Bot API 适配器

    支持的功能：
    - 接收/发送文本消息
    - 接收/发送 Block Kit 富消息
    - 文件上传
    - 交互式组件（按钮、选择器等）
    - Slash 命令
    - Event API 回调
    """

    def __init__(self, config: ChannelConfig):
        super().__init__(config)
        self.bot_token = config.extra.get("bot_token", "")  # xoxb-xxx
        self.app_token = config.extra.get("app_token", "")  # xapp-xxx (可选)
        self.signing_secret = config.extra.get("signing_secret", "")
        self.http_client: Optional[httpx.AsyncClient] = None

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.SLACK

    async def initialize(self) -> bool:
        """初始化 Slack 适配器

        验证 Bot Token 是否有效。
        """
        if not self.bot_token:
            logger.error("[Slack] Bot Token 未配置")
            return False

        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self.bot_token}",
                "Content-Type": "application/json",
            }
        )

        try:
            # 验证 Bot Token
            result = await self._call_api("auth.test")
            if result and result.get("ok"):
                logger.info(f"[Slack] Bot 初始化成功: @{result.get('user', 'unknown')}")
                self._is_initialized = True
                return True
            else:
                logger.error(f"[Slack] Bot Token 验证失败: {result.get('error', 'unknown')}")
                return False
        except Exception as e:
            logger.error(f"[Slack] 初始化异常: {e}")
            return False

    async def shutdown(self) -> None:
        """关闭适配器"""
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None
        self._is_initialized = False
        logger.info("[Slack] 适配器已关闭")

    async def send_message(self, request: SendMessageRequest) -> SendMessageResponse:
        """发送消息到 Slack"""
        if not self._is_initialized:
            return SendMessageResponse(success=False, error="适配器未初始化")

        try:
            channel = request.channel_id

            # 构建消息参数
            params = self._build_message_params(request)

            # 检查是否有文件附件
            if request.attachments and request.attachments[0].file_id:
                result = await self._upload_and_share(channel, request)
            else:
                result = await self._call_api("chat.postMessage", params)

            if result and result.get("ok"):
                return SendMessageResponse(
                    success=True,
                    message_id=f"slack_{result.get('ts', '')}",
                    original_id=result.get("ts"),
                    timestamp=int(float(result.get("ts", "0")) * 1000),
                )
            else:
                return SendMessageResponse(
                    success=False,
                    error=result.get("error", "发送失败") if result else "未知错误"
                )
        except Exception as e:
            logger.error(f"[Slack] 发送消息异常: {e}")
            return SendMessageResponse(success=False, error=str(e))

    async def parse_webhook(self, payload: WebhookPayload) -> Optional[UnifiedMessage]:
        """解析 Slack Webhook 回调（来自 Events API 或 Interactive Components）"""
        try:
            data = payload.raw_data

            # 处理 URL 验证挑战
            if data.get("type") == "url_verification":
                logger.info("[Slack] 收到 URL 验证挑战")
                return None

            # 处理 Event API 回调
            if data.get("type") == "event_callback":
                event = data.get("event", {})
                return self._parse_event(event)

            # 处理交互组件回调
            if payload.metadata and payload.metadata.get("payload"):
                interaction_payload = payload.metadata["payload"]
                if isinstance(interaction_payload, str):
                    import json
                    interaction_payload = json.loads(interaction_payload)
                return self._parse_interaction(interaction_payload)

            # 处理 Slash 命令
            if data.get("command"):
                return self._parse_slash_command(data)

            return None
        except Exception as e:
            logger.error(f"[Slack] 解析 Webhook 异常: {e}")
            return None

    def verify_signature(self, payload: WebhookPayload) -> bool:
        """验证 Slack Webhook 签名

        Slack 使用 HMAC-SHA256 签名验证请求
        """
        if not self.signing_secret:
            return True

        signature = payload.signature
        timestamp = payload.metadata.get("timestamp", "") if payload.metadata else ""
        body = payload.metadata.get("raw_body", "") if payload.metadata else ""

        if not signature or not timestamp:
            return False

        # 防止重放攻击（5分钟内有效）
        try:
            request_time = int(timestamp)
            if abs(time.time() - request_time) > 300:
                logger.warning("[Slack] 请求时间戳过期")
                return False
        except ValueError:
            return False

        # 计算签名
        base_string = f"v0:{timestamp}:{body}"
        computed_signature = "v0=" + hmac.new(
            self.signing_secret.encode(),
            base_string.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, computed_signature)

    async def get_user_info(self, user_id: str) -> Optional[dict[str, Any]]:
        """获取 Slack 用户信息"""
        if not self._is_initialized:
            return None

        try:
            result = await self._call_api("users.info", {"user": user_id})
            if result and result.get("ok"):
                user = result.get("user", {})
                profile = user.get("profile", {})
                return {
                    "user_id": user.get("id"),
                    "name": user.get("name"),
                    "real_name": profile.get("real_name"),
                    "display_name": profile.get("display_name"),
                    "email": profile.get("email"),
                    "avatar": profile.get("image_192") or profile.get("image_72"),
                    "title": profile.get("title"),
                    "phone": profile.get("phone"),
                }
            return None
        except Exception as e:
            logger.error(f"[Slack] 获取用户信息异常: {e}")
            return None

    async def get_channel_info(self, channel_id: str) -> Optional[dict[str, Any]]:
        """获取 Slack 频道信息"""
        if not self._is_initialized:
            return None

        try:
            result = await self._call_api("conversations.info", {"channel": channel_id})
            if result and result.get("ok"):
                channel = result.get("channel", {})
                return {
                    "id": channel.get("id"),
                    "name": channel.get("name"),
                    "type": self._get_channel_type(channel),
                    "topic": channel.get("topic", {}).get("value"),
                    "purpose": channel.get("purpose", {}).get("value"),
                    "num_members": channel.get("num_members"),
                    "is_private": channel.get("is_private", False),
                }
            return None
        except Exception as e:
            logger.error(f"[Slack] 获取频道信息异常: {e}")
            return None

    # ==================== 私有方法 ====================

    async def _call_api(self, method: str, params: Optional[dict] = None) -> Optional[dict]:
        """调用 Slack Web API"""
        if not self.http_client:
            return None

        url = f"{SLACK_API_BASE}/{method}"
        try:
            # Slack API 使用 form-encoded 或 JSON
            response = await self.http_client.post(url, json=params or {})
            return response.json()
        except Exception as e:
            logger.error(f"[Slack] API 调用异常 [{method}]: {e}")
            return None

    async def _upload_and_share(
        self, channel: str, request: SendMessageRequest
    ) -> Optional[dict]:
        """上传文件并分享到频道"""
        # 注意：实际文件上传需要使用 files.post 或 files.upload
        # 这里简化处理，假设附件已有 URL
        if not request.attachments:
            return None

        attachment = request.attachments[0]
        if attachment.url:
            # 如果是图片，使用图片块显示
            blocks = [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": request.content},
                },
                {
                    "type": "image",
                    "image_url": attachment.url,
                    "alt_text": attachment.file_name or "image",
                }
            ]
            return await self._call_api("chat.postMessage", {
                "channel": channel,
                "blocks": blocks,
            })

        # 其他情况作为普通消息发送
        return await self._call_api("chat.postMessage", {
            "channel": channel,
            "text": request.content,
        })

    def _build_message_params(self, request: SendMessageRequest) -> dict:
        """构建 Slack 消息参数"""
        params = {
            "channel": request.channel_id,
            "text": request.content,  # fallback text
        }

        # 处理回复
        if request.reply_to:
            params["thread_ts"] = request.reply_to.replace("slack_", "")

        # 处理 Block Kit
        blocks = request.metadata.get("blocks")
        if blocks:
            params["blocks"] = blocks

        # 处理附件（Slack 附件格式）
        attachments = request.metadata.get("attachments")
        if attachments:
            params["attachments"] = attachments

        # 处理 unfurl 设置
        if request.metadata.get("unfurl_links") is not None:
            params["unfurl_links"] = request.metadata["unfurl_links"]

        return params

    def _parse_event(self, event: dict) -> UnifiedMessage:
        """解析 Slack Event API 事件"""
        event_type = event.get("type")

        if event_type == "message":
            return self._parse_message_event(event)
        elif event_type == "app_mention":
            return self._parse_mention_event(event)
        else:
            # 其他事件类型
            return UnifiedMessage(
                message_id=f"slack_event_{event_type}_{event.get('event_ts', '')}",
                original_id=event.get("event_ts", ""),
                channel_type=ChannelType.SLACK,
                channel_id=event.get("channel", ""),
                sender_id=event.get("user", ""),
                sender_name="",
                message_type=MessageType.SYSTEM,
                content=f"Event: {event_type}",
                raw_content=event,
                status=MessageStatus.DELIVERED,
                timestamp=int(float(event.get("event_ts", "0")) * 1000),
                metadata={"event_type": event_type},
            )

    def _parse_message_event(self, event: dict) -> UnifiedMessage:
        """解析 Slack 消息事件"""
        # 过滤子类型消息
        subtype = event.get("subtype")
        if subtype in ["message_changed", "message_deleted", "bot_message"]:
            # 这些是特殊消息，可以单独处理或忽略
            pass

        # 判断消息类型
        message_type = MessageType.TEXT
        attachments = []

        if event.get("files"):
            for file in event["files"]:
                attachments.append(UnifiedAttachment(
                    file_id=file.get("id"),
                    file_name=file.get("name"),
                    file_type=file.get("mimetype", "application/octet-stream"),
                    file_size=file.get("size"),
                    url=file.get("url_private"),
                    thumbnail_url=file.get("thumb_360"),
                ))
            if any(f.get("mimetype", "").startswith("image/") for f in event.get("files", [])):
                message_type = MessageType.IMAGE
            else:
                message_type = MessageType.FILE

        return UnifiedMessage(
            message_id=f"slack_{event.get('ts', '')}",
            original_id=event.get("ts", ""),
            channel_type=ChannelType.SLACK,
            channel_id=event.get("channel", ""),
            sender_id=event.get("user", ""),
            sender_name="",
            sender_type="bot" if event.get("bot_id") else "user",
            message_type=message_type,
            content=event.get("text", ""),
            raw_content=event,
            attachments=attachments,
            reply_to=event.get("thread_ts"),
            status=MessageStatus.DELIVERED,
            timestamp=int(float(event.get("ts", "0")) * 1000),
            metadata={
                "edited": event.get("edited") is not None,
                "subtype": subtype,
            }
        )

    def _parse_mention_event(self, event: dict) -> UnifiedMessage:
        """解析 Slack @提及 事件"""
        return UnifiedMessage(
            message_id=f"slack_{event.get('ts', '')}",
            original_id=event.get("ts", ""),
            channel_type=ChannelType.SLACK,
            channel_id=event.get("channel", ""),
            sender_id=event.get("user", ""),
            sender_name="",
            message_type=MessageType.TEXT,
            content=event.get("text", ""),
            raw_content=event,
            status=MessageStatus.DELIVERED,
            timestamp=int(float(event.get("ts", "0")) * 1000),
            metadata={"is_mention": True},
        )

    def _parse_interaction(self, payload: dict) -> UnifiedMessage:
        """解析 Slack 交互组件回调"""
        interaction_type = payload.get("type")
        user = payload.get("user", {})
        channel = payload.get("channel", {})

        content = ""
        if interaction_type == "block_actions":
            actions = payload.get("actions", [])
            content = ",".join([a.get("action_id", "") or a.get("value", "") for a in actions])
        elif interaction_type == "view_submission":
            content = "view_submission"
        elif interaction_type == "shortcut":
            content = payload.get("callback_id", "")

        return UnifiedMessage(
            message_id=f"slack_interaction_{payload.get('trigger_id', '')}",
            original_id=payload.get("trigger_id", ""),
            channel_type=ChannelType.SLACK,
            channel_id=channel.get("id", ""),
            sender_id=user.get("id", ""),
            sender_name=user.get("name", ""),
            sender_type="user",
            message_type=MessageType.INTERACTIVE,
            content=content,
            raw_content=payload,
            status=MessageStatus.DELIVERED,
            timestamp=int(time.time() * 1000),
            metadata={
                "interaction_type": interaction_type,
                "callback_id": payload.get("callback_id"),
                "trigger_id": payload.get("trigger_id"),
            }
        )

    def _parse_slash_command(self, data: dict) -> UnifiedMessage:
        """解析 Slack Slash 命令"""
        return UnifiedMessage(
            message_id=f"slack_slash_{data.get('trigger_id', '')}",
            original_id=data.get("trigger_id", ""),
            channel_type=ChannelType.SLACK,
            channel_id=data.get("channel_id", ""),
            sender_id=data.get("user_id", ""),
            sender_name=data.get("user_name", ""),
            sender_type="user",
            message_type=MessageType.TEXT,
            content=data.get("text", ""),
            raw_content=data,
            status=MessageStatus.DELIVERED,
            timestamp=int(time.time() * 1000),
            metadata={
                "command": data.get("command"),
                "response_url": data.get("response_url"),
            }
        )

    def _get_channel_type(self, channel: dict) -> str:
        """获取频道类型"""
        if channel.get("is_im"):
            return "direct_message"
        elif channel.get("is_mpim"):
            return "multi_party_dm"
        elif channel.get("is_private"):
            return "private_channel"
        elif channel.get("is_group"):
            return "private_group"
        else:
            return "public_channel"
