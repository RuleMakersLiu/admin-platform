"""API依赖注入"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

# 重新导出数据库依赖
__all__ = ["get_db", "AsyncSession"]
