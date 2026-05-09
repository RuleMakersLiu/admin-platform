import api from './api'

// 技能数据类型
export interface Skill {
  id: string
  name: string
  description: string
  longDescription?: string
  category: string
  categoryName: string
  author: string
  authorId: string
  version: string
  icon?: string
  tags: string[]
  rating: number
  ratingCount: number
  downloadCount: number
  createTime: number
  updateTime: number
  isDownloaded?: boolean
  isPublished?: boolean
}

// 分类数据类型
export interface Category {
  id: string
  name: string
  icon?: string
  count: number
}

// 评分请求
export interface RateRequest {
  rating: number
  comment?: string
}

// 评分记录
export interface Rating {
  id: string
  skillId: string
  userId: string
  userName: string
  rating: number
  comment?: string
  createTime: number
}

// 列表查询参数
export interface SkillQueryParams {
  keyword?: string
  category?: string
  sortBy?: 'rating' | 'downloads' | 'newest'
  page?: number
  pageSize?: number
}

// 列表响应
export interface SkillListResponse {
  list: Skill[]
  total: number
  page: number
  pageSize: number
}

// 技能市场 API
export const skillsMarketApi = {
  // 获取技能列表
  getSkills: (params: SkillQueryParams): Promise<SkillListResponse> =>
    api.get('/skills/market', { params }),

  // 获取技能详情
  getSkillDetail: (id: string): Promise<Skill> =>
    api.get(`/skills/market/${id}`),

  // 获取分类列表
  getCategories: (): Promise<Category[]> =>
    api.get('/skills/market/categories'),

  // 下载技能
  downloadSkill: (id: string): Promise<{ success: boolean; message: string }> =>
    api.post(`/skills/market/download/${id}`),

  // 评分技能
  rateSkill: (id: string, data: RateRequest): Promise<{ success: boolean; message: string }> =>
    api.post(`/skills/market/rate/${id}`, data),

  // 获取技能评分列表
  getRatings: (skillId: string, params?: { page?: number; pageSize?: number }): Promise<{
    list: Rating[]
    total: number
  }> =>
    api.get(`/skills/market/${skillId}/ratings`, { params }),

  // 发布技能
  publishSkill: (data: {
    name: string
    description: string
    longDescription?: string
    category: string
    version: string
    tags?: string[]
    config: string
  }): Promise<{ success: boolean; id: string }> =>
    api.post('/skills/market/publish', data),

  // 获取我发布的技能
  getMySkills: (params?: { page?: number; pageSize?: number }): Promise<SkillListResponse> =>
    api.get('/skills/market/my', { params }),

  // 删除我发布的技能
  deleteMySkill: (id: string): Promise<{ success: boolean }> =>
    api.delete(`/skills/market/my/${id}`),
}

export default skillsMarketApi
