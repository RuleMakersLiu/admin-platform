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
-- 项目模板与自动化测试
-- ---------------------------------------------

-- 项目模板表
DROP TABLE IF EXISTS `gen_project_template`;
CREATE TABLE `gen_project_template` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(100) NOT NULL COMMENT '模板名称',
  `code` varchar(50) NOT NULL COMMENT '模板编码',
  `language` varchar(30) NOT NULL COMMENT '语言: java/php/node/go/python',
  `framework` varchar(50) NOT NULL COMMENT '框架: spring-boot/laravel/express/gin/fastapi/vue/react',
  `version` varchar(20) DEFAULT '1.0.0' COMMENT '模板版本',
  `description` text COMMENT '模板描述',
  `structure` json NOT NULL COMMENT '项目结构定义(JSON): {files: [{path, content, is_template}]}',
  `variables` json DEFAULT NULL COMMENT '模板变量定义(JSON): [{name, label, type, default, required}]',
  `test_config` json DEFAULT NULL COMMENT '测试配置(JSON): {docker_image, test_cmd, coverage_cmd}',
  `build_config` json DEFAULT NULL COMMENT '构建配置(JSON): {dockerfile, build_cmd, output_dir}',
  `icon` varchar(50) DEFAULT NULL COMMENT '图标',
  `sort` int(11) DEFAULT 0 COMMENT '排序',
  `is_builtin` tinyint(1) DEFAULT 0 COMMENT '是否内置: 0否 1是',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID(0=全局)',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 0禁用 1启用',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(毫秒)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_code_tenant` (`code`, `tenant_id`),
  KEY `idx_language` (`language`),
  KEY `idx_framework` (`framework`),
  KEY `idx_tenant_id` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='项目模板表';

-- 已生成项目表
DROP TABLE IF EXISTS `gen_project`;
CREATE TABLE `gen_project` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(100) NOT NULL COMMENT '项目名称',
  `code` varchar(50) NOT NULL COMMENT '项目编码',
  `description` text COMMENT '项目描述',
  `template_id` bigint(20) NOT NULL COMMENT '使用的模板ID',
  `language` varchar(30) NOT NULL COMMENT '语言',
  `framework` varchar(50) NOT NULL COMMENT '框架',
  `variables` json DEFAULT NULL COMMENT '生成时使用的变量值(JSON)',
  `config_json` json DEFAULT NULL COMMENT '生成配置快照',
  `repo_url` varchar(255) DEFAULT NULL COMMENT '仓库地址',
  `branch` varchar(50) DEFAULT 'main' COMMENT '分支',
  `deploy_project_id` bigint(20) DEFAULT NULL COMMENT '关联的部署项目ID',
  `test_pass_rate` decimal(5,2) DEFAULT NULL COMMENT '最近测试通过率',
  `last_test_time` bigint(20) DEFAULT NULL COMMENT '最近测试时间(毫秒)',
  `admin_id` bigint(20) NOT NULL COMMENT '创建者ID',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 0禁用 1启用 2生成中 3测试中',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(毫秒)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_code_tenant` (`code`, `tenant_id`),
  KEY `idx_template_id` (`template_id`),
  KEY `idx_admin_id` (`admin_id`),
  KEY `idx_tenant_id` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='已生成项目表';

