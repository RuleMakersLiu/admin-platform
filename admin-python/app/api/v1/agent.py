"""智能分身路由"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents import AgentType, agent_service
from app.api.deps import get_db
from app.api.v1.auth import get_current_user
from app.schemas.common import (
    ChatRequest,
    ChatResponse,
    CreateProjectRequest,
    CreateSessionRequest,
    CreateTaskRequest,
    CreateBugRequest,
    UpdateStatusRequest,
    Response,
    SessionItem,
    SessionListResponse,
)
from app.services.project_service import ProjectService
from app.services.task_service import TaskService
from app.services.bug_service import BugService

router = APIRouter(prefix="/agent", tags=["智能分身"])


# ==================== 对话相关 ====================


@router.post("/chat", response_model=Response)
async def chat(request: ChatRequest, user: dict = Depends(get_current_user)):
    """发送对话消息"""
    agent_type = request.agent_type or AgentType.PM

    result = await agent_service.chat(
        session_id=request.session_id,
        message=request.message,
        agent_type=agent_type,
        project_id=request.project_id,
    )

    return Response(data=ChatResponse(**result).model_dump(by_alias=True))


@router.get("/chat/sessions", response_model=Response)
async def list_sessions(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取会话列表"""
    # TODO: 从数据库获取会话列表
    sessions = []
    return Response(
        data=SessionListResponse(total=len(sessions), list=sessions).model_dump(
            by_alias=True
        )
    )


@router.post("/chat/sessions", response_model=Response)
async def create_session(
    request: CreateSessionRequest, user: dict = Depends(get_current_user)
):
    """创建新会话"""
    session_id = agent_service.create_session()

    session = SessionItem(
        session_id=session_id,
        title=request.title or "新对话",
        current_agent=AgentType.PM,
        status="active",
        create_time=int(__import__("time").time() * 1000),
    )

    return Response(data=session.model_dump(by_alias=True))


@router.get("/chat/sessions/{session_id}", response_model=Response)
async def get_session_history(session_id: str, user: dict = Depends(get_current_user)):
    """获取会话历史"""
    messages = agent_service.get_session_messages(session_id)
    return Response(data={"sessionId": session_id, "messages": messages})


@router.delete("/chat/sessions/{session_id}", response_model=Response)
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    """删除会话"""
    agent_service.delete_session(session_id)
    return Response(message="删除成功")


# ==================== 项目相关 ====================


