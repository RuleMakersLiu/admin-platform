"""系统管理API"""
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.models import SysAdmin, SysAdminGroup, SysMenu, SysTenant, SysLlmConfig, SysGitConfig
from app.schemas.common import PaginatedResult, Response

router = APIRouter(prefix="/system", tags=["系统管理"])


# ==================== 请求模型 ====================
class CreateAdminRequest(BaseModel):
    """创建管理员请求"""
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    real_name: str = Field(..., min_length=2, max_length=64)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=128)
    admin_group_id: int
    tenant_id: int = 1
    status: int = 1


class UpdateAdminRequest(BaseModel):
    """更新管理员请求"""
    real_name: Optional[str] = Field(None, min_length=2, max_length=64)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=128)
    admin_group_id: Optional[int] = None
    status: Optional[int] = None
    password: Optional[str] = Field(None, min_length=6, max_length=128)


class CreateGroupRequest(BaseModel):
    """创建角色组请求"""
    group_name: str = Field(..., min_length=2, max_length=64)
    power: str = "[]"
    status: int = 1


class UpdateGroupRequest(BaseModel):
    """更新角色组请求"""
    group_name: Optional[str] = Field(None, min_length=2, max_length=64)
    power: Optional[str] = None
    status: Optional[int] = None


class CreateMenuRequest(BaseModel):
    """创建菜单请求"""
    parent_id: int = 0
    menu_name: str = Field(..., min_length=2, max_length=64)
    menu_type: int = 1
    path: Optional[str] = None
    component: Optional[str] = None
    permission: Optional[str] = None
    icon: Optional[str] = None
    sort: int = 0
    status: int = 1


class UpdateMenuRequest(BaseModel):
    """更新菜单请求"""
    menu_name: Optional[str] = None
    menu_type: Optional[int] = None
    path: Optional[str] = None
    component: Optional[str] = None
    permission: Optional[str] = None
    icon: Optional[str] = None
    sort: Optional[int] = None
    status: Optional[int] = None


