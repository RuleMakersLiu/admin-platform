import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import {
  Button, Spin, Input, Tag, Empty,
  message, Space, Typography, Alert, Drawer,
  Tooltip, Badge, Collapse, Select, Modal,
} from 'antd'
import {
  CheckCircleOutlined, CloseCircleOutlined,
  LoadingOutlined, RollbackOutlined, EyeOutlined, CodeOutlined,
  SendOutlined,
  DownloadOutlined,
  ThunderboltOutlined, BranchesOutlined, HistoryOutlined,
  ExclamationCircleOutlined, PlayCircleOutlined, ArrowLeftOutlined,
  UndoOutlined, SettingOutlined, ReloadOutlined,
  EditOutlined, SaveOutlined, ToolOutlined,
} from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import { pipelineApi, type PipelineStatus, type PipelineStreamEvent } from '@/services/pipeline'
import { generatorApi } from '@/services/api'
import api from '@/services/api'
import { MarkdownRenderer } from '@/utils/markdown'
import { canUsePipelineWorkbench, canUseProductPortal, saveLastPortalPath, useAuthStore } from '@/stores/auth'
import {
  AGENT_COLORS, STAGE_ICONS, STAGE_NAMES, STAGE_KEYS, PRODUCT_STAGE_KEYS,
  appendLiveOutput, renderSafeOutput, confirmActionLabel, confirmDescription,
  PipelineHistoryList, STAGE_AGENT_MAP, createPipelineShell,
  PMQualityPanel, PreviewQualityPanel, styles,
} from './pipelineHelpers'

