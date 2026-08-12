import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dataset_factory import (
    CaseDraft,
    OracleType,
    RiskLevel,
    SourceType,
    Split,
    canonical_case_hash,
    validate_case,
    validate_release,
)
from app.schemas import (
    AgentCreate,
    DatasetCaseInput,
    DatasetCreate,
    ExperimentCreate,
    GoldenImportRequest,
)
from app.security import RequestContext


async def _audit(
    session: AsyncSession,
    context: RequestContext,
    action: str,
    resource_type: str,
    resource_id: object,
    details: dict[str, Any] | None = None,
) -> None:
    """Write an append-only tenant-scoped audit record in the caller transaction."""
    await session.execute(text("""
        INSERT INTO eval_audit_log
            (tenant_id, actor_id, actor_type, action, resource_type, resource_id, details)
        VALUES
            (:tenant_id, :actor_id, 'ADMIN', :action, :resource_type, :resource_id,
             CAST(:details AS jsonb))
    """), {
        "tenant_id": context.tenant_id,
        "actor_id": context.admin_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": str(resource_id),
        "details": json.dumps(details or {}, ensure_ascii=False),
    })


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
               latest.id AS latest_version_id, COALESCE(latest.version, 0) AS latest_version,
               COALESCE(latest.status, 'DRAFT') AS latest_status,
               COALESCE(latest.case_count, 0) AS latest_case_count,
               COALESCE(latest.review_round, 0) AS review_round,
               COALESCE(MAX(v.case_count) FILTER (WHERE v.status = 'PUBLISHED'), 0) AS published_cases
        FROM eval_dataset d
        LEFT JOIN eval_dataset_version v ON v.dataset_id = d.id AND v.tenant_id = d.tenant_id
        LEFT JOIN LATERAL (
            SELECT id, version, status, case_count, review_round
            FROM eval_dataset_version
            WHERE dataset_id = d.id AND tenant_id = d.tenant_id
            ORDER BY version DESC LIMIT 1
        ) latest ON TRUE
        WHERE d.tenant_id = :tenant_id AND d.archived_at IS NULL
        GROUP BY d.id, latest.id, latest.version, latest.status, latest.case_count, latest.review_round
        ORDER BY d.created_at DESC
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
    await _audit(session, context, "DATASET_CREATED", "DATASET", dataset["id"])
    return dataset


def _case_draft(payload: DatasetCaseInput) -> CaseDraft:
    return CaseDraft(
        external_id=payload.external_id,
        category=payload.category,
        risk_level=RiskLevel(payload.risk_level.value),
        split=Split(payload.split),
        source_type=SourceType(payload.source_type),
        input_payload=payload.input_payload,
        expected_state=payload.expected_state,
        rubric=payload.rubric,
        budget=payload.budget,
        deterministic_checks=payload.deterministic_checks,
        tool_policy=payload.tool_policy,
        oracle_type=OracleType(payload.oracle_type),
        initial_state_ref=payload.initial_state_ref,
        prohibited_behaviors=tuple(payload.prohibited_behaviors),
        source_group_id=payload.source_group_id,
        source_parent_hash=payload.source_parent_hash,
    )


async def _refresh_case_count(
    session: AsyncSession, context: RequestContext, version_id: UUID
) -> None:
    await session.execute(text("""
        UPDATE eval_dataset_version v SET case_count = (
            SELECT COUNT(*) FROM eval_case c
            WHERE c.dataset_version_id = v.id AND c.tenant_id = v.tenant_id
        ) WHERE v.id = :version_id AND v.tenant_id = :tenant_id
    """), {"version_id": version_id, "tenant_id": context.tenant_id})


async def _draft_version(
    session: AsyncSession, context: RequestContext, dataset_id: UUID
) -> dict[str, Any] | None:
    row = await session.execute(text("""
        SELECT v.id, v.version, v.status, v.review_round, d.created_by
        FROM eval_dataset_version v
        JOIN eval_dataset d ON d.id = v.dataset_id AND d.tenant_id = v.tenant_id
        WHERE v.dataset_id = :dataset_id AND v.tenant_id = :tenant_id
        ORDER BY v.version DESC LIMIT 1
    """), {"dataset_id": dataset_id, "tenant_id": context.tenant_id})
    mapping = row.mappings().one_or_none()
    return dict(mapping) if mapping else None


