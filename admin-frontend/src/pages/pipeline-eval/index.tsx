import { useCallback, useEffect, useState } from 'react'
import { Card, Col, Row, Statistic, Table, Tag, Spin, Typography, Empty, Button, Modal, InputNumber, Input, message, Space } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { http } from '@/services/api'

const { Text } = Typography

interface EvalRow {
  pipeline_id: string
  project_id?: string
  user_request: string
  status: string
  retry_count: number
  create_time: number
  update_time: number
  overall_score: number | null
  pm_quality_score: number | null
  design_quality_score: number | null
  preview_quality_score: number | null
  judge_score: number | null
  hallucination_score: number | null
  vision_score: number | null
  e2e_passed: number | null
  human_score: number | null
  human_comment: string | null
  review_passed: number | null
  tests_passed: number | null
}

interface ScoreModalState {
  visible: boolean
  pid: string
  score: number
  comment: string
}

interface EvalStats {
  total: number
  avg_overall_score: number | null
  review_pass_rate: number | null
  tests_pass_rate: number | null
  avg_retry_count: number | null
  score_buckets: { lt60: number; '60_80': number; gte80: number }
  daily_trend: { date: string; avg_score: number; count: number }[]
}

const scoreColor = (s: number | null | undefined): string => {
  if (s === null || s === undefined) return '#94a3b8'
  if (s >= 80) return '#22c55e'
  if (s >= 60) return '#f59e0b'
  return '#ef4444'
}
const pct = (v: number | null | undefined) => (v === null || v === undefined ? '-' : `${Math.round(v * 100)}%`)