# ==================== 用户管理 ====================
@router.get("/admin/list", response_model=Response)
async def list_admins(
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    status: Optional[int] = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取管理员列表"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysAdmin.is_deleted == 0]
    if not is_super:
        conditions.append(SysAdmin.tenant_id == tenant_id)

    if keyword:
        conditions.append(
            or_(
                SysAdmin.username.ilike(f"%{keyword}%"),
                SysAdmin.real_name.ilike(f"%{keyword}%")
            )
        )

    if status is not None:
        conditions.append(SysAdmin.status == status)

    # 查询总数
    count_stmt = select(func.count()).select_from(SysAdmin).where(*conditions)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    # 分页查询
    stmt = (
        select(SysAdmin, SysAdminGroup.name)
        .outerjoin(SysAdminGroup, SysAdmin.admin_group_id == SysAdminGroup.id)
        .where(*conditions)
        .order_by(SysAdmin.create_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(stmt)
    rows = result.all()

    items = []
    for admin, group_name in rows:
        items.append({
            "id": admin.id,
            "username": admin.username,
            "realName": admin.real_name,
            "phone": admin.phone,
            "email": admin.email,
            "adminGroupId": admin.admin_group_id,
            "groupName": group_name,
            "status": admin.status,
            "tenantId": admin.tenant_id,
            "createTime": admin.create_time,
            "updateTime": admin.update_time,
        })

    return Response(data={"list": items, "total": total})


@router.post("/admin", response_model=Response)
async def create_admin(
    request: CreateAdminRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建管理员"""
    import bcrypt
    is_super = user.get("isSuper")

    # 检查用户名是否已存在
    stmt = select(SysAdmin).where(SysAdmin.username == request.username)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        return Response(code=400, message="用户名已存在")

    # 加密密码
    hashed_password = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()

    # 非超管只能创建本租户用户
    create_tenant_id = request.tenant_id if is_super else user.get("tenantId")

    now = int(time.time() * 1000)
    admin = SysAdmin(
        username=request.username,
        password=hashed_password,
        real_name=request.real_name,
        phone=request.phone,
        email=request.email,
        admin_group_id=request.admin_group_id,
        tenant_id=create_tenant_id,
        status=request.status,
        create_time=now,
        update_time=now,
        is_deleted=0,
    )

    db.add(admin)
    await db.flush()
    await db.refresh(admin)

    return Response(data={
        "id": admin.id,
        "username": admin.username,
        "realName": admin.real_name,
    })


@router.get("/admin/{admin_id}", response_model=Response)
async def get_admin(
    admin_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取管理员详情"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysAdmin.id == admin_id, SysAdmin.is_deleted == 0]
    if not is_super:
        conditions.append(SysAdmin.tenant_id == tenant_id)

    stmt = (
        select(SysAdmin, SysAdminGroup.name)
        .outerjoin(SysAdminGroup, SysAdmin.admin_group_id == SysAdminGroup.id)
        .where(*conditions)
    )
    result = await db.execute(stmt)
    row = result.first()

    if not row:
        return Response(code=404, message="用户不存在")

    admin, group_name = row
    return Response(data={
        "id": admin.id,
        "username": admin.username,
        "realName": admin.real_name,
        "phone": admin.phone,
        "email": admin.email,
        "adminGroupId": admin.admin_group_id,
        "groupName": group_name,
        "status": admin.status,
        "tenantId": admin.tenant_id,
        "createTime": admin.create_time,
    })


@router.put("/admin/{admin_id}", response_model=Response)
async def update_admin(
    admin_id: int,
    request: UpdateAdminRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新管理员"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysAdmin.id == admin_id, SysAdmin.is_deleted == 0]
    if not is_super:
        conditions.append(SysAdmin.tenant_id == tenant_id)

    stmt = select(SysAdmin).where(*conditions)
    result = await db.execute(stmt)
    admin = result.scalar_one_or_none()

    if not admin:
        return Response(code=404, message="用户不存在")

    if request.real_name is not None:
        admin.real_name = request.real_name
    if request.phone is not None:
        admin.phone = request.phone
    if request.email is not None:
        admin.email = request.email
    if request.admin_group_id is not None:
        admin.admin_group_id = request.admin_group_id
    if request.status is not None:
        admin.status = request.status
    if request.password:
        import bcrypt
        admin.password = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()

    admin.update_time = int(time.time() * 1000)
    await db.flush()

    return Response(data={"id": admin.id})


@router.delete("/admin/{admin_id}", response_model=Response)
async def delete_admin(
    admin_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除管理员（软删除）"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysAdmin.id == admin_id, SysAdmin.is_deleted == 0]
    if not is_super:
        conditions.append(SysAdmin.tenant_id == tenant_id)

    stmt = select(SysAdmin).where(*conditions)
    result = await db.execute(stmt)
    admin = result.scalar_one_or_none()

    if not admin:
        return Response(code=404, message="用户不存在")

    # 不能删除自己
    if admin.id == user.get("adminId"):
        return Response(code=400, message="不能删除自己")

    admin.is_deleted = 1
    admin.update_time = int(time.time() * 1000)
    await db.flush()

    return Response(message="删除成功")


# ==================== 角色管理 ====================
@router.get("/group/list", response_model=Response)
async def list_groups(
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取角色列表"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysAdminGroup.is_deleted == 0]
    if not is_super:
        conditions.append(SysAdminGroup.tenant_id == tenant_id)

    if keyword:
        conditions.append(SysAdminGroup.name.ilike(f"%{keyword}%"))

    count_stmt = select(func.count()).select_from(SysAdminGroup).where(*conditions)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    stmt = (
        select(SysAdminGroup)
        .where(*conditions)
        .order_by(SysAdminGroup.create_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(stmt)
    items = result.scalars().all()

    return Response(data={
        "list": [{
            "id": g.id,
            "groupName": g.name,
            "power": g.power,
            "status": g.status,
            "createTime": g.create_time,
        } for g in items],
        "total": total
    })


@router.post("/group", response_model=Response)
async def create_group(
    request: CreateGroupRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建角色"""
    tenant_id = user.get("tenantId")

    now = int(time.time() * 1000)
    group = SysAdminGroup(
        name=request.group_name,
        power=request.power,
        status=request.status,
        tenant_id=tenant_id,
        create_time=now,
        update_time=now,
        is_deleted=0,
    )

    db.add(group)
    await db.flush()
    await db.refresh(group)

    return Response(data={"id": group.id, "groupName": group.name})


@router.put("/group/{group_id}", response_model=Response)
async def update_group(
    group_id: int,
    request: UpdateGroupRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新角色"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysAdminGroup.id == group_id, SysAdminGroup.is_deleted == 0]
    if not is_super:
        conditions.append(SysAdminGroup.tenant_id == tenant_id)

    stmt = select(SysAdminGroup).where(*conditions)
    result = await db.execute(stmt)
    group = result.scalar_one_or_none()

    if not group:
        return Response(code=404, message="角色不存在")

    if request.group_name is not None:
        group.name = request.group_name
    if request.power is not None:
        group.power = request.power
    if request.status is not None:
        group.status = request.status

    group.update_time = int(time.time() * 1000)
    await db.flush()

    return Response(data={"id": group.id})


@router.delete("/group/{group_id}", response_model=Response)
async def delete_group(
    group_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除角色"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysAdminGroup.id == group_id, SysAdminGroup.is_deleted == 0]
    if not is_super:
        conditions.append(SysAdminGroup.tenant_id == tenant_id)

    stmt = select(SysAdminGroup).where(*conditions)
    result = await db.execute(stmt)
    group = result.scalar_one_or_none()

    if not group:
        return Response(code=404, message="角色不存在")

    # 检查是否有用户在使用该角色
    admin_stmt = select(func.count()).select_from(SysAdmin).where(
        SysAdmin.admin_group_id == group_id,
        SysAdmin.is_deleted == 0
    )
    admin_count = await db.execute(admin_stmt)
    if admin_count.scalar() > 0:
        return Response(code=400, message="该角色下存在用户，无法删除")

    group.is_deleted = 1
    group.update_time = int(time.time() * 1000)
    await db.flush()

    return Response(message="删除成功")


# ==================== 菜单管理 ====================
@router.get("/menu/list", response_model=Response)
async def list_menus(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取菜单列表（树形）"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysMenu.is_deleted == 0]
    if not is_super:
        conditions.append(SysMenu.tenant_id == tenant_id)

    stmt = (
        select(SysMenu)
        .where(*conditions)
        .order_by(SysMenu.sort, SysMenu.create_time)
    )

    result = await db.execute(stmt)
    menus = result.scalars().all()

    # 构建树形结构
    menu_list = [{
        "id": m.id,
        "parentId": m.parent_id,
        "menuName": m.name,
        "menuType": m.menu_type,
        "path": m.path,
        "component": m.component,
        "permission": m.permission,
        "icon": m.icon,
        "sort": m.sort,
        "status": m.status,
    } for m in menus]

    return Response(data=menu_list)


@router.post("/menu", response_model=Response)
async def create_menu(
    request: CreateMenuRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建菜单"""
    tenant_id = user.get("tenantId")

    now = int(time.time() * 1000)
    menu = SysMenu(
        parent_id=request.parent_id,
        menu_name=request.menu_name,
        menu_type=request.menu_type,
        path=request.path,
        component=request.component,
        permission=request.permission,
        icon=request.icon,
        sort=request.sort,
        status=request.status,
        tenant_id=tenant_id,
        create_time=now,
        update_time=now,
        is_deleted=0,
    )

    db.add(menu)
    await db.flush()
    await db.refresh(menu)

    return Response(data={"id": menu.id, "menuName": menu.name})


@router.put("/menu/{menu_id}", response_model=Response)
async def update_menu(
    menu_id: int,
    request: UpdateMenuRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新菜单"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysMenu.id == menu_id, SysMenu.is_deleted == 0]
    if not is_super:
        conditions.append(SysMenu.tenant_id == tenant_id)

    stmt = select(SysMenu).where(*conditions)
    result = await db.execute(stmt)
    menu = result.scalar_one_or_none()

    if not menu:
        return Response(code=404, message="菜单不存在")

    if request.menu_name is not None:
        menu.name = request.menu_name
    if request.menu_type is not None:
        menu.menu_type = request.menu_type
    if request.path is not None:
        menu.path = request.path
    if request.component is not None:
        menu.component = request.component
    if request.permission is not None:
        menu.permission = request.permission
    if request.icon is not None:
        menu.icon = request.icon
    if request.sort is not None:
        menu.sort = request.sort
    if request.status is not None:
        menu.status = request.status

    menu.update_time = int(time.time() * 1000)
    await db.flush()

    return Response(data={"id": menu.id})


@router.delete("/menu/{menu_id}", response_model=Response)
async def delete_menu(
    menu_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除菜单"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysMenu.id == menu_id, SysMenu.is_deleted == 0]
    if not is_super:
        conditions.append(SysMenu.tenant_id == tenant_id)

    stmt = select(SysMenu).where(*conditions)
    result = await db.execute(stmt)
    menu = result.scalar_one_or_none()

    if not menu:
        return Response(code=404, message="菜单不存在")

    # 检查是否有子菜单
    child_stmt = select(func.count()).select_from(SysMenu).where(
        SysMenu.parent_id == menu_id,
        SysMenu.is_deleted == 0
    )
    child_count = await db.execute(child_stmt)
    if child_count.scalar() > 0:
        return Response(code=400, message="存在子菜单，无法删除")

    menu.is_deleted = 1
    menu.update_time = int(time.time() * 1000)
    await db.flush()

    return Response(message="删除成功")


# ==================== 租户管理 ====================
@router.get("/tenant/all", response_model=Response)
async def get_all_tenants(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取所有启用的租户（下拉框用）"""
    result = await db.execute(
        select(SysTenant).where(SysTenant.status == 1, SysTenant.is_deleted == 0).order_by(SysTenant.id)
    )
    tenants = result.scalars().all()
    return Response(data=[
        {"id": t.id, "name": t.name, "code": t.code}
        for t in tenants
    ])


@router.get("/tenant/list", response_model=Response)
async def list_tenants(
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取租户列表"""
    conditions = [SysTenant.is_deleted == 0]

    if keyword:
        conditions.append(
            or_(
                SysTenant.name.ilike(f"%{keyword}%"),
                SysTenant.code.ilike(f"%{keyword}%")
            )
        )

    count_stmt = select(func.count()).select_from(SysTenant).where(*conditions)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    stmt = (
        select(SysTenant)
        .where(*conditions)
        .order_by(SysTenant.create_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(stmt)
    items = result.scalars().all()

    return Response(data={
        "list": [{
            "id": t.id,
            "tenantName": t.name,
            "tenantCode": t.code,
            "contactName": t.contact_name,
            "contactPhone": t.contact_phone,
            "status": t.status,
            "createTime": t.create_time,
        } for t in items],
        "total": total
    })


class CreateTenantRequest(BaseModel):
    """创建租户请求"""
    tenant_name: str = Field(..., min_length=2, max_length=100)
    tenant_code: str = Field(..., min_length=2, max_length=50)
    contact_name: Optional[str] = Field(None, max_length=50)
    contact_phone: Optional[str] = Field(None, max_length=20)
    status: int = 1


class UpdateTenantRequest(BaseModel):
    """更新租户请求"""
    tenant_name: Optional[str] = Field(None, min_length=2, max_length=100)
    contact_name: Optional[str] = Field(None, max_length=50)
    contact_phone: Optional[str] = Field(None, max_length=20)
    status: Optional[int] = None


@router.post("/tenant", response_model=Response)
async def create_tenant(
    request: CreateTenantRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建租户"""
    # 检查租户编码是否已存在
    stmt = select(SysTenant).where(SysTenant.code == request.tenant_code)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        return Response(code=400, message="租户编码已存在")

    now = int(time.time() * 1000)
    tenant = SysTenant(
        name=request.tenant_name,
        code=request.tenant_code,
        contact_name=request.contact_name,
        contact_phone=request.contact_phone,
        status=request.status,
        create_time=now,
        update_time=now,
    )

    db.add(tenant)
    await db.flush()
    await db.refresh(tenant)

    return Response(data={"id": tenant.id, "tenantName": tenant.name})


@router.put("/tenant/{tenant_id}", response_model=Response)
async def update_tenant(
    tenant_id: int,
    request: UpdateTenantRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新租户"""
    stmt = select(SysTenant).where(SysTenant.id == tenant_id)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()

    if not tenant:
        return Response(code=404, message="租户不存在")

    if request.tenant_name is not None:
        tenant.name = request.tenant_name
    if request.contact_name is not None:
        tenant.contact_name = request.contact_name
    if request.contact_phone is not None:
        tenant.contact_phone = request.contact_phone
    if request.status is not None:
        tenant.status = request.status

    tenant.update_time = int(time.time() * 1000)
    await db.flush()

    return Response(data={"id": tenant.id})


@router.delete("/tenant/{tenant_id}", response_model=Response)
async def delete_tenant(
    tenant_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除租户"""
    stmt = select(SysTenant).where(SysTenant.id == tenant_id)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()

    if not tenant:
        return Response(code=404, message="租户不存在")

    # 检查是否有用户在该租户下
    admin_stmt = select(func.count()).select_from(SysAdmin).where(
        SysAdmin.tenant_id == tenant_id,
        SysAdmin.is_deleted == 0
    )
    admin_count = await db.execute(admin_stmt)
    if admin_count.scalar() > 0:
        return Response(code=400, message="该租户下存在用户，无法删除")

    # 硬删除租户
    await db.execute(delete(SysTenant).where(SysTenant.id == tenant_id))
    await db.flush()

    return Response(message="删除成功")


# ==================== LLM 配置管理 ====================

class CreateLlmConfigRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    provider: str = Field(..., min_length=1, max_length=50)
    base_url: str = Field("", max_length=255)
    api_key: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1, max_length=100)
    max_tokens: int = 4096
    temperature: float = 0.7
    status: int = 1


class UpdateLlmConfigRequest(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    status: Optional[int] = None


@router.get("/llm", response_model=Response)
async def list_llm_configs(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
):
    """获取 LLM 配置列表"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = []
    if not is_super:
        conditions.append(SysLlmConfig.tenant_id == tenant_id)
    if keyword:
        conditions.append(SysLlmConfig.name.ilike(f"%{keyword}%"))

    total_result = await db.execute(
        select(func.count()).select_from(SysLlmConfig).where(*conditions)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(SysLlmConfig)
        .where(*conditions)
        .order_by(SysLlmConfig.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = result.scalars().all()

    return Response(data={
        "total": total,
        "list": [{
            "id": c.id,
            "name": c.name,
            "provider": c.provider,
            "base_url": c.base_url,
            "api_key": c.api_key[:8] + "..." if c.api_key and len(c.api_key) > 8 else c.api_key,
            "model_name": c.model_name,
            "max_tokens": c.max_tokens,
            "temperature": float(c.temperature) if c.temperature else 0.7,
            "is_default": c.is_default,
            "status": c.status,
            "create_time": c.create_time,
            "update_time": c.update_time,
        } for c in items],
    })


@router.get("/llm/{config_id}", response_model=Response)
async def get_llm_config(
    config_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取 LLM 配置详情"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysLlmConfig.id == config_id]
    if not is_super:
        conditions.append(SysLlmConfig.tenant_id == tenant_id)

    result = await db.execute(
        select(SysLlmConfig).where(*conditions)
    )
    config = result.scalar_one_or_none()
    if not config:
        return Response(code=404, message="配置不存在")
    return Response(data={
        "id": config.id,
        "name": config.name,
        "provider": config.provider,
        "base_url": config.base_url,
        "api_key": config.api_key,
        "model_name": config.model_name,
        "max_tokens": config.max_tokens,
        "temperature": float(config.temperature) if config.temperature else 0.7,
        "is_default": config.is_default,
        "status": config.status,
    })


@router.post("/llm", response_model=Response)
async def create_llm_config(
    request: CreateLlmConfigRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建 LLM 配置"""
    now = int(time.time() * 1000)
    config = SysLlmConfig(
        name=request.name,
        provider=request.provider,
        base_url=request.base_url,
        api_key=request.api_key,
        model_name=request.model_name,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        status=request.status,
        tenant_id=user.get("tenantId", 0),
        admin_id=user.get("adminId", 0),
        create_time=now,
        update_time=now,
    )
    db.add(config)
    await db.flush()
    return Response(data={"id": config.id})


@router.put("/llm/{config_id}", response_model=Response)
async def update_llm_config(
    config_id: int,
    request: UpdateLlmConfigRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新 LLM 配置"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysLlmConfig.id == config_id]
    if not is_super:
        conditions.append(SysLlmConfig.tenant_id == tenant_id)

    result = await db.execute(
        select(SysLlmConfig).where(*conditions)
    )
    config = result.scalar_one_or_none()
    if not config:
        return Response(code=404, message="配置不存在")

    if request.name is not None:
        config.name = request.name
    if request.provider is not None:
        config.provider = request.provider
    if request.base_url is not None:
        config.base_url = request.base_url
    if request.api_key is not None:
        config.api_key = request.api_key
    if request.model_name is not None:
        config.model_name = request.model_name
    if request.max_tokens is not None:
        config.max_tokens = request.max_tokens
    if request.temperature is not None:
        config.temperature = request.temperature
    if request.status is not None:
        config.status = request.status
    config.update_time = int(time.time() * 1000)
    await db.flush()
    return Response(data={"id": config.id})


@router.delete("/llm/{config_id}", response_model=Response)
async def delete_llm_config(
    config_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除 LLM 配置"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysLlmConfig.id == config_id]
    if not is_super:
        conditions.append(SysLlmConfig.tenant_id == tenant_id)

    await db.execute(delete(SysLlmConfig).where(*conditions))
    await db.flush()
    return Response(message="删除成功")


@router.post("/llm/{config_id}/test", response_model=Response)
async def test_llm_config(
    config_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """测试 LLM 连接"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysLlmConfig.id == config_id]
    if not is_super:
        conditions.append(SysLlmConfig.tenant_id == tenant_id)

    result = await db.execute(
        select(SysLlmConfig).where(*conditions)
    )
    config = result.scalar_one_or_none()
    if not config:
        return Response(code=404, message="配置不存在")

    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{config.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model_name,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5,
                },
            )
            if resp.status_code == 200:
                return Response(data={"success": True, "message": "连接成功"})
            else:
                return Response(code=400, message=f"连接失败: HTTP {resp.status_code}")
    except Exception as e:
        return Response(code=400, message=f"连接失败: {str(e)}")


@router.post("/llm/{config_id}/default", response_model=Response)
async def set_llm_default(
    config_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """设为默认 LLM 配置"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysLlmConfig.id == config_id]
    if not is_super:
        conditions.append(SysLlmConfig.tenant_id == tenant_id)

    result2 = await db.execute(
        select(SysLlmConfig).where(*conditions)
    )
    config = result2.scalar_one_or_none()
    if not config:
        return Response(code=404, message="配置不存在")

    target_tenant_id = config.tenant_id if is_super else tenant_id
    result = await db.execute(
        select(SysLlmConfig).where(
            SysLlmConfig.tenant_id == target_tenant_id,
            SysLlmConfig.is_default == 1,
        )
    )
    old_default = result.scalar_one_or_none()
    if old_default:
        old_default.is_default = 0

    config.is_default = 1
    config.update_time = int(time.time() * 1000)
    await db.flush()
    return Response(message="设置成功")


# ==================== Git 配置管理 ====================

class CreateGitConfigRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    platform: str = Field(..., min_length=1, max_length=20)
    base_url: str = Field("", max_length=255)
    access_token: str = Field(..., min_length=1)
    webhook_secret: Optional[str] = None
    ssh_key: Optional[str] = None
    status: int = 1


class UpdateGitConfigRequest(BaseModel):
    name: Optional[str] = None
    platform: Optional[str] = None
    base_url: Optional[str] = None
    access_token: Optional[str] = None
    webhook_secret: Optional[str] = None
    ssh_key: Optional[str] = None
    status: Optional[int] = None


@router.get("/git", response_model=Response)
async def list_git_configs(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
):
    """获取 Git 配置列表"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = []
    if not is_super:
        conditions.append(SysGitConfig.tenant_id == tenant_id)
    if keyword:
        conditions.append(SysGitConfig.name.ilike(f"%{keyword}%"))

    total_result = await db.execute(
        select(func.count()).select_from(SysGitConfig).where(*conditions)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(SysGitConfig)
        .where(*conditions)
        .order_by(SysGitConfig.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = result.scalars().all()

    return Response(data={
        "total": total,
        "list": [{
            "id": c.id,
            "name": c.name,
            "platform": c.platform,
            "base_url": c.base_url,
            "access_token": c.access_token[:8] + "..." if c.access_token and len(c.access_token) > 8 else c.access_token,
            "webhook_secret": c.webhook_secret,
            "is_default": c.is_default,
            "status": c.status,
            "create_time": c.create_time,
            "update_time": c.update_time,
        } for c in items],
    })


@router.get("/git/{config_id}", response_model=Response)
async def get_git_config(
    config_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取 Git 配置详情"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysGitConfig.id == config_id]
    if not is_super:
        conditions.append(SysGitConfig.tenant_id == tenant_id)

    result = await db.execute(
        select(SysGitConfig).where(*conditions)
    )
    config = result.scalar_one_or_none()
    if not config:
        return Response(code=404, message="配置不存在")
    return Response(data={
        "id": config.id,
        "name": config.name,
        "platform": config.platform,
        "base_url": config.base_url,
        "access_token": config.access_token,
        "webhook_secret": config.webhook_secret,
        "ssh_key": config.ssh_key,
        "is_default": config.is_default,
        "status": config.status,
    })


@router.post("/git", response_model=Response)
async def create_git_config(
    request: CreateGitConfigRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建 Git 配置"""
    now = int(time.time() * 1000)
    config = SysGitConfig(
        name=request.name,
        platform=request.platform,
        base_url=request.base_url,
        access_token=request.access_token,
        webhook_secret=request.webhook_secret,
        ssh_key=request.ssh_key,
        status=request.status,
        tenant_id=user.get("tenantId", 0),
        admin_id=user.get("adminId", 0),
        create_time=now,
        update_time=now,
    )
    db.add(config)
    await db.flush()
    return Response(data={"id": config.id})


@router.put("/git/{config_id}", response_model=Response)
async def update_git_config(
    config_id: int,
    request: UpdateGitConfigRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新 Git 配置"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysGitConfig.id == config_id]
    if not is_super:
        conditions.append(SysGitConfig.tenant_id == tenant_id)

    result = await db.execute(
        select(SysGitConfig).where(*conditions)
    )
    config = result.scalar_one_or_none()
    if not config:
        return Response(code=404, message="配置不存在")

    if request.name is not None:
        config.name = request.name
    if request.platform is not None:
        config.platform = request.platform
    if request.base_url is not None:
        config.base_url = request.base_url
    if request.access_token is not None:
        config.access_token = request.access_token
    if request.webhook_secret is not None:
        config.webhook_secret = request.webhook_secret
    if request.ssh_key is not None:
        config.ssh_key = request.ssh_key
    if request.status is not None:
        config.status = request.status
    config.update_time = int(time.time() * 1000)
    await db.flush()
    return Response(data={"id": config.id})


@router.delete("/git/{config_id}", response_model=Response)
async def delete_git_config(
    config_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除 Git 配置"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysGitConfig.id == config_id]
    if not is_super:
        conditions.append(SysGitConfig.tenant_id == tenant_id)

    await db.execute(delete(SysGitConfig).where(*conditions))
    await db.flush()
    return Response(message="删除成功")


@router.post("/git/{config_id}/test", response_model=Response)
async def test_git_config(
    config_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """测试 Git 连接"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysGitConfig.id == config_id]
    if not is_super:
        conditions.append(SysGitConfig.tenant_id == tenant_id)

    result = await db.execute(
        select(SysGitConfig).where(*conditions)
    )
    config = result.scalar_one_or_none()
    if not config:
        return Response(code=404, message="配置不存在")

    import httpx
    try:
        url = config.base_url.rstrip("/") + "/api/v4/user" if config.platform == "gitlab" else "https://api.github.com/user"
        headers = {"Authorization": f"token {config.access_token}"}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                return Response(data={"success": True, "message": "连接成功"})
            return Response(code=400, message=f"连接失败: HTTP {resp.status_code}")
    except Exception as e:
        return Response(code=400, message=f"连接失败: {str(e)}")


@router.post("/git/{config_id}/default", response_model=Response)
async def set_git_default(
    config_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """设为默认 Git 配置"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysGitConfig.id == config_id]
    if not is_super:
        conditions.append(SysGitConfig.tenant_id == tenant_id)

    result2 = await db.execute(
        select(SysGitConfig).where(*conditions)
    )
    config = result2.scalar_one_or_none()
    if not config:
        return Response(code=404, message="配置不存在")

    target_tenant_id = config.tenant_id if is_super else tenant_id
    result = await db.execute(
        select(SysGitConfig).where(
            SysGitConfig.tenant_id == target_tenant_id,
            SysGitConfig.is_default == 1,
        )
    )
    old_default = result.scalar_one_or_none()
    if old_default:
        old_default.is_default = 0

    config.is_default = 1
    config.update_time = int(time.time() * 1000)
    await db.flush()
    return Response(message="设置成功")


@router.get("/group/all", response_model=Response)
async def get_all_groups(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取所有角色（下拉框用）"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    conditions = [SysAdminGroup.is_deleted == 0, SysAdminGroup.status == 1]
    if not is_super:
        conditions.append(SysAdminGroup.tenant_id == tenant_id)

    stmt = (
        select(SysAdminGroup)
        .where(*conditions)
        .order_by(SysAdminGroup.create_time.desc())
    )

    result = await db.execute(stmt)
    items = result.scalars().all()

    return Response(data=[{
        "id": g.id,
        "groupName": g.name,
    } for g in items])