async def create_dataset_version(
    session: AsyncSession, context: RequestContext, dataset_id: UUID, clone_latest: bool
) -> dict[str, Any]:
    latest = await _draft_version(session, context, dataset_id)
    if not latest:
        raise ValueError("dataset does not exist")
    if latest["status"] in {"DRAFT", "REVIEWING"}:
        raise ValueError("finish the current dataset version before creating a new one")
    row = await session.execute(text("""
        INSERT INTO eval_dataset_version (tenant_id, dataset_id, version)
        VALUES (:tenant_id, :dataset_id, :version)
        RETURNING id, dataset_id, version, status, case_count, review_round, created_at
    """), {
        "tenant_id": context.tenant_id, "dataset_id": dataset_id,
        "version": latest["version"] + 1,
    })
    version = dict(row.mappings().one())
    if clone_latest:
        await session.execute(text("""
            INSERT INTO eval_case (
                external_id, tenant_id, dataset_version_id, category, risk_level, split,
                input_payload, initial_state_ref, expected_state, rubric, tool_policy, budget,
                deterministic_checks, source_type, source_hash, reviewed_by, created_by,
                oracle_type, prohibited_behaviors, source_group_id, source_parent_hash
            )
            SELECT external_id, tenant_id, :new_version_id, category, risk_level, split,
                   input_payload, initial_state_ref, expected_state, rubric, tool_policy, budget,
                   deterministic_checks, source_type, source_hash, NULL, :created_by,
                   oracle_type, prohibited_behaviors, source_group_id, source_parent_hash
            FROM eval_case
            WHERE tenant_id = :tenant_id AND dataset_version_id = :old_version_id
        """), {
            "new_version_id": version["id"], "old_version_id": latest["id"],
            "tenant_id": context.tenant_id, "created_by": context.admin_id,
        })
        await _refresh_case_count(session, context, version["id"])
    await _audit(session, context, "DATASET_VERSION_CREATED", "DATASET_VERSION", version["id"], {
        "dataset_id": str(dataset_id), "cloned": clone_latest,
    })
    return version


async def get_dataset_version(
    session: AsyncSession, context: RequestContext, version_id: UUID
) -> dict[str, Any] | None:
    row = await session.execute(text("""
        SELECT v.id, v.dataset_id, d.name AS dataset_name, v.version, v.status,
               v.case_count, v.content_hash, v.review_round, v.published_at,
               COUNT(r.id) FILTER (
                   WHERE r.review_round = v.review_round AND r.decision = 'APPROVE'
               ) AS approvals,
               COUNT(r.id) FILTER (
                   WHERE r.review_round = v.review_round AND r.decision = 'REJECT'
               ) AS rejections
        FROM eval_dataset_version v
        JOIN eval_dataset d ON d.id = v.dataset_id AND d.tenant_id = v.tenant_id
        LEFT JOIN eval_dataset_review r
          ON r.dataset_version_id = v.id AND r.tenant_id = v.tenant_id
        WHERE v.id = :version_id AND v.tenant_id = :tenant_id
        GROUP BY v.id, d.id
    """), {"version_id": version_id, "tenant_id": context.tenant_id})
    mapping = row.mappings().one_or_none()
    return dict(mapping) if mapping else None


async def list_dataset_cases(
    session: AsyncSession, context: RequestContext, version_id: UUID
) -> list[dict[str, Any]]:
    rows = await session.execute(text("""
        SELECT id, external_id, category, risk_level, split, source_type, source_group_id,
               oracle_type,
               CASE WHEN split = 'HIDDEN' THEN NULL ELSE initial_state_ref END AS initial_state_ref,
               CASE WHEN split = 'HIDDEN' THEN NULL ELSE input_payload END AS input_payload,
               CASE WHEN split = 'HIDDEN' THEN NULL ELSE expected_state END AS expected_state,
               CASE WHEN split = 'HIDDEN' THEN NULL ELSE rubric END AS rubric,
               CASE WHEN split = 'HIDDEN' THEN NULL ELSE tool_policy END AS tool_policy,
               CASE WHEN split = 'HIDDEN' THEN NULL ELSE budget END AS budget,
               CASE WHEN split = 'HIDDEN' THEN NULL ELSE deterministic_checks END AS deterministic_checks,
               CASE WHEN split = 'HIDDEN' THEN NULL ELSE prohibited_behaviors END AS prohibited_behaviors,
               CASE WHEN split = 'HIDDEN' THEN NULL ELSE source_parent_hash END AS source_parent_hash,
               reviewed_by, created_at
        FROM eval_case
        WHERE dataset_version_id = :version_id AND tenant_id = :tenant_id
        ORDER BY created_at, id
    """), {"version_id": version_id, "tenant_id": context.tenant_id})
    return [dict(row) for row in rows.mappings()]


