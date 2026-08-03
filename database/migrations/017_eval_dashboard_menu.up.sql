-- 017: 流水线质量看板菜单入口 —— 挂在「开发流水线」(/pipeline) 下，与 Golden/AI 评测同级。
-- 展示每条流水线的综合分 + LLM judge/幻觉/视觉/E2E 分 + 人工覆盖分（human_score）+ 存为 golden。
-- 幂等：按 path 判断是否已存在（live DB 已手动插入 id=124，重建 DB 时此迁移补上）。
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
        RAISE NOTICE '开发流水线父菜单(/pipeline)未找到，跳过 eval-dashboard 菜单插入';
    ELSEIF NOT EXISTS (SELECT 1 FROM sys_menu WHERE path = '/pipeline/eval' AND is_deleted = 0) THEN
        INSERT INTO sys_menu (
            parent_id, name, path, component, permission, icon,
            menu_type, sort, status, tenant_id, create_time, update_time, visible
        ) VALUES (
            pipeline_parent_id, '质量看板', '/pipeline/eval', 'pipeline-eval/index',
            'flow:pipeline:list', 'BarChartOutlined',
            2, 33, 1, 1, now_ms, now_ms, 1
        );
    END IF;
END $$;
