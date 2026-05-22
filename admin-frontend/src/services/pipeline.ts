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
  status: 'pending' | 'running' | 'completed' | 'failed'
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
  stages: Record<string, StageResult>
  created_at: string
  updated_at: string
}

export interface PipelineListItem {
  pipeline_id: string
  project_id: string
  status: string
  current_stage: string
  created_at: string
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
    frontend_project_id?: string
    backend_tech?: string
    frontend_tech?: string
    skill_config?: Record<string, unknown>
  }) =>
    api.post(`${BASE}/create`, data) as any as Promise<{ pipeline_id: string; status: string }>,

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

  getOutput: (id: string, stage?: string) =>
    api.get(`${BASE}/${id}/output`, { params: { stage: stage || '' } }) as any,

  list: () =>
    api.get(`${BASE}/list`) as any,

  rollback: (id: string) =>
    api.post(`${BASE}/${id}/rollback`) as any,

  getTemplates: () =>
    api.get('/flow/templates') as any,

  // Prompt 管理
  getDefaultPrompts: () =>
    api.get('/flow/prompts/defaults') as any as Promise<Record<string, string>>,

  getProjectPrompts: (projectCode: string) =>
    api.get(`/flow/projects/${projectCode}/prompts`) as any as Promise<Record<string, string>>,

  updateProjectPrompts: (projectCode: string, prompts: Record<string, string>) =>
    api.put(`/flow/projects/${projectCode}/prompts`, { prompts }) as any,
}
