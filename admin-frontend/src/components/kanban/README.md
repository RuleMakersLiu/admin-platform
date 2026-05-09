# AI 协作可视化看板

## 概述

这是一个用于可视化展示 AI 智能体协作过程的看板系统。基于 React + TypeScript + Ant Design + Zustand 技术栈开发。

## 功能特性

### 1. 智能体列视图
- 每个智能体（协调者、项目经理、后端开发、前端开发、测试工程师、报告专员）都有独立的列
- 实时显示智能体状态（空闲、工作中、等待中、异常）
- 显示智能体负载和完成任务数
- 展示智能体专长标签

### 2. 任务卡片
- 显示任务标题、描述、状态、优先级
- 支持进度条显示（进行中的任务）
- 显示任务标签和依赖关系
- 支持拖拽移动任务

### 3. 实时通信
- WebSocket 连接到 `ws://localhost:8086/ws`
- 30秒心跳保持连接
- 实时接收任务状态更新
- 支持断线重连（最多5次）

### 4. 过滤和搜索
- 按智能体过滤任务
- 按状态过滤任务
- 关键词搜索任务

## 项目结构

```
admin-frontend/src/
├── components/kanban/
│   ├── TaskCard.tsx          # 任务卡片组件
│   ├── TaskCard.css          # 任务卡片样式
│   ├── AgentColumn.tsx       # 智能体列组件
│   ├── AgentColumn.css       # 智能体列样式
│   ├── KanbanBoard.tsx       # 看板主组件
│   ├── KanbanBoard.css       # 看板主样式
│   └── index.ts              # 组件导出
├── pages/kanban/
│   ├── index.tsx             # 看板页面
│   └── index.css             # 页面样式
├── stores/kanban.ts          # Zustand 状态管理
├── hooks/useKanbanWebSocket.ts  # WebSocket Hook
├── types/kanban.ts           # TypeScript 类型定义
└── data/mockKanbanData.ts    # 模拟数据
```

## 使用方法

### 访问看板页面

启动前端项目后，访问 `/kanban` 路由即可看到看板页面。

```bash
cd admin-frontend
npm run dev
```

然后在浏览器中访问 `http://localhost:5173/kanban`

### WebSocket 消息格式

#### 客户端发送消息

```typescript
// 心跳
{
  type: 'kanban.heartbeat',
  timestamp: 1700000000000
}

// 请求同步数据
{
  type: 'kanban.sync',
  timestamp: 1700000000000
}

// 创建任务
{
  type: 'task.create',
  payload: {
    title: '新任务',
    status: 'pending',
    priority: 'medium',
    assignedAgent: 'be'
  },
  timestamp: 1700000000000
}

// 移动任务
{
  type: 'task.move',
  payload: {
    taskId: 'task-1',
    newStatus: 'in_progress',
    newAgent: 'be'
  },
  timestamp: 1700000000000
}
```

#### 服务器推送消息

```typescript
// 全量同步
{
  type: 'kanban.sync',
  payload: {
    tasks: [...],
    agents: {...}
  },
  timestamp: 1700000000000
}

// 任务创建
{
  type: 'task.created',
  payload: {
    id: 'task-1',
    title: '新任务',
    // ... 其他字段
  },
  timestamp: 1700000000000
}

// 任务状态更新
{
  type: 'task.updated',
  payload: {
    taskId: 'task-1',
    updates: {
      status: 'completed',
      progress: 100
    }
  },
  timestamp: 1700000000000
}

// 智能体状态变化
{
  type: 'agent.status_changed',
  payload: {
    agentId: 'be',
    status: 'working'
  },
  timestamp: 1700000000000
}
```

## 组件说明

### TaskCard

任务卡片组件，显示单个任务的详细信息。

**Props:**
- `task: Task` - 任务数据
- `onClick?: () => void` - 点击回调
- `draggable?: boolean` - 是否可拖拽（默认 true）
- `onDragStart?: (e: React.DragEvent, taskId: string) => void` - 拖拽开始回调

### AgentColumn

智能体列组件，显示单个智能体的所有任务。

**Props:**
- `agent: Agent` - 智能体数据
- `tasks: Task[]` - 任务列表
- `onTaskClick?: (task: Task) => void` - 任务点击回调
- `onTaskDrop?: (taskId: string, agentId: AgentType) => void` - 任务放置回调
- `onCreateTask?: (agentId: AgentType) => void` - 创建任务回调

### KanbanBoard

看板主组件，整合所有智能体列。

无需 props，内部使用 Zustand store 管理状态。

## 状态管理

使用 Zustand 进行状态管理，主要包含：

- `tasks: Task[]` - 所有任务
- `agents: Record<AgentType, Agent>` - 所有智能体
- `connectionStatus: KanbanWSStatus` - WebSocket 连接状态
- `filterAgent: AgentType | 'all'` - 智能体过滤器
- `filterStatus: TaskStatus | 'all'` - 状态过滤器
- `searchKeyword: string` - 搜索关键词

## 测试

可以使用 `mockKanbanData.ts` 中的模拟数据进行测试：

```typescript
import { initializeKanbanData } from '@/data/mockKanbanData';

const { agents, tasks } = initializeKanbanData();
// 使用模拟数据初始化 store
```

## 注意事项

1. 确保 WebSocket 服务器在 `ws://localhost:8086/ws` 运行
2. 如果使用不同的 WebSocket 地址，可以在 `useKanbanWebSocket` hook 中修改
3. 暗色主题已支持，会自动跟随系统主题
4. 响应式设计，支持移动端访问（建议平板或桌面端以获得最佳体验）

## 后续优化

- [ ] 添加任务详情抽屉
- [ ] 支持任务批量操作
- [ ] 添加任务时间线视图
- [ ] 支持导出看板数据
- [ ] 添加任务评论功能
- [ ] 支持任务附件上传
