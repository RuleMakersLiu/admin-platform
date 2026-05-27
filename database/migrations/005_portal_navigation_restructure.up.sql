-- Re-home role portal menus after the portal selection and pipeline navigation redesign.
-- This migration is safe to run on databases that already applied the old 004 menu seed.

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
            parent_id, name, path, component, permission, icon, menu_type, visible, sort,
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
            parent_id, name, path, component, permission, icon, menu_type, visible, sort,
            status, tenant_id, create_time, update_time
        )
        VALUES (0, '开发流水线', '/pipeline', 'Layout', NULL, 'RocketOutlined', 1, 1, 30, 1, 1, now_ms, now_ms)
        RETURNING id INTO pipeline_parent_id;
    END IF;

    UPDATE sys_menu
    SET visible = 0,
        status = 1,
        update_time = now_ms
    WHERE permission = 'portal:select';

    UPDATE sys_menu
    SET parent_id = project_parent_id,
        name = '项目接入',
        path = '/project/access',
        component = 'portal/developer/index',
        icon = 'CodeOutlined',
        menu_type = 2,
        visible = 1,
        status = 1,
        sort = 0,
        update_time = now_ms
    WHERE permission = 'portal:developer';

    IF NOT FOUND THEN
        INSERT INTO sys_menu (
            parent_id, name, path, component, permission, icon, menu_type, visible, sort,
            status, tenant_id, create_time, update_time
        )
        VALUES (
            project_parent_id, '项目接入', '/project/access', 'portal/developer/index', 'portal:developer',
            'CodeOutlined', 2, 1, 0, 1, 1, now_ms, now_ms
        );
    END IF;

    UPDATE sys_menu
    SET parent_id = pipeline_parent_id,
        name = '需求开发',
        path = '/pipeline/requirement',
        component = 'portal/product/index',
        icon = 'RocketOutlined',
        menu_type = 2,
        visible = 0,
        status = 1,
        sort = 0,
        update_time = now_ms
    WHERE permission = 'portal:product';

    IF NOT FOUND THEN
        INSERT INTO sys_menu (
            parent_id, name, path, component, permission, icon, menu_type, visible, sort,
            status, tenant_id, create_time, update_time
        )
        VALUES (
            pipeline_parent_id, '需求开发', '/pipeline/requirement', 'portal/product/index', 'portal:product',
            'RocketOutlined', 2, 1, 0, 1, 1, now_ms, now_ms
        );
    END IF;

    UPDATE sys_menu
    SET parent_id = pipeline_parent_id,
        name = '开发流水线',
        path = '/pipeline/development',
        component = 'pipeline/index',
        icon = 'ThunderboltOutlined',
        menu_type = 2,
        permission = NULL,
        visible = 1,
        status = 1,
        sort = 0,
        update_time = now_ms
    WHERE permission = 'flow:pipeline:list'
       OR path = '/pipeline/development';

    IF NOT FOUND THEN
        INSERT INTO sys_menu (
            parent_id, name, path, component, permission, icon, menu_type, visible, sort,
            status, tenant_id, create_time, update_time
        )
        VALUES (
            pipeline_parent_id, '开发流水线', '/pipeline/development', 'pipeline/index', NULL,
            'ThunderboltOutlined', 2, 1, 0, 1, 1, now_ms, now_ms
        );
    END IF;

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, menu_type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT pipeline_parent_id, '匹配项目 Skill', NULL, NULL, 'flow:pipeline:match', NULL, 3, 0, 25, 1, 1, now_ms, now_ms
    WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = 'flow:pipeline:match');

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, menu_type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT pipeline_parent_id, '创建流水线', NULL, NULL, 'flow:pipeline:create', NULL, 3, 0, 26, 1, 1, now_ms, now_ms
    WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = 'flow:pipeline:create');

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, menu_type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT pipeline_parent_id, '执行流水线', NULL, NULL, 'flow:pipeline:execute', NULL, 3, 0, 27, 1, 1, now_ms, now_ms
    WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = 'flow:pipeline:execute');

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, menu_type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT pipeline_parent_id, '确认流水线', NULL, NULL, 'flow:pipeline:confirm', NULL, 3, 0, 28, 1, 1, now_ms, now_ms
    WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE permission = 'flow:pipeline:confirm');

    UPDATE sys_admin_group
    SET power = (
        SELECT jsonb_agg(DISTINCT permission_key)::text
        FROM (
            SELECT jsonb_array_elements_text(COALESCE(NULLIF(sys_admin_group.power, '')::jsonb, '[]'::jsonb)) AS permission_key
            UNION ALL SELECT 'flow:pipeline:match'
            UNION ALL SELECT 'flow:pipeline:create'
            UNION ALL SELECT 'flow:pipeline:list'
            UNION ALL SELECT 'flow:pipeline:execute'
            UNION ALL SELECT 'flow:pipeline:confirm'
        ) permissions
    )
    WHERE power IS NOT NULL
      AND power LIKE '%portal:product%'
      AND power NOT LIKE '%flow:pipeline:match%';
END $$;