async def get_dataset_case_for_edit(
    session: AsyncSession, context: RequestContext, version_id: UUID, case_id: UUID
) -> dict[str, Any] | None:
    row = await session.execute(text("""
        SELECT c.id, c.external_id, c.category, c.risk_level, c.split, c.source_type,
               c.input_payload, c.initial_state_ref, c.expected_state, c.rubric,
               c.tool_policy, c.budget, c.deterministic_checks, c.oracle_type,
               c.prohibited_behaviors, c.source_group_id, c.source_parent_hash
        FROM eval_case c
        JOIN eval_dataset_version v ON v.id = c.dataset_version_id AND v.tenant_id = c.tenant_id
        WHERE c.id = :case_id AND c.dataset_version_id = :version_id
          AND c.tenant_id = :tenant_id AND v.status = 'DRAFT'
    """), {
        "case_id": case_id, "version_id": version_id, "tenant_id": context.tenant_id,
    })
    mapping = row.mappings().one_or_none()
    if mapping and mapping["split"] == "HIDDEN":
        await _audit(session, context, "HIDDEN_CASE_EDIT_VIEWED", "DATASET_CASE", case_id, {
            "version_id": str(version_id),
        })
    return dict(mapping) if mapping else None


async def list_dataset_cases_for_review(
    session: AsyncSession, context: RequestContext, version_id: UUID
) -> list[dict[str, Any]]:
    rows = await session.execute(text("""
        SELECT c.id, c.external_id, c.category, c.risk_level, c.split, c.source_type,
               c.source_group_id, c.oracle_type, c.initial_state_ref, c.input_payload,
               c.expected_state, c.rubric, c.tool_policy, c.budget,
               c.deterministic_checks, c.prohibited_behaviors, c.source_parent_hash,
               c.created_at
        FROM eval_case c
        JOIN eval_dataset_version v ON v.id = c.dataset_version_id AND v.tenant_id = c.tenant_id
        WHERE c.dataset_version_id = :version_id AND c.tenant_id = :tenant_id
          AND v.status = 'REVIEWING'
        ORDER BY c.created_at, c.id
    """), {"version_id": version_id, "tenant_id": context.tenant_id})
    cases = [dict(row) for row in rows.mappings()]
    if any(case["split"] == "HIDDEN" for case in cases):
        await _audit(session, context, "HIDDEN_CASES_REVIEW_VIEWED", "DATASET_VERSION", version_id, {
            "case_count": len(cases),
        })
    return cases


async def import_dataset_cases(
    session: AsyncSession,
    context: RequestContext,
    dataset_id: UUID,
    payloads: list[DatasetCaseInput],
    dry_run: bool,
) -> dict[str, Any]:
    version = await _draft_version(session, context, dataset_id)
    if not version:
        raise ValueError("dataset does not exist")
    if version["status"] != "DRAFT":
        raise ValueError("only a DRAFT dataset version accepts case changes")

    drafts = [_case_draft(payload) for payload in payloads]
    validation_errors: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    seen_external_ids: set[UUID] = set()
    for index, draft in enumerate(drafts):
        errors = validate_case(draft)
        content_hash = canonical_case_hash(draft)
        if content_hash in seen_hashes:
            errors.append("duplicate within import batch")
        if draft.external_id in seen_external_ids:
            errors.append("duplicate external ID within import batch")
        if errors:
            validation_errors.append({"index": index, "external_id": draft.external_id, "errors": errors})
        seen_hashes.add(content_hash)
        seen_external_ids.add(draft.external_id)

    existing = await session.execute(text("""
        SELECT external_id, source_hash FROM eval_case
        WHERE tenant_id = :tenant_id AND dataset_version_id = :version_id
          AND (external_id = ANY(:external_ids) OR source_hash = ANY(:source_hashes))
    """), {
        "tenant_id": context.tenant_id,
        "version_id": version["id"],
        "external_ids": [draft.external_id for draft in drafts],
        "source_hashes": [canonical_case_hash(draft) for draft in drafts],
    })
    for row in existing.mappings():
        validation_errors.append({
            "external_id": row["external_id"],
            "errors": ["external ID or exact case content already exists in this version"],
        })
    if validation_errors or dry_run:
        return {
            "valid": not validation_errors,
            "dry_run": dry_run,
            "imported": 0,
            "version_id": version["id"],
            "errors": validation_errors,
        }

    for payload, draft in zip(payloads, drafts, strict=True):
        await _insert_case(session, context, version["id"], payload, draft)
    await _refresh_case_count(session, context, version["id"])
    await _audit(session, context, "DATASET_CASES_IMPORTED", "DATASET_VERSION", version["id"], {
        "count": len(payloads),
    })
    return {
        "valid": True,
        "dry_run": False,
        "imported": len(payloads),
        "version_id": version["id"],
        "errors": [],
    }


