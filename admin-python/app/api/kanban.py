"""看板API路由"""
import time
import uuid
from typing import Optional, List
import json

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, or_

from app.api.deps import get_db
from app.api.v1.auth import get_current_user
from app.schemas.common import Response
from app.models.task import KanbanTask, KanbanColumn, TaskComment, TaskActivity, TaskStatus

router = APIRouter(prefix="/kanban", tags=["看板管理"])


# ==================== 看板数据 ====================

@router.get("/projects/{project_id}/board", response_model=Response)
async def get_kanban_board(
    project_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取项目看板数据"""
    tenant_id = user.get("tenantId")
    
    # 获取列配置
    columns_result = await db.execute(
        select(KanbanColumn)
        .where(
            KanbanColumn.project_id == project_id,
            KanbanColumn.tenant_id == tenant_id,
            KanbanColumn.is_deleted == 0,
            KanbanColumn.is_active == 1,
        )
        .order_by(KanbanColumn.sort_order)
    )
    columns = columns_result.scalars().all()
    
    # 如果没有列配置，创建默认列
    if not columns:
        default_columns = [
            {"column_id": "todo", "name": "待办", "status": "todo", "sort_order": 0, "is_system": 1},
            {"column_id": "in_progress", "name": "进行中", "status": "in_progress", "sort_order": 1, "is_system": 1},
            {"column_id": "in_review", "name": "代码审查", "status": "in_review", "sort_order": 2, "is_system": 1},
            {"column_id": "testing", "name": "测试中", "status": "testing", "sort_order": 3, "is_system": 1},
            {"column_id": "done", "name": "已完成", "status": "done", "sort_order": 4, "is_system": 1},
        ]
        columns = []
        for col_data in default_columns:
            column = KanbanColumn(
                column_id=col_data["column_id"],
                project_id=project_id,
                name=col_data["name"],
                status=col_data["status"],
                sort_order=col_data["sort_order"],
                is_system=col_data["is_system"],
                tenant_id=tenant_id,
            )
            db.add(column)
            columns.append(column)
        await db.commit()
        for col in columns:
            await db.refresh(col)
    
    # 获取任务
    tasks_result = await db.execute(
        select(KanbanTask)
        .where(
            KanbanTask.project_id == project_id,
            KanbanTask.tenant_id == tenant_id,
            KanbanTask.is_deleted == 0,
        )
        .order_by(KanbanTask.column_id, KanbanTask.sort_order)
    )
    tasks = tasks_result.scalars().all()
    
    # 按列分组任务
    tasks_by_column = {}
    for task in tasks:
        col_id = task.column_id
        if col_id not in tasks_by_column:
            tasks_by_column[col_id] = []
        tasks_by_column[col_id].append(task.to_dict())
    
    # 组装看板数据
    board_data = {
        "columns": [col.to_dict() for col in columns],
        "tasks": tasks_by_column,
        "statistics": {
            "totalTasks": len(tasks),
            "completedTasks": sum(1 for t in tasks if t.status == TaskStatus.DONE.value),
            "inProgressTasks": sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS.value),
        }
    }
    
    return Response(data=board_data)


# ==================== 任务操作 ====================

@router.post("/tasks", response_model=Response)
async def create_kanban_task(
    project_id: int,
    title: str,
    description: Optional[str] = None,
    task_type: str = "feature",
    priority: str = "P2",
    assignee: Optional[str] = None,
    column_id: str = "todo",
    due_time: Optional[int] = None,
    tags: Optional[List[str]] = None,
    acceptance_criteria: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建看板任务"""
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
        column_id=column_id,
        status=column_id,
        due_time=due_time,
        tags=",".join(tags) if tags else None,
        acceptance_criteria=acceptance_criteria,
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


@router.put("/tasks/{task_id}/move", response_model=Response)
async def move_kanban_task(
    task_id: str,
    column_id: str,
    sort_order: Optional[int] = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """移动任务到新列"""
    tenant_id = user.get("tenantId")
    admin_id = user.get("adminId")
    
    # 获取任务
    result = await db.execute(
        select(KanbanTask)
        .where(KanbanTask.task_id == task_id, KanbanTask.tenant_id == tenant_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        return Response(code=404, message="任务不存在")
    
    old_column_id = task.column_id
    old_status = task.status
    
    # 更新任务
    update_data = {
        "column_id": column_id,
        "status": column_id,
        "update_time": int(time.time() * 1000),
    }
    if sort_order is not None:
        update_data["sort_order"] = sort_order
    
    await db.execute(
        update(KanbanTask)
        .where(KanbanTask.task_id == task_id)
        .values(**update_data)
    )
    
    # 如果移动到done列，更新完成时间
    if column_id == "done" and old_column_id != "done":
        await db.execute(
            update(KanbanTask)
            .where(KanbanTask.task_id == task_id)
            .values(end_time=int(time.time() * 1000), progress=100)
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
        new_value=column_id,
        tenant_id=tenant_id,
    )
    db.add(activity)
    await db.commit()
    
    return Response(message="任务移动成功")


@router.put("/tasks/{task_id}/assign", response_model=Response)
async def assign_kanban_task(
    task_id: str,
    assignee: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """分配任务"""
    tenant_id = user.get("tenantId")
    admin_id = user.get("adminId")
    
    result = await db.execute(
        select(KanbanTask)
        .where(KanbanTask.task_id == task_id, KanbanTask.tenant_id == tenant_id)
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


@router.put("/tasks/{task_id}/progress", response_model=Response)
async def update_task_progress(
    task_id: str,
    progress: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新任务进度"""
    tenant_id = user.get("tenantId")
    
    if progress < 0 or progress > 100:
        return Response(code=400, message="进度必须在0-100之间")
    
    result = await db.execute(
        select(KanbanTask)
        .where(KanbanTask.task_id == task_id, KanbanTask.tenant_id == tenant_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        return Response(code=404, message="任务不存在")
    
    await db.execute(
        update(KanbanTask)
        .where(KanbanTask.task_id == task_id)
        .values(progress=progress, update_time=int(time.time() * 1000))
    )
    await db.commit()
    
    return Response(message="进度更新成功")


@router.get("/tasks/{task_id}", response_model=Response)
async def get_kanban_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取任务详情"""
    tenant_id = user.get("tenantId")
    
    result = await db.execute(
        select(KanbanTask)
        .where(KanbanTask.task_id == task_id, KanbanTask.tenant_id == tenant_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        return Response(code=404, message="任务不存在")
    
    # 获取评论
    comments_result = await db.execute(
        select(TaskComment)
        .where(
            TaskComment.task_id == task_id,
            TaskComment.is_deleted == 0
        )
        .order_by(TaskComment.create_time.desc())
        .limit(20)
    )
    comments = comments_result.scalars().all()
    
    # 获取活动
    activities_result = await db.execute(
        select(TaskActivity)
        .where(TaskActivity.task_id == task_id)
        .order_by(TaskActivity.create_time.desc())
        .limit(20)
    )
    activities = activities_result.scalars().all()
    
    return Response(data={
        **task.to_dict(),
        "comments": [c.to_dict() for c in comments],
        "activities": [a.to_dict() for a in activities],
    })


@router.delete("/tasks/{task_id}", response_model=Response)
async def delete_kanban_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除任务"""
    tenant_id = user.get("tenantId")
    
    await db.execute(
        update(KanbanTask)
        .where(KanbanTask.task_id == task_id, KanbanTask.tenant_id == tenant_id)
        .values(is_deleted=1, update_time=int(time.time() * 1000))
    )
    await db.commit()
    
    return Response(message="任务删除成功")


# ==================== 评论 ====================

@router.post("/tasks/{task_id}/comments", response_model=Response)
async def add_task_comment(
    task_id: str,
    content: str,
    parent_comment_id: Optional[str] = None,
    reply_to: Optional[str] = None,
    attachments: Optional[List[str]] = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """添加任务评论"""
    tenant_id = user.get("tenantId")
    admin_id = user.get("adminId")
    
    # 获取任务以获取project_id
    result = await db.execute(
        select(KanbanTask)
        .where(KanbanTask.task_id == task_id, KanbanTask.tenant_id == tenant_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        return Response(code=404, message="任务不存在")
    
    comment = TaskComment(
        comment_id=f"cmt_{uuid.uuid4().hex[:12]}",
        task_id=task_id,
        project_id=task.project_id,
        content=content,
        author=str(admin_id),
        author_type="user",
        parent_comment_id=parent_comment_id,
        reply_to=reply_to,
        attachments=json.dumps(attachments) if attachments else None,
        tenant_id=tenant_id,
    )
    
    db.add(comment)
    
    # 更新评论数
    await db.execute(
        update(KanbanTask)
        .where(KanbanTask.task_id == task_id)
        .values(comment_count=KanbanTask.comment_count + 1)
    )
    
    # 记录活动
    activity = TaskActivity(
        activity_id=f"act_{uuid.uuid4().hex[:12]}",
        task_id=task_id,
        project_id=task.project_id,
        activity_type="commented",
        actor=str(admin_id),
        actor_type="user",
        related_id=comment.comment_id,
        tenant_id=tenant_id,
    )
    db.add(activity)
    await db.commit()
    
    return Response(data=comment.to_dict(), message="评论添加成功")


# ==================== 列管理 ====================

@router.post("/projects/{project_id}/columns", response_model=Response)
async def create_column(
    project_id: int,
    name: str,
    color: Optional[str] = None,
    wip_limit: Optional[int] = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建看板列"""
    tenant_id = user.get("tenantId")
    
    # 获取最大排序值
    result = await db.execute(
        select(func.max(KanbanColumn.sort_order))
        .where(
            KanbanColumn.project_id == project_id,
            KanbanColumn.tenant_id == tenant_id,
            KanbanColumn.is_deleted == 0,
        )
    )
    max_order = result.scalar() or 0
    
    column = KanbanColumn(
        column_id=f"col_{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        name=name,
        color=color,
        status="custom",
        wip_limit=wip_limit,
        sort_order=max_order + 1,
        is_system=0,
        tenant_id=tenant_id,
    )
    
    db.add(column)
    await db.commit()
    await db.refresh(column)
    
    return Response(data=column.to_dict(), message="列创建成功")


@router.put("/columns/{column_id}", response_model=Response)
async def update_column(
    column_id: str,
    name: Optional[str] = None,
    color: Optional[str] = None,
    wip_limit: Optional[int] = None,
    is_active: Optional[bool] = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新看板列"""
    tenant_id = user.get("tenantId")
    
    result = await db.execute(
        select(KanbanColumn)
        .where(KanbanColumn.column_id == column_id, KanbanColumn.tenant_id == tenant_id)
    )
    column = result.scalar_one_or_none()
    
    if not column:
        return Response(code=404, message="列不存在")
    
    if column.is_system:
        return Response(code=400, message="系统列不可修改")
    
    update_data = {"update_time": int(time.time() * 1000)}
    if name is not None:
        update_data["name"] = name
    if color is not None:
        update_data["color"] = color
    if wip_limit is not None:
        update_data["wip_limit"] = wip_limit
    if is_active is not None:
        update_data["is_active"] = 1 if is_active else 0
    
    await db.execute(
        update(KanbanColumn)
        .where(KanbanColumn.column_id == column_id)
        .values(**update_data)
    )
    await db.commit()
    
    return Response(message="列更新成功")


@router.delete("/columns/{column_id}", response_model=Response)
async def delete_column(
    column_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除看板列"""
    tenant_id = user.get("tenantId")
    
    result = await db.execute(
        select(KanbanColumn)
        .where(KanbanColumn.column_id == column_id, KanbanColumn.tenant_id == tenant_id)
    )
    column = result.scalar_one_or_none()
    
    if not column:
        return Response(code=404, message="列不存在")
    
    if column.is_system:
        return Response(code=400, message="系统列不可删除")
    
    # 检查是否有任务
    task_result = await db.execute(
        select(func.count())
        .select_from(KanbanTask)
        .where(
            KanbanTask.column_id == column_id,
            KanbanTask.is_deleted == 0
        )
    )
    task_count = task_result.scalar()
    
    if task_count > 0:
        return Response(code=400, message=f"该列下还有{task_count}个任务，请先移动任务")
    
    await db.execute(
        update(KanbanColumn)
        .where(KanbanColumn.column_id == column_id)
        .values(is_deleted=1, update_time=int(time.time() * 1000))
    )
    await db.commit()
    
    return Response(message="列删除成功")


@router.put("/projects/{project_id}/columns/reorder", response_model=Response)
async def reorder_columns(
    project_id: int,
    column_orders: List[dict],  # [{"columnId": "xxx", "sortOrder": 0}, ...]
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重新排序列"""
    tenant_id = user.get("tenantId")
    
    for item in column_orders:
        await db.execute(
            update(KanbanColumn)
            .where(
                KanbanColumn.column_id == item["columnId"],
                KanbanColumn.project_id == project_id,
                KanbanColumn.tenant_id == tenant_id,
            )
            .values(sort_order=item["sortOrder"], update_time=int(time.time() * 1000))
        )
    
    await db.commit()
    
    return Response(message="列排序更新成功")
