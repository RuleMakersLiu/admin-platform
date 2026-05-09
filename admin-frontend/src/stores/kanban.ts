import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import type { 
  Task, 
  Agent, 
  AgentType, 
  TaskStatus, 
  KanbanWSStatus,
  KanbanStats 
} from '@/types/kanban';

interface KanbanState {
  // 任务数据
  tasks: Task[];
  
  // 智能体数据
  agents: Record<AgentType, Agent>;
  
  // WebSocket 连接状态
  connectionStatus: KanbanWSStatus;
  
  // UI 状态
  selectedTaskId: string | null;
  filterAgent: AgentType | 'all';
  filterStatus: TaskStatus | 'all';
  searchKeyword: string;
  isLoading: boolean;
  
  // Actions - 任务管理
  setTasks: (tasks: Task[]) => void;
  addTask: (task: Task) => void;
  updateTask: (taskId: string, updates: Partial<Task>) => void;
  deleteTask: (taskId: string) => void;
  moveTask: (taskId: string, newStatus: TaskStatus, newAgent?: AgentType) => void;
  
  // Actions - 智能体管理
  setAgents: (agents: Record<AgentType, Agent>) => void;
  updateAgent: (agentId: AgentType, updates: Partial<Agent>) => void;
  updateAgentStatus: (agentId: AgentType, status: Agent['status']) => void;
  
  // Actions - 连接状态
  setConnectionStatus: (status: KanbanWSStatus) => void;
  
  // Actions - UI
  setSelectedTask: (taskId: string | null) => void;
  setFilterAgent: (agent: AgentType | 'all') => void;
  setFilterStatus: (status: TaskStatus | 'all') => void;
  setSearchKeyword: (keyword: string) => void;
  setIsLoading: (loading: boolean) => void;
  
  // Getters - 获取过滤后的数据
  getFilteredTasks: () => Task[];
  getTasksByAgent: (agentId: AgentType) => Task[];
  getTasksByStatus: (status: TaskStatus) => Task[];
  getTaskById: (taskId: string) => Task | undefined;
  getAgentWorkload: (agentId: AgentType) => number;
  getStats: () => KanbanStats;
}

// 默认智能体数据
const DEFAULT_AGENTS: Record<AgentType, Agent> = {
  be: {
    id: 'be',
    name: '后端开发',
    status: 'idle',
    completedTasks: 0,
    specialties: ['API开发', '数据库设计', '性能优化'],
    load: 0,
  },
  fe: {
    id: 'fe',
    name: '前端开发',
    status: 'idle',
    completedTasks: 0,
    specialties: ['UI实现', '组件开发', '交互优化'],
    load: 0,
  },
  pjm: {
    id: 'pjm',
    name: '项目经理',
    status: 'idle',
    completedTasks: 0,
    specialties: ['需求分析', '进度管理', '风险评估'],
    load: 0,
  },
  qa: {
    id: 'qa',
    name: '测试工程师',
    status: 'idle',
    completedTasks: 0,
    specialties: ['测试用例', '自动化测试', 'Bug追踪'],
    load: 0,
  },
  rpt: {
    id: 'rpt',
    name: '报告专员',
    status: 'idle',
    completedTasks: 0,
    specialties: ['文档编写', '进度报告', '数据可视化'],
    load: 0,
  },
  coordinator: {
    id: 'coordinator',
    name: '协调者',
    status: 'idle',
    completedTasks: 0,
    specialties: ['任务分配', '冲突解决', '资源调度'],
    load: 0,
  },
};

