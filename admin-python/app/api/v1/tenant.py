"""租户管理 - 路由已在 system.py 中实现"""
from fastapi import APIRouter

router = APIRouter(prefix="/system/tenant", tags=["租户管理"])
