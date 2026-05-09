-- =============================================
-- 添加技能市场菜单
-- =============================================

-- 添加技能市场菜单（ID从300开始）
INSERT INTO sys_menu (id, parent_id, name, path, component, permission, icon, type, visible, sort, status, tenant_id, create_time, update_time) VALUES
(300, 0, '技能市场', '/skills', 'Layout', NULL, 'appstore', 1, 1, 5, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000, EXTRACT(EPOCH FROM NOW()) * 1000),
(301, 300, '技能列表', '/skills/market', 'skills/market/index', 'skills_market_list', 'shop', 2, 1, 1, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000, EXTRACT(EPOCH FROM NOW()) * 1000)
ON CONFLICT (id) DO NOTHING;

-- 添加WebChat菜单
INSERT INTO sys_menu (id, parent_id, name, path, component, permission, icon, type, visible, sort, status, tenant_id, create_time, update_time) VALUES
(400, 0, 'WebChat', '/webchat', 'webchat/index', NULL, 'message', 2, 1, 6, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000, EXTRACT(EPOCH FROM NOW()) * 1000)
ON CONFLICT (id) DO NOTHING;

-- 验证
SELECT '菜单数据插入完成' as status;
SELECT id, parent_id, name, path, permission FROM sys_menu WHERE id >= 300 ORDER BY id;
