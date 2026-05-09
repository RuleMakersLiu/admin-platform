-- =============================================
-- 菜单数据修复脚本
-- 执行前请先备份数据
-- =============================================

-- 先检查并删除可能存在的重复菜单（根据 name 和 path 判断）
DELETE FROM `sys_menu` WHERE `name` = '大模型配置' AND `path` = '/system/llm';
DELETE FROM `sys_menu` WHERE `name` = 'Git配置' AND `path` = '/system/git';
DELETE FROM `sys_menu` WHERE `name` = '智能分身' AND `path` = '/agent';
DELETE FROM `sys_menu` WHERE `name` IN ('智能对话', '任务管理', '项目配置', 'Bug修复') AND `path` LIKE '/agent%';

-- 插入缺失的菜单
-- 系统管理下的子菜单
INSERT INTO `sys_menu` (`parent_id`, `name`, `path`, `component`, `permission`, `icon`, `type`, `visible`, `sort`, `status`, `tenant_id`, `create_time`, `update_time`) VALUES
(1, '大模型配置', '/system/llm', 'system/llm/index', 'system_llm_list', 'RobotOutlined', 2, 1, 50, 1, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(1, 'Git配置', '/system/git', 'system/git/index', 'system_git_list', 'GithubOutlined', 2, 1, 51, 1, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000);

-- 智能分身模块
INSERT INTO `sys_menu` (`parent_id`, `name`, `path`, `component`, `permission`, `icon`, `type`, `visible`, `sort`, `status`, `tenant_id`, `create_time`, `update_time`) VALUES
(12, 0, '智能分身', '/agent', 'Layout', NULL, 'robot', 1, 1, 1, 4, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000);

-- 智能分身子菜单
INSERT INTO `sys_menu` (`parent_id`, `name`, `path`, `component`, `permission`, `icon`, `type`, `visible`, `sort`, `status`, `tenant_id`, `create_time`, `update_time`) VALUES
(12, '智能对话', '/agent/chat', 'agent/chat/index', 'agent_chat_list', 'message', 2, 1, 1, 1, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(12, '任务管理', '/agent/task', 'agent/task/index', 'agent_task_list', 'schedule', 2, 1, 1, 2, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(12, '项目配置', '/agent/project', 'agent/project/index', 'agent_project_list', 'folder', 2, 1, 1, 3, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(12, 'Bug修复', '/agent/bug', 'agent/bug/index', 'agent_bug_list', 'bug', 2, 1, 1, 4, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000);

-- 更新智能分身子菜单的 parent_id（如果上面插入的智能分身菜单ID不是12）
SET @agent_parent_id = (SELECT id FROM (SELECT id FROM `sys_menu` WHERE `name` = '智能分身' AND `path` = '/agent' LIMIT 1) AS tmp);
UPDATE `sys_menu` SET `parent_id` = @agent_parent_id WHERE `name` IN ('智能对话', '任务管理', '项目配置', 'Bug修复') AND `path` LIKE '/agent/%';

-- 验证插入结果
SELECT id, parent_id, name, path, icon, type, sort FROM `sys_menu` ORDER BY parent_id, sort;