-- 测试任务表
DROP TABLE IF EXISTS `test_task`;
CREATE TABLE `test_task` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `task_no` varchar(50) NOT NULL COMMENT '任务编号',
  `project_id` bigint(20) NOT NULL COMMENT '项目ID',
  `type` varchar(30) NOT NULL DEFAULT 'unit' COMMENT '测试类型: unit/integration/e2e/custom',
  `docker_image` varchar(100) DEFAULT NULL COMMENT '测试使用的Docker镜像',
  `test_cmd` varchar(500) DEFAULT NULL COMMENT '测试命令',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 1待执行 2执行中 3成功 4失败 5已取消',
  `progress` int(11) DEFAULT 0 COMMENT '进度(0-100)',
  `total_cases` int(11) DEFAULT 0 COMMENT '总用例数',
  `passed_cases` int(11) DEFAULT 0 COMMENT '通过用例数',
  `failed_cases` int(11) DEFAULT 0 COMMENT '失败用例数',
  `coverage` decimal(5,2) DEFAULT NULL COMMENT '代码覆盖率(%)',
  `log` longtext COMMENT '执行日志',
  `error_msg` text COMMENT '错误信息',
  `result_json` json DEFAULT NULL COMMENT '详细测试结果(JSON)',
  `duration` int(11) DEFAULT NULL COMMENT '耗时(毫秒)',
  `admin_id` bigint(20) NOT NULL COMMENT '操作人ID',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `start_time` bigint(20) DEFAULT NULL COMMENT '开始时间(毫秒)',
  `end_time` bigint(20) DEFAULT NULL COMMENT '结束时间(毫秒)',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(毫秒)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_task_no` (`task_no`),
  KEY `idx_project_id` (`project_id`),
  KEY `idx_status` (`status`),
  KEY `idx_admin_id` (`admin_id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='测试任务表';

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
(6, 0, '项目管理', '/project', 'Layout', NULL, 'code', 1, 1, 1, 2, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(7, 6, '创建项目', '/project/create', 'project/create/index', 'project_create', 'plus', 2, 1, 1, 1, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(8, 6, '项目列表', '/project/list', 'project/list/index', 'project_list', 'folder', 2, 1, 1, 2, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(9, 6, '测试中心', '/project/test', 'project/test/index', 'project_test', 'experiment', 2, 1, 1, 3, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(10, 0, '部署管理', '/deploy', 'Layout', NULL, 'cloud-server', 1, 1, 1, 3, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(11, 10, '项目配置', '/deploy/project', 'deploy/project/index', 'deploy_project_list', 'folder', 2, 1, 1, 1, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),
(12, 10, '任务列表', '/deploy/task', 'deploy/task/index', 'deploy_task_list', 'schedule', 2, 1, 1, 2, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000);

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

-- ---------------------------------------------
-- 内置项目模板数据
-- ---------------------------------------------

INSERT INTO `gen_project_template` (`name`, `code`, `language`, `framework`, `description`, `structure`, `variables`, `test_config`, `build_config`, `icon`, `sort`, `is_builtin`, `tenant_id`, `status`, `create_time`, `update_time`) VALUES
-- Java Spring Boot
('Spring Boot 项目', 'spring-boot', 'java', 'spring-boot', 'Java Spring Boot 后端项目，集成 MyBatis-Plus、Swagger、Redis',
 '[{"path":"pom.xml","content":"<?xml version=\\"1.0\\" encoding=\\"UTF-8\\"?>\\n<project xmlns=\\"http://maven.apache.org/POM/4.0.0\\" xmlns:xsi=\\"http://www.w3.org/2001/XMLSchema-instance\\"\\n         xsi:schemaLocation=\\"http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd\\">\\n    <modelVersion>4.0.0</modelVersion>\\n    <parent>\\n        <groupId>org.springframework.boot</groupId>\\n        <artifactId>spring-boot-starter-parent</artifactId>\\n        <version>3.2.0</version>\\n    </parent>\\n    <groupId>{{.GroupId}}</groupId>\\n    <artifactId>{{.ArtifactId}}</artifactId>\\n    <version>1.0.0</version>\\n    <name>{{.ProjectName}}</name>\\n    <properties><java.version>17</java.version></properties>\\n    <dependencies>\\n        <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency>\\n        <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-data-redis</artifactId></dependency>\\n        <dependency><groupId>com.baomidou</groupId><artifactId>mybatis-plus-boot-starter</artifactId><version>3.5.5</version></dependency>\\n        <dependency><groupId>org.projectlombok</groupId><artifactId>lombok</artifactId><optional>true</optional></dependency>\\n        <dependency><groupId>org.springdoc</groupId><artifactId>springdoc-openapi-starter-webmvc-ui</artifactId><version>2.3.0</version></dependency>\\n        <dependency><groupId>org.postgresql</groupId><artifactId>postgresql</artifactId><scope>runtime</scope></dependency>\\n        <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-test</artifactId><scope>test</scope></dependency>\\n    </dependencies>\\n    <build><plugins><plugin><groupId>org.springframework.boot</groupId><artifactId>spring-boot-maven-plugin</artifactId></plugin></plugins></build>\\n</project>","is_template":true},{"path":"src/main/java/{{.PackagePath}}/Application.java","content":"package {{.PackageName}};\\n\\nimport org.springframework.boot.SpringApplication;\\nimport org.springframework.boot.autoconfigure.SpringBootApplication;\\n\\n@SpringBootApplication\\npublic class Application {\\n    public static void main(String[] args) {\\n        SpringApplication.run(Application.class, args);\\n    }\\n}","is_template":true},{"path":"src/main/java/{{.PackagePath}}/config/RedisConfig.java","content":"package {{.PackageName}}.config;\\n\\nimport org.springframework.context.annotation.Bean;\\nimport org.springframework.context.annotation.Configuration;\\nimport org.springframework.data.redis.connection.RedisConnectionFactory;\\nimport org.springframework.data.redis.core.RedisTemplate;\\nimport org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;\\nimport org.springframework.data.redis.serializer.StringRedisSerializer;\\n\\n@Configuration\\npublic class RedisConfig {\\n    @Bean\\n    public RedisTemplate<String, Object> redisTemplate(RedisConnectionFactory factory) {\\n        RedisTemplate<String, Object> template = new RedisTemplate<>();\\n        template.setConnectionFactory(factory);\\n        template.setKeySerializer(new StringRedisSerializer());\\n        template.setValueSerializer(new GenericJackson2JsonRedisSerializer());\\n        return template;\\n    }\\n}","is_template":true},{"path":"src/main/java/{{.PackagePath}}/common/Result.java","content":"package {{.PackageName}}.common;\\n\\nimport lombok.Data;\\n\\n@Data\\npublic class Result<T> {\\n    private int code;\\n    private String message;\\n    private T data;\\n\\n    public static <T> Result<T> success(T data) {\\n        Result<T> r = new Result<>();\\n        r.setCode(200);\\n        r.setMessage(\\"success\\");\\n        r.setData(data);\\n        return r;\\n    }\\n\\n    public static <T> Result<T> error(int code, String message) {\\n        Result<T> r = new Result<>();\\n        r.setCode(code);\\n        r.setMessage(message);\\n        return r;\\n    }\\n}","is_template":true},{"path":"src/main/resources/application.yml","content":"server:\\n  port: {{.Port}}\\n\\nspring:\\n  datasource:\\n    url: jdbc:postgresql://localhost:5432/{{.ArtifactId}}\\n    username: postgres\\n    password: postgres\\n  data:\\n    redis:\\n      host: localhost\\n      port: 6379\\n\\nmybatis-plus:\\n  mapper-locations: classpath:mapper/**/*.xml\\n  configuration:\\n    map-underscore-to-camel-case: true","is_template":true},{"path":"Dockerfile","content":"FROM eclipse-temurin:17-jdk-alpine\\nVOLUME /tmp\\nCOPY target/*.jar app.jar\\nENTRYPOINT[\\"java\\",\\"-jar\\",\\"/app.jar\\"]","is_template":true},{"path":".gitignore","content":"target/\\n!.mvn/wrapper/maven-wrapper.jar\\n*.class\\n.idea/\\n*.iml","is_template":false}]',
 '[{"name":"ProjectName","label":"项目名称","type":"text","default":"my-project","required":true},{"name":"GroupId","label":"Group ID","type":"text","default":"com.example","required":true},{"name":"ArtifactId","label":"Artifact ID","type":"text","default":"my-project","required":true},{"name":"PackageName","label":"包名","type":"text","default":"com.example.myproject","required":true},{"name":"PackagePath","label":"包路径","type":"text","default":"com/example/myproject","required":true},{"name":"Port","label":"服务端口","type":"number","default":"8080","required":true}]',
 '{"docker_image":"maven:3.9-eclipse-temurin-17","test_cmd":"cd /app && mvn test","coverage_cmd":"cd /app && mvn jacoco:report"}',
 '{"dockerfile":"FROM maven:3.9-eclipse-temurin-17 AS build\\nWORKDIR /app\\nCOPY pom.xml .\\nRUN mvn dependency:go-offline\\nCOPY src ./src\\nRUN mvn package -DskipTests\\nFROM eclipse-temurin:17-jdk-alpine\\nCOPY --from=build /app/target/*.jar app.jar\\nENTRYPOINT [\\"java\\",\\"-jar\\",\\"/app.jar\\"]","build_cmd":"mvn clean package -DskipTests","output_dir":"target/"}',
 'java', 1, 1, 0, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),

-- PHP Laravel
('Laravel 项目', 'laravel', 'php', 'laravel', 'PHP Laravel 后端项目，集成 Eloquent ORM、Redis、Swagger',
 '[{"path":"composer.json","content":"{\\n    \\"name\\": \\"{{.VendorName}}/{{.ProjectName}}\\",\\n    \\"type\\": \\"project\\",\\n    \\"require\\": {\\n        \\"php\\": \\"^8.2\\",\\n        \\"laravel/framework\\": \\"^11.0\\",\\n        \\"laravel/tinker\\": \\"^2.9\\",\\n        \\"predis/predis\\": \\"^2.0\\",\\n        \\"darkaonline/l5-swagger\\": \\"^8.6\\"\\n    },\\n    \\"require-dev\\": {\\n        \\"phpunit/phpunit\\": \\"^11.0\\",\\n        \\"mockery/mockery\\": \\"^1.6\\"\\n    },\\n    \\"autoload\\": {\\n        \\"psr-4\\": {\\n            \\"App\\\\\\\\\\": \\"app/\\",\\n            \\"Database\\\\\\\\Factories\\\\\\\\\\": \\"database/factories/\\",\\n            \\"Database\\\\\\\\Seeders\\\\\\\\\\": \\"database/seeders/\\"\\n        }\\n    },\\n    \\"scripts\\": {\\n        \\"post-autoload-dump\\": [\\"Illuminate\\\\\\\\Foundation\\\\\\\\ComposerScripts::postAutoloadDump\\", \\"@php artisan package:discover --ansi\\"],\\n        \\"post-update-cmd\\": [\\"@php artisan vendor:publish --tag=laravel-assets --ansi --force\\"]\\n    },\\n    \\"config\\": {\\n        \\"optimize-autoloader\\": true,\\n        \\"preferred-install\\": \\"dist\\",\\n        \\"sort-packages\\": true,\\n        \\"allow-plugins\\": {}\\n    },\\n    \\"minimum-stability\\": \\"stable\\",\\n    \\"prefer-stable\\": true\\n}","is_template":true},{"path":"app/Http/Kernel.php","content":"<?php\\n\\nnamespace App\\\\Http;\\n\\nuse Illuminate\\\\Foundation\\\\Http\\\\Kernel as HttpKernel;\\n\\nclass Kernel extends HttpKernel\\n{\\n    protected $middleware = [\\n        \\\\Illuminate\\\\Foundation\\\\Http\\\\Middleware\\\\ValidatePostSize::class,\\n        \\\\Illuminate\\\\Foundation\\\\Http\\\\Middleware\\\\TrimStrings::class,\\n        \\\\Illuminate\\\\Foundation\\\\Http\\\\Middleware\\\\ConvertEmptyStringsToNull::class,\\n    ];\\n}","is_template":true},{"path":"app/Models/User.php","content":"<?php\\n\\nnamespace App\\\\Models;\\n\\nuse Illuminate\\\\Database\\\\Eloquent\\\\Factories\\\\HasFactory;\\nuse Illuminate\\\\Foundation\\\\Auth\\\\User as Authenticatable;\\n\\nclass User extends Authenticatable\\n{\\n    use HasFactory;\\n    protected $fillable = [\\"name\\", \\"email\\", \\"password\\"];\\n    protected $hidden = [\\"password\\", \\"remember_token\\"];\\n}","is_template":true},{"path":"config/database.php","content":"<?php\\nreturn [\\n    \\"default\\\" => env(\\"DB_CONNECTION\\", \\"pgsql\\"),\\n    \\"connections\\" => [\\n        \\"pgsql\\" => [\\n            \\"driver\\" => \\"pgsql\\",\\n            \\"url\\" => env(\\"DATABASE_URL\\"),\\n            \\"host\\" => env(\\"DB_HOST\\", \\"127.0.0.1\\"),\\n            \\"port\\" => env(\\"DB_PORT\\", \\"5432\\"),\\n            \\"database\\" => env(\\"DB_DATABASE\\", \\"{{.ProjectName}}\\"),\\n            \\"username\\" => env(\\"DB_USERNAME\\", \\"postgres\\"),\\n            \\"password\\" => env(\\"DB_PASSWORD\\", \\"\\"),\\n        ],\\n    ],\\n];","is_template":true},{"path":".env.example","content":"APP_NAME={{.ProjectName}}\\nAPP_ENV=local\\nAPP_KEY=\\nDB_CONNECTION=pgsql\\nDB_HOST=127.0.0.1\\nDB_PORT=5432\\nDB_DATABASE={{.ProjectName}}\\nREDIS_HOST=127.0.0.1","is_template":true},{"path":"Dockerfile","content":"FROM php:8.2-fpm-alpine\\nRUN docker-php-ext-install pdo_pgsql pcntl\\nCOPY . /var/www/html\\nWORKDIR /var/www/html\\nRUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer\\nRUN composer install --no-dev --optimize-autoloader\\nRUN php artisan key:generate","is_template":true},{"path":".gitignore","content":"/vendor\\n/node_modules\\n.env\\nstorage/*.key","is_template":false}]',
 '[{"name":"ProjectName","label":"项目名称","type":"text","default":"my-project","required":true},{"name":"VendorName","label":"Vendor名","type":"text","default":"mycompany","required":true}]',
 '{"docker_image":"composer:latest","test_cmd":"cd /app && composer install && php vendor/bin/phpunit","coverage_cmd":"cd /app && php vendor/bin/phpunit --coverage-text"}',
 '{"dockerfile":"FROM composer:latest AS build\\nWORKDIR /app\\nCOPY composer.json composer.lock ./\\nRUN composer install --no-dev --optimize-autoloader\\nCOPY . .\\nRUN php artisan key:generate\\nFROM php:8.2-fpm-alpine\\nCOPY --from=build /app /var/www/html\\nWORKDIR /var/www/html","build_cmd":"composer install --no-dev","output_dir":"public/"}',
 'php', 2, 1, 0, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),

-- Node.js Express
('Express 项目', 'express', 'node', 'express', 'Node.js Express 后端项目，集成 TypeScript、Prisma ORM、Swagger',
 '[{"path":"package.json","content":"{\\n  \\"name\\": \\"{{.ProjectName}}\\",\\n  \\"version\\": \\"1.0.0\\",\\n  \\"scripts\\": {\\n    \\"dev\\": \\"ts-node-dev --respawn src/index.ts\\",\\n    \\"build\\": \\"tsc\\",\\n    \\"start\\": \\"node dist/index.js\\",\\n    \\"test\\": \\"jest --coverage\\",\\n    \\"lint\\": \\"eslint src/\\\\"\\n  },\\n  \\"dependencies\\": {\\n    \\"express\\": \\"^4.18.2\\",\\n    \\"cors\\": \\"^2.8.5\\",\\n    \\"helmet\\": \\"^7.1.0\\",\\n    \\"@prisma/client\\": \\"^5.7.0\\",\\n    \\"ioredis\\": \\"^5.3.2\\",\\n    \\"swagger-jsdoc\\": \\"^6.2.8\\",\\n    \\"swagger-ui-express\\": \\"^5.0.0\\"\\n  },\\n  \\"devDependencies\\": {\\n    \\"typescript\\": \\"^5.3.0\\",\\n    \\"@types/express\\": \\"^4.17.21\\",\\n    \\"@types/node\\": \\"^20.10.0\\",\\n    \\"ts-node-dev\\": \\"^2.0.0\\",\\n    \\"jest\\": \\"^29.7.0\\",\\n    \\"ts-jest\\": \\"^29.1.0\\",\\n    \\"@types/jest\\": \\"^29.5.0\\",\\n    \\"eslint\\": \\"^8.55.0\\"\\n  }\\n}","is_template":true},{"path":"tsconfig.json","content":"{\\n  \\"compilerOptions\\": {\\n    \\"target\\": \\"ES2022\\",\\n    \\"module\\": \\"commonjs\\",\\n    \\"lib\\": [\\"ES2022\\"],\\n    \\"outDir\\": \\"./dist\\",\\n    \\"rootDir\\": \\"./src\\",\\n    \\"strict\\": true,\\n    \\"esModuleInterop\\": true,\\n    \\"skipLibCheck\\": true,\\n    \\"forceConsistentCasingInFileNames\\": true\\n  },\\n  \\"include\\": [\\"src/**/*\\"],\\n  \\"exclude\\": [\\"node_modules\\", \\"dist\\", \\"__tests__\\"]\\n}","is_template":true},{"path":"src/index.ts","content":"import express from \\"express\\";\\nimport cors from \\"cors\\";\\nimport helmet from \\"helmet\\";\\n\\nconst app = express();\\nconst PORT = process.env.PORT || {{.Port}};\\n\\napp.use(helmet());\\napp.use(cors());\\napp.use(express.json());\\n\\napp.get(\\"/health\\", (req, res) => {\\n  res.json({ status: \\"ok\\", timestamp: Date.now() });\\n});\\n\\napp.listen(PORT, () => {\\n  console.log(\`Server running on port \\${PORT}\`);\\n});\\n\\nexport default app;","is_template":true},{"path":"Dockerfile","content":"FROM node:20-alpine AS build\\nWORKDIR /app\\nCOPY package*.json ./\\nRUN npm ci\\nCOPY . .\\nRUN npm run build\\nFROM node:20-alpine\\nCOPY --from=build /app/dist ./dist\\nCOPY --from=build /app/node_modules ./node_modules\\nCOPY --from=build /app/package.json ./\\nEXPOSE {{.Port}}\\nCMD [\\"node\\", \\"dist/index.js\\"]","is_template":true},{"path":".gitignore","content":"node_modules/\\ndist/\\ncoverage/\\n.env","is_template":false}]',
 '[{"name":"ProjectName","label":"项目名称","type":"text","default":"my-project","required":true},{"name":"Port","label":"服务端口","type":"number","default":"3000","required":true}]',
 '{"docker_image":"node:20-alpine","test_cmd":"cd /app && npm ci && npm test","coverage_cmd":"cd /app && npm ci && npm test -- --coverage"}',
 '{"dockerfile":"FROM node:20-alpine AS build\\nWORKDIR /app\\nCOPY package*.json ./\\nRUN npm ci\\nCOPY . .\\nRUN npm run build\\nFROM node:20-alpine\\nCOPY --from=build /app/dist ./dist\\nCOPY --from=build /app/node_modules ./node_modules\\nEXPOSE 3000\\nCMD [\\"node\\",\\"dist/index.js\\"]","build_cmd":"npm run build","output_dir":"dist/"}',
 'node', 3, 1, 0, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),

-- Go Gin
('Gin 项目', 'gin', 'go', 'gin', 'Go Gin 后端项目，集成 GORM、Redis、Swagger',
 '[{"path":"go.mod","content":"module {{.ModuleName}}\\n\\ngo 1.21\\n\\nrequire (\\n    github.com/gin-gonic/gin v1.9.1\\n    gorm.io/gorm v1.25.5\\n    gorm.io/driver/postgres v1.5.4\\n    github.com/redis/go-redis/v9 v9.3.0\\n    github.com/swaggo/files v1.0.1\\n    github.com/swaggo/gin-swagger v1.6.0\\n)","is_template":true},{"path":"cmd/main.go","content":"package main\\n\\nimport (\\n    \\"{{.ModuleName}}/internal/router\\"\\n    \\"github.com/gin-gonic/gin\\"\\n)\\n\\nfunc main() {\\n    r := gin.Default()\\n    router.Setup(r)\\n    r.Run(\\"::{{.Port}}\\")\\n}","is_template":true},{"path":"internal/router/router.go","content":"package router\\n\\nimport \\"github.com/gin-gonic/gin\\"\\n\\nfunc Setup(r *gin.Engine) {\\n    r.GET(\\"/health\\", func(c *gin.Context) {\\n        c.JSON(200, gin.H{\\"status\\": \\"ok\\"})\\n    })\\n    api := r.Group(\\"/api\\")\\n    {\\n        // Register routes here\\n        _ = api\\n    }\\n}","is_template":true},{"path":"internal/model/response.go","content":"package model\\n\\ntype Result struct {\\n    Code    int         \\"json:\\\\"code\\\\"\\"\\n    Message string      \\"json:\\\\"message\\\\"\\"\\n    Data    interface{} \\"json:\\\\"data\\\\"\\"\\n}\\n\\nfunc Success(data interface{}) Result {\\n    return Result{Code: 200, Message: \\"success\\", Data: data}\\n}\\n\\nfunc Error(code int, msg string) Result {\\n    return Result{Code: code, Message: msg}\\n}","is_template":true},{"path":"Dockerfile","content":"FROM golang:1.21-alpine AS build\\nWORKDIR /app\\nCOPY go.mod go.sum ./\\nRUN go mod download\\nCOPY . .\\nRUN CGO_ENABLED=0 go build -o /server cmd/main.go\\nFROM alpine:latest\\nCOPY --from=build /server /server\\nEXPOSE {{.Port}}\\nCMD [\\"/server\\"]","is_template":true},{"path":".gitignore","content":"/server\\n*.exe\\nvendor/","is_template":false}]',
 '[{"name":"ModuleName","label":"模块名","type":"text","default":"github.com/example/my-project","required":true},{"name":"Port","label":"服务端口","type":"number","default":"8080","required":true}]',
 '{"docker_image":"golang:1.21-alpine","test_cmd":"cd /app && go test ./... -v -cover","coverage_cmd":"cd /app && go test ./... -coverprofile=coverage.out && go tool cover -func=coverage.out"}',
 '{"dockerfile":"FROM golang:1.21-alpine AS build\\nWORKDIR /app\\nCOPY go.mod go.sum ./\\nRUN go mod download\\nCOPY . .\\nRUN CGO_ENABLED=0 go build -o /server cmd/main.go\\nFROM alpine:latest\\nCOPY --from=build /server /server\\nEXPOSE 8080\\nCMD [\\"/server\\"]","build_cmd":"go build -o server cmd/main.go","output_dir":"."}',
 'go', 4, 1, 0, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),

-- Python FastAPI
('FastAPI 项目', 'fastapi', 'python', 'fastapi', 'Python FastAPI 后端项目，集成 SQLAlchemy、Redis、Alembic',
 '[{"path":"requirements.txt","content":"fastapi==0.108.0\\nuvicorn[standard]==0.25.0\\nsqlalchemy==2.0.23\\npsycopg2-binary==2.9.9\\nalembic==1.13.0\\nredis==5.0.1\\npydantic==2.5.2\\npydantic-settings==2.1.0\\npytest==7.4.3\\nhttpx==0.25.2\\npytest-cov==4.1.0","is_template":false},{"path":"app/main.py","content":"from fastapi import FastAPI\\nfrom fastapi.middleware.cors import CORSMiddleware\\n\\napp = FastAPI(title=\\"{{.ProjectName}}\\", version=\\"1.0.0\\")\\n\\napp.add_middleware(\\n    CORSMiddleware,\\n    allow_origins=[\\"*\\"],\\n    allow_methods=[\\"*\\"],\\n    allow_headers=[\\"*\\"],\\n)\\n\\n@app.get(\\"/health\\")\\nasync def health():\\n    return {\\"status\\": \\"ok\\"}\\n","is_template":true},{"path":"app/core/config.py","content":"from pydantic_settings import BaseSettings\\n\\nclass Settings(BaseSettings):\\n    APP_NAME: str = \\"{{.ProjectName}}\\"\\n    DATABASE_URL: str = \\"postgresql://postgres:postgres@localhost:5432/{{.ProjectName}}\\"\\n    REDIS_URL: str = \\"redis://localhost:6379/0\\"\\n    class Config:\\n        env_file = \\".env\\"\\n\\nsettings = Settings()","is_template":true},{"path":"app/core/database.py","content":"from sqlalchemy import create_engine\\nfrom sqlalchemy.orm import sessionmaker, declarative_base\\nfrom .config import settings\\n\\nengine = create_engine(settings.DATABASE_URL)\\nSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)\\nBase = declarative_base()\\n\\ndef get_db():\\n    db = SessionLocal()\\n    try:\\n        yield db\\n    finally:\\n        db.close()","is_template":true},{"path":"Dockerfile","content":"FROM python:3.12-slim\\nWORKDIR /app\\nCOPY requirements.txt .\\nRUN pip install --no-cache-dir -r requirements.txt\\nCOPY . .\\nEXPOSE {{.Port}}\\nCMD [\\"uvicorn\\", \\"app.main:app\\", \\"--host\\", \\"0.0.0.0\\", \\"--port\\", \\"{{.Port}}\\"]","is_template":true},{"path":".gitignore","content":"__pycache__/\\n*.pyc\\n.env\\n.venv/","is_template":false}]',
 '[{"name":"ProjectName","label":"项目名称","type":"text","default":"my-project","required":true},{"name":"Port","label":"服务端口","type":"number","default":"8000","required":true}]',
 '{"docker_image":"python:3.12-slim","test_cmd":"cd /app && pip install -r requirements.txt && python -m pytest --cov=app -v","coverage_cmd":"cd /app && python -m pytest --cov=app --cov-report=term-missing"}',
 '{"dockerfile":"FROM python:3.12-slim\\nWORKDIR /app\\nCOPY requirements.txt .\\nRUN pip install --no-cache-dir -r requirements.txt\\nCOPY . .\\nEXPOSE 8000\\nCMD [\\"uvicorn\\",\\"app.main:app\\",\\"--host\\",\\"0.0.0.0\\",\\"--port\\",\\"8000\\"]","build_cmd":"pip install -r requirements.txt","output_dir":"."}',
 'python', 5, 1, 0, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000),

-- Vue3 + Vite + Ant Design
('Vue3 项目', 'vue3', 'javascript', 'vue', 'Vue3 前端项目，集成 Vite、Ant Design Vue、TypeScript、Pinia',
 '[{"path":"package.json","content":"{\\n  \\"name\\": \\"{{.ProjectName}}\\",\\n  \\"version\\": \\"1.0.0\\",\\n  \\"type\\": \\"module\\",\\n  \\"scripts\\": {\\n    \\"dev\\": \\"vite\\",\\n    \\"build\\": \\"vue-tsc && vite build\\",\\n    \\"preview\\": \\"vite preview\\",\\n    \\"test\\": \\"vitest\\",\\n    \\"test:coverage\\": \\"vitest --coverage\\",\\n    \\"lint\\": \\"eslint . --ext .vue,.js,.jsx,.ts,.tsx\\"\\n  },\\n  \\"dependencies\\": {\\n    \\"vue\\": \\"^3.4.0\\",\\n    \\"vue-router\\": \\"^4.2.0\\",\\n    \\"pinia\\": \\"^2.1.0\\",\\n    \\"ant-design-vue\\": \\"^4.1.0\\",\\n    \\"axios\\": \\"^1.6.0\\"\\n  },\\n  \\"devDependencies\\": {\\n    \\"@vitejs/plugin-vue\\": \\"^5.0.0\\",\\n    \\"vite\\": \\"^5.0.0\\",\\n    \\"typescript\\": \\"^5.3.0\\",\\n    \\"vue-tsc\\": \\"^1.8.0\\",\\n    \\"vitest\\": \\"^1.0.0\\",\\n    \\"@vue/test-utils\\": \\"^2.4.0\\"\\n  }\\n}","is_template":true},{"path":"vite.config.ts","content":"import { defineConfig } from \\"vite\\"\\nimport vue from \\"@vitejs/plugin-vue\\"\\nimport { resolve } from \\"path\\"\\n\\nexport default defineConfig({\\n  plugins: [vue()],\\n  resolve: {\\n    alias: { \\"@\\": resolve(__dirname, \\"src\\") }\\n  },\\n  server: { port: {{.Port}} }\\n})","is_template":true},{"path":"src/main.ts","content":"import { createApp } from \\"vue\\"\\nimport { createPinia } from \\"pinia\\"\\nimport Antd from \\"ant-design-vue\\"\\nimport App from \\"./App.vue\\"\\nimport router from \\"./router\\"\\nimport \\"ant-design-vue/dist/reset.css\\"\\n\\nconst app = createApp(App)\\napp.use(createPinia())\\napp.use(router)\\napp.use(Antd)\\napp.mount(\\"#app\\")","is_template":true},{"path":"src/App.vue","content":"<template>\\n  <router-view />\\n</template>","is_template":true},{"path":"src/router/index.ts","content":"import { createRouter, createWebHistory } from \\"vue-router\\"\\n\\nconst routes = [\\n  { path: \\"/\\", name: \\"Home\\", component: () => import(\\"@/pages/Home.vue\\") }\\n]\\n\\nexport default createRouter({\\n  history: createWebHistory(),\\n  routes\\n})","is_template":true},{"path":"Dockerfile","content":"FROM node:20-alpine AS build\\nWORKDIR /app\\nCOPY package*.json ./\\nRUN npm ci\\nCOPY . .\\nRUN npm run build\\nFROM nginx:alpine\\nCOPY --from=build /app/dist /usr/share/nginx/html\\nEXPOSE 80\\nCMD [\\"nginx\\",\\"-g\\",\\"daemon off;\\"]","is_template":true},{"path":".gitignore","content":"node_modules/\\ndist/\\ncoverage/","is_template":false}]',
 '[{"name":"ProjectName","label":"项目名称","type":"text","default":"my-vue-app","required":true},{"name":"Port","label":"开发端口","type":"number","default":"5173","required":true}]',
 '{"docker_image":"node:20-alpine","test_cmd":"cd /app && npm ci && npm test","coverage_cmd":"cd /app && npm ci && npm run test:coverage"}',
 '{"dockerfile":"FROM node:20-alpine AS build\\nWORKDIR /app\\nCOPY package*.json ./\\nRUN npm ci\\nCOPY . .\\nRUN npm run build\\nFROM nginx:alpine\\nCOPY --from=build /app/dist /usr/share/nginx/html\\nEXPOSE 80\\nCMD [\\"nginx\\",\\"-g\\",\\"daemon off;\\"]","build_cmd":"npm run build","output_dir":"dist/"}',
 'vue', 6, 1, 0, 1, UNIX_TIMESTAMP()*1000, UNIX_TIMESTAMP()*1000);
