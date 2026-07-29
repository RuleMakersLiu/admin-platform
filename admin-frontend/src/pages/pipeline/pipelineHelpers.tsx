/**
 * Module-level constants, helpers, presentational sub-components, types and the
 * inline-style registry for the pipeline workbench. Extracted verbatim from
 * index.tsx (F9 split) — pure relocation, no behavior change.
 */
import React from 'react'
import { Spin, Tag, Space, Typography, Alert, Button, Progress } from 'antd'
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  EyeOutlined,
  FileTextOutlined,
  Html5Outlined,
  CodeOutlined,
  BugOutlined,
  BranchesOutlined,
  RocketOutlined,
  SendOutlined,
  HistoryOutlined,
  DeleteOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import type { PipelineStatus } from '@/services/pipeline'

const { Text } = Typography

export const AGENT_COLORS: Record<string, string> = {
  PM: '#3b82f6', PJM: '#8b5cf6', BE: '#22c55e', FE: '#f97316', QA: '#ef4444', RPT: '#14b8a6',
}

export const STAGE_ICONS: Record<string, React.ReactNode> = {
  requirement: <FileTextOutlined />,
  page_design: <FileTextOutlined />,
  prototype: <EyeOutlined />,
  delivery: <SendOutlined />,
  ui_preview: <EyeOutlined />,
  backend_dev: <CodeOutlined />,
  frontend_dev: <Html5Outlined />,
  development: <CodeOutlined />,
  code_review: <CheckCircleOutlined />,
  testing: <BugOutlined />,
  commit: <BranchesOutlined />,
  deploy: <RocketOutlined />,
  eval: <SafetyCertificateOutlined />,
  report: <FileTextOutlined />,
}

export const STAGE_NAMES: Record<string, string> = {
  requirement: '需求分析',
  page_design: '页面设计',
  prototype: '前端预览代码',
  delivery: '交付包',
  ui_preview: 'UI预览',
  backend_dev: '后端开发',
  frontend_dev: '前端开发',
  development: '代码生成',
  code_review: '代码审查',
  testing: '自动化测试',
  commit: '代码提交',
  deploy: '部署发布',
  eval: '自动测评',
  report: '总结报告',
}

export const STAGE_KEYS = ['requirement', 'page_design', 'prototype', 'delivery', 'frontend_dev', 'backend_dev', 'code_review', 'testing', 'commit', 'deploy', 'eval', 'report']
export const PRODUCT_STAGE_KEYS = ['requirement', 'page_design', 'prototype', 'delivery', 'code_review', 'report']
export const LIVE_STREAM_OUTPUT_LIMIT = 60000
export const STAGE_RENDER_OUTPUT_LIMIT = 120000

export const clipOutput = (value: string, limit: number, label: string) => {
  if (value.length <= limit) return value
  return [
    `【${label}过长，已仅保留最近 ${Math.round(limit / 1000)}K 字符，完整内容会在阶段完成后保存到阶段结果。】`,
    '',
    value.slice(-limit),
  ].join('\n')
}

export const appendLiveOutput = (current: string, chunk: string) =>
  clipOutput(`${current || ''}${chunk || ''}`, LIVE_STREAM_OUTPUT_LIMIT, '实时输出')

export const renderSafeOutput = (value: string) =>
  clipOutput(value || '', STAGE_RENDER_OUTPUT_LIMIT, '阶段输出')

export const confirmActionLabel = (stage = '') => {
  const labels: Record<string, string> = {
    requirement: '确认需求，进入页面设计',
    page_design: '确认页面设计，生成前端预览代码',
    prototype: '确认前端预览，生成 API 契约',
    delivery: '确认交付内容，进入下一阶段',
    frontend_dev: '确认前端代码，进入下一阶段',
    backend_dev: '确认后端代码，进入下一阶段',
    code_review: '确认审查结果，生成报告',
    testing: '确认测试结果，进入下一阶段',
    commit: '确认提交结果，进入下一阶段',
    deploy: '确认部署结果，生成报告',
    report: '确认报告，完成流水线',
  }
  return labels[stage] || '确认当前阶段并继续'
}

export const confirmDescription = (stage = '') => {
  if (stage === 'report') return '确认后流水线将完成；退回时可在下方填写报告修订意见。'
  return '确认后将自动推进到下一阶段；退回时可在下方填写修订意见。'
}

