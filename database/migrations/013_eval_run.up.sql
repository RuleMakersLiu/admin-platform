-- 013: 评测运行记录表 —— 关联 golden case 与 pipeline 执行，承载自动评审结果
CREATE TABLE IF NOT EXISTS eval_run (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    golden_case_id BIGINT NOT NULL,
    pipeline_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    overall_score INT,
    judgment TEXT,
    create_time BIGINT NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT,
    update_time BIGINT NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT,
    is_deleted INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_eval_run_tenant ON eval_run (tenant_id);
CREATE INDEX IF NOT EXISTS idx_eval_run_pipeline ON eval_run (pipeline_id);
CREATE INDEX IF NOT EXISTS idx_eval_run_golden_case ON eval_run (golden_case_id);
