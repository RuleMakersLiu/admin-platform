-- 012: 评测 Golden Cases 菜单入口 —— 挂在「开发流水线」(/pipeline) 下
-- 幂等：按 path 判断是否已存在；父菜单按 path 动态查找，避免硬编码 id。
DO $$
DECLARE
    pipeline_parent_id BIGINT;
    now_ms BIGINT := (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT;
BEGIN
    SELECT id INTO pipeline_parent_id
    FROM sys_menu
    WHERE path = '/pipeline' AND parent_id = 0 AND type = 1
    LIMIT 1;

    IF pipeline_parent_id IS NULL THEN
        RAISE NOTICE '开发流水线父菜单(/pipeline)未找到，跳过 eval-golden 菜单插入';
    ELSEIF NOT EXISTS (SELECT 1 FROM sys_menu WHERE path = '/pipeline/eval-golden') THEN
        INSERT INTO sys_menu (
            parent_id, name, path, component, permission, icon,
            type, visible, sort, status, tenant_id, create_time, update_time
        ) VALUES (
            pipeline_parent_id, 'Golden 评测', '/pipeline/eval-golden', 'eval-golden/index',
            'flow:pipeline:list', 'TrophyOutlined',
            2, 1, 34, 1, 1, now_ms, now_ms
        );
    END IF;
END $$;
