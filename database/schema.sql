-- =============================================
-- 后台管理系统数据库表结构
-- 版本: 1.0.0
-- 日期: 2026-02-25
-- =============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ---------------------------------------------
-- 系统管理相关表
-- ---------------------------------------------

-- 管理员表
DROP TABLE IF EXISTS `sys_admin`;
CREATE TABLE `sys_admin` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `username` varchar(50) NOT NULL COMMENT '用户名',
  `password` varchar(100) NOT NULL COMMENT '密码(BCrypt加密)',
  `real_name` varchar(50) DEFAULT NULL COMMENT '真实姓名',
  `email` varchar(100) DEFAULT NULL COMMENT '邮箱',
  `phone` varchar(20) DEFAULT NULL COMMENT '手机号',
  `avatar` varchar(255) DEFAULT NULL COMMENT '头像URL',
  `group_id` bigint(20) DEFAULT NULL COMMENT '用户组ID',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 0禁用 1启用',
  `last_login_time` bigint(20) DEFAULT NULL COMMENT '最后登录时间(时间戳毫秒)',
  `last_login_ip` varchar(50) DEFAULT NULL COMMENT '最后登录IP',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(时间戳毫秒)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_username_tenant` (`username`, `tenant_id`),
  KEY `idx_group_id` (`group_id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='管理员表';

-- 管理员组表
DROP TABLE IF EXISTS `sys_admin_group`;
CREATE TABLE `sys_admin_group` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(50) NOT NULL COMMENT '组名称',
  `parent_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '父级ID',
  `path` varchar(500) NOT NULL DEFAULT '0' COMMENT '层级路径(如: 0,1,2)',
  `power` text COMMENT '权限标识列表(JSON数组)',
  `is_super` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否超级管理员: 0否 1是',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `sort` int(11) NOT NULL DEFAULT 0 COMMENT '排序',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 0禁用 1启用',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(时间戳毫秒)',
  PRIMARY KEY (`id`),
  KEY `idx_parent_id` (`parent_id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_path` (`path`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='管理员组表';

-- 管理员-平台关联表
DROP TABLE IF EXISTS `sys_admin_platform`;
CREATE TABLE `sys_admin_platform` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `admin_id` bigint(20) NOT NULL COMMENT '管理员ID',
  `platform_id` bigint(20) NOT NULL COMMENT '平台ID',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_admin_platform` (`admin_id`, `platform_id`),
  KEY `idx_admin_id` (`admin_id`),
  KEY `idx_platform_id` (`platform_id`),
  KEY `idx_tenant_id` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='管理员-平台关联表';

-- 平台表
DROP TABLE IF EXISTS `sys_platform`;
CREATE TABLE `sys_platform` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(50) NOT NULL COMMENT '平台名称',
  `code` varchar(50) NOT NULL COMMENT '平台编码',
  `description` varchar(255) DEFAULT NULL COMMENT '平台描述',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 0禁用 1启用',
  `sort` int(11) NOT NULL DEFAULT 0 COMMENT '排序',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(时间戳毫秒)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_code_tenant` (`code`, `tenant_id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='平台表';

-- 模块菜单表
DROP TABLE IF EXISTS `sys_menu`;
CREATE TABLE `sys_menu` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `parent_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '父级ID',
  `name` varchar(50) NOT NULL COMMENT '菜单名称',
  `path` varchar(255) DEFAULT NULL COMMENT '路由路径',
  `component` varchar(255) DEFAULT NULL COMMENT '组件路径',
  `permission` varchar(100) DEFAULT NULL COMMENT '权限标识(如: admin_user_list)',
  `icon` varchar(50) DEFAULT NULL COMMENT '图标',
  `type` tinyint(1) NOT NULL DEFAULT 1 COMMENT '类型: 1目录 2菜单 3按钮/权限',
  `visible` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否可见: 0隐藏 1显示',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 0禁用 1启用',
  `sort` int(11) NOT NULL DEFAULT 0 COMMENT '排序',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(时间戳毫秒)',
  PRIMARY KEY (`id`),
  KEY `idx_parent_id` (`parent_id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_permission` (`permission`),
  KEY `idx_type` (`type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模块菜单表';

