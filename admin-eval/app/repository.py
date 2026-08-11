from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import AgentCreate, DatasetCreate, ExperimentCreate
from app.security import RequestContext


async def list_agents(session: AsyncSession, context: RequestContext) -> list[dict[str, Any]]:
    rows = await session.execute(text("""
        SELECT id, name, description, adapter_type, isolation_scope, risk_level, status, created_at
        FROM eval_agent WHERE tenant_id = :tenant_id AND archived_at IS NULL
        ORDER BY created_at DESC
    """), {"tenant_id": context.tenant_id})
    return [dict(row) for row in rows.mappings()]


async def create_agent(
    session: AsyncSession, context: RequestContext, payload: AgentCreate
) -> dict[str, Any]:
    row = await session.execute(text("""
        INSERT INTO eval_agent
            (tenant_id, name, description, adapter_type, isolation_scope, risk_level, created_by)
        VALUES
            (:tenant_id, :name, :description, :adapter_type, :isolation_scope, :risk_level, :created_by)
        RETURNING id, name, adapter_type, isolation_scope, risk_level, status, created_at
    """), {
        "tenant_id": context.tenant_id,
        "name": payload.name,
        "description": payload.description,
        "adapter_type": payload.adapter_type.value,
        "isolation_scope": payload.isolation_scope,
        "risk_level": payload.risk_level.value,
        "created_by": context.admin_id,
    })
    return dict(row.mappings().one())


async def list_datasets(session: AsyncSession, context: RequestContext) -> list[dict[str, Any]]:
    rows = await session.execute(text("""
        SELECT d.id, d.name, d.description, d.visibility, d.created_at,
               COALESCE(MAX(v.version), 0) AS latest_version,
               COALESCE(MAX(v.case_count) FILTER (WHERE v.status = 'PUBLISHED'), 0) AS published_cases
        FROM eval_dataset d
        LEFT JOIN eval_dataset_version v ON v.dataset_id = d.id AND v.tenant_id = d.tenant_id
        WHERE d.tenant_id = :tenant_id AND d.archived_at IS NULL
        GROUP BY d.id ORDER BY d.created_at DESC
    """), {"tenant_id": context.tenant_id})
    return [dict(row) for row in rows.mappings()]


async def create_dataset(
    session: AsyncSession, context: RequestContext, payload: DatasetCreate
) -> dict[str, Any]:
    row = await session.execute(text("""
        INSERT INTO eval_dataset (tenant_id, name, description, created_by)
        VALUES (:tenant_id, :name, :description, :created_by)
        RETURNING id, name, description, visibility, created_at
    """), {
        "tenant_id": context.tenant_id,
        "name": payload.name,
        "description": payload.description,
        "created_by": context.admin_id,
    })
    dataset = dict(row.mappings().one())
    await session.execute(text("""
        INSERT INTO eval_dataset_version (tenant_id, dataset_id, version)
        VALUES (:tenant_id, :dataset_id, 1)
    """), {"tenant_id": context.tenant_id, "dataset_id": dataset["id"]})
    return dataset


async def list_experiments(session: AsyncSession, context: RequestContext) -> list[dict[str, Any]]:
    rows = await session.execute(text("""
        SELECT e.id, e.name, e.experiment_type, e.status, e.repetitions, e.created_at,
               COUNT(DISTINCT v.id) AS variant_count, COUNT(DISTINCT t.id) AS trial_count
        FROM eval_experiment e
        LEFT JOIN eval_variant v ON v.experiment_id = e.id AND v.tenant_id = e.tenant_id
        LEFT JOIN eval_trial t ON t.experiment_id = e.id AND t.tenant_id = e.tenant_id
        WHERE e.tenant_id = :tenant_id AND e.archived_at IS NULL
        GROUP BY e.id ORDER BY e.created_at DESC
    """), {"tenant_id": context.tenant_id})
    return [dict(row) for row in rows.mappings()]


