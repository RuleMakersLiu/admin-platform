# AI协作可视化看板 - 后端API文档

## 基础信息

- **Base URL**: `http://api.example.com/api/v1`
- **认证方式**: Bearer Token (JWT)
- **数据格式**: JSON
- **字符编码**: UTF-8

---

## 1. 任务管理 API

### 1.1 创建任务
**POST** `/tasks`

**请求参数**:
```json
{
  "title": "string",
  "description": "string",
  "priority": "low|medium|high|urgent",
  "assigned_agents": ["agent_id_1", "agent_id_2"],
  "dependencies": ["task_id_1"],
  "estimated_time": 120,
  "tags": ["tag1", "tag2"]
}
```

**响应**:
```json
{
  "code": 200,
  "message": "Task created successfully",
  "data": {
    "task_id": "uuid",
    "title": "string",
    "status": "pending",
    "created_at": "2026-03-13 19:00:00",
    "updated_at": "2026-03-13 19:00:00"
  }
}
```

### 1.2 获取任务列表
**GET** `/tasks`

**查询参数**:
- `status`: pending|running|completed|failed
- `assigned_agent`: agent_id
- `priority`: low|medium|high|urgent
- `page`: 页码
- `per_page`: 每页数量

**响应**:
```json
{
  "code": 200,
  "data": {
    "tasks": [
      {
        "task_id": "uuid",
        "title": "string",
        "status": "running",
        "priority": "high",
        "assigned_agents": ["agent_id_1"],
        "progress": 60,
        "created_at": "2026-03-13 19:00:00",
        "started_at": "2026-03-13 19:05:00"
      }
    ],
    "pagination": {
      "current_page": 1,
      "per_page": 20,
      "total": 100,
      "last_page": 5
    }
  }
}
```

### 1.3 获取任务详情
**GET** `/tasks/{task_id}`

**响应**:
```json
{
  "code": 200,
  "data": {
    "task_id": "uuid",
    "title": "string",
    "description": "string",
    "status": "running",
    "priority": "high",
    "assigned_agents": [
      {
        "agent_id": "uuid",
        "name": "需求分析师",
        "role": "analyst"
      }
    ],
    "dependencies": ["task_id_1"],
    "progress": 60,
    "estimated_time": 120,
    "actual_time": 72,
    "tags": ["需求", "文档"],
    "collaboration_records": [
      {
        "record_id": "uuid",
        "agent_id": "uuid",
        "action": "started",
        "timestamp": "2026-03-13 19:05:00",
        "details": {}
      }
    ],
    "created_at": "2026-03-13 19:00:00",
    "updated_at": "2026-03-13 19:10:00"
  }
}
```

### 1.4 更新任务状态
**PATCH** `/tasks/{task_id}/status`

**请求参数**:
```json
{
  "status": "running|completed|failed",
  "progress": 80,
  "agent_id": "uuid",
  "message": "string"
}
```

**响应**:
```json
{
  "code": 200,
  "message": "Task status updated successfully",
  "data": {
    "task_id": "uuid",
    "status": "running",
    "progress": 80,
    "updated_at": "2026-03-13 19:15:00"
  }
}
```

### 1.5 分配任务给智能体
**POST** `/tasks/{task_id}/assign`

**请求参数**:
```json
{
  "agent_ids": ["agent_id_1", "agent_id_2"]
}
```

**响应**:
```json
{
  "code": 200,
  "message": "Task assigned successfully",
  "data": {
    "task_id": "uuid",
    "assigned_agents": ["agent_id_1", "agent_id_2"]
  }
}
```

### 1.6 删除任务
**DELETE** `/tasks/{task_id}`

**响应**:
```json
{
  "code": 200,
  "message": "Task deleted successfully"
}
```

---

## 2. 智能体状态 API

### 2.1 获取所有智能体状态
**GET** `/agents`

