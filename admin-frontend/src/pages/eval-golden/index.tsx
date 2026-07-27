import { useCallback, useEffect, useState } from 'react'
import {
  Button, Card, Form, Input, Modal, Popconfirm, Space, Switch, Table, Tag, Typography, message,
} from 'antd'
import { PlusOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { http } from '@/services/api'

const { TextArea } = Input
const { Text, Paragraph } = Typography

interface GoldenCase {
  id: number
  name: string
  category: string
  project_type?: string | null
  input_spec: unknown
  expected_criteria: unknown
  tags?: string | null
  enabled: number
  create_time: number
}

interface CriterionResult {
  criterion: string
  score: number | null
  passed: boolean
  reason: string
}
interface JudgeResult {
  overall_score: number | null
  per_criterion?: CriterionResult[]
  summary?: string
  error?: string
  model?: string
}

// TextArea 值 → 文本或 JSON（与后端 to_storage 对齐）
function parseField(v: string): unknown {
  const s = (v || '').trim()
  if (!s) return ''
  try {
    return JSON.parse(s)
  } catch {
    return s
  }
}
function stringifyField(v: unknown): string {
  if (v == null) return ''
  if (typeof v === 'string') return v
  return JSON.stringify(v, null, 2)
}

export default function EvalGoldenPage() {
  const [cases, setCases] = useState<GoldenCase[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<GoldenCase | null>(null)
  const [form] = Form.useForm()

  const [judgeOpen, setJudgeOpen] = useState(false)
  const [judgeCase, setJudgeCase] = useState<GoldenCase | null>(null)
  const [judgeOutput, setJudgeOutput] = useState('')
  const [judgeResult, setJudgeResult] = useState<JudgeResult | null>(null)
  const [judgeLoading, setJudgeLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await http.get<GoldenCase[]>('/eval/golden-cases?limit=200')
      setCases(data || [])
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ category: 'general', enabled: true })
    setModalOpen(true)
  }

  const openEdit = (c: GoldenCase) => {
    setEditing(c)
    form.setFieldsValue({
      name: c.name,
      category: c.category,
      project_type: c.project_type || '',
      input_spec: stringifyField(c.input_spec),
      expected_criteria: stringifyField(c.expected_criteria),
      tags: c.tags || '',
      enabled: c.enabled === 1,
    })
    setModalOpen(true)
  }

  const submit = async () => {
    const v = await form.validateFields()
    const body = {
      name: v.name as string,
      category: (v.category as string) || 'general',
      project_type: (v.project_type as string) || null,
      input_spec: parseField(v.input_spec as string),
      expected_criteria: parseField(v.expected_criteria as string),
      tags: (v.tags as string) || null,
      enabled: v.enabled ? 1 : 0,
    }
    try {
      if (editing) {
        await http.put(`/eval/golden-cases/${editing.id}`, body)
        message.success('已更新')
      } else {
        await http.post('/eval/golden-cases', body)
        message.success('已创建')
      }
      setModalOpen(false)
      load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存失败')
    }
  }

  const remove = async (id: number) => {
    try {
      await http.delete(`/eval/golden-cases/${id}`)
      message.success('已删除')
      load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '删除失败')
    }
  }

  const openJudge = (c: GoldenCase) => {
    setJudgeCase(c)
    setJudgeOutput('')
    setJudgeResult(null)
    setJudgeOpen(true)
  }

  const runJudge = async () => {
    if (!judgeCase) return
    setJudgeLoading(true)
    setJudgeResult(null)
    try {
      const res = await http.post<JudgeResult>('/eval/golden-cases/judge', {
        golden_case_id: judgeCase.id,
        output: judgeOutput,
      })
      setJudgeResult(res)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '评审失败')
    } finally {
      setJudgeLoading(false)
    }
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: '名称', dataIndex: 'name' },
    {
      title: '分类', dataIndex: 'category', width: 110,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    { title: '项目类型', dataIndex: 'project_type', width: 120, render: (v?: string) => v || '-' },
    {
      title: '启用', dataIndex: 'enabled', width: 80,
      render: (v: number) => <Tag color={v === 1 ? 'green' : 'default'}>{v === 1 ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作', width: 220, render: (_: unknown, row: GoldenCase) => (
        <Space>
          <Button size="small" icon={<ThunderboltOutlined />} onClick={() => openJudge(row)}>评审</Button>
          <Button size="small" onClick={() => openEdit(row)}>编辑</Button>
          <Popconfirm title="确认删除该 Golden case？" onConfirm={() => remove(row.id)}>
            <Button size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card
      title="评测 Golden Cases"
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建</Button>
        </Space>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        dataSource={cases}
        columns={columns}
        pagination={{ pageSize: 10 }}
      />

      <Modal
        title={editing ? '编辑 Golden case' : '新建 Golden case'}
        open={modalOpen}
        onOk={submit}
        onCancel={() => setModalOpen(false)}
        width={680}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true, min: 1, max: 128 }]}>
            <Input placeholder="如：商品列表页-基础回归" />
          </Form.Item>
          <Space style={{ display: 'flex' }} >
            <Form.Item name="category" label="分类" style={{ width: 200 }}>
              <Input placeholder="frontend / backend / general" />
            </Form.Item>
            <Form.Item name="project_type" label="项目类型" style={{ width: 200 }}>
              <Input placeholder="可选" />
            </Form.Item>
            <Form.Item name="enabled" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Space>
          <Form.Item name="input_spec" label="需求 / 输入（文本或 JSON）" rules={[{ required: true }]}>
            <TextArea rows={4} placeholder={'实现一个支持手机号验证码登录的页面\n或 JSON：{"requirement": "..."}'} />
          </Form.Item>
          <Form.Item name="expected_criteria" label="评判标准（文本或 JSON 数组）" rules={[{ required: true }]}>
            <TextArea rows={4} placeholder={'有登录表单\n支持验证码\n或 ["有登录表单", "支持验证码"]'} />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Input placeholder="逗号分隔，可选" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`LLM 评审${judgeCase ? ' · ' + judgeCase.name : ''}`}
        open={judgeOpen}
        onCancel={() => setJudgeOpen(false)}
        width={720}
        footer={
          <Space>
            <Button onClick={() => setJudgeOpen(false)}>关闭</Button>
            <Button type="primary" loading={judgeLoading} onClick={runJudge} disabled={!judgeOutput.trim()}>
              运行评审
            </Button>
          </Space>
        }
      >
        <Text type="secondary">粘贴待评审的产物（代码 / 文档 / 设计说明）：</Text>
        <TextArea rows={6} value={judgeOutput} onChange={(e) => setJudgeOutput(e.target.value)} style={{ marginTop: 8 }} />
        {judgeResult && (
          <div style={{ marginTop: 16 }}>
            {judgeResult.error ? (
              <Text type="danger">评审失败：{judgeResult.error}</Text>
            ) : (
              <>
                <Space align="center">
                  <Text>综合分：</Text>
                  <Text strong style={{ fontSize: 22, color: (judgeResult.overall_score ?? 0) >= 60 ? '#52c41a' : '#ff4d4f' }}>
                    {judgeResult.overall_score ?? '-'}
                  </Text>
                  {judgeResult.model && <Text type="secondary">（{judgeResult.model}）</Text>}
                </Space>
                {judgeResult.summary && <Paragraph style={{ marginTop: 8 }}>{judgeResult.summary}</Paragraph>}
                <Table
                  size="small"
                  rowKey={(_, i) => String(i)}
                  style={{ marginTop: 8 }}
                  pagination={false}
                  dataSource={judgeResult.per_criterion || []}
                  columns={[
                    { title: '标准', dataIndex: 'criterion' },
                    { title: '分数', dataIndex: 'score', width: 70 },
                    {
                      title: '通过', dataIndex: 'passed', width: 70,
                      render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? '通过' : '未过'}</Tag>,
                    },
                    { title: '理由', dataIndex: 'reason' },
                  ]}
                />
              </>
            )}
          </div>
        )}
      </Modal>
    </Card>
  )
}
