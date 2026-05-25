import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import {
  Button, Spin, Input, Tag, Empty,
  message, Space, Typography, Alert, Drawer,
  Tooltip, Badge, Collapse, Select, Modal,
  Progress,
} from 'antd'
import {
  CheckCircleOutlined, CloseCircleOutlined,
  LoadingOutlined, RollbackOutlined, EyeOutlined, CodeOutlined,
  FileTextOutlined, RocketOutlined, BugOutlined, SendOutlined,
  Html5Outlined, DownloadOutlined,
  ThunderboltOutlined, BranchesOutlined, HistoryOutlined,
  ExclamationCircleOutlined, PlayCircleOutlined, ArrowLeftOutlined,
  UndoOutlined, SettingOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import { pipelineApi, type PipelineStatus, type PipelineStreamEvent } from '@/services/pipeline'
import { generatorApi } from '@/services/api'
import api from '@/services/api'
import { MarkdownRenderer } from '@/utils/markdown'
import { extractHtmlBlocks, prepareUIPreviewHtml, repairTruncatedHtml } from '@/utils/sanitize'
import { saveLastPortalPath, useAuthStore } from '@/stores/auth'

const { TextArea } = Input
const { Title, Text, Paragraph } = Typography

const AGENT_COLORS: Record<string, string> = {
  PM: '#3b82f6', PJM: '#8b5cf6', BE: '#22c55e', FE: '#f97316', QA: '#ef4444', RPT: '#14b8a6',
}

const STAGE_ICONS: Record<string, React.ReactNode> = {
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
  report: <FileTextOutlined />,
}

const STAGE_NAMES: Record<string, string> = {
  requirement: '需求分析',
  page_design: '页面设计',
  prototype: '原型预览',
  delivery: '交付包',
  ui_preview: 'UI预览',
  backend_dev: '后端开发',
  frontend_dev: '前端开发',
  development: '代码生成',
  code_review: '代码审查',
  testing: '自动化测试',
  commit: '代码提交',
  deploy: '部署发布',
  report: '总结报告',
}

const STAGE_KEYS = ['requirement', 'page_design', 'prototype', 'delivery', 'frontend_dev', 'backend_dev', 'code_review', 'testing', 'commit', 'deploy', 'report']

const STATUS_COLORS: Record<string, { bg: string; color: string; text: string }> = {
  running:           { bg: 'rgba(49,92,246,0.12)', color: '#315cf6', text: '执行中' },
  completed:         { bg: 'rgba(34,197,94,0.12)', color: '#86efac', text: '已完成' },
  failed:            { bg: 'rgba(239,68,68,0.12)',  color: '#fca5a5', text: '失败' },
  waiting_confirm:   { bg: 'rgba(245,158,11,0.13)', color: '#fcd34d', text: '待确认' },
  pending:           { bg: '#f4f7fb', color: '#667085', text: '待执行' },
}

const PipelineHistoryList: React.FC<{
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

const STAGE_AGENT_MAP: Record<string, string> = {
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

const createPipelineShell = (
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

interface PMQualitySummary {
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

interface PreviewQualitySummary {
  score?: number
  ready_for_preview?: boolean
  issues?: string[]
  passed_checks?: string[]
}

const toList = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean)
  if (typeof value === 'string' && value.trim()) return [value.trim()]
  return []
}

const PMQualityPanel: React.FC<{
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

const PreviewQualityPanel: React.FC<{
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

type StyleFn<T extends any[]> = (...args: T) => React.CSSProperties

interface Styles {
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

const styles: Styles = {
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
    padding: '28px 24px 24px',
    marginBottom: 16,
    borderRadius: 8,
    border: '1px solid #e5eaf3',
    background: '#f8fafd',
    color: '#243044',
    position: 'relative' as const,
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
  },
  outputLabel: {
    position: 'absolute' as const,
    top: 8,
    right: 12,
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
      status === 'waiting_confirm' ? 'rgba(245, 158, 11, 0.13)' :
      'rgba(148, 163, 184, 0.08)',
    color:
      status === 'running' ? '#315cf6' :
      status === 'completed' ? '#16a34a' :
      status === 'failed' ? '#dc2626' :
      status === 'waiting_confirm' ? '#b45309' :
      '#667085',
    border: `1px solid ${
      status === 'running' ? 'rgba(59, 130, 246, 0.28)' :
      status === 'completed' ? 'rgba(34, 197, 94, 0.26)' :
      status === 'failed' ? 'rgba(239, 68, 68, 0.26)' :
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

/* ============ Component ============ */

const PipelinePage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const { user } = useAuthStore()
  const initialId = searchParams.get('id') || localStorage.getItem('lastPipelineId') || ''
  const [pipelineId, setPipelineId] = useState<string>(initialId)
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null)
  const [userRequest, setUserRequest] = useState('')
  const [loading, setLoading] = useState(false)
  const [projects, setProjects] = useState<any[]>([])
  const [backendProjectId, setBackendProjectId] = useState<string | undefined>(undefined)
  const [frontendProjectId, setFrontendProjectId] = useState<string | undefined>(undefined)
  const [feedback, setFeedback] = useState('')
  const [showCreate, setShowCreate] = useState(!initialId)

  // pipelineId 变化时同步 URL 和 localStorage
  useEffect(() => {
    if (pipelineId) {
      setSearchParams({ id: pipelineId })
      localStorage.setItem('lastPipelineId', pipelineId)
    }
  }, [pipelineId])
  const [previewVisible, setPreviewVisible] = useState(false)
  const [selectedStage, setSelectedStage] = useState<string>('')
  const [defaultPrompts, setDefaultPrompts] = useState<Record<string, string>>({})
  const [editedPrompts, setEditedPrompts] = useState<Record<string, string>>({})
  const [promptsDrawerVisible, setPromptsDrawerVisible] = useState(false)
  const [mergedPrompts, setMergedPrompts] = useState<Record<string, string>>({})
  const [pipelineHistory, setPipelineHistory] = useState<any[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [executionActive, setExecutionActive] = useState(false)
  const [streamingStage, setStreamingStage] = useState('')
  const [streamOutputByStage, setStreamOutputByStage] = useState<Record<string, string>>({})
  const streamAbortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    saveLastPortalPath(user, '/pipeline/development')
  }, [user])

  useEffect(() => {
    return () => streamAbortRef.current?.abort()
  }, [])

  useEffect(() => {
    generatorApi.getProjects({ page: 1, page_size: 100 }).then((data: any) => {
      setProjects(data?.list || [])
    }).catch(() => {})
  }, [])

  const refreshStatus = useCallback(async (targetId = pipelineId) => {
    if (!targetId) return
    try {
      const data = await pipelineApi.getStatus(targetId)
      // 防御：确保每个 stage 的 output 是字符串（部分 LLM 返回 content blocks 数组）
      if (data?.stages) {
        for (const key of Object.keys(data.stages)) {
          const stage = data.stages[key]
          if (stage.output && typeof stage.output !== 'string') {
            if (Array.isArray(stage.output)) {
              stage.output = (stage.output as any[])
                .map((item: any) => (typeof item === 'string' ? item : item?.text || JSON.stringify(item)))
                .join('\n')
            } else {
              stage.output = String(stage.output)
            }
          }
        }
      }
      setPipeline(data)
      if (['waiting_confirm', 'completed', 'failed', 'cancelled'].includes(data.status)) {
        setExecutionActive(false)
      } else if (data.status === 'running') {
        setExecutionActive(true)
      }
    } catch {
      // pipeline 不存在或已过期，清除无效 ID
      setPipelineId('')
      setPipeline(null)
      setShowCreate(true)
      localStorage.removeItem('lastPipelineId')
    }
  }, [pipelineId])

  useEffect(() => { refreshStatus() }, [refreshStatus])

  // 加载历史流水线
  const fetchPipelineHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const res = await pipelineApi.list()
      const list = res?.data?.list || res?.data || res?.list || res || []
      setPipelineHistory(Array.isArray(list) ? list : [])
    } catch { /* ignore */ }
    setHistoryLoading(false)
  }, [])

  useEffect(() => { fetchPipelineHistory() }, [fetchPipelineHistory])

  const handleDeletePipeline = async (id: string) => {
    Modal.confirm({
        title: <span style={{ color: '#111827' }}>确认删除</span>,
      content: <span style={{ color: '#667085' }}>删除后无法恢复，确定要删除这条流水线吗？</span>,
      okType: 'danger',
      okText: '删除',
      cancelText: '取消',
      onOk: async () => {
        try {
          await api.delete(`/flow/pipeline/${id}`)
          message.success('已删除')
          fetchPipelineHistory()
          if (pipelineId === id) {
            setPipelineId('')
            setPipeline(null)
            setShowCreate(true)
            setSearchParams({})
          }
        } catch (e: any) {
          message.error(e?.message || '删除失败')
        }
      },
    })
  }

  // Load default prompts on mount
  useEffect(() => {
    let cancelled = false
    pipelineApi.getDefaultPrompts().then((data) => {
      if (cancelled) return
      setDefaultPrompts(data || {})
      setEditedPrompts({})
    }).catch(() => { /* ignore */ })
    return () => { cancelled = true }
  }, [])

  // 运行中自动刷新
  useEffect(() => {
    if (!pipelineId || !pipeline) return
    if (pipeline.status !== 'running' && !executionActive) return
    const timer = setInterval(() => refreshStatus(), 2000)
    return () => clearInterval(timer)
  }, [pipelineId, pipeline?.status, executionActive, refreshStatus])

  const applyStreamEvent = useCallback((event: PipelineStreamEvent) => {
    if (event.type === 'heartbeat') return

    if (event.stage) {
      setStreamingStage(event.stage)
    }

    if (event.type === 'stage_started' && event.stage) {
      setExecutionActive(true)
      setStreamOutputByStage((prev) => ({ ...prev, [event.stage as string]: '' }))
      setPipeline((prev) => {
        if (!prev) {
          return createPipelineShell(
            event.pipeline_id || pipelineId || '',
            userRequest,
            event.stage as string,
          )
        }
        const stage = prev.stages?.[event.stage as string]
        if (!stage) return { ...prev, status: 'running', current_stage: event.stage as string }
        return {
          ...prev,
          status: 'running',
          current_stage: event.stage as string,
          stages: {
            ...prev.stages,
            [event.stage as string]: { ...stage, status: 'running', output: '' },
          },
        }
      })
      return
    }

    if (event.type === 'chunk' && event.stage && event.content) {
      const stageKey = event.stage
      setExecutionActive(true)
      setStreamOutputByStage((prev) => ({
        ...prev,
        [stageKey]: `${prev[stageKey] || ''}${event.content || ''}`,
      }))
      setPipeline((prev) => {
        if (!prev) return prev
        const stage = prev.stages?.[stageKey]
        if (!stage) return prev
        return {
          ...prev,
          status: 'running',
          current_stage: stageKey,
          stages: {
            ...prev.stages,
            [stageKey]: {
              ...stage,
              status: 'running',
              output: `${stage.output || ''}${event.content || ''}`,
            },
          },
        }
      })
      return
    }

    if (event.type === 'stage_completed' && event.stage) {
      const stageKey = event.stage
      setPipeline((prev) => {
        if (!prev) return prev
        const stage = prev.stages?.[stageKey]
        if (!stage) return prev
        return {
          ...prev,
          stages: {
            ...prev.stages,
            [stageKey]: {
              ...stage,
              status: 'completed',
              output: event.output || stage.output,
              structured_output: event.result || stage.structured_output,
              preview_html: event.preview_html || stage.preview_html,
            },
          },
        }
      })
      return
    }

    if (['waiting_confirm', 'completed', 'failed', 'done', 'error'].includes(event.type)) {
      setExecutionActive(false)
    }
  }, [pipelineId, userRequest])

  const runPipelineStream = useCallback(async (targetId: string, input = '') => {
    streamAbortRef.current?.abort()
    const controller = new AbortController()
    streamAbortRef.current = controller
    setExecutionActive(true)
    let receivedEvent = false

    try {
      await pipelineApi.executeStream(
        targetId,
        input,
        (event) => {
          receivedEvent = true
          applyStreamEvent(event)
        },
        controller.signal,
      )
      await refreshStatus(targetId)
    } catch (e: any) {
      if (e?.name === 'AbortError') return
      if (!receivedEvent) {
        await pipelineApi.execute(targetId, input)
        await refreshStatus(targetId)
        return
      }
      message.error(e?.message || '流式执行中断，请刷新状态后重试')
      await refreshStatus(targetId)
    } finally {
      if (streamAbortRef.current === controller) {
        streamAbortRef.current = null
      }
      setExecutionActive(false)
    }
  }, [applyStreamEvent, refreshStatus])

  const handleCreate = async () => {
    if (!userRequest.trim()) {
      message.warning('请输入需求描述')
      return
    }
    setLoading(true)
    try {
      const backendProj = projects.find(p => String(p.id) === backendProjectId)
      const frontendProj = projects.find(p => String(p.id) === frontendProjectId)
      const customPrompts = Object.fromEntries(
        Object.entries(editedPrompts)
          .filter(([key, value]) => value !== undefined && value !== defaultPrompts[key])
          .map(([key, value]) => [key, value.trim()]),
      )
      const skillConfig = Object.keys(customPrompts).length
        ? { custom_prompts: customPrompts }
        : undefined
      const data = await pipelineApi.create({
        user_request: userRequest.trim(),
        project_id: '',
        project_name: '',
        backend_project_id: backendProjectId || '',
        frontend_project_id: frontendProjectId || '',
        backend_tech: backendProj ? `${backendProj.language}/${backendProj.framework}` : '',
        frontend_tech: frontendProj ? `${frontendProj.language}/${frontendProj.framework}` : '',
        skill_config: skillConfig,
      })
      const id = data.pipeline_id
      setPipelineId(id)
      setPipeline(createPipelineShell(id, userRequest.trim()))
      setSearchParams({ id })
      localStorage.setItem('lastPipelineId', id)
      setShowCreate(false)
      message.success('流水线创建成功')
      // 自动执行第一阶段（LLM调用可能较慢，需要较长超时）
      await runPipelineStream(id)
      await refreshStatus(id)
    } catch (e: any) {
      message.error(e?.message || '创建失败')
    } finally {
      setLoading(false)
    }
  }

  const handleConfirm = async (confirmed: boolean) => {
    if (!pipelineId) return
    setLoading(true)
    try {
      const submittedFeedback = feedback.trim()
      const result = await pipelineApi.confirm(pipelineId, confirmed, submittedFeedback)
      message.success(confirmed ? '已确认，推进下一阶段' : '已退回，正在重新执行')
      setFeedback('')
      await refreshStatus()
      if (confirmed && result?.stage) {
        // 确认后自动触发下一阶段
        runPipelineStream(pipelineId).catch(() => {})
      } else if (!confirmed) {
        // 退回后自动重新执行当前阶段
        runPipelineStream(pipelineId).catch(() => {})
      }
    } catch (e: any) {
      message.error(e?.message || '操作失败')
      await refreshStatus()
    } finally {
      setLoading(false)
    }
  }

  const handleRerun = async () => {
    if (!pipelineId) return
    setLoading(true)
    try {
      await runPipelineStream(pipelineId, feedback)
      setFeedback('')
      await refreshStatus(pipelineId)
    } catch (e: any) {
      message.error(e?.message || '执行失败')
    } finally {
      setLoading(false)
    }
  }

  const handleRollback = async () => {
    if (!pipelineId) return
    setLoading(true)
    try {
      await pipelineApi.rollback(pipelineId)
      message.success('已回退')
      await refreshStatus()
    } catch (e: any) {
      message.error(e?.message || '回退失败')
    } finally {
      setLoading(false)
    }
  }


  const getStepsStatus = (stageKey: string): 'wait' | 'process' | 'finish' | 'error' => {
    if (!pipeline) return 'wait'
    const stage = pipeline.stages?.[stageKey]
    if (!stage) return 'wait'
    if (stage.status === 'completed') return 'finish'
    if (stage.status === 'running') return 'process'
    if (stage.status === 'failed') return 'error'
    return 'wait'
  }

  const isWaitingConfirm = pipeline?.status === 'waiting_confirm'

  // Active stage key: use selectedStage if set, otherwise current stage
  const activeStageKey = selectedStage || pipeline?.current_stage || ''
  const currentStage = pipeline?.stages?.[activeStageKey]
  const isViewingCurrent = activeStageKey === pipeline?.current_stage
  const liveStageOutput = (isViewingCurrent && streamOutputByStage[activeStageKey]) || currentStage?.output || ''
  const pmQuality = activeStageKey === 'requirement'
    ? currentStage?.structured_output?.pm_quality
    : activeStageKey === 'page_design'
      ? currentStage?.structured_output?.design_quality
      : undefined
  const previewQuality = ['ui_preview', 'prototype'].includes(activeStageKey)
    ? currentStage?.structured_output?.preview_quality
    : undefined

  const htmlBlocks = useMemo(() => {
    if (!liveStageOutput) return []
    return extractHtmlBlocks(liveStageOutput)
  }, [liveStageOutput])

  // For prototype/ui_preview, also try direct HTML extraction if blocks are empty
  const previewHtmlContent = useMemo(() => {
    if (!['ui_preview', 'prototype'].includes(activeStageKey)) return ''
    if (currentStage?.preview_html) return currentStage.preview_html
    if (!liveStageOutput) return ''
    // Try extracted blocks first
    if (htmlBlocks.length > 0) {
      return htmlBlocks.map((b: any) => b.code || b).join('\n')
    }
    // Fallback: extract between ```html and ```
    const raw = liveStageOutput
    const startIdx = raw.indexOf('```html')
    if (startIdx === -1) return ''
    const htmlStart = raw.indexOf('\n', startIdx) + 1
    const endIdx = raw.lastIndexOf('```')
    if (endIdx > htmlStart) {
      return raw.substring(htmlStart, endIdx).trim()
    }
    // Last resort: take everything after ```html
    return raw.substring(htmlStart).trim()
  }, [activeStageKey, liveStageOutput, htmlBlocks, currentStage?.preview_html])

  const hasHtmlPreview = previewHtmlContent.length > 0 && ['ui_preview', 'prototype'].includes(activeStageKey)

  // Strip markdown/prg code block wrappers for text stages
  const displayOutput = useMemo(() => {
    if (!liveStageOutput) return ''
    const raw = String(liveStageOutput)
    // If this is a code-heavy stage, return as-is
    if (['development', 'testing', 'code_review'].includes(activeStageKey)) return raw
    // Strip ```markdown, ```prg, ```md wrappers
    const stripped = raw.replace(/^```(?:markdown|prg|md)\s*\n?/i, '').replace(/\n?```\s*$/i, '')
    return stripped
  }, [liveStageOutput, activeStageKey])

  const inlinePreviewSrc = useMemo(() => {
    if (!hasHtmlPreview) return ''
    return prepareUIPreviewHtml(repairTruncatedHtml(previewHtmlContent))
  }, [hasHtmlPreview, previewHtmlContent])

  const isRunning = pipeline?.status === 'running' || executionActive
  const isCompleted = pipeline?.status === 'completed'
  const isFailed = pipeline?.status === 'failed'

  // ============ Create Panel ============
  if (showCreate) {
    return (
      <div className="pipeline-workbench pipeline-create-layout" style={styles.createRoot}>
        <div style={styles.createCard}>
          <div style={styles.createHeader}>
            <div style={styles.createIcon}>
              <ThunderboltOutlined />
            </div>
            <Title level={4} style={{ color: '#111827', marginBottom: 4 }}>
              创建开发流水线
            </Title>
            <Paragraph style={{ color: '#667085', marginBottom: 0, fontSize: 14 }}>
              描述你的需求，AI Agent 团队将自动完成从需求分析到部署的完整开发流程
            </Paragraph>
          </div>

          <div style={styles.createBody}>
            {/* Agent showcase chips */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
              {Object.entries(AGENT_COLORS).map(([agent, color]) => (
                <span
                  key={agent}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                    padding: '3px 10px',
                    borderRadius: 14,
                    fontSize: 11,
                    fontWeight: 600,
                    background: `${color}15`,
                    color,
                    border: `1px solid ${color}30`,
                  }}
                >
                  {agent}
                </span>
              ))}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
              <Select
                placeholder="后端项目（决定后端技术栈）"
                value={backendProjectId}
                onChange={setBackendProjectId}
                allowClear
                showSearch
                optionFilterProp="label"
                options={projects.map((p: any) => ({
                  label: `${p.name} (${p.language}/${p.framework})`,
                  value: String(p.id),
                }))}
              />
              <Select
                placeholder="前端项目（决定前端技术栈，如 PHP 转发层也选这里）"
                value={frontendProjectId}
                onChange={setFrontendProjectId}
                allowClear
                showSearch
                optionFilterProp="label"
                options={projects.map((p: any) => ({
                  label: `${p.name} (${p.language}/${p.framework})`,
                  value: String(p.id),
                }))}
              />
            </div>
            {((backendProjectId && projects.find(p => String(p.id) === backendProjectId)) ||
              (frontendProjectId && projects.find(p => String(p.id) === frontendProjectId))) && (
              <div style={{
                marginBottom: 12, padding: '8px 12px', borderRadius: 8,
                background: 'rgba(59, 130, 246, 0.08)', border: '1px solid rgba(59, 130, 246, 0.18)',
                display: 'flex', gap: 16, flexWrap: 'wrap',
              }}>
                {backendProjectId && (() => {
                  const p = projects.find(p => String(p.id) === backendProjectId)
                  return p ? <Tag color="blue">后端: {p.language}/{p.framework}</Tag> : null
                })()}
                {frontendProjectId && (() => {
                  const p = projects.find(p => String(p.id) === frontendProjectId)
                  return p ? <Tag color="green">前端: {p.language}/{p.framework}</Tag> : null
                })()}
              </div>
            )}

            <TextArea
              rows={6}
              placeholder="请描述你的需求，例如：开发一个用户管理系统，包含用户注册、登录、权限管理等功能..."
              value={userRequest}
              onChange={(e) => setUserRequest(e.target.value)}
              style={{ marginBottom: 16, borderRadius: 10 }}
            />

            {/* Prompt Configuration Editor */}
            <div style={styles.promptCollapseWrap}>
              <Collapse
                ghost
                items={[{
                  key: 'prompts',
                  label: (
                    <div style={styles.promptCollapseBar}>
                      <span style={styles.promptCollapseTitle}>
                        <SettingOutlined />
                        阶段 Prompt 配置
                      </span>
                      <Text style={{ fontSize: 11, color: '#64748b' }}>
                        {Object.keys(defaultPrompts).length > 0 ? `${STAGE_KEYS.length} 个阶段` : '加载中...'}
                      </Text>
                    </div>
                  ),
                  children: (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                      {STAGE_KEYS.map((key) => {
                        const agent = STAGE_AGENT_MAP[key]
                        const agentColor = AGENT_COLORS[agent]
                        const promptText = editedPrompts[key] ?? defaultPrompts[key] ?? ''
                        const isEdited = editedPrompts[key] !== undefined && editedPrompts[key] !== defaultPrompts[key]
                        return (
                          <div key={key}>
                            <div style={styles.promptStageHeader}>
                              <span style={{ fontSize: 14, color: '#315cf6' }}>{STAGE_ICONS[key]}</span>
                              <Text style={{ color: '#111827', fontSize: 13, fontWeight: 600 }}>
                                {STAGE_NAMES[key]}
                              </Text>
                              <Tag color={agentColor} style={{ margin: 0, borderRadius: 6, fontSize: 11 }}>
                                {agent}
                              </Tag>
                              {isEdited && (
                                <Tag
                                  style={{
                                    margin: 0,
                                    borderRadius: 6,
                                    fontSize: 10,
                                    background: 'rgba(245, 158, 11, 0.12)',
                                    color: '#fcd34d',
                                    border: '1px solid rgba(245, 158, 11, 0.28)',
                                  }}
                                >
                                  已修改
                                </Tag>
                              )}
                              <Button
                                type="text"
                                size="small"
                                icon={<UndoOutlined />}
                                disabled={!isEdited}
                                style={styles.promptResetBtn}
                                onClick={() => {
                                  setEditedPrompts((prev) => {
                                    const next = { ...prev }
                                    delete next[key]
                                    return next
                                  })
                                }}
                              >
                                恢复默认
                              </Button>
                            </div>
                            <TextArea
                              rows={8}
                              value={promptText}
                              placeholder="暂无默认 Prompt"
                              onChange={(e) => {
                                setEditedPrompts((prev) => ({
                                  ...prev,
                                  [key]: e.target.value,
                                }))
                              }}
                              style={{
                                borderRadius: 8,
                                fontSize: 13,
                                fontFamily: "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace",
                              }}
                            />
                          </div>
                        )
                      })}
                    </div>
                  ),
                }]}
              />
            </div>

            <Button
              type="primary"
              size="large"
              onClick={handleCreate}
              loading={loading}
              block
              icon={<ThunderboltOutlined />}
              style={{
                height: 48,
                borderRadius: 10,
                fontSize: 15,
                fontWeight: 600,
              }}
            >
              {loading ? '正在创建...' : '启动流水线'}
            </Button>
          </div>
        </div>

        {/* 历史流水线列表 */}
        <div style={{
          flex: 1, minWidth: 320, padding: 20,
          background: '#ffffff',
          border: '1px solid #e5eaf3',
          borderRadius: 10, alignSelf: 'stretch',
          boxShadow: '0 18px 45px rgba(15, 23, 42, 0.06)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <Text style={{ color: '#111827', fontSize: 15, fontWeight: 600 }}>
              <HistoryOutlined style={{ color: '#315cf6', marginRight: 8 }} />
              历史流水线
            </Text>
            <Button size="small" icon={<ReloadOutlined />} onClick={fetchPipelineHistory}>
              刷新
            </Button>
          </div>
          <PipelineHistoryList
            pipelines={pipelineHistory}
            loading={historyLoading}
            onSelect={(id) => { setPipelineId(id); setShowCreate(false) }}
            onDelete={handleDeletePipeline}
          />
        </div>
      </div>
    )
  }

  if (!pipeline) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <Spin size="large" />
      </div>
    )
  }

  // ============ Main Pipeline View ============
  const completedStages = STAGE_KEYS.filter(
    (key) => pipeline.stages?.[key]?.status === 'completed'
  )

  return (
    <div className="pipeline-workbench" style={styles.mainRoot}>
      {/* ---- Header Bar ---- */}
      <div style={styles.headerBar}>
        <div style={styles.headerLeft}>
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => {
              setPipelineId('')
              setPipeline(null)
              setShowCreate(true)
              setSearchParams({})
              fetchPipelineHistory()
            }}
            style={{ color: '#667085', marginRight: 8 }}
          />
          <BranchesOutlined style={{ color: '#60a5fa', fontSize: 16 }} />
          <Text style={styles.pipelineIdText}>
            {pipelineId.length > 12
              ? `${pipelineId.slice(0, 8)}...${pipelineId.slice(-4)}`
              : pipelineId}
          </Text>
          <span style={styles.statusBadge(pipeline.status)}>
            {isRunning && <LoadingOutlined style={{ fontSize: 11 }} />}
            {isCompleted && <CheckCircleOutlined style={{ fontSize: 11 }} />}
            {isFailed && <CloseCircleOutlined style={{ fontSize: 11 }} />}
            {isWaitingConfirm && <ExclamationCircleOutlined style={{ fontSize: 11 }} />}
            {pipeline.status}
          </span>
          {pipeline.user_request && (
            <Tooltip title={pipeline.user_request}>
              <Text type="secondary" style={{ fontSize: 12, maxWidth: 260 }} ellipsis>
                {pipeline.user_request}
              </Text>
            </Tooltip>
          )}
        </div>
        <Space size={8}>
          <Button
            size="small"
            icon={<SettingOutlined />}
            onClick={async () => {
              // Merge: defaults + project-level overrides if available
              const defaults = { ...defaultPrompts }
              if (pipeline?.project_id) {
                try {
                  const projectPrompts = await pipelineApi.getProjectPrompts(pipeline.project_id)
                  Object.assign(defaults, projectPrompts || {})
                } catch { /* ignore, use defaults */ }
              }
              setMergedPrompts(defaults)
              setPromptsDrawerVisible(true)
            }}
            style={{ borderRadius: 6 }}
          >
            查看 Prompt
          </Button>
          {isRunning && (
            <Button
              size="small"
              danger
              onClick={handleRollback}
              disabled={isRunning}
              style={{ borderRadius: 6, opacity: 0.5 }}
            >
              回退
            </Button>
          )}
          {!isRunning && (
            <Button
              size="small"
              icon={<RollbackOutlined />}
              onClick={handleRollback}
              disabled={isRunning}
              style={{ borderRadius: 6 }}
            >
              回退
            </Button>
          )}
        </Space>
      </div>

      {/* ---- Stage Tracker + Content ---- */}
      <div className="pipeline-stage-layout" style={styles.stageTrackerRow}>
        {/* Sidebar: Vertical Stage Tracker */}
        <div className="pipeline-stage-sidebar" style={styles.stageTrackSidebar}>
          {STAGE_KEYS.map((key, idx) => {
            const stageStatus = getStepsStatus(key)
            const stageStr = pipeline.stages?.[key]?.status || 'pending'
            const isActive = key === activeStageKey
            const isDone = stageStatus === 'finish'
            const isCurrent = key === pipeline.current_stage && stageStatus === 'process'
            const isErr = stageStatus === 'error'
            const canView = isDone || isCurrent || isErr

            return (
              <div key={key}>
                {/* connector line */}
                {idx > 0 && (
                  <div
                    style={{
                      width: 1,
                      height: 8,
                      marginLeft: 27,
                      background: isDone
                        ? 'rgba(82, 196, 26, 0.25)'
                        : 'rgba(255, 255, 255, 0.06)',
                    }}
                  />
                )}
                <div
                  style={{
                    ...styles.stageItem(isActive, stageStr),
                    cursor: canView ? 'pointer' : 'default',
                  }}
                  className="pipeline-stage-item"
                  onClick={() => canView ? setSelectedStage(key === selectedStage ? '' : key) : undefined}
                >
                  <div style={styles.stageItemIcon(stageStr)}>
                    {isCurrent ? (
                      <LoadingOutlined style={{ fontSize: 13 }} />
                    ) : isErr ? (
                      <CloseCircleOutlined style={{ fontSize: 13 }} />
                    ) : isDone ? (
                      <CheckCircleOutlined style={{ fontSize: 13 }} />
                    ) : (
                      <span style={{ fontSize: 13 }}>{STAGE_ICONS[key]}</span>
                    )}
                  </div>
                  <span style={styles.stageItemName(isActive, stageStr)}>
                    {STAGE_NAMES[key]}
                  </span>
                </div>
              </div>
            )
          })}
        </div>

        {/* Content Area */}
        <div className="pipeline-stage-content" style={styles.contentArea}>
          {/* Stage Detail */}
          <div style={styles.stageDetailCard}>
            {/* Detail Header */}
            <div style={styles.stageDetailHeader}>
              {!isViewingCurrent && (
                <Button
                  type="text"
                  size="small"
                  icon={<ArrowLeftOutlined />}
                  onClick={() => setSelectedStage('')}
                  style={{ color: '#315cf6', marginRight: 8, padding: '0 4px' }}
                >
                  返回当前
                </Button>
              )}
              <div style={{
                ...styles.stageItemIcon(currentStage?.status || 'pending'),
                width: 32,
                height: 32,
                fontSize: 15,
              }}>
                {isRunning && isViewingCurrent ? (
                  <LoadingOutlined />
                ) : (
                  STAGE_ICONS[activeStageKey]
                )}
              </div>
              <Text strong style={{ color: '#111827', fontSize: 15 }}>
                {STAGE_NAMES[activeStageKey] || activeStageKey}
                {!isViewingCurrent && <Text style={{ color: '#64748b', fontSize: 12, marginLeft: 8 }}>(历史查看)</Text>}
              </Text>
              <Tag
                color={AGENT_COLORS[currentStage?.agent_type || 'PM']}
                style={{ margin: 0, borderRadius: 6 }}
              >
                {currentStage?.agent_type || 'PM'}
              </Tag>
              <span style={styles.statusBadge(
                isViewingCurrent && isRunning ? 'running' :
                isViewingCurrent && isWaitingConfirm ? 'waiting_confirm' :
                currentStage?.status === 'completed' ? 'completed' :
                currentStage?.status === 'failed' ? 'failed' : 'pending'
              )}>
                {isViewingCurrent && isRunning ? '执行中' :
                 isViewingCurrent && isWaitingConfirm ? '等待确认' :
                 currentStage?.status === 'completed' ? '已完成' :
                 currentStage?.status === 'failed' ? '失败' : '待执行'}
              </span>
            </div>

            {/* Detail Body */}
            <div style={styles.stageDetailBody}>
              {loading && !executionActive && (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <Spin size="large" tip="Agent 正在工作..." />
                </div>
              )}

              {/* Error Display */}
              {currentStage?.status === 'failed' && currentStage?.error && (
                <div style={{
                  padding: 16, marginBottom: 16,
                  background: 'rgba(245, 34, 45, 0.08)',
                  border: '1px solid rgba(245, 34, 45, 0.3)',
                borderRadius: 8, color: '#dc2626',
                }}>
                  <strong>错误信息：</strong>{currentStage.error}
                </div>
              )}

              {executionActive && isViewingCurrent && (
                <div style={{
                  padding: 14,
                  marginBottom: 16,
                  background: 'rgba(59, 130, 246, 0.08)',
                  border: '1px solid rgba(59, 130, 246, 0.18)',
                  borderRadius: 10,
                }}>
                  <Space size={8} style={{ marginBottom: liveStageOutput ? 8 : 0 }}>
                    <LoadingOutlined style={{ color: '#315cf6' }} />
                    <Text style={{ color: '#315cf6', fontSize: 13 }}>
                      Agent 正在实时输出{streamingStage ? `：${STAGE_NAMES[streamingStage] || streamingStage}` : ''}
                    </Text>
                  </Space>
                  {liveStageOutput && (
                    <Text style={{ color: '#667085', fontSize: 12 }}>
                      可以先看方向是否对；当前阶段结束后可直接确认、退回或补充修改意见。
                    </Text>
                  )}
                </div>
              )}

              {pmQuality && (
                <PMQualityPanel stageKey={activeStageKey} quality={pmQuality} />
              )}

              {previewQuality && (
                <PreviewQualityPanel quality={previewQuality} />
              )}

              {/* Output */}
              {liveStageOutput && (!loading || executionActive) && (
                <div style={styles.outputContainer}>
                  <span style={styles.outputLabel}>OUTPUT</span>
                  {hasHtmlPreview ? (
                    <iframe
                      srcDoc={inlinePreviewSrc}
                      style={{
                        width: '100%',
                        minHeight: 400,
                        border: '1px solid rgba(148, 163, 184, 0.18)',
                        borderRadius: 8,
                      }}
                      sandbox="allow-same-origin allow-scripts"
                      title="UI Preview"
                    />
                  ) : (
                    <MarkdownRenderer content={displayOutput} className="pipeline-markdown" />
                  )}
                </div>
              )}
              {/* HTML Preview - open in new window for non-tech users */}
              {hasHtmlPreview && (currentStage?.status === 'completed' || isWaitingConfirm) && (
                <Button
                  type="primary"
                  icon={<EyeOutlined />}
                  onClick={() => {
                    const repaired = repairTruncatedHtml(previewHtmlContent)
                    const blob = new Blob([repaired], { type: 'text/html' })
                    const url = URL.createObjectURL(blob)
                    window.open(url, '_blank')
                  }}
                  style={{
                    marginBottom: 16,
                    borderRadius: 8,
                    background: '#16a34a',
                    borderColor: '#16a34a',
                  }}
                >
                  在新窗口打开预览
                </Button>
              )}

              {/* Code Files */}
              {currentStage?.code_files && Object.keys(currentStage.code_files).length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                    <Text style={{ color: '#667085', fontSize: 12, textTransform: 'uppercase', letterSpacing: 0 }}>
                      生成的代码文件
                    </Text>
                    <Button
                      size="small"
                      icon={<DownloadOutlined />}
                      onClick={() => {
                        // 打包所有代码文件为 zip
                        const files = Object.entries(currentStage.code_files || {})
                        if (files.length === 1) {
                          // 单文件直接下载
                          const [name, content] = files[0]
                          const blob = new Blob([content as string], { type: 'text/plain' })
                          const url = URL.createObjectURL(blob)
                          const a = document.createElement('a')
                          a.href = url
                          a.download = name
                          a.click()
                          URL.revokeObjectURL(url)
                        } else {
                          // 多文件逐个下载
                          files.forEach(([name, content]) => {
                            const blob = new Blob([content as string], { type: 'text/plain' })
                            const url = URL.createObjectURL(blob)
                            const a = document.createElement('a')
                            a.href = url
                            a.download = name
                            a.click()
                            URL.revokeObjectURL(url)
                          })
                        }
                      }}
                      style={{ borderRadius: 6, fontSize: 12 }}
                    >
                      下载代码
                    </Button>
                  </div>
                  {Object.entries(currentStage.code_files).map(([name, content]) => (
                    <div key={name} style={styles.codeFileItem}>
                      <CodeOutlined style={{ color: '#60a5fa', fontSize: 12 }} />
                      <Text code style={{ fontSize: 12 }}>{name}</Text>
                      <Text type="secondary" style={{ fontSize: 11, marginLeft: 'auto' }}>
                        {(content as string).length} chars
                      </Text>
                    </div>
                  ))}
                </div>
              )}

              {/* Confirm Panel - only when viewing current stage */}
              {isWaitingConfirm && isViewingCurrent && (
                <div style={styles.confirmPanel}>
                  <Alert
                    message="请确认当前阶段输出是否符合预期"
                    description="确认后将自动推进到下一阶段；退回时可在下方填写修订意见。"
                    type="warning"
                    showIcon
                    style={{
                      marginBottom: 14,
                      background: 'rgba(120, 53, 15, 0.22)',
                      border: '1px solid rgba(245, 158, 11, 0.22)',
                      borderRadius: 8,
                    }}
                  />
                  <TextArea
                    rows={3}
                    placeholder="如果有修订意见，请在此输入..."
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    style={{ marginBottom: 0, borderRadius: 8 }}
                  />
                  <div style={styles.confirmPanelActions}>
                    <Button
                      type="primary"
                      icon={<CheckCircleOutlined />}
                      onClick={() => handleConfirm(true)}
                      loading={loading}
                      style={{ borderRadius: 8 }}
                    >
                      确认并继续
                    </Button>
                    <Button
                      danger
                      icon={<CloseCircleOutlined />}
                      onClick={() => handleConfirm(false)}
                      loading={loading}
                      style={{ borderRadius: 8 }}
                    >
                      退回修订
                    </Button>
                  </div>
                </div>
              )}

              {/* Fail Panel */}
              {isFailed && (
                <div style={styles.failPanel}>
                  <Alert
                    message={currentStage?.error || '执行失败'}
                    type="error"
                    showIcon
                    style={{
                      marginBottom: 14,
                      background: 'rgba(245, 34, 45, 0.08)',
                      border: '1px solid rgba(245, 34, 45, 0.15)',
                      borderRadius: 8,
                    }}
                  />
                  <Space>
                    <Button
                      type="primary"
                      onClick={handleRerun}
                      loading={loading}
                      icon={<PlayCircleOutlined />}
                      style={{ borderRadius: 8 }}
                    >
                      重新执行
                    </Button>
                    <Button
                      icon={<RollbackOutlined />}
                      onClick={handleRollback}
                      style={{ borderRadius: 8 }}
                    >
                      回退
                    </Button>
                  </Space>
                </div>
              )}

              {/* Pending — 回退后可继续执行 */}
              {!isRunning && !isWaitingConfirm && !isFailed && !isCompleted && pipeline?.status === 'pending' && (
                <div style={{
                  marginTop: 16,
                  padding: 16,
                  background: 'rgba(59, 130, 246, 0.08)',
                  borderRadius: 10,
                  border: '1px solid rgba(59, 130, 246, 0.18)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }}>
                  <PlayCircleOutlined style={{ fontSize: 18, color: '#60a5fa' }} />
                  <Text style={{ color: 'rgba(255,255,255,0.65)', flex: 1 }}>
                    当前阶段待执行，点击继续推进流水线
                  </Text>
                  <Button
                    type="primary"
                    onClick={handleRerun}
                    loading={loading}
                    icon={<SendOutlined />}
                    style={{ borderRadius: 8 }}
                  >
                    继续执行
                  </Button>
                </div>
              )}

              {/* Completed */}
              {isCompleted && (
                <div style={styles.completedBanner}>
                  <CheckCircleOutlined style={{ fontSize: 22, color: '#22c55e' }} />
                  <div>
                    <Text strong style={{ color: '#86efac', fontSize: 15 }}>
                      流水线全部完成
                    </Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      所有 8 个阶段已成功执行，项目代码已就绪。
                    </Text>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Execution History */}
          <div style={styles.historyCard}>
            <div style={{
              padding: '14px 20px',
              borderBottom: '1px solid #e5eaf3',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}>
              <HistoryOutlined style={{ color: '#315cf6' }} />
              <Text style={{ color: '#111827', fontSize: 13, fontWeight: 600 }}>
                执行历史
              </Text>
              <Badge
                count={completedStages.length}
                style={{ background: '#edf3ff', color: '#315cf6', boxShadow: 'none' }}
                overflowCount={99}
              />
            </div>
            <div style={{ padding: '8px 20px 16px' }}>
              {completedStages.length === 0 ? (
                <Empty
                  description="暂无完成的阶段"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  style={{ padding: '16px 0' }}
                />
              ) : (
                completedStages.map((key, idx) => {
                  const stage = pipeline.stages[key]
                  const isLast = idx === completedStages.length - 1
                  return (
                    <div key={key} style={styles.timelineRow(isLast)}>
                      <div style={{ position: 'relative' }}>
                        <div style={styles.timelineDot(stage.status)} />
                        {!isLast && <div style={styles.timelineLine} />}
                      </div>
                      <div style={styles.timelineContent}>
                        <Text style={{ color: '#334155', fontSize: 13, fontWeight: 500 }}>
                          {STAGE_NAMES[key]}
                        </Text>
                        <Tag
                          color={AGENT_COLORS[stage.agent_type]}
                          style={{ margin: 0, fontSize: 11, borderRadius: 4, lineHeight: '18px', padding: '0 6px' }}
                        >
                          {stage.agent_type}
                        </Tag>
                        {stage.completed_at && (
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            {stage.completed_at}
                          </Text>
                        )}
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>
      </div>

      {/* UI Preview Drawer */}
      <Drawer
        title={
          <Space>
            <EyeOutlined style={{ color: '#315cf6' }} />
            <span>UI 预览</span>
          </Space>
        }
        width="80%"
        open={previewVisible}
        onClose={() => setPreviewVisible(false)}
        styles={{
          header: {
            background: '#ffffff',
            borderBottom: '1px solid #e5eaf3',
          },
          body: {
            background: '#f6f8fc',
            padding: 16,
          },
        }}
      >
        {hasHtmlPreview && previewHtmlContent ? (
          <iframe
            srcDoc={prepareUIPreviewHtml(repairTruncatedHtml(previewHtmlContent))}
            style={{
              width: '100%',
              height: '80vh',
              border: '1px solid rgba(148, 163, 184, 0.16)',
              borderRadius: 10,
            }}
            sandbox="allow-same-origin allow-scripts"
            title="UI Preview"
          />
        ) : (
          <Empty description="暂无预览" />
        )}
      </Drawer>

      {/* Prompt Drawer */}
      <Drawer
        title={
          <Space>
            <SettingOutlined style={{ color: '#315cf6' }} />
            <span>阶段 Prompt 配置</span>
            <Text style={{ fontSize: 12, color: '#64748b' }}>
              (最终合并结果)
            </Text>
          </Space>
        }
        width={640}
        open={promptsDrawerVisible}
        onClose={() => setPromptsDrawerVisible(false)}
        styles={{
          header: {
            background: '#ffffff',
            borderBottom: '1px solid #e5eaf3',
          },
          body: {
            background: '#f6f8fc',
            padding: 20,
          },
        }}
      >
        {Object.keys(mergedPrompts).length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin tip="加载 Prompt 中..." />
          </div>
        ) : (
          STAGE_KEYS.map((key) => {
            const agent = STAGE_AGENT_MAP[key]
            const agentColor = AGENT_COLORS[agent]
            const promptText = mergedPrompts[key] || ''
            return (
              <div key={key} style={styles.promptDrawerStage}>
                <div style={styles.promptDrawerStageHeader}>
                  <span style={{ color: agentColor, fontSize: 14 }}>{STAGE_ICONS[key]}</span>
                  <Text style={{ color: '#111827', fontSize: 14, fontWeight: 600 }}>
                    {STAGE_NAMES[key]}
                  </Text>
                  <Tag color={agentColor} style={{ margin: 0, borderRadius: 6, fontSize: 11 }}>
                    {agent}
                  </Tag>
                </div>
                {promptText ? (
                  <div style={styles.promptDrawerBody}>{promptText}</div>
                ) : (
                  <Text style={{ color: '#64748b', fontSize: 12, fontStyle: 'italic' }}>
                    暂无 Prompt 配置
                  </Text>
                )}
              </div>
            )
          })
        )}
      </Drawer>
    </div>
  )
}

export default PipelinePage
