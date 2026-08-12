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
    create_dataset_version,
    create_experiment,
    delete_dataset_case,
    get_experiment_for_start,
    get_dataset_case_for_edit,
    get_dataset_version,
    import_dataset_cases,
    import_legacy_golden_cases,
    list_agents,
    list_dataset_cases,
    list_dataset_cases_for_review,
    list_datasets,
    list_experiments,
    publish_dataset_version,
    review_dataset_version,
    submit_dataset_review,
    transition_experiment,
    update_dataset_case,
)
from app.schemas import (
    AgentCreate,
    ApiResponse,
    DatasetCaseImport,
    DatasetCaseUpdate,
    DatasetCreate,
    DatasetPublishRequest,
    DatasetReviewRequest,
    DatasetVersionCreate,
    ExperimentCreate,
    GoldenImportRequest,
)
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


@app.post("/api/eval/dataset/{dataset_id}/version/create", response_model=ApiResponse)
async def dataset_version_create(
    dataset_id: UUID,
    payload: DatasetVersionCreate,
    session: AsyncSession = Depends(tenant_session),
) -> ApiResponse:
    context = session.info["request_context"]
    try:
        version = await create_dataset_version(session, context, dataset_id, payload.clone_latest)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ApiResponse(data=version)


@app.get("/api/eval/dataset/version/{version_id}", response_model=ApiResponse)
async def dataset_version_view(
    version_id: UUID, session: AsyncSession = Depends(tenant_session)
) -> ApiResponse:
    context = session.info["request_context"]
    version = await get_dataset_version(session, context, version_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="dataset version not found")
    return ApiResponse(data=version)


@app.get("/api/eval/dataset/version/{version_id}/cases", response_model=ApiResponse)
async def dataset_case_list(
    version_id: UUID, session: AsyncSession = Depends(tenant_session)
) -> ApiResponse:
    context = session.info["request_context"]
    version = await get_dataset_version(session, context, version_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="dataset version not found")
    return ApiResponse(data=await list_dataset_cases(session, context, version_id))


@app.get("/api/eval/dataset/version/{version_id}/review-cases", response_model=ApiResponse)
async def dataset_review_case_list(
    version_id: UUID, session: AsyncSession = Depends(tenant_session)
) -> ApiResponse:
    context = session.info["request_context"]
    cases = await list_dataset_cases_for_review(session, context, version_id)
    if not cases:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="reviewing dataset version not found or contains no cases",
        )
    return ApiResponse(data=cases)


@app.get("/api/eval/dataset/version/{version_id}/cases/{case_id}/edit", response_model=ApiResponse)
async def dataset_case_edit_view(
    version_id: UUID, case_id: UUID, session: AsyncSession = Depends(tenant_session)
) -> ApiResponse:
    context = session.info["request_context"]
    case = await get_dataset_case_for_edit(session, context, version_id, case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="case not found or dataset version is not DRAFT",
        )
    return ApiResponse(data=case)


@app.post("/api/eval/dataset/{dataset_id}/cases/import", response_model=ApiResponse)
async def dataset_case_import(
    dataset_id: UUID,
    payload: DatasetCaseImport,
    session: AsyncSession = Depends(tenant_session),
) -> ApiResponse:
    context = session.info["request_context"]
    try:
        result = await import_dataset_cases(session, context, dataset_id, payload.cases, payload.dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if result["errors"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=result)
    return ApiResponse(data=result)


@app.put("/api/eval/dataset/version/{version_id}/cases/{case_id}", response_model=ApiResponse)
async def dataset_case_update(
    version_id: UUID,
    case_id: UUID,
    payload: DatasetCaseUpdate,
    session: AsyncSession = Depends(tenant_session),
) -> ApiResponse:
    context = session.info["request_context"]
    try:
        result = await update_dataset_case(session, context, version_id, case_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ApiResponse(data=result)


@app.delete("/api/eval/dataset/version/{version_id}/cases/{case_id}", response_model=ApiResponse)
async def dataset_case_delete(
    version_id: UUID, case_id: UUID, session: AsyncSession = Depends(tenant_session)
) -> ApiResponse:
    context = session.info["request_context"]
    deleted = await delete_dataset_case(session, context, version_id, case_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="case does not exist or dataset version is not DRAFT",
        )
    return ApiResponse(data={"id": case_id, "deleted": True})


@app.post("/api/eval/dataset/{dataset_id}/import-golden", response_model=ApiResponse)
async def dataset_import_golden(
    dataset_id: UUID,
    payload: GoldenImportRequest,
    session: AsyncSession = Depends(tenant_session),
) -> ApiResponse:
    context = session.info["request_context"]
    try:
        result = await import_legacy_golden_cases(session, context, dataset_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ApiResponse(data=result)


@app.post("/api/eval/dataset/version/{version_id}/submit-review", response_model=ApiResponse)
async def dataset_submit_review(
    version_id: UUID, session: AsyncSession = Depends(tenant_session)
) -> ApiResponse:
    context = session.info["request_context"]
    try:
        result = await submit_dataset_review(session, context, version_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if result["errors"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=result)
    return ApiResponse(data=result)


@app.post("/api/eval/dataset/version/{version_id}/review", response_model=ApiResponse)
async def dataset_review(
    version_id: UUID,
    payload: DatasetReviewRequest,
    session: AsyncSession = Depends(tenant_session),
) -> ApiResponse:
    context = session.info["request_context"]
    try:
        result = await review_dataset_version(
            session, context, version_id, payload.decision, payload.comment
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ApiResponse(data=result)


@app.post("/api/eval/dataset/version/{version_id}/publish", response_model=ApiResponse)
async def dataset_publish(
    version_id: UUID,
    payload: DatasetPublishRequest,
    session: AsyncSession = Depends(tenant_session),
) -> ApiResponse:
    context = session.info["request_context"]
    try:
        result = await publish_dataset_version(
            session, context, version_id, payload.expected_review_round
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ApiResponse(data=result)


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
