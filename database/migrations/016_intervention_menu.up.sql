-- 016: 待人工介入队列菜单入口 —— 挂在「开发流水线」(/pipeline) 下，与 AI 评测同级。
-- 流水线某阶段自动重试耗尽会进入 needs_human，这里集中处理。幂等：按 path 判断是否已存在。
DO $$
DECLARE
    pipeline_parent_id BIGINT;
    now_ms BIGINT := (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT;
BEGIN
    SELECT id INTO pipeline_parent_id
    FROM sys_menu
    WHERE path = '/pipeline' AND parent_id = 0 AND menu_type = 1 AND is_deleted = 0
    LIMIT 1;

    IF pipeline_parent_id IS NULL THEN
        RAISE NOTICE '开发流水线父菜单(/pipeline)未找到，跳过 intervention 菜单插入';
    ELSEIF NOT EXISTS (SELECT 1 FROM sys_menu WHERE path = '/pipeline/intervention' AND is_deleted = 0) THEN
        INSERT INTO sys_menu (
            parent_id, name, path, component, permission, icon,
            menu_type, sort, status, tenant_id, create_time, update_time, visible
        ) VALUES (
            pipeline_parent_id, '待人工介入', '/pipeline/intervention', 'pipeline-intervention/index',
            'flow:pipeline:list', 'ToolOutlined',
            2, 36, 1, 1, now_ms, now_ms, 1
        );
    END IF;
END $$;
