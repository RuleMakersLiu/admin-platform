"""埋点数据处理工作进程"""
import asyncio
import logging
import signal
from typing import List

from app.services.tracking_consumer import (
    TrackingConsumer,
    TrackingEvent,
    create_tracking_consumer,
)
from app.services.tracking_analyzer import get_tracking_analyzer, close_tracking_analyzer

logger = logging.getLogger(__name__)


class TrackingWorker:
    """埋点数据处理工作进程"""

    def __init__(self):
        self.consumer: TrackingConsumer = None
        self._running = False

    async def start(self):
        """启动工作进程"""
        logger.info("[TrackingWorker] Starting...")

        # 初始化ClickHouse
        self.analyzer = await get_tracking_analyzer()
        logger.info("[TrackingWorker] ClickHouse initialized")

        # 创建并启动消费者
        self.consumer = await create_tracking_consumer()
        await self.consumer.start()
        logger.info("[TrackingWorker] Kafka consumer started")

        self._running = True

        # 开始消费
        await self.consumer.consume(self.process_events)

    async def stop(self):
        """停止工作进程"""
        logger.info("[TrackingWorker] Stopping...")
        self._running = False

        if self.consumer:
            await self.consumer.stop()

        # 刷新剩余的事件
        await self.analyzer.flush()

        # 关闭ClickHouse连接
        await close_tracking_analyzer()

        logger.info("[TrackingWorker] Stopped")

    async def process_events(self, events: List[TrackingEvent]):
        """
        处理一批事件

        Args:
            events: 事件列表
        """
        try:
            # 转换为ClickHouse格式
            event_dicts = [event.to_clickhouse_dict() for event in events]

            # 批量插入ClickHouse
            await self.analyzer.insert_events(event_dicts)

            logger.info(
                f"[TrackingWorker] Processed {len(events)} events, "
                f"Stats: {self.consumer.get_stats()}"
            )

        except Exception as e:
            logger.error(f"[TrackingWorker] Failed to process events: {e}")
            raise

    def get_stats(self) -> dict:
        """获取统计信息"""
        if not self.consumer:
            return {}
        return self.consumer.get_stats()


# 全局工作进程实例
_worker: TrackingWorker = None


async def start_tracking_worker():
    """启动埋点工作进程"""
    global _worker
    _worker = TrackingWorker()
    await _worker.start()


async def stop_tracking_worker():
    """停止埋点工作进程"""
    global _worker
    if _worker:
        await _worker.stop()


def get_tracking_worker() -> TrackingWorker:
    """获取工作进程实例"""
    return _worker


async def main():
    """主函数 - 独立运行工作进程"""
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )

    worker = TrackingWorker()

    # 设置信号处理
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(worker.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await worker.start()
    except Exception as e:
        logger.error(f"Worker failed: {e}")
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
