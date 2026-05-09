import api from './api'

export interface LLMConfig {
  id: number
  name: string
  provider: string
  base_url: string
  api_key: string
  model_name: string
  max_tokens: number
  temperature: number
  is_default: number
  status: number
  create_time: number
  update_time: number
}

export interface LLMConfigForm {
  name: string
  provider: string
  base_url: string
  api_key: string
  model_name: string
  max_tokens?: number
  temperature?: number
  status?: number
}

export const llmService = {
  list: (params?: { keyword?: string; page?: number; page_size?: number }) =>
    api.get('/system/llm', { params }),
  get: (id: number) => api.get(`/system/llm/${id}`),
  create: (data: LLMConfigForm) => api.post('/system/llm', data),
  update: (id: number, data: Partial<LLMConfigForm>) => api.put(`/system/llm/${id}`, data),
  delete: (id: number) => api.delete(`/system/llm/${id}`),
  test: (id: number) => api.post(`/system/llm/${id}/test`),
  setDefault: (id: number) => api.post(`/system/llm/${id}/default`),
}

// LLM 提供商选项
export const llmProviders = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'azure', label: 'Azure OpenAI' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'zhipu', label: '智谱 AI' },
  { value: 'qwen', label: '通义千问' },
  { value: 'ollama', label: 'Ollama (本地)' },
  { value: 'custom', label: '自定义' },
]
