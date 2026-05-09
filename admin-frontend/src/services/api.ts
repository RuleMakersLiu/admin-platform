import axios from 'axios'
import { useAuthStore } from '@/stores/auth'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    const token = useAuthStore.getState().token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    const { data } = response
    if (data.code === 200 || data.code === 0) {
      return data.data
    }
    return Promise.reject(new Error(data.message || '请求失败'))
  },
  (error) => {
    if (error.response) {
      const { status, data } = error.response
      if (status === 401) {
        useAuthStore.getState().logout()
        window.location.href = '/login'
      }
      const msg = data?.detail || data?.message || '请求失败'
      return Promise.reject(new Error(msg))
    }
    return Promise.reject(new Error('网络错误，请检查网络连接'))
  }
)

export default api

// 认证接口
export const authApi = {
  login: (data: { username: string; password: string; tenantId?: number }) =>
    api.post('/auth/login', data),
  logout: () => api.post('/auth/logout'),
  getInfo: () => api.get('/auth/info'),
  getMenus: () => api.get('/auth/menus'),
  refreshToken: () => api.post('/auth/refresh'),
  getTenants: () => axios.get('/api/auth/tenants').then(res => res.data.data),
}

// 代码生成接口
export const generatorApi = {
  chat: (data: { session_id?: string; prompt: string }) =>
    api.post('/generator/chat', data),
  getChatHistory: (sessionId: string) =>
    api.get(`/generator/chat/${sessionId}`),
  getConfigList: (params: any) => api.get('/generator/config', { params }),
  createConfig: (data: any) => api.post('/generator/config', data),
  updateConfig: (id: number, data: any) =>
    api.put(`/generator/config/${id}`, data),
  deleteConfig: (id: number) => api.delete(`/generator/config/${id}`),
  previewCode: (id: number) => api.get(`/generator/preview/${id}`),
  downloadCode: (id: number) => api.get(`/generator/download/${id}`),
}

// 部署接口
export const deployApi = {
  getProjects: () => api.get('/deploy/projects'),
  getTasks: (params: any) => api.get('/deploy/tasks', { params }),
  createTask: (data: any) => api.post('/deploy/tasks', data),
  executeTask: (id: number) => api.post(`/deploy/tasks/${id}/execute`),
  getTaskLogs: (id: number) => api.get(`/deploy/tasks/${id}/logs`),
  getContainers: () => api.get('/deploy/containers'),
  getContainerLogs: (id: string) => api.get(`/deploy/containers/${id}/logs`),
  startContainer: (id: string) => api.post(`/deploy/containers/${id}/start`),
  stopContainer: (id: string) => api.post(`/deploy/containers/${id}/stop`),
}

