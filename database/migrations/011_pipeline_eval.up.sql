-- 011_pipeline_eval.up.sql
-- Eval 评测闭环：pipeline_eval_result 表（pipeline 终态聚合各 stage 评测信号为可 SQL 聚合的扁平列）
-- 幂等：CREATE TABLE/INDEX IF NOT EXISTS，与 ensure_runtime_schema 保持一致

CREATE TABLE IF NOT EXISTS pipeline_eval_result (
    id BIGSERIAL PRIMARY KEY,
    eval_id VARCHAR(64) NOT NULL,
    pipeline_id VARCHAR(64) NOT NULL,
    tenant_id BIGINT NOT NULL,
    project_id VARCHAR(64),
    status VARCHAR(32) NOT NULL,
    overall_score INTEGER,
    pm_quality_score INTEGER,
    design_quality_score INTEGER,
    preview_quality_score INTEGER,
    review_passed SMALLINT,
    tests_passed SMALLINT,
    tests_total INTEGER,
    tests_passed_count INTEGER,
    tests_failed_count INTEGER,
    retry_count INTEGER,
    auto_repair_iterations INTEGER,
    framework VARCHAR(32),
    test_duration_ms INTEGER,
    stage_scores TEXT,
    cost_input_tokens BIGINT,
    cost_output_tokens BIGINT,
    create_time BIGINT NOT NULL,
    update_time BIGINT NOT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS uk_pipeline_eval_id ON pipeline_eval_result(eval_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_eval_pipeline ON pipeline_eval_result(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_eval_tenant_time ON pipeline_eval_result(tenant_id, create_time);