export const STATUS_COLORS: Record<string, { bg: string; color: string; text: string }> = {
  running:           { bg: 'rgba(49,92,246,0.12)', color: '#315cf6', text: '执行中' },
  completed:         { bg: 'rgba(34,197,94,0.12)', color: '#86efac', text: '已完成' },
  failed:            { bg: 'rgba(239,68,68,0.12)',  color: '#fca5a5', text: '失败' },
  waiting_confirm:   { bg: 'rgba(245,158,11,0.13)', color: '#fcd34d', text: '待确认' },
  pending:           { bg: '#f4f7fb', color: '#667085', text: '待执行' },
}

export const PipelineHistoryList: React.FC<{
  pipelines: any[]
  loading: boolean
  onSelect: (id: string) => void
  onDelete: (id: string) => void
}> = ({ pipelines, loading, onSelect, onDelete }) => {
  if (loading) return <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>
  if (!pipelines.length) return (
    <div style={{ textAlign: 'center', padding: '32px 0' }}>
      <HistoryOutlined style={{ fontSize: 32, color: '#333', marginBottom: 8 }} />
      <div style={{ color: '#64748b', fontSize: 13 }}>暂无历史流水线</div>
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 340, overflow: 'auto' }}>
      {pipelines.map((p) => {
        const s = STATUS_COLORS[p.status] || STATUS_COLORS.pending
        const stageName = STAGE_NAMES[p.current_stage] || p.current_stage
        return (
          <div key={p.pipeline_id} className="pipeline-history-item workbench-card" style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '12px 16px', borderRadius: 10, cursor: 'pointer',
            background: '#ffffff',
            border: '1px solid #e5eaf3',
            transition: 'all 0.2s',
          }}
            onClick={() => onSelect(p.pipeline_id)}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <Text style={{ color: '#111827', fontSize: 13, fontWeight: 500 }} ellipsis>
                  {p.user_request?.slice(0, 50) || p.pipeline_id}
                </Text>
                <span style={{
                  background: s.bg, color: s.color, padding: '1px 8px',
                  borderRadius: 4, fontSize: 11, fontWeight: 500, whiteSpace: 'nowrap',
                }}>
                  {s.text}
                </span>
              </div>
              <div style={{ fontSize: 11, color: '#64748b', display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{ fontFamily: 'monospace', color: '#444' }}>{p.pipeline_id?.slice(0, 12)}...</span>
                <span style={{ color: '#333' }}>·</span>
                <span>{stageName}</span>
                <span style={{ color: '#333' }}>·</span>
                <span>{p.create_time ? new Date(p.create_time).toLocaleString() : ''}</span>
              </div>
            </div>
            <Button size="small" danger type="text" icon={<DeleteOutlined />}
              onClick={(e) => { e.stopPropagation(); onDelete(p.pipeline_id) }} />
          </div>
        )
      })}
    </div>
  )
}

export const STAGE_AGENT_MAP: Record<string, string> = {
  requirement: 'PM',
  page_design: 'PM',
  prototype: 'FE',
  delivery: 'PJM',
  ui_preview: 'FE',
  backend_dev: 'BE',
  frontend_dev: 'FE',
  development: 'BE',
  code_review: 'QA',
  testing: 'QA',
  commit: 'PJM',
  deploy: 'PJM',
  report: 'RPT',
}

export const createPipelineShell = (
  pipelineId: string,
  userRequest: string,
  currentStage = 'requirement',
): PipelineStatus => {
  const now = new Date().toISOString()
  const stages = STAGE_KEYS.reduce<PipelineStatus['stages']>((acc, key) => {
    acc[key] = {
      stage: key,
      agent_type: STAGE_AGENT_MAP[key] || 'PM',
      status: key === currentStage ? 'running' : 'pending',
      output: '',
      structured_output: {},
      preview_html: '',
      code_files: {},
      error: '',
      started_at: key === currentStage ? now : null,
      completed_at: null,
    }
    return acc
  }, {})

  return {
    pipeline_id: pipelineId,
    project_id: '',
    user_request: userRequest,
    status: 'running',
    current_stage: currentStage,
    stages,
    created_at: now,
    updated_at: now,
  }
}

export interface PMQualitySummary {
  score?: number
  ready_for_review?: boolean
  missing_items?: string[]
  review_focus?: string[]
  primary_pages?: string[]
  permission_points?: string[]
  permission_model?: string[]
  data_scope_rules?: string[]
  policy_examples?: string[]
  data_entities?: string[]
  acceptance_criteria?: string[]
}

