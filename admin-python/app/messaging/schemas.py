"""消息模块数据模式"""
import time
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
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
    LOCATION = "location"
    CONTACT = "contact"
    STICKER = "sticker"
    INTERACTIVE = "interactive"
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


class UnifiedLocation(BaseModel):
    """统一位置格式"""
    latitude: float
    longitude: float
    accuracy: Optional[float] = None


class UnifiedContact(BaseModel):
    """统一联系人格式"""
    phone_number: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    user_id: Optional[str] = None


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
    # 未指定类型时默认文本——绝大多数主动发送的消息都是文本
    message_type: MessageType = MessageType.TEXT
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
    """统一消息格式。

    序列化支持 camelCase 别名（model_dump(by_alias=True) → messageId/channelType…），
    构造仍用 snake_case 字段名（populate_by_name）。
    """
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    message_id: str
    channel_type: ChannelType
    channel_id: str
    sender_id: str
    content: str
    # 未显式传入时默认取当前 unix 时间——消息总应带时间戳
    timestamp: int = Field(default_factory=lambda: int(time.time()))
    original_id: Optional[str] = None
    sender_name: Optional[str] = None
    sender_avatar: Optional[str] = None
    sender_type: Optional[str] = None
    # 未指定类型时默认文本（带附件的消息应显式传 IMAGE/FILE 等）
    message_type: Optional[MessageType] = MessageType.TEXT
    raw_content: Optional[Dict[str, Any]] = None
    attachments: Optional[List[UnifiedAttachment]] = None
    location: Optional[UnifiedLocation] = None
    contact: Optional[UnifiedContact] = None
    reply_to: Optional[str] = None
    # 新建消息默认待发送
    status: Optional[MessageStatus] = MessageStatus.PENDING
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
