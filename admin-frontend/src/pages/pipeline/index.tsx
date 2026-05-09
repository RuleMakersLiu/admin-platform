import React, { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Button, Spin, Input, Tag, Empty,
  message, Space, Typography, Alert, Drawer,
  Tooltip, Badge, Collapse,
} from 'antd'
import {
  CheckCircleOutlined, CloseCircleOutlined,
  LoadingOutlined, RollbackOutlined, EyeOutlined, CodeOutlined,
  FileTextOutlined, RocketOutlined, BugOutlined, SendOutlined,
  ThunderboltOutlined, BranchesOutlined, HistoryOutlined,
  ExclamationCircleOutlined, PlayCircleOutlined, ArrowLeftOutlined,
  UndoOutlined, SettingOutlined,
} from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import { pipelineApi, type PipelineStatus } from '@/services/pipeline'
import { MarkdownRenderer } from '@/utils/markdown'
import { extractHtmlBlocks, prepareUIPreviewHtml } from '@/utils/sanitize'

const { TextArea } = Input
const { Title, Text, Paragraph } = Typography

const AGENT_COLORS: Record<string, string> = {
  PM: '#1890ff', PJM: '#722ed1', BE: '#52c41a', FE: '#fa8c16', QA: '#f5222d', RPT: '#13c2c2',
}

const STAGE_ICONS: Record<string, React.ReactNode> = {
  requirement: <FileTextOutlined />,
  ui_preview: <EyeOutlined />,
  development: <CodeOutlined />,
  code_review: <CheckCircleOutlined />,
  testing: <BugOutlined />,
  commit: <SendOutlined />,
  deploy: <RocketOutlined />,
  report: <FileTextOutlined />,
}

const STAGE_NAMES: Record<string, string> = {
  requirement: '需求分析',
  ui_preview: 'UI预览',
  development: '代码生成',
  code_review: '代码审查',
  testing: '自动化测试',
  commit: '代码提交',
  deploy: '部署发布',
  report: '总结报告',
}

const STAGE_KEYS = ['requirement', 'ui_preview', 'development', 'code_review', 'testing', 'commit', 'deploy', 'report']

