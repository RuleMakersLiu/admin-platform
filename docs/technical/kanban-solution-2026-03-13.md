# AI协作可视化看板 - 完整技术方案

> 生成时间：2026-03-13
> 参与智能体：架构设计师 + 前端开发 + 后端开发 + QA工程师
> 分析模型：GLM-5

---

## 一、方案概览

### 核心目标
- 实时展示6个AI智能体（PM/PJM/BE/FE/QA/RPT）的协作过程
- 验收标准：看板加载<3秒，状态更新延迟<500ms，支持50+并发任务

### 技术栈
| 层级 | 技术选型 |
|------|----------|
| 前端 | Vue 3 + Pinia + Ant Design Vue + @vue-flow/core + ECharts |
| 后端 | Laravel 8 + Swoole (WebSocket) |
| 存储 | MySQL 8.0 + Redis Cluster + ClickHouse |
| 测试 | Playwright (E2E) + k6 (性能) + Artillery (WebSocket) |

### 工作量评估
| 角色 | 工时 | 说明 |
|------|------|------|
| 前端 | 80h (10d) | 看板UI + WebSocket + 可视化 |
| 后端 | 60h (7.5d) | API + Swoole服务 + 状态同步 |
| Go | 0h | - |
| Python | 16h (2d) | 智能体状态上报 |
| **总计** | **156h (19.5d)** | 2人团队约2.5周 |

---

## 二、技术架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      前端层 (Vue 3)                              │
│  看板视图 | 智能体节点 | 任务卡片 | 时间线回放 | 统计图表        │
└────────────────────────────┬────────────────────────────────────┘
                             │ WebSocket + REST API
┌────────────────────────────┴────────────────────────────────────┐
│                    应用层 (Laravel 8 + Swoole)                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ HTTP API │  │WebSocket │  │ 任务队列  │  │ 状态同步  │        │
│  │ (FPM)    │  │ (Swoole) │  │ (Queue)  │  │ (Observer)│        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Redis Cluster │    │  MySQL 8.0   │    │ ClickHouse   │
│ (实时状态)    │    │ (业务数据)   │    │ (历史分析)   │
└──────────────┘    └──────────────┘    └──────────────┘
```

---

## 三、核心组件

### 3.1 前端组件树

```
src/
├── views/
│   └── KanbanBoard.vue              # 看板主容器
├── components/
│   ├── board/                       # 看板布局
│   │   ├── BoardContainer.vue
│   │   ├── ColumnPanel.vue
│   │   └── DropZone.vue
│   ├── card/                        # 任务卡片
│   │   ├── TaskCard.vue
│   │   ├── CardHeader.vue
│   │   └── CardMeta.vue
│   ├── agent/                       # 智能体节点
│   │   ├── AgentNode.vue
│   │   ├── AgentAvatar.vue
│   │   └── AgentStatusBadge.vue
│   ├── flow/                        # 流程图
│   │   ├── FlowCanvas.vue
│   │   ├── FlowEdge.vue
│   │   └── FlowMinimap.vue
│   └── timeline/                    # 时间线回放
│       ├── TimelineView.vue
│       ├── TimelinePlayer.vue
│       └── TimelineEvent.vue
├── stores/                          # Pinia状态管理
│   ├── agent.ts
│   ├── task.ts
│   ├── connection.ts
│   └── timeline.ts
└── composables/
    ├── useWebSocket.js
    ├── useDragDrop.js
    └── useTimeline.js
```

### 3.2 后端服务

```
app/
├── Http/Controllers/
│   ├── TaskController.php           # 任务CRUD
│   ├── AgentController.php          # 智能体状态
│   └── CollaborationController.php  # 协作记录
├── Services/
│   ├── TaskService.php
│   ├── AgentStatusService.php
│   └── CollaborationService.php
├── WebSocket/
│   ├── Server.php                   # Swoole服务
│   ├── Handler.php                  # 消息处理
│   └── RoomManager.php              # 房间管理
└── Observers/
    ├── TaskObserver.php             # 任务变更监听
    └── AgentObserver.php            # 智能体状态监听
