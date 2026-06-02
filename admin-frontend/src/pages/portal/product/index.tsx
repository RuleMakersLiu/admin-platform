import { Fragment, useEffect, useRef, useState } from 'react'
import { Alert, Button, Collapse, Empty, Input, List, Modal, Radio, Space, Steps, Tag, Typography, message } from 'antd'
import {
  CheckCircleOutlined,
  CodeOutlined,
  DownloadOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  FullscreenOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  RocketOutlined,
} from '@ant-design/icons'
import { pipelineApi, type PipelineArtifact, type PipelineListItem, type PipelineStatus, type ProjectSkillMatch } from '@/services/pipeline'
import { saveLastPortalPath, useAuthStore } from '@/stores/auth'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

const stageLabel: Record<string, string> = {
  requirement: '需求分析',
  page_design: '页面设计',
  prototype: '前端预览代码',
  delivery: 'API 契约',
  frontend_dev: '前端代码',
  code_review: '自动审查',
  report: '报告',
}

const stageOrder = ['requirement', 'page_design', 'prototype', 'delivery', 'code_review', 'report']
const LAST_PRODUCT_PIPELINE_ID = 'lastProductPipelineId'

const formatMatchSource = (source: string) => {
  const sourceLabels: Record<string, string> = {
    llm: '大模型分析',
    rule: '规则匹配',
    backend_role_rule: '后端角色匹配',
    backend_project_group: '后端项目组',
  }
  return sourceLabels[source] || '项目规则匹配'
}

const getMatchSourceColor = (source: string) => {
  const sourceColors: Record<string, string> = {
    llm: 'blue',
    rule: 'gold',
    backend_role_rule: 'cyan',
    backend_project_group: 'purple',
  }
  return sourceColors[source] || 'geekblue'
}

