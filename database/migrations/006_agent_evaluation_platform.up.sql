-- Agent evaluation control-plane schema (PostgreSQL).
-- External execution remains disabled by service configuration until G0/G1 pass.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS eval_agent (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    name VARCHAR(120) NOT NULL,
    description TEXT,
    adapter_type VARCHAR(32) NOT NULL CHECK (adapter_type IN ('HTTP', 'SSE', 'OPENAI_COMPATIBLE', 'CONTAINER', 'CLI')),
    isolation_scope VARCHAR(24) NOT NULL CHECK (isolation_scope IN ('FULL', 'RUNNER_ONLY')),
    risk_level VARCHAR(16) NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'PROHIBITED')),
    status VARCHAR(16) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')),
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at TIMESTAMPTZ,
    UNIQUE (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS eval_agent_version (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    agent_id UUID NOT NULL REFERENCES eval_agent(id),
    version VARCHAR(80) NOT NULL,
    endpoint_ref VARCHAR(255),
    image_digest VARCHAR(255),
    model_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    prompt_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    skill_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    tool_config JSONB NOT NULL DEFAULT '[]'::jsonb,
    secret_ref VARCHAR(255),
    security_status VARCHAR(24) NOT NULL DEFAULT 'PENDING' CHECK (security_status IN ('PENDING', 'APPROVED', 'REJECTED', 'REVOKED')),
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, agent_id, version),
    CHECK (image_digest IS NULL OR image_digest ~ '^[-a-z0-9./]+@sha256:[a-f0-9]{64}$')
);

CREATE TABLE IF NOT EXISTS eval_dataset (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    name VARCHAR(160) NOT NULL,
    description TEXT,
    visibility VARCHAR(16) NOT NULL DEFAULT 'PRIVATE' CHECK (visibility IN ('PRIVATE', 'SHARED')),
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at TIMESTAMPTZ,
    UNIQUE (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS eval_dataset_version (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    dataset_id UUID NOT NULL REFERENCES eval_dataset(id),
    version INTEGER NOT NULL CHECK (version > 0),
    status VARCHAR(16) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'REVIEWING', 'PUBLISHED', 'ARCHIVED')),
    content_hash CHAR(64),
    case_count INTEGER NOT NULL DEFAULT 0 CHECK (case_count >= 0),
    published_by BIGINT,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, dataset_id, version),
    CHECK ((status = 'PUBLISHED' AND published_by IS NOT NULL AND published_at IS NOT NULL AND content_hash IS NOT NULL) OR status <> 'PUBLISHED')
);

CREATE TABLE IF NOT EXISTS eval_case (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    dataset_version_id UUID NOT NULL REFERENCES eval_dataset_version(id),
    category VARCHAR(80) NOT NULL,
    risk_level VARCHAR(16) NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    split VARCHAR(16) NOT NULL CHECK (split IN ('DEVELOPMENT', 'REGRESSION', 'HIDDEN')),
    input_payload JSONB NOT NULL,
    initial_state_ref VARCHAR(255),
    expected_state JSONB NOT NULL,
    rubric JSONB NOT NULL,
    tool_policy JSONB NOT NULL DEFAULT '[]'::jsonb,
    budget JSONB NOT NULL,
    deterministic_checks JSONB NOT NULL,
    source_type VARCHAR(24) NOT NULL CHECK (source_type IN ('DEIDENTIFIED', 'EXPERT', 'AI_VARIANT', 'SYNTHETIC')),
    source_hash CHAR(64) NOT NULL,
    reviewed_by BIGINT,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, dataset_version_id, external_id),
    UNIQUE (tenant_id, dataset_version_id, source_hash)
);

CREATE TABLE IF NOT EXISTS eval_evaluator (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    name VARCHAR(120) NOT NULL,
    version VARCHAR(80) NOT NULL,
    evaluator_type VARCHAR(24) NOT NULL CHECK (evaluator_type IN ('SECURITY', 'STATE', 'SCHEMA', 'TOOL', 'CHECKPOINT', 'LLM_JUDGE', 'HUMAN')),
    config JSONB NOT NULL,
    prompt_hash CHAR(64),
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name, version)
);

CREATE TABLE IF NOT EXISTS eval_price_book (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    version VARCHAR(80) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    prices JSONB NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, version)
);