export default function PipelineEvalPage() {
  const [loading, setLoading] = useState(false)
  const [rows, setRows] = useState<EvalRow[]>([])
  const [stats, setStats] = useState<EvalStats | null>(null)
  const [scoreModal, setScoreModal] = useState<ScoreModalState>({ visible: false, pid: '', score: 80, comment: '' })

  const openScoreModal = (row: EvalRow) =>
    setScoreModal({ visible: true, pid: row.pipeline_id, score: row.human_score ?? 80, comment: row.human_comment ?? '' })

  const submitScore = async () => {
    try {
      await http.put(`/flow/pipeline/eval/${scoreModal.pid}/human-score`, {
        score: scoreModal.score,
        comment: scoreModal.comment || null,
      })
      message.success('人工评分已保存')
      setScoreModal((s) => ({ ...s, visible: false }))
      refresh()
    } catch {
      message.error('保存失败，请稍后重试')
    }
  }

  const saveAsGolden = async (row: EvalRow) => {
    try {
      const res = await http.post<{ id: number }>(`/eval/golden-cases/from-pipeline/${row.pipeline_id}`, {})
      message.success(`已存为 Golden case #${res?.id ?? ''}（可在 Golden 用例页编辑标准）`)
    } catch (e: unknown) {
      message.error(((e as { message?: string })?.message) || '存为 Golden 失败')
    }
  }

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const [list, s] = await Promise.all([
        http.get<EvalRow[]>('/flow/pipeline/eval/list?limit=100'),
        http.get<EvalStats>('/flow/pipeline/eval/stats?days=30'),
      ])
      setRows(list || [])
      setStats(s || null)
    } catch {
      /* ignore — stats remain stale */
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const maxTrend = Math.max(1, ...(stats?.daily_trend?.map((t) => t.avg_score) || [1]))

  return (
    <div style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16, gap: 12 }}>
        <Text strong style={{ fontSize: 18, color: '#111827' }}>
          流水线质量看板
        </Text>
        <Button size="small" icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
          刷新
        </Button>
      </div>

      <Spin spinning={loading}>
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card>
              <Statistic title="Pipeline 数（30 天）" value={stats?.total ?? '-'} />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="平均综合分"
                value={stats?.avg_overall_score ?? '-'}
                suffix={stats?.avg_overall_score != null ? '/100' : ''}
                valueStyle={{ color: scoreColor(stats?.avg_overall_score) }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="Review 通过率"
                value={pct(stats?.review_pass_rate)}
                valueStyle={{ color: '#22c55e' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="Tests 通过率"
                value={pct(stats?.tests_pass_rate)}
                valueStyle={{ color: '#22c55e' }}
              />
            </Card>
          </Col>
        </Row>

        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={12}>
            <Card title="质量分桶分布" size="small" style={{ height: '100%' }}>
              {stats && stats.total > 0 ? (
                <Row gutter={8}>
                  {(
                    [
                      ['<60', stats.score_buckets.lt60, '#ef4444'],
                      ['60-80', stats.score_buckets['60_80'], '#f59e0b'],
                      ['≥80', stats.score_buckets.gte80, '#22c55e'],
                    ] as const
                  ).map(([label, n, color]) => (
                    <Col span={8} key={label}>
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: 24, fontWeight: 600, color }}>{n}</div>
                        <Text style={{ fontSize: 12 }}>{label}</Text>
                      </div>
                    </Col>
                  ))}
                </Row>
              ) : (
                <Empty description="暂无数据" />
              )}
            </Card>
          </Col>
          <Col span={12}>
            <Card title="综合分趋势（按天）" size="small" style={{ height: '100%' }}>
              {stats && stats.daily_trend.length > 0 ? (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'flex-end',
                    gap: 4,
                    height: 120,
                    padding: '0 8px',
                  }}
                >
                  {stats.daily_trend.map((t) => (
                    <div
                      key={t.date}
                      style={{ flex: 1, textAlign: 'center', height: '100%' }}
                      title={`${t.date}: 均分 ${t.avg_score}（${t.count} 条）`}
                    >
                      <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', height: '100%' }}>
                        <div
                          style={{
                            height: `${(t.avg_score / maxTrend) * 100}%`,
                            minHeight: 4,
                            background: scoreColor(t.avg_score),
                            borderRadius: 4,
                          }}
                        />
                        <Text style={{ fontSize: 9, color: '#94a3b8', display: 'block', marginTop: 4 }}>
                          {t.date.slice(5)}
                        </Text>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty description="暂无数据" />
              )}
            </Card>
          </Col>
        </Row>

        <Card title="Pipeline 列表（按综合分可排序）" size="small">
          <Table<EvalRow>
            rowKey="pipeline_id"
            dataSource={rows}
            size="small"
            pagination={{ pageSize: 20 }}
            columns={[
              { title: '需求', dataIndex: 'user_request', ellipsis: true, width: 260 },
              {
                title: '状态',
                dataIndex: 'status',
                width: 100,
                render: (s: string) => (
                  <Tag color={s === 'completed' ? 'success' : s === 'failed' ? 'error' : 'processing'}>
                    {s}
                  </Tag>
                ),
              },
              {
                title: '综合分',
                dataIndex: 'overall_score',
                width: 90,
                sorter: (a, b) => (a.overall_score ?? -1) - (b.overall_score ?? -1),
                render: (s: number | null) =>
                  s === null ? '-' : <Text strong style={{ color: scoreColor(s) }}>{s}</Text>,
              },
              { title: 'PM', dataIndex: 'pm_quality_score', width: 64, render: (s: number | null) => s ?? '-' },
              { title: '设计', dataIndex: 'design_quality_score', width: 64, render: (s: number | null) => s ?? '-' },
              { title: '预览', dataIndex: 'preview_quality_score', width: 64, render: (s: number | null) => s ?? '-' },
              {
                title: 'Judge',
                dataIndex: 'judge_score',
                width: 76,
                sorter: (a, b) => (a.judge_score ?? -1) - (b.judge_score ?? -1),
                render: (s: number | null) =>
                  s === null ? '-' : <Text strong style={{ color: scoreColor(s) }}>{s}</Text>,
              },
              { title: '幻觉', dataIndex: 'hallucination_score', width: 64, render: (s: number | null) => s ?? '-' },
              { title: '视觉', dataIndex: 'vision_score', width: 64, render: (s: number | null) => s ?? '-' },
              {
                title: 'E2E',
                dataIndex: 'e2e_passed',
                width: 70,
                render: (v: number | null) =>
                  v === null ? '-' : <Tag color={v ? 'success' : 'error'}>{v ? '通过' : '未过'}</Tag>,
              },
              {
                title: '人工分',
                dataIndex: 'human_score',
                width: 76,
                sorter: (a, b) => (a.human_score ?? -1) - (b.human_score ?? -1),
                render: (s: number | null) =>
                  s === null || s === undefined ? '-' : <Text strong style={{ color: scoreColor(s) }}>{s}</Text>,
              },
              {
                title: 'Review',
                dataIndex: 'review_passed',
                width: 80,
                render: (v: number | null) =>
                  v === null ? '-' : <Tag color={v ? 'success' : 'error'}>{v ? '通过' : '未过'}</Tag>,
              },
              {
                title: '测试',
                dataIndex: 'tests_passed',
                width: 80,
                render: (v: number | null) =>
                  v === null ? '-' : <Tag color={v ? 'success' : 'error'}>{v ? '通过' : '未过'}</Tag>,
              },
              { title: 'Retry', dataIndex: 'retry_count', width: 64 },
              {
                title: '操作',
                width: 170,
                render: (_: unknown, row: EvalRow) => (
                  <Space size={0}>
                    <Button size="small" type="link" onClick={() => openScoreModal(row)}>人工评分</Button>
                    <Button size="small" type="link" onClick={() => saveAsGolden(row)}>存为 golden</Button>
                  </Space>
                ),
              },
            ]}
          />
        </Card>
      </Spin>

      <Modal
        title="人工评分"
        open={scoreModal.visible}
        onOk={submitScore}
        onCancel={() => setScoreModal((s) => ({ ...s, visible: false }))}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <div style={{ marginBottom: 12 }}>
          <Text>分数（0-100，用于校准 LLM judge）</Text>
          <InputNumber
            min={0}
            max={100}
            value={scoreModal.score}
            onChange={(v) => setScoreModal((s) => ({ ...s, score: Number(v) || 0 }))}
            style={{ width: '100%', marginTop: 4 }}
          />
        </div>
        <div>
          <Text>评语（可选）</Text>
          <Input.TextArea
            rows={3}
            value={scoreModal.comment}
            onChange={(e) => setScoreModal((s) => ({ ...s, comment: e.target.value }))}
            style={{ marginTop: 4 }}
          />
        </div>
      </Modal>
    </div>
  )
}
