-- Add multi-tenant user ownership and project generation scope.

CREATE TABLE IF NOT EXISTS sys_admin_tenant (
    id BIGSERIAL PRIMARY KEY,
    admin_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    is_default SMALLINT NOT NULL DEFAULT 0,
    create_time BIGINT NOT NULL DEFAULT ((EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT),
    update_time BIGINT NOT NULL DEFAULT ((EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT),
    CONSTRAINT uk_sys_admin_tenant UNIQUE (admin_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_sys_admin_tenant_admin ON sys_admin_tenant(admin_id);
CREATE INDEX IF NOT EXISTS idx_sys_admin_tenant_tenant ON sys_admin_tenant(tenant_id);

CREATE TABLE IF NOT EXISTS project_tenant_scope (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    enabled SMALLINT NOT NULL DEFAULT 1,
    created_by BIGINT NOT NULL DEFAULT 0,
    create_time BIGINT NOT NULL DEFAULT ((EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT),
    update_time BIGINT NOT NULL DEFAULT ((EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT),
    CONSTRAINT uk_project_tenant_scope UNIQUE (project_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_project_tenant_scope_project ON project_tenant_scope(project_id);
CREATE INDEX IF NOT EXISTS idx_project_tenant_scope_tenant ON project_tenant_scope(tenant_id);
CREATE INDEX IF NOT EXISTS idx_project_tenant_scope_enabled ON project_tenant_scope(enabled);

INSERT INTO sys_admin_tenant (admin_id, tenant_id, is_default)
SELECT id, tenant_id, 1
FROM sys_admin
WHERE is_deleted = 0
  AND tenant_id IS NOT NULL
ON CONFLICT (admin_id, tenant_id) DO UPDATE SET
    is_default = CASE WHEN sys_admin_tenant.tenant_id = EXCLUDED.tenant_id THEN 1 ELSE sys_admin_tenant.is_default END,
    update_time = ((EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT);

INSERT INTO project_tenant_scope (project_id, tenant_id, enabled, created_by)
SELECT project_id, COALESCE(tenant_id, 0), 1, COALESCE(confirmed_by, 0)
FROM project_knowledge
WHERE project_id IS NOT NULL
ON CONFLICT (project_id, tenant_id) DO UPDATE SET
    enabled = 1,
    update_time = ((EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT);