const { TextArea } = Input
const { Title, Text, Paragraph } = Typography

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
  const [rollbackModalVisible, setRollbackModalVisible] = useState(false)
  const [rollbackStage, setRollbackStage] = useState<string | undefined>(undefined)
  const [showCreate, setShowCreate] = useState(!initialId)

  // pipelineId 变化时同步 URL 和 localStorage
  useEffect(() => {
    if (pipelineId) {
      setSearchParams({ id: pipelineId })
      localStorage.setItem('lastPipelineId', pipelineId)
    }
  }, [pipelineId])
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
  const [sandboxPreviewUrl, setSandboxPreviewUrl] = useState('')
  const [sandboxPreviewLoading, setSandboxPreviewLoading] = useState(false)
  const [editingStage, setEditingStage] = useState('')
  const [editedStageOutput, setEditedStageOutput] = useState('')
  const [stageOutputSaving, setStageOutputSaving] = useState(false)
  const streamAbortRef = useRef<AbortController | null>(null)
  const streamReconnectKeyRef = useRef('')
  // Streaming chunks can arrive dozens of times per second. Writing each one
  // straight to state re-renders the whole page per chunk (jank). Buffer them
  // and flush on a short interval instead — ~12 fps is smooth for streaming
  // text and cuts re-render count by an order of magnitude.
  const pendingChunksRef = useRef<Record<string, string>>({})
  const chunkFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isProductOnlyFlow = canUseProductPortal(user) && !canUsePipelineWorkbench(user)

  useEffect(() => {
    saveLastPortalPath(user, '/pipeline/development')
  }, [user])

  useEffect(() => {
    return () => {
      streamAbortRef.current?.abort()
      if (chunkFlushTimerRef.current) clearTimeout(chunkFlushTimerRef.current)
    }
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
      if (['waiting_confirm', 'completed', 'failed', 'cancelled', 'needs_human'].includes(data.status)) {
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
      const list = res || []
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

  const handleStartSandboxPreview = async () => {
    if (!pipelineId) return
    setSandboxPreviewLoading(true)
    try {
      const data = await pipelineApi.startSandboxPreview(pipelineId)
      const cookiePath = `/api/flow/pipeline/${pipelineId}/sandbox-preview/`
      document.cookie = `sandbox_preview_token_${pipelineId}=${encodeURIComponent(data.preview_token)}; path=${cookiePath}; SameSite=Lax`
      const url = `${data.preview_url}?preview_token=${encodeURIComponent(data.preview_token)}&_preview_ts=${Date.now()}`
      setSandboxPreviewUrl('')
      setSandboxPreviewUrl(url)
      message.success('真实前端预览已启动')
    } catch (e: any) {
      message.error(e?.message || '真实预览启动失败')
    } finally {
      setSandboxPreviewLoading(false)
    }
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

  // Drain buffered streaming chunks into state in a single update.
  const flushPendingChunks = useCallback(() => {
    chunkFlushTimerRef.current = null
    const pending = pendingChunksRef.current
    if (!pending || !Object.keys(pending).length) return
    pendingChunksRef.current = {}
    setStreamOutputByStage((prev) => {
      const next = { ...prev }
      for (const stageKey of Object.keys(pending)) {
        next[stageKey] = appendLiveOutput(next[stageKey] || '', pending[stageKey])
      }
      return next
    })
  }, [])

  const scheduleChunkFlush = useCallback(() => {
    if (chunkFlushTimerRef.current != null) return
    chunkFlushTimerRef.current = setTimeout(flushPendingChunks, 80)
  }, [flushPendingChunks])

  const applyStreamEvent = useCallback((event: PipelineStreamEvent) => {
    if (event.type === 'heartbeat') return

    if (event.stage) {
      setStreamingStage(event.stage)
    }

    if ((event.type === 'stage_started' || event.type === 'stage_retry') && event.stage) {
      flushPendingChunks()
      setExecutionActive(true)
      const stageKey = event.stage as string
      setStreamOutputByStage({ [stageKey]: '' })
      setPipeline((prev) => {
        if (!prev) {
          return createPipelineShell(
            event.pipeline_id || pipelineId || '',
            userRequest,
            stageKey,
          )
        }
        const stage = prev.stages?.[stageKey]
        if (!stage) return { ...prev, status: 'running', current_stage: stageKey }
        return {
          ...prev,
          status: 'running',
          current_stage: stageKey,
          stages: {
            ...prev.stages,
            [stageKey]: { ...stage, status: 'running', output: '' },
          },
        }
      })
      return
    }

    if (event.type === 'chunk' && event.stage && event.content) {
      const stageKey = event.stage
      setExecutionActive(true)
      // Buffer the chunk; flush to state on a throttle (see flushPendingChunks).
      // We deliberately do NOT mirror the output into `pipeline` per chunk —
      // the live <pre> reads streamOutputByStage, and the final output arrives
      // via the stage_completed event (or a server refresh on reconnect), so a
      // per-chunk pipeline update would only force the whole page to re-render.
      pendingChunksRef.current[stageKey] =
        (pendingChunksRef.current[stageKey] || '') + (event.content || '')
      scheduleChunkFlush()
      return
    }

    if (event.type === 'stage_completed' && event.stage) {
      flushPendingChunks()
      const stageKey = event.stage
      setStreamOutputByStage((prev) => {
        const next = { ...prev }
        delete next[stageKey]
        return next
      })
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

    if (['waiting_confirm', 'completed', 'failed', 'needs_human', 'done', 'error'].includes(event.type)) {
      setExecutionActive(false)
      streamReconnectKeyRef.current = ''
      if ((event.type === 'failed' || event.type === 'error') && event.stage) {
        setStreamOutputByStage((prev) => {
          const next = { ...prev }
          delete next[event.stage as string]
          return next
        })
      }
    }
  }, [pipelineId, userRequest, flushPendingChunks, scheduleChunkFlush])

  const runPipelineStream = useCallback(async (targetId: string, input = '') => {
    streamAbortRef.current?.abort()
    const controller = new AbortController()
    streamAbortRef.current = controller
    setExecutionActive(true)
    setStreamOutputByStage({})
    setPipeline((prev) => {
      const stageKey = prev?.current_stage
      if (!prev || !stageKey || !prev.stages?.[stageKey]) return prev
      return {
        ...prev,
        status: 'running',
        stages: {
          ...prev.stages,
          [stageKey]: {
            ...prev.stages[stageKey],
            status: 'running',
            output: '',
          },
        },
      }
    })
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
  }, [applyStreamEvent, pipeline?.current_stage, refreshStatus])

  useEffect(() => {
    if (!pipelineId || !pipeline || pipeline.status !== 'running') return
    if (streamAbortRef.current) return

    const reconnectKey = `${pipelineId}:${pipeline.current_stage}`
    if (streamReconnectKeyRef.current === reconnectKey) return
    streamReconnectKeyRef.current = reconnectKey

    runPipelineStream(pipelineId).catch(() => {
      streamReconnectKeyRef.current = ''
    })
  }, [pipelineId, pipeline?.status, pipeline?.current_stage, runPipelineStream])

  const handleCreate = async () => {
    if (!userRequest.trim()) {
      message.warning('请输入需求描述')
      return
    }
    setLoading(true)
    try {
      let matchedSkill = null as Awaited<ReturnType<typeof pipelineApi.matchProjectSkill>> | null
      if (isProductOnlyFlow) {
        message.loading({ content: '正在匹配项目 Skill...', key: 'pipeline-create' })
        matchedSkill = await pipelineApi.matchProjectSkill({ user_request: userRequest.trim() })
        message.success({
          content: `已匹配项目：${matchedSkill.skill.project_name || matchedSkill.skill.project_id}`,
          key: 'pipeline-create',
        })
      }

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
      const matchedProjectId = matchedSkill ? String(matchedSkill.skill.project_id) : ''
      const data = await pipelineApi.create({
        user_request: userRequest.trim(),
        project_id: matchedProjectId,
        project_name: '',
        backend_project_id: isProductOnlyFlow ? '' : backendProjectId || '',
        frontend_project_id: isProductOnlyFlow ? matchedProjectId : frontendProjectId || '',
        backend_tech: isProductOnlyFlow ? '' : backendProj ? `${backendProj.language}/${backendProj.framework}` : '',
        frontend_tech: isProductOnlyFlow && matchedSkill
          ? [matchedSkill.skill.language, matchedSkill.skill.framework].filter(Boolean).join('/')
          : frontendProj ? `${frontendProj.language}/${frontendProj.framework}` : '',
        pipeline_mode: isProductOnlyFlow ? 'frontend_contract_review' : undefined,
        skill_config: matchedSkill
          ? {
              ...(skillConfig || {}),
              entry: 'product_pipeline',
              auto_matched: true,
              match_source: matchedSkill.match_source,
              match_reason: matchedSkill.match_reason,
              match_confidence: matchedSkill.confidence,
              project_skill: {
                project_id: matchedSkill.skill.project_id,
                project_name: matchedSkill.skill.project_name,
                skill_version: matchedSkill.skill.skill_version,
                confirmed_at: matchedSkill.skill.confirmed_at,
              },
            }
          : skillConfig,
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
      if (result?.error) {
        throw new Error(result.error)
      }
      message.success(result?.status === 'completed' ? '流水线执行完成' : confirmed ? '已确认，推进下一阶段' : '已退回，正在重新执行')
      setFeedback('')
      await refreshStatus()
      if (result?.status === 'completed') {
        return
      }
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

  const handleRejectAndRerunCurrentStage = async () => {
    setSelectedStage('')
    await handleConfirm(false)
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

  const handleRollbackToStage = async (stage: string) => {
    if (!pipelineId) return
    setLoading(true)
    try {
      await pipelineApi.rollback(pipelineId, stage, feedback)
      message.success(`已回退到${STAGE_NAMES[stage] || stage}，将按修改意见重新执行`)
      setSelectedStage('')
      setRollbackModalVisible(false)
      setRollbackStage(undefined)
      await refreshStatus(pipelineId)
      await runPipelineStream(pipelineId, feedback)
      setFeedback('')
    } catch (e: any) {
      message.error(e?.message || '回退失败')
      await refreshStatus(pipelineId)
    } finally {
      setLoading(false)
    }
  }

  const startEditStageOutput = () => {
    if (!activeStageKey) return
    setEditingStage(activeStageKey)
    setEditedStageOutput(String(liveStageOutput || ''))
  }

  const cancelEditStageOutput = () => {
    setEditingStage('')
    setEditedStageOutput('')
  }

  const saveStageOutput = async () => {
    if (!pipelineId || !editingStage) return
    setStageOutputSaving(true)
    try {
      // needs_human 下人工介入保存：跳过可运行性强校验，允许人工覆盖后继续
      await pipelineApi.updateStageOutput(pipelineId, editingStage, editedStageOutput, isNeedsHuman)
      message.success('已保存当前阶段内容')
      setStreamOutputByStage((prev) => {
        const next = { ...prev }
        delete next[editingStage]
        return next
      })
      setEditingStage('')
      setEditedStageOutput('')
      await refreshStatus(pipelineId)
    } catch (e: any) {
      message.error(e?.message || '保存失败')
    } finally {
      setStageOutputSaving(false)
    }
  }

  const handleResume = async (action: 'approve' | 'retry') => {
    if (!pipelineId) return
    setLoading(true)
    try {
      const res = await pipelineApi.resume(pipelineId, action, feedback)
      if (res?.error) {
        message.error(res.error)
        return
      }
      message.success(action === 'approve' ? '已通过并推进到下一阶段' : '已退回，将重新生成')
      setFeedback('')
      setSelectedStage('')
      await refreshStatus(pipelineId)
      // 推进/重生成后，触发下一阶段执行（watcher 或前端驱动）
      await runPipelineStream(pipelineId, action === 'retry' ? feedback : undefined)
    } catch (e: any) {
      message.error(e?.message || '恢复失败')
      await refreshStatus(pipelineId)
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
    if (stage.status === 'failed' || stage.status === 'needs_human') return 'error'
    return 'wait'
  }

  const isWaitingConfirm = pipeline?.status === 'waiting_confirm'
  const isNeedsHuman = pipeline?.status === 'needs_human'

  // Active stage key: use selectedStage if set, otherwise current stage
  const activeStageKey = selectedStage || pipeline?.current_stage || ''
  const currentStage = pipeline?.stages?.[activeStageKey]
  const isViewingCurrent = activeStageKey === pipeline?.current_stage
  const hasLiveStageOutput = isViewingCurrent && Object.prototype.hasOwnProperty.call(streamOutputByStage, activeStageKey)
  const liveStageOutput = hasLiveStageOutput ? streamOutputByStage[activeStageKey] : currentStage?.output || ''
  const isLiveStreamingOutput = hasLiveStageOutput && executionActive && isViewingCurrent
  const isEditingStageOutput = editingStage === activeStageKey
  const pmQuality = activeStageKey === 'requirement'
    ? currentStage?.structured_output?.pm_quality
    : activeStageKey === 'page_design'
      ? currentStage?.structured_output?.design_quality
      : undefined
  const previewQuality = ['ui_preview', 'prototype'].includes(activeStageKey)
    ? currentStage?.structured_output?.preview_quality
    : undefined

  // Strip markdown/prg code block wrappers for text stages
  const displayOutput = useMemo(() => {
    if (!liveStageOutput) return ''
    const raw = renderSafeOutput(String(liveStageOutput))
    // If this is a code-heavy stage, return as-is
    if (['development', 'testing', 'code_review'].includes(activeStageKey)) return raw
    // Strip ```markdown, ```prg, ```md wrappers
    const stripped = raw.replace(/^```(?:markdown|prg|md)\s*\n?/i, '').replace(/\n?```\s*$/i, '')
    return stripped
  }, [liveStageOutput, activeStageKey])

  const isRunning = pipeline?.status === 'running' || executionActive
  const isCompleted = pipeline?.status === 'completed'
  const isFailed = pipeline?.status === 'failed'
  const visibleStageKeys = pipeline?.pipeline_mode === 'frontend_contract_review' ? PRODUCT_STAGE_KEYS : STAGE_KEYS
  const canRollbackActiveStage = Boolean(
    pipelineId &&
    currentStage?.status === 'completed' &&
    visibleStageKeys.includes(activeStageKey) &&
    visibleStageKeys.indexOf(activeStageKey) <= visibleStageKeys.indexOf(pipeline?.current_stage || activeStageKey)
  )
  const rollbackStageOptions = useMemo(() => {
    if (!pipeline) return []
    const stageKeys = pipeline.pipeline_mode === 'frontend_contract_review' ? PRODUCT_STAGE_KEYS : STAGE_KEYS
    const currentIdx = stageKeys.indexOf(pipeline.current_stage || '')
    return stageKeys
      .filter((key) => {
        const stage = pipeline.stages?.[key]
        const idx = stageKeys.indexOf(key)
        return stage?.status === 'completed' && (currentIdx === -1 || idx <= currentIdx)
      })
      .map((key) => ({ label: STAGE_NAMES[key] || key, value: key }))
  }, [pipeline])

  const openRollbackModal = () => {
    const preferred = canRollbackActiveStage ? activeStageKey : rollbackStageOptions[rollbackStageOptions.length - 1]?.value
    setRollbackStage(preferred)
    setRollbackModalVisible(true)
  }

  useEffect(() => {
    setEditingStage('')
    setEditedStageOutput('')
  }, [activeStageKey])

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
              {isProductOnlyFlow
                ? '描述产品需求，系统会自动匹配项目 Skill，并生成需求文档、前端预览、代码和审查结果'
                : '描述你的需求，AI Agent 团队将自动完成从需求分析到部署的完整开发流程'}
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

            {isProductOnlyFlow ? (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 12, borderRadius: 8 }}
                message="产品模式"
                description="提交需求后自动匹配最相关的项目 Skill，用于生成需求文档、前端预览、代码和自动审查。"
              />
            ) : (
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
            )}
            {!isProductOnlyFlow && ((backendProjectId && projects.find(p => String(p.id) === backendProjectId)) ||
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
  const completedStages = visibleStageKeys.filter(
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
            {isNeedsHuman && <ToolOutlined style={{ fontSize: 11 }} />}
            {isNeedsHuman ? '待人工处理' : pipeline.status}
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
          {isWaitingConfirm && (
            <Tooltip title={`驳回当前${STAGE_NAMES[pipeline.current_stage] || pipeline.current_stage || '阶段'}并重新生成，可先在当前阶段下方填写修改意见`}>
              <Button
                size="small"
                type="primary"
                danger
                icon={<ReloadOutlined />}
                onClick={handleRejectAndRerunCurrentStage}
                loading={loading}
                style={{ borderRadius: 6 }}
              >
                重新生成当前阶段
              </Button>
            </Tooltip>
          )}
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
          <Tooltip title={isRunning ? '当前正在执行，阶段结束后可以回退重做' : '选择已完成阶段并重新执行该阶段及后续阶段'}>
            <Button
              size="small"
              icon={<RollbackOutlined />}
              onClick={openRollbackModal}
              disabled={isRunning || rollbackStageOptions.length === 0}
              style={{ borderRadius: 6 }}
            >
              回退重做
            </Button>
          </Tooltip>
        </Space>
      </div>

      {/* ---- Stage Tracker + Content ---- */}
      <div className="pipeline-stage-layout" style={styles.stageTrackerRow}>
        {/* Sidebar: Vertical Stage Tracker */}
        <div className="pipeline-stage-sidebar" style={styles.stageTrackSidebar}>
          {visibleStageKeys.map((key, idx) => {
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
                isViewingCurrent && isNeedsHuman ? 'needs_human' :
                isViewingCurrent && isWaitingConfirm ? 'waiting_confirm' :
                currentStage?.status === 'completed' ? 'completed' :
                currentStage?.status === 'failed' ? 'failed' : 'pending'
              )}>
                {isViewingCurrent && isRunning ? '执行中' :
                 isViewingCurrent && isNeedsHuman ? '待人工' :
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

              {canRollbackActiveStage && (
                <div style={{
                  padding: 14,
                  marginBottom: 16,
                  background: 'rgba(245, 158, 11, 0.08)',
                  border: '1px solid rgba(245, 158, 11, 0.2)',
                  borderRadius: 10,
                }}>
                  <TextArea
                    rows={3}
                    placeholder={`输入修改意见，回退到${STAGE_NAMES[activeStageKey] || activeStageKey}后会重新执行该阶段及后续阶段`}
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    style={{ marginBottom: 10, borderRadius: 8 }}
                  />
                  <Button
                    icon={<RollbackOutlined />}
                    loading={loading}
                    onClick={() => handleRollbackToStage(activeStageKey)}
                    style={{ borderRadius: 8 }}
                  >
                    回退到此阶段重做
                  </Button>
                </div>
              )}

              {/* Output */}
              {liveStageOutput && (!loading || executionActive) && (
                <div style={styles.outputContainer}>
                  <div style={styles.outputHeader}>
                    <span style={styles.outputLabel}>{isEditingStageOutput ? 'EDITING' : 'OUTPUT'}</span>
                    <Space size={8}>
                      {isEditingStageOutput ? (
                        <>
                          <Button
                            size="small"
                            icon={<SaveOutlined />}
                            type="primary"
                            loading={stageOutputSaving}
                            onClick={saveStageOutput}
                            style={{ borderRadius: 6, fontSize: 12 }}
                          >
                            保存修改
                          </Button>
                          <Button
                            size="small"
                            onClick={cancelEditStageOutput}
                            disabled={stageOutputSaving}
                            style={{ borderRadius: 6, fontSize: 12 }}
                          >
                            取消
                          </Button>
                        </>
                      ) : (
                        <Button
                          size="small"
                          icon={<EditOutlined />}
                          onClick={startEditStageOutput}
                          disabled={isRunning}
                          style={{ borderRadius: 6, fontSize: 12 }}
                        >
                          编辑内容
                        </Button>
                      )}
                    </Space>
                  </div>
                  {isEditingStageOutput ? (
                    <TextArea
                      value={editedStageOutput}
                      onChange={(e) => setEditedStageOutput(e.target.value)}
                      autoSize={{ minRows: 12, maxRows: 28 }}
                      style={{
                        borderRadius: 8,
                        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                        fontSize: 12,
                        lineHeight: 1.6,
                      }}
                    />
                  ) : (
                    isLiveStreamingOutput ? (
                      <pre style={{
                        margin: 0,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                        fontSize: 12,
                        lineHeight: 1.65,
                      }}>
                        {displayOutput}
                      </pre>
                    ) : (
                      <MarkdownRenderer content={displayOutput} className="pipeline-markdown" />
                    )
                  )}
                </div>
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

              {pipelineId && (
                <div style={{ marginBottom: 16 }}>
                  <Text style={{ display: 'block', marginBottom: 8, color: '#64748b', fontSize: 12 }}>
                    真实前端预览会把生成代码写入匹配前端项目的沙箱副本，并使用该项目的 npm 脚本启动。
                  </Text>
                  <Space wrap>
                    <Button
                      type="primary"
                      icon={<EyeOutlined />}
                      loading={sandboxPreviewLoading}
                      onClick={handleStartSandboxPreview}
                      style={{
                        borderRadius: 8,
                        background: '#2563eb',
                        borderColor: '#2563eb',
                      }}
                    >
                      启动真实前端预览
                    </Button>
                    {sandboxPreviewUrl && (
                      <Button
                        icon={<EyeOutlined />}
                        onClick={() => window.open(sandboxPreviewUrl, '_blank')}
                        style={{ borderRadius: 8 }}
                      >
                        新窗口打开真实预览
                      </Button>
                    )}
                  </Space>
                  {sandboxPreviewUrl && (
                    <div
                      style={{
                        width: '100%',
                        overflow: 'auto',
                        marginTop: 12,
                        border: '1px solid rgba(148, 163, 184, 0.28)',
                        borderRadius: 8,
                        background: '#f8fafd',
                      }}
                    >
                      <iframe
                        src={sandboxPreviewUrl}
                        style={{
                          display: 'block',
                          width: '1280px',
                          maxWidth: 'none',
                          height: 720,
                          border: 0,
                          background: '#fff',
                        }}
                        sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
                        title="真实前端预览"
                      />
                    </div>
                  )}
                </div>
              )}

              {/* Confirm Panel - only when viewing current stage */}
              {isWaitingConfirm && isViewingCurrent && (
                <div style={styles.confirmPanel}>
                  <Alert
                    message={`请确认${STAGE_NAMES[activeStageKey] || activeStageKey || '当前阶段'}输出是否符合预期`}
                    description={confirmDescription(activeStageKey)}
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
                      {confirmActionLabel(activeStageKey)}
                    </Button>
                    <Button
                      danger
                      icon={<CloseCircleOutlined />}
                      onClick={handleRejectAndRerunCurrentStage}
                      loading={loading}
                      style={{ borderRadius: 8 }}
                    >
                      驳回修改并重新生成
                    </Button>
                  </div>
                </div>
              )}

              {/* Needs Human Panel — 重试耗尽，暂停交人工 */}
              {isNeedsHuman && isViewingCurrent && (() => {
                const review: any = (currentStage as any)?.human_review || {}
                const issues: string[] = review.issues || []
                const fileHints: string[] = review.file_hints || []
                const lineHints: string[] = review.line_hints || []
                return (
                  <div style={styles.failPanel}>
                    <Alert
                      message={`待人工处理：${STAGE_NAMES[activeStageKey] || activeStageKey}自动重试 ${review.retry_count ?? 3} 次仍未通过`}
                      description={currentStage?.error || review.reason || '请人工修改后继续'}
                      type="warning"
                      showIcon
                      style={{
                        marginBottom: 14,
                        background: 'rgba(234, 88, 12, 0.10)',
                        border: '1px solid rgba(234, 88, 12, 0.28)',
                        borderRadius: 8,
                      }}
                    />
                    {(issues.length > 0 || fileHints.length > 0) && (
                      <div style={{ marginBottom: 12, padding: 12, background: 'rgba(148,163,184,0.06)', borderRadius: 8 }}>
                        {issues.map((it, i) => (
                          <div key={`i-${i}`} style={{ color: 'rgba(255,255,255,0.78)', fontSize: 13, marginBottom: 4 }}>
                            • {it}
                          </div>
                        ))}
                        {fileHints.map((f, i) => (
                          <div key={`f-${i}`} style={{ color: '#f59e0b', fontSize: 12, fontFamily: 'monospace', marginTop: 4 }}>
                            📄 {f}{lineHints[i] ? ` — ${lineHints[i]}` : ''}
                          </div>
                        ))}
                      </div>
                    )}
                    <Text style={{ display: 'block', color: 'rgba(255,255,255,0.55)', fontSize: 12, marginBottom: 8 }}>
                      可点上方「编辑内容」修改产物后通过，或带反馈重新生成。
                    </Text>
                    <TextArea
                      rows={2}
                      placeholder="重新生成的修订意见（可选）..."
                      value={feedback}
                      onChange={(e) => setFeedback(e.target.value)}
                      style={{ marginBottom: 10, borderRadius: 8 }}
                    />
                    <div style={styles.confirmPanelActions}>
                      <Button
                        type="primary"
                        icon={<CheckCircleOutlined />}
                        onClick={() => handleResume('approve')}
                        loading={loading}
                        style={{ borderRadius: 8 }}
                      >
                        人工通过并继续
                      </Button>
                      <Button
                        icon={<ReloadOutlined />}
                        onClick={() => handleResume('retry')}
                        loading={loading}
                        style={{ borderRadius: 8 }}
                      >
                        带反馈重新生成
                      </Button>
                    </div>
                  </div>
                )
              })()}

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
                      onClick={openRollbackModal}
                      disabled={rollbackStageOptions.length === 0}
                      style={{ borderRadius: 8 }}
                    >
                      回退重做
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

      <Modal
        title="回退重做"
        open={rollbackModalVisible}
        okText="回退并重新执行"
        cancelText="取消"
        confirmLoading={loading}
        okButtonProps={{ disabled: !rollbackStage }}
        onCancel={() => setRollbackModalVisible(false)}
        onOk={() => rollbackStage && handleRollbackToStage(rollbackStage)}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div>
            <Text strong>回退阶段</Text>
            <Select
              value={rollbackStage}
              options={rollbackStageOptions}
              onChange={(value) => {
                setRollbackStage(value)
                setSelectedStage(value)
              }}
              placeholder="选择要回退的阶段"
              style={{ width: '100%', marginTop: 8 }}
            />
          </div>
          <div>
            <Text strong>修改意见</Text>
            <TextArea
              rows={4}
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="填写需要调整的内容，系统会从所选阶段重新执行后续流程"
              style={{ marginTop: 8, borderRadius: 8 }}
            />
          </div>
        </Space>
      </Modal>

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
          visibleStageKeys.map((key) => {
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
