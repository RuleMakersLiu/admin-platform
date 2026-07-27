-- 009: 评测 Golden Case 表 —— 固定 输入→期望标准，支撑回归评测与质量门控
CREATE TABLE IF NOT EXISTS eval_golden_case (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    name VARCHAR(128) NOT NULL,
    category VARCHAR(64) NOT NULL DEFAULT 'general',
    project_type VARCHAR(64),
    input_spec TEXT NOT NULL,
    expected_criteria TEXT NOT NULL,
    tags VARCHAR(256),
    enabled INT NOT NULL DEFAULT 1,
    created_by BIGINT,
    create_time BIGINT NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT,
    update_time BIGINT NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT,
    is_deleted INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_eval_golden_case_tenant ON eval_golden_case (tenant_id);
CREATE INDEX IF NOT EXISTS idx_eval_golden_case_category ON eval_golden_case (category);
