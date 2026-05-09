"""FastAPI 依赖项"""
from typing import Dict

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.models import SysAdmin, SysAdminGroup


async def get_current_user(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """获取当前用户信息

    从 JWT Token 中解析用户信息
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="未登录")

    # 提取 token
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization

    try:
        # 解析 JWT
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"]
        )

        admin_id = payload.get("adminId")
        tenant_id = payload.get("tenantId")

        if not admin_id:
            raise HTTPException(status_code=401, detail="无效的Token")

        # 验证用户是否存在
        stmt = select(SysAdmin).where(
            SysAdmin.id == admin_id,
            SysAdmin.is_deleted == 0,
            SysAdmin.status == 1
        )
        result = await db.execute(stmt)
        admin = result.scalar_one_or_none()

        if not admin:
            raise HTTPException(status_code=401, detail="用户不存在或已禁用")

        # Check if user is super admin
        is_super = 0
        if admin.admin_group_id:
            grp_result = await db.execute(
                select(SysAdminGroup.is_super).where(SysAdminGroup.id == admin.admin_group_id)
            )
            row = grp_result.first()
            if row:
                is_super = row[0]

        return {
            "adminId": admin_id,
            "tenantId": tenant_id or admin.tenant_id,
            "username": admin.username,
            "realName": admin.real_name,
            "isSuper": is_super,
        }

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的Token")
