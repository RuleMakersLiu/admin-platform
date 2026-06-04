import api from './api'
import { useAuthStore } from '@/stores/auth'

export interface StageDef {
  key: string
  name: string
  agent: string
  icon: string
}

export interface StageResult {
  stage: string
  agent_type: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'waiting_confirm'
  output: string
  structured_output: Record<string, any>
  preview_html: string
  code_files: Record<string, string>
  error: string
  started_at: string | null
  completed_at: string | null
}

export interface PipelineStatus {
  pipeline_id: string
  project_id: string
  user_request: string
  status: string
  current_stage: string
  pipeline_mode?: string
  project_skill?: {
    project_id: string
    project_name: string
    skill_version?: number
    confirmed_at?: number | null
  } | null
  backend_project_skill?: {
    project_id: string
    project_name: string
    skill_version?: number
    confirmed_at?: number | null
  } | null
  backend_project_skills?: Array<{
    project_id: string
    project_name: string
    skill_version?: number
    confirmed_at?: number | null
  }>
  stages: Record<string, StageResult>
  created_at: string
  updated_at: string
}

export interface ProjectSkill {
  project_id: number
  project_name: string
  repo_url: string
  language: string
  framework: string
  project_brief: string
  skill_content: string
  skill_status: 'analyzing' | 'draft' | 'confirmed' | 'failed' | string
  skill_version: number
  confirmed_by?: number | null
  confirmed_at?: number | null
  analysis_status: string
  analysis_error?: string
  tenant_scope_ids?: number[]
}

export interface ProjectSkillMatch {
  skill: ProjectSkill
  backend_match?: ProjectSkillMatch
  backend_matches?: ProjectSkillMatch[]
  frontend_page_candidates?: {
    requires_selection?: boolean
    uncertain?: boolean
    candidates?: Array<{
      path: string
      confidence: number
      display_name?: string
      menu_hint?: string
      route_hint?: string
      developer_hint?: string
      matched_terms?: string[]
      reason?: string
      uncertain?: boolean
    }>
    error?: string
  }
  confidence: number
  match_reason: string
  match_source: 'llm' | 'rule' | string
  match_tags?: string[]
  candidates_considered: number
}

export interface FrontendPageCandidate {
  path: string
  confidence: number
  display_name?: string
  menu_hint?: string
  route_hint?: string
  developer_hint?: string
  matched_terms?: string[]
  reason?: string
  uncertain?: boolean
}

export interface FrontendPageCandidates {
  requires_selection?: boolean
  uncertain?: boolean
  candidates?: FrontendPageCandidate[]
  error?: string
}

export interface PipelineArtifact {
  pipeline_id: string
  status: string
  pipeline_mode: string
  preview_html: string
  preview_url?: string
  api_contract: string
  frontend_files: Record<string, string>
  review: Record<string, any>
  review_status?: string
  review_output?: string
  report: string
}

export interface PipelineListItem {
  pipeline_id: string
  project_id: string
  user_request: string
  status: string
  current_stage: string
  retry_count?: number
  create_time: number
  update_time: number
}

export interface PipelineStreamEvent {
  type: 'stage_started' | 'chunk' | 'stage_completed' | 'waiting_confirm' | 'stage_advanced' | 'completed' | 'failed' | 'done' | 'error' | 'heartbeat'
  pipeline_id?: string
  stage?: string
  status?: string
  content?: string
  output?: string
  preview_html?: string
  need_confirm?: boolean
  error?: string
  result?: Record<string, any>
}

const BASE = '/flow/pipeline'

const parseSseFrame = (frame: string): PipelineStreamEvent | null => {
  const dataLines = frame
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trim())

  if (!dataLines.length) return null
  try {
    return JSON.parse(dataLines.join('\n')) as PipelineStreamEvent
  } catch {
    return null
  }
}

