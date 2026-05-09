import api from './api'

// 知识条目接口
export interface Knowledge {
  id: number
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

// 知识库服务
export const knowledgeService = {
  list: (params?: { keyword?: string; category?: string; agent_type?: string }) =>
    api.get('/knowledge/search/list', { params }),
  get: (id: number) => api.get(`/knowledge/${id}`),
  create: (data: KnowledgeForm) => api.post('/knowledge/create', data),
  update: (id: number, data: Partial<KnowledgeForm>) => api.put(`/knowledge/${id}`, data),
  delete: (id: number) => api.delete(`/knowledge/${id}`),
}

// 知识分类选项
export const knowledgeCategories = [
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
