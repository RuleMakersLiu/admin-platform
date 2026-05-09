"""消息队列管理

使用 Redis Stream 实现消息队列，支持：
- 消息发布/消费
- 消费者组
- 消息确认（ACK）
- 死信队列
- 消息重试
"""
import asyncio
import json
import logging
import time
from typing import Any, Callable, Optional

import redis.asyncio as redis

from app.core.config import settings
from app.messaging.schemas import UnifiedMessage, ChannelType

logger = logging.getLogger(__name__)


class MessageQueue:
    """Redis Stream 消息队列

    使用 Redis Stream 实现可靠的消息队列，支持多消费者组。

    队列命名规范：
    - 主队列: messaging:inbox
    - 死信队列: messaging:dead_letter
    - 渠道专用队列: messaging:inbox:{channel_type}
    """

    # 队列键名
    INBOX_STREAM = "messaging:inbox"
    DEAD_LETTER_STREAM = "messaging:dead_letter"
    CONSUMER_GROUP = "messaging_workers"

    def __init__(self, redis_url: Optional[str] = None):
        """初始化消息队列

        Args:
            redis_url: Redis 连接 URL，默认使用配置中的 redis_url
        """
        self.redis_url = redis_url or settings.redis_url
        self.redis: Optional[redis.Redis] = None
        self._consumer_task: Optional[asyncio.Task] = None
        self._running = False

    async def connect(self) -> bool:
        """连接 Redis 并初始化消费者组"""
        try:
            self.redis = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )

            # 测试连接
            await self.redis.ping()

            # 确保主队列存在并创建消费者组
            try:
                await self.redis.xgroup_create(
                    self.INBOX_STREAM,
                    self.CONSUMER_GROUP,
                    id="0",
                    mkstream=True
                )
                logger.info(f"[MessageQueue] 创建消费者组: {self.CONSUMER_GROUP}")
            except redis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise
                logger.info(f"[MessageQueue] 消费者组已存在: {self.CONSUMER_GROUP}")

            # 创建死信队列
            try:
                await self.redis.xgroup_create(
                    self.DEAD_LETTER_STREAM,
                    f"{self.CONSUMER_GROUP}_dlq",
                    id="0",
                    mkstream=True
                )
            except redis.ResponseError:
                pass

            logger.info("[MessageQueue] 连接成功")
            return True
        except Exception as e:
            logger.error(f"[MessageQueue] 连接失败: {e}")
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        self._running = False
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        if self.redis:
            await self.redis.close()
            self.redis = None
        logger.info("[MessageQueue] 已断开连接")

    async def publish(
        self,
        message: UnifiedMessage,
        channel: Optional[str] = None
    ) -> str:
        """发布消息到队列

        Args:
            message: 统一格式消息
            channel: 可选的渠道专用队列名

        Returns:
            消息 ID
        """
        if not self.redis:
            raise RuntimeError("Redis 未连接")

        stream_key = channel or self.INBOX_STREAM

        # 序列化消息
        message_data = {
            "message_id": message.message_id,
            "original_id": message.original_id or "",
            "channel_type": message.channel_type.value,
            "channel_id": message.channel_id,
            "sender_id": message.sender_id,
            "sender_name": message.sender_name or "",
            "message_type": message.message_type.value,
            "content": message.content,
            "status": message.status.value,
            "timestamp": str(message.timestamp),
            "tenant_id": str(message.tenant_id) if message.tenant_id else "",
            "raw_content": json.dumps(message.raw_content) if message.raw_content else "",
            "metadata": json.dumps(message.metadata) if message.metadata else "",
        }

        # 发布到 Stream
        msg_id = await self.redis.xadd(stream_key, message_data)
        logger.debug(f"[MessageQueue] 发布消息: {msg_id} -> {stream_key}")
        return msg_id

    async def publish_batch(self, messages: list[UnifiedMessage]) -> list[str]:
        """批量发布消息"""
        msg_ids = []
        for message in messages:
            msg_id = await self.publish(message)
            msg_ids.append(msg_id)
        return msg_ids

    async def consume(
        self,
        handler: Callable[[UnifiedMessage], Any],
        count: int = 10,
        block: int = 5000,
        consumer_name: Optional[str] = None,
    ) -> None:
        """消费消息（阻塞式）

        Args:
            handler: 消息处理函数
            count: 每次拉取的消息数量
            block: 阻塞等待时间（毫秒）
            consumer_name: 消费者名称
        """
        if not self.redis:
            raise RuntimeError("Redis 未连接")

        consumer = consumer_name or f"consumer_{id(self)}"
        self._running = True

        logger.info(f"[MessageQueue] 开始消费消息，消费者: {consumer}")

        while self._running:
            try:
                # 从消费者组读取消息
                messages = await self.redis.xreadgroup(
                    groupname=self.CONSUMER_GROUP,
                    consumername=consumer,
                    streams={self.INBOX_STREAM: ">"},
                    count=count,
                    block=block,
                )

                if not messages:
                    continue

                # 处理消息
                for stream_key, stream_messages in messages:
                    for msg_id, msg_data in stream_messages:
                        try:
                            # 解析消息
                            message = self._parse_message(msg_data)

                            # 调用处理函数
                            await self._call_handler(handler, message)

                            # 确认消息
                            await self.redis.xack(self.INBOX_STREAM, self.CONSUMER_GROUP, msg_id)
                            logger.debug(f"[MessageQueue] 消息处理完成: {msg_id}")

                        except Exception as e:
                            logger.error(f"[MessageQueue] 消息处理失败: {msg_id}, {e}")
                            # 移动到死信队列
                            await self._move_to_dead_letter(msg_id, msg_data, str(e))
                            # 确认消息（避免重复处理）
                            await self.redis.xack(self.INBOX_STREAM, self.CONSUMER_GROUP, msg_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MessageQueue] 消费异常: {e}")
                await asyncio.sleep(1)

        logger.info(f"[MessageQueue] 停止消费，消费者: {consumer}")

    async def get_pending_messages(
        self,
        consumer_name: Optional[str] = None,
        min_idle_time: int = 60000,
    ) -> list[tuple[str, dict]]:
        """获取待处理/超时的消息

        用于处理消费者崩溃后未确认的消息。

        Args:
            consumer_name: 指定消费者的待处理消息
            min_idle_time: 最小空闲时间（毫秒），超过此时间视为超时

        Returns:
            待处理消息列表 [(msg_id, msg_data), ...]
        """
        if not self.redis:
            raise RuntimeError("Redis 未连接")

        # 获取待处理消息信息
        pending = await self.redis.xpending_range(
            self.INBOX_STREAM,
            self.CONSUMER_GROUP,
            min="-",
            max="+",
            count=100,
        )

        pending_messages = []
        current_time = int(time.time() * 1000)

        for item in pending:
            msg_id = item["message_id"]
            idle_time = item.get("time_since_delivered", 0) * 1000

            # 检查空闲时间
            if idle_time >= min_idle_time:
                # 认领消息
                messages = await self.redis.xclaim(
                    self.INBOX_STREAM,
                    self.CONSUMER_GROUP,
                    consumer_name or "recovery",
                    min_idle_time,
                    [msg_id],
                )
                pending_messages.extend(messages)

        return pending_messages

    async def get_queue_length(self) -> int:
        """获取队列长度"""
        if not self.redis:
            return 0
        info = await self.redis.xinfo_stream(self.INBOX_STREAM)
        return info.get("length", 0)

    async def get_dead_letter_count(self) -> int:
        """获取死信队列消息数量"""
        if not self.redis:
            return 0
        try:
            info = await self.redis.xinfo_stream(self.DEAD_LETTER_STREAM)
            return info.get("length", 0)
        except redis.ResponseError:
            return 0

    async def reprocess_dead_letters(self, limit: int = 10) -> int:
        """重新处理死信队列中的消息

        Returns:
            成功重新投递的消息数量
        """
        if not self.redis:
            return 0

        # 读取死信队列
        messages = await self.redis.xrange(self.DEAD_LETTER_STREAM, count=limit)

        reprocessed = 0
        for msg_id, msg_data in messages:
            # 移除死信队列中的错误信息
            msg_data.pop("_error", None)
            msg_data.pop("_failed_at", None)

            # 重新发布到主队列
            await self.redis.xadd(self.INBOX_STREAM, msg_data)

            # 删除死信队列中的消息
            await self.redis.xdel(self.DEAD_LETTER_STREAM, msg_id)
            reprocessed += 1

        return reprocessed

    # ==================== 私有方法 ====================

    def _parse_message(self, msg_data: dict) -> UnifiedMessage:
        """解析消息数据"""
        raw_content = msg_data.get("raw_content", "")
        metadata = msg_data.get("metadata", "")

        return UnifiedMessage(
            message_id=msg_data["message_id"],
            original_id=msg_data.get("original_id") or None,
            channel_type=ChannelType(msg_data["channel_type"]),
            channel_id=msg_data["channel_id"],
            sender_id=msg_data["sender_id"],
            sender_name=msg_data.get("sender_name") or None,
            message_type=msg_data.get("message_type", "text"),
            content=msg_data.get("content", ""),
            raw_content=json.loads(raw_content) if raw_content else None,
            status=msg_data.get("status", "pending"),
            timestamp=int(msg_data.get("timestamp", 0)),
            tenant_id=int(msg_data["tenant_id"]) if msg_data.get("tenant_id") else None,
            metadata=json.loads(metadata) if metadata else {},
        )

    async def _call_handler(
        self,
        handler: Callable[[UnifiedMessage], Any],
        message: UnifiedMessage
    ) -> None:
        """调用消息处理函数"""
        result = handler(message)
        if asyncio.iscoroutine(result):
            await result

    async def _move_to_dead_letter(
        self,
        msg_id: str,
        msg_data: dict,
        error: str
    ) -> None:
        """移动消息到死信队列"""
        msg_data["_error"] = error
        msg_data["_failed_at"] = str(int(time.time() * 1000))
        msg_data["_original_id"] = msg_id

        await self.redis.xadd(self.DEAD_LETTER_STREAM, msg_data)
        logger.warning(f"[MessageQueue] 消息移入死信队列: {msg_id}")
