import { useEffect, useState } from 'react'
import { Alert, Button, Collapse, Empty, Input, Space, Tag, Typography, message } from 'antd'
import {
  CheckCircleOutlined,
  CodeOutlined,
  DownloadOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  PlayCircleOutlined,
  RocketOutlined,
} from '@ant-design/icons'
import { pipelineApi, type PipelineArtifact, type PipelineStatus, type ProjectSkillMatch } from '@/services/pipeline'
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

  useEffect(() => {
    saveLastPortalPath(user, '/pipeline/requirement')
  }, [user])

  const appendLog = (line: string) => {
    setLogs((prev) => [line, ...prev].slice(0, 80))
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

  const runToCompletion = async (id: string) => {
    for (let i = 0; i < 16; i += 1) {
      await pipelineApi.executeStream(id, '', (event) => {
        if (event.type === 'stage_started' && event.stage) {
          appendLog(`开始执行：${stageLabel[event.stage] || event.stage}`)
        }
        if (event.type === 'stage_completed' && event.stage) {
          appendLog(`完成：${stageLabel[event.stage] || event.stage}`)
        }
        if (event.type === 'waiting_confirm' && event.stage) {
          appendLog(`自动确认阶段：${stageLabel[event.stage] || event.stage}`)
        }
        if (event.type === 'failed') {
          appendLog(`失败：${event.error || '未知错误'}`)
        }
      })

      const nextStatus = await refreshOutputs(id)
      if (nextStatus.status === 'waiting_confirm') {
        await pipelineApi.confirm(id, true, 'Confirmed by product portal automation.')
        continue
      }
      if (nextStatus.status === 'completed' || nextStatus.status === 'failed' || nextStatus.status === 'cancelled') {
        return nextStatus
      }
    }
    return refreshOutputs(id)
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

    try {
      appendLog('正在分析需求并匹配项目 Skill')
      const match = await pipelineApi.matchProjectSkill({ user_request: trimmedRequirement })
      setMatchedSkill(match)
      appendLog(`已匹配项目：${match.skill.project_name || match.skill.project_id}（${formatMatchSource(match.match_source)}）`)

      const projectId = String(match.skill.project_id)
      const created = await pipelineApi.create({
        user_request: trimmedRequirement,
        project_id: projectId,
        frontend_project_id: projectId,
        frontend_tech: [match.skill.language, match.skill.framework].filter(Boolean).join('/'),
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
        },
      })
      setPipelineId(created.pipeline_id)
      appendLog(`流水线已创建：${created.pipeline_id}`)

      const finalStatus = await runToCompletion(created.pipeline_id)
      if (finalStatus?.status === 'failed') {
        throw new Error('流水线执行失败，请查看自动审查或阶段日志')
      }
      message.success('流水线执行完成')
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : '流水线执行失败')
    } finally {
      setRunning(false)
    }
  }

  const fileItems = Object.entries(artifact?.frontend_files || {}).map(([path, content]) => ({
    key: path,
    label: path,
    children: <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 12 }}>{content}</pre>,
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
              message={`已匹配项目：${matchedSkill.skill.project_name || matchedSkill.skill.project_id}`}
              description={
                <Space direction="vertical" size={4}>
                  <Text>
                    {matchedSkill.skill.language || 'unknown'} / {matchedSkill.skill.framework || 'unknown'}
                    <Tag style={{ marginLeft: 8 }}>v{matchedSkill.skill.skill_version}</Tag>
                    <Tag color={matchedSkill.match_source === 'llm' ? 'blue' : 'gold'}>{formatMatchSource(matchedSkill.match_source)}</Tag>
                    <Tag color="green">{Math.round(matchedSkill.confidence * 100)}%</Tag>
                  </Text>
                  <Text>{matchedSkill.match_reason}</Text>
                </Space>
              }
            />
          )}

          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={running}
            block
            style={{ marginTop: 16 }}
            onClick={handleCreatePipeline}
          >
            分析需求并执行流水线
          </Button>

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
                <Button icon={<DownloadOutlined />} disabled={!pipelineId} onClick={() => pipelineApi.downloadFrontend(pipelineId)}>下载前端代码</Button>
              </Space>
            </Space>
          </div>

          {artifact?.preview_html && (
            <div className="workbench-card" style={{ background: '#fff', border: '1px solid #e5eaf3', borderRadius: 8, padding: 20 }}>
              <Space style={{ marginBottom: 12 }}>
                <RocketOutlined />
                <Title level={4} style={{ margin: 0 }}>预览</Title>
              </Space>
              <iframe
                title="pipeline-preview"
                srcDoc={artifact.preview_html}
                style={{ width: '100%', height: 460, border: '1px solid #e5eaf3', borderRadius: 6, background: '#fff' }}
              />
            </div>
          )}

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
                <Tag color={artifact?.review?.review_passed === false ? 'error' : artifact?.review ? 'success' : 'default'}>
                  {artifact?.review?.review_passed === false ? 'FAIL' : artifact?.review ? 'PASS/REVIEWED' : '等待审查'}
                </Tag>
              </Paragraph>
              <pre style={{ minHeight: 180, maxHeight: 420, overflow: 'auto', whiteSpace: 'pre-wrap', margin: 0 }}>
                {artifact?.review ? JSON.stringify(artifact.review, null, 2) : '等待 code_review 阶段输出'}
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
