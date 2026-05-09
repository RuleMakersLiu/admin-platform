"""智能体状态API路由"""
import time
import uuid
import json
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, or_

from app.api.deps import get_db
from app.api.v1.auth import get_current_user
from app.schemas.common import Response
from app.models.agent import (
    AgentInfo, AgentStatus, AgentHeartbeat, AgentWorkLog,
    AgentWorkStatus
)

router = APIRouter(prefix="/agents", tags=["智能体状态"])


# ==================== 智能体信息 ====================

@router.get("", response_model=Response)
async def list_agents(
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    agent_type: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取智能体列表"""
    tenant_id = user.get("tenantId")
    
    query = select(AgentInfo).where(
        AgentInfo.tenant_id == tenant_id,
        AgentInfo.is_deleted == 0,
    )
    
    if agent_type:
        query = query.where(AgentInfo.agent_type == agent_type)
    if status:
        query = query.where(AgentInfo.status == status)
    
    query = query.order_by(AgentInfo.agent_type, AgentInfo.create_time)
    
    result = await db.execute(query)
    agents = result.scalars().all()
    
    # 获取每个智能体的实时状态
    agents_data = []
    for agent in agents:
        agent_dict = agent.to_dict()
        
        # 获取实时状态
        status_result = await db.execute(
            select(AgentStatus)
            .where(AgentStatus.agent_id == agent.agent_id)
            .order_by(AgentStatus.update_time.desc())
            .limit(1)
        )
        latest_status = status_result.scalar_one_or_none()
        
        if latest_status:
            agent_dict["currentStatus"] = latest_status.to_dict()
        else:
            agent_dict["currentStatus"] = None
        
        agents_data.append(agent_dict)
    
    return Response(data={
        "total": len(agents_data),
        "list": agents_data,
    })


@router.get("/{agent_id}", response_model=Response)
async def get_agent(
    agent_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取智能体详情"""
    tenant_id = user.get("tenantId")
    
    result = await db.execute(
        select(AgentInfo)
        .where(
            AgentInfo.agent_id == agent_id,
            AgentInfo.tenant_id == tenant_id,
        )
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        return Response(code=404, message="智能体不存在")
    
    agent_dict = agent.to_dict()
    
    # 获取实时状态
    status_result = await db.execute(
        select(AgentStatus)
        .where(AgentStatus.agent_id == agent_id)
        .order_by(AgentStatus.update_time.desc())
        .limit(1)
    )
    agent_dict["currentStatus"] = status_result.scalar_one_or_none()
    
    # 获取最近工作日志
    logs_result = await db.execute(
        select(AgentWorkLog)
        .where(AgentWorkLog.agent_id == agent_id)
        .order_by(AgentWorkLog.create_time.desc())
        .limit(10)
    )
    agent_dict["recentLogs"] = [log.to_dict() for log in logs_result.scalars().all()]
    
    return Response(data=agent_dict)


@router.get("/types/overview", response_model=Response)
async def get_agent_types_overview(
    project_id: Optional[int] = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取各类型智能体概览"""
    tenant_id = user.get("tenantId")
    
    # 定义智能体类型
    agent_types = ["PM", "PJM", "BE", "FE", "QA", "RPT"]
    
    overview = []
    for agent_type in agent_types:
        # 获取该类型的智能体信息
        result = await db.execute(
            select(AgentInfo)
            .where(
                AgentInfo.agent_type == agent_type,
                AgentInfo.tenant_id == tenant_id,
                AgentInfo.is_deleted == 0,
            )
        )
        agents = result.scalars().all()
        
        type_data = {
            "agentType": agent_type,
            "name": get_agent_type_name(agent_type),
            "totalAgents": len(agents),
            "idleAgents": 0,
            "workingAgents": 0,
            "errorAgents": 0,
            "offlineAgents": 0,
            "agents": [],
        }
        
        for agent in agents:
            # 获取状态
            status_result = await db.execute(
                select(AgentStatus)
                .where(AgentStatus.agent_id == agent.agent_id)
                .order_by(AgentStatus.update_time.desc())
                .limit(1)
            )
            latest_status = status_result.scalar_one_or_none()
            
            work_status = latest_status.work_status if latest_status else AgentWorkStatus.OFFLINE.value
            
            if work_status == AgentWorkStatus.IDLE.value:
                type_data["idleAgents"] += 1
            elif work_status == AgentWorkStatus.WORKING.value:
                type_data["workingAgents"] += 1
            elif work_status == AgentWorkStatus.ERROR.value:
                type_data["errorAgents"] += 1
            else:
                type_data["offlineAgents"] += 1
            
            type_data["agents"].append({
                "agentId": agent.agent_id,
                "name": agent.name,
                "status": work_status,
                "currentTaskId": latest_status.current_task_id if latest_status else None,
                "progress": latest_status.progress if latest_status else 0,
            })
        
        overview.append(type_data)
    
    return Response(data=overview)


def get_agent_type_name(agent_type: str) -> str:
    """获取智能体类型名称"""
    names = {
        "PM": "产品经理",
        "PJM": "项目经理",
        "BE": "后端开发",
        "FE": "前端开发",
        "QA": "测试分身",
        "RPT": "汇报分身",
    }
    return names.get(agent_type, agent_type)


# ==================== 状态管理 ====================

@router.get("/{agent_id}/status", response_model=Response)
async def get_agent_status(
    agent_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取智能体实时状态"""
    tenant_id = user.get("tenantId")
    
    result = await db.execute(
        select(AgentStatus)
        .where(AgentStatus.agent_id == agent_id)
        .order_by(AgentStatus.update_time.desc())
        .limit(1)
    )
    status = result.scalar_one_or_none()
    
    if not status:
        return Response(code=404, message="状态不存在")
    
    return Response(data=status.to_dict())


@router.put("/{agent_id}/status", response_model=Response)
async def update_agent_status(
    agent_id: str,
    work_status: str,
    current_task_id: Optional[str] = None,
    current_action: Optional[str] = None,
    progress: Optional[int] = None,
    progress_message: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新智能体状态"""
    tenant_id = user.get("tenantId")
    
    result = await db.execute(
        select(AgentStatus)
        .where(AgentStatus.agent_id == agent_id)
        .order_by(AgentStatus.update_time.desc())
        .limit(1)
    )
    status = result.scalar_one_or_none()
    
    if not status:
        # 创建新状态记录
        # 先获取agent信息
        agent_result = await db.execute(
            select(AgentInfo).where(AgentInfo.agent_id == agent_id)
        )
        agent = agent_result.scalar_one_or_none()
        
        status = AgentStatus(
            status_id=f"st_{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            agent_type=agent.agent_type if agent else "UNKNOWN",
            work_status=work_status,
            current_task_id=current_task_id,
            current_action=current_action,
            progress=progress or 0,
            progress_message=progress_message,
            tenant_id=tenant_id,
        )
        db.add(status)
    else:
        # 更新状态
        update_data = {
            "work_status": work_status,
            "update_time": int(time.time() * 1000),
        }
        if current_task_id is not None:
            update_data["current_task_id"] = current_task_id
        if current_action is not None:
            update_data["current_action"] = current_action
        if progress is not None:
            update_data["progress"] = progress
        if progress_message is not None:
            update_data["progress_message"] = progress_message
        
        await db.execute(
            update(AgentStatus)
            .where(AgentStatus.status_id == status.status_id)
            .values(**update_data)
        )
    
    await db.commit()
    
    return Response(message="状态更新成功")


@router.post("/{agent_id}/heartbeat", response_model=Response)
async def agent_heartbeat(
    agent_id: str,
    status: str,
    current_task_id: Optional[str] = None,
    cpu_usage: Optional[float] = None,
    memory_usage: Optional[float] = None,
    extra_data: Optional[dict] = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """智能体心跳"""
    tenant_id = user.get("tenantId")
    
    # 获取agent信息
    agent_result = await db.execute(
        select(AgentInfo).where(AgentInfo.agent_id == agent_id)
    )
    agent = agent_result.scalar_one_or_none()
    
    # 记录心跳
    heartbeat = AgentHeartbeat(
        heartbeat_id=f"hb_{uuid.uuid4().hex[:12]}",
        agent_id=agent_id,
        agent_type=agent.agent_type if agent else "UNKNOWN",
        status=status,
        current_task_id=current_task_id,
        cpu_usage=cpu_usage,
        memory_usage=memory_usage,
        extra_data=json.dumps(extra_data) if extra_data else None,
        tenant_id=tenant_id,
    )
    db.add(heartbeat)
    
    # 更新实时状态
    status_result = await db.execute(
        select(AgentStatus)
        .where(AgentStatus.agent_id == agent_id)
        .order_by(AgentStatus.update_time.desc())
        .limit(1)
    )
    agent_status = status_result.scalar_one_or_none()
    
    if agent_status:
        await db.execute(
            update(AgentStatus)
            .where(AgentStatus.status_id == agent_status.status_id)
            .values(
                work_status=status,
                current_task_id=current_task_id,
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                last_heartbeat=int(time.time() * 1000),
                update_time=int(time.time() * 1000),
            )
        )
    else:
        new_status = AgentStatus(
            status_id=f"st_{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            agent_type=agent.agent_type if agent else "UNKNOWN",
            work_status=status,
            current_task_id=current_task_id,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            tenant_id=tenant_id,
        )
        db.add(new_status)
    
    await db.commit()
    
    return Response(message="心跳记录成功")


# ==================== 工作日志 ====================

@router.get("/{agent_id}/logs", response_model=Response)
async def get_agent_work_logs(
    agent_id: str,
    project_id: Optional[int] = None,
    task_id: Optional[str] = None,
    action: Optional[str] = None,
    level: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取智能体工作日志"""
    tenant_id = user.get("tenantId")
    
    query = select(AgentWorkLog).where(AgentWorkLog.agent_id == agent_id)
    
    if project_id:
        query = query.where(AgentWorkLog.project_id == project_id)
    if task_id:
        query = query.where(AgentWorkLog.task_id == task_id)
    if action:
        query = query.where(AgentWorkLog.action == action)
    if level:
        query = query.where(AgentWorkLog.level == level)
    
    # 获取总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()
    
    # 分页
    query = query.order_by(AgentWorkLog.create_time.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    logs = result.scalars().all()
    
    return Response(data={
        "total": total,
        "page": page,
        "pageSize": page_size,
        "list": [log.to_dict() for log in logs],
    })


@router.post("/{agent_id}/logs", response_model=Response)
async def create_agent_work_log(
    agent_id: str,
    action: str,
    message: str,
    project_id: Optional[int] = None,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    level: str = "info",
    input_data: Optional[dict] = None,
    output_data: Optional[dict] = None,
    duration_ms: Optional[int] = None,
    token_count: Optional[int] = None,
    model_used: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建工作日志"""
    tenant_id = user.get("tenantId")
    
    # 获取agent信息
    agent_result = await db.execute(
        select(AgentInfo).where(AgentInfo.agent_id == agent_id)
    )
    agent = agent_result.scalar_one_or_none()
    
    log = AgentWorkLog(
        log_id=f"log_{uuid.uuid4().hex[:12]}",
        agent_id=agent_id,
        agent_type=agent.agent_type if agent else "UNKNOWN",
        project_id=project_id,
        session_id=session_id,
        task_id=task_id,
        action=action,
        level=level,
        message=message,
        input_data=json.dumps(input_data) if input_data else None,
        output_data=json.dumps(output_data) if output_data else None,
        duration_ms=duration_ms,
        token_count=token_count,
        model_used=model_used,
        tenant_id=tenant_id,
    )
    
    db.add(log)
    await db.commit()
    
    return Response(data=log.to_dict(), message="日志创建成功")


# ==================== 批量状态查询 ====================

@router.post("/batch/status", response_model=Response)
async def get_batch_agent_status(
    agent_ids: List[str],
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量获取智能体状态"""
    tenant_id = user.get("tenantId")
    
    result = await db.execute(
        select(AgentStatus)
        .where(AgentStatus.agent_id.in_(agent_ids))
        .order_by(AgentStatus.update_time.desc())
    )
    statuses = result.scalars().all()
    
    # 按agent_id分组，取最新的
    status_map = {}
    for status in statuses:
        if status.agent_id not in status_map:
            status_map[status.agent_id] = status.to_dict()
    
    return Response(data=status_map)


@router.get("/project/{project_id}/status", response_model=Response)
async def get_project_agents_status(
    project_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取项目相关智能体状态"""
    tenant_id = user.get("tenantId")
    
    # 获取项目相关的智能体状态
    result = await db.execute(
        select(AgentStatus)
        .where(AgentStatus.project_id == project_id)
        .order_by(AgentStatus.agent_type, AgentStatus.update_time.desc())
    )
    statuses = result.scalars().all()
    
    # 按类型分组
    status_by_type = {}
    for status in statuses:
        if status.agent_type not in status_by_type:
            status_by_type[status.agent_type] = []
        status_by_type[status.agent_type].append(status.to_dict())
    
    # 获取统计
    stats = {
        "total": len(statuses),
        "working": sum(1 for s in statuses if s.work_status == AgentWorkStatus.WORKING.value),
        "idle": sum(1 for s in statuses if s.work_status == AgentWorkStatus.IDLE.value),
        "error": sum(1 for s in statuses if s.work_status == AgentWorkStatus.ERROR.value),
        "offline": sum(1 for s in statuses if s.work_status == AgentWorkStatus.OFFLINE.value),
    }
    
    return Response(data={
        "statuses": status_by_type,
        "statistics": stats,
    })
