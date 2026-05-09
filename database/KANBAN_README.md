# 看板系统数据库设计文档

## 📋 概述

本数据库设计支持智能体协作看板系统，采用 **PostgreSQL 15** 数据库。

## 🗂️ 表结构

### 1. agents（智能体表）

存储智能体的基本信息、能力和配置。

**主要字段：**
- `code`: 智能体唯一编码（BE/FE/PJM/QA/ARCH/CR）
- `name`: 智能体名称
- `capabilities`: 能力标签数组
- `system_prompt`: 系统提示词
- `model_config`: 模型配置（JSONB）
- `max_concurrent_tasks`: 最大并发任务数

**索引：**
- `idx_agents_code`: 编码索引
- `idx_agents_status`: 状态索引
- `idx_agents_tenant_id`: 租户索引

**外键：**
- `admin_id` → `sys_admin.id`（创建者）

---

### 2. tasks（任务表）

存储任务信息和执行状态。

**主要字段：**
- `task_no`: 任务编号（唯一）
- `title`: 任务标题
- `type`: 任务类型（feature/bug/optimize/test/docs）
- `priority`: 优先级（critical/high/medium/low）
- `status`: 状态（pending/assigned/running/completed/failed/cancelled）
- `progress`: 进度（0-100）
- `assignee_id`: 主负责人（智能体ID）
- `estimated_hours`: 预估工时
- `actual_hours`: 实际工时
- `tags`: 标签数组

**索引：**
- `idx_tasks_task_no`: 任务编号索引
- `idx_tasks_status`: 状态索引
- `idx_tasks_priority`: 优先级索引
- `idx_tasks_assignee_id`: 负责人索引
- `idx_tasks_deadline`: 截止时间索引

**外键：**
- `assignee_id` → `agents.id`
- `creator_id` → `sys_admin.id`
- `parent_task_id` → `tasks.id`

---

### 3. agent_sessions（智能体会话表）

存储智能体的会话记录。

**主要字段：**
- `session_id`: 会话ID（唯一）
- `agent_id`: 智能体ID
- `session_type`: 会话类型（autonomous/supervised/collaboration）
- `status`: 状态（active/paused/completed/failed）
- `message_count`: 消息数量
- `token_count`: Token消耗
- `task_id`: 关联任务ID

**索引：**
- `idx_agent_sessions_session_id`: 会话ID索引
- `idx_agent_sessions_agent_id`: 智能体索引
- `idx_agent_sessions_status`: 状态索引
- `idx_agent_sessions_start_time`: 开始时间索引

**外键：**
- `agent_id` → `agents.id`
- `admin_id` → `sys_admin.id`
- `task_id` → `tasks.id`

---

### 4. collaboration_records（协作记录表）

存储智能体之间的协作记录。

**主要字段：**
- `record_id`: 记录ID（唯一）
- `primary_agent_id`: 主要智能体ID
- `collaborator_agent_id`: 协作智能体ID
- `collaboration_type`: 协作类型（delegation/assistance/review/handoff）
- `action`: 动作（assign/transfer/requestHelp/review/approve/reject）
- `status`: 状态（pending/accepted/rejected/completed）
- `quality_score`: 质量评分（0-5）
- `efficiency_score`: 效率评分（0-5）

**索引：**
- `idx_collaboration_records_record_id`: 记录ID索引
- `idx_collaboration_records_task_id`: 任务索引
- `idx_collaboration_records_collaboration_type`: 协作类型索引
- `idx_collaboration_records_status`: 状态索引

**外键：**
- `task_id` → `tasks.id`
- `session_id` → `agent_sessions.id`
- `primary_agent_id` → `agents.id`
- `collaborator_agent_id` → `agents.id`
- `admin_id` → `sys_admin.id`

---

### 5. session_messages（会话消息表） - 扩展表

存储会话中的消息记录。

**主要字段：**
- `session_id`: 会话ID
- `sender_type`: 发送者类型（agent/admin/system）
- `sender_id`: 发送者ID
- `message_type`: 消息类型（text/code/file/action）
- `content`: 消息内容
- `tokens_used`: Token消耗

**索引：**
- `idx_session_messages_session_id`: 会话索引
- `idx_session_messages_sender_type`: 发送者类型索引
- `idx_session_messages_create_time`: 创建时间索引

**外键：**
- `session_id` → `agent_sessions.id`

---

## 🤖 初始数据

### 6个智能体

| Code | 名称 | 能力标签 | 最大并发任务 |
|------|------|----------|--------------|
| BE | 后端开发 | Java开发、Spring Boot、Python开发、FastAPI、数据库设计、微服务、性能优化 | 5 |
| FE | 前端开发 | Vue开发、React开发、TypeScript、Ant Design、前端架构、UI组件、性能优化 | 5 |
| PJM | 项目经理 | 项目规划、进度管理、资源协调、风险控制、需求分析、团队协作、沟通协调 | 10 |
| QA | 测试工程师 | 测试策略、测试用例、自动化测试、性能测试、缺陷管理、质量保证、测试工具 | 5 |
| ARCH | 系统架构师 | 架构设计、技术选型、微服务架构、分布式系统、性能优化、技术评审、最佳实践 | 3 |
| CR | 代码审查 | 代码审查、代码规范、安全审查、性能分析、最佳实践、重构建议、代码质量 | 10 |