@router.get("/projects", response_model=Response)
async def list_projects(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取项目列表"""
    admin_id = user.get("adminId")
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    filters = {}
    if status:
        filters["status"] = status
    if keyword:
        filters["keyword"] = keyword

    result = await ProjectService.list_projects(
        db=db,
        tenant_id=None if is_super else tenant_id,
        filters=filters,
        page=page,
        page_size=page_size,
    )

    return Response(
        data={
            "total": result.total,
            "list": [p.to_dict() for p in result.items],
        }
    )


@router.post("/projects", response_model=Response)
async def create_project(
    request: CreateProjectRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建项目"""
    admin_id = user.get("adminId")
    tenant_id = user.get("tenantId")

    project = await ProjectService.create_project(
        db=db,
        admin_id=admin_id,
        tenant_id=tenant_id,
        data=request.model_dump(),
    )

    return Response(data=project.to_dict())


@router.get("/projects/{project_id}", response_model=Response)
async def get_project(
    project_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取项目详情"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")
    query_tenant = None if is_super else tenant_id

    project = await ProjectService.get_project(
        db=db,
        project_id=project_id,
        tenant_id=query_tenant,
    )

    if not project:
        return Response(code=404, message="项目不存在")

    # 获取项目统计
    stats = await ProjectService.get_project_statistics(
        db=db,
        project_id=project_id,
        tenant_id=query_tenant,
    )

    return Response(data={**project.to_dict(), "statistics": stats})


@router.put("/projects/{project_id}", response_model=Response)
async def update_project(
    project_id: int,
    request: CreateProjectRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新项目"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    project = await ProjectService.update_project(
        db=db,
        project_id=project_id,
        tenant_id=None if is_super else tenant_id,
        data=request.model_dump(exclude_unset=True),
    )

    if not project:
        return Response(code=404, message="项目不存在")

    return Response(data=project.to_dict())


@router.delete("/projects/{project_id}", response_model=Response)
async def delete_project(
    project_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除项目"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    success = await ProjectService.delete_project(
        db=db,
        project_id=project_id,
        tenant_id=None if is_super else tenant_id,
    )

    if not success:
        return Response(code=404, message="项目不存在")

    return Response(message="删除成功")


# ==================== 任务相关 ====================


@router.get("/tasks", response_model=Response)
async def list_tasks(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    project_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    assignee: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取任务列表"""
    filters = {}
    if project_id:
        filters["project_id"] = project_id
    if status:
        filters["status"] = status
    if assignee:
        filters["assignee"] = assignee

    result = await TaskService.list_tasks(
        db=db,
        project_id=project_id,
        filters=filters,
        page=page,
        page_size=page_size,
    )

    return Response(
        data={
            "total": result.total,
            "list": [t.to_dict() for t in result.items],
        }
    )


@router.post("/tasks", response_model=Response)
async def create_task(
    request: CreateTaskRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建任务"""
    # Map title to task_name for the service layer
    task_data = request.model_dump(exclude={"project_id", "title"})
    task_data["task_name"] = request.title

    task = await TaskService.create_task(
        db=db,
        project_id=request.project_id,
        data=task_data,
    )

    return Response(data=task.to_dict())


@router.get("/tasks/{task_id}", response_model=Response)
async def get_task(
    task_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取任务详情"""
    task = await TaskService.get_task(db=db, task_id=task_id)

    if not task:
        return Response(code=404, message="任务不存在")

    return Response(data=task.to_dict())


@router.put("/tasks/{task_id}", response_model=Response)
async def update_task(
    task_id: int,
    request: CreateTaskRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新任务"""
    task = await TaskService.update_task(
        db=db,
        task_id=task_id,
        data=request.model_dump(exclude_unset=True, exclude={"project_id"}),
    )

    if not task:
        return Response(code=404, message="任务不存在")

    return Response(data=task.to_dict())


@router.put("/tasks/{task_id}/status", response_model=Response)
async def update_task_status(
    task_id: int,
    request: UpdateStatusRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新任务状态"""
    task = await TaskService.update_task_status(
        db=db,
        task_id=task_id,
        new_status=request.status,
        note=request.note,
    )

    if not task:
        return Response(code=404, message="任务不存在")

    return Response(data=task.to_dict())


@router.put("/tasks/{task_id}/assign", response_model=Response)
async def assign_task(
    task_id: int,
    request: UpdateStatusRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """分配任务给分身"""
    task = await TaskService.assign_task(
        db=db,
        task_id=task_id,
        agent_type=request.status,  # status字段用于传递agent_type
    )

    if not task:
        return Response(code=404, message="任务不存在")

    return Response(data=task.to_dict())


# ==================== BUG相关 ====================


@router.get("/bugs", response_model=Response)
async def list_bugs(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    project_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取BUG列表"""
    filters = {}
    if project_id:
        filters["project_id"] = project_id
    if status:
        filters["status"] = status
    if severity:
        filters["severity"] = severity

    result = await BugService.list_bugs(
        db=db,
        project_id=project_id,
        filters=filters,
        page=page,
        page_size=page_size,
    )

    return Response(
        data={
            "total": result.total,
            "list": [b.to_dict() for b in result.items],
        }
    )


@router.post("/bugs", response_model=Response)
async def create_bug(
    request: CreateBugRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建BUG"""
    # Map title to bug_title for the service layer
    bug_data = request.model_dump(exclude={"project_id", "title"})
    bug_data["bug_title"] = request.title

    bug = await BugService.create_bug(
        db=db,
        project_id=request.project_id,
        data=bug_data,
    )

    return Response(data=bug.to_dict())


@router.get("/bugs/{bug_id}", response_model=Response)
async def get_bug(
    bug_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取BUG详情"""
    bug = await BugService.get_bug(db=db, bug_id=bug_id)

    if not bug:
        return Response(code=404, message="BUG不存在")

    return Response(data=bug.to_dict())


@router.put("/bugs/{bug_id}", response_model=Response)
async def update_bug(
    bug_id: int,
    request: CreateBugRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新BUG"""
    bug = await BugService.update_bug(
        db=db,
        bug_id=bug_id,
        data=request.model_dump(exclude_unset=True, exclude={"project_id"}),
    )

    if not bug:
        return Response(code=404, message="BUG不存在")

    return Response(data=bug.to_dict())


@router.put("/bugs/{bug_id}/status", response_model=Response)
async def update_bug_status(
    bug_id: int,
    request: UpdateStatusRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新BUG状态"""
    bug = await BugService.update_bug_status(
        db=db,
        bug_id=bug_id,
        new_status=request.status,
        note=request.note,
    )

    if not bug:
        return Response(code=404, message="BUG不存在")

    return Response(data=bug.to_dict())


@router.put("/bugs/{bug_id}/resolve", response_model=Response)
async def resolve_bug(
    bug_id: int,
    request: UpdateStatusRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """解决BUG"""
    bug = await BugService.resolve_bug(
        db=db,
        bug_id=bug_id,
        resolution=request.status,  # status字段用于传递resolution
        fix_note=request.note,
    )

    if not bug:
        return Response(code=404, message="BUG不存在")

    return Response(data=bug.to_dict())


@router.delete("/tasks/{task_id}", response_model=Response)
async def delete_task(
    task_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除任务"""
    ok = await TaskService.delete_task(db=db, task_id=task_id)
    if not ok:
        return Response(code=404, message="任务不存在")
    return Response(message="删除成功")


@router.delete("/bugs/{bug_id}", response_model=Response)
async def delete_bug(
    bug_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除BUG"""
    ok = await BugService.delete_bug(db=db, bug_id=bug_id)
    if not ok:
        return Response(code=404, message="BUG不存在")
    return Response(message="删除成功")


@router.get("/projects/{project_id}/statistics", response_model=Response)
async def get_project_statistics(
    project_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取项目统计"""
    tenant_id = user.get("tenantId")
    is_super = user.get("isSuper")

    stats = await ProjectService.get_project_statistics(
        db=db,
        project_id=project_id,
        tenant_id=None if is_super else tenant_id,
    )

    return Response(data=stats)