export interface PreviewQualitySummary {
  score?: number
  ready_for_preview?: boolean
  issues?: string[]
  passed_checks?: string[]
}

export const toList = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean)
  if (typeof value === 'string' && value.trim()) return [value.trim()]
  return []
}

export const PMQualityPanel: React.FC<{
  stageKey: string
  quality?: PMQualitySummary
}> = ({ stageKey, quality }) => {
  if (!quality) return null

  const score = Math.max(0, Math.min(100, Number(quality.score || 0)))
  const ready = Boolean(quality.ready_for_review)
  const missingItems = toList(quality.missing_items)
  const reviewFocus = toList(quality.review_focus)
  const permissionPoints = toList(quality.permission_points)
  const permissionModel = toList(quality.permission_model)
  const dataScopeRules = toList(quality.data_scope_rules)
  const policyExamples = toList(quality.policy_examples)
  const dataEntities = toList(quality.data_entities)
  const acceptanceCriteria = toList(quality.acceptance_criteria)
  const primaryPages = toList(quality.primary_pages)
  const title = stageKey === 'requirement' ? 'PM 需求质量门' : 'PM 页面设计质量门'

  const block = (label: string, items: string[], color: string) => {
    if (!items.length) return null
    return (
      <div style={{ minWidth: 180, flex: '1 1 220px' }}>
        <Text style={{ display: 'block', color: '#8aa4b8', fontSize: 12, marginBottom: 8 }}>
          {label}
        </Text>
        <Space size={[6, 6]} wrap>
          {items.slice(0, 8).map((item) => (
            <Tag key={item} color={color} style={{ margin: 0, borderRadius: 6 }}>
              {item}
            </Tag>
          ))}
        </Space>
      </div>
    )
  }

  return (
    <div style={{
      marginBottom: 16,
      padding: 18,
      borderRadius: 8,
      border: ready ? '1px solid rgba(34, 197, 94, 0.28)' : '1px solid rgba(245, 158, 11, 0.3)',
      background: ready ? 'rgba(20, 83, 45, 0.18)' : 'rgba(120, 53, 15, 0.18)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <CheckCircleOutlined style={{ color: ready ? '#86efac' : '#fcd34d' }} />
        <Text strong style={{ color: '#111827', fontSize: 14 }}>{title}</Text>
        <Tag color={ready ? 'success' : 'warning'} style={{ marginLeft: 'auto', borderRadius: 6 }}>
          {ready ? '可评审' : '需补充'}
        </Tag>
      </div>
      <Progress
        percent={score}
        size="small"
        status={ready ? 'success' : 'active'}
        strokeColor={ready ? '#22c55e' : '#f59e0b'}
        trailColor="rgba(148,163,184,0.14)"
      />
      {missingItems.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message="建议退回补齐后再进入下一阶段"
          description={missingItems.join('、')}
          style={{
            marginTop: 12,
            borderRadius: 8,
            background: '#fffbeb',
            border: '1px solid rgba(245, 158, 11, 0.2)',
          }}
        />
      )}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 14 }}>
        {block('评审重点', reviewFocus, 'blue')}
        {block('核心页面', primaryPages, 'cyan')}
        {block('权限点', permissionPoints, 'purple')}
        {block('权限模型', permissionModel, 'volcano')}
        {block('数据范围', dataScopeRules, 'orange')}
        {block('策略样例', policyExamples, 'magenta')}
        {block('数据对象', dataEntities, 'geekblue')}
        {block('验收标准', acceptanceCriteria, 'green')}
      </div>
    </div>
  )
}

