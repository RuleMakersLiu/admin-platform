-- Project-level Skill driven development pipeline.
-- PostgreSQL migration for the first-version frontend + contract + review flow.

CREATE TABLE IF NOT EXISTS project_knowledge (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL,
    project_name VARCHAR(200) NOT NULL DEFAULT '',
    repo_url VARCHAR(512),
    language VARCHAR(50),
    framework VARCHAR(100),
    project_brief TEXT,
    tech_summary TEXT,
    architecture TEXT,
    component_patterns TEXT,
    api_patterns TEXT,
    permission_model TEXT,
    coding_style TEXT,
    key_files TEXT,
    analysis_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    skill_content TEXT,
    skill_status VARCHAR(20) NOT NULL DEFAULT 'draft',
    skill_version INTEGER NOT NULL DEFAULT 1,
    confirmed_by BIGINT,
    confirmed_at BIGINT,
    analysis_error TEXT,
    raw_files TEXT,
    tenant_id BIGINT NOT NULL DEFAULT 0,
    create_time BIGINT NOT NULL DEFAULT ((EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT),
    update_time BIGINT NOT NULL DEFAULT ((EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT)
);

CREATE INDEX IF NOT EXISTS idx_project_knowledge_project ON project_knowledge(project_id);
CREATE INDEX IF NOT EXISTS idx_project_knowledge_status ON project_knowledge(skill_status);
CREATE INDEX IF NOT EXISTS idx_project_knowledge_tenant ON project_knowledge(tenant_id);

ALTER TABLE project_knowledge ADD COLUMN IF NOT EXISTS project_brief TEXT;
ALTER TABLE project_knowledge ADD COLUMN IF NOT EXISTS skill_content TEXT;
ALTER TABLE project_knowledge ADD COLUMN IF NOT EXISTS skill_status VARCHAR(20) NOT NULL DEFAULT 'draft';
ALTER TABLE project_knowledge ADD COLUMN IF NOT EXISTS skill_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE project_knowledge ADD COLUMN IF NOT EXISTS confirmed_by BIGINT;
ALTER TABLE project_knowledge ADD COLUMN IF NOT EXISTS confirmed_at BIGINT;
ALTER TABLE project_knowledge ADD COLUMN IF NOT EXISTS analysis_error TEXT;

ALTER TABLE dev_pipeline ADD COLUMN IF NOT EXISTS workspace_path VARCHAR(512);
ALTER TABLE dev_pipeline ADD COLUMN IF NOT EXISTS git_repo_url VARCHAR(512);
ALTER TABLE dev_pipeline ADD COLUMN IF NOT EXISTS git_branch VARCHAR(64);
ALTER TABLE dev_pipeline ADD COLUMN IF NOT EXISTS git_commit_sha VARCHAR(64);
ALTER TABLE dev_pipeline ADD COLUMN IF NOT EXISTS deploy_task_id VARCHAR(64);
ALTER TABLE dev_pipeline ADD COLUMN IF NOT EXISTS git_config_id BIGINT;
ALTER TABLE dev_pipeline ADD COLUMN IF NOT EXISTS skill_config TEXT;

DO $$
DECLARE
    project_parent_id BIGINT;
    pipeline_parent_id BIGINT;
    now_ms BIGINT := (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT;
BEGIN
    SELECT id INTO project_parent_id
    FROM sys_menu
    WHERE path = '/project' AND parent_id = 0
    ORDER BY id
    LIMIT 1;

    IF project_parent_id IS NULL THEN
        INSERT INTO sys_menu (
            parent_id, name, path, component, permission, icon, type, visible, sort,
            status, tenant_id, create_time, update_time
        )
        VALUES (0, '项目管理', '/project', 'Layout', NULL, 'CodeOutlined', 1, 1, 20, 1, 1, now_ms, now_ms)
        RETURNING id INTO project_parent_id;
    END IF;

    SELECT id INTO pipeline_parent_id
    FROM sys_menu
    WHERE path = '/pipeline' AND parent_id = 0 AND permission IS NULL
    ORDER BY id
    LIMIT 1;

    IF pipeline_parent_id IS NULL THEN
        INSERT INTO sys_menu (
            parent_id, name, path, component, permission, icon, type, visible, sort,
            status, tenant_id, create_time, update_time
        )
        VALUES (0, '开发流水线', '/pipeline', 'Layout', NULL, 'RocketOutlined', 1, 1, 30, 1, 1, now_ms, now_ms)
        RETURNING id INTO pipeline_parent_id;
    END IF;

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT
        0, '门户选择', '/portal-select', 'portal/select/index', 'portal:select',
        'AppstoreOutlined', 2, 0, 20, 1, 1, now_ms, now_ms
    WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = 'portal:select');

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT
        project_parent_id, '项目接入', '/project/access', 'portal/developer/index', 'portal:developer',
        'CodeOutlined', 2, 1, 0, 1, 1, now_ms, now_ms
    WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = 'portal:developer');

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT
        pipeline_parent_id, '需求开发', '/pipeline/requirement', 'portal/product/index', 'portal:product',
        'RocketOutlined', 2, 1, 0, 1, 1, now_ms, now_ms
    WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = 'portal:product');

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT
        pipeline_parent_id, '开发流水线', '/pipeline/development', 'pipeline/index', 'flow:pipeline:list',
        'ThunderboltOutlined', 2, 1, 1, 1, 1, now_ms, now_ms
    WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = 'flow:pipeline:list');

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT
        project_parent_id, '确认项目 Skill', NULL, NULL, 'developer:project-skill:confirm',
        NULL, 3, 0, 23, 1, 1, now_ms, now_ms
    WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = 'developer:project-skill:confirm');

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT
        pipeline_parent_id, '创建需求流水线', NULL, NULL, 'product:pipeline:create',
        NULL, 3, 0, 24, 1, 1, now_ms, now_ms
    WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = 'product:pipeline:create');

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT pipeline_parent_id, '匹配项目 Skill', NULL, NULL, 'flow:pipeline:match', NULL, 3, 0, 25, 1, 1, now_ms, now_ms
    WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = 'flow:pipeline:match');

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT pipeline_parent_id, '创建流水线', NULL, NULL, 'flow:pipeline:create', NULL, 3, 0, 26, 1, 1, now_ms, now_ms
    WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = 'flow:pipeline:create');

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT pipeline_parent_id, '执行流水线', NULL, NULL, 'flow:pipeline:execute', NULL, 3, 0, 27, 1, 1, now_ms, now_ms
    WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = 'flow:pipeline:execute');

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT pipeline_parent_id, '确认流水线', NULL, NULL, 'flow:pipeline:confirm', NULL, 3, 0, 28, 1, 1, now_ms, now_ms
    WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = 'flow:pipeline:confirm');
END $$;
