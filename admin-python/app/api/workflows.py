"""工作流编排（Workflow Studio）REST API：定义 CRUD + 节点类型 + 运行/恢复。"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.ai.workflow_compiler import WorkflowValidationError
from app.ai.workflow_registry import list_node_types
from app.core.deps import get_current_user
from app.services.workflow_studio_service import workflow_studio_service

router = APIRouter(prefix="/workflows", tags=["工作流编排"])


class DefinitionCreate(BaseModel):
    name: str
    dsl: dict
    description: str = ""


class DefinitionUpdate(BaseModel):
    name: Optional[str] = None
    dsl: Optional[dict] = None
    description: Optional[str] = None


class RunCreate(BaseModel):
    inputs: dict = {}


class RunResume(BaseModel):
    value: Any = None


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="工作流不存在")


@router.get("/node-types")
async def get_node_types(user: dict = Depends(get_current_user)):
    """节点类型注册表（编辑器左侧面板数据源）。"""
    return {"code": 200, "message": "查询成功",
            "data": [t.model_dump() for t in list_node_types()]}


@router.get("")
async def list_definitions(user: dict = Depends(get_current_user)):
    return {"code": 200, "message": "查询成功",
            "data": await workflow_studio_service.list_definitions(tenant_id=user.get("tenantId") or 0)}


@router.post("")
async def create_definition(
    body: DefinitionCreate,
    user: dict = Depends(get_current_user),
):
    try:
        data = await workflow_studio_service.create_definition(
            name=body.name, dsl=body.dsl, description=body.description,
            tenant_id=user.get("tenantId") or 0, created_by=user.get("adminId") or 0,
        )
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"code": 200, "message": "创建成功", "data": data}


@router.get("/{workflow_id}")
async def get_definition(workflow_id: str, user: dict = Depends(get_current_user)):
    data = await workflow_studio_service.get_definition(workflow_id)
    if not data:
        raise _not_found()
    return {"code": 200, "message": "查询成功", "data": data}


@router.put("/{workflow_id}")
async def update_definition(
    workflow_id: str,
    body: DefinitionUpdate,
    user: dict = Depends(get_current_user),
):
    try:
        data = await workflow_studio_service.update_definition(
            workflow_id, name=body.name, dsl=body.dsl, description=body.description,
        )
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise _not_found() from exc
    return {"code": 200, "message": "保存成功", "data": data}


@router.post("/{workflow_id}/publish")
async def publish_definition(workflow_id: str, user: dict = Depends(get_current_user)):
    try:
        data = await workflow_studio_service.publish_definition(workflow_id)
    except KeyError as exc:
        raise _not_found() from exc
    return {"code": 200, "message": "已发布", "data": data}


@router.post("/{workflow_id}/runs")
async def start_run(
    workflow_id: str,
    body: RunCreate,
    user: dict = Depends(get_current_user),
):
    try:
        data = await workflow_studio_service.start_run(
            workflow_id, inputs=body.inputs, tenant_id=user.get("tenantId") or 0,
        )
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise _not_found() from exc
    return {"code": 200, "message": "已开始运行", "data": data}


@router.get("/{workflow_id}/runs/{run_id}")
async def get_run(workflow_id: str, run_id: str, user: dict = Depends(get_current_user)):
    data = await workflow_studio_service.get_run(workflow_id, run_id)
    if not data:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return {"code": 200, "message": "查询成功", "data": data}


@router.post("/{workflow_id}/runs/{run_id}/resume")
async def resume_run(
    workflow_id: str,
    run_id: str,
    body: RunResume,
    user: dict = Depends(get_current_user),
):
    try:
        data = await workflow_studio_service.resume_run(workflow_id, run_id, body.value)
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="运行记录不存在") from exc
    return {"code": 200, "message": "已恢复运行", "data": data}
