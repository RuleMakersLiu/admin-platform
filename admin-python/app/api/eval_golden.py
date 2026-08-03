"""评测 Golden Case CRUD API（租户隔离 + 软删除）。"""
import json
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.eval_judge import (
    extract_pipeline_output,
    judge_hallucination,
    judge_output,
    judge_output_vision,
)
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


class GoldenFromPipelineRequest(BaseModel):
    name: Optional[str] = None
    category: str = "general"
    project_type: Optional[str] = None
    criteria: Optional[list[str]] = None


@router.post("/from-pipeline/{pipeline_id}")
async def create_from_pipeline(
    pipeline_id: str,
    req: GoldenFromPipelineRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """从一条已跑完的 pipeline 一键生成 Golden case：input_spec 取 user_request（+ 参考产物供人工对照），
    expected_criteria 默认 DEFAULT_EVAL_CRITERIA（可覆盖）。把人工认定的「好/坏」产物沉淀为回归基线。"""
    from app.models.agent_models import DevPipeline
    from app.ai.evaluators import DEFAULT_EVAL_CRITERIA

    pipe = (await db.execute(
        select(DevPipeline).where(
            DevPipeline.pipeline_id == pipeline_id, DevPipeline.is_deleted == 0
        )
    )).scalar_one_or_none()
    if not pipe:
        raise HTTPException(status_code=404, detail="pipeline 不存在")
    if pipe.tenant_id != user["tenantId"]:
        raise HTTPException(status_code=403, detail="无权访问该 pipeline")
    request_text = (pipe.user_request or "").strip()
    if not request_text:
        raise HTTPException(status_code=400, detail="该 pipeline 无 user_request，无法生成 Golden case")
    reference = extract_pipeline_output(pipe.stages_data)
    input_spec = {"request": request_text, "reference_output": (reference or "")[:6000]}
    case = EvalGoldenCase(
        tenant_id=user["tenantId"],
        name=(req.name or "").strip() or request_text[:40],
        category=req.category,
        project_type=req.project_type,
        input_spec=to_storage(input_spec),
        expected_criteria=to_storage(req.criteria or DEFAULT_EVAL_CRITERIA),
        tags=None,
        enabled=1,
        created_by=user["adminId"],
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return {"code": 200, "message": "已存为 Golden case", "data": _to_out(case)}


@router.post("/run-all")
async def run_all_golden_cases(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """一键回归：对当前租户全部 enabled golden case 各起一条 full 流水线 + EvalRun，后台无人值守驱动。
    并发受 pipeline_manager 执行信号量（PIPELINE_EXECUTION_CONCURRENCY）约束。用于改 prompt / 换模型后防退化。
    返回启动列表（每个 {golden_case_id, name, pipeline_id}）。"""
    import asyncio

    from app.ai.eval_judge import input_spec_to_request_text
    from app.ai.flow_manager import pipeline_manager
    from app.models.eval_run import EvalRun

    cases = (await db.execute(
        select(EvalGoldenCase).where(
            EvalGoldenCase.tenant_id == user["tenantId"],
            EvalGoldenCase.enabled == 1,
            EvalGoldenCase.is_deleted == 0,
        ).order_by(EvalGoldenCase.id)
    )).scalars().all()
    started = []
    for case in cases:
        user_request = input_spec_to_request_text(from_storage(case.input_spec))
        if not user_request:
            continue
        pipeline_id = await pipeline_manager.create_pipeline(
            user_request=user_request,
            tenant_id=user["tenantId"],
            creator_id=user["adminId"],
            pipeline_mode="full",
        )
        db.add(EvalRun(
            tenant_id=user["tenantId"], golden_case_id=case.id,
            pipeline_id=pipeline_id, status="running",
        ))
        asyncio.create_task(_eval_auto_run_pipeline(pipeline_id, user_request))
        started.append({"golden_case_id": case.id, "name": case.name, "pipeline_id": pipeline_id})
    await db.commit()
    return {
        "code": 200,
        "message": f"已启动 {len(started)} 条 golden 回归流水线（后台无人值守，完成自动评审）",
        "data": {"started": started, "count": len(started)},
    }


@router.get("/runs/history")
async def golden_runs_history(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """聚合近 days 天已评审(judged)的 eval_run，按 golden_case 分组：每个 case 的近期均分 / 通过率(>=60) /
    每次 run 的分数+时间。供对比「改 prompt / 换模型」前后的质量退化。"""
    from app.models.eval_run import EvalRun

    cutoff = int((time.time() - days * 86400) * 1000)
    rows = (await db.execute(
        select(EvalRun, EvalGoldenCase.name).join(
            EvalGoldenCase, EvalGoldenCase.id == EvalRun.golden_case_id
        ).where(
            EvalRun.tenant_id == user["tenantId"],
            EvalRun.is_deleted == 0,
            EvalRun.status == "judged",
            EvalRun.create_time >= cutoff,
        ).order_by(EvalRun.golden_case_id, EvalRun.create_time)
    )).all()
    by_case: dict = {}
    for run, name in rows:
        c = by_case.setdefault(run.golden_case_id, {
            "golden_case_id": run.golden_case_id, "name": name,
            "runs": [], "avg_score": None, "pass_rate": None,
        })
        c["runs"].append({
            "eval_run_id": run.id, "pipeline_id": run.pipeline_id,
            "score": run.overall_score, "time": run.create_time,
        })
    for c in by_case.values():
        scores = [r["score"] for r in c["runs"] if r["score"] is not None]
        if scores:
            c["avg_score"] = round(sum(scores) / len(scores), 1)
            c["pass_rate"] = round(sum(1 for s in scores if s >= 60) / len(scores), 4)
    return {"code": 200, "message": "查询成功", "data": {"days": days, "cases": list(by_case.values())}}


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


@router.post("/{case_id}/judge-pipeline-vision/{pipeline_id}")
async def judge_pipeline_vision(
    case_id: int,
    pipeline_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """视觉评测：把流水线生成的前端真实渲染截图，再用 GLM-4V 按评判标准评审渲染结果。

    与 judge-pipeline（读代码文本）互补——本接口评审「真正渲染出来对不对」。
    返回评审结果 + 截图(data_uri) 便于回看。
    """
    from app.services.vision_eval_service import render_pipeline_screenshot

    case = await _load_owned(case_id, user["tenantId"], db)
    from app.models.agent_models import DevPipeline

    stmt = select(DevPipeline).where(
        DevPipeline.pipeline_id == pipeline_id,
        DevPipeline.tenant_id == user["tenantId"],
        DevPipeline.is_deleted == 0,
    )
    pipe = (await db.execute(stmt)).scalar_one_or_none()
    if not pipe:
        raise HTTPException(status_code=404, detail="流水线不存在")

    try:
        rendered = await render_pipeline_screenshot(pipeline_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"渲染截图失败: {exc}")

    result = await judge_output_vision(
        rendered["data_uri"],
        from_storage(case.input_spec),
        from_storage(case.expected_criteria),
    )
    result["pipeline_id"] = pipeline_id
    result["screenshot"] = rendered["data_uri"]
    result["preview_url"] = rendered.get("preview_url")
    return {"code": 200, "message": "视觉评审完成", "data": result}


@router.post("/{case_id}/judge-pipeline-hallucination/{pipeline_id}")
async def judge_pipeline_hallucination(
    case_id: int,
    pipeline_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """幻觉评审：检测流水线产物中【需求】未支撑的虚构内容（编造 API/库/路径/配置等）。

    hallucination_score：100=完全有据无虚构，0=大量虚构；flagged 列出具体嫌疑。
    与 judge-pipeline（功能对不对）正交——本接口判「有没有瞎编」。
    """
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
    result = await judge_hallucination(
        from_storage(case.input_spec),
        output,
    )
    result["pipeline_id"] = pipeline_id
    return {"code": 200, "message": "幻觉评审完成", "data": result}


async def _eval_auto_run_pipeline(pipeline_id: str, user_request: str, max_iters: int = 80) -> None:
    """无人值守驱动 golden-case 流水线：自动执行各阶段 + 自动确认 confirm 关卡，直到终态。

    流水线是 stage-by-stage 模型——execute_stage 跑一个阶段 → waiting_confirm →
    confirm_stage 推进到下一阶段（status=pending，不自动执行）→ 再 execute_stage。
    本函数把这个「执行 + 确认」循环自动化。终态（completed/failed）由 execute_stage
    内部触发 _record_pipeline_eval → _auto_judge_eval_runs 自动评审，写入关联的 eval_run。
    """
    import asyncio

    from app.ai.flow_manager import pipeline_manager

    for _ in range(max_iters):
        try:
            st = await pipeline_manager.get_pipeline_status(pipeline_id)
        except Exception:
            return
        status = st.get("status")
        if status in ("completed", "failed"):
            return
        # needs_human：某阶段重试耗尽，暂停等人工。绝不自动放行——否则待人工的流水线
        # 会被无人值守 watcher 越过。交由开发人员介入队列处理，人工 resume 后另起 watcher。
        if status == "needs_human":
            return
        if status == "waiting_confirm":
            try:
                await pipeline_manager.confirm_stage(pipeline_id, True, "")
            except Exception:
                # confirm 可能因「需选择前端页面」等特殊关卡失败 —— 跳过本轮，下轮重试或终态退出
                pass
            await asyncio.sleep(1.0)
            continue
        # pending / running → 执行当前阶段（阻塞至该阶段完成，再回到循环顶部判断）
        try:
            await pipeline_manager.execute_stage(pipeline_id, user_request)
        except Exception:
            # 执行异常通常会把流水线置为 failed —— 下一轮 top 判定终态后退出
            await asyncio.sleep(1.0)


@router.post("/{case_id}/run")
async def run_golden_case(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """从 Golden case 创建并自动执行一条开发流水线；执行完成自动评审（写入 eval_run）。

    完整无人值守闭环：golden case → 创建管线(+EvalRun) → 自动执行+自动确认 → 终态自动评审。
    full 模式生成全新项目（frontend_contract_review 需已存在前端项目，不适用 golden case）。
    """
    import asyncio

    from app.ai.eval_judge import input_spec_to_request_text
    from app.ai.flow_manager import pipeline_manager
    from app.models.eval_run import EvalRun

    case = await _load_owned(case_id, user["tenantId"], db)
    user_request = input_spec_to_request_text(from_storage(case.input_spec))
    if not user_request:
        raise HTTPException(status_code=400, detail="Golden case 的 input_spec 无法解析为需求文本")

    pipeline_id = await pipeline_manager.create_pipeline(
        user_request=user_request,
        tenant_id=user["tenantId"],
        creator_id=user["adminId"],
        pipeline_mode="full",
    )

    # 关联 EvalRun —— 管线终态时 _record_pipeline_eval 据此自动评审
    run = EvalRun(
        tenant_id=user["tenantId"],
        golden_case_id=case_id,
        pipeline_id=pipeline_id,
        status="running",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # 后台无人值守驱动：自动执行各阶段 + 自动确认 confirm 关卡，终态自动评审
    asyncio.create_task(_eval_auto_run_pipeline(pipeline_id, user_request))

    return {
        "code": 200,
        "message": "已从 Golden case 创建并启动流水线，完成后自动评审",
        "data": {
            "pipeline_id": pipeline_id,
            "eval_run_id": run.id,
            "golden_case_id": case_id,
            "status": "running",
        },
    }


metrics_router = APIRouter(prefix="/eval", tags=["AI 评测指标"])


@metrics_router.get("/metrics")
async def ai_metrics(
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """AI 效果评测指标汇总：响应速度 / 准确率 / 生成效果 / 成本（按模型，时间窗口）。

    数据源：llm_usage_log（每次 LLM 调用的延迟/成功/token/成本）+ eval_run（golden 通过率/均分）。
    """
    tid = user["tenantId"]
    since_ms = int(time.time() * 1000) - hours * 3600 * 1000

    # 响应速度 + 成本（按模型；只统计已打延迟的调用，所有聚合在同一集合上，避免分子分母不一致）
    speed_q = text("""
        SELECT model,
            COUNT(*) AS calls,
            COUNT(*) FILTER (WHERE success = 1) AS ok,
            COALESCE(AVG(latency_ms), 0) AS avg_latency,
            COALESCE(SUM(latency_ms), 0) AS sum_latency,
            COALESCE(percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms), 0) AS p50,
            COALESCE(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms), 0) AS p95,
            COALESCE(AVG(ttft_ms), 0) AS avg_ttft,
            COALESCE(SUM(input_tokens), 0) AS input_tokens,
            COALESCE(SUM(output_tokens), 0) AS output_tokens,
            COALESCE(SUM(cost), 0) AS cost
        FROM llm_usage_log
        WHERE create_time >= :since
          AND (tenant_id = :tid OR tenant_id IS NULL)
          AND latency_ms IS NOT NULL
        GROUP BY model
    """)
    rows = (await db.execute(speed_q, {"since": since_ms, "tid": tid})).mappings().all()

    by_model, tot_calls, tot_ok, tot_in, tot_out, tot_cost = [], 0, 0, 0, 0, 0.0
    tot_sum_lat = 0.0
    for r in rows:
        m = r["model"] or "unknown"
        calls = int(r["calls"] or 0)
        ok = int(r["ok"] or 0)
        in_tok = int(r["input_tokens"] or 0)
        out_tok = int(r["output_tokens"] or 0)
        lat = float(r["avg_latency"] or 0)
        sum_lat = float(r["sum_latency"] or 0)
        cost = float(r["cost"] or 0)
        tot_calls += calls
        tot_ok += ok
        tot_in += in_tok
        tot_out += out_tok
        tot_sum_lat += sum_lat
        tot_cost += cost
        by_model.append({
            "model": m,
            "calls": calls,
            "success_rate": round(ok / calls * 100, 1) if calls else None,
            "avg_latency_ms": round(lat, 1),
            "p50_ms": round(float(r["p50"]), 1),
            "p95_ms": round(float(r["p95"]), 1),
            "avg_ttft_ms": round(float(r["avg_ttft"]), 1),
            "tokens_per_s": round(out_tok / (sum_lat / 1000), 1) if sum_lat else None,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost": round(cost, 4),
        })
    # 按流水线阶段的速度明细（stage 由 pipeline_context(stage=...) 归因）
    stage_q = text("""
        SELECT stage,
            COUNT(*) AS calls,
            COUNT(*) FILTER (WHERE success = 1) AS ok,
            COALESCE(AVG(latency_ms), 0) AS avg_latency,
            COALESCE(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms), 0) AS p95
        FROM llm_usage_log
        WHERE create_time >= :since
          AND (tenant_id = :tid OR tenant_id IS NULL)
          AND latency_ms IS NOT NULL AND stage IS NOT NULL
        GROUP BY stage
        ORDER BY avg_latency DESC
    """)
    srows = (await db.execute(stage_q, {"since": since_ms, "tid": tid})).mappings().all()
    by_stage = [
        {
            "stage": r["stage"],
            "calls": int(r["calls"] or 0),
            "success_rate": round(int(r["ok"] or 0) / int(r["calls"] or 1) * 100, 1) if r["calls"] else None,
            "avg_latency_ms": round(float(r["avg_latency"] or 0), 1),
            "p95_ms": round(float(r["p95"]), 1),
        }
        for r in srows
    ]

    overall_lat = (tot_sum_lat / tot_calls) if tot_calls else 0
    speed = {
        "overall": {
            "calls": tot_calls,
            "success_rate": round(tot_ok / tot_calls * 100, 1) if tot_calls else None,
            "avg_latency_ms": round(overall_lat, 1),
            "tokens_per_s": round(tot_out / (tot_sum_lat / 1000), 1) if tot_sum_lat else None,
            "input_tokens": tot_in,
            "output_tokens": tot_out,
            "cost": round(tot_cost, 4),
        },
        "by_model": sorted(by_model, key=lambda x: x["calls"], reverse=True),
        "by_stage": by_stage,
    }

    # 准确率 / 生成效果（golden case 评审通过率与均分）
    acc_q = text("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'judged') AS judged,
            COUNT(*) FILTER (WHERE status = 'judged' AND overall_score >= 60) AS passed,
            COALESCE(AVG(overall_score) FILTER (WHERE status = 'judged'), 0) AS avg_score
        FROM eval_run
        WHERE update_time >= :since AND tenant_id = :tid AND is_deleted = 0
    """)
    a = (await db.execute(acc_q, {"since": since_ms, "tid": tid})).mappings().first()
    judged = int(a["judged"] or 0)
    passed = int(a["passed"] or 0)
    avg_score = round(float(a["avg_score"] or 0), 1)
    accuracy = {
        "judged": judged,
        "passed": passed,
        "pass_rate": round(passed / judged * 100, 1) if judged else None,
        "avg_score": avg_score,
    }

    # 幻觉：从 eval_run.judgment 里抽 hallucination_score 聚合（终态自动评审写入）
    hal_q = text("""
        SELECT judgment FROM eval_run
        WHERE status = 'judged' AND update_time >= :since
          AND tenant_id = :tid AND is_deleted = 0
    """)
    hal_rows = (await db.execute(hal_q, {"since": since_ms, "tid": tid})).scalars().all()
    hal_scores: list = []
    for j in hal_rows:
        try:
            jd = json.loads(j) if j else {}
        except Exception:  # noqa: BLE001
            jd = {}
        s = jd.get("hallucination_score")
        if isinstance(s, (int, float)):
            hal_scores.append(s)
    hallucination = {
        "judged": len(hal_scores),
        "avg_score": round(sum(hal_scores) / len(hal_scores), 1) if hal_scores else None,
    }

    return {"code": 200, "message": "查询成功", "data": {
        "window_hours": hours,
        "speed": speed,
        "accuracy": accuracy,
        "quality": {"avg_score": avg_score, "judged": judged},
        "hallucination": hallucination,
        "cost": {
            "input_tokens": tot_in,
            "output_tokens": tot_out,
            "cost": round(tot_cost, 4),
            "by_model": [
                {"model": x["model"], "input_tokens": x["input_tokens"],
                 "output_tokens": x["output_tokens"], "cost": x["cost"]}
                for x in by_model
            ],
        },
    }}
