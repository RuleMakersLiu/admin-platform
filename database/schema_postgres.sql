-- PostgreSQL Schema for Admin Platform

-- 管理员表
CREATE TABLE IF NOT EXISTS sys_admin (
  id BIGSERIAL PRIMARY KEY,
  username VARCHAR(50) NOT NULL,
  password VARCHAR(100) NOT NULL,
  real_name VARCHAR(50),
  email VARCHAR(100),
  phone VARCHAR(20),
  avatar VARCHAR(255),
  group_id BIGINT,
  tenant_id BIGINT NOT NULL DEFAULT 0,
  status SMALLINT NOT NULL DEFAULT 1,
  last_login_time BIGINT,
  last_login_ip VARCHAR(50),
  create_time BIGINT NOT NULL,
  update_time BIGINT NOT NULL,
  CONSTRAINT uk_username_tenant UNIQUE (username, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_admin_group ON sys_admin(group_id);
CREATE INDEX IF NOT EXISTS idx_admin_tenant ON sys_admin(tenant_id);
CREATE INDEX IF NOT EXISTS idx_admin_status ON sys_admin(status);

-- 管理员组表
CREATE TABLE IF NOT EXISTS sys_admin_group (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(50) NOT NULL,
  parent_id BIGINT NOT NULL DEFAULT 0,
  path VARCHAR(500) NOT NULL DEFAULT '0',
  power TEXT,
  is_super SMALLINT NOT NULL DEFAULT 0,
  tenant_id BIGINT NOT NULL DEFAULT 0,
  sort INTEGER NOT NULL DEFAULT 0,
  status SMALLINT NOT NULL DEFAULT 1,
  create_time BIGINT NOT NULL,
  update_time BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_group_parent ON sys_admin_group(parent_id);
CREATE INDEX IF NOT EXISTS idx_group_tenant ON sys_admin_group(tenant_id);

-- 菜单表
CREATE TABLE IF NOT EXISTS sys_menu (
  id BIGSERIAL PRIMARY KEY,
  parent_id BIGINT NOT NULL DEFAULT 0,
  name VARCHAR(50) NOT NULL,
  path VARCHAR(255),
  component VARCHAR(255),
  permission VARCHAR(100),
  icon VARCHAR(50),
  type SMALLINT NOT NULL DEFAULT 1,
  visible SMALLINT NOT NULL DEFAULT 1,
  sort INTEGER NOT NULL DEFAULT 0,
  status SMALLINT NOT NULL DEFAULT 1,
  tenant_id BIGINT NOT NULL DEFAULT 0,
  create_time BIGINT NOT NULL,
  update_time BIGINT
);

CREATE INDEX IF NOT EXISTS idx_menu_parent ON sys_menu(parent_id);
CREATE INDEX IF NOT EXISTS idx_menu_tenant ON sys_menu(tenant_id);

-- 租户表
CREATE TABLE IF NOT EXISTS sys_tenant (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  code VARCHAR(50) NOT NULL,
  description VARCHAR(255),
  status SMALLINT NOT NULL DEFAULT 1,
  create_time BIGINT NOT NULL,
  update_time BIGINT,
  CONSTRAINT uk_tenant_code UNIQUE (code)
);

-- LLM配置表
CREATE TABLE IF NOT EXISTS sys_llm_config (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  provider VARCHAR(50) NOT NULL,
  base_url VARCHAR(255),
  api_key VARCHAR(255),
  model_name VARCHAR(100),
  max_tokens INTEGER DEFAULT 4096,
  temperature DECIMAL(3,2) DEFAULT 0.7,
  priority INTEGER DEFAULT 0,
  weight INTEGER DEFAULT 100,
  is_default BOOLEAN DEFAULT false,
  status SMALLINT DEFAULT 1,
  tenant_id BIGINT DEFAULT 0,
  admin_id BIGINT,
  extra_config JSONB,
  create_time BIGINT NOT NULL,
  update_time BIGINT
);

CREATE INDEX IF NOT EXISTS idx_llm_tenant ON sys_llm_config(tenant_id);
CREATE INDEX IF NOT EXISTS idx_llm_status ON sys_llm_config(status);

-- Git配置表
CREATE TABLE IF NOT EXISTS sys_git_config (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  platform VARCHAR(50) NOT NULL,
  host VARCHAR(255),
  access_token VARCHAR(255),
  ssh_key TEXT,
  default_branch VARCHAR(50) DEFAULT 'main',
  status SMALLINT DEFAULT 1,
  tenant_id BIGINT DEFAULT 0,
  admin_id BIGINT,
  create_time BIGINT NOT NULL,
  update_time BIGINT
);

-- 初始数据
INSERT INTO sys_tenant (id, name, code, status, create_time) VALUES
(1, '默认租户', 'default', 1, EXTRACT(EPOCH FROM NOW()) * 1000)
ON CONFLICT DO NOTHING;

INSERT INTO sys_admin_group (id, name, power, is_super, tenant_id, status, create_time, update_time) VALUES
(1, '超级管理员', '["*"]', 1, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000, EXTRACT(EPOCH FROM NOW()) * 1000)
ON CONFLICT DO NOTHING;

INSERT INTO sys_admin (id, username, password, real_name, group_id, tenant_id, status, create_time, update_time) VALUES
(1, 'admin', '\$2a\$10\$N.zmdr9k7uOCQb376NoUnuTJ8iAt6Z5EHsM8lE9lBOsl7iAt6Z5EH', '管理员', 1, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000, EXTRACT(EPOCH FROM NOW()) * 1000)
ON CONFLICT DO NOTHING;

-- 菜单数据
INSERT INTO sys_menu (id, parent_id, name, path, component, permission, icon, type, sort, status, tenant_id, create_time) VALUES
(1, 0, '系统管理', '/system', 'Layout', NULL, 'setting', 1, 99, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000),
(2, 1, '用户管理', '/system/admin', 'system/admin/index', 'system_admin_list', 'user', 2, 1, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000),
(3, 1, '角色管理', '/system/group', 'system/group/index', 'system_group_list', 'team', 2, 2, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000),
(4, 1, '菜单管理', '/system/menu', 'system/menu/index', 'system_menu_list', 'menu', 2, 3, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000),
(5, 1, '租户管理', '/system/tenant', 'system/tenant/index', 'system_tenant_list', 'bank', 2, 4, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000)
ON CONFLICT DO NOTHING;
