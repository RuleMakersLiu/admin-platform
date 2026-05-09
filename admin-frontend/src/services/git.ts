import api from './api'

export interface GitConfig {
  id: number
  name: string
  platform: string
  base_url: string
  access_token: string
  webhook_secret: string
  ssh_key: string
  is_default: number
  status: number
  create_time: number
  update_time: number
}

export interface GitConfigForm {
  name: string
  platform: string
  base_url?: string
  access_token: string
  webhook_secret?: string
  ssh_key?: string
  status?: number
}

export const gitService = {
  list: (params?: { keyword?: string; page?: number; page_size?: number }) =>
    api.get('/system/git', { params }),
  get: (id: number) => api.get(`/system/git/${id}`),
  create: (data: GitConfigForm) => api.post('/system/git', data),
  update: (id: number, data: Partial<GitConfigForm>) => api.put(`/system/git/${id}`, data),
  delete: (id: number) => api.delete(`/system/git/${id}`),
  test: (id: number) => api.post(`/system/git/${id}/test`),
  setDefault: (id: number) => api.post(`/system/git/${id}/default`),
  repos: (id: number) => api.get(`/system/git/${id}/repos`),
}

// Git 平台选项
export const gitPlatforms = [
  { value: 'github', label: 'GitHub' },
  { value: 'gitlab', label: 'GitLab' },
  { value: 'gitee', label: 'Gitee' },
  { value: 'gitea', label: 'Gitea' },
  { value: 'bitbucket', label: 'Bitbucket' },
  { value: 'custom', label: '自定义' },
]
