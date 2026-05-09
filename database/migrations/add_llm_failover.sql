-- =============================================
-- LLM故障转移功能 - 数据库迁移
-- 版本: 1.0.0
-- 日期: 2026-03-01
-- =============================================

SET NAMES utf8mb4;

-- ---------------------------------------------
-- 1. 为sys_llm_config表添加故障转移相关字段
-- ---------------------------------------------

-- 添加priority字段 (优先级，数字越小优先级越高)
ALTER TABLE `sys_llm_config` ADD COLUMN `priority` INT DEFAULT 0 COMMENT '优先级，数字越小优先级越高' AFTER `extra_config`;

-- 添加weight字段 (权重，用于负载均衡)
ALTER TABLE `sys_llm_config` ADD COLUMN `weight` INT DEFAULT 100 COMMENT '权重，用于负载均衡' AFTER `priority`;

-- 为priority和status添加复合索引
ALTER TABLE `sys_llm_config` ADD INDEX `idx_priority_status` (`priority`, `status`);

-- ---------------------------------------------
-- 2. 创建故障转移日志表
-- ---------------------------------------------

DROP TABLE IF EXISTS `agent_failover_log`;
CREATE TABLE `agent_failover_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `session_id` varchar(64) DEFAULT NULL COMMENT '会话ID',
  `original_config_id` bigint(20) NOT NULL COMMENT '原始配置ID',
  `failover_config_id` bigint(20) NOT NULL COMMENT '故障转移目标配置ID',
  `reason` varchar(255) NOT NULL COMMENT '故障转移原因',
  `original_error` text COMMENT '原始错误信息',
  `retry_count` int(11) DEFAULT 0 COMMENT '重试次数',
  `tenant_id` bigint(20) DEFAULT 0 COMMENT '租户ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(毫秒)',
  PRIMARY KEY (`id`),
  KEY `idx_session_id` (`session_id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='LLM故障转移日志表';

-- ---------------------------------------------
-- 3. 插入示例LLM配置数据
-- ---------------------------------------------

-- 插入Anthropic配置示例 (主提供商)
INSERT INTO `sys_llm_config`
(`name`, `provider`, `base_url`, `api_key`, `model_name`, `max_tokens`, `temperature`, `priority`, `weight`, `is_default`, `status`, `tenant_id`, `admin_id`, `create_time`, `update_time`)
VALUES
('Claude Sonnet', 'anthropic', 'https://api.anthropic.com', 'your-anthropic-api-key', 'claude-sonnet-4-20250514', 4096, 0.70, 0, 100, 1, 1, 0, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000);

-- 插入OpenAI配置示例 (备用提供商)
INSERT INTO `sys_llm_config`
(`name`, `provider`, `base_url`, `api_key`, `model_name`, `max_tokens`, `temperature`, `priority`, `weight`, `is_default`, `status`, `tenant_id`, `admin_id`, `create_time`, `update_time`)
VALUES
('GPT-4o', 'openai', 'https://api.openai.com', 'your-openai-api-key', 'gpt-4o', 4096, 0.70, 10, 80, 0, 1, 0, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000);

-- 插入自定义API配置示例 (第三备用)
INSERT INTO `sys_llm_config`
(`name`, `provider`, `base_url`, `api_key`, `model_name`, `max_tokens`, `temperature`, `priority`, `weight`, `is_default`, `status`, `tenant_id`, `admin_id`, `create_time`, `update_time`)
VALUES
('Custom LLM', 'custom', 'https://your-custom-llm.com/v1', 'your-custom-api-key', 'custom-model', 4096, 0.70, 20, 50, 0, 0, 0, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000);

-- ---------------------------------------------
-- 4. 添加LLM健康检查菜单
-- ---------------------------------------------

INSERT INTO `sys_menu`
(`parent_id`, `name`, `path`, `component`, `permission`, `icon`, `type`, `visible`, `sort`, `status`, `tenant_id`, `create_time`, `update_time`)
VALUES
(1, 'LLM健康检查', '/system/llm-health', 'system/llm-health/index', 'system_llm_health', 'api', 2, 1, 52, 1, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000);
