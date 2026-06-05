import { Fragment, useEffect, useRef, useState } from 'react'
import { Alert, Button, Collapse, Empty, Input, List, Modal, Radio, Space, Steps, Table, Tag, Typography, message } from 'antd'
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
import { pipelineApi, type FrontendPageCandidate, type FrontendPageCandidates, type PipelineArtifact, type PipelineListItem, type PipelineStatus, type ProjectSkillMatch } from '@/services/pipeline'
import { saveLastPortalPath, useAuthStore } from '@/stores/auth'

const { Title, Text } = Typography
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

const confirmActionLabel = (stage = '') => {
  const labels: Record<string, string> = {
    requirement: '确认需求，进入页面设计',
    page_design: '确认页面设计，生成前端预览代码',
    prototype: '确认前端预览，生成 API 契约',
    delivery: '确认 API 契约，进入自动审查',
    code_review: '确认审查结果，生成报告',
    report: '确认报告，完成流水线',
  }
  return labels[stage] || '确认当前阶段并继续'
}

const confirmRejectLabel = (stage = '') => {
  if (stage === 'report') return '提交反馈并重新生成报告'
  return `提交反馈并重新生成${stageLabel[stage] || '当前阶段'}`
}

const confirmMessage = (stage = '') => {
  if (stage === 'report') return '请确认报告，确认后流水线完成'
  return `请确认${stageLabel[stage] || stage || '当前阶段'}，确认后进入下一阶段`
}

const feedbackPlaceholder = (stage = '') => {
  if (stage === 'report') return '如果报告内容需要调整，请写明缺少哪些结论、风险或交付说明。'
  return '例如：我要的是零售商品列表，不是商品池；不要新建页面；只增加商品ID筛选项。'
}

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

const pageFunctionName = (path: string) => {
  const normalized = path.replace(/\\/g, '/')
  const fileName = normalized.split('/').pop()?.replace(/\.(vue|tsx|jsx|ts|js)$/i, '') || normalized
  const text = `${normalized}/${fileName}`.toLowerCase()
  const parts: string[] = []
  if (/retail|零售/.test(text)) parts.push('零售')
  if (/goods|product|sku|spu|商品/.test(text)) parts.push('商品')
  if (/pool|池/.test(text)) parts.push('池')
  if (/activity|活动/.test(text)) parts.push('活动')
  if (/order|订单/.test(text)) parts.push('订单')
  if (/list|列表/.test(text)) parts.push('列表')
  if (!parts.length) return fileName.replace(/([a-z])([A-Z])/g, '$1 $2')
  return parts.join('')
}

const candidateLabel = (candidate: FrontendPageCandidate) => {
  const name = candidate.display_name || pageFunctionName(candidate.path)
  return name.endsWith('页') ? name : `${name}页`
}

const candidateConfidenceLabel = (confidence = 0) => {
  if (confidence >= 0.75) return '很可能是这个'
  if (confidence >= 0.55) return '可能是这个'
  return '需要确认'
}

const candidateConfidenceColor = (confidence = 0) => {
  if (confidence >= 0.75) return 'green'
  if (confidence >= 0.55) return 'gold'
  return 'orange'
}

const severityColor = (severity = '') => {
  const value = severity.toLowerCase()
  if (value === 'critical') return 'red'
  if (value === 'major') return 'orange'
  if (value === 'minor') return 'blue'
  return 'default'
}

const splitSuggestions = (text = '') => {
  return text
    .split(/\n|(?=\d+\.\s*)/)
    .map((item) => item.replace(/^\d+\.\s*/, '').trim())
    .filter(Boolean)
}