// 智能分身接口
export const agentApi = {
  // 对话
  chat: (data: { session_id: string; project_id?: string; message: string; agent_type?: string }) =>
    api.post('/agent/chat', data),
  // 流式对话 - 使用 fetch + ReadableStream 实现 SSE
  chatStream: async (
    data: { session_id: string; project_id?: string; message: string; agent_type?: string },
    callbacks: {
      onStart?: () => void
      onContent?: (content: string) => void
      onComplete?: (response: { msg_id?: string; agent_type?: string }) => void
      onError?: (error: string) => void
    }
  ) => {
    const token = useAuthStore.getState().token
    const response = await fetch('/api/agent/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    })

    if (!response.ok) {
      const errorText = await response.text()
      callbacks.onError?.(errorText || '请求失败')
      throw new Error(errorText || '请求失败')
    }

    const reader = response.body?.getReader()
    if (!reader) {
      callbacks.onError?.('无法获取响应流')
      throw new Error('无法获取响应流')
    }

    const decoder = new TextDecoder()
    let buffer = ''
    let eventData = ''
    let eventType = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            eventData = line.slice(5).trim()
          } else if (line === '' && eventType && eventData) {
            // 空行表示一个完整的 SSE 消息
            try {
              const parsedData = JSON.parse(eventData)

              switch (eventType) {
                case 'start':
                  callbacks.onStart?.()
                  break
                case 'content':
                  callbacks.onContent?.(parsedData.content || '')
                  break
                case 'complete':
                  callbacks.onComplete?.(parsedData)
                  break
                case 'error':
                  callbacks.onError?.(parsedData.message || '未知错误')
                  break
              }
            } catch (e) {
              console.error('SSE 数据解析失败:', e)
            }
            eventType = ''
            eventData = ''
          }
        }
      }
    } catch (error) {
      callbacks.onError?.(String(error))
      throw error
    }
  },
  getSessions: () => api.get('/agent/chat/sessions'),
  createSession: (data: { project_id?: string; title?: string }) =>
    api.post('/agent/chat/sessions', data),
  getSessionHistory: (sessionId: string) =>
    api.get(`/agent/chat/sessions/${sessionId}`),
  deleteSession: (sessionId: string) =>
    api.delete(`/agent/chat/sessions/${sessionId}`),

  // 项目
  getProjects: (params?: { status?: string; keyword?: string; page?: number; page_size?: number }) =>
    api.get('/agent/projects', { params }),
  createProject: (data: { project_name: string; description?: string; priority?: string }) =>
    api.post('/agent/projects', data),
  getProject: (id: string) => api.get(`/agent/projects/${id}`),
  updateProject: (id: string, data: Partial<{ project_name: string; description?: string; priority?: string; status?: string; agent_type?: string }>) =>
    api.put(`/agent/projects/${id}`, data),
  deleteProject: (id: string) => api.delete(`/agent/projects/${id}`),

  // 任务
  getTasks: (params?: { project_id?: string; status?: string; assignee?: string }) =>
    api.get('/agent/tasks', { params }),
  createTask: (data: {
    title: string;
    description: string;
    priority: string;
    assignee_type: string;
    project_id: string;
    due_date?: number | null;
    acceptance_criteria?: string[];
  }) => api.post('/agent/tasks', data),
  updateTaskStatus: (id: string, data: { status: string; progress?: number }) =>
    api.put(`/agent/tasks/${id}/status`, data),
  updateTask: (id: string, data: Record<string, any>) =>
    api.put(`/agent/tasks/${id}`, data),
  deleteTask: (id: string) =>
    api.delete(`/agent/tasks/${id}`),
  assignTask: (id: string, agentType: string) =>
    api.put(`/agent/tasks/${id}/assign`, { agent_type: agentType }),
  getTaskDetail: (id: string) =>
    api.get(`/agent/tasks/${id}`),

  // BUG
  getBugs: (params?: { project_id?: string; status?: string; severity?: string; keyword?: string; sortBy?: string; page?: number; page_size?: number }) =>
    api.get('/agent/bugs', { params }),
  createBug: (data: {
    title: string;
    description?: string;
    steps_to_reproduce?: string;
    expected_behavior?: string;
    actual_behavior?: string;
    severity: string;
    project_id: string;
    assignee?: string;
  }) => api.post('/agent/bugs', data),
  updateBugStatus: (id: string, data: { status: string; fix_note?: string }) =>
    api.put(`/agent/bugs/${id}/status`, data),
  getBugDetail: (id: string) =>
    api.get(`/agent/bugs/${id}`),
  resolveBug: (id: string, resolution: string) =>
    api.put(`/agent/bugs/${id}/resolve`, { resolution }),
  deleteBug: (id: string) =>
    api.delete(`/agent/bugs/${id}`),
}

// 项目管理接口（独立导出，便于直接调用）
export const projectApi = {
  list: (params?: { status?: string; keyword?: string; page?: number; page_size?: number }) =>
    api.get('/agent/projects', { params }),
  get: (id: string) => api.get(`/agent/projects/${id}`),
  create: (data: { project_name: string; description?: string; priority?: string; agent_type?: string }) =>
    api.post('/agent/projects', data),
  update: (id: string, data: Partial<{ project_name: string; description?: string; priority?: string; status?: string; agent_type?: string }>) =>
    api.put(`/agent/projects/${id}`, data),
  delete: (id: string) => api.delete(`/agent/projects/${id}`),
}

// 分身类型
export type AgentType = 'PM' | 'PJM' | 'BE' | 'FE' | 'QA' | 'RPT'

// 分身类型名称映射
export const agentTypeNames: Record<AgentType, string> = {
  PM: '产品经理',
  PJM: '项目经理',
  BE: '后端开发',
  FE: '前端开发',
  QA: '测试分身',
  RPT: '汇报分身',
}

// 分身类型颜色
export const agentTypeColors: Record<AgentType, string> = {
  PM: '#1890ff',
  PJM: '#722ed1',
  BE: '#52c41a',
  FE: '#eb2f96',
  QA: '#fa8c16',
  RPT: '#13c2c2',
}