**响应**:
```json
{
  "code": 200,
  "data": {
    "agents": [
      {
        "agent_id": "uuid",
        "name": "需求分析师",
        "role": "analyst",
        "status": "working|idle|offline",
        "current_task": {
          "task_id": "uuid",
          "title": "分析用户需求"
        },
        "workload": 80,
        "last_heartbeat": "2026-03-13 19:10:00",
        "statistics": {
          "total_tasks": 50,
          "completed_tasks": 45,
          "avg_completion_time": 45
        }
      }
    ]
  }
}
```

### 2.2 获取单个智能体状态
**GET** `/agents/{agent_id}`

**响应**:
```json
{
  "code": 200,
  "data": {
    "agent_id": "uuid",
    "name": "需求分析师",
    "role": "analyst",
    "status": "working",
    "current_task": {
      "task_id": "uuid",
      "title": "分析用户需求",
      "progress": 60
    },
    "workload": 80,
    "capabilities": ["需求分析", "文档编写"],
    "last_heartbeat": "2026-03-13 19:10:00",
    "statistics": {
      "total_tasks": 50,
      "completed_tasks": 45,
      "failed_tasks": 2,
      "avg_completion_time": 45,
      "success_rate": 95.5
    },
    "recent_activities": [
      {
        "action": "completed",
        "task_title": "需求文档编写",
        "timestamp": "2026-03-13 18:00:00"
      }
    ]
  }
}
```

### 2.3 更新智能体状态
**PATCH** `/agents/{agent_id}/status`

**请求参数**:
```json
{
  "status": "working|idle|offline",
  "current_task_id": "uuid|null",
  "workload": 80,
  "heartbeat": true
}
```

**响应**:
```json
{
  "code": 200,
  "message": "Agent status updated successfully",
  "data": {
    "agent_id": "uuid",
    "status": "working",
    "updated_at": "2026-03-13 19:15:00"
  }
}
```

---

## 3. 协作记录 API

### 3.1 获取协作记录列表
**GET** `/collaborations`

**查询参数**:
- `task_id`: 任务ID
- `agent_id`: 智能体ID
- `action`: started|completed|transferred|failed
- `start_date`: 开始日期
- `end_date`: 结束日期
- `page`: 页码
- `per_page`: 每页数量

**响应**:
```json
{
  "code": 200,
  "data": {
    "records": [
      {
        "record_id": "uuid",
        "task_id": "uuid",
        "task_title": "需求分析",
        "agent_id": "uuid",
        "agent_name": "需求分析师",
        "action": "completed",
        "details": {
          "progress": 100,
          "output_files": ["需求文档.pdf"]
        },
        "duration": 1800,
        "timestamp": "2026-03-13 19:00:00"
      }
    ],
    "pagination": {
      "current_page": 1,
      "per_page": 20,
      "total": 200
    }
  }
}
```

### 3.2 创建协作记录
**POST** `/collaborations`

**请求参数**:
```json
{
  "task_id": "uuid",
  "agent_id": "uuid",
  "action": "started|completed|transferred|failed",
  "details": {
    "progress": 100,
    "message": "string",
    "output_files": ["file1.pdf"]
  }
}
```

**响应**:
```json
{
  "code": 200,
  "message": "Collaboration record created successfully",
  "data": {
    "record_id": "uuid",
    "timestamp": "2026-03-13 19:00:00"
  }
}
```

### 3.3 获取任务协作时间线
**GET** `/tasks/{task_id}/timeline`

**响应**:
```json
{
  "code": 200,
  "data": {
    "task_id": "uuid",
    "timeline": [
      {
        "timestamp": "2026-03-13 19:00:00",
        "agent_id": "uuid",
        "agent_name": "需求分析师",
        "action": "started",
        "details": {}
      },
      {
        "timestamp": "2026-03-13 19:10:00",
        "agent_id": "uuid",
        "agent_name": "需求分析师",
        "action": "transferred",
        "details": {
          "to_agent": "UI设计师",
          "reason": "需要设计界面"
        }
      },
      {
        "timestamp": "2026-03-13 19:20:00",
        "agent_id": "uuid",
        "agent_name": "UI设计师",
        "action": "completed",
        "details": {
          "output": "界面设计稿.fig"
        }
      }
    ]
  }
}
```

