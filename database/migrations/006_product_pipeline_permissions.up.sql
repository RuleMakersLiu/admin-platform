-- Add complete product pipeline API permissions to the role permission tree.
-- These are button-level permissions used by the gateway permission middleware.

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
    SELECT pipeline_parent_id, item.name, NULL, NULL, item.permission, NULL, 3, 0, item.sort, 1, 1, now_ms, now_ms
    FROM (
        VALUES
            ('查看流水线列表', 'flow:pipeline:list', 29),
            ('查看流水线状态', 'flow:pipeline:status', 30),
            ('查看流水线产物', 'flow:pipeline:artifact', 31),
            ('查看预览产物', 'flow:pipeline:preview', 32),
            ('查看阶段输出', 'flow:pipeline:output', 33),
            ('流式执行流水线', 'flow:pipeline:execute-stream', 34),
            ('下载前端代码', 'flow:pipeline:frontend-download', 35),
            ('回退流水线', 'flow:pipeline:rollback', 36),
            ('删除流水线', 'flow:pipeline:delete', 37)
    ) AS item(name, permission, sort)
    WHERE NOT EXISTS (
        SELECT 1 FROM sys_menu WHERE sys_menu.permission = item.permission
    );
END $$;
