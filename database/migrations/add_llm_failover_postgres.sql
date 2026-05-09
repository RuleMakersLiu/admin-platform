-- =============================================
-- LLM故障转移功能 - PostgreSQL迁移
-- 版本: 1.0.0
-- 日期: 2026-03-08
-- =============================================

-- ---------------------------------------------
-- 1. 为sys_llm_config表添加故障转移相关字段
-- ---------------------------------------------

-- 添加priority字段 (优先级，数字越小优先级越高)
ALTER TABLE sys_llm_config ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 0;

-- 添加weight字段 (权重，用于负载均衡)
ALTER TABLE sys_llm_config ADD COLUMN IF NOT EXISTS weight INTEGER DEFAULT 100;

-- 为priority和status添加复合索引
CREATE INDEX IF NOT EXISTS idx_priority_status ON sys_llm_config(priority, status);

-- ---------------------------------------------
-- 2. 创建故障转移日志表
-- ---------------------------------------------

DROP TABLE IF EXISTS agent_failover_log;
CREATE TABLE agent_failover_log (
  id BIGSERIAL PRIMARY KEY,
  session_id VARCHAR(64),
  original_config_id BIGINT NOT NULL,
  failover_config_id BIGINT NOT NULL,
  reason VARCHAR(255) NOT NULL,
  original_error TEXT,
  retry_count INTEGER DEFAULT 0,
  tenant_id BIGINT DEFAULT 0,
  create_time BIGINT NOT NULL
);

CREATE INDEX idx_failover_session ON agent_failover_log(session_id);
CREATE INDEX idx_failover_tenant ON agent_failover_log(tenant_id);
CREATE INDEX idx_failover_time ON agent_failover_log(create_time);

-- ---------------------------------------------
-- 3. 插入示例LLM配置数据
-- ---------------------------------------------

-- 插入Anthropic配置示例 (主提供商)
INSERT INTO sys_llm_config
(name, provider, base_url, api_key, model_name, max_tokens, temperature, priority, weight, is_default, status, tenant_id, admin_id, create_time, update_time)
VALUES
('Claude Sonnet', 'anthropic', 'https://api.anthropic.com', 'your-anthropic-api-key', 'claude-sonnet-4-20250514', 4096, 0.70, 0, 100, true, 1, 0, 1, EXTRACT(EPOCH FROM NOW()) * 1000, EXTRACT(EPOCH FROM NOW()) * 1000)
ON CONFLICT DO NOTHING;

-- 插入OpenAI配置示例 (备用提供商)
INSERT INTO sys_llm_config
(name, provider, base_url, api_key, model_name, max_tokens, temperature, priority, weight, is_default, status, tenant_id, admin_id, create_time, update_time)
VALUES
('GPT-4o', 'openai', 'https://api.openai.com', 'your-openai-api-key', 'gpt-4o', 4096, 0.70, 10, 80, false, 1, 0, 1, EXTRACT(EPOCH FROM NOW()) * 1000, EXTRACT(EPOCH FROM NOW()) * 1000)
ON CONFLICT DO NOTHING;

-- 插入自定义API配置示例 (第三备用)
INSERT INTO sys_llm_config
(name, provider, base_url, api_key, model_name, max_tokens, temperature, priority, weight, is_default, status, tenant_id, admin_id, create_time, update_time)
VALUES
('Custom LLM', 'custom', 'https://your-custom-llm.com/v1', 'your-custom-api-key', 'custom-model', 4096, 0.70, 20, 50, false, 0, 0, 1, EXTRACT(EPOCH FROM NOW()) * 1000, EXTRACT(EPOCH FROM NOW()) * 1000)
ON CONFLICT DO NOTHING;