async def _insert_case(
    session: AsyncSession,
    context: RequestContext,
    version_id: UUID,
    payload: DatasetCaseInput,
    draft: CaseDraft,
) -> None:
    await session.execute(text("""
        INSERT INTO eval_case (
            external_id, tenant_id, dataset_version_id, category, risk_level, split,
            input_payload, initial_state_ref, expected_state, rubric, tool_policy, budget,
            deterministic_checks, source_type, source_hash, created_by, oracle_type,
            prohibited_behaviors, source_group_id, source_parent_hash
        ) VALUES (
            :external_id, :tenant_id, :version_id, :category, :risk_level, :split,
            CAST(:input_payload AS jsonb), :initial_state_ref, CAST(:expected_state AS jsonb),
            CAST(:rubric AS jsonb), CAST(:tool_policy AS jsonb), CAST(:budget AS jsonb),
            CAST(:deterministic_checks AS jsonb), :source_type, :source_hash, :created_by,
            :oracle_type, CAST(:prohibited_behaviors AS jsonb), :source_group_id,
            :source_parent_hash
        )
    """), {
        "external_id": payload.external_id,
        "tenant_id": context.tenant_id,
        "version_id": version_id,
        "category": payload.category,
        "risk_level": payload.risk_level.value,
        "split": payload.split,
        "input_payload": json.dumps(payload.input_payload, ensure_ascii=False),
        "initial_state_ref": payload.initial_state_ref,
        "expected_state": json.dumps(payload.expected_state, ensure_ascii=False),
        "rubric": json.dumps(payload.rubric, ensure_ascii=False),
        "tool_policy": json.dumps(payload.tool_policy, ensure_ascii=False),
        "budget": json.dumps(payload.budget, ensure_ascii=False),
        "deterministic_checks": json.dumps(payload.deterministic_checks, ensure_ascii=False),
        "source_type": payload.source_type,
        "source_hash": canonical_case_hash(draft),
        "created_by": context.admin_id,
        "oracle_type": payload.oracle_type,
        "prohibited_behaviors": json.dumps(payload.prohibited_behaviors, ensure_ascii=False),
        "source_group_id": payload.source_group_id,
        "source_parent_hash": payload.source_parent_hash,
    })


