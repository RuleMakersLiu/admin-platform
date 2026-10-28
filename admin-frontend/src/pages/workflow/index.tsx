/**
 * 工作流编排（Workflow Studio）：Dify 式可视化画布。
 *
 * 三层架构的前端层：React Flow 画布 ⇄ DSL（存后端 draft/published）⇄ LangGraph 编译执行。
 * 左侧为节点面板（后端注册表驱动），点击节点可配置（antd Form 按字段 schema 渲染），
 * 边可配置 when 条件表达式；运行面板轮询执行状态，waiting_human 时可录入恢复值。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ReactFlow, Background, Controls, MiniMap, Handle, Position, addEdge,
  useEdgesState, useNodesState,
  type Connection, type Edge, type Node, type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  Alert, Button, Card, Drawer, Empty, Form, Input, Modal, Select, Space, Tag, Typography, message,
} from 'antd'
import { PlayCircleOutlined, PlusOutlined, SaveOutlined, SendOutlined, UploadOutlined } from '@ant-design/icons'
import {
  workflowApi, type WfDefinition, type WfDsl, type WfNodeType, type WfRun,
} from '@/services/api'

const NODE_COLORS: Record<string, string> = {
  start: '#52c41a', llm: '#1677ff', condition: '#fa8c16',
  human_input: '#722ed1', end: '#8c8c8c',
}

type WfNodeData = {
  type: string
  label: string
  config: Record<string, unknown>
  fields: WfNodeType['fields']
}

function WorkflowNodeCard({ data }: NodeProps) {
  const wf = (data ?? {}) as unknown as WfNodeData
  const color = NODE_COLORS[wf.type] || '#1677ff'
  return (
    <div style={{
      padding: '8px 14px', borderRadius: 8, minWidth: 120, textAlign: 'center',
      border: `2px solid ${color}`, background: '#fff', boxShadow: '0 2px 6px rgba(0,0,0,.08)',
    }}>
      <Handle type="target" position={Position.Left} />
      <div style={{ fontWeight: 600 }}>{wf.label || wf.type}</div>
      <div style={{ fontSize: 12, color: '#888' }}>{wf.type}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

const nodeTypes = { wf: WorkflowNodeCard }

const EMPTY_DSL: WfDsl = {
  version: 1,
  nodes: [
    { id: 'start', type: 'start', name: '开始', config: {}, position: { x: 60, y: 200 } },
    { id: 'end', type: 'end', name: '结束', config: {}, position: { x: 640, y: 200 } },
  ],
  edges: [{ from: 'start', to: 'end' }],
}

function toCanvas(dsl: WfDsl, registry: WfNodeType[]) {
  const nodes: Node[] = (dsl.nodes || []).map((n) => ({
    id: n.id, type: 'wf', position: n.position || { x: 0, y: 0 },
    data: {
      type: n.type, label: n.name || n.type, config: n.config || {},
      fields: registry.find((r) => r.type === n.type)?.fields || [],
    } as unknown as Record<string, unknown>,
  }))
  const edges: Edge[] = (dsl.edges || []).map((e, i) => ({
    id: `e-${e.from}-${e.to}-${i}`, source: e.from, target: e.to,
    label: e.when || undefined, animated: true,
  }))
  return { nodes, edges }
}

export default function WorkflowStudio() {
  const [registry, setRegistry] = useState<WfNodeType[]>([])
  const [defs, setDefs] = useState<WfDefinition[]>([])
  const [currentId, setCurrentId] = useState<string>('')
  const [name, setName] = useState('未命名工作流')
  const [status, setStatus] = useState<'draft' | 'published'>('draft')
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([] as Node[])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([] as Edge[])
  const [drawer, setDrawer] = useState<{ kind: 'node' | 'edge'; id: string } | null>(null)
  const [run, setRun] = useState<WfRun | null>(null)
  const [runModalOpen, setRunModalOpen] = useState(false)
  const [inputsText, setInputsText] = useState('{}')
  const [resumeText, setResumeText] = useState('true')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [form] = Form.useForm()
  const [messageApi, contextHolder] = message.useMessage()

  useEffect(() => {
    workflowApi.listNodeTypes().then(setRegistry).catch(() => messageApi.error('节点类型加载失败'))
    workflowApi.listDefinitions().then((list) => {
      setDefs(list || [])
      if (list?.length) loadDefinition(list[0], registry)
    }).catch(() => messageApi.error('工作流列表加载失败'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadDefinition = (def: WfDefinition, reg?: WfNodeType[]) => {
    const r = reg ?? registry
    setCurrentId(def.workflow_id)
    setName(def.name)
    setStatus(def.status)
    const { nodes: ns, edges: es } = toCanvas(def.dsl || EMPTY_DSL, r)
    setNodes(ns)
    setEdges(es)
    setRun(null)
  }

  const currentDsl = useCallback(() => ({
    version: 1,
    name,
    nodes: nodes.map((n) => {
      const d = n.data as unknown as WfNodeData
      return {
        id: n.id, type: d.type, name: d.label, config: d.config || {},
        position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
      }
    }),
    edges: edges.map((e) => ({
      from: e.source, to: e.target,
      when: typeof e.label === 'string' && e.label ? e.label : undefined,
    })),
  }), [nodes, edges, name])

  const onConnect = useCallback(
    (c: Connection) => setEdges((eds) => addEdge({ ...c, animated: true }, eds)),
    [setEdges],
  )

  const addNode = (spec: WfNodeType) => {
    const id = `${spec.type}_${Date.now().toString(36).slice(-4)}`
    setNodes((ns) => [...ns, {
      id, type: 'wf',
      position: { x: 200 + Math.random() * 260, y: 80 + Math.random() * 260 },
      data: {
        type: spec.type, label: spec.name,
        config: Object.fromEntries((spec.fields || []).map((f) => [f.key, f.default ?? ''])),
        fields: spec.fields,
      } as unknown as Record<string, unknown>,
    }])
  }

  const save = async (publish = false) => {
    const dsl = currentDsl()
    try {
      if (currentId) {
        await workflowApi.updateDefinition(currentId, { name, dsl })
        if (publish) await workflowApi.publishDefinition(currentId)
      } else {
        const created = await workflowApi.createDefinition({ name, dsl })
        setCurrentId(created.workflow_id)
        if (publish) await workflowApi.publishDefinition(created.workflow_id)
      }
      setStatus(publish ? 'published' : 'draft')
      const list = await workflowApi.listDefinitions()
      setDefs(list || [])
      messageApi.success(publish ? '已发布' : '已保存')
    } catch (e) {
      messageApi.error(`保存失败：${(e as Error).message}`)
    }
  }

  const startRun = async () => {
    if (!currentId) { messageApi.warning('请先保存工作流'); return }
    let inputs: Record<string, unknown> = {}
    try { inputs = JSON.parse(inputsText || '{}') } catch { messageApi.error('inputs 不是合法 JSON'); return }
    try {
      const { run_id } = await workflowApi.startRun(currentId, inputs)
      setRunModalOpen(false)
      setRun({ run_id, workflow_id: currentId, status: 'running', inputs, outputs: {}, error: '', waiting_node: '', waiting_message: '' })
      if (pollRef.current) clearInterval(pollRef.current)
      pollRef.current = setInterval(async () => {
        try {
          const r = await workflowApi.getRun(currentId, run_id)
          setRun(r)
          if (r.status !== 'running') { clearInterval(pollRef.current!) ; pollRef.current = null }
        } catch { /* 轮询失败静默重试 */ }
      }, 1500)
    } catch (e) {
      messageApi.error(`启动失败：${(e as Error).message}`)
    }
  }

  const resumeRun = async () => {
    if (!run || !currentId) return
    let value: unknown = true
    try {
      value = JSON.parse(resumeText || 'true')
    } catch { /* 非法 JSON 按字符串处理 */ value = resumeText }
    try {
      await workflowApi.resumeRun(currentId, run.run_id, value)
      const poll = setInterval(async () => {
        const r = await workflowApi.getRun(currentId, run.run_id)
        setRun(r)
        if (r.status !== 'running') { clearInterval(poll); pollRef.current = null }
      }, 1500)
      pollRef.current = poll
    } catch (e) {
      messageApi.error(`恢复失败：${(e as Error).message}`)
    }
  }

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  const drawerNode = useMemo(
    () => drawer?.kind === 'node' ? nodes.find((n) => n.id === drawer.id) : null,
    [drawer, nodes],
  )
  const drawerEdge = useMemo(
    () => drawer?.kind === 'edge' ? edges.find((e) => e.id === drawer.id) : null,
    [drawer, edges],
  )

  const openNodeDrawer = (nodeId: string) => {
    const node = nodes.find((n) => n.id === nodeId)
    if (node) { setDrawer({ kind: 'node', id: nodeId }); form.setFieldsValue((node.data as unknown as WfNodeData).config) }
  }

  const categories = useMemo(() => {
    const m = new Map<string, WfNodeType[]>()
    registry.forEach((t) => m.set(t.category, [...(m.get(t.category) || []), t]))
    return [...m.entries()]
  }, [registry])

  const runStatusTag = (s?: string) => (
    <Tag color={s === 'completed' ? 'green' : s === 'failed' ? 'red' : s === 'waiting_human' ? 'purple' : 'blue'}>
      {s}
    </Tag>
  )

  return (
    <Card
      title={<Space>工作流编排<Tag>{status === 'published' ? '已发布' : '草稿'}</Tag></Space>}
      extra={
        <Space wrap>
          <Select
            style={{ minWidth: 180 }} placeholder="选择工作流" value={currentId || undefined}
            options={defs.map((d) => ({ value: d.workflow_id, label: d.name }))}
            onChange={(v) => { const d = defs.find((x) => x.workflow_id === v); if (d) loadDefinition(d) }}
          />
          <Input style={{ width: 160 }} value={name} onChange={(e) => setName(e.target.value)} placeholder="工作流名称" />
          <Button icon={<SaveOutlined />} onClick={() => save(false)}>保存</Button>
          <Button icon={<UploadOutlined />} onClick={() => save(true)}>发布</Button>
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => setRunModalOpen(true)}>运行</Button>
        </Space>
      }
    >
      {contextHolder}
      <div style={{ display: 'flex', gap: 12, height: 'calc(100vh - 210px)' }}>
        <div style={{ width: 190, borderRight: '1px solid #f0f0f0', paddingRight: 8, overflowY: 'auto' }}>
          {categories.map(([cat, types]) => (
            <div key={cat} style={{ marginBottom: 12 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>{cat}</Typography.Text>
              {types.map((t) => (
                <div key={t.type} title={t.description}
                  onClick={() => addNode(t)}
                  style={{
                    margin: '4px 0', padding: '6px 10px', borderRadius: 6, cursor: 'pointer',
                    border: `1px solid ${NODE_COLORS[t.type] || '#d9d9d9'}`, fontSize: 13,
                  }}>
                  <PlusOutlined style={{ color: NODE_COLORS[t.type], marginRight: 6 }} />{t.name}
                </div>
              ))}
            </div>
          ))}
        </div>

        <div style={{ flex: 1 }}>
          <ReactFlow
            nodes={nodes} edges={edges}
            onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
            onConnect={onConnect} nodeTypes={nodeTypes}
            onNodeDoubleClick={(_, n) => openNodeDrawer(n.id)}
            onEdgeDoubleClick={(_, e) => { setDrawer({ kind: 'edge', id: e.id }); form.setFieldsValue({ when: e.label || '' }) }}
            fitView
          >
            <Background /> <Controls /> <MiniMap />
          </ReactFlow>
        </div>

        <div style={{ width: 320, borderLeft: '1px solid #f0f0f0', paddingLeft: 12, overflowY: 'auto' }}>
          <Typography.Title level={5}>运行结果</Typography.Title>
          {!run && <Empty description="点击「运行」执行工作流" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
          {run && (
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <div>{runStatusTag(run.status)} <Typography.Text code>{run.run_id}</Typography.Text></div>
              {run.status === 'waiting_human' && (
                <Alert type="warning" showIcon
                  message={`等待人工输入（${run.waiting_node}）`}
                  description={
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <div>{run.waiting_message}</div>
                      <Input.Group compact>
                        <Input style={{ width: 'calc(100% - 72px)' }} value={resumeText} onChange={(e) => setResumeText(e.target.value)} />
                        <Button type="primary" icon={<SendOutlined />} onClick={resumeRun}>恢复</Button>
                      </Input.Group>
                    </Space>
                  }
                />
              )}
              {run.status === 'failed' && <Alert type="error" message="执行失败" description={run.error} />}
              {Object.entries(run.outputs || {}).map(([nodeId, out]) => (
                <div key={nodeId} style={{ borderTop: '1px dashed #eee', paddingTop: 6 }}>
                  <Typography.Text strong>{nodeId}</Typography.Text>
                  <pre style={{ margin: '4px 0 0', fontSize: 12, background: '#fafafa', padding: 6, borderRadius: 6, maxHeight: 160, overflow: 'auto' }}>
                    {JSON.stringify(out, null, 2)}
                  </pre>
                </div>
              ))}
            </Space>
          )}
        </div>
      </div>

      <Drawer
        title={drawerNode ? `节点配置：${(drawerNode.data as unknown as WfNodeData).label}` : '边条件'}
        open={!!drawer} onClose={() => setDrawer(null)} width={420}
        extra={<Button type="primary" size="small" onClick={() => setDrawer(null)}>完成</Button>}
      >
        {drawerNode && (
          <Form form={form} layout="vertical"
            onValuesChange={(_, all) => {
              const d = drawerNode.data as unknown as WfNodeData
              setNodes((ns) => ns.map((n) => n.id === drawerNode.id
                ? { ...n, data: { ...d, config: all } as unknown as Record<string, unknown> } : n))
            }}>
            {(drawerNode.data as unknown as WfNodeData).fields?.map((f) => (
              <Form.Item key={f.key} name={f.key} label={f.label} rules={f.required ? [{ required: true }] : []}>
                {f.type === 'text' ? (
                  <Input.TextArea rows={3} placeholder={f.placeholder} />
                ) : f.type === 'select' ? (
                  <Select options={f.options} />
                ) : (
                  <Input placeholder={f.placeholder} />
                )}
              </Form.Item>
            ))}
          </Form>
        )}
        {drawerEdge && (
          <Form form={form} layout="vertical">
            <Form.Item name="when" label="when 条件表达式（留空 = 无条件）"
              extra="分支节点出边示例：vars.cond.result == true；支持 input.x / 节点ID.字段、len() 等白名单函数">
              <Input
                onChange={(e) => setEdges((es) => es.map((x) => x.id === drawerEdge.id
                  ? { ...x, label: e.target.value || undefined } : x))}
              />
            </Form.Item>
          </Form>
        )}
      </Drawer>

      <Modal title="运行工作流" open={runModalOpen} onOk={startRun} onCancel={() => setRunModalOpen(false)} okText="运行">
        <Typography.Paragraph type="secondary">运行入参（JSON，模板中用 {'{{#input.变量名}}'} 引用）</Typography.Paragraph>
        <Input.TextArea rows={5} value={inputsText} onChange={(e) => setInputsText(e.target.value)} />
      </Modal>
    </Card>
  )
}