export const pipelineApi = {
  create: (data: {
    user_request: string
    project_id?: string
    project_name?: string
    backend_project_id?: string
    backend_project_ids?: string[]
    frontend_project_id?: string
    backend_tech?: string
    frontend_tech?: string
    pipeline_mode?: string
    skill_config?: Record<string, unknown>
  }) =>
    api.post(`${BASE}/create`, data) as any as Promise<{ pipeline_id: string; status: string }>,

  matchProjectSkill: (data: { user_request: string }) =>
    api.post(`${BASE}/match`, data) as any as Promise<ProjectSkillMatch>,

  updateSkillConfig: (id: string, skill_config: Record<string, unknown>) =>
    api.put(`${BASE}/${id}/skill-config`, { skill_config }) as any as Promise<{ message?: string }>,

  execute: (id: string, user_input?: string) =>
    api.post(`${BASE}/${id}/execute`, { user_input: user_input || '' }, { timeout: 300000 }) as any,

  executeStream: async (
    id: string,
    user_input: string | undefined,
    onEvent: (event: PipelineStreamEvent) => void,
    signal?: AbortSignal,
  ) => {
    const { token, user } = useAuthStore.getState()
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (token) headers.Authorization = `Bearer ${token}`
    if (user) {
      headers['X-Admin-Id'] = String(user.adminId)
      headers['X-Tenant-Id'] = String(user.tenantId)
    }

    const response = await fetch(`/api${BASE}/${id}/execute-stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ user_input: user_input || '' }),
      signal,
    })

    if (!response.ok) {
      throw new Error(await response.text() || 'Pipeline stream failed')
    }
    if (!response.body) {
      throw new Error('Pipeline stream is not readable')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    let reading = true
    while (reading) {
      const { done, value } = await reader.read()
      if (done) {
        reading = false
        break
      }

      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split(/\r?\n\r?\n/)
      buffer = frames.pop() || ''

      for (const frame of frames) {
        const event = parseSseFrame(frame)
        if (event) onEvent(event)
      }
    }

    if (buffer.trim()) {
      const event = parseSseFrame(buffer)
      if (event) onEvent(event)
    }
  },

  confirm: (id: string, confirmed: boolean, feedback?: string) =>
    api.post(`${BASE}/${id}/confirm`, { confirmed, feedback: feedback || '' }, { timeout: 300000 }) as any,

  getStatus: (id: string) =>
    api.get(`${BASE}/${id}/status`) as any as Promise<PipelineStatus>,

  getPreview: (id: string) =>
    api.get(`${BASE}/${id}/preview`) as any as Promise<{ preview_html: string; output: string }>,

  startSandboxPreview: (id: string) =>
    api.post(`${BASE}/${id}/sandbox-preview/start`) as any as Promise<{
      pipeline_id: string
      status: string
      preview_url: string
      preview_token: string
    }>,

  getArtifact: (id: string) =>
    api.get(`${BASE}/${id}/artifact`) as any as Promise<PipelineArtifact>,

  downloadFrontend: async (id: string) => {
    const { token, user } = useAuthStore.getState()
    const headers: Record<string, string> = {}
    if (token) headers.Authorization = `Bearer ${token}`
    if (user) {
      headers['X-Admin-Id'] = String(user.adminId)
      headers['X-Tenant-Id'] = String(user.tenantId)
    }

    const response = await fetch(`/api${BASE}/${id}/frontend-download`, { headers })
    if (!response.ok) {
      throw new Error(await response.text() || '下载失败')
    }

    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${id}-frontend.zip`
    link.click()
    URL.revokeObjectURL(url)
  },

  getOutput: (id: string, stage?: string) =>
    api.get(`${BASE}/${id}/output`, { params: { stage: stage || '' } }) as any,

  updateStageOutput: (id: string, stage: string, output: string) =>
    api.put(`${BASE}/${id}/stages/${stage}/output`, { output }) as any,

  list: () =>
    api.get(`${BASE}/list`) as any,

  rollback: (id: string, stage?: string, feedback?: string) =>
    api.post(`${BASE}/${id}/rollback`, { stage, feedback: feedback || '' }) as any,

  delete: (id: string) =>
    api.delete(`${BASE}/${id}`) as any,

  getTemplates: () =>
    api.get('/flow/templates') as any,

  // Prompt 管理
  getDefaultPrompts: () =>
    api.get('/flow/prompts/defaults') as any as Promise<Record<string, string>>,

  getProjectPrompts: (projectCode: string) =>
    api.get(`/flow/projects/${projectCode}/prompts`) as any as Promise<Record<string, string>>,

  updateProjectPrompts: (projectCode: string, prompts: Record<string, string>) =>
    api.put(`/flow/projects/${projectCode}/prompts`, { prompts }) as any,

  analyzeProject: (projectId: string | number) =>
    api.post(`/flow/projects/${projectId}/analyze`) as any,

  getProjectSkill: (projectId: string | number) =>
    api.get(`/flow/projects/${projectId}/skill`) as any as Promise<ProjectSkill | null>,

  updateProjectSkill: (
    projectId: string | number,
    data: { project_brief?: string; skill_content?: string; tenant_scope_ids?: number[] },
  ) =>
    api.put(`/flow/projects/${projectId}/skill`, data) as any as Promise<ProjectSkill>,

  confirmProjectSkill: (projectId: string | number) =>
    api.post(`/flow/projects/${projectId}/skill/confirm`) as any as Promise<ProjectSkill>,
}
