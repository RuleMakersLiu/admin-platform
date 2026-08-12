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
  latest_version_id: string
  latest_status: 'DRAFT' | 'REVIEWING' | 'PUBLISHED' | 'ARCHIVED'
  latest_case_count: number
  review_round: number
  published_cases: number
  created_at: string
}

export type EvalDatasetVersion = {
  id: string
  dataset_id: string
  dataset_name: string
  version: number
  status: 'DRAFT' | 'REVIEWING' | 'PUBLISHED' | 'ARCHIVED'
  case_count: number
  content_hash?: string
  review_round: number
  approvals: number
  rejections: number
  published_at?: string
}

export type EvalDatasetCase = {
  id: string
  external_id: string
  category: string
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH'
  split: 'DEVELOPMENT' | 'REGRESSION' | 'HIDDEN'
  source_type: 'DEIDENTIFIED' | 'EXPERT' | 'AI_VARIANT' | 'SYNTHETIC'
  input_payload?: Record<string, unknown> | null
  initial_state_ref?: string
  expected_state?: Record<string, unknown> | null
  rubric?: Record<string, unknown> | null
  tool_policy?: Array<Record<string, unknown>> | null
  budget?: Record<string, unknown> | null
  deterministic_checks?: Array<Record<string, unknown>> | null
  oracle_type: 'STATE' | 'EXACT' | 'REFERENCE' | 'TOOL_TRACE' | 'HYBRID'
  prohibited_behaviors: string[]
  source_group_id?: string
  source_parent_hash?: string
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
  createDatasetVersion: (datasetId: string, cloneLatest = true) =>
    api.post<unknown, EvalDatasetVersion>(`/eval/dataset/${datasetId}/version/create`, { clone_latest: cloneLatest }),
  getDatasetVersion: (versionId: string) =>
    api.get<unknown, EvalDatasetVersion>(`/eval/dataset/version/${versionId}`),
  listDatasetCases: (versionId: string) =>
    api.get<unknown, EvalDatasetCase[]>(`/eval/dataset/version/${versionId}/cases`),
  listDatasetCasesForReview: (versionId: string) =>
    api.get<unknown, EvalDatasetCase[]>(`/eval/dataset/version/${versionId}/review-cases`),
  getDatasetCaseForEdit: (versionId: string, caseId: string) =>
    api.get<unknown, EvalDatasetCase>(`/eval/dataset/version/${versionId}/cases/${caseId}/edit`),
  importDatasetCases: (datasetId: string, cases: Array<Record<string, unknown>>, dryRun = false) =>
    api.post<unknown, { valid: boolean; imported: number; errors: unknown[] }>(
      `/eval/dataset/${datasetId}/cases/import`, { cases, dry_run: dryRun },
    ),
  updateDatasetCase: (versionId: string, caseId: string, data: Record<string, unknown>) =>
    api.put(`/eval/dataset/version/${versionId}/cases/${caseId}`, data),
  deleteDatasetCase: (versionId: string, caseId: string) =>
    api.delete(`/eval/dataset/version/${versionId}/cases/${caseId}`),
  importLegacyGolden: (datasetId: string) =>
    api.post<unknown, { imported: number; skipped: Array<{ golden_case_id: number; reason: string }> }>(
      `/eval/dataset/${datasetId}/import-golden`, { split: 'DEVELOPMENT' },
    ),
  submitDatasetReview: (versionId: string) =>
    api.post(`/eval/dataset/version/${versionId}/submit-review`),
  reviewDataset: (versionId: string, decision: 'APPROVE' | 'REJECT', comment?: string) =>
    api.post(`/eval/dataset/version/${versionId}/review`, { decision, comment }),
  publishDataset: (versionId: string, expectedReviewRound: number) =>
    api.post(`/eval/dataset/version/${versionId}/publish`, { expected_review_round: expectedReviewRound }),
  listExperiments: () => api.get<unknown, EvalExperiment[]>('/eval/experiment/view'),
  cancelExperiment: (id: string) => api.post(`/eval/experiment/${id}/cancel`),
}
