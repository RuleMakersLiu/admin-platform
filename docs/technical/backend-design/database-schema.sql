-- ============================================
-- AI协作可视化看板 - 数据库表结构
-- 技术栈: Laravel 8 + MySQL 8.0+
-- 创建时间: 2026-03-13
-- ============================================

-- 设置字符集
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================
-- 1. 智能体表 (agents)
-- ============================================
DROP TABLE IF EXISTS `agents`;
CREATE TABLE `agents` (
  `id` CHAR(36) NOT NULL COMMENT '智能体UUID',
  `name` VARCHAR(100) NOT NULL COMMENT '智能体名称',
  `role` VARCHAR(50) NOT NULL COMMENT '角色: analyst, designer, frontend, backend, tester, pm',
  `status` ENUM('working', 'idle', 'offline') DEFAULT 'offline' COMMENT '当前状态',
  `current_task_id` CHAR(36) NULL COMMENT '当前任务ID',
  `workload` TINYINT UNSIGNED DEFAULT 0 COMMENT '工作负载 0-100',
  `capabilities` JSON NULL COMMENT '能力标签列表',
  `config` JSON NULL COMMENT '智能体配置',
  `last_heartbeat_at` TIMESTAMP NULL COMMENT '最后心跳时间',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted_at` TIMESTAMP NULL,
  PRIMARY KEY (`id`),
  INDEX `idx_role` (`role`),
  INDEX `idx_status` (`status`),
  INDEX `idx_last_heartbeat` (`last_heartbeat_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='智能体表';

-- ============================================
-- 2. 任务表 (tasks)
-- ============================================
DROP TABLE IF EXISTS `tasks`;
CREATE TABLE `tasks` (
  `id` CHAR(36) NOT NULL COMMENT '任务UUID',
  `title` VARCHAR(200) NOT NULL COMMENT '任务标题',
  `description` TEXT NULL COMMENT '任务描述',
  `status` ENUM('pending', 'running', 'completed', 'failed') DEFAULT 'pending' COMMENT '任务状态',
  `priority` ENUM('low', 'medium', 'high', 'urgent') DEFAULT 'medium' COMMENT '优先级',
  `progress` TINYINT UNSIGNED DEFAULT 0 COMMENT '进度 0-100',
  `estimated_time` INT UNSIGNED DEFAULT 0 COMMENT '预估时间(分钟)',
  `actual_time` INT UNSIGNED DEFAULT 0 COMMENT '实际耗时(分钟)',
  `tags` JSON NULL COMMENT '标签列表',
  `metadata` JSON NULL COMMENT '扩展元数据',
  `created_by` CHAR(36) NULL COMMENT '创建者ID',
  `started_at` TIMESTAMP NULL COMMENT '开始时间',
  `completed_at` TIMESTAMP NULL COMMENT '完成时间',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted_at` TIMESTAMP NULL,
  PRIMARY KEY (`id`),
  INDEX `idx_status` (`status`),
  INDEX `idx_priority` (`priority`),
  INDEX `idx_created_at` (`created_at`),
  INDEX `idx_started_at` (`started_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='任务表';

-- ============================================
-- 3. 任务依赖关系表 (task_dependencies)
-- ============================================
DROP TABLE IF EXISTS `task_dependencies`;
CREATE TABLE `task_dependencies` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT,
  `task_id` CHAR(36) NOT NULL COMMENT '任务ID',
  `depends_on_task_id` CHAR(36) NOT NULL COMMENT '依赖的任务ID',
  `type` ENUM('blocking', 'optional') DEFAULT 'blocking' COMMENT '依赖类型',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_task_dependency` (`task_id`, `depends_on_task_id`),
  INDEX `idx_depends_on` (`depends_on_task_id`),
  FOREIGN KEY (`task_id`) REFERENCES `tasks`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`depends_on_task_id`) REFERENCES `tasks`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='任务依赖关系表';

-- ============================================
-- 4. 任务-智能体关联表 (task_agents)
-- ============================================
DROP TABLE IF EXISTS `task_agents`;
CREATE TABLE `task_agents` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT,
  `task_id` CHAR(36) NOT NULL COMMENT '任务ID',
  `agent_id` CHAR(36) NOT NULL COMMENT '智能体ID',
  `role` ENUM('primary', 'secondary', 'reviewer') DEFAULT 'primary' COMMENT '参与角色',
  `assigned_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '分配时间',
  `started_at` TIMESTAMP NULL COMMENT '开始时间',
  `completed_at` TIMESTAMP NULL COMMENT '完成时间',
  `status` ENUM('assigned', 'working', 'completed', 'failed') DEFAULT 'assigned',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_task_agent` (`task_id`, `agent_id`),
  INDEX `idx_agent` (`agent_id`),
  FOREIGN KEY (`task_id`) REFERENCES `tasks`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`agent_id`) REFERENCES `agents`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='任务智能体关联表';

-- ============================================
-- 5. 协作记录表 (collaboration_records)
-- ============================================
DROP TABLE IF EXISTS `collaboration_records`;
CREATE TABLE `collaboration_records` (
  `id` CHAR(36) NOT NULL COMMENT '记录UUID',
  `task_id` CHAR(36) NOT NULL COMMENT '任务ID',
  `agent_id` CHAR(36) NOT NULL COMMENT '智能体ID',
  `action` ENUM('started', 'completed', 'transferred', 'failed') NOT NULL COMMENT '动作类型',
  `details` JSON NULL COMMENT '详细信息',
  `duration` INT UNSIGNED DEFAULT 0 COMMENT '持续时间(秒)',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_task` (`task_id`),
  INDEX `idx_agent` (`agent_id`),
  INDEX `idx_action` (`action`),
  INDEX `idx_created_at` (`created_at`),
  FOREIGN KEY (`task_id`) REFERENCES `tasks`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`agent_id`) REFERENCES `agents`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='协作记录表';

-- ============================================
-- 6. 智能体统计表 (agent_statistics)
-- ============================================
DROP TABLE IF EXISTS `agent_statistics`;
CREATE TABLE `agent_statistics` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT,
  `agent_id` CHAR(36) NOT NULL COMMENT '智能体ID',
  `date` DATE NOT NULL COMMENT '统计日期',
  `total_tasks` INT UNSIGNED DEFAULT 0 COMMENT '总任务数',
  `completed_tasks` INT UNSIGNED DEFAULT 0 COMMENT '完成任务数',
  `failed_tasks` INT UNSIGNED DEFAULT 0 COMMENT '失败任务数',
  `total_work_time` INT UNSIGNED DEFAULT 0 COMMENT '总工作时间(分钟)',
  `avg_completion_time` INT UNSIGNED DEFAULT 0 COMMENT '平均完成时间(分钟)',
  `success_rate` DECIMAL(5,2) DEFAULT 0.00 COMMENT '成功率',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_agent_date` (`agent_id`, `date`),
  INDEX `idx_date` (`date`),
  FOREIGN KEY (`agent_id`) REFERENCES `agents`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='智能体统计表';

-- ============================================
-- 7. WebSocket连接表 (websocket_connections)
-- ============================================
DROP TABLE IF EXISTS `websocket_connections`;
CREATE TABLE `websocket_connections` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT,
  `fd` INT UNSIGNED NOT NULL COMMENT 'Swoole连接描述符',
  `user_id` CHAR(36) NULL COMMENT '用户ID',
  `rooms` JSON NULL COMMENT '订阅的房间列表',
  `ip` VARCHAR(45) NULL COMMENT '客户端IP',
  `user_agent` VARCHAR(255) NULL COMMENT '用户代理',
  `connected_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '连接时间',
  `last_ping_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后心跳时间',
  `status` ENUM('active', 'inactive') DEFAULT 'active',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_fd` (`fd`),
  INDEX `idx_user` (`user_id`),
  INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='WebSocket连接表';

-- ============================================
-- 8. 系统日志表 (system_logs)
-- ============================================
DROP TABLE IF EXISTS `system_logs`;
CREATE TABLE `system_logs` (
  `id` BIGINT UNSIGNED AUTO_INCREMENT,
  `level` ENUM('debug', 'info', 'warning', 'error', 'critical') DEFAULT 'info',
  `category` VARCHAR(50) NOT NULL COMMENT '日志类别',
  `message` TEXT NOT NULL COMMENT '日志消息',
  `context` JSON NULL COMMENT '上下文数据',
  `agent_id` CHAR(36) NULL COMMENT '相关智能体ID',
  `task_id` CHAR(36) NULL COMMENT '相关任务ID',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_level` (`level`),
  INDEX `idx_category` (`category`),
  INDEX `idx_agent` (`agent_id`),
  INDEX `idx_task` (`task_id`),
  INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统日志表';

-- ============================================
-- 初始化数据 - 6个智能体
-- ============================================
INSERT INTO `agents` (`id`, `name`, `role`, `status`, `capabilities`, `config`) VALUES
(UUID(), '需求分析师', 'analyst', 'idle', '["需求分析", "文档编写", "用户调研"]', '{"max_concurrent_tasks": 1}'),
(UUID(), 'UI设计师', 'designer', 'idle', '["界面设计", "原型制作", "设计规范"]', '{"max_concurrent_tasks": 1}'),
(UUID(), '前端工程师', 'frontend', 'idle', '["Vue开发", "组件开发", "性能优化"]', '{"max_concurrent_tasks": 2}'),
(UUID(), '后端工程师', 'backend', 'idle', '["API开发", "数据库设计", "系统架构"]', '{"max_concurrent_tasks": 2}'),
(UUID(), '测试工程师', 'tester', 'idle', '["功能测试", "自动化测试", "性能测试"]', '{"max_concurrent_tasks": 2}'),
(UUID(), '项目经理', 'pm', 'idle', '["进度管理", "风险控制", "资源协调"]', '{"max_concurrent_tasks": 3}');

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================
-- 视图 - 任务看板视图
-- ============================================
CREATE OR REPLACE VIEW `v_task_dashboard` AS
SELECT 
    t.id,
    t.title,
    t.status,
    t.priority,
    t.progress,
    t.created_at,
    t.started_at,
    t.completed_at,
    GROUP_CONCAT(DISTINCT a.name) as assigned_agents,
    COUNT(DISTINCT a.id) as agent_count,
    (SELECT COUNT(*) FROM task_dependencies WHERE task_id = t.id) as dependency_count
FROM tasks t
LEFT JOIN task_agents ta ON t.id = ta.task_id
LEFT JOIN agents a ON ta.agent_id = a.id
WHERE t.deleted_at IS NULL
GROUP BY t.id;

-- ============================================
-- 视图 - 智能体工作台视图
-- ============================================
CREATE OR REPLACE VIEW `v_agent_workspace` AS
SELECT 
    a.id,
    a.name,
    a.role,
    a.status,
    a.workload,
    a.last_heartbeat_at,
    t.id as current_task_id,
    t.title as current_task_title,
    t.progress as current_task_progress,
    (SELECT COUNT(*) FROM task_agents WHERE agent_id = a.id AND status = 'assigned') as pending_tasks,
    (SELECT COUNT(*) FROM task_agents WHERE agent_id = a.id AND status = 'working') as working_tasks,
    (SELECT COUNT(*) FROM collaboration_records WHERE agent_id = a.id AND action = 'completed') as completed_tasks
FROM agents a
LEFT JOIN tasks t ON a.current_task_id = t.id
WHERE a.deleted_at IS NULL;

-- ============================================
-- 存储过程 - 更新智能体统计
-- ============================================
DELIMITER //
CREATE PROCEDURE `sp_update_agent_statistics`(IN p_agent_id CHAR(36), IN p_date DATE)
BEGIN
    INSERT INTO agent_statistics (
        agent_id, 
        date, 
        total_tasks, 
        completed_tasks, 
        failed_tasks, 
        total_work_time,
        avg_completion_time,
        success_rate
    )
    SELECT 
        p_agent_id,
        p_date,
        COUNT(DISTINCT task_id) as total_tasks,
        SUM(CASE WHEN action = 'completed' THEN 1 ELSE 0 END) as completed_tasks,
        SUM(CASE WHEN action = 'failed' THEN 1 ELSE 0 END) as failed_tasks,
        SUM(duration) / 60 as total_work_time,
        AVG(CASE WHEN action = 'completed' THEN duration / 60 ELSE NULL END) as avg_completion_time,
        (SUM(CASE WHEN action = 'completed' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(DISTINCT task_id), 0)) as success_rate
    FROM collaboration_records
    WHERE agent_id = p_agent_id
      AND DATE(created_at) = p_date
    ON DUPLICATE KEY UPDATE
        total_tasks = VALUES(total_tasks),
        completed_tasks = VALUES(completed_tasks),
        failed_tasks = VALUES(failed_tasks),
        total_work_time = VALUES(total_work_time),
        avg_completion_time = VALUES(avg_completion_time),
        success_rate = VALUES(success_rate),
        updated_at = NOW();
END //
DELIMITER ;

-- ============================================
-- 存储过程 - 清理过期连接
-- ============================================
DELIMITER //
CREATE PROCEDURE `sp_cleanup_inactive_connections`()
BEGIN
    DELETE FROM websocket_connections 
    WHERE status = 'inactive' 
       OR last_ping_at < DATE_SUB(NOW(), INTERVAL 90 SECOND);
END //
DELIMITER ;

-- ============================================
-- 触发器 - 任务状态变更日志
-- ============================================
DELIMITER //
CREATE TRIGGER `tr_task_status_change` 
AFTER UPDATE ON `tasks`
FOR EACH ROW
BEGIN
    IF OLD.status != NEW.status THEN
        INSERT INTO system_logs (level, category, message, context, task_id)
        VALUES (
            'info',
            'task_status_change',
            CONCAT('Task status changed from ', OLD.status, ' to ', NEW.status),
            JSON_OBJECT('old_status', OLD.status, 'new_status', NEW.status, 'progress', NEW.progress),
            NEW.id
        );
    END IF;
END //
DELIMITER ;

-- ============================================
-- 触发器 - 智能体状态变更日志
-- ============================================
DELIMITER //
CREATE TRIGGER `tr_agent_status_change` 
AFTER UPDATE ON `agents`
FOR EACH ROW
BEGIN
    IF OLD.status != NEW.status THEN
        INSERT INTO system_logs (level, category, message, context, agent_id)
        VALUES (
            'info',
            'agent_status_change',
            CONCAT('Agent ', NEW.name, ' status changed from ', OLD.status, ' to ', NEW.status),
            JSON_OBJECT('old_status', OLD.status, 'new_status', NEW.status),
            NEW.id
        );
    END IF;
END //
DELIMITER ;

-- ============================================
-- 索引优化建议
-- ============================================
-- 对于大量数据，考虑添加以下复合索引：
-- ALTER TABLE `collaboration_records` ADD INDEX `idx_task_agent_created` (`task_id`, `agent_id`, `created_at`);
-- ALTER TABLE `tasks` ADD INDEX `idx_status_priority_created` (`status`, `priority`, `created_at`);

-- ============================================
-- 分区建议 (对于大规模数据)
-- ============================================
-- collaboration_records 表按月分区：
-- ALTER TABLE `collaboration_records` PARTITION BY RANGE (YEAR(created_at)*100 + MONTH(created_at)) (
--     PARTITION p202603 VALUES LESS THAN (202604),
--     PARTITION p202604 VALUES LESS THAN (202605),
--     PARTITION pmax VALUES LESS THAN MAXVALUE
-- );

-- ============================================
-- 数据保留策略建议
-- ============================================
-- system_logs 保留 90 天
-- websocket_connections 自动清理
-- agent_statistics 按月归档
