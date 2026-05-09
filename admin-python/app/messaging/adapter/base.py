"""消息适配器基类

定义了所有渠道适配器必须实现的接口。
适配器负责：
1. 将平台特定格式的消息转换为统一格式（接收）
2. 将统一格式转换为平台特定格式并发送（发送）
3. 处理 Webhook 回调
"""
from abc import ABC, abstractmethod
from typing import Any, Optional

from app.messaging.schemas import (
    ChannelType,
    ChannelConfig,
    UnifiedMessage,
    SendMessageRequest,
    SendMessageResponse,
    WebhookPayload,
)


class MessageAdapter(ABC):
    """消息适配器抽象基类

    所有渠道适配器都必须继承此类并实现所有抽象方法。
    适配器是渠道无关的消息处理层，负责统一消息格式的转换。
    """

    def __init__(self, config: ChannelConfig):
        """初始化适配器

        Args:
            config: 渠道配置信息
        """
        self.config = config
        self._is_initialized = False

    @property
    @abstractmethod
    def channel_type(self) -> ChannelType:
        """返回适配器支持的渠道类型"""
        pass

    @abstractmethod
    async def initialize(self) -> bool:
        """初始化适配器

        用于建立与渠道平台的连接、验证凭证等。
        返回初始化是否成功。
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """关闭适配器

        用于清理资源、断开连接等。
        """
        pass

    @abstractmethod
    async def send_message(self, request: SendMessageRequest) -> SendMessageResponse:
        """发送消息

        将统一格式的消息请求转换为平台特定格式并发送。

        Args:
            request: 统一格式的发送消息请求

        Returns:
            发送结果响应
        """
        pass

    @abstractmethod
    async def parse_webhook(self, payload: WebhookPayload) -> Optional[UnifiedMessage]:
        """解析 Webhook 回调

        将平台推送的 Webhook 数据解析为统一消息格式。

        Args:
            payload: Webhook 回调数据

        Returns:
            解析后的统一消息，如果无法解析则返回 None
        """
        pass

    @abstractmethod
    def verify_signature(self, payload: WebhookPayload) -> bool:
        """验证 Webhook 签名

        验证回调请求是否来自正规渠道（防止伪造请求）。

        Args:
            payload: Webhook 回调数据

        Returns:
            签名是否有效
        """
        pass

    @abstractmethod
    async def get_user_info(self, user_id: str) -> Optional[dict[str, Any]]:
        """获取用户信息

        从渠道获取指定用户的基本信息。

        Args:
            user_id: 平台用户ID

        Returns:
            用户信息字典，获取失败返回 None
        """
        pass

    @abstractmethod
    async def get_channel_info(self, channel_id: str) -> Optional[dict[str, Any]]:
        """获取渠道信息

        获取群组、频道等渠道的详细信息。

        Args:
            channel_id: 渠道ID

        Returns:
            渠道信息字典，获取失败返回 None
        """
        pass

    @property
    def is_initialized(self) -> bool:
        """适配器是否已初始化"""
        return self._is_initialized


class AdapterRegistry:
    """适配器注册表

    用于管理和查找已注册的渠道适配器。
    采用单例模式，全局共享同一个注册表。
    """

    _instance: Optional["AdapterRegistry"] = None
    _adapters: dict[ChannelType, type[MessageAdapter]]

    def __new__(cls) -> "AdapterRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._adapters = {}
        return cls._instance

    def register(self, adapter_class: type[MessageAdapter]) -> None:
        """注册适配器类

        Args:
            adapter_class: 适配器类（非实例）
        """
        # 创建临时实例获取 channel_type
        temp_config = ChannelConfig(channel_type=ChannelType.WEBSOCKET)
        temp_instance = adapter_class(temp_config)
        channel_type = temp_instance.channel_type
        self._adapters[channel_type] = adapter_class

    def get(self, channel_type: ChannelType) -> Optional[type[MessageAdapter]]:
        """获取适配器类

        Args:
            channel_type: 渠道类型

        Returns:
            适配器类，未注册返回 None
        """
        return self._adapters.get(channel_type)

    def create(
        self, channel_type: ChannelType, config: ChannelConfig
    ) -> Optional[MessageAdapter]:
        """创建适配器实例

        Args:
            channel_type: 渠道类型
            config: 渠道配置

        Returns:
            适配器实例，未注册返回 None
        """
        adapter_class = self._adapters.get(channel_type)
        if adapter_class:
            return adapter_class(config)
        return None

    def list_registered(self) -> list[ChannelType]:
        """列出所有已注册的渠道类型"""
        return list(self._adapters.keys())


# 全局注册表实例
adapter_registry = AdapterRegistry()