```

---

## 四、数据库设计

### 核心表结构

```sql
-- 1. 智能体表
CREATE TABLE `agents` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(20) NOT NULL COMMENT 'PM/PJM/BE/FE/QA/RPT',
    `name` VARCHAR(100) NOT NULL,
    `color` VARCHAR(20),
    `capabilities` JSON,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_code` (`code`)
);

-- 2. 任务表
CREATE TABLE `tasks` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `project_id` BIGINT UNSIGNED NOT NULL,
    `title` VARCHAR(500) NOT NULL,
    `status` ENUM('pending', 'in_progress', 'review', 'completed', 'blocked'),
    `priority` ENUM('critical', 'high', 'medium', 'low'),
    `assigned_agent_id` BIGINT UNSIGNED,
    `dependencies` JSON,
    `estimated_hours` DECIMAL(6,2),
    `due_date` DATE,
    PRIMARY KEY (`id`),
    INDEX `idx_project_status` (`project_id`, `status`)
);

-- 3. 智能体会话表
CREATE TABLE `agent_sessions` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `agent_id` BIGINT UNSIGNED NOT NULL,
    `status` ENUM('idle', 'thinking', 'working', 'waiting', 'error'),
    `current_activity` VARCHAR(500),
    `progress` TINYINT UNSIGNED,
    `last_heartbeat_at` TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_agent_status` (`agent_id`, `status`)
);

-- 4. 协作记录表
CREATE TABLE `collaboration_records` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `project_id` BIGINT UNSIGNED NOT NULL,
    `agent_id` BIGINT UNSIGNED NOT NULL,
    `task_id` BIGINT UNSIGNED,
    `action` VARCHAR(50),
    `from_state` JSON,
    `to_state` JSON,
    `created_at` TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_project_time` (`project_id`, `created_at`)
);
```

---

## 五、API接口设计

### RESTful API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/projects/{id}/tasks | 获取项目任务列表 |
| POST | /api/tasks | 创建任务 |
| PUT | /api/tasks/{id} | 更新任务 |
| DELETE | /api/tasks/{id} | 删除任务 |
| PUT | /api/tasks/{id}/assign | 分配任务给智能体 |
| PUT | /api/tasks/{id}/status | 更新任务状态 |
| GET | /api/agents | 获取智能体列表 |
| GET | /api/agents/{id}/status | 获取智能体状态 |
| PUT | /api/agents/{id}/status | 更新智能体状态 |
| GET | /api/projects/{id}/timeline | 获取协作时间线 |
| GET | /api/projects/{id}/statistics | 获取统计数据 |

### WebSocket协议

```json
// 客户端 → 服务端
{
  "type": "subscribe",
  "channel": "kanban-updates",
  "projectId": 1
}

// 服务端 → 客户端（状态更新）
{
  "type": "agent:status",
  "data": {
    "id": "PM",
    "status": "working",
    "currentTask": "task-123",
    "progress": 45
  },
  "timestamp": 1710123456789
}

// 服务端 → 客户端（任务移动）
{
  "type": "task:moved",
  "data": {
    "taskId": "task-123",
    "fromAgent": "PM",
    "toAgent": "BE",
    "newStatus": "in_progress"
  },
  "timestamp": 1710123456789
}

// 心跳
{
  "type": "ping",
  "timestamp": 1710123456789
}
```

---

## 六、Redis缓存策略

### 数据结构设计

| Key | 类型 | TTL | 说明 |
|-----|------|-----|------|
| `agent:{id}:status` | Hash | 5min | 智能体实时状态 |
| `task:{id}` | Hash | 10min | 任务详情缓存 |
| `project:{id}:tasks` | List | 5min | 项目任务ID列表 |
| `kanban:connections` | Set | - | 在线WebSocket连接 |
| `room:{projectId}` | Set | - | 项目房间成员 |

### 缓存策略

```php
// Write-Through: 写入时同时更新缓存
public function updateAgentStatus($id, $status) {
    DB::transaction(function() use ($id, $status) {
        AgentSession::where('agent_id', $id)->update($status);
        Redis::hset("agent:{$id}:status", $status);
    });
}

// Cache-Aside: 读取时先查缓存
public function getTask($id) {
    $cached = Redis::hgetall("task:{$id}");
    if ($cached) return $cached;
    
    $task = Task::find($id);
    Redis::hmset("task:{$id}", $task->toArray());
    Redis::expire("task:{$id}", 600);
    return $task;
}
```

---

## 七、状态同步机制

### 6个智能体协作流程

```
用户提交需求
    │
    ▼
┌───────┐
│  PM   │ ← 需求分析，生成PRD
└───┬───┘
    │
    ▼
┌───────┐
│  PJM  │ ← 任务拆分，分配给各智能体
└───┬───┘
    │
    ├──→ ┌───────┐
    │    │  BE   │ ← 后端开发
    │    └───────┘
    │
    ├──→ ┌───────┐
    │    │  FE   │ ← 前端开发
    │    └───────┘
    │
    └──→ ┌───────┐
         │  QA   │ ← 测试验证
         └───┬───┘
             │
             ▼
         ┌───────┐
         │  RPT  │ ← 生成报告
         └───────┘
```

