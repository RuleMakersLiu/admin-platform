"""消息路由分发

负责将消息路由到正确的处理器或目标渠道。
支持：
- 基于渠道类型的路由
- 基于租户的路由
- 消息过滤和转换
- 广播和组播
"""
import asyncio
import logging
from typing import Any, Callable, Optional

from app.messaging.adapter.base import MessageAdapter, adapter_registry
from app.messaging.schemas import (
    ChannelType,
    ChannelConfig,
    UnifiedMessage,
    SendMessageRequest,
    SendMessageResponse,
    WebhookPayload,
)
from app.messaging.service.message_queue import MessageQueue

logger = logging.getLogger(__name__)


# 消息处理器类型
MessageHandler = Callable[[UnifiedMessage], Any]


class MessageRouter:
    """消息路由器

    核心功能：
    1. 管理各渠道适配器实例
    2. 路由消息到正确的处理器
    3. 处理 Webhook 回调
    4. 消息分发（广播、组播）
    """

    def __init__(self, message_queue: Optional[MessageQueue] = None):
        """初始化消息路由器

        Args:
            message_queue: 消息队列实例
        """
        self.message_queue = message_queue or MessageQueue()
        self._adapters: dict[ChannelType, MessageAdapter] = {}
        self._handlers: dict[str, list[MessageHandler]] = {}
        self._channel_handlers: dict[ChannelType, list[MessageHandler]] = {}
        self._running = False

    async def initialize(self) -> bool:
        """初始化路由器和消息队列"""
        # 连接消息队列
        if not await self.message_queue.connect():
            logger.error("[MessageRouter] 消息队列连接失败")
            return False

        logger.info("[MessageRouter] 初始化完成")
        return True

    async def shutdown(self) -> None:
        """关闭路由器"""
        self._running = False

        # 关闭所有适配器
        for adapter in self._adapters.values():
            await adapter.shutdown()
        self._adapters.clear()

        # 断开消息队列
        await self.message_queue.disconnect()

        logger.info("[MessageRouter] 已关闭")

    # ==================== 适配器管理 ====================

    def register_adapter(self, config: ChannelConfig) -> Optional[MessageAdapter]:
        """注册渠道适配器

        Args:
            config: 渠道配置

        Returns:
            创建的适配器实例，失败返回 None
        """
        channel_type = config.channel_type

        # 检查是否已注册
        if channel_type in self._adapters:
            logger.warning(f"[MessageRouter] 适配器已存在: {channel_type}")
            return self._adapters[channel_type]

        # 创建适配器
        adapter = adapter_registry.create(channel_type, config)
        if not adapter:
            logger.error(f"[MessageRouter] 未找到适配器类型: {channel_type}")
            return None

        self._adapters[channel_type] = adapter
        logger.info(f"[MessageRouter] 注册适配器: {channel_type}")
        return adapter

    async def initialize_adapter(self, channel_type: ChannelType) -> bool:
        """初始化指定渠道适配器"""
        adapter = self._adapters.get(channel_type)
        if not adapter:
            logger.error(f"[MessageRouter] 适配器未注册: {channel_type}")
            return False

        if adapter.is_initialized:
            return True

        return await adapter.initialize()

    async def initialize_all_adapters(self) -> dict[ChannelType, bool]:
        """初始化所有已注册的适配器"""
        results = {}
        for channel_type, adapter in self._adapters.items():
            results[channel_type] = await adapter.initialize()
        return results

    def get_adapter(self, channel_type: ChannelType) -> Optional[MessageAdapter]:
        """获取适配器实例"""
        return self._adapters.get(channel_type)

    # ==================== 处理器注册 ====================

    def on_message(self, handler_id: str) -> Callable:
        """注册全局消息处理器装饰器

        Args:
            handler_id: 处理器唯一标识

        Example:
            @router.on_message("logger")
            async def log_message(msg: UnifiedMessage):
                print(f"Received: {msg.content}")
        """
        def decorator(func: MessageHandler) -> MessageHandler:
            if handler_id not in self._handlers:
                self._handlers[handler_id] = []
            self._handlers[handler_id].append(func)
            logger.debug(f"[MessageRouter] 注册处理器: {handler_id}")
            return func
        return decorator

    def on_channel(self, channel_type: ChannelType) -> Callable:
        """注册渠道专用处理器装饰器

        Args:
            channel_type: 渠道类型

        Example:
            @router.on_channel(ChannelType.TELEGRAM)
            async def handle_telegram(msg: UnifiedMessage):
                # 处理 Telegram 消息
                pass
        """
        def decorator(func: MessageHandler) -> MessageHandler:
            if channel_type not in self._channel_handlers:
                self._channel_handlers[channel_type] = []
            self._channel_handlers[channel_type].append(func)
            logger.debug(f"[MessageRouter] 注册渠道处理器: {channel_type}")
            return func
        return decorator

    # ==================== 消息发送 ====================

    async def send_message(self, request: SendMessageRequest) -> SendMessageResponse:
        """发送消息到指定渠道

        Args:
            request: 发送消息请求

        Returns:
            发送结果
        """
        adapter = self._adapters.get(request.channel_type)
        if not adapter:
            return SendMessageResponse(
                success=False,
                error=f"未找到渠道适配器: {request.channel_type}"
            )

        if not adapter.is_initialized:
            return SendMessageResponse(
                success=False,
                error=f"适配器未初始化: {request.channel_type}"
            )

        return await adapter.send_message(request)

    async def broadcast(
        self,
        content: str,
        channels: Optional[list[ChannelType]] = None,
        exclude: Optional[list[ChannelType]] = None,
    ) -> dict[ChannelType, SendMessageResponse]:
        """广播消息到多个渠道

        Args:
            content: 消息内容
            channels: 指定渠道列表（None 表示所有已初始化的渠道）
            exclude: 排除的渠道列表

        Returns:
            各渠道的发送结果
        """
        # 确定目标渠道
        target_channels = channels or list(self._adapters.keys())
        if exclude:
            target_channels = [c for c in target_channels if c not in exclude]

        results = {}
        tasks = []

        for channel_type in target_channels:
            adapter = self._adapters.get(channel_type)
            if adapter and adapter.is_initialized:
                request = SendMessageRequest(
                    channel_type=channel_type,
                    channel_id="broadcast",  # 广播消息需要指定实际 channel_id
                    content=content,
                )
                tasks.append((channel_type, adapter.send_message(request)))

        # 并行发送
        for channel_type, task in tasks:
            try:
                results[channel_type] = await task
            except Exception as e:
                results[channel_type] = SendMessageResponse(
                    success=False,
                    error=str(e)
                )

        return results

    # ==================== Webhook 处理 ====================

    async def handle_webhook(
        self,
        channel_type: ChannelType,
        payload: WebhookPayload
    ) -> Optional[UnifiedMessage]:
        """处理 Webhook 回调

        Args:
            channel_type: 渠道类型
            payload: Webhook 数据

        Returns:
            解析后的统一消息
        """
        adapter = self._adapters.get(channel_type)
        if not adapter:
            logger.warning(f"[MessageRouter] 未注册适配器: {channel_type}")
            return None

        # 验证签名
        if not adapter.verify_signature(payload):
            logger.warning(f"[MessageRouter] Webhook 签名验证失败: {channel_type}")
            return None

        # 解析消息
        message = await adapter.parse_webhook(payload)
        if not message:
            return None

        # 发布到消息队列
        await self.message_queue.publish(message)

        # 触发处理器
        await self._dispatch_handlers(message)

        return message

    # ==================== 消息消费 ====================

    async def start_consuming(self, consumer_name: Optional[str] = None) -> None:
        """开始消费消息队列中的消息

        Args:
            consumer_name: 消费者名称
        """
        self._running = True
        await self.message_queue.consume(
            handler=self._handle_queued_message,
            consumer_name=consumer_name,
        )

    async def _handle_queued_message(self, message: UnifiedMessage) -> None:
        """处理队列中的消息"""
        await self._dispatch_handlers(message)

    async def _dispatch_handlers(self, message: UnifiedMessage) -> None:
        """分发消息到处理器"""
        tasks = []

        # 触发全局处理器
        for handler_list in self._handlers.values():
            for handler in handler_list:
                tasks.append(self._call_handler(handler, message))

        # 触发渠道专用处理器
        channel_handlers = self._channel_handlers.get(message.channel_type, [])
        for handler in channel_handlers:
            tasks.append(self._call_handler(handler, message))

        # 并行执行所有处理器
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _call_handler(
        self,
        handler: MessageHandler,
        message: UnifiedMessage
    ) -> None:
        """安全调用处理器"""
        try:
            result = handler(message)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            handler_name = getattr(handler, "__name__", str(handler))
            logger.error(f"[MessageRouter] 处理器异常 [{handler_name}]: {e}")

    # ==================== 路由规则 ====================

    async def route_to_handler(
        self,
        message: UnifiedMessage,
        target_handler: str
    ) -> bool:
        """将消息路由到指定处理器

        Args:
            message: 统一消息
            target_handler: 目标处理器 ID

        Returns:
            是否成功路由
        """
        handlers = self._handlers.get(target_handler, [])
        if not handlers:
            logger.warning(f"[MessageRouter] 未找到处理器: {target_handler}")
            return False

        for handler in handlers:
            await self._call_handler(handler, message)
        return True

    async def route_by_tenant(
        self,
        message: UnifiedMessage
    ) -> Optional[str]:
        """基于租户路由消息

        根据消息的 tenant_id 查找对应的处理器。

        Args:
            message: 统一消息

        Returns:
            路由到的处理器 ID，未找到返回 None
        """
        if not message.tenant_id:
            return None

        # 命名约定: tenant_{tenant_id}
        handler_id = f"tenant_{message.tenant_id}"
        if handler_id in self._handlers:
            return handler_id

        return None


# ==================== 全局路由器实例 ====================

_global_router: Optional[MessageRouter] = None


def get_message_router() -> MessageRouter:
    """获取全局消息路由器实例"""
    global _global_router
    if _global_router is None:
        _global_router = MessageRouter()
    return _global_router


async def init_message_router() -> MessageRouter:
    """初始化全局消息路由器"""
    router = get_message_router()
    await router.initialize()
    return router
