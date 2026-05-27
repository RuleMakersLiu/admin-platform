import { Fragment, useEffect, useState } from 'react'
import { Alert, Button, Collapse, Empty, Input, List, Modal, Space, Steps, Tag, Typography, message } from 'antd'
import {
  CheckCircleOutlined,
  CodeOutlined,
  DownloadOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  FullscreenOutlined,
  PlayCircleOutlined,
  RocketOutlined,
} from '@ant-design/icons'
import { pipelineApi, type PipelineArtifact, type PipelineListItem, type PipelineStatus, type ProjectSkillMatch } from '@/services/pipeline'
import { saveLastPortalPath, useAuthStore } from '@/stores/auth'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

const stageLabel: Record<string, string> = {
  requirement: '需求分析',
  page_design: '页面设计',
  prototype: '预览生成',
  delivery: 'API 契约',
  frontend_dev: '前端代码',
  code_review: '自动审查',
  report: '报告',
}

const stageOrder = ['requirement', 'page_design', 'prototype', 'delivery', 'frontend_dev', 'code_review', 'report']

const formatMatchSource = (source: string) => (source === 'llm' ? '大模型分析' : '规则兜底')

export default function ProductPortal() {
  const { user } = useAuthStore()
  const [requirement, setRequirement] = useState('')
  const [running, setRunning] = useState(false)
  const [pipelineId, setPipelineId] = useState('')
  const [status, setStatus] = useState<PipelineStatus | null>(null)
  const [artifact, setArtifact] = useState<PipelineArtifact | null>(null)
  const [matchedSkill, setMatchedSkill] = useState<ProjectSkillMatch | null>(null)
  const [logs, setLogs] = useState<string[]>([])
  const [currentStage, setCurrentStage] = useState('')
  const [streamOutputByStage, setStreamOutputByStage] = useState<Record<string, string>>({})
  const [awaitingConfirmStage, setAwaitingConfirmStage] = useState('')
  const [feedback, setFeedback] = useState('')
  const [pipelines, setPipelines] = useState<PipelineListItem[]>([])
  const [pipelineListLoading, setPipelineListLoading] = useState(false)

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
    return nextStatus
  }

  const restorePipeline = async (id: string) => {
    setRunning(false)
    setPipelineId(id)
    setMatchedSkill(null)
    setFeedback('')
    setStreamOutputByStage({})
    try {
      const nextStatus = await refreshOutputs(id)
      setRequirement(nextStatus.user_request || '')
      setCurrentStage(nextStatus.current_stage || '')
      setAwaitingConfirmStage(nextStatus.status === 'waiting_confirm' ? nextStatus.current_stage : '')
      setLogs((prev) => [`已切换到流水线：${id}`, ...prev].slice(0, 80))
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : '加载流水线失败')
    }
  }

  const runUntilPause = async (id: string, userInput = '') => {
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
  }

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
      appendLog('正在分析需求并匹配项目 Skill')
      const match = await pipelineApi.matchProjectSkill({ user_request: trimmedRequirement })
      setMatchedSkill(match)
      appendLog(`已匹配前端项目：${match.skill.project_name || match.skill.project_id}（${formatMatchSource(match.match_source)}）`)
      const backendMatches = match.backend_matches || (match.backend_match ? [match.backend_match] : [])
      if (backendMatches.length) {
        appendLog(`已匹配后端项目组：${backendMatches.map(item => item.skill.project_name || item.skill.project_id).join('、')}`)
      }

      const projectId = String(match.skill.project_id)
      const backendProjectIds = backendMatches.map(item => String(item.skill.project_id))
      const backendProjectId = backendProjectIds[0] || ''
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
      const finalStatus = await runUntilPause(pipelineId)
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
        setStatus(null)
        setArtifact(null)
        setCurrentStage('')
        setAwaitingConfirmStage('')
        setStreamOutputByStage({})
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

  const openPreviewInNewPage = () => {
    if (!artifact?.preview_html) return
    const blob = new Blob([artifact.preview_html], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank', 'noopener,noreferrer')
    window.setTimeout(() => URL.revokeObjectURL(url), 60000)
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
            onChange={(event) => setRequirement(event.target.value)}
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
                    <Tag color={matchedSkill.match_source === 'llm' ? 'blue' : 'gold'}>{formatMatchSource(matchedSkill.match_source)}</Tag>
                    <Tag color="green">{Math.round(matchedSkill.confidence * 100)}%</Tag>
                  </Text>
                  <Text>{matchedSkill.match_reason}</Text>
                  {(matchedSkill.backend_matches || (matchedSkill.backend_match ? [matchedSkill.backend_match] : [])).map((backendMatch) => (
                    <Fragment key={backendMatch.skill.project_id}>
                      <Text>
                        后端：{backendMatch.skill.project_name || backendMatch.skill.project_id} · {' '}
                        {backendMatch.skill.language || 'unknown'} / {backendMatch.skill.framework || 'unknown'}
                        <Tag style={{ marginLeft: 8 }}>v{backendMatch.skill.skill_version}</Tag>
                        <Tag color={backendMatch.match_source === 'llm' ? 'blue' : 'gold'}>{formatMatchSource(backendMatch.match_source)}</Tag>
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
            分析需求并执行流水线
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
                    <Button danger loading={running} onClick={() => resumePipeline(false)}>按反馈重做本阶段</Button>
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
                      disabled={running || !pipelineId || pipelineId !== item.pipeline_id || ['completed', 'failed', 'cancelled', 'waiting_confirm'].includes(item.status)}
                      onClick={continueSelectedPipeline}
                    >
                      继续
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
              )}
            />
          </div>

          <div style={{ marginTop: 18 }}>
            <Title level={5}>执行日志</Title>
            {logs.length ? logs.map((line, index) => (
              <div key={`${line}-${index}`} style={{ fontSize: 12, color: '#475569', padding: '4px 0', borderBottom: '1px solid #f1f5f9' }}>
                {line}
              </div>
            )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无执行日志" />}
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
          </div>

          <div className="workbench-card" style={{ background: '#fff', border: '1px solid #e5eaf3', borderRadius: 8, padding: 20 }}>
            <Space style={{ marginBottom: 12 }}>
              <FileSearchOutlined />
              <Title level={4} style={{ margin: 0 }}>实时输出</Title>
            </Space>
            {streamItems.length ? <Collapse items={streamItems} defaultActiveKey={activeStage ? [activeStage] : undefined} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="等待阶段输出" />}
          </div>

          <div className="workbench-card" style={{ background: '#fff', border: '1px solid #e5eaf3', borderRadius: 8, padding: 20 }}>
            <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 12 }}>
              <Space>
                <RocketOutlined />
                <Title level={4} style={{ margin: 0 }}>预览</Title>
              </Space>
              <Button
                size="small"
                icon={<FullscreenOutlined />}
                disabled={!artifact?.preview_html}
                onClick={openPreviewInNewPage}
              >
                新页面预览
              </Button>
            </Space>
            {artifact?.preview_html ? (
              <iframe
                title="pipeline-preview"
                srcDoc={artifact.preview_html}
                style={{ width: '100%', height: 520, border: '1px solid #e5eaf3', borderRadius: 6, background: '#fff' }}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="等待预览生成" />
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

          <div className="workbench-card" style={{ background: '#fff', border: '1px solid #e5eaf3', borderRadius: 8, padding: 20 }}>
            <Space style={{ marginBottom: 12 }}>
              <CodeOutlined />
              <Title level={4} style={{ margin: 0 }}>前端代码</Title>
            </Space>
            {fileItems.length ? <Collapse items={fileItems} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="等待 frontend_dev 阶段生成代码" />}
          </div>
        </div>
      </div>
    </div>
  )
}
