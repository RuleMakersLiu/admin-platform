"""消息模块 - 简化版"""
from app.messaging.schemas import (
    AdapterConfig,
    ChannelConfig,
    ChannelInfo,
    ChannelType,
    Message,
    MessageType,
    Response,
    SendMessageRequest,
    SendMessageResponse,
    UnifiedMessage,
)

__all__ = [
    "Response",
    "Message",
    "ChannelInfo",
    "SendMessageRequest",
    "SendMessageResponse",
    "AdapterConfig",
    "ChannelType",
    "MessageType",
    "UnifiedMessage",
    "ChannelConfig",
]
