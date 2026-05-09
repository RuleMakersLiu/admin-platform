"""数据模型"""
import time
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SysAdmin(Base):
    """管理员模型"""
    __tablename__ = "sys_admin"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password: Mapped[str] = mapped_column(String(128))
    real_name: Mapped[str] = mapped_column(String(64))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(128))
    status: Mapped[int] = mapped_column(Integer, default=1)
    # 数据库列名是 admin_group_id
    admin_group_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)


class SysAdminGroup(Base):
    """管理员组模型"""
    __tablename__ = "sys_admin_group"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))  # 数据库列名是 name
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0)
    power: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON格式的权限列表
    is_super: Mapped[int] = mapped_column(Integer, default=0)  # 是否超级管理员: 0否 1是
    status: Mapped[int] = mapped_column(Integer, default=1)
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)


class SysMenu(Base):
    """菜单模型"""
    __tablename__ = "sys_menu"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0)
    name: Mapped[str] = mapped_column(String(64))
    path: Mapped[Optional[str]] = mapped_column(String(255))
    component: Mapped[Optional[str]] = mapped_column(String(255))
    permission: Mapped[Optional[str]] = mapped_column(String(100))
    icon: Mapped[Optional[str]] = mapped_column(String(64))
    # 数据库列名是 menu_type
    menu_type: Mapped[int] = mapped_column(Integer)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(Integer, default=1)
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)


class SysLlmConfig(Base):
    """LLM 配置模型"""
    __tablename__ = "sys_llm_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(50))
    base_url: Mapped[str] = mapped_column(String(255), default="")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    model_name: Mapped[str] = mapped_column(String(100))
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    temperature: Mapped[float] = mapped_column(Numeric(3, 2), default=0.7)
    extra_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(Integer, default=1)
    tenant_id: Mapped[int] = mapped_column(BigInteger, default=0)
    admin_id: Mapped[int] = mapped_column(BigInteger, default=0)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))


class SysGitConfig(Base):
    """Git 配置模型"""
    __tablename__ = "sys_git_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    platform: Mapped[str] = mapped_column(String(20))
    base_url: Mapped[str] = mapped_column(String(255), default="")
    access_token: Mapped[str] = mapped_column(String(500), default="")
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ssh_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(Integer, default=1)
    tenant_id: Mapped[int] = mapped_column(BigInteger, default=0)
    admin_id: Mapped[int] = mapped_column(BigInteger, default=0)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))


class SysTenant(Base):
    """租户模型"""
    __tablename__ = "sys_tenant"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(50), unique=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(50))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20))
    status: Mapped[int] = mapped_column(Integer, default=1)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)
