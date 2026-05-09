// 看板任务状态
export type TaskStatus = 'pending' | 'in_progress' | 'review' | 'completed';

// 任务优先级
export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent';

// 智能体类型
export type AgentType = 'be' | 'fe' | 'pjm' | 'qa' | 'rpt' | 'coordinator';

// 智能体状态
export type AgentStatus = 'idle' | 'working' | 'waiting' | 'error';

// 单个任务
export interface Task {
  id: string;
  title: string;
  description?: string;
  status: TaskStatus;
  priority: TaskPriority;
  assignedAgent?: AgentType;
  createdBy: AgentType | 'human';
  createdAt: number;
  updatedAt: number;
  progress?: number; // 0-100
  dependencies?: string[]; // 任务ID列表
  tags?: string[];
  metadata?: {
    estimatedTime?: number;
    actualTime?: number;
    complexity?: number;
    [key: string]: any;
  };
}

// 智能体信息
export interface Agent {
  id: AgentType;
  name: string;
  avatar?: string;
  status: AgentStatus;
  currentTask?: string; // 当前任务ID
  completedTasks: number;
  specialties: string[];
  load: number; // 0-100 负载
  metadata?: {
    lastActive?: number;
    avgCompletionTime?: number;
    [key: string]: any;
  };
}

// 智能体列（看板的一列）
export interface AgentColumn {
  id: AgentType;
  agent: Agent;
  tasks: Task[];
}

// WebSocket 连接状态
export type KanbanWSStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

// WebSocket 消息类型
export type KanbanWSMessageType =
  | 'task.created'
  | 'task.updated'
  | 'task.deleted'
  | 'task.moved'
  | 'agent.status_changed'
  | 'agent.assigned'
  | 'kanban.sync'
  | 'kanban.heartbeat'
  | 'error';

// WebSocket 消息结构
export interface KanbanWSMessage<T = any> {
  type: KanbanWSMessageType;
  payload: T;
  timestamp: number;
  agentId?: AgentType;
}

// 看板统计
export interface KanbanStats {
  totalTasks: number;
  completedTasks: number;
  inProgressTasks: number;
  pendingTasks: number;
  reviewTasks: number;
  avgCompletionTime: number;
  agentStats: Record<AgentType, {
    completed: number;
    inProgress: number;
    avgTime: number;
  }>;
}

// 智能体名称映射
export const AGENT_NAMES: Record<AgentType, string> = {
  be: '后端开发',
  fe: '前端开发',
  pjm: '项目经理',
  qa: '测试工程师',
  rpt: '报告专员',
  coordinator: '协调者',
};

// 状态颜色映射
export const STATUS_COLORS: Record<TaskStatus, string> = {
  pending: '#default',
  in_progress: 'processing',
  review: 'warning',
  completed: 'success',
};

// 优先级颜色映射
export const PRIORITY_COLORS: Record<TaskPriority, string> = {
  low: 'default',
  medium: 'blue',
  high: 'orange',
  urgent: 'red',
};
