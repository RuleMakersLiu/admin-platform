import api from './api'

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

const BASE = '/flow/pipeline'

export const pipelineApi = {
  create: (data: { project_id?: string; user_request: string }) =>
    api.post(`${BASE}/create`, data) as any as Promise<{ pipeline_id: string; status: string }>,

  execute: (id: string, user_input?: string) =>
    api.post(`${BASE}/${id}/execute`, { user_input: user_input || '' }) as any,

  confirm: (id: string, confirmed: boolean, feedback?: string) =>
    api.post(`${BASE}/${id}/confirm`, { confirmed, feedback: feedback || '' }) as any,

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