---

## 4. 统计分析 API

### 4.1 获取整体统计数据
**GET** `/statistics/overview`

**查询参数**:
- `period`: day|week|month
- `start_date`: 开始日期
- `end_date`: 结束日期

**响应**:
```json
{
  "code": 200,
  "data": {
    "period": "week",
    "tasks": {
      "total": 100,
      "completed": 85,
      "running": 10,
      "failed": 5,
      "completion_rate": 85
    },
    "agents": {
      "total": 6,
      "active": 5,
      "idle": 1,
      "avg_workload": 75
    },
    "time": {
      "avg_task_duration": 45,
      "total_work_time": 7200
    },
    "collaborations": {
      "total_transfers": 30,
      "success_rate": 95
    }
  }
}
```

### 4.2 获取智能体性能统计
**GET** `/statistics/agents`

**响应**:
```json
{
  "code": 200,
  "data": {
    "agents": [
      {
        "agent_id": "uuid",
        "name": "需求分析师",
        "performance": {
          "tasks_completed": 45,
          "success_rate": 95.5,
          "avg_completion_time": 40,
          "total_work_time": 1800
        }
      }
    ]
  }
}
```

---

## 5. WebSocket 连接

### 5.1 连接信息
**WebSocket URL**: `ws://ws.example.com:9501`

**连接参数**:
- `token`: JWT认证令牌
- `room`: dashboard|task_{id}|agent_{id}

### 5.2 客户端 → 服务端消息

#### 订阅房间
```json
{
  "type": "subscribe",
  "room": "dashboard"
}
```

#### 取消订阅
```json
{
  "type": "unsubscribe",
  "room": "dashboard"
}
```

#### 心跳
```json
{
  "type": "ping",
  "timestamp": 1710338400
}
```

### 5.3 服务端 → 客户端消息

#### 心跳响应
```json
{
  "type": "pong",
  "timestamp": 1710338400
}
```

#### 智能体状态更新
```json
{
  "type": "agent_status_update",
  "data": {
    "agent_id": "uuid",
    "status": "working",
    "current_task": "任务标题",
    "workload": 80
  },
  "timestamp": "2026-03-13 19:15:00"
}
```

#### 任务状态更新
```json
{
  "type": "task_status_update",
  "data": {
    "task_id": "uuid",
    "status": "running",
    "progress": 60,
    "agent_id": "uuid"
  },
  "timestamp": "2026-03-13 19:15:00"
}
```

#### 新协作记录
```json
{
  "type": "collaboration_created",
  "data": {
    "record_id": "uuid",
    "task_id": "uuid",
    "agent_id": "uuid",
    "action": "completed"
  },
  "timestamp": "2026-03-13 19:15:00"
}
```

#### 看板全景更新
```json
{
  "type": "dashboard_update",
  "data": {
    "agents": [...],
    "tasks": [...],
    "statistics": {...}
  },
  "timestamp": "2026-03-13 19:15:00"
}
```

---

## 6. 错误码定义

| 错误码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未授权 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 资源冲突 |
| 422 | 业务逻辑错误 |
| 500 | 服务器内部错误 |
| 503 | 服务不可用 |

---

## 7. 限流规则

- API请求：60次/分钟/IP
- WebSocket连接：5个/IP
- 心跳间隔：30秒
- 连接超时：90秒无心跳断开

---

## 8. 数据字段说明

### 任务状态 (task.status)
- `pending`: 待处理
- `running`: 执行中
- `completed`: 已完成
- `failed`: 失败

### 优先级 (task.priority)
- `low`: 低
- `medium`: 中
- `high`: 高
- `urgent`: 紧急

### 智能体状态 (agent.status)
- `working`: 工作中
- `idle`: 空闲
- `offline`: 离线

### 协作动作 (collaboration.action)
- `started`: 开始任务
- `completed`: 完成任务
- `transferred`: 转交任务
- `failed`: 任务失败
