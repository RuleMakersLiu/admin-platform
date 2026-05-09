"""消息模块数据模式"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from enum import Enum


class ChannelType(str, Enum):
    """消息渠道类型"""
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    FEISHU = "feishu"
    WEBSOCKET = "websocket"


class MessageType(str, Enum):
    """消息类型"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"
    SYSTEM = "system"


class MessageStatus(str, Enum):
    """消息状态"""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class UnifiedAttachment(BaseModel):
    """统一附件格式"""
    file_id: Optional[str] = None
    file_name: Optional[str] = None
    file_type: str
    file_size: Optional[int] = None
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None


class Response(BaseModel):
    """通用响应模型"""
    success: bool
    message: Optional[str] = None
    data: Optional[Any] = None


class Message(BaseModel):
    """消息模型"""
    id: Optional[str] = None
    channel: str
    content: str
    sender: Optional[str] = None
    timestamp: Optional[int] = None


class ChannelInfo(BaseModel):
    """频道信息"""
    channel_id: str
    channel_type: str
    name: Optional[str] = None


class SendMessageRequest(BaseModel):
    """发送消息请求"""
    channel_type: ChannelType
    channel_id: str
    content: str
    recipient: Optional[str] = None
    message_type: Optional[MessageType] = None
    attachments: Optional[List[UnifiedAttachment]] = None
    metadata: Optional[Dict[str, Any]] = None
    reply_to: Optional[str] = None
    sender_id: Optional[str] = None


class SendMessageResponse(BaseModel):
    """发送消息响应"""
    success: bool
    message_id: Optional[str] = None
    original_id: Optional[str] = None
    error: Optional[str] = None


class AdapterConfig(BaseModel):
    """适配器配置"""
    adapter_type: str
    enabled: bool = True
    config: Dict[str, Any] = {}


class UnifiedMessage(BaseModel):
    """统一消息格式"""
    message_id: str
    channel_type: ChannelType
    channel_id: str
    sender_id: str
    content: str
    timestamp: int
    original_id: Optional[str] = None
    sender_name: Optional[str] = None
    sender_avatar: Optional[str] = None
    sender_type: Optional[str] = None
    message_type: Optional[MessageType] = None
    raw_content: Optional[Dict[str, Any]] = None
    attachments: Optional[List[UnifiedAttachment]] = None
    reply_to: Optional[str] = None
    status: Optional[MessageStatus] = None
    metadata: Optional[Dict[str, Any]] = None
    tenant_id: Optional[int] = None


class ChannelConfig(BaseModel):
    """渠道配置"""
    channel_type: ChannelType
    enabled: bool = True
    extra: Dict[str, Any] = {}


class WebhookPayload(BaseModel):
    """Webhook回调数据"""
    channel_type: ChannelType
    raw_data: Dict[str, Any]
    signature: Optional[str] = None
    timestamp: int