export const useKanbanStore = create<KanbanState>()(
  subscribeWithSelector(
    (set, get) => ({
      // 初始状态
      tasks: [],
      agents: DEFAULT_AGENTS,
      connectionStatus: 'disconnected',
      selectedTaskId: null,
      filterAgent: 'all',
      filterStatus: 'all',
      searchKeyword: '',
      isLoading: false,

      // 任务管理
      setTasks: (tasks) => set({ tasks }),

      addTask: (task) => set((state) => ({
        tasks: [...state.tasks, task],
      })),

      updateTask: (taskId, updates) => set((state) => ({
        tasks: state.tasks.map((task) =>
          task.id === taskId ? { ...task, ...updates, updatedAt: Date.now() } : task
        ),
      })),

      deleteTask: (taskId) => set((state) => ({
        tasks: state.tasks.filter((task) => task.id !== taskId),
        selectedTaskId: state.selectedTaskId === taskId ? null : state.selectedTaskId,
      })),

      moveTask: (taskId, newStatus, newAgent) => set((state) => ({
        tasks: state.tasks.map((task) =>
          task.id === taskId
            ? {
                ...task,
                status: newStatus,
                assignedAgent: newAgent || task.assignedAgent,
                updatedAt: Date.now(),
              }
            : task
        ),
      })),

      // 智能体管理
      setAgents: (agents) => set({ agents }),

      updateAgent: (agentId, updates) => set((state) => ({
        agents: {
          ...state.agents,
          [agentId]: { ...state.agents[agentId], ...updates },
        },
      })),

      updateAgentStatus: (agentId, status) => set((state) => ({
        agents: {
          ...state.agents,
          [agentId]: { 
            ...state.agents[agentId], 
            status,
            metadata: {
              ...state.agents[agentId].metadata,
              lastActive: Date.now(),
            },
          },
        },
      })),

      // 连接状态
      setConnectionStatus: (status) => set({ connectionStatus: status }),

      // UI 状态
      setSelectedTask: (taskId) => set({ selectedTaskId: taskId }),
      setFilterAgent: (agent) => set({ filterAgent: agent }),
      setFilterStatus: (status) => set({ filterStatus: status }),
      setSearchKeyword: (keyword) => set({ searchKeyword: keyword }),
      setIsLoading: (loading) => set({ isLoading: loading }),

      // Getters
      getFilteredTasks: () => {
        const state = get();
        let filtered = state.tasks;

        // 按智能体过滤
        if (state.filterAgent !== 'all') {
          filtered = filtered.filter(
            (task) => task.assignedAgent === state.filterAgent
          );
        }

        // 按状态过滤
        if (state.filterStatus !== 'all') {
          filtered = filtered.filter((task) => task.status === state.filterStatus);
        }

        // 按关键词搜索
        if (state.searchKeyword) {
          const keyword = state.searchKeyword.toLowerCase();
          filtered = filtered.filter(
            (task) =>
              task.title.toLowerCase().includes(keyword) ||
              task.description?.toLowerCase().includes(keyword) ||
              task.tags?.some((tag) => tag.toLowerCase().includes(keyword))
          );
        }

        return filtered;
      },

      getTasksByAgent: (agentId) => {
        return get().tasks.filter((task) => task.assignedAgent === agentId);
      },

      getTasksByStatus: (status) => {
        return get().tasks.filter((task) => task.status === status);
      },

      getTaskById: (taskId) => {
        return get().tasks.find((task) => task.id === taskId);
      },

      getAgentWorkload: (agentId) => {
        const tasks = get().tasks.filter(
          (task) => task.assignedAgent === agentId && task.status !== 'completed'
        );
        return tasks.length;
      },

      getStats: () => {
        const state = get();
        const tasks = state.tasks;
        
        const stats: KanbanStats = {
          totalTasks: tasks.length,
          completedTasks: tasks.filter((t) => t.status === 'completed').length,
          inProgressTasks: tasks.filter((t) => t.status === 'in_progress').length,
          pendingTasks: tasks.filter((t) => t.status === 'pending').length,
          reviewTasks: tasks.filter((t) => t.status === 'review').length,
          avgCompletionTime: 0,
          agentStats: {} as any,
        };

        // 计算每个智能体的统计
        const agentTypes: AgentType[] = ['be', 'fe', 'pjm', 'qa', 'rpt', 'coordinator'];
        for (const agentId of agentTypes) {
          const agentTasks = tasks.filter((t) => t.assignedAgent === agentId);
          const completed = agentTasks.filter((t) => t.status === 'completed');
          
          stats.agentStats[agentId] = {
            completed: completed.length,
            inProgress: agentTasks.filter((t) => t.status === 'in_progress').length,
            avgTime: 0, // TODO: 根据实际数据计算
          };
        }

        return stats;
      },
    })
  )
);

// 选择器 Hooks - 性能优化
export const useTasks = () => useKanbanStore((state) => state.tasks);
export const useAgents = () => useKanbanStore((state) => state.agents);
export const useConnectionStatus = () => 
  useKanbanStore((state) => state.connectionStatus);
export const useSelectedTask = () => useKanbanStore((state) => state.selectedTaskId);
export const useKanbanFilters = () =>
  useKanbanStore((state) => ({
    filterAgent: state.filterAgent,
    filterStatus: state.filterStatus,
    searchKeyword: state.searchKeyword,
  }));

export default useKanbanStore;