export const PreviewQualityPanel: React.FC<{
  quality?: PreviewQualitySummary
}> = ({ quality }) => {
  if (!quality) return null

  const score = Math.max(0, Math.min(100, Number(quality.score || 0)))
  const ready = Boolean(quality.ready_for_preview)
  const issues = toList(quality.issues)
  const passedChecks = toList(quality.passed_checks)

  return (
    <div style={{
      marginBottom: 16,
      padding: 18,
      borderRadius: 8,
      border: ready ? '1px solid rgba(34, 197, 94, 0.28)' : '1px solid rgba(245, 158, 11, 0.3)',
      background: ready ? 'rgba(20, 83, 45, 0.16)' : 'rgba(120, 53, 15, 0.18)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        {ready ? (
          <CheckCircleOutlined style={{ color: '#86efac' }} />
        ) : (
          <ExclamationCircleOutlined style={{ color: '#fcd34d' }} />
        )}
        <Text strong style={{ color: '#111827', fontSize: 14 }}>预览质量检查</Text>
        <Tag color={ready ? 'success' : 'warning'} style={{ marginLeft: 'auto', borderRadius: 6 }}>
          {ready ? '可预览' : '需优化'}
        </Tag>
      </div>
      <Progress
        percent={score}
        size="small"
        status={ready ? 'success' : 'active'}
        strokeColor={ready ? '#22c55e' : '#f59e0b'}
        trailColor="rgba(148,163,184,0.14)"
      />
      {issues.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message="预览还不够稳定"
          description={issues.join('、')}
          style={{
            marginTop: 12,
            borderRadius: 8,
            background: 'rgba(120, 53, 15, 0.2)',
            border: '1px solid rgba(245, 158, 11, 0.2)',
          }}
        />
      )}
      {passedChecks.length > 0 && (
        <Space size={[6, 6]} wrap style={{ marginTop: 14 }}>
          {passedChecks.slice(0, 8).map((item) => (
            <Tag key={item} color="blue" style={{ margin: 0, borderRadius: 6 }}>
              {item}
            </Tag>
          ))}
        </Space>
      )}
    </div>
  )
}

/* ============ Inline Styles ============ */

export type StyleFn<T extends any[]> = (...args: T) => React.CSSProperties

export interface Styles {
  createRoot: React.CSSProperties
  createCard: React.CSSProperties
  createHeader: React.CSSProperties
  createIcon: React.CSSProperties
  createBody: React.CSSProperties
  mainRoot: React.CSSProperties
  headerBar: React.CSSProperties
  headerLeft: React.CSSProperties
  pipelineIdText: React.CSSProperties
  stageTrackerRow: React.CSSProperties
  stageTrackSidebar: React.CSSProperties
  stageItem: StyleFn<[boolean, string]>
  stageItemIcon: StyleFn<[string]>
  stageItemName: StyleFn<[boolean, string]>
  contentArea: React.CSSProperties
  stageDetailCard: React.CSSProperties
  stageDetailHeader: React.CSSProperties
  stageDetailBody: React.CSSProperties
  outputContainer: React.CSSProperties
  outputHeader: React.CSSProperties
  outputLabel: React.CSSProperties
  confirmPanel: React.CSSProperties
  confirmPanelActions: React.CSSProperties
  failPanel: React.CSSProperties
  historyCard: React.CSSProperties
  timelineRow: StyleFn<[boolean]>
  timelineDot: StyleFn<[string]>
  timelineLine: React.CSSProperties
  timelineContent: React.CSSProperties
  codeFileItem: React.CSSProperties
  completedBanner: React.CSSProperties
  statusBadge: StyleFn<[string]>
  promptCollapseWrap: React.CSSProperties
  promptCollapseBar: React.CSSProperties
  promptCollapseTitle: React.CSSProperties
  promptStageHeader: React.CSSProperties
  promptResetBtn: React.CSSProperties
  promptDrawerStage: React.CSSProperties
  promptDrawerStageHeader: React.CSSProperties
  promptDrawerBody: React.CSSProperties
}

