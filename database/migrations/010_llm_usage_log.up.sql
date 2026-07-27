-- 010: LLM 用量记录表 —— 按 pipeline/tenant 归因，支撑 eval 成本列与成本看板
CREATE TABLE IF NOT EXISTS llm_usage_log (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT,
    pipeline_id VARCHAR(64),
    model VARCHAR(64) NOT NULL,
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    cost DOUBLE PRECISION NOT NULL DEFAULT 0,
    create_time BIGINT NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_log_tenant ON llm_usage_log (tenant_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_log_pipeline ON llm_usage_log (pipeline_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_log_create_time ON llm_usage_log (create_time);