export default function ProductPortal() {
  const { user } = useAuthStore()
  const [requirement, setRequirement] = useState('')
  const [running, setRunning] = useState(false)
  const [pipelineId, setPipelineId] = useState('')
  const [status, setStatus] = useState<PipelineStatus | null>(null)
  const [artifact, setArtifact] = useState<PipelineArtifact | null>(null)
  const [matchedSkill, setMatchedSkill] = useState<ProjectSkillMatch | null>(null)
  const [matchedRequirement, setMatchedRequirement] = useState('')
  const [selectedPagePath, setSelectedPagePath] = useState('')
  const [logs, setLogs] = useState<string[]>([])
  const [currentStage, setCurrentStage] = useState('')
  const [streamOutputByStage, setStreamOutputByStage] = useState<Record<string, string>>({})
  const [awaitingConfirmStage, setAwaitingConfirmStage] = useState('')
  const [feedback, setFeedback] = useState('')
  const [pipelines, setPipelines] = useState<PipelineListItem[]>([])
  const [pipelineListLoading, setPipelineListLoading] = useState(false)
  const [sandboxPreviewUrl, setSandboxPreviewUrl] = useState('')
  const [sandboxPreviewLoading, setSandboxPreviewLoading] = useState(false)
  const autoResumeKeyRef = useRef('')
  const streamActiveRef = useRef(false)

  useEffect(() => {
    saveLastPortalPath(user, '/pipeline/development')
  }, [user])

  const loadPipelines = async () => {
    setPipelineListLoading(true)
    try {
      const list = await pipelineApi.list()
      setPipelines((list || []).filter((item: PipelineListItem) => item.user_request))
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : '加载流水线列表失败')
    } finally {
      setPipelineListLoading(false)
    }
  }

  useEffect(() => {
    loadPipelines()
  }, [])

  const appendLog = (line: string) => {
    setLogs((prev) => [line, ...prev].slice(0, 80))
  }

  const appendStreamOutput = (stage: string, content: string) => {
    if (!stage || !content) return
    setStreamOutputByStage((prev) => ({
      ...prev,
      [stage]: `${prev[stage] || ''}${content}`.slice(-20000),
    }))
  }

  const refreshOutputs = async (id: string) => {
    const [nextStatus, nextArtifact] = await Promise.all([
      pipelineApi.getStatus(id),
      pipelineApi.getArtifact(id),
    ])
    setStatus(nextStatus)
    setArtifact(nextArtifact)
    setCurrentStage(nextStatus.current_stage || '')
    setAwaitingConfirmStage(nextStatus.status === 'waiting_confirm' ? nextStatus.current_stage : '')
    if (nextStatus.status === 'running') {
      setRunning(true)
    }
    return nextStatus
  }

  const restorePipeline = async (id: string) => {
    setPipelineId(id)
    localStorage.setItem(LAST_PRODUCT_PIPELINE_ID, id)
    setMatchedSkill(null)
    setMatchedRequirement('')
    setSelectedPagePath('')
    setFeedback('')
      setStreamOutputByStage({})
      setSandboxPreviewUrl('')
    try {
      const nextStatus = await refreshOutputs(id)
      setRequirement(nextStatus.user_request || '')
      setRunning(nextStatus.status === 'running')
      setLogs((prev) => [`已切换到流水线：${id}`, ...prev].slice(0, 80))
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : '加载流水线失败')
    }
  }

  useEffect(() => {
    const lastId = localStorage.getItem(LAST_PRODUCT_PIPELINE_ID)
    if (lastId) {
      restorePipeline(lastId)
    }
  }, [])

  const runUntilPause = async (id: string, userInput = '') => {
    streamActiveRef.current = true
    setRunning(true)
    try {
      for (let i = 0; i < 16; i += 1) {
        await pipelineApi.executeStream(id, userInput, (event) => {
          if (event.type === 'stage_started' && event.stage) {
            setCurrentStage(event.stage)
            appendLog(`开始执行：${stageLabel[event.stage] || event.stage}`)
          }
          if (event.type === 'chunk' && event.stage && event.content) {
            setCurrentStage(event.stage)
            appendStreamOutput(event.stage, event.content)
          }
          if (event.type === 'stage_completed' && event.stage) {
            appendLog(`完成：${stageLabel[event.stage] || event.stage}`)
          }
          if (event.type === 'waiting_confirm' && event.stage) {
            setAwaitingConfirmStage(event.stage)
            setCurrentStage(event.stage)
            appendLog(`等待人工确认：${stageLabel[event.stage] || event.stage}`)
          }
          if (event.type === 'failed') {
            appendLog(`失败：${event.error || '未知错误'}`)
          }
        })
        userInput = ''

        const nextStatus = await refreshOutputs(id)
        setCurrentStage(nextStatus.current_stage || currentStage)
        if (nextStatus.status === 'waiting_confirm') {
          setAwaitingConfirmStage(nextStatus.current_stage)
          setRunning(false)
          return nextStatus
        }
        if (nextStatus.status === 'completed' || nextStatus.status === 'failed' || nextStatus.status === 'cancelled') {
          setRunning(false)
          return nextStatus
        }
      }
      return refreshOutputs(id)
    } finally {
      streamActiveRef.current = false
    }
  }

  useEffect(() => {
    if (!pipelineId || status?.status !== 'running' || streamActiveRef.current) return

    const resumeKey = `${pipelineId}:${status.current_stage}`
    if (autoResumeKeyRef.current === resumeKey) return
    autoResumeKeyRef.current = resumeKey

    setRunning(true)
    appendLog(`恢复执行：${stageLabel[status.current_stage] || status.current_stage}`)
    runUntilPause(pipelineId)
      .catch((error: unknown) => {
        autoResumeKeyRef.current = ''
        message.error(error instanceof Error ? error.message : '恢复执行失败')
        setRunning(false)
      })
  }, [pipelineId, status?.status, status?.current_stage])

  const resumePipeline = async (confirmed: boolean) => {
    if (!pipelineId) return
    setRunning(true)
    try {
      const note = feedback.trim()
      await pipelineApi.confirm(
        pipelineId,
        confirmed,
        note || (confirmed ? '人工确认通过，继续执行。' : '请按人工反馈调整后重新生成。'),
      )
      appendLog(`${confirmed ? '确认通过' : '退回调整'}：${stageLabel[awaitingConfirmStage] || awaitingConfirmStage}`)
      setAwaitingConfirmStage('')
      setFeedback('')
      const finalStatus = await runUntilPause(pipelineId, confirmed ? '' : note)
      if (finalStatus?.status === 'failed') {
        message.error('流水线执行失败，请查看阶段输出')
      } else if (finalStatus?.status === 'completed') {
        message.success('流水线执行完成')
      }
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : '继续执行失败')
      setRunning(false)
    }
  }

  const handleCreatePipeline = async () => {
    const trimmedRequirement = requirement.trim()
    if (!trimmedRequirement) {
      message.warning('请输入需求')
      return
    }

    setRunning(true)
    setLogs([])
    setArtifact(null)
    setStatus(null)
    setMatchedSkill(null)
    setCurrentStage('')
    setAwaitingConfirmStage('')
    setFeedback('')
    setStreamOutputByStage({})

    try {
      let match = matchedRequirement === trimmedRequirement ? matchedSkill : null
      if (!match) {
        appendLog('正在分析需求并匹配项目 Skill')
        match = await pipelineApi.matchProjectSkill({ user_request: trimmedRequirement })
        setMatchedSkill(match)
        setMatchedRequirement(trimmedRequirement)
        const pageCandidates = match.frontend_page_candidates?.candidates || []
        setSelectedPagePath(pageCandidates[0]?.path || '')
        appendLog(`已匹配前端项目：${match.skill.project_name || match.skill.project_id}（${formatMatchSource(match.match_source)}）`)
        if (match.frontend_page_candidates?.requires_selection) {
          if (pageCandidates.length) {
            message.info(match.frontend_page_candidates.uncertain ? '页面匹配不确定，请人工选择候选页面' : '已列出现有页面候选，请确认要修改的页面后再次执行')
          } else {
            message.warning('未找到与需求相关的现有页面候选，无法继续生成')
          }
          return
        }
      }
      const backendMatches = match.backend_matches || (match.backend_match ? [match.backend_match] : [])
      if (backendMatches.length) {
        appendLog(`已匹配后端项目组：${backendMatches.map(item => item.skill.project_name || item.skill.project_id).join('、')}`)
      }

      const projectId = String(match.skill.project_id)
      const backendProjectIds = backendMatches.map(item => String(item.skill.project_id))
      const backendProjectId = backendProjectIds[0] || ''
      const requiresPageSelection = Boolean(match.frontend_page_candidates?.requires_selection)
      const selectedCandidate = (match.frontend_page_candidates?.candidates || []).find(item => item.path === selectedPagePath)
      if (requiresPageSelection && !selectedPagePath) {
        message.error('这是现有功能改造，但没有可确认的现有页面候选；请先完善项目源码分析或 Project Skill')
        return
      }
      const created = await pipelineApi.create({
        user_request: trimmedRequirement,
        project_id: projectId,
        frontend_project_id: projectId,
        backend_project_id: backendProjectId,
        backend_project_ids: backendProjectIds,
        frontend_tech: [match.skill.language, match.skill.framework].filter(Boolean).join('/'),
        backend_tech: backendMatches.length
          ? backendMatches
              .map(item => [item.skill.language, item.skill.framework].filter(Boolean).join('/'))
              .filter(Boolean)
              .join(' + ')
          : undefined,
        pipeline_mode: 'frontend_contract_review',
        skill_config: {
          entry: 'product_portal',
          auto_matched: true,
          selected_frontend_page_path: selectedPagePath || undefined,
          selected_frontend_page_confidence: selectedCandidate?.confidence,
          match_source: match.match_source,
          match_reason: match.match_reason,
          match_confidence: match.confidence,
          project_skill: {
            project_id: match.skill.project_id,
            project_name: match.skill.project_name,
            skill_version: match.skill.skill_version,
            confirmed_at: match.skill.confirmed_at,
          },
          backend_project_skills: backendMatches.map(item => ({
            project_id: item.skill.project_id,
            project_name: item.skill.project_name,
            skill_version: item.skill.skill_version,
            confirmed_at: item.skill.confirmed_at,
            match_source: item.match_source,
            match_reason: item.match_reason,
            match_confidence: item.confidence,
          })),
          backend_project_skill: backendMatches[0] ? {
            project_id: backendMatches[0].skill.project_id,
            project_name: backendMatches[0].skill.project_name,
            skill_version: backendMatches[0].skill.skill_version,
            confirmed_at: backendMatches[0].skill.confirmed_at,
            match_source: backendMatches[0].match_source,
            match_reason: backendMatches[0].match_reason,
            match_confidence: backendMatches[0].confidence,
          } : undefined,
        },
      })
      setPipelineId(created.pipeline_id)
      localStorage.setItem(LAST_PRODUCT_PIPELINE_ID, created.pipeline_id)
      appendLog(`流水线已创建：${created.pipeline_id}`)
      loadPipelines()

      const finalStatus = await runUntilPause(created.pipeline_id)
      if (finalStatus?.status === 'failed') {
        throw new Error('流水线执行失败，请查看自动审查或阶段日志')
      }
      if (finalStatus?.status === 'completed') {
        message.success('流水线执行完成')
      } else if (finalStatus?.status === 'waiting_confirm') {
        message.info('已暂停，等待人工确认或调整')
      }
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : '流水线执行失败')
      setRunning(false)
    } finally {
      if (!awaitingConfirmStage) setRunning(false)
    }
  }

  const continueSelectedPipeline = async () => {
    if (!pipelineId) return
    setRunning(true)
    try {
      const note = feedback.trim()
      if (status?.status === 'failed') {
        const failedStage = status.current_stage || currentStage || 'prototype'
        await pipelineApi.rollback(
          pipelineId,
          failedStage,
          note || '当前阶段失败，请根据错误反馈重新生成并修复。',
        )
        appendLog(`重新生成：${stageLabel[failedStage] || failedStage}`)
        setFeedback('')
        setAwaitingConfirmStage('')
      }
      const finalStatus = await runUntilPause(pipelineId, note)
      loadPipelines()
      if (finalStatus?.status === 'failed') {
        message.error('流水线执行失败，请查看阶段输出')
      } else if (finalStatus?.status === 'completed') {
        message.success('流水线执行完成')
      }
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : '继续执行失败')
      setRunning(false)
    }
  }

  const deletePipeline = async (id: string) => {
    try {
      await pipelineApi.delete(id)
      message.success('已删除流水线')
      if (pipelineId === id) {
        setPipelineId('')
        localStorage.removeItem(LAST_PRODUCT_PIPELINE_ID)
        setStatus(null)
        setArtifact(null)
        setCurrentStage('')
        setAwaitingConfirmStage('')
        setStreamOutputByStage({})
        setSandboxPreviewUrl('')
      }
      loadPipelines()
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : '删除失败')
    }
  }

  const handleDownloadFrontend = async () => {
    if (!pipelineId) return
    if (!Object.keys(artifact?.frontend_files || {}).length) {
      message.info('前端代码还没有生成，等“前端代码”阶段完成后再下载')
      return
    }
    try {
      await pipelineApi.downloadFrontend(pipelineId)
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : '下载失败')
    }
  }

  const handleStartSandboxPreview = async () => {
    if (!pipelineId) return
    if (!Object.keys(artifact?.frontend_files || {}).length) {
      message.info('前端代码还没有生成，等“前端代码”阶段完成后再启动真实预览')
      return
    }
    setSandboxPreviewLoading(true)
    try {
      const data = await pipelineApi.startSandboxPreview(pipelineId)
      const cookiePath = `/api/flow/pipeline/${pipelineId}/sandbox-preview/`
      document.cookie = `sandbox_preview_token_${pipelineId}=${encodeURIComponent(data.preview_token)}; path=${cookiePath}; SameSite=Lax`
      setSandboxPreviewUrl('')
      setSandboxPreviewUrl(`${data.preview_url}?preview_token=${encodeURIComponent(data.preview_token)}&_preview_ts=${Date.now()}`)
      appendLog('真实前端预览已启动')
      message.success('真实前端预览已启动')
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : '真实预览启动失败')
    } finally {
      setSandboxPreviewLoading(false)
    }
  }

  const fileItems = Object.entries(artifact?.frontend_files || {}).map(([path, content]) => ({
    key: path,
    label: path,
    children: <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 12 }}>{content}</pre>,
  }))

  const activeStage = currentStage || status?.current_stage || ''
  const stageItems = stageOrder.map((stage) => {
    const stageStatus = status?.stages?.[stage]?.status
    return {
      title: stageLabel[stage] || stage,
      status: stageStatus === 'completed'
        ? 'finish' as const
        : stageStatus === 'failed'
          ? 'error' as const
          : stage === activeStage || stageStatus === 'running'
            ? 'process' as const
            : 'wait' as const,
    }
  })
  const streamItems = stageOrder
    .filter((stage) => streamOutputByStage[stage] || status?.stages?.[stage]?.output)
    .map((stage) => ({
      key: stage,
      label: stageLabel[stage] || stage,
      children: (
        <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 12, maxHeight: 360, overflow: 'auto' }}>
          {streamOutputByStage[stage] || status?.stages?.[stage]?.output || ''}
        </pre>
      ),
    }))

  return (
    <div className="workbench-page">
      <Space align="start" className="workbench-title-row workbench-title-row-between">
        <div>
          <Title level={3} style={{ margin: 0 }}>需求开发</Title>
          <Text type="secondary">输入产品需求后自动匹配已确认项目 Skill，并生成预览、前端代码、API 契约和审查结果。</Text>
        </div>
      </Space>

      <div className="workbench-grid">
        <div className="workbench-card" style={{ background: '#fff', border: '1px solid #e5eaf3', borderRadius: 8, padding: 20 }}>
          <Space style={{ marginBottom: 12 }}>
            <FileSearchOutlined />
            <Title level={4} style={{ margin: 0 }}>输入需求</Title>
          </Space>

          <TextArea
            rows={12}
            value={requirement}
            onChange={(event) => {
              const nextValue = event.target.value
              setRequirement(nextValue)
              if (matchedRequirement && nextValue.trim() !== matchedRequirement) {
                setMatchedSkill(null)
                setMatchedRequirement('')
                setSelectedPagePath('')
              }
            }}
            placeholder="描述产品需求、页面目标、核心字段、权限点和验收标准"
          />

          {matchedSkill && (
            <Alert
              type="success"
              showIcon
              style={{ marginTop: 12 }}
              message="已匹配项目"
              description={
                <Space direction="vertical" size={4}>
                  <Text>
                    前端：{matchedSkill.skill.project_name || matchedSkill.skill.project_id} · {' '}
                    {matchedSkill.skill.language || 'unknown'} / {matchedSkill.skill.framework || 'unknown'}
                    <Tag style={{ marginLeft: 8 }}>v{matchedSkill.skill.skill_version}</Tag>
                    <Tag color={getMatchSourceColor(matchedSkill.match_source)}>{formatMatchSource(matchedSkill.match_source)}</Tag>
                    <Tag color="green">{Math.round(matchedSkill.confidence * 100)}%</Tag>
                  </Text>
                  <Text>{matchedSkill.match_reason}</Text>
                  {matchedSkill.frontend_page_candidates?.requires_selection && (
                    <Alert
                      type={selectedPagePath ? 'info' : 'warning'}
                      showIcon
                      message={matchedSkill.frontend_page_candidates.uncertain ? '页面匹配不确定，请人工选择' : '选择要修改的现有页面'}
                      description={
                        (matchedSkill.frontend_page_candidates.candidates || []).length ? (
                          <Radio.Group
                            value={selectedPagePath}
                            onChange={(event) => setSelectedPagePath(event.target.value)}
                            style={{ width: '100%' }}
                          >
                            <Space direction="vertical" style={{ width: '100%' }}>
                              {(matchedSkill.frontend_page_candidates.candidates || []).slice(0, 5).map((candidate) => (
                                <Radio key={candidate.path} value={candidate.path}>
                                  <Space wrap size={6}>
                                    <Text code>{candidate.path}</Text>
                                    <Tag color={candidate.confidence >= 0.75 ? 'green' : candidate.confidence >= 0.55 ? 'gold' : 'orange'}>
                                      {Math.round(candidate.confidence * 100)}%
                                    </Tag>
                                    {(candidate.uncertain || matchedSkill.frontend_page_candidates?.uncertain) && (
                                      <Tag color="orange">低置信</Tag>
                                    )}
                                    {candidate.matched_terms?.slice(0, 4).map((term) => (
                                      <Tag key={term}>{term}</Tag>
                                    ))}
                                    <Text type="secondary">{candidate.reason}</Text>
                                  </Space>
                                </Radio>
                              ))}
                            </Space>
                          </Radio.Group>
                        ) : (
                          <Text type="warning">
                            未找到与需求相关的现有页面候选。系统不会新建页面冒充现有功能改造。
                          </Text>
                        )
                      }
                    />
                  )}
                  {(matchedSkill.backend_matches || (matchedSkill.backend_match ? [matchedSkill.backend_match] : [])).map((backendMatch) => (
                    <Fragment key={backendMatch.skill.project_id}>
                      <Text>
                        后端：{backendMatch.skill.project_name || backendMatch.skill.project_id} · {' '}
                        {backendMatch.skill.language || 'unknown'} / {backendMatch.skill.framework || 'unknown'}
                        <Tag style={{ marginLeft: 8 }}>v{backendMatch.skill.skill_version}</Tag>
                        <Tag color={getMatchSourceColor(backendMatch.match_source)}>{formatMatchSource(backendMatch.match_source)}</Tag>
                        <Tag color="green">{Math.round(backendMatch.confidence * 100)}%</Tag>
                      </Text>
                      <Text>{backendMatch.match_reason}</Text>
                    </Fragment>
                  ))}
                </Space>
              }
            />
          )}

          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={running && !awaitingConfirmStage}
            disabled={running || Boolean(awaitingConfirmStage)}
            block
            style={{ marginTop: 16 }}
            onClick={handleCreatePipeline}
          >
            {matchedSkill && matchedRequirement === requirement.trim() ? '确认页面并执行流水线' : '分析需求并匹配页面'}
          </Button>

          {awaitingConfirmStage && (
            <Alert
              type="warning"
              showIcon
              style={{ marginTop: 12 }}
              message={`等待人工确认：${stageLabel[awaitingConfirmStage] || awaitingConfirmStage}`}
              description={
                <Space direction="vertical" style={{ width: '100%' }}>
                  <TextArea
                    rows={4}
                    value={feedback}
                    onChange={(event) => setFeedback(event.target.value)}
                    placeholder="填写调整方向，例如：列表字段减少到 8 个、弹窗改为抽屉、导出权限只给财务角色。留空则直接确认继续。"
                  />
                  <Space>
                    <Button type="primary" loading={running} onClick={() => resumePipeline(true)}>确认继续</Button>
                    <Button danger icon={<ReloadOutlined />} loading={running} onClick={() => resumePipeline(false)}>
                      驳回修改并重新生成
                    </Button>
                  </Space>
                </Space>
              }
            />
          )}

          <div style={{ marginTop: 18 }}>
            <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 8 }}>
              <Title level={5} style={{ margin: 0 }}>流水线</Title>
              <Button size="small" onClick={loadPipelines} loading={pipelineListLoading}>刷新</Button>
            </Space>
            <List
              size="small"
              loading={pipelineListLoading}
              dataSource={pipelines.slice(0, 8)}
              locale={{ emptyText: '暂无流水线' }}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    <Button key="view" size="small" onClick={() => restorePipeline(item.pipeline_id)}>查看</Button>,
                    <Button
                      key="run"
                      size="small"
                      type="link"
                      disabled={running || !pipelineId || pipelineId !== item.pipeline_id || ['completed', 'cancelled', 'waiting_confirm'].includes(item.status)}
                      onClick={continueSelectedPipeline}
                    >
                      {item.status === 'failed' ? '重新生成' : '继续'}
                    </Button>,
                    item.status === 'waiting_confirm' && pipelineId === item.pipeline_id ? (
                      <Space key="confirm-actions" size={0}>
                        <Button
                          size="small"
                          type="link"
                          loading={running}
                          onClick={() => resumePipeline(true)}
                        >
                          确认
                        </Button>
                        <Button
                          size="small"
                          danger
                          type="link"
                          loading={running}
                          onClick={() => resumePipeline(false)}
                        >
                          重新生成
                        </Button>
                      </Space>
                    ) : null,
                    <Button
                      key="delete"
                      size="small"
                      danger
                      type="link"
                      disabled={running && pipelineId === item.pipeline_id}
                      onClick={() => {
                        Modal.confirm({
                          title: '删除流水线',
                          content: `确定删除「${item.user_request || item.pipeline_id}」吗？删除后不会再出现在历史列表。`,
                          okText: '删除',
                          okButtonProps: { danger: true },
                          cancelText: '取消',
                          onOk: () => deletePipeline(item.pipeline_id),
                        })
                      }}
                    >
                      删除
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Space size={6} wrap>
                        <Text strong ellipsis style={{ maxWidth: 220 }}>{item.user_request || item.pipeline_id}</Text>
                        <Tag color={item.status === 'completed' ? 'success' : item.status === 'failed' ? 'error' : 'processing'}>{item.status}</Tag>
                      </Space>
                    }
                    description={`${stageLabel[item.current_stage] || item.current_stage || '未开始'} · ${item.pipeline_id}`}
                  />
                </List.Item>
              )}
            />
          </div>

          <div style={{ marginTop: 18 }}>
            <Title level={5}>执行日志</Title>
            <div style={{ maxHeight: 220, overflowY: 'auto', border: '1px solid #eef2f7', borderRadius: 6, padding: '6px 8px', background: '#fbfdff' }}>
              {logs.length ? logs.map((line, index) => (
                <div
                  key={`${line}-${index}`}
                  style={{ fontSize: 12, color: '#475569', padding: '4px 0', borderBottom: '1px solid #f1f5f9', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                >
                  {line}
                </div>
              )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无执行日志" />}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="workbench-card" style={{ background: '#fff', border: '1px solid #e5eaf3', borderRadius: 8, padding: 20 }}>
            <Space style={{ justifyContent: 'space-between', width: '100%' }}>
              <div>
                <Title level={4} style={{ margin: 0 }}>流水线产物</Title>
                <Text type="secondary">{pipelineId || '尚未创建流水线'}</Text>
              </div>
              <Space>
                {status && <Tag color={status.status === 'completed' ? 'success' : status.status === 'failed' ? 'error' : 'processing'}>{status.status}</Tag>}
                {activeStage && <Tag color="blue">{stageLabel[activeStage] || activeStage}</Tag>}
                {status?.status === 'waiting_confirm' && (
                  <Button
                    type="primary"
                    icon={<CheckCircleOutlined />}
                    loading={running}
                    onClick={() => resumePipeline(true)}
                  >
                    确认继续
                  </Button>
                )}
                {status?.status === 'waiting_confirm' && (
                  <Button
                    danger
                    icon={<ReloadOutlined />}
                    loading={running}
                    onClick={() => resumePipeline(false)}
                  >
                    重新生成当前阶段
                  </Button>
                )}
                {status?.status === 'failed' && (
                  <Button
                    danger
                    icon={<ReloadOutlined />}
                    loading={running}
                    onClick={continueSelectedPipeline}
                  >
                    重新生成当前阶段
                  </Button>
                )}
                <Button
                  icon={<DownloadOutlined />}
                  disabled={!pipelineId || !Object.keys(artifact?.frontend_files || {}).length}
                  onClick={handleDownloadFrontend}
                >
                  下载前端代码
                </Button>
              </Space>
            </Space>
            {status && (
              <Space wrap style={{ marginTop: 10 }}>
                {status.project_skill && (
                  <Tag color="cyan">前端：{status.project_skill.project_name || status.project_skill.project_id}</Tag>
                )}
                {(status.backend_project_skills?.length ? status.backend_project_skills : status.backend_project_skill ? [status.backend_project_skill] : []).map((backendSkill) => (
                  <Tag key={backendSkill.project_id} color="purple">后端：{backendSkill.project_name || backendSkill.project_id}</Tag>
                ))}
              </Space>
            )}
            <Steps
              size="small"
              items={stageItems}
              current={Math.max(stageOrder.indexOf(activeStage), 0)}
              style={{ marginTop: 18 }}
            />
            {status?.status === 'waiting_confirm' && (
              <Alert
                type="warning"
                showIcon
                style={{ marginTop: 16 }}
                message={`当前阶段等待确认：${stageLabel[status.current_stage] || status.current_stage}`}
                description={
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Text>
                      如果右侧输出和前端代码方向正确，点击“确认继续”；如果预览没正常生成或页面不对，填写修改意见后点击“重新生成当前阶段”。
                    </Text>
                    <TextArea
                      rows={3}
                      value={feedback}
                      onChange={(event) => setFeedback(event.target.value)}
                      placeholder="例如：预览未生成；页面路径不对；不要新建 mock 数据；请改现有零售商品列表页。"
                    />
                    <Space>
                      <Button type="primary" icon={<CheckCircleOutlined />} loading={running} onClick={() => resumePipeline(true)}>
                        确认继续
                      </Button>
                      <Button danger icon={<ReloadOutlined />} loading={running} onClick={() => resumePipeline(false)}>
                        重新生成当前阶段
                      </Button>
                    </Space>
                  </Space>
                }
              />
            )}
          </div>

          <div className="workbench-card" style={{ background: '#fff', border: '1px solid #e5eaf3', borderRadius: 8, padding: 20 }}>
            <Space style={{ marginBottom: 12 }}>
              <FileSearchOutlined />
              <Title level={4} style={{ margin: 0 }}>实时输出</Title>
            </Space>
            {streamItems.length ? <Collapse items={streamItems} defaultActiveKey={activeStage ? [activeStage] : undefined} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="等待阶段输出" />}
          </div>

          <div className="workbench-card" style={{ background: '#fff', border: '1px solid #e5eaf3', borderRadius: 8, padding: 20 }}>
            <Space style={{ marginBottom: 12 }}>
              <CodeOutlined />
              <Title level={4} style={{ margin: 0 }}>前端代码</Title>
            </Space>
            {fileItems.length ? <Collapse items={fileItems} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="等待前端预览代码生成" />}
          </div>

          <div className="workbench-card" style={{ background: '#fff', border: '1px solid #e5eaf3', borderRadius: 8, padding: 20 }}>
            <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 12 }}>
              <Space>
                <RocketOutlined />
                <Title level={4} style={{ margin: 0 }}>真实前端预览</Title>
              </Space>
              <Space>
                <Button
                  size="small"
                  icon={<RocketOutlined />}
                  loading={sandboxPreviewLoading}
                  disabled={!pipelineId || !Object.keys(artifact?.frontend_files || {}).length}
                  onClick={handleStartSandboxPreview}
                >
                  启动真实预览
                </Button>
                {sandboxPreviewUrl && (
                  <Button
                    size="small"
                    icon={<FullscreenOutlined />}
                    onClick={() => window.open(sandboxPreviewUrl, '_blank')}
                  >
                    新页面打开
                  </Button>
                )}
              </Space>
            </Space>
            <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
              这里会把生成代码覆盖到匹配前端项目的沙箱副本中，并按项目脚本启动。
            </Text>
            {sandboxPreviewUrl ? (
              <iframe
                title="real-frontend-preview"
                src={sandboxPreviewUrl}
                sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
                style={{ width: '100%', height: 520, border: '1px solid #e5eaf3', borderRadius: 6, background: '#fff' }}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="等待前端预览代码生成后启动真实预览" />
            )}
          </div>

          <div className="workbench-two-column">
            <div className="workbench-card" style={{ background: '#fff', border: '1px solid #e5eaf3', borderRadius: 8, padding: 20 }}>
              <Space style={{ marginBottom: 12 }}>
                <FileTextOutlined />
                <Title level={4} style={{ margin: 0 }}>API 契约</Title>
              </Space>
              <pre style={{ minHeight: 220, maxHeight: 420, overflow: 'auto', whiteSpace: 'pre-wrap', margin: 0 }}>
                {artifact?.api_contract || '等待 delivery 阶段生成 API 契约'}
              </pre>
            </div>

            <div className="workbench-card" style={{ background: '#fff', border: '1px solid #e5eaf3', borderRadius: 8, padding: 20 }}>
              <Space style={{ marginBottom: 12 }}>
                <CheckCircleOutlined />
                <Title level={4} style={{ margin: 0 }}>自动审查</Title>
              </Space>
              <Paragraph>
                <Tag color={artifact?.review_status === 'completed' ? (artifact?.review?.review_passed === false ? 'error' : 'success') : 'default'}>
                  {artifact?.review_status === 'completed'
                    ? (artifact?.review?.review_passed === false ? 'FAIL' : 'PASS/REVIEWED')
                    : '等待审查'}
                </Tag>
              </Paragraph>
              <pre style={{ minHeight: 180, maxHeight: 420, overflow: 'auto', whiteSpace: 'pre-wrap', margin: 0 }}>
                {artifact?.review_status === 'completed'
                  ? JSON.stringify(artifact.review || { output: artifact.review_output || '' }, null, 2)
                  : '等待 code_review 阶段输出'}
              </pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