export const styles: Styles = {
  /* -- Create page -- */
  createRoot: {
    padding: 24,
    minHeight: 'calc(100vh - 120px)',
    display: 'flex',
    gap: 20,
    alignItems: 'flex-start',
    flexWrap: 'wrap' as const,
    background: 'linear-gradient(180deg, #fbfdff 0%, #f6f8fc 100%)',
  },
  createCard: {
    maxWidth: 560,
    width: '100%',
    border: '1px solid #e5eaf3',
    borderRadius: 12,
    background: '#ffffff',
    boxShadow: '0 18px 45px rgba(15, 23, 42, 0.08)',
    overflow: 'hidden',
  },
  createHeader: {
    padding: '32px 32px 0 32px',
    textAlign: 'center' as const,
  },
  createIcon: {
    fontSize: 42,
    color: '#315cf6',
    marginBottom: 16,
  },
  createBody: {
    padding: '24px 32px 32px',
  },

  /* -- Main page layout -- */
  mainRoot: {
    padding: 24,
    minHeight: 'calc(100vh - 120px)',
    background: 'linear-gradient(180deg, #fbfdff 0%, #f6f8fc 100%)',
  },

  /* -- Header bar -- */
  headerBar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '14px 18px',
    marginBottom: 16,
    background: '#ffffff',
    border: '1px solid #e5eaf3',
    borderRadius: 10,
    boxShadow: '0 12px 32px rgba(15, 23, 42, 0.06)',
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    flexWrap: 'wrap' as const,
  },
  pipelineIdText: {
    fontFamily: "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace",
    fontSize: 13,
    color: '#315cf6',
  },

  /* -- Vertical stage tracker -- */
  stageTrackerRow: {
    display: 'flex',
    alignItems: 'stretch',
    gap: 16,
    marginBottom: 16,
  },
  stageTrackSidebar: {
    width: 232,
    flexShrink: 0,
    background: '#ffffff',
    border: '1px solid #e5eaf3',
    borderRadius: 10,
    padding: '12px 0',
    overflowY: 'auto' as const,
  },
  stageItem: (isActive: boolean, status: string) => ({
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '10px 16px',
    cursor: status === 'completed' || isActive ? 'pointer' : 'default',
    position: 'relative' as const,
    background: isActive
      ? 'linear-gradient(90deg, rgba(49, 92, 246, 0.12), rgba(49, 92, 246, 0.03))'
      : 'transparent',
    borderLeft: isActive ? '3px solid #315cf6' : '3px solid transparent',
    transition: 'all 0.25s ease',
  }),
  stageItemIcon: (status: string) => ({
    width: 28,
    height: 28,
    borderRadius: 8,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 13,
    flexShrink: 0,
    background:
      status === 'completed' ? 'rgba(82, 196, 26, 0.15)' :
      status === 'running' ? 'rgba(49, 92, 246, 0.12)' :
      status === 'failed' ? 'rgba(239, 68, 68, 0.14)' :
      '#f4f7fb',
    color:
      status === 'completed' ? '#16a34a' :
      status === 'running' ? '#315cf6' :
      status === 'failed' ? '#dc2626' :
      '#667085',
    border: `1px solid ${
      status === 'completed' ? 'rgba(34, 197, 94, 0.32)' :
      status === 'running' ? 'rgba(59, 130, 246, 0.32)' :
      status === 'failed' ? 'rgba(239, 68, 68, 0.32)' :
      'rgba(148, 163, 184, 0.14)'
    }`,
  }),
  stageItemName: (isActive: boolean, status: string) => ({
    fontSize: 13,
    color: isActive ? '#111827' : status === 'completed' ? '#334155' : '#667085',
    fontWeight: isActive ? 600 : 400,
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  }),

  /* -- Content area -- */
  contentArea: {
    flex: 1,
    minWidth: 0,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 16,
  },

  /* -- Stage detail card -- */
  stageDetailCard: {
    background: '#ffffff',
    border: '1px solid #e5eaf3',
    borderRadius: 10,
    overflow: 'hidden',
    boxShadow: '0 18px 45px rgba(15, 23, 42, 0.06)',
  },
  stageDetailHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: '16px 20px',
    borderBottom: '1px solid #edf1f7',
    background: '#fbfdff',
  },
  stageDetailBody: {
    padding: 20,
  },

  /* -- Output container -- */
  outputContainer: {
    maxHeight: 620,
    overflow: 'auto',
    padding: '16px 20px 20px',
    marginBottom: 16,
    borderRadius: 8,
    border: '1px solid #e5eaf3',
    background: '#f8fafd',
    color: '#243044',
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
  },
  outputHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    marginBottom: 12,
  },
  outputLabel: {
    fontSize: 11,
    color: '#667085',
    textTransform: 'uppercase' as const,
    letterSpacing: 0,
  },

  /* -- Confirm panel -- */
  confirmPanel: {
    marginTop: 16,
    padding: 20,
    background: '#fffbeb',
    border: '1px solid rgba(245, 158, 11, 0.26)',
    borderRadius: 10,
    boxShadow: 'none',
    transition: 'all 0.3s ease',
  },
  confirmPanelActions: {
    display: 'flex',
    gap: 12,
    marginTop: 12,
  },

  /* -- Fail panel -- */
  failPanel: {
    marginTop: 16,
    padding: 20,
    background: '#fef2f2',
    border: '1px solid rgba(239, 68, 68, 0.24)',
    borderRadius: 10,
  },

  /* -- Timeline / history card -- */
  historyCard: {
    background: '#ffffff',
    border: '1px solid #e5eaf3',
    borderRadius: 10,
  },
  timelineRow: (_isLast: boolean) => ({
    display: 'flex',
    gap: 14,
    padding: '10px 0',
    position: 'relative' as const,
  }),
  timelineDot: (status: string) => ({
    width: 10,
    height: 10,
    borderRadius: '50%',
    flexShrink: 0,
    marginTop: 4,
    background:
      status === 'completed' ? '#22c55e' :
      status === 'running' ? '#315cf6' :
      status === 'failed' ? '#dc2626' : '#c4ccd8',
    boxShadow:
      status === 'completed' ? '0 0 0 3px rgba(34, 197, 94, 0.12)' :
      status === 'running' ? '0 0 0 3px rgba(59, 130, 246, 0.14)' :
      'none',
  }),
  timelineLine: {
    position: 'absolute' as const,
    left: 4.5,
    top: 24,
    bottom: -10,
    width: 1,
    background: '#e5eaf3',
  },
  timelineContent: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    flexWrap: 'wrap' as const,
  },

  /* -- Code file list -- */
  codeFileItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 12px',
    borderRadius: 8,
    background: '#f8fafd',
    border: '1px solid #e5eaf3',
    marginBottom: 6,
    transition: 'all 0.2s ease',
  },

  /* -- Completed banner -- */
  completedBanner: {
    padding: '16px 20px',
    background: '#f0fdf4',
    border: '1px solid rgba(34, 197, 94, 0.25)',
    borderRadius: 10,
    display: 'flex',
    alignItems: 'center',
    gap: 12,
  },

  /* -- Utility -- */
  statusBadge: (status: string) => ({
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '2px 10px',
    borderRadius: 12,
    fontSize: 12,
    fontWeight: 500,
    background:
      status === 'running' ? 'rgba(59, 130, 246, 0.14)' :
      status === 'completed' ? 'rgba(34, 197, 94, 0.12)' :
      status === 'failed' ? 'rgba(239, 68, 68, 0.12)' :
      status === 'needs_human' ? 'rgba(234, 88, 12, 0.14)' :
      status === 'waiting_confirm' ? 'rgba(245, 158, 11, 0.13)' :
      'rgba(148, 163, 184, 0.08)',
    color:
      status === 'running' ? '#315cf6' :
      status === 'completed' ? '#16a34a' :
      status === 'failed' ? '#dc2626' :
      status === 'needs_human' ? '#ea580c' :
      status === 'waiting_confirm' ? '#b45309' :
      '#667085',
    border: `1px solid ${
      status === 'running' ? 'rgba(59, 130, 246, 0.28)' :
      status === 'completed' ? 'rgba(34, 197, 94, 0.26)' :
      status === 'failed' ? 'rgba(239, 68, 68, 0.26)' :
      status === 'needs_human' ? 'rgba(234, 88, 12, 0.30)' :
      status === 'waiting_confirm' ? 'rgba(245, 158, 11, 0.28)' :
      'rgba(148, 163, 184, 0.12)'
    }`,
  }),

  /* -- Prompt editor (create panel) -- */
  promptCollapseWrap: {
    marginBottom: 16,
  },
  promptCollapseBar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    width: '100%',
    paddingRight: 8,
  },
  promptCollapseTitle: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    color: '#315cf6',
    fontSize: 14,
    fontWeight: 600,
  },
  promptStageHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    marginBottom: 10,
  },
  promptResetBtn: {
    marginLeft: 'auto',
    fontSize: 11,
    color: '#667085',
    borderRadius: 6,
    borderColor: '#dbe3ef',
  },
  promptDrawerStage: {
    marginBottom: 24,
  },
  promptDrawerStageHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    marginBottom: 10,
    paddingBottom: 8,
    borderBottom: '1px solid #e5eaf3',
  },
  promptDrawerBody: {
    padding: '8px 12px',
    borderRadius: 8,
    background: '#f8fafd',
    border: '1px solid #e5eaf3',
    color: '#243044',
    fontSize: 13,
    lineHeight: 1.7,
    whiteSpace: 'pre-wrap' as const,
    maxHeight: 300,
    overflow: 'auto',
  },
}
