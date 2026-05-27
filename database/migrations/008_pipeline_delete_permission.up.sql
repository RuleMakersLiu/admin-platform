-- Ensure product managers can configure and use the pipeline delete permission.

DO $$
DECLARE
    pipeline_parent_id BIGINT;
    now_ms BIGINT := (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT;
BEGIN
    SELECT id INTO pipeline_parent_id
    FROM sys_menu
    WHERE path = '/pipeline'
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

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, menu_type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT pipeline_parent_id, '删除流水线', NULL, NULL, 'flow:pipeline:delete', NULL, 3, 0, 37, 1, 1, now_ms, now_ms
    WHERE NOT EXISTS (
        SELECT 1 FROM sys_menu WHERE permission = 'flow:pipeline:delete'
    );

    UPDATE sys_admin_group
    SET power = (
        SELECT jsonb_agg(DISTINCT permission_key)::text
        FROM (
            SELECT jsonb_array_elements_text(COALESCE(NULLIF(power, '')::jsonb, '[]'::jsonb)) AS permission_key
            UNION ALL SELECT 'flow:pipeline:delete'
        ) permissions
    ),
    update_time = now_ms
    WHERE name = '产品经理'
      AND is_super = 0
      AND COALESCE(power, '') NOT LIKE '%flow:pipeline:delete%';
END $$;