async def update_dataset_case(
    session: AsyncSession,
    context: RequestContext,
    version_id: UUID,
    case_id: UUID,
    payload: DatasetCaseInput,
) -> dict[str, Any]:
    draft = _case_draft(payload)
    errors = validate_case(draft)
    if errors:
        raise ValueError("; ".join(errors))
    result = await session.execute(text("""
        UPDATE eval_case c SET
            external_id = :external_id, category = :category, risk_level = :risk_level,
            split = :split, input_payload = CAST(:input_payload AS jsonb),
            initial_state_ref = :initial_state_ref, expected_state = CAST(:expected_state AS jsonb),
            rubric = CAST(:rubric AS jsonb), tool_policy = CAST(:tool_policy AS jsonb),
            budget = CAST(:budget AS jsonb), deterministic_checks = CAST(:checks AS jsonb),
            source_type = :source_type, source_hash = :source_hash, oracle_type = :oracle_type,
            prohibited_behaviors = CAST(:prohibited AS jsonb), source_group_id = :source_group_id,
            source_parent_hash = :source_parent_hash
        FROM eval_dataset_version v
        WHERE c.id = :case_id AND c.dataset_version_id = :version_id
          AND c.tenant_id = :tenant_id AND v.id = c.dataset_version_id
          AND v.tenant_id = c.tenant_id AND v.status = 'DRAFT'
    """), {
        "case_id": case_id, "version_id": version_id, "tenant_id": context.tenant_id,
        "external_id": payload.external_id, "category": payload.category,
        "risk_level": payload.risk_level.value, "split": payload.split,
        "input_payload": json.dumps(payload.input_payload, ensure_ascii=False),
        "initial_state_ref": payload.initial_state_ref,
        "expected_state": json.dumps(payload.expected_state, ensure_ascii=False),
        "rubric": json.dumps(payload.rubric, ensure_ascii=False),
        "tool_policy": json.dumps(payload.tool_policy, ensure_ascii=False),
        "budget": json.dumps(payload.budget, ensure_ascii=False),
        "checks": json.dumps(payload.deterministic_checks, ensure_ascii=False),
        "source_type": payload.source_type, "source_hash": canonical_case_hash(draft),
        "oracle_type": payload.oracle_type,
        "prohibited": json.dumps(payload.prohibited_behaviors, ensure_ascii=False),
        "source_group_id": payload.source_group_id, "source_parent_hash": payload.source_parent_hash,
    })
    if result.rowcount != 1:
        raise ValueError("case does not exist or dataset version is not DRAFT")
    await _audit(session, context, "DATASET_CASE_UPDATED", "DATASET_CASE", case_id, {
        "version_id": str(version_id),
    })
    return {"id": case_id, "version_id": version_id, "updated": True}


async def delete_dataset_case(
    session: AsyncSession, context: RequestContext, version_id: UUID, case_id: UUID
) -> bool:
    result = await session.execute(text("""
        DELETE FROM eval_case c USING eval_dataset_version v
        WHERE c.id = :case_id AND c.dataset_version_id = :version_id
          AND c.tenant_id = :tenant_id AND v.id = c.dataset_version_id
          AND v.tenant_id = c.tenant_id AND v.status = 'DRAFT'
    """), {"case_id": case_id, "version_id": version_id, "tenant_id": context.tenant_id})
    if result.rowcount == 1:
        await _refresh_case_count(session, context, version_id)
        await _audit(session, context, "DATASET_CASE_DELETED", "DATASET_CASE", case_id, {
            "version_id": str(version_id),
        })
    return result.rowcount == 1


def _parse_storage(raw: Any) -> Any:
    if raw is None or not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except ValueError:
        return raw


