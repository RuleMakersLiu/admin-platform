-- =============================================
-- 菜单数据修复脚本 - PostgreSQL (修复版)
-- =============================================

-- 检查并删除可能存在的重复菜单
DELETE FROM sys_menu WHERE name = '大模型配置' AND path = '/system/llm';
DELETE FROM sys_menu WHERE name = 'Git配置' AND path = '/system/git';
DELETE FROM sys_menu WHERE name = '智能分身' AND path = '/agent';
DELETE FROM sys_menu WHERE name IN ('智能对话', '任务管理', '项目配置', 'Bug修复') AND path LIKE '/agent%';

-- 插入缺失的菜单（使用不同的ID避免冲突）
-- 系统管理下的子菜单 - ID从100开始
INSERT INTO sys_menu (id, parent_id, name, path, component, permission, icon, type, visible, sort, status, tenant_id, create_time, update_time) VALUES
(100, 1, '大模型配置', '/system/llm', 'system/llm/index', 'system_llm_list', 'RobotOutlined', 2, 1, 50, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000, EXTRACT(EPOCH FROM NOW()) * 1000),
(101, 1, 'Git配置', '/system/git', 'system/git/index', 'system_git_list', 'GithubOutlined', 2, 1, 51, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000, EXTRACT(EPOCH FROM NOW()) * 1000)
ON CONFLICT (id) DO NOTHING;

-- 智能分身模块 - ID从200开始
INSERT INTO sys_menu (id, parent_id, name, path, component, permission, icon, type, visible, sort, status, tenant_id, create_time, update_time) VALUES
(200, 0, '智能分身', '/agent', 'Layout', NULL, 'robot', 1, 1, 4, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000, EXTRACT(EPOCH FROM NOW()) * 1000)
ON CONFLICT (id) DO NOTHING;

-- 智能分身子菜单 - ID从201开始
INSERT INTO sys_menu (id, parent_id, name, path, component, permission, icon, type, visible, sort, status, tenant_id, create_time, update_time) VALUES
(201, 200, '智能对话', '/agent/chat', 'agent/chat/index', 'agent_chat_list', 'message', 2, 1, 1, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000, EXTRACT(EPOCH FROM NOW()) * 1000),
(202, 200, '任务管理', '/agent/task', 'agent/task/index', 'agent_task_list', 'schedule', 2, 1, 2, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000, EXTRACT(EPOCH FROM NOW()) * 1000),
(203, 200, '项目配置', '/agent/project', 'agent/project/index', 'agent_project_list', 'folder', 2, 1, 3, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000, EXTRACT(EPOCH FROM NOW()) * 1000),
(204, 200, 'Bug修复', '/agent/bug', 'agent/bug/index', 'agent_bug_list', 'bug', 2, 1, 4, 1, 1, EXTRACT(EPOCH FROM NOW()) * 1000, EXTRACT(EPOCH FROM NOW()) * 1000)
ON CONFLICT (id) DO NOTHING;

-- 验证插入结果
SELECT '菜单数据插入完成：' as status;
SELECT id, parent_id, name, path FROM sys_menu WHERE id >= 100 ORDER BY id;