async def create_experiment(
    session: AsyncSession, context: RequestContext, payload: ExperimentCreate
) -> dict[str, Any]:
    published = await session.scalar(text("""
        SELECT EXISTS(
            SELECT 1 FROM eval_dataset_version
            WHERE id = :id AND tenant_id = :tenant_id AND status = 'PUBLISHED'
        )
    """), {"id": payload.dataset_version_id, "tenant_id": context.tenant_id})
    if not published:
        raise ValueError("experiment requires a published dataset version")

    versions = await session.scalar(text("""
        SELECT COUNT(*) FROM eval_agent_version
        WHERE tenant_id = :tenant_id AND id = ANY(:ids) AND security_status = 'APPROVED'
    """), {"tenant_id": context.tenant_id, "ids": payload.agent_version_ids})
    if versions != len(payload.agent_version_ids):
        raise ValueError("all agent versions must be security-approved")

    row = await session.execute(text("""
        INSERT INTO eval_experiment
            (tenant_id, name, dataset_version_id, price_book_id, sandbox_policy_version,
             repetitions, experiment_type, execution_order_seed, created_by)
        VALUES
            (:tenant_id, :name, :dataset_version_id, :price_book_id, :sandbox_policy_version,
             :repetitions, :experiment_type, :execution_order_seed, :created_by)
        RETURNING id, name, experiment_type, repetitions, status, created_at
    """), {
        "tenant_id": context.tenant_id,
        "name": payload.name,
        "dataset_version_id": payload.dataset_version_id,
        "price_book_id": payload.price_book_id,
        "sandbox_policy_version": payload.sandbox_policy_version,
        "repetitions": payload.repetitions,
        "experiment_type": payload.experiment_type,
        "execution_order_seed": payload.execution_order_seed,
        "created_by": context.admin_id,
    })
    experiment = dict(row.mappings().one())
    for index, version_id in enumerate(payload.agent_version_ids):
        await session.execute(text("""
            INSERT INTO eval_variant (tenant_id, experiment_id, agent_version_id, label)
            VALUES (:tenant_id, :experiment_id, :agent_version_id, :label)
        """), {
            "tenant_id": context.tenant_id,
            "experiment_id": experiment["id"],
            "agent_version_id": version_id,
            "label": f"V{index + 1}",
        })
    return experiment


async def get_experiment_for_start(
    session: AsyncSession, context: RequestContext, experiment_id: UUID
) -> dict[str, Any] | None:
    row = await session.execute(text("""
        SELECT e.id, e.status, e.security_approval_id, d.case_count,
               COUNT(v.id) AS variant_count, e.repetitions
        FROM eval_experiment e
        JOIN eval_dataset_version d ON d.id = e.dataset_version_id AND d.tenant_id = e.tenant_id
        JOIN eval_variant v ON v.experiment_id = e.id AND v.tenant_id = e.tenant_id
        WHERE e.id = :id AND e.tenant_id = :tenant_id AND d.status = 'PUBLISHED'
        GROUP BY e.id, d.case_count
    """), {"id": experiment_id, "tenant_id": context.tenant_id})
    mapping = row.mappings().one_or_none()
    return dict(mapping) if mapping else None


async def transition_experiment(
    session: AsyncSession,
    context: RequestContext,
    experiment_id: UUID,
    expected_statuses: tuple[str, ...],
    new_status: str,
) -> bool:
    result = await session.execute(text("""
        UPDATE eval_experiment SET status = :new_status,
            started_at = CASE WHEN :new_status = 'QUEUED' THEN now() ELSE started_at END,
            completed_at = CASE WHEN :new_status = 'CANCELLED' THEN now() ELSE completed_at END
        WHERE id = :id AND tenant_id = :tenant_id AND status = ANY(:expected_statuses)
    """), {
        "new_status": new_status,
        "id": experiment_id,
        "tenant_id": context.tenant_id,
        "expected_statuses": list(expected_statuses),
    })
    return result.rowcount == 1
