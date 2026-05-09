"""Kafka消费者 - 埋点数据消费服务"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings

logger = logging.getLogger(__name__)


class TrackingEvent(BaseModel):
    """埋点事件模型"""
    # 基础信息
    event_id: str = Field(..., description="事件ID")
    event_type: str = Field(..., description="事件类型")
    event_name: str = Field(..., description="事件名称")
    timestamp: int = Field(..., description="事件时间戳（毫秒）")
    platform: Optional[str] = Field(None, description="平台")
    version: Optional[str] = Field(None, description="应用版本")

    # 用户信息
    user_id: Optional[str] = Field(None, description="用户ID")
    device_id: Optional[str] = Field(None, description="设备ID")
    session_id: Optional[str] = Field(None, description="会话ID")
    tenant_id: Optional[str] = Field(None, description="租户ID")
    admin_id: Optional[str] = Field(None, description="管理员ID")
    username: Optional[str] = Field(None, description="用户名")
    user_type: Optional[str] = Field(None, description="用户类型")

    # 设备信息
    device_type: Optional[str] = Field(None, description="设备类型")
    os: Optional[str] = Field(None, description="操作系统")
    os_version: Optional[str] = Field(None, description="操作系统版本")
    browser: Optional[str] = Field(None, description="浏览器")
    browser_version: Optional[str] = Field(None, description="浏览器版本")
    screen_width: Optional[int] = Field(None, description="屏幕宽度")
    screen_height: Optional[int] = Field(None, description="屏幕高度")
    language: Optional[str] = Field(None, description="语言")

    # 地理信息
    ip: Optional[str] = Field(None, description="IP地址")
    country: Optional[str] = Field(None, description="国家")
    province: Optional[str] = Field(None, description="省份")
    city: Optional[str] = Field(None, description="城市")

    # 页面信息
    page_url: Optional[str] = Field(None, description="页面URL")
    page_title: Optional[str] = Field(None, description="页面标题")
    referrer: Optional[str] = Field(None, description="来源页面")
    page_duration: Optional[int] = Field(None, description="页面停留时长（毫秒）")

    # 事件属性
    properties: Optional[Dict[str, Any]] = Field(None, description="自定义属性")

    # 元数据
    source: Optional[str] = Field(None, description="来源")
    user_agent: Optional[str] = Field(None, description="User-Agent")

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v):
        """验证时间戳"""
        if v <= 0:
            raise ValueError('timestamp must be positive')
        return v

    def to_clickhouse_dict(self) -> Dict[str, Any]:
        """转换为ClickHouse格式的字典"""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type,
            'event_name': self.event_name,
            'timestamp': datetime.fromtimestamp(self.timestamp / 1000),
            'platform': self.platform or '',
            'version': self.version or '',
            'user_id': self.user_id or '',
            'device_id': self.device_id or '',
            'session_id': self.session_id or '',
            'tenant_id': self.tenant_id or '',
            'admin_id': self.admin_id or '',
            'username': self.username or '',
            'user_type': self.user_type or '',
            'device_type': self.device_type or '',
            'os': self.os or '',
            'os_version': self.os_version or '',
            'browser': self.browser or '',
            'browser_version': self.browser_version or '',
            'screen_width': self.screen_width or 0,
            'screen_height': self.screen_height or 0,
            'language': self.language or '',
            'ip': self.ip or '',
            'country': self.country or '',
            'province': self.province or '',
            'city': self.city or '',
            'page_url': self.page_url or '',
            'page_title': self.page_title or '',
            'referrer': self.referrer or '',
            'page_duration': self.page_duration or 0,
            'properties': json.dumps(self.properties) if self.properties else '{}',
            'source': self.source or '',
            'user_agent': self.user_agent or '',
        }


class TrackingConsumer:
    """Kafka消费者"""

    def __init__(
        self,
        topic: str,
        bootstrap_servers: str,
        group_id: str = "tracking-consumer",
        batch_size: int = 100,
        batch_timeout: int = 5,
    ):
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.consumer: Optional[AIOKafkaConsumer] = None
        self._running = False
        self._processed_count = 0
        self._failed_count = 0

    async def start(self):
        """启动消费者"""
        try:
            self.consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset='latest',
                enable_auto_commit=False,
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            )
            await self.consumer.start()
            self._running = True
            logger.info(f"[TrackingConsumer] Started consuming topic: {self.topic}")
        except Exception as e:
            logger.error(f"[TrackingConsumer] Failed to start: {e}")
            raise

    async def stop(self):
        """停止消费者"""
        self._running = False
        if self.consumer:
            await self.consumer.stop()
            logger.info("[TrackingConsumer] Stopped")

    async def consume(self, process_callback):
        """
        消费消息

        Args:
            process_callback: 处理回调函数，接收 List[TrackingEvent] 参数
        """
        batch: List[TrackingEvent] = []

        try:
            async for message in self.consumer:
                if not self._running:
                    break

                try:
                    # 解析事件
                    event = TrackingEvent(**message.value)
                    batch.append(event)

                    logger.debug(
                        f"[TrackingConsumer] Received event: {event.event_type}/{event.event_name}"
                    )

                    # 批量处理
                    if len(batch) >= self.batch_size:
                        await self._process_batch(batch, process_callback)
                        await self.consumer.commit()
                        batch = []

                except Exception as e:
                    logger.error(f"[TrackingConsumer] Failed to parse event: {e}")
                    self._failed_count += 1

            # 处理剩余的消息
            if batch:
                await self._process_batch(batch, process_callback)
                await self.consumer.commit()

        except KafkaError as e:
            logger.error(f"[TrackingConsumer] Kafka error: {e}")
            raise
        except Exception as e:
            logger.error(f"[TrackingConsumer] Unexpected error: {e}")
            raise

    async def _process_batch(
        self, batch: List[TrackingEvent], process_callback
    ):
        """处理一批事件"""
        try:
            await process_callback(batch)
            self._processed_count += len(batch)
            logger.info(f"[TrackingConsumer] Processed {len(batch)} events")
        except Exception as e:
            logger.error(f"[TrackingConsumer] Failed to process batch: {e}")
            self._failed_count += len(batch)
            raise

    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return {
            'processed_count': self._processed_count,
            'failed_count': self._failed_count,
        }


async def create_tracking_consumer() -> TrackingConsumer:
    """创建埋点消费者实例"""
    # 从配置读取Kafka设置
    kafka_bootstrap = getattr(settings, 'kafka_bootstrap_servers', 'localhost:9092')
    kafka_topic = getattr(settings, 'kafka_tracking_topic', 'tracking-events')
    kafka_group = getattr(settings, 'kafka_tracking_group', 'tracking-consumer')

    consumer = TrackingConsumer(
        topic=kafka_topic,
        bootstrap_servers=kafka_bootstrap,
        group_id=kafka_group,
        batch_size=100,
        batch_timeout=5,
    )

    return consumer