async def import_legacy_golden_cases(
    session: AsyncSession,
    context: RequestContext,
    dataset_id: UUID,
    request: GoldenImportRequest,
) -> dict[str, Any]:
    version = await _draft_version(session, context, dataset_id)
    if not version or version["status"] != "DRAFT":
        raise ValueError("legacy Golden cases can only be imported into a DRAFT version")
    params: dict[str, Any] = {"tenant_id": context.tenant_id}
    clause = ""
    if request.golden_case_ids:
        clause = " AND id = ANY(:ids)"
        params["ids"] = request.golden_case_ids
    rows = await session.execute(text(f"""
        SELECT id, name, category, project_type, input_spec, expected_criteria, tags
        FROM eval_golden_case
        WHERE tenant_id = :tenant_id AND is_deleted = 0 AND enabled = 1 {clause}
        ORDER BY id
    """), params)
    imported = 0
    skipped: list[dict[str, Any]] = []
    for row in rows.mappings():
        input_spec = _parse_storage(row["input_spec"])
        criteria = _parse_storage(row["expected_criteria"])
        request_text = input_spec.get("request") if isinstance(input_spec, dict) else input_spec
        reference = input_spec.get("reference_output") if isinstance(input_spec, dict) else None
        if not isinstance(request_text, str) or not request_text.strip() or not reference:
            skipped.append({"golden_case_id": row["id"], "reason": "request or reference output missing"})
            continue
        payload = DatasetCaseInput(
            category=row["category"] or "general",
            risk_level=RiskLevel.LOW,
            split=request.split,
            source_type="EXPERT",
            input_payload={"request": request_text.strip()},
            expected_state={"reference_output": str(reference)[:6000]},
            rubric={"criteria": criteria if isinstance(criteria, list) else [str(criteria)]},
            tool_policy=[],
            budget={"timeout_seconds": 600, "max_tool_calls": 0, "max_model_cost": 5},
            deterministic_checks=[{
                "type": "output",
                "operator": "not_empty",
            }],
            oracle_type="REFERENCE",
            prohibited_behaviors=["PRODUCTION_WRITE", "SECRET_DISCLOSURE"],
            source_group_id=f"legacy-golden:{row['id']}",
        )
        draft = _case_draft(payload)
        duplicate = await session.scalar(text("""
            SELECT EXISTS(SELECT 1 FROM eval_case
                WHERE tenant_id = :tenant_id AND dataset_version_id = :version_id
                  AND source_hash = :source_hash)
        """), {
            "tenant_id": context.tenant_id, "version_id": version["id"],
            "source_hash": canonical_case_hash(draft),
        })
        if duplicate:
            skipped.append({"golden_case_id": row["id"], "reason": "already imported"})
            continue
        await _insert_case(session, context, version["id"], payload, draft)
        imported += 1
    await _refresh_case_count(session, context, version["id"])
    await _audit(session, context, "LEGACY_GOLDEN_IMPORTED", "DATASET_VERSION", version["id"], {
        "imported": imported, "skipped": len(skipped),
    })
    return {"version_id": version["id"], "imported": imported, "skipped": skipped}


async def _load_release_drafts(
    session: AsyncSession, context: RequestContext, version_id: UUID
) -> list[CaseDraft]:
    rows = await session.execute(text("""
        SELECT external_id, category, risk_level, split, source_type, input_payload,
               expected_state, rubric, budget, deterministic_checks, tool_policy,
               oracle_type, initial_state_ref, prohibited_behaviors, source_group_id,
               source_parent_hash
        FROM eval_case WHERE tenant_id = :tenant_id AND dataset_version_id = :version_id
        ORDER BY id
    """), {"tenant_id": context.tenant_id, "version_id": version_id})
    return [CaseDraft(
        external_id=row["external_id"], category=row["category"],
        risk_level=RiskLevel(row["risk_level"]), split=Split(row["split"]),
        source_type=SourceType(row["source_type"]), input_payload=row["input_payload"],
        expected_state=row["expected_state"], rubric=row["rubric"], budget=row["budget"],
        deterministic_checks=row["deterministic_checks"], tool_policy=row["tool_policy"],
        oracle_type=OracleType(row["oracle_type"]), initial_state_ref=row["initial_state_ref"],
        prohibited_behaviors=tuple(row["prohibited_behaviors"] or []),
        source_group_id=row["source_group_id"], source_parent_hash=row["source_parent_hash"],
    ) for row in rows.mappings()]


async def submit_dataset_review(
    session: AsyncSession, context: RequestContext, version_id: UUID
) -> dict[str, Any]:
    drafts = await _load_release_drafts(session, context, version_id)
    errors = validate_release(drafts)
    if not drafts:
        errors.append("dataset version has no cases")
    if errors:
        return {"submitted": False, "errors": errors}
    result = await session.execute(text("""
        UPDATE eval_dataset_version SET status = 'REVIEWING', review_round = review_round + 1
        WHERE id = :version_id AND tenant_id = :tenant_id AND status = 'DRAFT'
        RETURNING review_round
    """), {"version_id": version_id, "tenant_id": context.tenant_id})
    row = result.mappings().one_or_none()
    if not row:
        raise ValueError("only a DRAFT version can be submitted for review")
    await _audit(session, context, "DATASET_REVIEW_SUBMITTED", "DATASET_VERSION", version_id, {
        "review_round": row["review_round"],
    })
    return {"submitted": True, "review_round": row["review_round"], "errors": []}


