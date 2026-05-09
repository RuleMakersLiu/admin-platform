"""多渠道消息模块测试"""
import pytest
from datetime import datetime

from app.messaging.schemas import (
    UnifiedMessage,
    UnifiedAttachment,
    ChannelType,
    MessageType,
    MessageStatus,
    SendMessageRequest,
    ChannelConfig,
)
from app.messaging.adapter.base import MessageAdapter, adapter_registry


class TestUnifiedMessage:
    """统一消息格式测试"""

    def test_create_text_message(self):
        """测试创建文本消息"""
        msg = UnifiedMessage(
            message_id="test_001",
            channel_type=ChannelType.TELEGRAM,
            channel_id="chat_123",
            sender_id="user_456",
            content="Hello, World!",
        )

        assert msg.message_id == "test_001"
        assert msg.channel_type == ChannelType.TELEGRAM
        assert msg.message_type == MessageType.TEXT
        assert msg.status == MessageStatus.PENDING
        assert msg.content == "Hello, World!"
        assert isinstance(msg.timestamp, int)

    def test_create_message_with_attachments(self):
        """测试创建带附件的消息"""
        attachment = UnifiedAttachment(
            file_id="file_001",
            file_name="image.png",
            file_type="image/png",
            file_size=1024,
            url="https://example.com/image.png",
        )

        msg = UnifiedMessage(
            message_id="test_002",
            channel_type=ChannelType.DISCORD,
            channel_id="channel_789",
            sender_id="user_123",
            message_type=MessageType.IMAGE,
            content="Check this out!",
            attachments=[attachment],
        )

        assert len(msg.attachments) == 1
        assert msg.attachments[0].file_name == "image.png"
        assert msg.message_type == MessageType.IMAGE

    def test_message_serialization(self):
        """测试消息序列化"""
        msg = UnifiedMessage(
            message_id="test_003",
            channel_type=ChannelType.SLACK,
            channel_id="C12345",
            sender_id="U12345",
            content="Test message",
            tenant_id=1,
        )

        # 使用 alias 序列化
        data = msg.model_dump(by_alias=True)
        assert data["messageId"] == "test_003"
        assert data["channelType"] == "slack"
        assert data["tenantId"] == 1


class TestSendMessageRequest:
    """发送消息请求测试"""

    def test_create_send_request(self):
        """测试创建发送请求"""
        request = SendMessageRequest(
            channel_type=ChannelType.TELEGRAM,
            channel_id="chat_123",
            content="Hello!",
        )

        assert request.channel_type == ChannelType.TELEGRAM
        assert request.message_type == MessageType.TEXT

    def test_send_request_with_reply(self):
        """测试带回复的发送请求"""
        request = SendMessageRequest(
            channel_type=ChannelType.DISCORD,
            channel_id="channel_456",
            content="Replying to message",
            reply_to="msg_789",
        )

        assert request.reply_to == "msg_789"


class TestAdapterRegistry:
    """适配器注册表测试"""

    def test_registry_singleton(self):
        """测试注册表单例"""
        registry1 = adapter_registry
        from app.messaging.adapter.base import AdapterRegistry
        registry2 = AdapterRegistry()

        assert registry1 is registry2

    def test_list_registered_empty(self):
        """测试空注册表"""
        # 注意：如果已有适配器注册，这个测试可能失败
        # 这里只是演示测试结构
        registered = adapter_registry.list_registered()
        assert isinstance(registered, list)


class TestChannelConfig:
    """渠道配置测试"""

    def test_create_config(self):
        """测试创建渠道配置"""
        config = ChannelConfig(
            channel_type=ChannelType.TELEGRAM,
            enabled=True,
            extra={
                "bot_token": "test_token",
            }
        )

        assert config.channel_type == ChannelType.TELEGRAM
        assert config.enabled is True
        assert config.extra["bot_token"] == "test_token"

    def test_disabled_config(self):
        """测试禁用的配置"""
        config = ChannelConfig(
            channel_type=ChannelType.SLACK,
            enabled=False,
        )

        assert config.enabled is False


class TestMessageType:
    """消息类型测试"""

    def test_message_types(self):
        """测试所有消息类型"""
        assert MessageType.TEXT.value == "text"
        assert MessageType.IMAGE.value == "image"
        assert MessageType.VIDEO.value == "video"
        assert MessageType.AUDIO.value == "audio"
        assert MessageType.FILE.value == "file"
        assert MessageType.LOCATION.value == "location"
        assert MessageType.CONTACT.value == "contact"
        assert MessageType.STICKER.value == "sticker"
        assert MessageType.SYSTEM.value == "system"
        assert MessageType.INTERACTIVE.value == "interactive"


class TestChannelType:
    """渠道类型测试"""

    def test_channel_types(self):
        """测试所有渠道类型"""
        assert ChannelType.TELEGRAM.value == "telegram"
        assert ChannelType.DISCORD.value == "discord"
        assert ChannelType.SLACK.value == "slack"
        assert ChannelType.FEISHU.value == "feishu"
        assert ChannelType.WEBSOCKET.value == "websocket"


# pytest markers
pytestmark = pytest.mark.asyncio
