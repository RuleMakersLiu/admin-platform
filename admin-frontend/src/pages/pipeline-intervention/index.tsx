import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Col, Empty, Row, Skeleton, Table, Tag, Tooltip, Typography, message } from 'antd'
import { ReloadOutlined, ToolOutlined } from '@ant-design/icons'
import { pipelineApi } from '@/services/pipeline'

const { Title, Text } = Typography

interface InterventionRow {
  pipeline_id: string
  current_stage: string
  current_stage_name: string
  user_request: string
  update_time: number
  reason: string
  issues: string[]
  file_hints: string[]
  retry_count: number
}

export default function PipelineInterventionPage() {
  const navigate = useNavigate()
  const [data, setData] = useState<InterventionRow[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await pipelineApi.interventionList()
      setData(res || [])
    } catch (e) {
      message.error((e as Error)?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <div style={{ padding: 24 }}>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>
            <ToolOutlined style={{ color: '#ea580c', marginRight: 8 }} />
            待人工介入
          </Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            这些流水线在某阶段自动重试耗尽，已暂停等待人工修改。处理后点「人工通过并继续」或「带反馈重新生成」。
          </Text>
        </Col>
        <Col>
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
        </Col>
      </Row>

      <Skeleton loading={loading && !data.length} active>
        <Card size="small">
          {data.length ? (
            <Table<InterventionRow>
              rowKey="pipeline_id"
              size="small"
              pagination={false}
              dataSource={data}
              onRow={(row) => ({
                onClick: () => navigate(`/pipeline/development?id=${row.pipeline_id}`),
                style: { cursor: 'pointer' },
              })}
              columns={[
                {
                  title: '流水线', dataIndex: 'pipeline_id', key: 'pid',
                  render: (v: string) => <Text copyable style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</Text>,
                },
                {
                  title: '卡住阶段', dataIndex: 'current_stage_name', key: 'stage',
                  render: (v: string) => <Tag color="orange">{v}</Tag>,
                },
                { title: '需求', dataIndex: 'user_request', key: 'req', ellipsis: true },
                {
                  title: '重试', dataIndex: 'retry_count', key: 'rc', width: 70,
                  render: (v: number) => <Tag color="red">{v} 次</Tag>,
                },
                {
                  title: '问题摘要', key: 'reason', ellipsis: true,
                  render: (_: any, row) => (
                    <Tooltip title={row.issues?.length ? row.issues.join('\n') : row.reason}>
                      <span>{row.issues?.length ? `${row.issues.length} 项问题` : row.reason}</span>
                    </Tooltip>
                  ),
                },
                {
                  title: '涉及文件', key: 'files', width: 120,
                  render: (_: any, row) => row.file_hints?.length
                    ? <Tag color="gold">{row.file_hints.length} 处</Tag>
                    : <Text type="secondary">-</Text>,
                },
              ]}
            />
          ) : (
            <Empty description="当前没有待人工介入的流水线 🎉" />
          )}
        </Card>
      </Skeleton>
    </div>
  )
}