CREATE TABLE IF NOT EXISTS eval_experiment (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    name VARCHAR(160) NOT NULL,
    dataset_version_id UUID NOT NULL REFERENCES eval_dataset_version(id),
    price_book_id UUID NOT NULL REFERENCES eval_price_book(id),
    sandbox_policy_version VARCHAR(80) NOT NULL,
    repetitions INTEGER NOT NULL CHECK (repetitions BETWEEN 1 AND 10),
    experiment_type VARCHAR(24) NOT NULL CHECK (experiment_type IN ('PAIRED_OFFLINE', 'SHADOW_REPLAY')),
    status VARCHAR(24) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'APPROVED', 'QUEUED', 'RUNNING', 'SCORING', 'REVIEWING', 'COMPLETED', 'PAUSED', 'CANCELLED', 'SECURITY_STOPPED', 'PARTIAL', 'FAILED')),
    execution_order_seed BIGINT NOT NULL,
    security_approval_id UUID,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ,
    UNIQUE (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS eval_variant (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    experiment_id UUID NOT NULL REFERENCES eval_experiment(id),
    agent_version_id UUID NOT NULL REFERENCES eval_agent_version(id),
    label VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, experiment_id, label),
    UNIQUE (tenant_id, experiment_id, agent_version_id)
);

CREATE TABLE IF NOT EXISTS eval_trial (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    experiment_id UUID NOT NULL REFERENCES eval_experiment(id),
    variant_id UUID NOT NULL REFERENCES eval_variant(id),
    case_id UUID NOT NULL REFERENCES eval_case(id),
    repetition INTEGER NOT NULL CHECK (repetition > 0),
    status VARCHAR(24) NOT NULL DEFAULT 'CREATED' CHECK (status IN ('CREATED', 'QUEUED', 'RUNNING', 'SCORING', 'REVIEWING', 'SUCCEEDED', 'FAILED', 'TIMED_OUT', 'BUDGET_EXCEEDED', 'POLICY_DENIED', 'SECURITY_TERMINATED', 'INFRA_ERROR', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE (tenant_id, experiment_id, variant_id, case_id, repetition)
);

CREATE TABLE IF NOT EXISTS eval_trial_attempt (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    trial_id UUID NOT NULL REFERENCES eval_trial(id),
    attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
    run_idempotency_key VARCHAR(180) NOT NULL,
    status VARCHAR(24) NOT NULL,
    isolation_scope VARCHAR(24) NOT NULL CHECK (isolation_scope IN ('FULL', 'RUNNER_ONLY')),
    image_digest VARCHAR(255),
    sandbox_instance_id VARCHAR(255),
    error_class VARCHAR(32) CHECK (error_class IS NULL OR error_class IN ('AGENT', 'INFRA', 'SECURITY', 'POLICY', 'BUDGET')),
    error_code VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE (tenant_id, trial_id, attempt_no),
    UNIQUE (run_idempotency_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_trial_one_active_attempt
ON eval_trial_attempt (trial_id)
WHERE status IN ('CREATED', 'QUEUED', 'RUNNING', 'COLLECTING');

CREATE TABLE IF NOT EXISTS eval_score (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    trial_id UUID NOT NULL REFERENCES eval_trial(id),
    evaluator_id UUID NOT NULL REFERENCES eval_evaluator(id),
    evaluator_version VARCHAR(80) NOT NULL,
    score NUMERIC(10,6),
    passed BOOLEAN,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    score_idempotency_key VARCHAR(220) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (score_idempotency_key)
);

CREATE TABLE IF NOT EXISTS eval_review_assignment (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    experiment_id UUID NOT NULL REFERENCES eval_experiment(id),
    case_id UUID NOT NULL REFERENCES eval_case(id),
    left_trial_id UUID NOT NULL REFERENCES eval_trial(id),
    right_trial_id UUID NOT NULL REFERENCES eval_trial(id),
    display_a_trial_id UUID NOT NULL REFERENCES eval_trial(id),
    display_b_trial_id UUID NOT NULL REFERENCES eval_trial(id),
    blind_order_hash CHAR(64) NOT NULL,
    reviewer_id BIGINT NOT NULL,
    review_round SMALLINT NOT NULL CHECK (review_round IN (1, 2, 3)),
    status VARCHAR(16) NOT NULL DEFAULT 'ASSIGNED' CHECK (status IN ('ASSIGNED', 'SUBMITTED', 'ARBITRATION', 'CANCELLED')),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    submitted_at TIMESTAMPTZ,
    identity_revealed_at TIMESTAMPTZ,
    CHECK (left_trial_id <> right_trial_id),
    CHECK (display_a_trial_id <> display_b_trial_id),
    CHECK (
        (display_a_trial_id = left_trial_id AND display_b_trial_id = right_trial_id) OR
        (display_a_trial_id = right_trial_id AND display_b_trial_id = left_trial_id)
    ),
    UNIQUE (tenant_id, experiment_id, case_id, reviewer_id)
);

CREATE TABLE IF NOT EXISTS eval_human_review (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    assignment_id UUID NOT NULL REFERENCES eval_review_assignment(id),
    reviewer_id BIGINT NOT NULL,
    preference VARCHAR(24) CHECK (preference IS NULL OR preference IN ('A_STRONG', 'A_SLIGHT', 'TIE', 'B_SLIGHT', 'B_STRONG', 'BOTH_FAILED')),
    absolute_scores JSONB,
    security_passed BOOLEAN NOT NULL,
    comment TEXT,
    correction_of UUID REFERENCES eval_human_review(id),
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_human_review_original
ON eval_human_review (tenant_id, assignment_id)
WHERE correction_of IS NULL;

CREATE TABLE IF NOT EXISTS eval_security_approval (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    resource_type VARCHAR(32) NOT NULL,
    resource_id UUID NOT NULL,
    action VARCHAR(48) NOT NULL,
    requested_by BIGINT NOT NULL,
    first_approved_by BIGINT,
    second_approved_by BIGINT,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'REVOKED')),
    evidence_ref VARCHAR(255),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ,
    CHECK (first_approved_by IS NULL OR first_approved_by <> requested_by),
    CHECK (second_approved_by IS NULL OR second_approved_by NOT IN (requested_by, first_approved_by)),
    CHECK (status <> 'APPROVED' OR (first_approved_by IS NOT NULL AND second_approved_by IS NOT NULL))
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_eval_experiment_security_approval') THEN
        ALTER TABLE eval_experiment
            ADD CONSTRAINT fk_eval_experiment_security_approval
            FOREIGN KEY (security_approval_id) REFERENCES eval_security_approval(id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS eval_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    actor_id BIGINT,
    actor_type VARCHAR(24) NOT NULL,
    action VARCHAR(120) NOT NULL,
    resource_type VARCHAR(80) NOT NULL,
    resource_id VARCHAR(120) NOT NULL,
    request_id VARCHAR(120),
    source_ip INET,
    before_hash CHAR(64),
    after_hash CHAR(64),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_eval_agent_tenant ON eval_agent (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_eval_case_dataset ON eval_case (tenant_id, dataset_version_id, split);
CREATE INDEX IF NOT EXISTS idx_eval_experiment_tenant ON eval_experiment (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_eval_trial_experiment ON eval_trial (tenant_id, experiment_id, status);
CREATE INDEX IF NOT EXISTS idx_eval_review_queue ON eval_review_assignment (tenant_id, reviewer_id, status, assigned_at);
CREATE INDEX IF NOT EXISTS idx_eval_audit_resource ON eval_audit_log (tenant_id, resource_type, resource_id, created_at DESC);

CREATE OR REPLACE FUNCTION eval_reject_frozen_experiment_update() RETURNS trigger AS $$
BEGIN
    IF OLD.status NOT IN ('DRAFT', 'APPROVED') AND (
        NEW.dataset_version_id IS DISTINCT FROM OLD.dataset_version_id OR
        NEW.price_book_id IS DISTINCT FROM OLD.price_book_id OR
        NEW.sandbox_policy_version IS DISTINCT FROM OLD.sandbox_policy_version OR
        NEW.repetitions IS DISTINCT FROM OLD.repetitions OR
        NEW.experiment_type IS DISTINCT FROM OLD.experiment_type OR
        NEW.execution_order_seed IS DISTINCT FROM OLD.execution_order_seed
    ) THEN
        RAISE EXCEPTION 'started evaluation experiment configuration is immutable';
    END IF;
    IF OLD.status = 'SECURITY_STOPPED' AND NEW.status <> 'SECURITY_STOPPED' THEN
        RAISE EXCEPTION 'security-stopped experiment requires security-admin recovery workflow';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_eval_experiment_immutable ON eval_experiment;
CREATE TRIGGER trg_eval_experiment_immutable
BEFORE UPDATE ON eval_experiment
FOR EACH ROW EXECUTE FUNCTION eval_reject_frozen_experiment_update();

CREATE OR REPLACE FUNCTION eval_reject_human_review_update() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'human reviews are append-only; create a correction record';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_eval_human_review_append_only ON eval_human_review;
CREATE TRIGGER trg_eval_human_review_append_only
BEFORE UPDATE OR DELETE ON eval_human_review
FOR EACH ROW EXECUTE FUNCTION eval_reject_human_review_update();

CREATE OR REPLACE FUNCTION eval_validate_review_assignment() RETURNS trigger AS $$
DECLARE
    case_split VARCHAR(16);
    case_creator BIGINT;
    conflicting_agent_maintainers INTEGER;
    valid_trial_count INTEGER;
BEGIN
    SELECT split, created_by INTO case_split, case_creator
    FROM eval_case
    WHERE id = NEW.case_id AND tenant_id = NEW.tenant_id;

    IF case_split IS NULL THEN
        RAISE EXCEPTION 'review case does not belong to tenant';
    END IF;
    IF case_split = 'HIDDEN' AND case_creator = NEW.reviewer_id THEN
        RAISE EXCEPTION 'hidden-case creator cannot review their own case';
    END IF;

    SELECT COUNT(*) INTO valid_trial_count
    FROM eval_trial
    WHERE tenant_id = NEW.tenant_id
      AND experiment_id = NEW.experiment_id
      AND case_id = NEW.case_id
      AND id IN (NEW.left_trial_id, NEW.right_trial_id);
    IF valid_trial_count <> 2 THEN
        RAISE EXCEPTION 'A/B trials must belong to the same tenant, experiment, and case';
    END IF;

    SELECT COUNT(*) INTO conflicting_agent_maintainers
    FROM eval_trial t
    JOIN eval_variant v ON v.id = t.variant_id AND v.tenant_id = t.tenant_id
    JOIN eval_agent_version av ON av.id = v.agent_version_id AND av.tenant_id = v.tenant_id
    WHERE t.id IN (NEW.left_trial_id, NEW.right_trial_id)
      AND t.tenant_id = NEW.tenant_id
      AND av.created_by = NEW.reviewer_id;
    IF conflicting_agent_maintainers > 0 THEN
        RAISE EXCEPTION 'Agent version maintainer cannot review their own Agent';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_eval_review_assignment_validate ON eval_review_assignment;
CREATE TRIGGER trg_eval_review_assignment_validate
BEFORE INSERT ON eval_review_assignment
FOR EACH ROW EXECUTE FUNCTION eval_validate_review_assignment();

CREATE OR REPLACE FUNCTION eval_reject_review_assignment_identity_update() RETURNS trigger AS $$
BEGIN
    IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR
       NEW.experiment_id IS DISTINCT FROM OLD.experiment_id OR
       NEW.case_id IS DISTINCT FROM OLD.case_id OR
       NEW.left_trial_id IS DISTINCT FROM OLD.left_trial_id OR
       NEW.right_trial_id IS DISTINCT FROM OLD.right_trial_id OR
       NEW.display_a_trial_id IS DISTINCT FROM OLD.display_a_trial_id OR
       NEW.display_b_trial_id IS DISTINCT FROM OLD.display_b_trial_id OR
       NEW.blind_order_hash IS DISTINCT FROM OLD.blind_order_hash OR
       NEW.reviewer_id IS DISTINCT FROM OLD.reviewer_id OR
       NEW.review_round IS DISTINCT FROM OLD.review_round THEN
        RAISE EXCEPTION 'review identity mapping is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_eval_review_assignment_immutable ON eval_review_assignment;
CREATE TRIGGER trg_eval_review_assignment_immutable
BEFORE UPDATE ON eval_review_assignment
FOR EACH ROW EXECUTE FUNCTION eval_reject_review_assignment_identity_update();

CREATE OR REPLACE FUNCTION eval_validate_human_review_actor() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM eval_review_assignment a
        WHERE a.id = NEW.assignment_id
          AND a.tenant_id = NEW.tenant_id
          AND a.reviewer_id = NEW.reviewer_id
          AND (
              (NEW.correction_of IS NULL AND a.status IN ('ASSIGNED', 'ARBITRATION')) OR
              (NEW.correction_of IS NOT NULL AND a.status = 'SUBMITTED')
          )
    ) THEN
        RAISE EXCEPTION 'review actor does not match active assignment';
    END IF;
    IF NEW.correction_of IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM eval_human_review original
        WHERE original.id = NEW.correction_of
          AND original.tenant_id = NEW.tenant_id
          AND original.assignment_id = NEW.assignment_id
    ) THEN
        RAISE EXCEPTION 'correction must reference a review for the same assignment';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_eval_human_review_actor ON eval_human_review;
CREATE TRIGGER trg_eval_human_review_actor
BEFORE INSERT ON eval_human_review
FOR EACH ROW EXECUTE FUNCTION eval_validate_human_review_actor();

DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'eval_agent', 'eval_agent_version', 'eval_dataset', 'eval_dataset_version',
        'eval_case', 'eval_evaluator', 'eval_price_book', 'eval_experiment',
        'eval_variant', 'eval_trial', 'eval_trial_attempt', 'eval_score', 'eval_review_assignment',
        'eval_human_review', 'eval_security_approval', 'eval_audit_log'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.tenant_id'', true)::bigint) WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true)::bigint)',
            table_name
        );
    END LOOP;
