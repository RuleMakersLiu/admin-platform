"""评测 Golden Case CRUD API（租户隔离 + 软删除）。"""
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.eval_judge import extract_pipeline_output, judge_output
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.eval_golden_case import EvalGoldenCase
from app.schemas.eval_golden import (
    GoldenCaseCreate,
    GoldenCaseUpdate,
    from_storage,
    to_storage,
)

router = APIRouter(prefix="/eval/golden-cases", tags=["评测 Golden Cases"])


def _to_out(case: EvalGoldenCase) -> dict:
    return {
        "id": case.id,
        "tenant_id": case.tenant_id,
        "name": case.name,
        "category": case.category,
        "project_type": case.project_type,
        "input_spec": from_storage(case.input_spec),
        "expected_criteria": from_storage(case.expected_criteria),
        "tags": case.tags,
        "enabled": case.enabled,
        "created_by": case.created_by,
        "create_time": case.create_time,
    }


async def _load_owned(case_id: int, tenant_id: int, db: AsyncSession) -> EvalGoldenCase:
    stmt = select(EvalGoldenCase).where(
        EvalGoldenCase.id == case_id,
        EvalGoldenCase.is_deleted == 0,
    )
    case = (await db.execute(stmt)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Golden case 不存在")
    if case.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="无权访问该 Golden case")
    return case


@router.get("")
async def list_cases(
    category: Optional[str] = None,
    enabled: Optional[int] = None,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """获取当前租户的 Golden case 列表。"""
    tenant_id = user["tenantId"]
    stmt = select(EvalGoldenCase).where(
        EvalGoldenCase.tenant_id == tenant_id,
        EvalGoldenCase.is_deleted == 0,
    )
    if category:
        stmt = stmt.where(EvalGoldenCase.category == category)
    if enabled is not None:
        stmt = stmt.where(EvalGoldenCase.enabled == enabled)
    stmt = stmt.order_by(EvalGoldenCase.id.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return {"code": 200, "message": "查询成功", "data": [_to_out(c) for c in rows]}


@router.post("")
async def create_case(
    req: GoldenCaseCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """创建 Golden case。"""
    case = EvalGoldenCase(
        tenant_id=user["tenantId"],
        name=req.name,
        category=req.category,
        project_type=req.project_type,
        input_spec=to_storage(req.input_spec),
        expected_criteria=to_storage(req.expected_criteria),
        tags=req.tags,
        enabled=req.enabled,
        created_by=user["adminId"],
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return {"code": 200, "message": "创建成功", "data": _to_out(case)}


@router.get("/{case_id}")
async def get_case(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    case = await _load_owned(case_id, user["tenantId"], db)
    return {"code": 200, "message": "查询成功", "data": _to_out(case)}


@router.put("/{case_id}")
async def update_case(
    case_id: int,
    req: GoldenCaseUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    case = await _load_owned(case_id, user["tenantId"], db)
    data = req.model_dump(exclude_unset=True)
    if "input_spec" in data and data["input_spec"] is not None:
        case.input_spec = to_storage(data.pop("input_spec"))
    if "expected_criteria" in data and data["expected_criteria"] is not None:
        case.expected_criteria = to_storage(data.pop("expected_criteria"))
    for key, value in data.items():
        setattr(case, key, value)
    case.update_time = int(time.time() * 1000)
    await db.commit()
    await db.refresh(case)
    return {"code": 200, "message": "更新成功", "data": _to_out(case)}


@router.delete("/{case_id}")
async def delete_case(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    case = await _load_owned(case_id, user["tenantId"], db)
    case.is_deleted = 1
    case.update_time = int(time.time() * 1000)
    await db.commit()
    return {"code": 200, "message": "删除成功"}


class JudgeRequest(BaseModel):
    golden_case_id: Optional[int] = None
    input_spec: Optional[Any] = None
    output: str
    criteria: Optional[Any] = None


@router.post("/judge")
async def judge_endpoint(
    req: JudgeRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """LLM-as-judge：按评判标准对产物逐项打分。可带 golden_case_id 自动取需求与标准。"""
    input_spec = req.input_spec
    criteria = req.criteria
    if req.golden_case_id is not None:
        case = await _load_owned(req.golden_case_id, user["tenantId"], db)
        input_spec = from_storage(case.input_spec)
        if criteria is None:
            criteria = from_storage(case.expected_criteria)
    result = await judge_output(
        input_spec if input_spec is not None else "",
        req.output,
        criteria if criteria is not None else "",
    )
    return {"code": 200, "message": "评审完成", "data": result}


@router.post("/{case_id}/judge-pipeline/{pipeline_id}")
async def judge_pipeline(
    case_id: int,
    pipeline_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """用 golden case 评审某条已完成 pipeline 的产物（自动抽取 stages_data 中的生成代码）。"""
    from app.models.agent_models import DevPipeline

    case = await _load_owned(case_id, user["tenantId"], db)
    stmt = select(DevPipeline).where(
        DevPipeline.pipeline_id == pipeline_id,
        DevPipeline.tenant_id == user["tenantId"],
        DevPipeline.is_deleted == 0,
    )
    pipe = (await db.execute(stmt)).scalar_one_or_none()
    if not pipe:
        raise HTTPException(status_code=404, detail="流水线不存在")

    output = extract_pipeline_output(pipe.stages_data)
    result = await judge_output(
        from_storage(case.input_spec),
        output,
        from_storage(case.expected_criteria),
    )
    result["pipeline_id"] = pipeline_id
    return {"code": 200, "message": "评审完成", "data": result}
