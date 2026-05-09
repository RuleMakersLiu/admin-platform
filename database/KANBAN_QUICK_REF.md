# 看板系统数据库 - 快速参考

## 📦 已创建的文件

| 文件 | 说明 | 大小 |
|------|------|------|
| `kanban_schema.sql` | PostgreSQL表结构和初始数据SQL | ~21KB |
| `KANBAN_README.md` | 详细的设计文档和使用说明 | ~6.5KB |
| `init_kanban.sh` | 数据库初始化脚本 | ~1.4KB |
| `verify_kanban.sh` | 数据库验证脚本 | ~2.5KB |

---

## 🚀 快速开始

### 方式1: 使用初始化脚本（推荐）

```bash
cd /home/pastorlol/admin-platform/database

# 执行初始化
./init_kanban.sh

# 验证结果
./verify_kanban.sh
```

### 方式2: 手动执行SQL

```bash
# 进入PostgreSQL容器
docker exec -it admin-postgres psql -U postgres -d admin_platform

# 执行SQL文件
\i /path/to/kanban_schema.sql
```

### 方式3: 使用psql命令

```bash
psql -h localhost -U postgres -d admin_platform -f database/kanban_schema.sql
```

---

## 🗂️ 数据表概览

```
agents (智能体表)
├── id: 主键
├── code: 唯一编码 (BE/FE/PJM/QA/ARCH/CR)
├── name: 名称
├── capabilities: 能力标签数组
├── system_prompt: 系统提示词
├── model_config: 模型配置
└── max_concurrent_tasks: 最大并发任务

tasks (任务表)
├── id: 主键
├── task_no: 任务编号
├── title: 标题
├── type: 类型 (feature/bug/optimize/test/docs)
├── priority: 优先级 (critical/high/medium/low)
├── status: 状态 (pending/running/completed/failed)
├── assignee_id: 负责人 → agents.id
└── progress: 进度 (0-100)

agent_sessions (会话表)
├── id: 主键
├── session_id: 会话ID
├── agent_id: 智能体 → agents.id
├── task_id: 任务 → tasks.id
├── status: 状态 (active/paused/completed/failed)
└── token_count: Token消耗

collaboration_records (协作记录表)
├── id: 主键
├── primary_agent_id: 主要智能体 → agents.id
├── collaborator_agent_id: 协作智能体 → agents.id
├── collaboration_type: 协作类型
├── action: 动作
└── quality_score: 质量评分 (0-5)

session_messages (消息表)
├── id: 主键
├── session_id: 会话 → agent_sessions.id
├── sender_type: 发送者类型 (agent/admin/system)
├── content: 消息内容
└── tokens_used: Token消耗
```

---

## 🤖 初始智能体

| 编码 | 名称 | 主要能力 | 并发数 | 性格 |
|------|------|----------|--------|------|
| **BE** | 后端开发 | Java/Python/微服务 | 5 | 专业严谨 |
| **FE** | 前端开发 | Vue/React/UI | 5 | 细致创新 |
| **PJM** | 项目经理 | 规划/协调/管理 | 10 | 稳重高效 |
| **QA** | 测试工程师 | 测试策略/自动化 | 5 | 细致严谨 |
| **ARCH** | 系统架构师 | 架构设计/技术选型 | 3 | 前瞻系统 |
| **CR** | 代码审查 | 代码质量/最佳实践 | 10 | 专业严格 |

---

## 💡 常用查询

### 查看智能体任务统计

```sql
SELECT 
    a.code, a.name,
    COUNT(t.id) AS total_tasks,
    COUNT(CASE WHEN t.status = 'completed' THEN 1 END) AS completed,
    AVG(t.progress) AS avg_progress
FROM agents a
LEFT JOIN tasks t ON a.id = t.assignee_id
GROUP BY a.id;
```

### 查看最新协作记录

```sql
SELECT 
    a1.name AS from_agent,
    a2.name AS to_agent,
    cr.collaboration_type,
    cr.action,
    cr.status
FROM collaboration_records cr
JOIN agents a1 ON cr.primary_agent_id = a1.id
LEFT JOIN agents a2 ON cr.collaborator_agent_id = a2.id
ORDER BY cr.create_time DESC
LIMIT 10;
```

### 查看会话统计

```sql
SELECT 
    a.name,
    COUNT(s.id) AS sessions,
    SUM(s.message_count) AS messages,
    SUM(s.token_count) AS tokens
FROM agents a
LEFT JOIN agent_sessions s ON a.id = s.agent_id
WHERE s.status = 'completed'
GROUP BY a.id;
```

---

## 🔧 环境变量

初始化脚本支持以下环境变量：

```bash
# 数据库连接参数（默认值）
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=admin_platform
export DB_USER=postgres
export DB_PASSWORD=postgres

# 执行初始化
./init_kanban.sh
```

---

## 📊 数据库关系图

```
┌─────────────┐
│  sys_admin  │ (管理员表 - 已存在)
└──────┬──────┘
       │
       ├─────────────────┐
       │                 │
       ▼                 ▼
┌─────────────┐    ┌─────────────┐
│   agents    │◄───│    tasks    │ (任务表)
└──────┬──────┘    └──────┬──────┘
       │                  │
       │                  │
       ▼                  ▼
┌──────────────────────────────┐
│      agent_sessions          │ (会话表)
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│    session_messages          │ (消息表)
└──────────────────────────────┘

       ▲
       │
┌──────┴───────────────────────┐
│  collaboration_records       │ (协作记录)
└──────────────────────────────┘
```

---

## ⚠️ 注意事项

1. **数据库类型**: PostgreSQL 15
2. **时间戳格式**: 毫秒时间戳 (BIGINT)
3. **多租户**: 所有表都有 `tenant_id` 字段
4. **外键约束**: 删除时会级联或设置为NULL
5. **索引优化**: 已在常用字段上创建索引

---

## 📝 后续任务

- [ ] 在应用层创建对应的Model类
- [ ] 实现任务分配逻辑
- [ ] 实现智能体协作流程
- [ ] 创建看板前端页面
- [ ] 添加WebSocket实时通信

---

**创建日期**: 2026-03-13  
**数据库版本**: PostgreSQL 15  
**状态**: ✅ 已完成
