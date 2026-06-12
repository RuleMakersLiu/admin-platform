import api from './api'

// 知识条目接口
export interface Knowledge {
  id: string
  title: string
  content: string
  category: string
  tags: string[]
  agent_type: string
  status: number
  create_time: number
  update_time: number
}

// 知识条目表单接口
export interface KnowledgeForm {
  title: string
  content: string
  category: string
  tags: string[]
  agent_type: string
  status?: number
}

export interface KnowledgeGraphNode {
  id: string
  title: string
  category?: string
  tags?: string[]
  project_id?: number
}

export interface KnowledgeGraphEdge {
  id: string
  source: string
  target: string
  relation: string
  weight: number
}

export interface KnowledgeGraph {
  nodes: KnowledgeGraphNode[]
  edges: KnowledgeGraphEdge[]
}

export interface KnowledgeRelatedEdge {
  edge_id: string
  direction: 'outgoing' | 'incoming'
  source_id?: string
  target_id?: string
  relation_type: string
  weight: number
  description?: string
}

// 知识库服务
export const knowledgeService = {
  list: (params?: { keyword?: string; category?: string; agent_type?: string }) =>
    api.get('/knowledge/search/list', {
      params: {
        query: params?.keyword,
        category: params?.category,
      },
    }),
  get: (id: string) => api.get(`/knowledge/${id}`),
  create: (data: KnowledgeForm) => api.post('/knowledge/create', data),
  update: (id: string, data: Partial<KnowledgeForm>) => api.put(`/knowledge/${id}`, data),
  delete: (id: string) => api.delete(`/knowledge/${id}`),
  graph: (params?: { category?: string; max_nodes?: number }) =>
    api.get('/knowledge/graph/view', { params: { scope: 'project', ...params } }),
  related: (id: string, params?: { relation_type?: string; direction?: 'both' | 'outgoing' | 'incoming'; limit?: number }) =>
    api.get(`/knowledge/graph/related/${id}`, { params }),
  autoLink: (id: string) => api.post(`/knowledge/graph/auto-link/${id}`),
}

// 知识分类选项
export const knowledgeCategories = [
  { value: 'ai_upgrade', label: 'AI 升级报告' },
  { value: 'project_analysis', label: '项目分析' },
  { value: 'pipeline_delivery', label: '流水线交付' },
  { value: 'product', label: '产品需求' },
  { value: 'technical', label: '技术规范' },
  { value: 'business', label: '业务规则' },
  { value: 'faq', label: '常见问题' },
  { value: 'guide', label: '操作指南' },
  { value: 'best_practice', label: '最佳实践' },
  { value: 'other', label: '其他' },
]

// 分身类型选项（与 api.ts 中保持一致）
export const agentTypeOptions = [
  { value: 'PM', label: '产品经理' },
  { value: 'PJM', label: '项目经理' },
  { value: 'BE', label: '后端开发' },
  { value: 'FE', label: '前端开发' },
  { value: 'QA', label: '测试分身' },
  { value: 'RPT', label: '汇报分身' },
]

// 常用标签选项
export const commonTags = [
  '重要',
  '紧急',
  '待确认',
  '已归档',
  '常用',
  '参考',
  '模板',
  '规范',
]
