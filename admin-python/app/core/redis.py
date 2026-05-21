"""Redis 客户端"""
import logging
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Optional[aioredis.Redis] = None
_gateway_client: Optional[aioredis.Redis] = None


async def get_redis_client() -> aioredis.Redis:
    """获取 Redis 异步客户端（单例，db 1）"""
    global _client
    if _client is None:
        _client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


async def get_gateway_redis() -> aioredis.Redis:
    """获取 Gateway 共享的 Redis 客户端（db 0），用于写入权限缓存"""
    global _gateway_client
    if _gateway_client is None:
        url = settings.redis_url.rsplit("/", 1)[0] + "/0"
        _gateway_client = aioredis.from_url(url, encoding="utf-8", decode_responses=True)
    return _gateway_client


async def close_redis():
    """关闭 Redis 连接"""
    global _client, _gateway_client
    if _client:
        await _client.close()
        _client = None
    if _gateway_client:
        await _gateway_client.close()
        _gateway_client = None