### 状态同步流程

1. **智能体上报状态** → 2. **Redis缓存更新** → 3. **Observer监听** → 4. **WebSocket广播** → 5. **前端渲染**

```php
// Observer监听状态变更
class AgentObserver {
    public function updated(AgentSession $session) {
        // 推送到Redis Pub/Sub
        Redis::publish('agent:status', json_encode([
            'id' => $session->agent_id,
            'status' => $session->status,
            'progress' => $session->progress
        ]));
    }
}

// WebSocket服务订阅并广播
$redis->subscribe(['agent:status'], function($channel, $message) {
    $data = json_decode($message, true);
    $this->broadcastToRoom("project:{$data['project_id']}", [
        'type' => 'agent:status',
        'data' => $data
    ]);
});
```

---

## 八、测试方案

### 测试用例统计

| 类型 | 数量 | 自动化率 |
|------|------|----------|
| 功能测试 | 10 | 70% |
| 性能测试 | 5 | 90% |
| 边界测试 | 8 | 50% |
| E2E测试 | 12 | 100% |

### 性能验收标准

| 指标 | 目标值 | 测试方法 |
|------|--------|----------|
| 状态更新延迟 | P95 < 500ms | k6压测 |
| 看板首屏加载 | < 3秒 | Puppeteer |
| 50并发任务渲染 | < 2秒 | Playwright |
| 断线重连数据恢复 | 100%无丢失 | 手动测试 |
| WebSocket吞吐 | 50条/秒不丢消息 | Artillery |

### 质量门禁

**必须通过项** (GO/NO-GO):
- [ ] P95状态更新延迟 < 500ms
- [ ] 断线重连5秒内恢复，无数据丢失
- [ ] 50并发任务加载 < 2秒
- [ ] E2E测试通过率 = 100%
- [ ] P0级Bug = 0
- [ ] 安全扫描无高危漏洞
- [ ] 单元测试覆盖率 > 70%

---

## 九、部署方案

### 灰度发布

| 阶段 | 流量 | 持续时间 | 验证内容 |
|------|------|----------|----------|
| 1 | 5% | 1-2天 | 功能完整性 |
| 2 | 20% | 2-3天 | 性能指标 |
| 3 | 50% | 2-3天 | 业务指标 |
| 4 | 100% | - | 全量发布 |

### 监控指标

| 指标 | 告警阈值 | 级别 |
|------|----------|------|
| websocket.connections | > 80%容量 | P2 |
| render.latency_p99 | > 2s | P1 |
| realtime.update.delay | > 500ms | P2 |
| websocket.error.rate | > 1% | P0 |

### 回滚预案

```bash
# 1. 切换流量到旧版本（1分钟）
kubectl rollout undo deployment/kanban-frontend

# 2. 回滚后端服务（2分钟）
kubectl rollout undo deployment/kanban-api

# 3. 验证回滚（2分钟）
./scripts/health-check.sh kanban
```

---

## 十、实施计划

### 里程碑

| 里程碑 | 时间 | 交付物 |
|--------|------|--------|
| M1 | 第1周 | 看板原型 + WebSocket基础 |
| M2 | 第2周 | 核心功能开发完成 |
| M3 | 第3周 | 性能优化 + 测试通过 |

### 下一步行动

1. **立即开始**
   - [ ] 数据库表创建
   - [ ] 前端组件脚手架
   - [ ] Swoole WebSocket服务搭建

2. **本周完成**
   - [ ] API接口开发
   - [ ] 前端看板基础布局
   - [ ] 智能体状态同步机制

3. **下周完成**
   - [ ] 拖拽交互
   - [ ] 历史回放功能
   - [ ] 性能测试

---

## 附录：相关文档

| 文档 | 路径 |
|------|------|
| 后端详细设计 | `docs/technical/backend-design/` |
| 测试方案 | `docs/technical/test-plan-kanban.md` |
| 产品经理分析 | `docs/pm-analysis-2026-03-13.md` |
| 项目经理分析 | `docs/pjm-analysis-2026-03-13.md` |

---

> 本方案由4个智能体（架构设计师/前端开发/后端开发/QA工程师）并行讨论生成