-- 租户表
DROP TABLE IF EXISTS `sys_tenant`;
CREATE TABLE `sys_tenant` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(100) NOT NULL COMMENT '租户名称',
  `code` varchar(50) NOT NULL COMMENT '租户编码',
  `contact_name` varchar(50) DEFAULT NULL COMMENT '联系人',
  `contact_phone` varchar(20) DEFAULT NULL COMMENT '联系电话',
  `domain` varchar(255) DEFAULT NULL COMMENT '域名',
  `logo` varchar(255) DEFAULT NULL COMMENT 'Logo',
  `config` text COMMENT '租户配置(JSON)',
  `expire_time` bigint(20) DEFAULT NULL COMMENT '过期时间(时间戳毫秒)',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 0禁用 1启用',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(时间戳毫秒)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_code` (`code`),
  UNIQUE KEY `uk_domain` (`domain`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租户表';

-- 操作日志表
DROP TABLE IF EXISTS `sys_operation_log`;
CREATE TABLE `sys_operation_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `admin_id` bigint(20) NOT NULL COMMENT '操作人ID',
  `username` varchar(50) DEFAULT NULL COMMENT '操作人用户名',
  `module` varchar(50) DEFAULT NULL COMMENT '模块名称',
  `action` varchar(50) DEFAULT NULL COMMENT '操作类型',
  `method` varchar(10) DEFAULT NULL COMMENT '请求方法',
  `url` varchar(500) DEFAULT NULL COMMENT '请求URL',
  `params` text COMMENT '请求参数',
  `ip` varchar(50) DEFAULT NULL COMMENT '操作IP',
  `user_agent` varchar(500) DEFAULT NULL COMMENT '用户代理',
  `response` text COMMENT '响应结果',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 0失败 1成功',
  `error_msg` text COMMENT '错误信息',
  `duration` int(11) DEFAULT NULL COMMENT '耗时(毫秒)',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  PRIMARY KEY (`id`),
  KEY `idx_admin_id` (`admin_id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_module` (`module`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='操作日志表';

-- ---------------------------------------------
-- 代码生成相关表
-- ---------------------------------------------

-- 功能配置表
DROP TABLE IF EXISTS `gen_function_config`;
CREATE TABLE `gen_function_config` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `table_name` varchar(100) NOT NULL COMMENT '表名',
  `function_name` varchar(100) NOT NULL COMMENT '功能名称',
  `function_desc` varchar(255) DEFAULT NULL COMMENT '功能描述',
  `module_name` varchar(50) DEFAULT NULL COMMENT '模块名称',
  `business_name` varchar(50) DEFAULT NULL COMMENT '业务名称',
  `form_config` text COMMENT '表单配置(JSON)',
  `table_config` text COMMENT '表格配置(JSON)',
  `api_config` text COMMENT 'API配置(JSON)',
  `gen_type` tinyint(1) NOT NULL DEFAULT 1 COMMENT '生成方式: 1命令式 2对话式',
  `is_table_created` tinyint(1) NOT NULL DEFAULT 0 COMMENT '表是否已创建: 0否 1是',
  `is_java_generated` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Java代码是否已生成: 0否 1是',
  `is_vue_generated` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Vue代码是否已生成: 0否 1是',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 0禁用 1启用',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(时间戳毫秒)',
  PRIMARY KEY (`id`),
  KEY `idx_table_name` (`table_name`),
  KEY `idx_tenant_id` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='功能配置表';

-- 字段配置表
DROP TABLE IF EXISTS `gen_field_config`;
CREATE TABLE `gen_field_config` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `function_id` bigint(20) NOT NULL COMMENT '功能配置ID',
  `column_name` varchar(100) NOT NULL COMMENT '数据库字段名',
  `column_type` varchar(50) NOT NULL COMMENT '数据库字段类型',
  `field_name` varchar(100) NOT NULL COMMENT 'Java字段名',
  `field_type` varchar(50) NOT NULL COMMENT 'Java字段类型',
  `field_label` varchar(100) DEFAULT NULL COMMENT '字段标签',
  `html_type` varchar(20) DEFAULT NULL COMMENT '表单类型: input/select/textarea/date/...',
  `dict_type` varchar(50) DEFAULT NULL COMMENT '字典类型',
  `is_pk` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否主键: 0否 1是',
  `is_required` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否必填: 0否 1是',
  `is_list` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否列表显示: 0否 1是',
  `is_form` tinyint(1) NOT NULL DEFAULT 1 COMMENT '是否表单字段: 0否 1是',
  `is_query` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否查询字段: 0否 1是',
  `query_type` varchar(20) DEFAULT NULL COMMENT '查询类型: eq/like/between/gt/lt/...',
  `validate_rule` varchar(255) DEFAULT NULL COMMENT '验证规则',
  `sort` int(11) NOT NULL DEFAULT 0 COMMENT '排序',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(时间戳毫秒)',
  PRIMARY KEY (`id`),
  KEY `idx_function_id` (`function_id`),
  KEY `idx_tenant_id` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='字段配置表';

-- 对话记录表
DROP TABLE IF EXISTS `gen_chat_history`;
CREATE TABLE `gen_chat_history` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `session_id` varchar(50) NOT NULL COMMENT '会话ID',
  `admin_id` bigint(20) NOT NULL COMMENT '管理员ID',
  `type` tinyint(1) NOT NULL COMMENT '类型: 1命令式 2自然语言',
  `command` varchar(100) DEFAULT NULL COMMENT '命令标识',
  `prompt` text COMMENT '用户输入',
  `response` longtext COMMENT 'AI响应',
  `structured_data` longtext COMMENT '结构化数据(JSON)',
  `tokens_used` int(11) DEFAULT NULL COMMENT 'Token消耗',
  `response_time` int(11) DEFAULT NULL COMMENT '响应时间(毫秒)',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 1处理中 2成功 3失败',
  `error_msg` text COMMENT '错误信息',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  PRIMARY KEY (`id`),
  KEY `idx_session_id` (`session_id`),
  KEY `idx_admin_id` (`admin_id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='对话记录表';

-- 代码模板表
DROP TABLE IF EXISTS `gen_template`;
CREATE TABLE `gen_template` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(100) NOT NULL COMMENT '模板名称',
  `code` varchar(50) NOT NULL COMMENT '模板编码',
  `type` varchar(20) NOT NULL COMMENT '模板类型: entity/mapper/service/controller/vue',
  `content` longtext COMMENT '模板内容',
  `file_name_pattern` varchar(255) DEFAULT NULL COMMENT '文件名模式',
  `file_path_pattern` varchar(255) DEFAULT NULL COMMENT '文件路径模式',
  `description` varchar(255) DEFAULT NULL COMMENT '模板描述',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 0禁用 1启用',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(时间戳毫秒)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_code_tenant` (`code`, `tenant_id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_type` (`type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='代码模板表';

-- ---------------------------------------------
-- 部署相关表
-- ---------------------------------------------

-- 部署任务表
DROP TABLE IF EXISTS `deploy_task`;
CREATE TABLE `deploy_task` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `task_no` varchar(50) NOT NULL COMMENT '任务编号',
  `name` varchar(100) NOT NULL COMMENT '任务名称',
  `type` tinyint(1) NOT NULL COMMENT '类型: 1构建 2部署 3回滚',
  `project` varchar(50) DEFAULT NULL COMMENT '项目名称',
  `env` varchar(20) DEFAULT NULL COMMENT '环境: dev/test/prod',
  `config` text COMMENT '任务配置(JSON)',
  `chat_history_id` bigint(20) DEFAULT NULL COMMENT '对话记录ID',
  `admin_id` bigint(20) NOT NULL COMMENT '操作人ID',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 1待执行 2执行中 3成功 4失败 5已取消',
  `progress` int(11) DEFAULT 0 COMMENT '进度(0-100)',
  `log` longtext COMMENT '执行日志',
  `error_msg` text COMMENT '错误信息',
  `start_time` bigint(20) DEFAULT NULL COMMENT '开始时间(时间戳毫秒)',
  `end_time` bigint(20) DEFAULT NULL COMMENT '结束时间(时间戳毫秒)',
  `duration` int(11) DEFAULT NULL COMMENT '耗时(毫秒)',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(时间戳毫秒)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_task_no` (`task_no`),
  KEY `idx_admin_id` (`admin_id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_status` (`status`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='部署任务表';

-- 部署记录表
DROP TABLE IF EXISTS `deploy_record`;
CREATE TABLE `deploy_record` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `task_id` bigint(20) NOT NULL COMMENT '任务ID',
  `step` varchar(50) NOT NULL COMMENT '步骤名称',
  `step_name` varchar(100) DEFAULT NULL COMMENT '步骤描述',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 1待执行 2执行中 3成功 4失败',
  `log` text COMMENT '步骤日志',
  `duration` int(11) DEFAULT NULL COMMENT '耗时(毫秒)',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  PRIMARY KEY (`id`),
  KEY `idx_task_id` (`task_id`),
  KEY `idx_tenant_id` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='部署记录表';

-- 项目配置表
DROP TABLE IF EXISTS `deploy_project`;
CREATE TABLE `deploy_project` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(100) NOT NULL COMMENT '项目名称',
  `code` varchar(50) NOT NULL COMMENT '项目编码',
  `type` varchar(20) NOT NULL COMMENT '项目类型: java/go/vue/react',
  `repo_url` varchar(255) DEFAULT NULL COMMENT '仓库地址',
  `branch` varchar(50) DEFAULT NULL COMMENT '分支',
  `build_cmd` varchar(255) DEFAULT NULL COMMENT '构建命令',
  `dockerfile` text COMMENT 'Dockerfile内容',
  `image_name` varchar(100) DEFAULT NULL COMMENT '镜像名称',
  `deploy_config` text COMMENT '部署配置(JSON)',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 0禁用 1启用',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(时间戳毫秒)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_code_tenant` (`code`, `tenant_id`),
  KEY `idx_tenant_id` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='项目配置表';

-- ---------------------------------------------
-- 初始数据
-- ---------------------------------------------

-- 插入默认租户
INSERT INTO `sys_tenant` (`id`, `name`, `code`, `contact_name`, `contact_phone`, `domain`, `status`, `create_time`, `update_time`)
VALUES (1, '默认租户', 'default', '系统管理员', '13800000000', NULL, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000);

-- 插入超级管理员组
INSERT INTO `sys_admin_group` (`id`, `name`, `parent_id`, `path`, `power`, `is_super`, `tenant_id`, `status`, `create_time`, `update_time`)
VALUES (1, '超级管理员', 0, '0', NULL, 1, 1, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000);

-- 插入默认管理员 (密码: admin123, BCrypt加密)
INSERT INTO `sys_admin` (`id`, `username`, `password`, `real_name`, `group_id`, `tenant_id`, `status`, `create_time`, `update_time`)
VALUES (1, 'admin', '$2a$10$N.zmdr9k7uOCQb376NoUnuTJ8iAt6Z5EHsM8lE9lBOsl7iAt6Z5EH', '系统管理员', 1, 1, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000);

-- 插入默认菜单
INSERT INTO `sys_menu` (`id`, `parent_id`, `name`, `path`, `component`, `permission`, `icon`, `type`, `visible`, `status`, `sort`, `tenant_id`, `create_time`, `update_time`) VALUES
(1, 0, '系统管理', '/system', 'Layout', NULL, 'setting', 1, 1, 1, 1, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(2, 1, '用户管理', '/system/admin', 'system/admin/index', 'system_admin_list', 'user', 2, 1, 1, 1, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(3, 1, '角色管理', '/system/group', 'system/group/index', 'system_group_list', 'team', 2, 1, 1, 2, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(4, 1, '菜单管理', '/system/menu', 'system/menu/index', 'system_menu_list', 'menu', 2, 1, 1, 3, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(5, 1, '租户管理', '/system/tenant', 'system/tenant/index', 'system_tenant_list', 'cluster', 2, 1, 1, 4, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(6, 0, '代码生成', '/generator', 'Layout', NULL, 'code', 1, 1, 1, 2, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(7, 6, '功能配置', '/generator/config', 'generator/config/index', 'generator_config_list', 'tool', 2, 1, 1, 1, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(8, 6, '对话生成', '/generator/chat', 'generator/chat/index', 'generator_chat_list', 'message', 2, 1, 1, 2, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(9, 0, '部署管理', '/deploy', 'Layout', NULL, 'cloud-server', 1, 1, 1, 3, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(10, 9, '项目配置', '/deploy/project', 'deploy/project/index', 'deploy_project_list', 'folder', 2, 1, 1, 1, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(11, 9, '任务列表', '/deploy/task', 'deploy/task/index', 'deploy_task_list', 'schedule', 2, 1, 1, 2, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000);

SET FOREIGN_KEY_CHECKS = 1;

-- =============================================
-- 核心功能增强 - 新增表
-- =============================================

-- 大模型配置表
DROP TABLE IF EXISTS `sys_llm_config`;
CREATE TABLE `sys_llm_config` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL COMMENT '配置名称',
  `provider` varchar(50) NOT NULL COMMENT '提供商: openai/anthropic/azure/custom',
  `base_url` varchar(255) NOT NULL COMMENT 'API Base URL',
  `api_key` varchar(255) NOT NULL COMMENT 'API Key (AES加密)',
  `model_name` varchar(100) NOT NULL COMMENT '模型名称',
  `max_tokens` int(11) DEFAULT 4096 COMMENT '最大Token',
  `temperature` decimal(3,2) DEFAULT 0.70 COMMENT '温度参数',
  `extra_config` json DEFAULT NULL COMMENT '额外配置',
  `is_default` tinyint(1) DEFAULT 0 COMMENT '是否默认',
  `status` tinyint(1) DEFAULT 1 COMMENT '状态: 0禁用 1启用',
  `tenant_id` bigint(20) DEFAULT 0 COMMENT '租户ID',
  `admin_id` bigint(20) NOT NULL COMMENT '创建者ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(毫秒)',
  PRIMARY KEY (`id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='大模型配置表';

-- Git平台配置表
DROP TABLE IF EXISTS `sys_git_config`;
CREATE TABLE `sys_git_config` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL COMMENT '配置名称',
  `platform` varchar(20) NOT NULL COMMENT '平台: gitlab/github/gitee/gitea',
  `base_url` varchar(255) NOT NULL COMMENT 'Git服务URL',
  `access_token` varchar(255) NOT NULL COMMENT 'Access Token (AES加密)',
  `webhook_secret` varchar(255) DEFAULT NULL COMMENT 'Webhook密钥',
  `ssh_key` text DEFAULT NULL COMMENT 'SSH私钥',
  `extra_config` json DEFAULT NULL COMMENT '额外配置',
  `is_default` tinyint(1) DEFAULT 0 COMMENT '是否默认',
  `status` tinyint(1) DEFAULT 1 COMMENT '状态',
  `tenant_id` bigint(20) DEFAULT 0 COMMENT '租户ID',
  `admin_id` bigint(20) NOT NULL COMMENT '创建者ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(毫秒)',
  PRIMARY KEY (`id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_platform` (`platform`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Git平台配置表';

-- 项目成员表
DROP TABLE IF EXISTS `sys_project_member`;
CREATE TABLE `sys_project_member` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `project_id` bigint(20) NOT NULL COMMENT '项目ID',
  `project_type` varchar(20) NOT NULL COMMENT '项目类型: agent/deploy',
  `admin_id` bigint(20) NOT NULL COMMENT '用户ID',
  `role` varchar(20) NOT NULL COMMENT '角色: owner/maintainer/developer',
  `permissions` json DEFAULT NULL COMMENT '细粒度权限',
  `added_by` bigint(20) DEFAULT NULL COMMENT '添加者ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(毫秒)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_project_admin` (`project_id`, `project_type`, `admin_id`),
  KEY `idx_admin_id` (`admin_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目成员表';

-- 开发流水线表
CREATE TABLE `dev_pipeline` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `pipeline_id` varchar(64) NOT NULL COMMENT '流水线ID',
  `project_id` varchar(64) DEFAULT NULL COMMENT '项目ID',
  `user_request` text COMMENT '用户需求描述',
  `status` varchar(32) NOT NULL DEFAULT 'pending' COMMENT '状态: pending/running/waiting_confirm/completed/failed/cancelled',
  `current_stage` varchar(32) NOT NULL DEFAULT 'requirement' COMMENT '当前阶段',
  `stages_data` text COMMENT '阶段数据JSON',
  `retry_count` int(11) NOT NULL DEFAULT 0 COMMENT '当前循环重试次数',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `creator_id` bigint(20) DEFAULT NULL COMMENT '创建者ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(毫秒)',
  `is_deleted` int(11) NOT NULL DEFAULT 0 COMMENT '是否删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_pipeline_id` (`pipeline_id`),
  KEY `idx_status` (`status`),
  KEY `idx_tenant` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='开发流水线表';

-- 菜单数据 (系统管理的 parent_id = 1)
INSERT INTO `sys_menu` (`parent_id`, `name`, `path`, `component`, `permission`, `icon`, `type`, `visible`, `sort`, `status`, `tenant_id`, `create_time`, `update_time`) VALUES
(1, '大模型配置', '/system/llm', 'system/llm/index', 'system_llm_list', 'RobotOutlined', 2, 1, 50, 1, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(1, 'Git配置', '/system/git', 'system/git/index', 'system_git_list', 'GithubOutlined', 2, 1, 51, 1, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
-- 智能分身模块
(12, 0, '智能分身', '/agent', 'Layout', NULL, 'robot', 1, 1, 1, 4, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(13, 12, '智能对话', '/agent/chat', 'agent/chat/index', 'agent_chat_list', 'message', 2, 1, 1, 1, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(14, 12, '任务管理', '/agent/task', 'agent/task/index', 'agent_task_list', 'schedule', 2, 1, 1, 2, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(15, 12, '项目配置', '/agent/project', 'agent/project/index', 'agent_project_list', 'folder', 2, 1, 1, 3, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(16, 12, 'Bug修复', '/agent/bug', 'agent/bug/index', 'agent_bug_list', 'bug', 2, 1, 1, 4, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000);

-- ---------------------------------------------
-- 知识图谱相关表
-- ---------------------------------------------

-- 知识图谱边表
CREATE TABLE IF NOT EXISTS `knowledge_edge` (
    `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    `edge_id` varchar(64) NOT NULL COMMENT '边业务ID(KE-xxx)',
    `source_id` varchar(64) NOT NULL COMMENT '起点知识条目ID',
    `target_id` varchar(64) NOT NULL COMMENT '终点知识条目ID',
    `relation_type` varchar(64) NOT NULL COMMENT '关系类型: depends_on/related_to/derived_from/supersedes/references',
    `weight` decimal(3,2) DEFAULT 1.00 COMMENT '关系权重(0.00~1.00)',
    `description` varchar(255) DEFAULT NULL COMMENT '关系描述',
    `tenant_id` bigint(20) NOT NULL COMMENT '租户ID',
    `create_time` bigint(20) NOT NULL COMMENT '创建时间(毫秒时间戳)',
    `is_deleted` int(11) DEFAULT 0 COMMENT '是否删除: 0否 1是',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_edge_id` (`edge_id`),
    KEY `idx_knowledge_edge_source` (`source_id`),
    KEY `idx_knowledge_edge_target` (`target_id`),
    KEY `idx_knowledge_edge_tenant` (`tenant_id`),
    KEY `idx_knowledge_edge_relation` (`relation_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识图谱边表';
