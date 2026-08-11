from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import tenant_session
from app.messaging import publisher
from app.repository import (
    create_agent,
    create_dataset,
    create_experiment,
    get_experiment_for_start,
    list_agents,
    list_datasets,
    list_experiments,
    transition_experiment,
)
from app.schemas import AgentCreate, ApiResponse, DatasetCreate, ExperimentCreate
from app.security import RequestContext, require_request_context


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.execution_gate_open:
        await publisher.start()
    yield
    await publisher.stop()


app = FastAPI(
    title="Admin Agent Evaluation",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "admin-eval",
        "execution_enabled": settings.execution_gate_open,
        "security_gate": settings.approved_gate_reference or "NOT_APPROVED",
    }


@app.get("/api/eval/security/approve", response_model=ApiResponse)
async def security_status(_: RequestContext = Depends(require_request_context)) -> ApiResponse:
    return ApiResponse(data={
        "execution_enabled": settings.execution_gate_open,
        "gate_reference": settings.approved_gate_reference or None,
        "scope": "OFFLINE_AND_SANDBOX_SHADOW_ONLY",
        "production_write_tools": False,
        "remote_agent_isolation": "RUNNER_ONLY",
    })


@app.get("/api/eval/agent/list", response_model=ApiResponse)
async def agent_list(session: AsyncSession = Depends(tenant_session)) -> ApiResponse:
    context = session.info["request_context"]
    return ApiResponse(data=await list_agents(session, context))


@app.post("/api/eval/agent/create", response_model=ApiResponse)
async def agent_create(payload: AgentCreate, session: AsyncSession = Depends(tenant_session)) -> ApiResponse:
    context = session.info["request_context"]
    return ApiResponse(data=await create_agent(session, context, payload))


@app.get("/api/eval/dataset/list", response_model=ApiResponse)
async def dataset_list(session: AsyncSession = Depends(tenant_session)) -> ApiResponse:
    context = session.info["request_context"]
    return ApiResponse(data=await list_datasets(session, context))


@app.post("/api/eval/dataset/create", response_model=ApiResponse)
async def dataset_create(payload: DatasetCreate, session: AsyncSession = Depends(tenant_session)) -> ApiResponse:
    context = session.info["request_context"]
    return ApiResponse(data=await create_dataset(session, context, payload))


@app.get("/api/eval/experiment/view", response_model=ApiResponse)
async def experiment_list(session: AsyncSession = Depends(tenant_session)) -> ApiResponse:
    context = session.info["request_context"]
    return ApiResponse(data=await list_experiments(session, context))


@app.post("/api/eval/experiment/create", response_model=ApiResponse)
async def experiment_create(
    payload: ExperimentCreate, session: AsyncSession = Depends(tenant_session)
) -> ApiResponse:
    context = session.info["request_context"]
    try:
        experiment = await create_experiment(session, context, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ApiResponse(data=experiment)


@app.post("/api/eval/experiment/{experiment_id}/run", response_model=ApiResponse)
async def experiment_run(
    experiment_id: UUID, session: AsyncSession = Depends(tenant_session)
) -> ApiResponse:
    if not settings.execution_gate_open:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="external execution is locked until G0/G1 approval is configured",
        )
    context: RequestContext = session.info["request_context"]
    experiment = await get_experiment_for_start(session, context, experiment_id)
    if not experiment or experiment["status"] != "APPROVED" or not experiment["security_approval_id"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="experiment is not approved")
    trial_count = experiment["case_count"] * experiment["variant_count"] * experiment["repetitions"]
    if trial_count > settings.max_experiment_trials:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="trial limit exceeded")
    changed = await transition_experiment(session, context, experiment_id, ("APPROVED",), "QUEUED")
    if not changed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="experiment state changed")
    await publisher.publish("eval.run.requested", str(experiment_id), {
        "experiment_id": str(experiment_id),
        "tenant_id": context.tenant_id,
        "requested_by": context.admin_id,
        "trial_count": trial_count,
        "gate_reference": settings.approved_gate_reference,
    })
    return ApiResponse(data={"id": experiment_id, "status": "QUEUED", "trial_count": trial_count})


@app.post("/api/eval/experiment/{experiment_id}/cancel", response_model=ApiResponse)
async def experiment_cancel(
    experiment_id: UUID, session: AsyncSession = Depends(tenant_session)
) -> ApiResponse:
    context: RequestContext = session.info["request_context"]
    changed = await transition_experiment(
        session, context, experiment_id,
        ("APPROVED", "QUEUED", "RUNNING", "SCORING", "REVIEWING", "PAUSED"),
        "CANCELLED",
    )
    if not changed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="experiment cannot be cancelled")
    if settings.execution_gate_open:
        await publisher.publish("eval.run.cancelled", str(experiment_id), {
            "experiment_id": str(experiment_id),
            "tenant_id": context.tenant_id,
            "cancelled_by": context.admin_id,
        })
    return ApiResponse(data={"id": experiment_id, "status": "CANCELLED"})