async def review_dataset_version(
    session: AsyncSession,
    context: RequestContext,
    version_id: UUID,
    decision: str,
    comment: str | None,
) -> dict[str, Any]:
    version = await session.execute(text("""
        SELECT v.status, v.review_round, d.created_by
        FROM eval_dataset_version v
        JOIN eval_dataset d ON d.id = v.dataset_id AND d.tenant_id = v.tenant_id
        WHERE v.id = :version_id AND v.tenant_id = :tenant_id
    """), {"version_id": version_id, "tenant_id": context.tenant_id})
    row = version.mappings().one_or_none()
    if not row or row["status"] != "REVIEWING":
        raise ValueError("dataset version is not awaiting review")
    if row["created_by"] == context.admin_id:
        raise ValueError("dataset creator cannot review their own dataset")
    already_reviewed = await session.scalar(text("""
        SELECT EXISTS(SELECT 1 FROM eval_dataset_review
            WHERE tenant_id = :tenant_id AND dataset_version_id = :version_id
              AND review_round = :review_round AND reviewer_id = :reviewer_id)
    """), {
        "tenant_id": context.tenant_id, "version_id": version_id,
        "review_round": row["review_round"], "reviewer_id": context.admin_id,
    })
    if already_reviewed:
        raise ValueError("reviewer already submitted a decision for this review round")
    await session.execute(text("""
        INSERT INTO eval_dataset_review
            (tenant_id, dataset_version_id, review_round, reviewer_id, decision, comment)
        VALUES (:tenant_id, :version_id, :review_round, :reviewer_id, :decision, :comment)
    """), {
        "tenant_id": context.tenant_id, "version_id": version_id,
        "review_round": row["review_round"], "reviewer_id": context.admin_id,
        "decision": decision, "comment": comment,
    })
    if decision == "REJECT":
        await session.execute(text("""
            UPDATE eval_dataset_version SET status = 'DRAFT'
            WHERE id = :version_id AND tenant_id = :tenant_id AND status = 'REVIEWING'
        """), {"version_id": version_id, "tenant_id": context.tenant_id})
    approvals = await session.scalar(text("""
        SELECT COUNT(*) FROM eval_dataset_review
        WHERE tenant_id = :tenant_id AND dataset_version_id = :version_id
          AND review_round = :review_round AND decision = 'APPROVE'
    """), {
        "tenant_id": context.tenant_id, "version_id": version_id,
        "review_round": row["review_round"],
    })
    await _audit(session, context, "DATASET_REVIEW_DECIDED", "DATASET_VERSION", version_id, {
        "review_round": row["review_round"], "decision": decision,
    })
    return {"decision": decision, "review_round": row["review_round"], "approvals": approvals}


async def publish_dataset_version(
    session: AsyncSession,
    context: RequestContext,
    version_id: UUID,
    expected_review_round: int,
) -> dict[str, Any]:
    drafts = await _load_release_drafts(session, context, version_id)
    errors = validate_release(drafts)
    if errors:
        raise ValueError("; ".join(errors))
    approvals = await session.scalar(text("""
        SELECT COUNT(*) FROM eval_dataset_review
        WHERE tenant_id = :tenant_id AND dataset_version_id = :version_id
          AND review_round = :review_round AND decision = 'APPROVE'
    """), {
        "tenant_id": context.tenant_id, "version_id": version_id,
        "review_round": expected_review_round,
    })
    if approvals < 2:
        raise ValueError("two independent approvals are required before publish")
    content_hash = hashlib.sha256(
        "".join(sorted(canonical_case_hash(draft) for draft in drafts)).encode()
    ).hexdigest()
    result = await session.execute(text("""
        UPDATE eval_dataset_version SET status = 'PUBLISHED', content_hash = :content_hash,
            case_count = :case_count, published_by = :published_by, published_at = now()
        WHERE id = :version_id AND tenant_id = :tenant_id AND status = 'REVIEWING'
          AND review_round = :review_round
    """), {
        "content_hash": content_hash, "case_count": len(drafts),
        "published_by": context.admin_id, "version_id": version_id,
        "tenant_id": context.tenant_id, "review_round": expected_review_round,
    })
    if result.rowcount != 1:
        raise ValueError("dataset version state or review round changed")
    await _audit(session, context, "DATASET_VERSION_PUBLISHED", "DATASET_VERSION", version_id, {
        "review_round": expected_review_round, "case_count": len(drafts),
        "content_hash": content_hash,
    })
    return {"id": version_id, "status": "PUBLISHED", "case_count": len(drafts), "content_hash": content_hash}


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
