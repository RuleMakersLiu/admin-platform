-- 014: LLM 调用性能与成功指标 —— 支撑 AI 效果评测体系
-- 维度：响应速度(latency/ttft/tokens-per-s/success)、准确率、幻觉、生成效果、成本
-- 在已有 llm_usage_log(成本/token) 基础上补性能列；幂等。
ALTER TABLE llm_usage_log ADD COLUMN IF NOT EXISTS latency_ms INTEGER;        -- 单次调用总延迟(ms)
ALTER TABLE llm_usage_log ADD COLUMN IF NOT EXISTS ttft_ms INTEGER;           -- 流式首字延迟(ms)；非流式 NULL
ALTER TABLE llm_usage_log ADD COLUMN IF NOT EXISTS success SMALLINT DEFAULT 1;-- 1 成功 / 0 失败
ALTER TABLE llm_usage_log ADD COLUMN IF NOT EXISTS error VARCHAR(255);        -- 失败时错误摘要
ALTER TABLE llm_usage_log ADD COLUMN IF NOT EXISTS stage VARCHAR(64);         -- 调用来源/阶段(chat/vision/judge/requirement/prototype...)

CREATE INDEX IF NOT EXISTS idx_llm_usage_log_model ON llm_usage_log (model);
CREATE INDEX IF NOT EXISTS idx_llm_usage_log_create_time ON llm_usage_log (create_time);
CREATE INDEX IF NOT EXISTS idx_llm_usage_log_success ON llm_usage_log (success);