const normalizedContractField = (value: unknown) => String(value || '')
  .trim()
  .replace(/^(?:this\.)?(?:queryParam|params|parameter|query|request|body|payload|form)\./, '')
  .replace(/^(?:query|body|request|param|params|payload)[\s:：=]+/i, '')
  .replace(/^[`'"]|[`'"]$/g, '')

const reviewFieldValue = (record: Record<string, any>, keys: string[]) => {
  for (const key of keys) {
    if (record[key]) return record[key]
  }
  return ''
}

const reviewFieldMismatchIsEquivalent = (record: Record<string, any>) => {
  const frontendField = normalizedContractField(reviewFieldValue(record, [
    'frontend_field',
    'frontend_param',
    'frontend_parameter',
    'current_field',
    'actual_field',
  ]))
  const contractField = normalizedContractField(reviewFieldValue(record, [
    'contract_field',
    'api_field',
    'api_param',
    'api_parameter',
    'expected_field',
    'request_field',
  ]))
  return Boolean(frontendField && contractField && frontendField === contractField)
}

const normalizeReview = (review: Record<string, any>) => {
  const mismatches = Array.isArray(review.field_mismatches) ? review.field_mismatches : []
  const actionableMismatches = mismatches.filter((item) => !reviewFieldMismatchIsEquivalent(item))
  if (actionableMismatches.length === mismatches.length) return review

  return {
    ...review,
    review_passed: actionableMismatches.length ? review.review_passed : true,
    contract_alignment: actionableMismatches.length
      ? review.contract_alignment
      : '前端 queryParam 字段已与 API 契约请求参数对齐，无字段名不一致问题。',
    field_mismatches: actionableMismatches,
    fix_suggestions: actionableMismatches.length ? review.fix_suggestions : '',
  }
}

const reviewFailureDescription = (review: Record<string, any>, mismatches: Record<string, any>[]) => {
  if (review.review_passed !== false) return review.contract_alignment || '未发现阻塞问题。'
  const criticalIssue = mismatches.find((item) => String(item.severity || '').toLowerCase() === 'critical')
  const issue = criticalIssue || mismatches[0]
  if (issue?.fix) return issue.fix
  if (issue?.frontend_field) return `需处理：${issue.frontend_field}`
  if (review.fix_suggestions) return review.fix_suggestions
  return '存在字段、接口或运行风险，请按下方建议修复。'
}

const ReviewSummary = ({
  artifact,
  regenerating,
  onRegenerate,
}: {
  artifact: PipelineArtifact | null
  regenerating?: boolean
  onRegenerate?: () => void
}) => {
  if (artifact?.review_status !== 'completed') {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="等待自动审查输出" />
  }

  const review = normalizeReview(artifact.review || {})
  const passed = review.review_passed !== false
  const mismatches = Array.isArray(review.field_mismatches) ? review.field_mismatches : []
  const suggestions = splitSuggestions(String(review.fix_suggestions || ''))
  const rawOutput = String(review.output || artifact.review_output || '')
  const description = reviewFailureDescription(review, mismatches)

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Alert
        type={passed ? 'success' : 'error'}
        showIcon
        message={passed ? '审查通过，可以继续' : '审查未通过，需要先调整'}
        description={description}
      />

      {!passed && review.contract_alignment && review.contract_alignment !== description && (
        <Alert
          type="info"
          showIcon
          message="契约对齐结论"
          description={review.contract_alignment}
        />
      )}

      <Space wrap>
        <Tag color={passed ? 'success' : 'error'}>{passed ? 'PASS' : 'FAIL'}</Tag>
        {review.backend_score && <Tag color="purple">API 契约 {review.backend_score}</Tag>}
        {review.frontend_score && <Tag color="cyan">前端代码 {review.frontend_score}</Tag>}
        {mismatches.length > 0 && <Tag color="orange">{mismatches.length} 个需处理问题</Tag>}
      </Space>

      {!passed && onRegenerate && (
        <Button type="primary" danger icon={<ReloadOutlined />} loading={regenerating} onClick={onRegenerate}>
          按审查意见重新生成前端预览
        </Button>
      )}

      {mismatches.length > 0 && (
        <Table
          size="small"
          pagination={false}
          rowKey={(record, index) => `${record.location || 'issue'}-${index}`}
          dataSource={mismatches}
          columns={[
            {
              title: '级别',
              dataIndex: 'severity',
              width: 86,
              render: (value) => <Tag color={severityColor(String(value || ''))}>{value || 'issue'}</Tag>,
            },
            {
              title: '位置',
              dataIndex: 'location',
              width: 150,
              render: (value) => value || '-',
            },
            {
              title: '问题',
              render: (_, record) => (
                <Space direction="vertical" size={2}>
                  {record.frontend_field && <Text>当前：<Text code>{record.frontend_field}</Text></Text>}
                  {record.contract_field && record.contract_field !== '-' && <Text>应为：<Text code>{record.contract_field}</Text></Text>}
                  {record.fix && <Text type="secondary">{record.fix}</Text>}
                </Space>
              ),
            },
          ]}
        />
      )}

      {suggestions.length > 0 && (
        <div style={{ border: '1px solid #e5eaf3', borderRadius: 8, padding: 12, background: '#fbfdff' }}>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>建议动作</Text>
          <Space direction="vertical" size={6}>
            {suggestions.map((item, index) => (
              <Text key={`${item}-${index}`}>{index + 1}. {item}</Text>
            ))}
          </Space>
        </div>
      )}

      {rawOutput && (
        <Collapse
          size="small"
          items={[{
            key: 'raw-review',
            label: '查看原始审查内容',
            children: (
              <pre style={{ maxHeight: 360, overflow: 'auto', whiteSpace: 'pre-wrap', margin: 0, fontSize: 12 }}>
                {rawOutput}
              </pre>
            ),
          }]}
        />
      )}
    </Space>
  )
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

  const getPendingPageSelection = (): FrontendPageCandidates | null => {
    const structured = status?.stages?.[status.current_stage || '']?.structured_output || {}
    if (!structured.needs_frontend_page_selection) return null
    return (structured.frontend_page_candidates || null) as FrontendPageCandidates | null
  }

  const renderPageCandidateOptions = (
    candidates: FrontendPageCandidate[],
    options?: { uncertain?: boolean; limit?: number },
  ) => (
    <Radio.Group
      value={selectedPagePath}
      onChange={(event) => setSelectedPagePath(event.target.value)}
      style={{ width: '100%' }}
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        {candidates.slice(0, options?.limit || 6).map((candidate) => {
          const checked = selectedPagePath === candidate.path
          return (
            <Radio
              key={candidate.path}
              value={candidate.path}
              style={{
                display: 'block',
                width: '100%',
                padding: '10px 12px',
                margin: 0,
                border: `1px solid ${checked ? '#91caff' : '#f0f0f0'}`,
                borderRadius: 6,
                background: checked ? '#e6f4ff' : '#fff',
              }}
            >
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Space wrap size={6}>
                  <Text strong>{candidateLabel(candidate)}</Text>
                  <Tag color={candidateConfidenceColor(candidate.confidence)}>
                    {candidateConfidenceLabel(candidate.confidence)}
                  </Tag>
                  {(candidate.uncertain || options?.uncertain) && <Tag color="orange">请你确认</Tag>}
                </Space>
                <Text type="secondary">
                  {candidate.menu_hint || candidate.reason || '系统根据页面内容和业务词匹配到的现有功能'}
                </Text>
                <Space wrap size={6}>
                  {candidate.route_hint && <Tag color="blue">路由：{candidate.route_hint}</Tag>}
                  {candidate.matched_terms?.slice(0, 3).map((term) => <Tag key={term}>{term}</Tag>)}
                </Space>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  开发定位：{candidate.developer_hint || candidate.path}
                </Text>
              </Space>
            </Radio>
          )
        })}
      </Space>
    </Radio.Group>
  )

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

  useEffect(() => {
    const candidates = getPendingPageSelection()?.candidates || []
    if (!selectedPagePath && candidates[0]?.path) {
      setSelectedPagePath(candidates[0].path)
    }
  }, [status?.pipeline_id, status?.status, status?.current_stage])

  const resumePipeline = async (confirmed: boolean) => {
    if (!pipelineId) return
    setRunning(true)
    try {
      const note = feedback.trim()
      const confirmResult = await pipelineApi.confirm(
        pipelineId,
        confirmed,
        note || (confirmed ? '人工确认通过，继续执行。' : '请按人工反馈调整后重新生成。'),
      )
      if (confirmResult?.error) {
        throw new Error(confirmResult.error)
      }
      const targetStage = awaitingConfirmStage || status?.current_stage || currentStage
      appendLog(`${confirmed ? '确认通过' : '退回调整'}：${stageLabel[awaitingConfirmStage] || awaitingConfirmStage}`)
      if (!confirmed) {
        appendLog(`本次修改意见：${note || '请按人工反馈调整后重新生成。'}`)
        if (targetStage) {
          setStreamOutputByStage((prev) => ({ ...prev, [targetStage]: '' }))
        }
        setArtifact((prev) => prev ? { ...prev, frontend_files: {}, preview_html: '', preview_url: '' } : prev)
      }
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

  const submitFeedbackAndRegenerate = async () => {
    const note = feedback.trim()
    if (!note) {
      message.warning('请先填写要调整的页面功能问题')
      return
    }
    await resumePipeline(false)
  }

  const regenerateFromReview = async () => {
    if (!pipelineId) return
    const review = normalizeReview(artifact?.review || {})
    const mismatches = Array.isArray(review.field_mismatches) ? review.field_mismatches : []
    const feedbackText = [
      '自动审查未通过，请按以下问题重新生成前端预览代码，生成后需要再次通过可运行性和契约审查。',
      review.contract_alignment ? `审查结论：${review.contract_alignment}` : '',
      mismatches.length
        ? `需修复问题：${mismatches.map((item: any) => [
          item.location,
          item.frontend_field ? `当前 ${item.frontend_field}` : '',
          item.contract_field && item.contract_field !== '-' ? `应为 ${item.contract_field}` : '',
          item.fix,
        ].filter(Boolean).join('，')).join('；')}`
        : '',
      review.fix_suggestions ? `修复建议：${review.fix_suggestions}` : '',
      '必须保留现有页面、现有查询条件、现有表格列和现有接口；只做本次需求要求的增量改造。',
    ].filter(Boolean).join('\n')

    setRunning(true)
    try {
      await pipelineApi.rollback(pipelineId, 'prototype', feedbackText)
      appendLog('按自动审查意见回到前端预览代码并重新生成')
      setAwaitingConfirmStage('')
      setCurrentStage('prototype')
      setFeedback('')
      setSandboxPreviewUrl('')
      setStreamOutputByStage((prev) => ({
        ...prev,
        prototype: '',
        delivery: '',
        code_review: '',
        report: '',
      }))
      setArtifact((prev) => prev ? {
        ...prev,
        frontend_files: {},
        preview_html: '',
        preview_url: '',
        review: {},
        review_output: '',
        review_status: 'pending',
      } : prev)

      const finalStatus = await runUntilPause(pipelineId, feedbackText)
      if (finalStatus?.status === 'failed') {
        message.error('重新生成失败，请查看阶段输出')
      } else if (finalStatus?.status === 'waiting_confirm') {
        message.success('已重新生成，等待确认')
      } else if (finalStatus?.status === 'completed') {
        message.success('流水线执行完成')
      }
      loadPipelines()
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : '按审查意见重新生成失败')
      setRunning(false)
    }
  }

  const selectExistingPageAndRegenerate = async () => {
    if (!pipelineId) return
    const candidates = getPendingPageSelection()?.candidates || []
    const selectedCandidate = candidates.find((item) => item.path === selectedPagePath)
    if (!selectedPagePath) {
      message.warning('请先选择要修改的页面功能')
      return
    }
    setRunning(true)
    try {
      await pipelineApi.updateSkillConfig(pipelineId, {
        selected_frontend_page_path: selectedPagePath,
        selected_frontend_page_confidence: selectedCandidate?.confidence,
      })
      const label = selectedCandidate ? candidateLabel(selectedCandidate) : pageFunctionName(selectedPagePath)
      const confirmResult = await pipelineApi.confirm(
        pipelineId,
        false,
        `已人工选择要修改的页面功能：${label}。必须基于该现有页面重新生成，不允许改成商品池或新建页面。`,
      )
      if (confirmResult?.error) {
        throw new Error(confirmResult.error)
      }
      appendLog(`已选择页面功能：${label}`)
      setAwaitingConfirmStage('')
      setFeedback('')
      setArtifact((prev) => prev ? { ...prev, frontend_files: {}, preview_html: '', preview_url: '' } : prev)
      await runUntilPause(pipelineId)
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : '选择页面后重新生成失败')
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
      if (status?.status === 'waiting_confirm') {
        const confirmStage = status.current_stage || awaitingConfirmStage || currentStage
        const confirmResult = await pipelineApi.confirm(
          pipelineId,
          true,
          note || '人工确认通过，继续执行。',
        )
        if (confirmResult?.error) {
          throw new Error(confirmResult.error)
        }
        appendLog(`确认通过：${stageLabel[confirmStage] || confirmStage}`)
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
  const pendingPageSelection = getPendingPageSelection()
  const pendingPageCandidates = pendingPageSelection?.candidates || []
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
                          renderPageCandidateOptions(
                            matchedSkill.frontend_page_candidates.candidates || [],
                            { uncertain: matchedSkill.frontend_page_candidates.uncertain, limit: 5 },
                          )
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
            {matchedSkill && matchedRequirement === requirement.trim() ? '确认页面功能并执行' : '分析需求并匹配页面功能'}
          </Button>

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
              renderItem={(item) => {
                const runLabel = item.status === 'failed'
                  ? '重新生成'
                  : item.status === 'waiting_confirm'
                    ? confirmActionLabel(item.current_stage)
                    : '继续'
                return (
                  <List.Item
                    actions={[
                      <Button key="view" size="small" onClick={() => restorePipeline(item.pipeline_id)}>查看</Button>,
                      <Button
                        key="run"
                        size="small"
                        type="link"
                        disabled={running || !pipelineId || pipelineId !== item.pipeline_id || ['completed', 'cancelled'].includes(item.status)}
                        onClick={continueSelectedPipeline}
                      >
                        {runLabel}
                      </Button>,
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
                )
              }}
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
                message={pendingPageSelection ? '请选择要修改的页面功能' : confirmMessage(status.current_stage)}
                description={
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {pendingPageSelection ? (
                      pendingPageCandidates.length ? (
                        renderPageCandidateOptions(pendingPageCandidates, {
                          uncertain: pendingPageSelection.uncertain,
                          limit: 6,
                        })
                      ) : (
                        <Text type="warning">没有找到像“零售商品列表”这样的现有页面候选，系统不会新建页面冒充现有功能。</Text>
                      )
                    ) : (
                      <TextArea
                        rows={3}
                        value={feedback}
                        onChange={(event) => setFeedback(event.target.value)}
                        placeholder={feedbackPlaceholder(status.current_stage)}
                      />
                    )}
                    {pendingPageSelection ? (
                      <Button type="primary" loading={running} disabled={!pendingPageCandidates.length} onClick={selectExistingPageAndRegenerate}>
                        选定此页面功能并重新生成
                      </Button>
                    ) : (
                      <Space wrap>
                        <Button type="primary" loading={running} onClick={() => resumePipeline(true)}>
                          {confirmActionLabel(status.current_stage)}
                        </Button>
                        <Button danger icon={<ReloadOutlined />} loading={running} onClick={submitFeedbackAndRegenerate}>
                          {confirmRejectLabel(status.current_stage)}
                        </Button>
                      </Space>
                    )}
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
              <div
                style={{
                  width: '100%',
                  overflow: 'auto',
                  border: '1px solid #e5eaf3',
                  borderRadius: 8,
                  background: '#f8fafd',
                }}
              >
                <iframe
                  title="real-frontend-preview"
                  src={sandboxPreviewUrl}
                  sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
                  style={{
                    display: 'block',
                    width: '1280px',
                    maxWidth: 'none',
                    height: 720,
                    border: 0,
                    background: '#fff',
                  }}
                />
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="等待前端预览代码生成后启动真实预览" />
            )}
          </div>

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
            <ReviewSummary artifact={artifact} regenerating={running} onRegenerate={regenerateFromReview} />
          </div>
        </div>
      </div>
    </div>
  )
}