const STAGE_AGENT_MAP: Record<string, string> = {
  requirement: 'PM',
  ui_preview: 'FE',
  development: 'BE',
  code_review: 'BE',
  testing: 'QA',
  commit: 'PJM',
  deploy: 'PJM',
  report: 'RPT',
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
    alignItems: 'center',
    justifyContent: 'center',
  },
  createCard: {
    maxWidth: 720,
    width: '100%',
    border: '1px solid rgba(0, 212, 255, 0.2)',
    borderRadius: 16,
    background: 'rgba(15, 15, 25, 0.85)',
    backdropFilter: 'blur(20px)',
    overflow: 'hidden',
  },
  createHeader: {
    padding: '32px 32px 0 32px',
    textAlign: 'center' as const,
  },
  createIcon: {
    fontSize: 48,
    color: '#00d4ff',
    marginBottom: 16,
    filter: 'drop-shadow(0 0 12px rgba(0, 212, 255, 0.5))',
  },
  createBody: {
    padding: '24px 32px 32px',
  },

  /* -- Main page layout -- */
  mainRoot: {
    padding: 20,
    minHeight: 'calc(100vh - 120px)',
  },

  /* -- Header bar -- */
  headerBar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '14px 20px',
    marginBottom: 16,
    background: 'rgba(15, 15, 25, 0.7)',
    backdropFilter: 'blur(12px)',
    border: '1px solid rgba(0, 212, 255, 0.15)',
    borderRadius: 12,
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    flexWrap: 'wrap' as const,
  },
  pipelineIdText: {
    fontFamily: "'Rajdhani', monospace",
    fontSize: 14,
    color: '#00d4ff',
    letterSpacing: '0.5px',
  },

  /* -- Vertical stage tracker -- */
  stageTrackerRow: {
    display: 'flex',
    alignItems: 'stretch',
    gap: 16,
    marginBottom: 16,
  },
  stageTrackSidebar: {
    width: 220,
    flexShrink: 0,
    background: 'rgba(15, 15, 25, 0.7)',
    backdropFilter: 'blur(12px)',
    border: '1px solid rgba(0, 212, 255, 0.15)',
    borderRadius: 12,
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
      ? 'linear-gradient(90deg, rgba(0, 212, 255, 0.12), transparent)'
      : 'transparent',
    borderLeft: isActive ? '3px solid #00d4ff' : '3px solid transparent',
    transition: 'all 0.25s ease',
  }),
  stageItemIcon: (status: string) => ({
    width: 28,
    height: 28,
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 13,
    flexShrink: 0,
    background:
      status === 'completed' ? 'rgba(82, 196, 26, 0.15)' :
      status === 'running' ? 'rgba(0, 212, 255, 0.15)' :
      status === 'failed' ? 'rgba(245, 34, 45, 0.15)' :
      'rgba(255, 255, 255, 0.05)',
    color:
      status === 'completed' ? '#52c41a' :
      status === 'running' ? '#00d4ff' :
      status === 'failed' ? '#f5222d' :
      '#555',
    border: `1px solid ${
      status === 'completed' ? 'rgba(82, 196, 26, 0.3)' :
      status === 'running' ? 'rgba(0, 212, 255, 0.3)' :
      status === 'failed' ? 'rgba(245, 34, 45, 0.3)' :
      'rgba(255, 255, 255, 0.08)'
    }`,
  }),
  stageItemName: (isActive: boolean, status: string) => ({
    fontSize: 13,
    color: isActive ? '#e0e0e0' : status === 'completed' ? '#aaa' : '#555',
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
    background: 'rgba(15, 15, 25, 0.7)',
    backdropFilter: 'blur(12px)',
    border: '1px solid rgba(0, 212, 255, 0.15)',
    borderRadius: 12,
    overflow: 'hidden',
  },
  stageDetailHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: '16px 20px',
    borderBottom: '1px solid rgba(0, 212, 255, 0.1)',
    background: 'rgba(0, 212, 255, 0.03)',
  },
  stageDetailBody: {
    padding: 20,
  },

  /* -- Output container -- */
  outputContainer: {
    maxHeight: 560,
    overflow: 'auto',
    padding: 20,
    marginBottom: 16,
    borderRadius: 10,
    border: '1px solid rgba(0, 212, 255, 0.1)',
    background: 'rgba(10, 10, 18, 0.7)',
    color: '#e0e0e0',
    position: 'relative' as const,
  },
  outputLabel: {
    position: 'absolute' as const,
    top: 8,
    right: 12,
    fontSize: 11,
    color: '#555',
    textTransform: 'uppercase' as const,
    letterSpacing: '1px',
  },

  /* -- Confirm panel -- */
  confirmPanel: {
    marginTop: 16,
    padding: 20,
    background: 'rgba(250, 173, 20, 0.06)',
    backdropFilter: 'blur(12px)',
    border: '1px solid rgba(250, 173, 20, 0.25)',
    borderRadius: 12,
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(250, 173, 20, 0.1)',
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
    background: 'rgba(245, 34, 45, 0.06)',
    border: '1px solid rgba(245, 34, 45, 0.2)',
    borderRadius: 12,
  },

  /* -- Timeline / history card -- */
  historyCard: {
    background: 'rgba(15, 15, 25, 0.5)',
    border: '1px solid rgba(0, 212, 255, 0.1)',
    borderRadius: 12,
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
      status === 'completed' ? '#52c41a' :
      status === 'running' ? '#00d4ff' :
      status === 'failed' ? '#f5222d' : '#444',
    boxShadow:
      status === 'completed' ? '0 0 8px rgba(82, 196, 26, 0.5)' :
      status === 'running' ? '0 0 8px rgba(0, 212, 255, 0.5)' :
      'none',
  }),
  timelineLine: {
    position: 'absolute' as const,
    left: 4.5,
    top: 24,
    bottom: -10,
    width: 1,
    background: 'rgba(0, 212, 255, 0.12)',
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
    background: 'rgba(0, 212, 255, 0.04)',
    border: '1px solid rgba(0, 212, 255, 0.08)',
    marginBottom: 6,
    transition: 'all 0.2s ease',
  },

  /* -- Completed banner -- */
  completedBanner: {
    padding: '16px 20px',
    background: 'linear-gradient(135deg, rgba(82, 196, 26, 0.08), rgba(0, 212, 255, 0.06))',
    border: '1px solid rgba(82, 196, 26, 0.25)',
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
      status === 'running' ? 'rgba(0, 212, 255, 0.12)' :
      status === 'completed' ? 'rgba(82, 196, 26, 0.12)' :
      status === 'failed' ? 'rgba(245, 34, 45, 0.12)' :
      status === 'waiting_confirm' ? 'rgba(250, 173, 20, 0.12)' :
      'rgba(255, 255, 255, 0.05)',
    color:
      status === 'running' ? '#00d4ff' :
      status === 'completed' ? '#52c41a' :
      status === 'failed' ? '#f5222d' :
      status === 'waiting_confirm' ? '#faad14' :
      '#888',
    border: `1px solid ${
      status === 'running' ? 'rgba(0, 212, 255, 0.25)' :
      status === 'completed' ? 'rgba(82, 196, 26, 0.25)' :
      status === 'failed' ? 'rgba(245, 34, 45, 0.25)' :
      status === 'waiting_confirm' ? 'rgba(250, 173, 20, 0.25)' :
      'rgba(255, 255, 255, 0.08)'
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
    color: '#00d4ff',
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
    color: '#888',
    borderRadius: 6,
    borderColor: 'rgba(255,255,255,0.12)',
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
    borderBottom: '1px solid rgba(0, 212, 255, 0.1)',
  },
  promptDrawerBody: {
    padding: '8px 12px',
    borderRadius: 8,
    background: 'rgba(10, 10, 18, 0.7)',
    border: '1px solid rgba(0, 212, 255, 0.08)',
    color: '#ccc',
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
  const initialId = searchParams.get('id') || ''
  const [pipelineId, setPipelineId] = useState<string>(initialId)
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null)
  const [userRequest, setUserRequest] = useState('')
  const [loading, setLoading] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [showCreate, setShowCreate] = useState(!initialId)
  const [previewVisible, setPreviewVisible] = useState(false)
  const [previewHtml, setPreviewHtml] = useState('')
  const [selectedStage, setSelectedStage] = useState<string>('')
  const [defaultPrompts, setDefaultPrompts] = useState<Record<string, string>>({})
  const [editedPrompts, setEditedPrompts] = useState<Record<string, string>>({})
  const [promptsDrawerVisible, setPromptsDrawerVisible] = useState(false)
  const [mergedPrompts, setMergedPrompts] = useState<Record<string, string>>({})

  const refreshStatus = useCallback(async () => {
    if (!pipelineId) return
    try {
      const data = await pipelineApi.getStatus(pipelineId)
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
    } catch { /* ignore */ }
  }, [pipelineId])

  useEffect(() => { refreshStatus() }, [refreshStatus])

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
    if (pipeline.status !== 'running') return
    const timer = setInterval(refreshStatus, 3000)
    return () => clearInterval(timer)
  }, [pipelineId, pipeline?.status, refreshStatus])

  const handleCreate = async () => {
    if (!userRequest.trim()) {
      message.warning('请输入需求描述')
      return
    }
    setLoading(true)
    try {
      const data = await pipelineApi.create({ user_request: userRequest })
      const id = data.pipeline_id
      setPipelineId(id)
      setSearchParams({ id })
      setShowCreate(false)
      message.success('流水线创建成功')
      // 自动执行第一阶段（LLM调用可能较慢，需要较长超时）
      await pipelineApi.execute(id, userRequest)
      await refreshStatus()
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
      await pipelineApi.confirm(pipelineId, confirmed, feedback)
      message.success(confirmed ? '已确认，自动推进' : '已退回')
      setFeedback('')
      await refreshStatus()
    } catch (e: any) {
      message.error(e?.message || '操作失败')
    } finally {
      setLoading(false)
    }
  }

  const handleRerun = async () => {
    if (!pipelineId) return
    setLoading(true)
    try {
      await pipelineApi.execute(pipelineId, feedback)
      setFeedback('')
      await refreshStatus()
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

  const handlePreview = async () => {
    if (!pipelineId) return
    try {
      const data = await pipelineApi.getPreview(pipelineId)
      setPreviewHtml(data.preview_html || data.output || '')
      setPreviewVisible(true)
    } catch { /* ignore */ }
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

  const htmlBlocks = useMemo(() => {
    if (!currentStage?.output) return []
    return extractHtmlBlocks(currentStage.output)
  }, [currentStage?.output])

  const hasHtmlPreview = htmlBlocks.length > 0 && activeStageKey === 'ui_preview'

  // Strip markdown/prg code block wrappers for text stages
  const displayOutput = useMemo(() => {
    if (!currentStage?.output) return ''
    const raw = String(currentStage.output)
    // If this is a code-heavy stage, return as-is
    if (['development', 'testing', 'code_review'].includes(activeStageKey)) return raw
    // Strip ```markdown, ```prg, ```md wrappers
    const stripped = raw.replace(/^```(?:markdown|prg|md)\s*\n?/i, '').replace(/\n?```\s*$/i, '')
    return stripped
  }, [currentStage?.output, activeStageKey])

  const inlinePreviewSrc = useMemo(() => {
    if (!hasHtmlPreview) return ''
    const htmlCode = htmlBlocks.map((b: any) => b.code || b).join('\n')
    return prepareUIPreviewHtml(htmlCode)
  }, [hasHtmlPreview, htmlBlocks])

  const isRunning = pipeline?.status === 'running'
  const isCompleted = pipeline?.status === 'completed'
  const isFailed = pipeline?.status === 'failed'

  // ============ Create Panel ============
  if (showCreate) {
    return (
      <div style={styles.createRoot}>
        <div style={styles.createCard}>
          <div style={styles.createHeader}>
            <div style={styles.createIcon}>
              <ThunderboltOutlined />
            </div>
            <Title level={4} style={{ color: '#e0e0e0', marginBottom: 4 }}>
              创建开发流水线
            </Title>
            <Paragraph style={{ color: '#888', marginBottom: 0, fontSize: 14 }}>
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
                      <Text style={{ fontSize: 11, color: '#555' }}>
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
                              <span style={{ fontSize: 14, color: '#e0e0e0' }}>{STAGE_ICONS[key]}</span>
                              <Text style={{ color: '#e0e0e0', fontSize: 13, fontWeight: 600 }}>
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
                                    background: 'rgba(250, 173, 20, 0.12)',
                                    color: '#faad14',
                                    border: '1px solid rgba(250, 173, 20, 0.25)',
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
    <div style={styles.mainRoot}>
      {/* ---- Header Bar ---- */}
      <div style={styles.headerBar}>
        <div style={styles.headerLeft}>
          <BranchesOutlined style={{ color: '#00d4ff', fontSize: 16 }} />
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
      <div style={styles.stageTrackerRow}>
        {/* Sidebar: Vertical Stage Tracker */}
        <div style={styles.stageTrackSidebar}>
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
        <div style={styles.contentArea}>
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
                  style={{ color: '#00d4ff', marginRight: 8, padding: '0 4px' }}
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
              <Text strong style={{ color: '#e0e0e0', fontSize: 15 }}>
                {STAGE_NAMES[activeStageKey] || activeStageKey}
                {!isViewingCurrent && <Text style={{ color: '#666', fontSize: 12, marginLeft: 8 }}>(历史查看)</Text>}
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
              {loading && (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <Spin size="large" tip="Agent 正在工作..." />
                </div>
              )}

              {/* Output */}
              {currentStage?.output && !loading && (
                <div style={styles.outputContainer}>
                  <span style={styles.outputLabel}>OUTPUT</span>
                  {hasHtmlPreview ? (
                    <iframe
                      srcDoc={inlinePreviewSrc}
                      style={{
                        width: '100%',
                        minHeight: 400,
                        border: '1px solid rgba(0, 212, 255, 0.15)',
                        borderRadius: 8,
                      }}
                      sandbox="allow-same-origin allow-scripts"
                      title="UI Preview"
                    />
                  ) : (
                    <MarkdownRenderer content={displayOutput} />
                  )}
                </div>
              )}
              {/* UI Preview Button */}
              {(activeStageKey === 'ui_preview' && (currentStage?.status === 'completed' || isWaitingConfirm)) && (
                <Button
                  type="default"
                  icon={<EyeOutlined />}
                  onClick={handlePreview}
                  style={{
                    marginBottom: 16,
                    borderRadius: 8,
                    borderColor: 'rgba(0, 212, 255, 0.3)',
                    color: '#00d4ff',
                  }}
                >
                  查看完整预览
                </Button>
              )}

              {/* Code Files */}
              {currentStage?.code_files && Object.keys(currentStage.code_files).length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <Text style={{ color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: 8, display: 'block' }}>
                    生成的代码文件
                  </Text>
                  {Object.entries(currentStage.code_files).map(([name, content]) => (
                    <div key={name} style={styles.codeFileItem}>
                      <CodeOutlined style={{ color: '#00d4ff', fontSize: 12 }} />
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
                      background: 'rgba(250, 173, 20, 0.08)',
                      border: '1px solid rgba(250, 173, 20, 0.15)',
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
                  background: 'rgba(0, 212, 255, 0.06)',
                  borderRadius: 10,
                  border: '1px solid rgba(0, 212, 255, 0.15)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }}>
                  <PlayCircleOutlined style={{ fontSize: 18, color: '#00d4ff' }} />
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
                  <CheckCircleOutlined style={{ fontSize: 22, color: '#52c41a' }} />
                  <div>
                    <Text strong style={{ color: '#52c41a', fontSize: 15 }}>
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
              borderBottom: '1px solid rgba(0, 212, 255, 0.08)',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}>
              <HistoryOutlined style={{ color: '#00d4ff' }} />
              <Text style={{ color: '#aaa', fontSize: 13, fontWeight: 600 }}>
                执行历史
              </Text>
              <Badge
                count={completedStages.length}
                style={{ background: 'rgba(0, 212, 255, 0.2)', color: '#00d4ff', boxShadow: 'none' }}
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
                        <Text style={{ color: '#ccc', fontSize: 13, fontWeight: 500 }}>
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
            <EyeOutlined style={{ color: '#00d4ff' }} />
            <span>UI 预览</span>
          </Space>
        }
        width="80%"
        open={previewVisible}
        onClose={() => setPreviewVisible(false)}
        styles={{
          header: {
            background: 'rgba(15, 15, 25, 0.95)',
            borderBottom: '1px solid rgba(0, 212, 255, 0.15)',
          },
          body: {
            background: 'rgba(10, 10, 15, 0.9)',
            padding: 16,
          },
        }}
      >
        {previewHtml ? (
          <iframe
            srcDoc={prepareUIPreviewHtml(previewHtml)}
            style={{
              width: '100%',
              height: '80vh',
              border: '1px solid rgba(0, 212, 255, 0.15)',
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
            <SettingOutlined style={{ color: '#00d4ff' }} />
            <span>阶段 Prompt 配置</span>
            <Text style={{ fontSize: 12, color: '#666' }}>
              (最终合并结果)
            </Text>
          </Space>
        }
        width={640}
        open={promptsDrawerVisible}
        onClose={() => setPromptsDrawerVisible(false)}
        styles={{
          header: {
            background: 'rgba(15, 15, 25, 0.95)',
            borderBottom: '1px solid rgba(0, 212, 255, 0.15)',
          },
          body: {
            background: 'rgba(10, 10, 15, 0.9)',
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
                  <Text style={{ color: '#e0e0e0', fontSize: 14, fontWeight: 600 }}>
                    {STAGE_NAMES[key]}
                  </Text>
                  <Tag color={agentColor} style={{ margin: 0, borderRadius: 6, fontSize: 11 }}>
                    {agent}
                  </Tag>
                </div>
                {promptText ? (
                  <div style={styles.promptDrawerBody}>{promptText}</div>
                ) : (
                  <Text style={{ color: '#555', fontSize: 12, fontStyle: 'italic' }}>
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
