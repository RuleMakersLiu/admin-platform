"""任务管理API路由"""
import time
import uuid
import json
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, or_

from app.api.deps import get_db
from app.api.v1.auth import get_current_user
from app.schemas.common import Response
from app.models.task import KanbanTask, TaskActivity, TaskStatus, TaskPriority, TaskType
from app.models.agent import AgentWorkLog

router = APIRouter(prefix="/tasks", tags=["任务管理"])


# ==================== 任务CRUD ====================

@router.get("", response_model=Response)
async def list_tasks(
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    task_type: Optional[str] = None,
    assignee: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取任务列表"""
    tenant_id = user.get("tenantId")
    
    query = select(KanbanTask).where(
        KanbanTask.tenant_id == tenant_id,
        KanbanTask.is_deleted == 0,
    )
    
    if project_id:
        query = query.where(KanbanTask.project_id == project_id)
    if status:
        query = query.where(KanbanTask.status == status)
    if priority:
        query = query.where(KanbanTask.priority == priority)
    if task_type:
        query = query.where(KanbanTask.task_type == task_type)
    if assignee:
        query = query.where(KanbanTask.assignee == assignee)
    if keyword:
        query = query.where(
            or_(
                KanbanTask.title.ilike(f"%{keyword}%"),
                KanbanTask.description.ilike(f"%{keyword}%"),
            )
        )
    
    # 获取总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()
    
    # 分页
    query = query.order_by(KanbanTask.priority, KanbanTask.create_time.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    return Response(data={
        "total": total,
        "page": page,
        "pageSize": page_size,
        "list": [task.to_dict() for task in tasks],
    })


@router.post("", response_model=Response)
async def create_task(
    project_id: int = Body(...),
    title: str = Body(...),
    description: Optional[str] = Body(None),
    task_type: str = Body("feature"),
    priority: str = Body("P2"),
    assignee: Optional[str] = Body(None),
    due_time: Optional[int] = Body(None),
    tags: Optional[List[str]] = Body(None),
    acceptance_criteria: Optional[str] = Body(None),
    dependencies: Optional[List[str]] = Body(None),
    estimated_hours: Optional[float] = Body(None),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建任务"""
    tenant_id = user.get("tenantId")
    admin_id = user.get("adminId")
    
    task = KanbanTask(
        task_id=f"task_{uuid.uuid4().hex[:12]}",
        project_id=project_id,
        title=title,
        description=description,
        task_type=task_type,
        priority=priority,
        assignee=assignee,
        reporter=str(admin_id),
        column_id="todo",
        status=TaskStatus.TODO.value,
        due_time=due_time,
        tags=",".join(tags) if tags else None,
        acceptance_criteria=acceptance_criteria,
        dependencies=json.dumps(dependencies) if dependencies else None,
        estimated_hours=estimated_hours,
        tenant_id=tenant_id,
    )
    
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    # 记录活动
    activity = TaskActivity(
        activity_id=f"act_{uuid.uuid4().hex[:12]}",
        task_id=task.task_id,
        project_id=project_id,
        activity_type="created",
        actor=str(admin_id),
        actor_type="user",
        new_value=title,
        tenant_id=tenant_id,
    )
    db.add(activity)
    await db.commit()
    
    return Response(data=task.to_dict(), message="任务创建成功")


@router.get("/{task_id}", response_model=Response)
async def get_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取任务详情"""
    tenant_id = user.get("tenantId")
    
    result = await db.execute(
        select(KanbanTask)
        .where(
            KanbanTask.task_id == task_id,
            KanbanTask.tenant_id == tenant_id,
            KanbanTask.is_deleted == 0,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        return Response(code=404, message="任务不存在")
    
    task_dict = task.to_dict()
    
    # 获取活动历史
    activities_result = await db.execute(
        select(TaskActivity)
        .where(TaskActivity.task_id == task_id)
        .order_by(TaskActivity.create_time.desc())
        .limit(50)
    )
    task_dict["activities"] = [a.to_dict() for a in activities_result.scalars().all()]
    
    return Response(data=task_dict)


@router.put("/{task_id}", response_model=Response)
async def update_task(
    task_id: str,
    title: Optional[str] = Body(None),
    description: Optional[str] = Body(None),
    task_type: Optional[str] = Body(None),
    priority: Optional[str] = Body(None),
    assignee: Optional[str] = Body(None),
    due_time: Optional[int] = Body(None),
    tags: Optional[List[str]] = Body(None),
    acceptance_criteria: Optional[str] = Body(None),
    estimated_hours: Optional[float] = Body(None),
    actual_hours: Optional[float] = Body(None),
    progress: Optional[int] = Body(None),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新任务"""
    tenant_id = user.get("tenantId")
    admin_id = user.get("adminId")
    
    result = await db.execute(
        select(KanbanTask)
        .where(
            KanbanTask.task_id == task_id,
            KanbanTask.tenant_id == tenant_id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        return Response(code=404, message="任务不存在")
    
    # 构建更新数据
    update_data = {"update_time": int(time.time() * 1000)}
    changes = []
    
    if title is not None and title != task.title:
        changes.append(("title", task.title, title))
        update_data["title"] = title
    if description is not None and description != task.description:
        changes.append(("description", task.description, description))
        update_data["description"] = description
    if task_type is not None and task_type != task.task_type:
        changes.append(("task_type", task.task_type, task_type))
        update_data["task_type"] = task_type
    if priority is not None and priority != task.priority:
        changes.append(("priority", task.priority, priority))
        update_data["priority"] = priority
    if assignee is not None and assignee != task.assignee:
        changes.append(("assignee", task.assignee, assignee))
        update_data["assignee"] = assignee
    if due_time is not None and due_time != task.due_time:
        changes.append(("due_time", task.due_time, due_time))
        update_data["due_time"] = due_time
    if tags is not None:
        new_tags = ",".join(tags) if tags else None
        if new_tags != task.tags:
            changes.append(("tags", task.tags, new_tags))
            update_data["tags"] = new_tags
    if acceptance_criteria is not None and acceptance_criteria != task.acceptance_criteria:
        changes.append(("acceptance_criteria", task.acceptance_criteria, acceptance_criteria))
        update_data["acceptance_criteria"] = acceptance_criteria
    if estimated_hours is not None:
        update_data["estimated_hours"] = estimated_hours
    if actual_hours is not None:
        update_data["actual_hours"] = actual_hours
    if progress is not None:
        if 0 <= progress <= 100:
            update_data["progress"] = progress
    
    if not update_data:
        return Response(data=task.to_dict(), message="没有需要更新的内容")
    
    await db.execute(
        update(KanbanTask)
        .where(KanbanTask.task_id == task_id)
        .values(**update_data)
    )
    
    # 记录活动
    for field_name, old_value, new_value in changes:
        activity = TaskActivity(
            activity_id=f"act_{uuid.uuid4().hex[:12]}",
            task_id=task_id,
            project_id=task.project_id,
            activity_type="updated",
            actor=str(admin_id),
            actor_type="user",
            field_name=field_name,
            old_value=str(old_value) if old_value else None,
            new_value=str(new_value) if new_value else None,
            tenant_id=tenant_id,
        )
        db.add(activity)
    
    await db.commit()
    
    # 获取更新后的任务
    await db.refresh(task)
    
    return Response(data=task.to_dict(), message="任务更新成功")


@router.delete("/{task_id}", response_model=Response)
async def delete_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除任务"""
    tenant_id = user.get("tenantId")
    admin_id = user.get("adminId")
    
    result = await db.execute(
        select(KanbanTask)
        .where(
            KanbanTask.task_id == task_id,
            KanbanTask.tenant_id == tenant_id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        return Response(code=404, message="任务不存在")
    
    await db.execute(
        update(KanbanTask)
        .where(KanbanTask.task_id == task_id)
        .values(is_deleted=1, update_time=int(time.time() * 1000))
    )
    
    # 记录活动
    activity = TaskActivity(
        activity_id=f"act_{uuid.uuid4().hex[:12]}",
        task_id=task_id,
        project_id=task.project_id,
        activity_type="deleted",
        actor=str(admin_id),
        actor_type="user",
        tenant_id=tenant_id,
    )
    db.add(activity)
    await db.commit()
    
    return Response(message="任务删除成功")


# ==================== 任务状态变更 ====================

@router.put("/{task_id}/status", response_model=Response)
async def update_task_status(
    task_id: str,
    status: str = Body(...),
    note: Optional[str] = Body(None),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新任务状态"""
    tenant_id = user.get("tenantId")
    admin_id = user.get("adminId")
    
    result = await db.execute(
        select(KanbanTask)
        .where(
            KanbanTask.task_id == task_id,
            KanbanTask.tenant_id == tenant_id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        return Response(code=404, message="任务不存在")
    
    old_status = task.status
    old_column_id = task.column_id
    
    update_data = {
        "status": status,
        "column_id": status,
        "update_time": int(time.time() * 1000),
    }
    
    # 如果完成，设置结束时间和进度100%
    if status == TaskStatus.DONE.value and old_status != TaskStatus.DONE.value:
        update_data["end_time"] = int(time.time() * 1000)
        update_data["progress"] = 100
    
    # 如果开始进行，设置开始时间
    if status == TaskStatus.IN_PROGRESS.value and old_status == TaskStatus.TODO.value:
        update_data["start_time"] = int(time.time() * 1000)
    
    await db.execute(
        update(KanbanTask)
        .where(KanbanTask.task_id == task_id)
        .values(**update_data)
    )
    
    # 记录活动
    activity = TaskActivity(
        activity_id=f"act_{uuid.uuid4().hex[:12]}",
        task_id=task_id,
        project_id=task.project_id,
        activity_type="status_changed",
        actor=str(admin_id),
        actor_type="user",
        field_name="status",
        old_value=old_status,
        new_value=status,
        tenant_id=tenant_id,
    )
    db.add(activity)
    await db.commit()
    
    return Response(message="状态更新成功")


@router.put("/{task_id}/assign", response_model=Response)
async def assign_task(
    task_id: str,
    assignee: str = Body(...),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """分配任务"""
    tenant_id = user.get("tenantId")
    admin_id = user.get("adminId")
    
    result = await db.execute(
        select(KanbanTask)
        .where(
            KanbanTask.task_id == task_id,
            KanbanTask.tenant_id == tenant_id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        return Response(code=404, message="任务不存在")
    
    old_assignee = task.assignee
    
    await db.execute(
        update(KanbanTask)
        .where(KanbanTask.task_id == task_id)
        .values(assignee=assignee, update_time=int(time.time() * 1000))
    )
    
    # 记录活动
    activity = TaskActivity(
        activity_id=f"act_{uuid.uuid4().hex[:12]}",
        task_id=task_id,
        project_id=task.project_id,
        activity_type="assigned",
        actor=str(admin_id),
        actor_type="user",
        field_name="assignee",
        old_value=old_assignee,
        new_value=assignee,
        tenant_id=tenant_id,
    )
    db.add(activity)
    await db.commit()
    
    return Response(message="任务分配成功")


# ==================== 任务统计 ====================

@router.get("/project/{project_id}/statistics", response_model=Response)
async def get_task_statistics(
    project_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取项目任务统计"""
    tenant_id = user.get("tenantId")
    
    # 总数和各状态统计
    result = await db.execute(
        select(
            KanbanTask.status,
            func.count().label("count")
        )
        .where(
            KanbanTask.project_id == project_id,
            KanbanTask.tenant_id == tenant_id,
            KanbanTask.is_deleted == 0,
        )
        .group_by(KanbanTask.status)
    )
    status_counts = {row.status: row.count for row in result.all()}
    
    # 按类型统计
    type_result = await db.execute(
        select(
            KanbanTask.task_type,
            func.count().label("count")
        )
        .where(
            KanbanTask.project_id == project_id,
            KanbanTask.tenant_id == tenant_id,
            KanbanTask.is_deleted == 0,
        )
        .group_by(KanbanTask.task_type)
    )
    type_counts = {row.task_type: row.count for row in type_result.all()}
    
    # 按优先级统计
    priority_result = await db.execute(
        select(
            KanbanTask.priority,
            func.count().label("count")
        )
        .where(
            KanbanTask.project_id == project_id,
            KanbanTask.tenant_id == tenant_id,
            KanbanTask.is_deleted == 0,
        )
        .group_by(KanbanTask.priority)
    )
    priority_counts = {row.priority: row.count for row in priority_result.all()}
    
    # 按分配者统计
    assignee_result = await db.execute(
        select(
            KanbanTask.assignee,
            func.count().label("count")
        )
        .where(
            KanbanTask.project_id == project_id,
            KanbanTask.tenant_id == tenant_id,
            KanbanTask.is_deleted == 0,
        )
        .group_by(KanbanTask.assignee)
    )
    assignee_counts = {row.assignee: row.count for row in assignee_result.all() if row.assignee}
    
    total = sum(status_counts.values())
    
    return Response(data={
        "total": total,
        "byStatus": status_counts,
        "byType": type_counts,
        "byPriority": priority_counts,
        "byAssignee": assignee_counts,
        "completionRate": round(status_counts.get(TaskStatus.DONE.value, 0) / total * 100, 1) if total > 0 else 0,
    })


# ==================== 批量操作 ====================

@router.post("/batch/status", response_model=Response)
async def batch_update_status(
    task_ids: List[str] = Body(...),
    status: str = Body(...),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量更新任务状态"""
    tenant_id = user.get("tenantId")
    admin_id = user.get("adminId")
    
    await db.execute(
        update(KanbanTask)
        .where(
            KanbanTask.task_id.in_(task_ids),
            KanbanTask.tenant_id == tenant_id,
        )
        .values(
            status=status,
            column_id=status,
            update_time=int(time.time() * 1000),
        )
    )
    
    # 记录活动
    for task_id in task_ids:
        activity = TaskActivity(
            activity_id=f"act_{uuid.uuid4().hex[:12]}",
            task_id=task_id,
            activity_type="status_changed",
            actor=str(admin_id),
            actor_type="user",
            field_name="status",
            new_value=status,
            tenant_id=tenant_id,
        )
        db.add(activity)
    
    await db.commit()
    
    return Response(message=f"成功更新{len(task_ids)}个任务状态")


@router.post("/batch/assign", response_model=Response)
async def batch_assign(
    task_ids: List[str] = Body(...),
    assignee: str = Body(...),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量分配任务"""
    tenant_id = user.get("tenantId")
    admin_id = user.get("adminId")
    
    await db.execute(
        update(KanbanTask)
        .where(
            KanbanTask.task_id.in_(task_ids),
            KanbanTask.tenant_id == tenant_id,
        )
        .values(
            assignee=assignee,
            update_time=int(time.time() * 1000),
        )
    )
    
    # 记录活动
    for task_id in task_ids:
        activity = TaskActivity(
            activity_id=f"act_{uuid.uuid4().hex[:12]}",
            task_id=task_id,
            activity_type="assigned",
            actor=str(admin_id),
            actor_type="user",
            field_name="assignee",
            new_value=assignee,
            tenant_id=tenant_id,
        )
        db.add(activity)
    
    await db.commit()
    
    return Response(message=f"成功分配{len(task_ids)}个任务")


# ==================== 任务依赖 ====================

@router.get("/{task_id}/dependencies", response_model=Response)
async def get_task_dependencies(
    task_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取任务依赖"""
    tenant_id = user.get("tenantId")
    
    result = await db.execute(
        select(KanbanTask)
        .where(
            KanbanTask.task_id == task_id,
            KanbanTask.tenant_id == tenant_id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task or not task.dependencies:
        return Response(data={"dependencies": []})
    
    dep_ids = json.loads(task.dependencies)
    
    # 获取依赖任务详情
    dep_result = await db.execute(
        select(KanbanTask)
        .where(KanbanTask.task_id.in_(dep_ids))
    )
    dep_tasks = dep_result.scalars().all()
    
    return Response(data={
        "dependencies": [t.to_dict() for t in dep_tasks],
    })


@router.post("/{task_id}/dependencies", response_model=Response)
async def add_task_dependency(
    task_id: str,
    depends_on_task_id: str = Body(..., embed=True),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """添加任务依赖"""
    tenant_id = user.get("tenantId")
    
    result = await db.execute(
        select(KanbanTask)
        .where(
            KanbanTask.task_id == task_id,
            KanbanTask.tenant_id == tenant_id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        return Response(code=404, message="任务不存在")
    
    # 获取当前依赖
    current_deps = json.loads(task.dependencies) if task.dependencies else []
    
    if depends_on_task_id in current_deps:
        return Response(code=400, message="该依赖已存在")
    
    # 检查是否会造成循环依赖
    if depends_on_task_id == task_id:
        return Response(code=400, message="不能依赖自身")
    
    current_deps.append(depends_on_task_id)
    
    await db.execute(
        update(KanbanTask)
        .where(KanbanTask.task_id == task_id)
        .values(
            dependencies=json.dumps(current_deps),
            update_time=int(time.time() * 1000),
        )
    )
    await db.commit()
    
    return Response(message="依赖添加成功")


@router.delete("/{task_id}/dependencies/{depends_on_task_id}", response_model=Response)
async def remove_task_dependency(
    task_id: str,
    depends_on_task_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """移除任务依赖"""
    tenant_id = user.get("tenantId")
    
    result = await db.execute(
        select(KanbanTask)
        .where(
            KanbanTask.task_id == task_id,
            KanbanTask.tenant_id == tenant_id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task or not task.dependencies:
        return Response(code=404, message="依赖不存在")
    
    current_deps = json.loads(task.dependencies)
    
    if depends_on_task_id not in current_deps:
        return Response(code=404, message="依赖不存在")
    
    current_deps.remove(depends_on_task_id)
    
    await db.execute(
        update(KanbanTask)
        .where(KanbanTask.task_id == task_id)
        .values(
            dependencies=json.dumps(current_deps) if current_deps else None,
            update_time=int(time.time() * 1000),
        )
    )
    await db.commit()
    
    return Response(message="依赖移除成功")
