"""Discord Bot API 适配器实现

使用 Discord HTTP API 与 Discord 交互。
支持文本、嵌入消息、文件附件、按钮交互等。
"""
import logging
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

# Discord API 基础 URL
DISCORD_API_BASE = "https://discord.com/api/v10"


class DiscordAdapter(MessageAdapter):
    """Discord Bot API 适配器

    支持的功能：
    - 接收/发送文本消息
    - 接收/发送嵌入消息（Embed）
    - 接收/发送文件附件
    - 按钮、选择菜单等交互组件
    - Slash 命令
    """

    def __init__(self, config: ChannelConfig):
        super().__init__(config)
        self.bot_token = config.extra.get("bot_token", "")
        self.application_id = config.extra.get("application_id", "")
        self.http_client: Optional[httpx.AsyncClient] = None

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.DISCORD

    async def initialize(self) -> bool:
        """初始化 Discord 适配器

        验证 Bot Token 是否有效。
        """
        if not self.bot_token:
            logger.error("[Discord] Bot Token 未配置")
            return False

        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bot {self.bot_token}",
                "Content-Type": "application/json",
            }
        )

        try:
            # 验证 Bot Token
            result = await self._call_api("GET", "/users/@me")
            if result and result.get("id"):
                logger.info(f"[Discord] Bot 初始化成功: @{result.get('username', 'unknown')}")
                self._is_initialized = True
                return True
            else:
                logger.error(f"[Discord] Bot Token 验证失败: {result}")
                return False
        except Exception as e:
            logger.error(f"[Discord] 初始化异常: {e}")
            return False

    async def shutdown(self) -> None:
        """关闭适配器"""
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None
        self._is_initialized = False
        logger.info("[Discord] 适配器已关闭")

    async def send_message(self, request: SendMessageRequest) -> SendMessageResponse:
        """发送消息到 Discord"""
        if not self._is_initialized:
            return SendMessageResponse(success=False, error="适配器未初始化")

        try:
            channel_id = request.channel_id

            # 构建消息体
            message_data = self._build_message_data(request)

            result = await self._call_api("POST", f"/channels/{channel_id}/messages", message_data)

            if result and result.get("id"):
                return SendMessageResponse(
                    success=True,
                    message_id=f"discord_{result.get('id')}",
                    original_id=result.get("id"),
                )
            else:
                return SendMessageResponse(
                    success=False,
                    error=result.get("message", "发送失败") if result else "未知错误"
                )
        except Exception as e:
            logger.error(f"[Discord] 发送消息异常: {e}")
            return SendMessageResponse(success=False, error=str(e))

    async def parse_webhook(self, payload: WebhookPayload) -> Optional[UnifiedMessage]:
        """解析 Discord Webhook 回调（来自 Discord Gateway 或 HTTP Webhook）"""
        try:
            data = payload.raw_data

            # Discord 消息通过 Gateway 或 Interaction 发送
            # 这里处理 Interaction 类型的回调
            if data.get("type") == 2:  # APPLICATION_COMMAND
                return self._parse_interaction(data)
            elif data.get("type") == 3:  # MESSAGE_COMPONENT
                return self._parse_interaction(data)
            elif data.get("t") == "MESSAGE_CREATE":
                # Gateway 事件
                return self._parse_gateway_message(data.get("d", {}))

            # 直接消息格式
            if data.get("id") and data.get("content") is not None:
                return self._parse_message(data)

            return None
        except Exception as e:
            logger.error(f"[Discord] 解析 Webhook 异常: {e}")
            return None

    def verify_signature(self, payload: WebhookPayload) -> bool:
        """验证 Discord Webhook 签名

        Discord 使用 Ed25519 签名验证 Interaction 回调
        """
        # 需要使用 nacl 库进行 Ed25519 验证
        # 简化实现：检查必要的头信息
        public_key = self.config.extra.get("public_key")
        if not public_key:
            return True

        # 实际签名验证需要 nacl 库
        # 这里简化处理，实际生产环境需要完整实现
        signature = payload.signature
        timestamp = payload.metadata.get("timestamp", "") if payload.metadata else ""

        if not signature or not timestamp:
            return False

        # TODO: 实现完整的 Ed25519 签名验证
        return True

    async def get_user_info(self, user_id: str) -> Optional[dict[str, Any]]:
        """获取 Discord 用户信息"""
        if not self._is_initialized:
            return None

        try:
            result = await self._call_api("GET", f"/users/{user_id}")
            if result and result.get("id"):
                return {
                    "user_id": result.get("id"),
                    "username": result.get("username"),
                    "discriminator": result.get("discriminator"),
                    "avatar": self._get_avatar_url(result),
                    "banner": result.get("banner"),
                    "public_flags": result.get("public_flags"),
                }
            return None
        except Exception as e:
            logger.error(f"[Discord] 获取用户信息异常: {e}")
            return None

    async def get_channel_info(self, channel_id: str) -> Optional[dict[str, Any]]:
        """获取 Discord 频道信息"""
        if not self._is_initialized:
            return None

        try:
            result = await self._call_api("GET", f"/channels/{channel_id}")
            if result and result.get("id"):
                return {
                    "id": result.get("id"),
                    "type": self._get_channel_type_name(result.get("type", 0)),
                    "name": result.get("name"),
                    "topic": result.get("topic"),
                    "guild_id": result.get("guild_id"),
                    "position": result.get("position"),
                }
            return None
        except Exception as e:
            logger.error(f"[Discord] 获取频道信息异常: {e}")
            return None

    # ==================== 私有方法 ====================

    async def _call_api(
        self, method: str, endpoint: str, data: Optional[dict] = None
    ) -> Optional[dict]:
        """调用 Discord REST API"""
        if not self.http_client:
            return None

        url = f"{DISCORD_API_BASE}{endpoint}"
        try:
            if method == "GET":
                response = await self.http_client.get(url)
            elif method == "POST":
                response = await self.http_client.post(url, json=data)
            elif method == "PATCH":
                response = await self.http_client.patch(url, json=data)
            elif method == "DELETE":
                response = await self.http_client.delete(url)
            else:
                return None

            if response.status_code == 204:
                return {"success": True}

            return response.json()
        except Exception as e:
            logger.error(f"[Discord] API 调用异常 [{method} {endpoint}]: {e}")
            return None

    def _build_message_data(self, request: SendMessageRequest) -> dict:
        """构建 Discord 消息数据"""
        data = {
            "content": request.content,
        }

        # 处理附件
        if request.attachments:
            data["attachments"] = [
                {
                    "id": i,
                    "description": att.file_name or f"attachment_{i}",
                    "filename": att.file_name or f"file_{i}",
                }
                for i, att in enumerate(request.attachments)
                if att.url
            ]

        # 处理回复
        if request.reply_to:
            data["message_reference"] = {
                "message_id": request.reply_to.replace("discord_", ""),
            }

        # 处理嵌入消息
        embed = request.metadata.get("embed")
        if embed:
            data["embeds"] = [embed]

        # 处理组件（按钮等）
        components = request.metadata.get("components")
        if components:
            data["components"] = components

        return data

    def _parse_message(self, data: dict) -> UnifiedMessage:
        """解析 Discord 消息格式"""
        author = data.get("author", {})
        attachments = []

        for att in data.get("attachments", []):
            attachments.append(UnifiedAttachment(
                file_id=att.get("id"),
                file_name=att.get("filename"),
                file_type=att.get("content_type", "application/octet-stream"),
                file_size=att.get("size"),
                url=att.get("url"),
            ))

        # 判断消息类型
        message_type = MessageType.TEXT
        if attachments:
            if any(att.file_type.startswith("image/") for att in attachments):
                message_type = MessageType.IMAGE
            else:
                message_type = MessageType.FILE

        return UnifiedMessage(
            message_id=f"discord_{data.get('id', '')}",
            original_id=data.get("id", ""),
            channel_type=ChannelType.DISCORD,
            channel_id=data.get("channel_id", ""),
            sender_id=str(author.get("id", "")),
            sender_name=author.get("username", ""),
            sender_avatar=self._get_avatar_url(author),
            sender_type="bot" if author.get("bot") else "user",
            message_type=message_type,
            content=data.get("content", ""),
            raw_content=data,
            attachments=attachments,
            reply_to=str(data.get("message_reference", {}).get("message_id", "")) if data.get("message_reference") else None,
            status=MessageStatus.DELIVERED,
            timestamp=self._snowflake_to_timestamp(data.get("id", 0)),
            metadata={
                "guild_id": data.get("guild_id"),
                "mentions": [m.get("id") for m in data.get("mentions", [])],
                "reactions": data.get("reactions", []),
            }
        )

    def _parse_interaction(self, data: dict) -> UnifiedMessage:
        """解析 Discord Interaction"""
        interaction_data = data.get("data", {})
        user = interaction_data.get("user", {}) or data.get("member", {}).get("user", {})

        # 获取消息内容
        content = ""
        if interaction_data.get("options"):
            options = interaction_data.get("options", [])
            content = " ".join([o.get("value", "") for o in options if o.get("value")])
        elif interaction_data.get("custom_id"):
            content = interaction_data.get("custom_id")
        elif interaction_data.get("value"):
            content = interaction_data.get("value")

        return UnifiedMessage(
            message_id=f"discord_interaction_{data.get('id', '')}",
            original_id=data.get("id", ""),
            channel_type=ChannelType.DISCORD,
            channel_id=data.get("channel_id", ""),
            sender_id=str(user.get("id", "")),
            sender_name=user.get("username", ""),
            sender_avatar=self._get_avatar_url(user),
            sender_type="user",
            message_type=MessageType.INTERACTIVE,
            content=content,
            raw_content=data,
            status=MessageStatus.DELIVERED,
            timestamp=int(data.get("id", 0) >> 22) + 1420070400000 if data.get("id") else 0,
            metadata={
                "interaction_type": data.get("type"),
                "command_name": interaction_data.get("name"),
                "custom_id": interaction_data.get("custom_id"),
                "component_type": interaction_data.get("component_type"),
            }
        )

    def _parse_gateway_message(self, data: dict) -> UnifiedMessage:
        """解析 Discord Gateway 消息事件"""
        return self._parse_message(data)

    def _get_avatar_url(self, user: dict) -> Optional[str]:
        """获取用户头像 URL"""
        user_id = user.get("id")
        avatar_hash = user.get("avatar")
        if user_id and avatar_hash:
            return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png"
        return None

    def _snowflake_to_timestamp(self, snowflake: int) -> int:
        """将 Discord Snowflake ID 转换为时间戳（毫秒）"""
        # Discord epoch: 2015-01-01 00:00:00
        return (int(snowflake) >> 22) + 1420070400000

    def _get_channel_type_name(self, type_id: int) -> str:
        """获取频道类型名称"""
        types = {
            0: "text",
            1: "dm",
            2: "voice",
            3: "group_dm",
            4: "category",
            5: "announcement",
            10: "announcement_thread",
            11: "public_thread",
            12: "private_thread",
            13: "stage",
            14: "directory",
            15: "forum",
        }
        return types.get(type_id, "unknown")
