"""认证路由"""
from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.schemas.common import LoginRequest, LoginResponse, Response, UserInfo
from app.services.auth import AuthService
from app.models.models import SysTenant, SysMenu, SysAdminGroup

router = APIRouter(prefix="/auth", tags=["认证"])
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """获取当前用户"""
    token = credentials.credentials
    payload = AuthService.verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证令牌无效或已过期",
        )
    return payload


@router.get("/tenants", response_model=Response)
async def get_tenants(db: AsyncSession = Depends(get_db)):
    """获取租户列表（公开接口，用于登录页）"""
    stmt = select(SysTenant).where(SysTenant.status == 1).order_by(SysTenant.id)
    result = await db.execute(stmt)
    tenants = result.scalars().all()

    return Response(data=[
        {"id": t.id, "name": t.name, "code": t.code}
        for t in tenants
    ])


@router.post("/login", response_model=Response)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """用户登录"""
    result = await AuthService.login(
        db, request.username, request.password, request.tenant_id
    )
    if not result:
        return Response(code=401, message="用户名或密码错误")

    return Response(data=result.model_dump(by_alias=True))


@router.post("/logout", response_model=Response)
async def logout():
    """用户登出"""
    # JWT无状态，客户端删除Token即可
    return Response(message="登出成功")


@router.get("/info", response_model=Response)
async def get_info(
    user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """获取用户信息"""
    admin_id = user.get("adminId")
    info = await AuthService.get_user_info(db, admin_id)
    if not info:
        raise HTTPException(status_code=404, detail="用户不存在")

    return Response(data=info.model_dump(by_alias=True))


def build_menu_tree(menus: List[SysMenu]) -> List[dict]:
    """构建菜单树结构"""
    # 按父ID分组
    menu_map = {}
    children_map = {}

    for menu in menus:
        menu_dict = {
            "id": menu.id,
            "menuName": menu.name,
            "menuType": menu.menu_type,
            "path": menu.path,
            "icon": menu.icon,
            "permission": menu.permission,
            "sort": menu.sort,
            "children": []
        }
        menu_map[menu.id] = menu_dict

        if menu.parent_id not in children_map:
            children_map[menu.parent_id] = []
        children_map[menu.parent_id].append(menu.id)

    # 构建树结构
    root_menus = []

    def add_children(parent_id: int, parent_dict: dict):
        """递归添加子菜单"""
        if parent_id in children_map:
            child_ids = sorted(children_map[parent_id], key=lambda x: menu_map[x]["sort"])
            for child_id in child_ids:
                child_dict = menu_map[child_id]
                parent_dict["children"].append(child_dict)
                add_children(child_id, child_dict)

    # 获取根菜单 (parent_id = 0)
    if 0 in children_map:
        root_ids = sorted(children_map[0], key=lambda x: menu_map[x]["sort"])
        for root_id in root_ids:
            root_dict = menu_map[root_id]
            add_children(root_id, root_dict)
            root_menus.append(root_dict)

    return root_menus


@router.get("/menus", response_model=Response)
async def get_menus(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户菜单 - 从数据库读取"""
    admin_id = user.get("adminId")

    # 获取用户所属组信息
    from app.models.models import SysAdmin
    admin_stmt = select(SysAdmin).where(SysAdmin.id == admin_id)
    admin_result = await db.execute(admin_stmt)
    admin = admin_result.scalar_one_or_none()

    if not admin:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 获取用户组
    group_stmt = select(SysAdminGroup).where(SysAdminGroup.id == admin.admin_group_id)
    group_result = await db.execute(group_stmt)
    group = group_result.scalar_one_or_none()

    # 查询所有启用的菜单
    menu_stmt = select(SysMenu).where(
        SysMenu.status == 1,
        SysMenu.is_deleted == 0 if hasattr(SysMenu, 'is_deleted') else True
    ).order_by(SysMenu.sort)
    menu_result = await db.execute(menu_stmt)
    all_menus = menu_result.scalars().all()

    # 如果是超级管理员，返回所有菜单
    if group and group.is_super == 1:
        menus = build_menu_tree(all_menus)
        return Response(data=menus)

    # 否则根据权限过滤菜单
    import json
    permissions = []
    if group and group.power:
        try:
            permissions = json.loads(group.power) if isinstance(group.power, str) else group.power
        except json.JSONDecodeError:
            permissions = []

    # 过滤菜单: 目录类型(1)总是显示，菜单类型(2)需要权限
    filtered_menus = []
    for menu in all_menus:
        # 目录类型直接显示
        if menu.menu_type == 1:
            filtered_menus.append(menu)
        # 菜单类型检查权限
        elif menu.menu_type == 2 and menu.permission in permissions:
            filtered_menus.append(menu)

    menus = build_menu_tree(filtered_menus)
    return Response(data=menus)