---

## 🔗 表关系图

```
sys_admin (管理员表)
    ↓
agents (智能体表)
    ↓
tasks (任务表)
    ↓
agent_sessions (会话表)
    ↓
session_messages (消息表)

collaboration_records (协作记录)
    ↓
agents, tasks, agent_sessions
```

---

## 📊 查询示例

### 1. 查询智能体的任务统计

```sql
SELECT 
    a.code,
    a.name,
    COUNT(t.id) AS total_tasks,
    COUNT(CASE WHEN t.status = 'completed' THEN 1 END) AS completed_tasks,
    COUNT(CASE WHEN t.status = 'running' THEN 1 END) AS running_tasks,
    AVG(t.progress) AS avg_progress
FROM agents a
LEFT JOIN tasks t ON a.id = t.assignee_id
WHERE a.status = 1
GROUP BY a.id, a.code, a.name;
```

### 2. 查询智能体的协作记录

```sql
SELECT 
    a1.name AS primary_agent,
    a2.name AS collaborator_agent,
    cr.collaboration_type,
    cr.action,
    cr.status,
    cr.quality_score
FROM collaboration_records cr
JOIN agents a1 ON cr.primary_agent_id = a1.id
LEFT JOIN agents a2 ON cr.collaborator_agent_id = a2.id
ORDER BY cr.create_time DESC
LIMIT 20;
```

### 3. 查询会话统计

```sql
SELECT 
    a.name,
    COUNT(s.id) AS total_sessions,
    SUM(s.message_count) AS total_messages,
    SUM(s.token_count) AS total_tokens,
    AVG(s.duration) AS avg_duration
FROM agents a
LEFT JOIN agent_sessions s ON a.id = s.agent_id
WHERE s.status = 'completed'
GROUP BY a.id, a.name;
```

### 4. 查询任务执行效率

```sql
SELECT 
    a.name AS agent_name,
    t.type,
    AVG(t.actual_hours) AS avg_actual_hours,
    AVG(t.estimated_hours) AS avg_estimated_hours,
    AVG(t.actual_hours / t.estimated_hours) AS efficiency_ratio
FROM tasks t
JOIN agents a ON t.assignee_id = a.id
WHERE t.status = 'completed'
    AND t.estimated_hours > 0
    AND t.actual_hours > 0
GROUP BY a.id, a.name, t.type;
```

---

## 🚀 使用方法

### 1. 执行SQL脚本

```bash
# 进入PostgreSQL容器
docker exec -it admin-postgres psql -U postgres -d admin_platform

# 或者使用psql命令直接执行
psql -h localhost -U postgres -d admin_platform -f database/kanban_schema.sql
```

### 2. 验证表创建

```sql
-- 查看所有看板相关表
\dt

-- 查看智能体数据
SELECT id, code, name, status FROM agents;

-- 查看表结构
\d agents
\d tasks
\d agent_sessions
\d collaboration_records
\d session_messages
```

### 3. 清理数据（谨慎使用）

```sql
-- 删除所有看板相关表
DROP TABLE IF EXISTS session_messages CASCADE;
DROP TABLE IF EXISTS collaboration_records CASCADE;
DROP TABLE IF EXISTS agent_sessions CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS agents CASCADE;
```

---

## ⚠️ 注意事项

1. **时间戳格式**：所有时间字段使用毫秒时间戳（BIGINT）
2. **PostgreSQL特性**：
   - 使用 `BIGSERIAL` 作为自增主键
   - 使用 `TEXT[]` 存储数组
   - 使用 `JSONB` 存储JSON数据
   - 使用 `COMMENT ON` 添加字段注释
3. **外键约束**：确保删除顺序正确，使用 `ON DELETE CASCADE` 或 `ON DELETE SET NULL`
4. **租户隔离**：所有表都包含 `tenant_id` 字段，支持多租户
5. **索引优化**：已在常用查询字段上创建索引

---

## 📝 后续优化建议

1. **分区表**：对 `session_messages` 等大表按时间分区
2. **全文搜索**：对 `tasks.description` 添加全文搜索索引
3. **物化视图**：创建统计物化视图提升查询性能
4. **触发器**：添加自动更新 `update_time` 的触发器
5. **序列**：为 `task_no`、`record_id` 等创建专用序列

---

## 📚 相关文档

- [PostgreSQL 15 官方文档](https://www.postgresql.org/docs/15/index.html)
- [PostgreSQL JSONB 类型](https://www.postgresql.org/docs/15/datatype-json.html)
- [PostgreSQL 数组类型](https://www.postgresql.org/docs/15/arrays.html)

---

**创建时间**: 2026-03-13
**数据库版本**: PostgreSQL 15
**字符集**: UTF8
