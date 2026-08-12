-- 018: Complete the Agent evaluation dataset authoring, review and publish workflow.
-- Dataset cases remain mutable only while their version is DRAFT.

ALTER TABLE eval_dataset_version
    ADD COLUMN IF NOT EXISTS review_round INTEGER NOT NULL DEFAULT 0 CHECK (review_round >= 0);

ALTER TABLE eval_case
    ADD COLUMN IF NOT EXISTS oracle_type VARCHAR(24) NOT NULL DEFAULT 'HYBRID'
        CHECK (oracle_type IN ('STATE', 'EXACT', 'REFERENCE', 'TOOL_TRACE', 'HYBRID')),
    ADD COLUMN IF NOT EXISTS prohibited_behaviors JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS source_group_id VARCHAR(160),
    ADD COLUMN IF NOT EXISTS source_parent_hash CHAR(64);

-- Upgrade already-installed 006 schemas to tenant-bound foreign keys.
CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_dataset_tenant_id ON eval_dataset (tenant_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_dataset_version_tenant_id ON eval_dataset_version (tenant_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_agent_tenant_id ON eval_agent (tenant_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_agent_version_tenant_id ON eval_agent_version (tenant_id, id);
ALTER TABLE eval_dataset_version DROP CONSTRAINT IF EXISTS eval_dataset_version_dataset_id_fkey;
ALTER TABLE eval_dataset_version DROP CONSTRAINT IF EXISTS eval_dataset_version_dataset_tenant_fkey;
ALTER TABLE eval_dataset_version ADD CONSTRAINT eval_dataset_version_dataset_tenant_fkey
    FOREIGN KEY (tenant_id, dataset_id) REFERENCES eval_dataset(tenant_id, id);
ALTER TABLE eval_case DROP CONSTRAINT IF EXISTS eval_case_dataset_version_id_fkey;
ALTER TABLE eval_case DROP CONSTRAINT IF EXISTS eval_case_dataset_version_tenant_fkey;
ALTER TABLE eval_case ADD CONSTRAINT eval_case_dataset_version_tenant_fkey
    FOREIGN KEY (tenant_id, dataset_version_id) REFERENCES eval_dataset_version(tenant_id, id);
ALTER TABLE eval_agent_version DROP CONSTRAINT IF EXISTS eval_agent_version_agent_id_fkey;
ALTER TABLE eval_agent_version DROP CONSTRAINT IF EXISTS eval_agent_version_agent_tenant_fkey;
ALTER TABLE eval_agent_version ADD CONSTRAINT eval_agent_version_agent_tenant_fkey
    FOREIGN KEY (tenant_id, agent_id) REFERENCES eval_agent(tenant_id, id);

CREATE INDEX IF NOT EXISTS idx_eval_case_source_group
    ON eval_case (tenant_id, dataset_version_id, source_group_id);

CREATE TABLE IF NOT EXISTS eval_dataset_review (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id BIGINT NOT NULL,
    dataset_version_id UUID NOT NULL,
    review_round INTEGER NOT NULL CHECK (review_round > 0),
    reviewer_id BIGINT NOT NULL,
    decision VARCHAR(16) NOT NULL CHECK (decision IN ('APPROVE', 'REJECT')),
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, dataset_version_id, review_round, reviewer_id)
);

ALTER TABLE eval_dataset_review DROP CONSTRAINT IF EXISTS eval_dataset_review_dataset_version_id_fkey;
ALTER TABLE eval_dataset_review DROP CONSTRAINT IF EXISTS eval_dataset_review_version_tenant_fkey;
ALTER TABLE eval_dataset_review ADD CONSTRAINT eval_dataset_review_version_tenant_fkey
    FOREIGN KEY (tenant_id, dataset_version_id) REFERENCES eval_dataset_version(tenant_id, id);

CREATE INDEX IF NOT EXISTS idx_eval_dataset_review_version
    ON eval_dataset_review (tenant_id, dataset_version_id, review_round, created_at);

ALTER TABLE eval_dataset_review ENABLE ROW LEVEL SECURITY;
ALTER TABLE eval_dataset_review FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON eval_dataset_review;
CREATE POLICY tenant_isolation ON eval_dataset_review
    USING (tenant_id = current_setting('app.tenant_id', true)::bigint)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::bigint);

CREATE OR REPLACE FUNCTION eval_reject_frozen_case_mutation() RETURNS trigger AS $$
DECLARE
    target_version UUID;
    version_status VARCHAR(16);
BEGIN
    IF TG_OP = 'DELETE' THEN
        target_version := OLD.dataset_version_id;
    ELSE
        target_version := NEW.dataset_version_id;
    END IF;
    SELECT status INTO version_status FROM eval_dataset_version WHERE id = target_version;
    IF version_status IS DISTINCT FROM 'DRAFT' THEN
        RAISE EXCEPTION 'dataset cases are mutable only while the version is DRAFT';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_eval_case_draft_only ON eval_case;
CREATE TRIGGER trg_eval_case_draft_only
BEFORE INSERT OR UPDATE OR DELETE ON eval_case
FOR EACH ROW EXECUTE FUNCTION eval_reject_frozen_case_mutation();

CREATE OR REPLACE FUNCTION eval_reject_dataset_review_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'dataset reviews are append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_eval_dataset_review_append_only ON eval_dataset_review;
CREATE TRIGGER trg_eval_dataset_review_append_only
BEFORE UPDATE OR DELETE ON eval_dataset_review
FOR EACH ROW EXECUTE FUNCTION eval_reject_dataset_review_mutation();
