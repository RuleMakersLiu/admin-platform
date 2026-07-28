import { useCallback, useEffect, useState } from 'react'
import {
  Button, Card, Col, Empty, Row, Select, Skeleton, Statistic, Table, Tag, Typography, message,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { http } from '@/services/api'

const { Title, Text } = Typography

interface ModelRow {
  model: string
  calls: number
  success_rate: number | null
  avg_latency_ms: number
  p50_ms: number
  p95_ms: number
  avg_ttft_ms: number
  tokens_per_s: number | null
  input_tokens: number
  output_tokens: number
  cost: number
}

interface Metrics {
  window_hours: number
  speed: {
    overall: {
      calls: number
      success_rate: number | null
      avg_latency_ms: number
      tokens_per_s: number | null
      input_tokens: number
      output_tokens: number
      cost: number
    }
    by_model: ModelRow[]
  }
  accuracy: { judged: number; passed: number; pass_rate: number | null; avg_score: number }
  quality: { avg_score: number; judged: number }
  cost: { input_tokens: number; output_tokens: number; cost: number }
}

const scoreColor = (v: number | null) => (v == null ? '#8c8c8c' : v >= 80 ? '#52c41a' : v >= 60 ? '#faad14' : '#ff4d4f')

export default function AiMetricsPage() {
  const [hours, setHours] = useState(24)
  const [data, setData] = useState<Metrics | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await http.get<Metrics>(`/eval/metrics?hours=${hours}`)
      setData(res)
    } catch (e) {
      message.error((e as Error).message || '加载指标失败')
    } finally {
      setLoading(false)
    }
  }, [hours])

  useEffect(() => { load() }, [load])

  const o = data?.speed.overall
  const acc = data?.accuracy

  return (
    <div style={{ padding: 24 }}>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col><Title level={4} style={{ margin: 0 }}>AI 效果评测看板</Title></Col>
        <Col>
          <Select
            value={hours}
            onChange={setHours}
            style={{ width: 160, marginRight: 8 }}
            options={[
              { value: 1, label: '近 1 小时' },
              { value: 6, label: '近 6 小时' },
              { value: 24, label: '近 24 小时' },
              { value: 168, label: '近 7 天' },
              { value: 720, label: '近 30 天' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
        </Col>
      </Row>

      <Skeleton loading={loading && !data} active>
        {data ? (
          <>
            {/* 维度总览 */}
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={12} xl={6}>
                <Card title="响应速度" size="small">
                  <Statistic title="平均延迟" value={o?.avg_latency_ms ?? 0} suffix="ms"
                    valueStyle={{ color: (o?.avg_latency_ms ?? 0) <= 3000 ? '#52c41a' : (o?.avg_latency_ms ?? 0) <= 8000 ? '#faad14' : '#ff4d4f' }} />
                  <Row gutter={16} style={{ marginTop: 8 }}>
                    <Col span={12}><Text type="secondary">tokens/s </Text><Text strong>{o?.tokens_per_s ?? '-'}</Text></Col>
                    <Col span={12}><Text type="secondary">调用 </Text><Text>{o?.calls ?? 0}</Text></Col>
                  </Row>
                  <div style={{ marginTop: 6 }}>
                    <Text type="secondary">成功率 </Text>
                    <Tag color={scoreColor(o?.success_rate ?? null)}>{o?.success_rate == null ? '-' : o.success_rate + '%'}</Tag>
                  </div>
                </Card>
              </Col>
              <Col xs={24} lg={12} xl={6}>
                <Card title="准确率" size="small">
                  <Statistic title="通过率 (golden)" value={acc?.pass_rate ?? 0} suffix="%"
                    valueStyle={{ color: scoreColor(acc?.pass_rate ?? null) }} />
                  <Row gutter={16} style={{ marginTop: 8 }}>
                    <Col span={12}><Text type="secondary">通过 </Text><Text>{acc?.passed ?? 0}</Text></Col>
                    <Col span={12}><Text type="secondary">已评 </Text><Text>{acc?.judged ?? 0}</Text></Col>
                  </Row>
                </Card>
              </Col>
              <Col xs={24} lg={12} xl={6}>
                <Card title="生成效果" size="small">
                  <Statistic title="平均评分" value={data?.quality.avg_score ?? 0} suffix="/100"
                    valueStyle={{ color: scoreColor(data?.quality.avg_score ?? null) }} />
                  <div style={{ marginTop: 8 }}><Text type="secondary">基于 {data?.quality.judged ?? 0} 次评审</Text></div>
                </Card>
              </Col>
              <Col xs={24} lg={12} xl={6}>
                <Card title="成本" size="small">
                  <Statistic title="花费" value={data?.cost.cost ?? 0} precision={4} prefix="$" />
                  <Row gutter={16} style={{ marginTop: 8 }}>
                    <Col span={12}><Text type="secondary">入 tokens </Text><Text>{data?.cost.input_tokens ?? 0}</Text></Col>
                    <Col span={12}><Text type="secondary">出 tokens </Text><Text>{data?.cost.output_tokens ?? 0}</Text></Col>
                  </Row>
                </Card>
              </Col>
            </Row>

            {/* 按模型明细 */}
            <Card title={`按模型明细 · 近 ${data.window_hours} 小时`} size="small" style={{ marginTop: 16 }}>
              {data.speed.by_model.length ? (
                <Table<ModelRow>
                  rowKey="model"
                  size="small"
                  pagination={false}
                  dataSource={data.speed.by_model}
                  columns={[
                    { title: '模型', dataIndex: 'model', key: 'model' },
                    { title: '调用', dataIndex: 'calls', key: 'calls', sorter: (a, b) => a.calls - b.calls },
                    {
                      title: '成功率', dataIndex: 'success_rate', key: 'success_rate',
                      render: (v: number | null) => v == null ? '-' : <Tag color={scoreColor(v)}>{v}%</Tag>,
                      sorter: (a, b) => (a.success_rate ?? 0) - (b.success_rate ?? 0),
                    },
                    { title: '均延迟(ms)', dataIndex: 'avg_latency_ms', key: 'avg', sorter: (a, b) => a.avg_latency_ms - b.avg_latency_ms },
                    { title: 'P50(ms)', dataIndex: 'p50_ms', key: 'p50' },
                    { title: 'P95(ms)', dataIndex: 'p95_ms', key: 'p95', sorter: (a, b) => a.p95_ms - b.p95_ms },
                    { title: '首字(ms)', dataIndex: 'avg_ttft_ms', key: 'ttft' },
                    { title: 'tokens/s', dataIndex: 'tokens_per_s', key: 'tps', render: (v: number | null) => v ?? '-' },
                    { title: '出 tokens', dataIndex: 'output_tokens', key: 'out' },
                    { title: '花费($)', dataIndex: 'cost', key: 'cost', render: (v: number) => v.toFixed(4) },
                  ]}
                />
              ) : (
                <Empty description="该时间窗口内还没有已采集的 LLM 调用。发几条对话/跑条流水线后刷新即可。" />
              )}
            </Card>
          </>
        ) : null}
      </Skeleton>
    </div>
  )
}
