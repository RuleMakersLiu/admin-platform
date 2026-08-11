import api from './api'

export type EvalAgent = {
  id: string
  name: string
  description?: string
  adapter_type: 'HTTP' | 'SSE' | 'OPENAI_COMPATIBLE' | 'CONTAINER' | 'CLI'
  isolation_scope: 'FULL' | 'RUNNER_ONLY'
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH'
  status: string
  created_at: string
}

export type EvalDataset = {
  id: string
  name: string
  description?: string
  latest_version: number
  published_cases: number
  created_at: string
}

export type EvalExperiment = {
  id: string
  name: string
  experiment_type: 'PAIRED_OFFLINE' | 'SHADOW_REPLAY'
  status: string
  repetitions: number
  variant_count: number
  trial_count: number
  created_at: string
}

export type EvalSecurityStatus = {
  execution_enabled: boolean
  gate_reference?: string
  scope: string
  production_write_tools: boolean
  remote_agent_isolation: 'RUNNER_ONLY'
}

export const evaluationApi = {
  securityStatus: () => api.get<unknown, EvalSecurityStatus>('/eval/security/approve'),
  listAgents: () => api.get<unknown, EvalAgent[]>('/eval/agent/list'),
  createAgent: (data: Pick<EvalAgent, 'name' | 'adapter_type' | 'risk_level'> & { description?: string }) =>
    api.post<unknown, EvalAgent>('/eval/agent/create', data),
  listDatasets: () => api.get<unknown, EvalDataset[]>('/eval/dataset/list'),
  createDataset: (data: { name: string; description?: string }) =>
    api.post<unknown, EvalDataset>('/eval/dataset/create', data),
  listExperiments: () => api.get<unknown, EvalExperiment[]>('/eval/experiment/view'),
  cancelExperiment: (id: string) => api.post(`/eval/experiment/${id}/cancel`),
}