END $$;

-- Menu entries do not grant permissions. Roles must be assigned explicitly.
DO $$
DECLARE
    root_id BIGINT;
    now_ms BIGINT := (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT;
    item RECORD;
BEGIN
    SELECT id INTO root_id FROM sys_menu WHERE path = '/evaluation' AND parent_id = 0 LIMIT 1;
    IF root_id IS NULL THEN
        INSERT INTO sys_menu (parent_id, name, path, component, permission, icon, type, visible, sort, status, tenant_id, create_time, update_time)
        VALUES (0, 'Agent测评', '/evaluation', 'Layout', NULL, 'ExperimentOutlined', 1, 1, 40, 1, 1, now_ms, now_ms)
        RETURNING id INTO root_id;
    END IF;

    FOR item IN SELECT * FROM (VALUES
        ('Agent接入', '/evaluation/agents', 'evaluation/index', 'eval:agent:list', 0),
        ('数据集工厂', '/evaluation/datasets', 'evaluation/index', 'eval:dataset:list', 1),
        ('实验与A/B', '/evaluation/experiments', 'evaluation/index', 'eval:experiment:view', 2),
        ('人工审核', '/evaluation/reviews', 'evaluation/index', 'eval:review:score', 3),
        ('安全与审计', '/evaluation/security', 'evaluation/index', 'eval:security:approve', 4)
    ) AS v(name, path, component, permission, sort) LOOP
        INSERT INTO sys_menu (parent_id, name, path, component, permission, icon, type, visible, sort, status, tenant_id, create_time, update_time)
        SELECT root_id, item.name, item.path, item.component, item.permission, 'ExperimentOutlined', 2, 1, item.sort, 1, 1, now_ms, now_ms
        WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = item.permission);
    END LOOP;

    FOR item IN SELECT permission FROM (VALUES
        ('eval:agent:view'), ('eval:agent:create'), ('eval:agent:edit'), ('eval:agent:test'),
        ('eval:dataset:create'), ('eval:dataset:review'), ('eval:dataset:publish'),
        ('eval:experiment:create'), ('eval:experiment:run'), ('eval:experiment:cancel'),
        ('eval:review:arbitrate'), ('eval:artifact:view'), ('eval:artifact:download'), ('eval:cost:view')
    ) AS v(permission) LOOP
        INSERT INTO sys_menu (parent_id, name, permission, type, visible, sort, status, tenant_id, create_time, update_time)
        SELECT root_id, item.permission, item.permission, 3, 0, 100, 1, 1, now_ms, now_ms
        WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = item.permission);
    END LOOP;
END $$;
