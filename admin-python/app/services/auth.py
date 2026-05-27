"""认证服务"""
import time
from typing import Optional

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import SysAdmin, SysAdminGroup, SysAdminTenant, SysTenant
from app.schemas.common import LoginResponse, UserInfo
from app.services.permissions import parse_power


class AuthService:
    """认证服务"""

    @staticmethod
    async def get_admin_tenant_ids(db: AsyncSession, admin: SysAdmin, is_super: bool = False) -> list[int]:
        """Return tenant ids this admin can operate on."""
        if is_super:
            result = await db.execute(
                select(SysTenant.id).where(SysTenant.status == 1, SysTenant.is_deleted == 0).order_by(SysTenant.id)
            )
            return [int(row[0]) for row in result.all()]

        result = await db.execute(
            select(SysAdminTenant.tenant_id)
            .where(SysAdminTenant.admin_id == admin.id)
            .order_by(SysAdminTenant.is_default.desc(), SysAdminTenant.tenant_id)
        )
        tenant_ids = [int(row[0]) for row in result.all()]
        if admin.tenant_id and int(admin.tenant_id) not in tenant_ids:
            tenant_ids.insert(0, int(admin.tenant_id))
        return tenant_ids or [int(admin.tenant_id or 0)]

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )

    @staticmethod
    def hash_password(password: str) -> str:
        """加密密码"""
        return bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

    @staticmethod
    def create_token(admin_id: int, username: str, tenant_id: int) -> str:
        """创建JWT Token"""
        payload = {
            "adminId": admin_id,
            "username": username,
            "tenantId": tenant_id,
            "sub": username,
            "iat": int(time.time()),
            "exp": int(time.time()) + settings.jwt_expire_minutes * 60,
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    @staticmethod
    def verify_token(token: str) -> Optional[dict]:
        """验证JWT Token"""
        try:
            payload = jwt.decode(
                token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    @staticmethod
    async def login(
        db: AsyncSession, username: str, password: str, tenant_id: Optional[int] = None
    ) -> Optional[LoginResponse]:
        """用户登录"""
        # 查询用户
        stmt = select(SysAdmin).where(
            SysAdmin.username == username,
            SysAdmin.is_deleted == 0,
            SysAdmin.status == 1,
        )
        result = await db.execute(stmt)
        admin = result.scalar_one_or_none()

        if not admin:
            return None

        # 验证密码
        if not AuthService.verify_password(password, admin.password):
            return None

        group = None
        if admin.admin_group_id:
            group_result = await db.execute(
                select(SysAdminGroup).where(
                    SysAdminGroup.id == admin.admin_group_id,
                    SysAdminGroup.status == 1,
                )
            )
            group = group_result.scalar_one_or_none()
        is_super = bool(group and group.is_super == 1)
        tenant_ids = await AuthService.get_admin_tenant_ids(db, admin, is_super=is_super)
        login_tenant_id = int(tenant_id or admin.tenant_id or 0)
        if not is_super and login_tenant_id not in tenant_ids:
            return None

        # 创建Token
        token = AuthService.create_token(admin.id, admin.username, login_tenant_id)

        return LoginResponse(
            token=token,
            admin_id=admin.id,
            username=admin.username,
            real_name=admin.real_name,
            tenant_id=login_tenant_id,
            tenant_ids=tenant_ids,
        )

    @staticmethod
    async def get_user_info(db: AsyncSession, admin_id: int) -> Optional[UserInfo]:
        """获取用户信息"""
        stmt = select(SysAdmin).where(
            SysAdmin.id == admin_id, SysAdmin.is_deleted == 0
        )
        result = await db.execute(stmt)
        admin = result.scalar_one_or_none()

        if not admin:
            return None

        group = None
        if admin.admin_group_id:
            group_result = await db.execute(
                select(SysAdminGroup).where(
                    SysAdminGroup.id == admin.admin_group_id,
                    SysAdminGroup.status == 1,
                )
            )
            group = group_result.scalar_one_or_none()

        is_super = bool(group and group.is_super == 1)
        permissions = ["*"] if is_super else parse_power(group.power if group else None)
        tenant_ids = await AuthService.get_admin_tenant_ids(db, admin, is_super=is_super)

        return UserInfo(
            admin_id=admin.id,
            username=admin.username,
            real_name=admin.real_name,
            phone=admin.phone,
            email=admin.email,
            status=admin.status,
            admin_group_id=admin.admin_group_id,
            group_name=group.name if group else None,
            is_super=is_super,
            permissions=permissions,
            tenant_id=admin.tenant_id,
            tenant_ids=tenant_ids,
        )
