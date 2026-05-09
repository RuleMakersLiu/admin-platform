"""Redis 客户端"""
import logging
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Optional[aioredis.Redis] = None


async def get_redis_client() -> aioredis.Redis:
    """获取 Redis 异步客户端（单例）"""
    global _client
    if _client is None:
        _client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


async def close_redis():
    """关闭 Redis 连接"""
    global _client
    if _client:
        await _client.close()
        _client = None
