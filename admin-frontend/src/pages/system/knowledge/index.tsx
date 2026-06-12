import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import type { MouseEvent, WheelEvent } from 'react'
import {
  Table,
  Card,
  Button,
  Space,
  Tag,
  message,
  Popconfirm,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  Tooltip,
  Skeleton,
  Empty,
  Tabs,
  Row,
  Col,
  Statistic,
  Typography,
} from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  BookOutlined,
  SearchOutlined,
  ApartmentOutlined,
  ReloadOutlined,
  LinkOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  knowledgeService,
  knowledgeCategories,
  agentTypeOptions,
  commonTags,
  type Knowledge,
  type KnowledgeForm,
  type KnowledgeGraph,
} from '@/services/knowledge'

const { Option } = Select
const { TextArea } = Input
const { Text } = Typography

const graphNodeColors: Record<string, string> = {
  frontend: '#1677ff',
  api: '#13c2c2',
  service: '#52c41a',
  core: '#fa8c16',
  project: '#8c8c8c',
  project_analysis: '#1677ff',
  pipeline_delivery: '#52c41a',
  ai_upgrade: '#eb2f96',
  product: '#1677ff',
  technical: '#52c41a',
  business: '#fa8c16',
  faq: '#722ed1',
  guide: '#13c2c2',
  best_practice: '#d48806',
  other: '#8c8c8c',
}

type GraphPoint = { x: number; y: number }
type GraphPositions = Record<string, GraphPoint>
type GraphViewport = { x: number; y: number; scale: number }
type GraphDragState =
  | { type: 'node'; nodeId: string; startSvg: GraphPoint; startPos: GraphPoint }
  | { type: 'pan'; startClient: GraphPoint; startViewport: GraphViewport }

const relationLabels: Record<string, string> = {
  depends_on: '依赖',
  related_to: '相关',
  derived_from: '来源',
  supersedes: '替代',
  references: '引用',
  guides: '指导',
  uses_api: '调用接口',
}

const graphCanvas = { width: 960, height: 620 }

const getRelationLabel = (relation: string) => relationLabels[relation] || relation

const shortenTitle = (title: string, max = 20) => {
  const value = title || ''
  return value.length > max ? `${value.slice(0, max)}...` : value
}

const computeGraphPositions = (nodes: KnowledgeGraph['nodes'], edges: KnowledgeGraph['edges']): GraphPositions => {
  const positions: GraphPositions = {}
  if (!nodes.length) return positions

  const nodeIds = new Set(nodes.map((node) => node.id))
  const adjacency = new Map<string, Set<string>>()
  const degree = new Map<string, number>()
  nodes.forEach((node) => {
    adjacency.set(node.id, new Set())
    degree.set(node.id, 0)
  })
  edges.forEach((edge) => {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) return
    adjacency.get(edge.source)?.add(edge.target)
    adjacency.get(edge.target)?.add(edge.source)
    degree.set(edge.source, (degree.get(edge.source) || 0) + 1)
    degree.set(edge.target, (degree.get(edge.target) || 0) + 1)
  })

  const visited = new Set<string>()
  const components: string[][] = []
  nodes.forEach((node) => {
    if (visited.has(node.id)) return
    const queue = [node.id]
    const component: string[] = []
    visited.add(node.id)
    while (queue.length) {
      const current = queue.shift()!
      component.push(current)
      adjacency.get(current)?.forEach((next) => {
        if (!visited.has(next)) {
          visited.add(next)
          queue.push(next)
        }
      })
    }
    components.push(component.sort((a, b) => (degree.get(b) || 0) - (degree.get(a) || 0)))
  })
  components.sort((a, b) => b.length - a.length)

  const columns = Math.ceil(Math.sqrt(components.length))
  const rows = Math.ceil(components.length / columns)
  const cellWidth = graphCanvas.width / Math.max(columns, 1)
  const cellHeight = graphCanvas.height / Math.max(rows, 1)

  components.forEach((component, componentIndex) => {
    const column = componentIndex % columns
    const row = Math.floor(componentIndex / columns)
    const centerX = cellWidth * column + cellWidth / 2
    const centerY = cellHeight * row + cellHeight / 2
    if (component.length === 1) {
      positions[component[0]] = { x: centerX, y: centerY }
      return
    }

    const radius = Math.min(Math.max(90, component.length * 15), Math.min(cellWidth, cellHeight) * 0.34)
    component.forEach((id, index) => {
      if (index === 0 && (degree.get(id) || 0) > 1) {
        positions[id] = { x: centerX, y: centerY }
        return
      }
      const ringIndex = (degree.get(component[0]) || 0) > 1 ? index - 1 : index
      const ringSize = (degree.get(component[0]) || 0) > 1 ? component.length - 1 : component.length
      const angle = (Math.PI * 2 * ringIndex) / Math.max(ringSize, 1) - Math.PI / 2
      const distance = radius + (ringIndex % 3) * 24
      positions[id] = {
        x: centerX + Math.cos(angle) * distance,
        y: centerY + Math.sin(angle) * distance,
      }
    })
  })

  return positions
}

// 骨架屏组件
const TableSkeleton = () => (
  <div style={{ padding: '16px 0' }}>
    <Skeleton active paragraph={{ rows: 5 }} />
  </div>
)

export default function KnowledgeList() {
  // 状态定义
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<Knowledge[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [debouncedKeyword, setDebouncedKeyword] = useState('')
  const [filterCategory, setFilterCategory] = useState<string>()
  const [filterAgentType, setFilterAgentType] = useState<string>()
  const [activeTab, setActiveTab] = useState('list')
  const [graphLoading, setGraphLoading] = useState(false)
  const [graphData, setGraphData] = useState<KnowledgeGraph>({ nodes: [], edges: [] })
  const [graphMaxNodes, setGraphMaxNodes] = useState(80)
  const [selectedGraphNodeId, setSelectedGraphNodeId] = useState<string>()
  const [graphPositions, setGraphPositions] = useState<GraphPositions>({})
  const [graphViewport, setGraphViewport] = useState<GraphViewport>({ x: 0, y: 0, scale: 1 })
  const graphSvgRef = useRef<SVGSVGElement | null>(null)
  const graphDragRef = useRef<GraphDragState | null>(null)

  // Modal states
  const [modalVisible, setModalVisible] = useState(false)
  const [modalLoading, setModalLoading] = useState(false)
  const [editingKnowledge, setEditingKnowledge] = useState<Knowledge | null>(null)

  const [form] = Form.useForm()

  // 防抖处理
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedKeyword(keyword)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [keyword])

  // 数据获取
  useEffect(() => {
    fetchData()
  }, [page, pageSize, debouncedKeyword, filterCategory, filterAgentType])

  useEffect(() => {
    if (activeTab === 'graph') {
      fetchGraph()
    }
  }, [activeTab, graphMaxNodes])

  const fetchData = async () => {
    setLoading(true)
    try {
      const result = (await knowledgeService.list({
        keyword: debouncedKeyword || undefined,
        category: filterCategory,
        agent_type: filterAgentType,
      })) as any
      setData((result?.items || result?.list || result || []).map((item: any) => ({
        ...item,
        id: item.knowledge_id || item.id,
      })))
      setTotal(result?.total || (Array.isArray(result) ? result.length : 0))
    } catch (error) {
      console.error('获取知识库列表失败:', error)
      setData([])
    } finally {
      setLoading(false)
    }
  }

  const fetchGraph = async () => {
    setGraphLoading(true)
    try {
      const result = (await knowledgeService.graph({
        max_nodes: graphMaxNodes,
      })) as unknown as KnowledgeGraph
      const nodes = result?.nodes || []
      const nodeIds = new Set(nodes.map((node) => node.id))
      setGraphData({
        nodes,
        edges: (result?.edges || []).filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)),
      })
      setGraphPositions(computeGraphPositions(nodes, result?.edges || []))
      setGraphViewport({ x: 0, y: 0, scale: 1 })
      setSelectedGraphNodeId((prev) => (prev && nodeIds.has(prev) ? prev : nodes[0]?.id))
    } catch (error) {
      console.error('获取知识图谱失败:', error)
      message.error('获取知识图谱失败')
      setGraphData({ nodes: [], edges: [] })
      setGraphPositions({})
      setSelectedGraphNodeId(undefined)
    } finally {
      setGraphLoading(false)
    }
  }

  // 事件处理
  const handleSearch = useCallback(() => {
    setPage(1)
    fetchData()
  }, [])

  const handleCreate = useCallback(() => {
    setEditingKnowledge(null)
    form.resetFields()
    form.setFieldsValue({
      status: 1,
      tags: [],
    })
    setModalVisible(true)
  }, [form])

  const handleEdit = useCallback(async (record: Knowledge) => {
    try {
      const result = (await knowledgeService.get(record.id)) as unknown as Knowledge
      setEditingKnowledge(result)
      form.setFieldsValue({
        title: result.title,
        content: result.content,
        category: result.category,
        tags: result.tags || [],
        agent_type: result.agent_type,
        status: result.status,
      })
      setModalVisible(true)
    } catch (error) {
      message.error('获取知识条目信息失败')
    }
  }, [form])

  const handleDelete = useCallback(async (id: string) => {
    try {
      await knowledgeService.delete(id)
      message.success('删除成功')
      fetchData()
    } catch (error) {
      message.error('删除失败')
    }
  }, [])

  const handleToggleStatus = useCallback(async (record: Knowledge) => {
    try {
      const newStatus = record.status === 1 ? 0 : 1
      await knowledgeService.update(record.id, { status: newStatus })
      message.success(newStatus === 1 ? '已启用' : '已禁用')
      fetchData()
    } catch (error) {
      message.error('状态切换失败')
    }
  }, [])

  const handleAutoLink = useCallback(async () => {
    if (!selectedGraphNodeId) return
    try {
      const result = (await knowledgeService.autoLink(selectedGraphNodeId)) as { count?: number }
      message.success(`自动关联完成，新增 ${result?.count || 0} 条关系`)
      fetchGraph()
    } catch (error) {
      message.error('自动关联失败')
    }
  }, [selectedGraphNodeId, graphMaxNodes])

  const getSvgPoint = useCallback((event: MouseEvent<SVGSVGElement | SVGGElement>): GraphPoint => {
    const svg = graphSvgRef.current
    if (!svg) return { x: 0, y: 0 }
    const rect = svg.getBoundingClientRect()
    return {
      x: ((event.clientX - rect.left) / rect.width) * graphCanvas.width,
      y: ((event.clientY - rect.top) / rect.height) * graphCanvas.height,
    }
  }, [])

  const handleGraphMouseDown = useCallback((event: MouseEvent<SVGSVGElement>) => {
    if (event.button !== 0) return
    graphDragRef.current = {
      type: 'pan',
      startClient: { x: event.clientX, y: event.clientY },
      startViewport: graphViewport,
    }
  }, [graphViewport])

  const handleNodeMouseDown = useCallback((event: MouseEvent<SVGGElement>, nodeId: string) => {
    event.stopPropagation()
    setSelectedGraphNodeId(nodeId)
    const startSvg = getSvgPoint(event)
    graphDragRef.current = {
      type: 'node',
      nodeId,
      startSvg,
      startPos: graphPositions[nodeId] || { x: 0, y: 0 },
    }
  }, [getSvgPoint, graphPositions])

  const handleGraphMouseMove = useCallback((event: MouseEvent<SVGSVGElement>) => {
    const drag = graphDragRef.current
    if (!drag) return

    if (drag.type === 'node') {
      const current = getSvgPoint(event)
      const dx = (current.x - drag.startSvg.x) / graphViewport.scale
      const dy = (current.y - drag.startSvg.y) / graphViewport.scale
      setGraphPositions((prev) => ({
        ...prev,
        [drag.nodeId]: {
          x: drag.startPos.x + dx,
          y: drag.startPos.y + dy,
        },
      }))
      return
    }

    setGraphViewport({
      ...drag.startViewport,
      x: drag.startViewport.x + (event.clientX - drag.startClient.x) / graphViewport.scale,
      y: drag.startViewport.y + (event.clientY - drag.startClient.y) / graphViewport.scale,
    })
  }, [getSvgPoint, graphViewport.scale])

  const handleGraphMouseUp = useCallback(() => {
    graphDragRef.current = null
  }, [])

  const handleGraphWheel = useCallback((event: WheelEvent<SVGSVGElement>) => {
    event.preventDefault()
    const direction = event.deltaY > 0 ? -1 : 1
    const nextScale = Math.min(2.2, Math.max(0.55, graphViewport.scale + direction * 0.12))
    setGraphViewport((prev) => ({ ...prev, scale: nextScale }))
  }, [graphViewport.scale])

  const resetGraphLayout = useCallback(() => {
    setGraphPositions(computeGraphPositions(graphData.nodes, graphData.edges))
    setGraphViewport({ x: 0, y: 0, scale: 1 })
  }, [graphData])

  const handleModalOk = useCallback(async () => {
    try {
      const values = await form.validateFields()
      setModalLoading(true)

      const submitData: KnowledgeForm = {
        title: values.title,
        content: values.content,
        category: values.category,
        tags: values.tags || [],
        agent_type: values.agent_type,
        status: values.status ? 1 : 0,
      }

      if (editingKnowledge) {
        await knowledgeService.update(editingKnowledge.id, submitData)
        message.success('更新成功')
      } else {
        await knowledgeService.create(submitData)
        message.success('创建成功')
      }

      setModalVisible(false)
      fetchData()
    } catch (error: any) {
      if (error?.message) {
        message.error(error.message)
      } else if (!error?.errorFields) {
        message.error('操作失败')
      }
    } finally {
      setModalLoading(false)
    }
  }, [editingKnowledge, form])

  // 获取分类名称
  const getCategoryName = (category: string) => {
    const graphCategoryMap: Record<string, string> = {
      frontend: '前端项目',
      api: '接口项目',
      service: '服务层项目',
      core: 'Core 项目',
      project: '项目',
    }
    if (graphCategoryMap[category]) return graphCategoryMap[category]
    const found = knowledgeCategories.find((c) => c.value === category)
    return found?.label || category
  }

  // 获取分类颜色
  const getCategoryColor = (category: string) => {
    const colorMap: Record<string, string> = {
      frontend: 'blue',
      api: 'cyan',
      service: 'green',
      core: 'orange',
      project: 'default',
      product: 'blue',
      technical: 'green',
      business: 'orange',
      faq: 'purple',
      guide: 'cyan',
      best_practice: 'gold',
      other: 'default',
    }
    return colorMap[category] || 'default'
  }

  // 获取分身类型名称
  const getAgentTypeName = (agentType: string) => {
    const found = agentTypeOptions.find((a) => a.value === agentType)
    return found?.label || agentType
  }

  // 获取分身类型颜色
  const getAgentTypeColor = (agentType: string) => {
    const colorMap: Record<string, string> = {
      PM: '#1890ff',
      PJM: '#722ed1',
      BE: '#52c41a',
      FE: '#eb2f96',
      QA: '#fa8c16',
      RPT: '#13c2c2',
    }
    return colorMap[agentType] || '#666'
  }

  const selectedGraphNode = useMemo(
    () => graphData.nodes.find((node) => node.id === selectedGraphNodeId),
    [graphData.nodes, selectedGraphNodeId],
  )

  const connectedEdges = useMemo(
    () => graphData.edges.filter((edge) => edge.source === selectedGraphNodeId || edge.target === selectedGraphNodeId),
    [graphData.edges, selectedGraphNodeId],
  )

  const graphNodeMap = useMemo(
    () => new Map(graphData.nodes.map((node) => [node.id, node])),
    [graphData.nodes],
  )

  const graphDegreeMap = useMemo(() => {
    const degree = new Map<string, number>()
    graphData.nodes.forEach((node) => degree.set(node.id, 0))
    graphData.edges.forEach((edge) => {
      degree.set(edge.source, (degree.get(edge.source) || 0) + 1)
      degree.set(edge.target, (degree.get(edge.target) || 0) + 1)
    })
    return degree
  }, [graphData])

  const activeGraphNodeIds = useMemo(() => {
    if (!selectedGraphNodeId) return new Set<string>()
    const ids = new Set([selectedGraphNodeId])
    connectedEdges.forEach((edge) => {
      ids.add(edge.source)
      ids.add(edge.target)
    })
    return ids
  }, [connectedEdges, selectedGraphNodeId])

  const renderGraphView = () => (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={8}>
          <Card size="small">
            <Statistic title="项目节点" value={graphData.nodes.length} prefix={<BookOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small">
            <Statistic title="项目关系" value={graphData.edges.length} prefix={<ApartmentOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card size="small">
            <Statistic title="图谱类型" value="项目关系" />
          </Card>
        </Col>
      </Row>

      <Card
        size="small"
        title={
          <Space>
            <ApartmentOutlined />
            项目关系图谱
          </Space>
        }
        extra={
          <Space wrap>
            <Select value={graphMaxNodes} style={{ width: 110 }} onChange={setGraphMaxNodes}>
              <Option value={30}>30 节点</Option>
              <Option value={50}>50 节点</Option>
              <Option value={80}>80 节点</Option>
              <Option value={120}>120 节点</Option>
            </Select>
            <Button icon={<ReloadOutlined />} onClick={fetchGraph} loading={graphLoading}>
              刷新
            </Button>
            <Button onClick={resetGraphLayout} disabled={!graphData.nodes.length}>
              重置布局
            </Button>
          </Space>
        }
      >
        {graphLoading ? (
          <TableSkeleton />
        ) : !graphData.nodes.length ? (
          <Empty description="暂无知识图谱数据" style={{ padding: '48px 0' }} />
        ) : (
          <Row gutter={[16, 16]}>
            <Col xs={24} lg={17}>
              <div style={{ width: '100%', border: '1px solid #e5eaf3', borderRadius: 6, background: '#f8fafd', overflow: 'hidden' }}>
                <svg
                  ref={graphSvgRef}
                  width="100%"
                  viewBox={`0 0 ${graphCanvas.width} ${graphCanvas.height}`}
                  role="img"
                  aria-label="知识图谱"
                  style={{ display: 'block', cursor: graphDragRef.current?.type === 'pan' ? 'grabbing' : 'grab', userSelect: 'none' }}
                  onMouseDown={handleGraphMouseDown}
                  onMouseMove={handleGraphMouseMove}
                  onMouseUp={handleGraphMouseUp}
                  onMouseLeave={handleGraphMouseUp}
                  onWheel={handleGraphWheel}
                >
                  <defs>
                    <marker id="knowledge-arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
                      <path d="M0,0 L0,6 L9,3 z" fill="#8c8c8c" />
                    </marker>
                    <marker id="knowledge-arrow-active" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
                      <path d="M0,0 L0,6 L9,3 z" fill="#1677ff" />
                    </marker>
                  </defs>
                  <rect x={0} y={0} width={graphCanvas.width} height={graphCanvas.height} fill="#f8fafd" />
                  <g transform={`translate(${graphViewport.x}, ${graphViewport.y}) scale(${graphViewport.scale})`}>
                  {graphData.edges.map((edge) => {
                    const source = graphPositions[edge.source]
                    const target = graphPositions[edge.target]
                    if (!source || !target) return null
                    const active = edge.source === selectedGraphNodeId || edge.target === selectedGraphNodeId
                    const muted = selectedGraphNodeId && !active
                    const midX = (source.x + target.x) / 2
                    const midY = (source.y + target.y) / 2
                    const label = getRelationLabel(edge.relation)
                    const labelWidth = Math.max(42, label.length * 13 + 18)
                    return (
                      <g key={edge.id}>
                        <line
                          x1={source.x}
                          y1={source.y}
                          x2={target.x}
                          y2={target.y}
                          stroke={active ? '#1677ff' : '#b8c3d6'}
                          strokeOpacity={muted ? 0.22 : 0.82}
                          strokeWidth={active ? 2.8 : Math.max(1.2, edge.weight * 1.8)}
                          markerEnd={active ? 'url(#knowledge-arrow-active)' : 'url(#knowledge-arrow)'}
                        />
                        <g opacity={muted ? 0.25 : 1}>
                          <rect
                            x={midX - labelWidth / 2}
                            y={midY - 13}
                            width={labelWidth}
                            height={22}
                            rx={11}
                            fill={active ? '#e6f4ff' : '#fff'}
                            stroke={active ? '#91caff' : '#d9e2f1'}
                          />
                          <text
                            x={midX}
                            y={midY + 2}
                            textAnchor="middle"
                            fontSize="12"
                            fill={active ? '#0958d9' : '#5b6475'}
                          >
                            {label}
                          </text>
                        </g>
                      </g>
                    )
                  })}
                  {graphData.nodes.map((node) => {
                    const pos = graphPositions[node.id]
                    if (!pos) return null
                    const selected = node.id === selectedGraphNodeId
                    const color = graphNodeColors[node.category || 'other'] || graphNodeColors.other
                    const degree = graphDegreeMap.get(node.id) || 0
                    const muted = selectedGraphNodeId && !activeGraphNodeIds.has(node.id)
                    const radius = selected ? 40 : Math.min(36, 27 + degree * 2)
                    return (
                      <g
                        key={node.id}
                        transform={`translate(${pos.x}, ${pos.y})`}
                        onMouseDown={(event) => handleNodeMouseDown(event, node.id)}
                        style={{ cursor: 'grab', opacity: muted ? 0.35 : 1 }}
                      >
                        <circle r={radius + 5} fill={selected ? '#e6f4ff' : '#fff'} stroke={selected ? '#1677ff' : '#d9e2f1'} strokeWidth={selected ? 2 : 1} />
                        <circle r={radius} fill="#fff" stroke={color} strokeWidth={selected ? 3 : 2} />
                        <circle r={8} cy={-13} fill={color} />
                        <text y={12} textAnchor="middle" fontSize="12" fontWeight={selected ? 600 : 500} fill="#262626">
                          {shortenTitle(node.title || node.id)}
                        </text>
                        <text y={28} textAnchor="middle" fontSize="10" fill="#8c8c8c">
                          {degree} 条关系
                        </text>
                      </g>
                    )
                  })}
                  </g>
                </svg>
              </div>
            </Col>
            <Col xs={24} lg={7}>
              <Card size="small" title="节点详情" extra={<Button size="small" icon={<LinkOutlined />} disabled={!selectedGraphNodeId} onClick={handleAutoLink}>自动关联</Button>}>
                {selectedGraphNode ? (
                  <Space direction="vertical" size={10} style={{ width: '100%' }}>
                    <Text strong>{selectedGraphNode.title}</Text>
                    <Text type="secondary">{selectedGraphNode.id}</Text>
                    <Space wrap>
                      {selectedGraphNode.category && <Tag color={getCategoryColor(selectedGraphNode.category)}>{getCategoryName(selectedGraphNode.category)}</Tag>}
                      {(selectedGraphNode.tags || []).slice(0, 6).map((tag) => <Tag key={tag}>{tag}</Tag>)}
                    </Space>
                    <div>
                      <Text type="secondary">关联关系</Text>
                      <div style={{ marginTop: 8 }}>
                        {connectedEdges.length ? connectedEdges.map((edge) => {
                          const otherId = edge.source === selectedGraphNode.id ? edge.target : edge.source
                          const otherNode = graphNodeMap.get(otherId)
                          const direction = edge.source === selectedGraphNode.id ? '指向' : '来自'
                          return (
                            <div key={edge.id} style={{ padding: '8px 0', borderBottom: '1px solid #f5f5f5' }}>
                              <Space direction="vertical" size={2}>
                                <Space>
                                  <Tag color="blue">{getRelationLabel(edge.relation)}</Tag>
                                  <Text type="secondary">{direction}</Text>
                                </Space>
                                <Text>{otherNode?.title || otherId}</Text>
                                <Text type="secondary">关系强度 {edge.weight}</Text>
                              </Space>
                            </div>
                          )
                        }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无关联" />}
                      </div>
                    </div>
                  </Space>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请选择节点" />
                )}
              </Card>
            </Col>
          </Row>
        )}
      </Card>
    </div>
  )

  // 表格列定义
  const columns: ColumnsType<Knowledge> = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    {
      title: '标题',
      dataIndex: 'title',
      width: 200,
      ellipsis: true,
      render: (title) => (
        <Tooltip title={title}>
          <span style={{ fontWeight: 500 }}>{title}</span>
        </Tooltip>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 100,
      render: (category) => (
        <Tag color={getCategoryColor(category)}>{getCategoryName(category)}</Tag>
      ),
    },
    {
      title: '标签',
      dataIndex: 'tags',
      width: 180,
      render: (tags: string[]) =>
        tags?.length > 0 ? (
          <Space size={[0, 4]} wrap>
            {tags.slice(0, 3).map((tag) => (
              <Tag key={tag} style={{ margin: 0 }}>
                {tag}
              </Tag>
            ))}
            {tags.length > 3 && (
              <Tooltip title={tags.slice(3).join(', ')}>
                <Tag style={{ margin: 0 }}>+{tags.length - 3}</Tag>
              </Tooltip>
            )}
          </Space>
        ) : (
          '-'
        ),
    },
    {
      title: '关联分身',
      dataIndex: 'agent_type',
      width: 100,
      render: (agentType) =>
        agentType ? (
          <Tag color={getAgentTypeColor(agentType)}>{getAgentTypeName(agentType)}</Tag>
        ) : (
          '-'
        ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (status, record) => (
        <Switch
          checked={status === 1}
          checkedChildren="启用"
          unCheckedChildren="禁用"
          onChange={() => handleToggleStatus(record)}
        />
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'create_time',
      width: 160,
      render: (time) => (time ? new Date(time).toLocaleString() : '-'),
    },
    {
      title: '操作',
      width: 150,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定删除该知识条目吗？"
            description="删除后将无法恢复"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const renderListView = () => (
    <>
      {loading ? (
        <TableSkeleton />
      ) : !data.length ? (
        <Empty description="暂无知识条目" style={{ padding: '40px 0' }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            添加知识
          </Button>
        </Empty>
      ) : (
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          scroll={{ x: 1200 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => {
              setPage(p)
              setPageSize(ps)
            },
          }}
        />
      )}
    </>
  )

  // 渲染
  return (
    <Card
      title={
        <Space>
          <BookOutlined />
          知识库管理
        </Space>
      }
      extra={activeTab === 'list' ? (
        <Space>
          <Input
            placeholder="搜索标题/内容"
            prefix={<SearchOutlined />}
            allowClear
            style={{ width: 180 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onPressEnter={handleSearch}
          />
          <Select
            placeholder="分类筛选"
            allowClear
            style={{ width: 120 }}
            value={filterCategory}
            onChange={(val) => {
              setFilterCategory(val)
              setPage(1)
            }}
          >
            {knowledgeCategories.map((c) => (
              <Option key={c.value} value={c.value}>
                {c.label}
              </Option>
            ))}
          </Select>
          <Select
            placeholder="分身类型"
            allowClear
            style={{ width: 120 }}
            value={filterAgentType}
            onChange={(val) => {
              setFilterAgentType(val)
              setPage(1)
            }}
          >
            {agentTypeOptions.map((a) => (
              <Option key={a.value} value={a.value}>
                {a.label}
              </Option>
            ))}
          </Select>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新增知识
          </Button>
        </Space>
      ) : null}
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'list',
            label: (
              <Space>
                <BookOutlined />
                知识条目
              </Space>
            ),
            children: renderListView(),
          },
          {
            key: 'graph',
            label: (
              <Space>
                <ApartmentOutlined />
                知识图谱
              </Space>
            ),
            children: renderGraphView(),
          },
        ]}
      />

      {/* 新建/编辑弹窗 */}
      <Modal
        title={editingKnowledge ? '编辑知识条目' : '新增知识条目'}
        open={modalVisible}
        onOk={handleModalOk}
        onCancel={() => setModalVisible(false)}
        confirmLoading={modalLoading}
        width={700}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ status: 1, tags: [] }}
        >
          <Form.Item
            name="title"
            label="标题"
            rules={[{ required: true, message: '请输入标题' }]}
          >
            <Input placeholder="请输入知识条目标题" maxLength={200} showCount />
          </Form.Item>

          <Form.Item
            name="content"
            label="内容"
            rules={[{ required: true, message: '请输入内容' }]}
          >
            <TextArea
              placeholder="请输入知识内容详情"
              autoSize={{ minRows: 6, maxRows: 12 }}
              showCount
              maxLength={5000}
            />
          </Form.Item>

          <Space style={{ width: '100%' }} size="large">
            <Form.Item
              name="category"
              label="分类"
              rules={[{ required: true, message: '请选择分类' }]}
              style={{ width: 200 }}
            >
              <Select placeholder="请选择分类">
                {knowledgeCategories.map((c) => (
                  <Option key={c.value} value={c.value}>
                    {c.label}
                  </Option>
                ))}
              </Select>
            </Form.Item>

            <Form.Item
              name="agent_type"
              label="关联分身"
              style={{ width: 200 }}
            >
              <Select placeholder="请选择关联分身" allowClear>
                {agentTypeOptions.map((a) => (
                  <Option key={a.value} value={a.value}>
                    {a.label}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Space>

          <Form.Item
            name="tags"
            label="标签"
            extra="可输入自定义标签或选择常用标签"
          >
            <Select
              mode="tags"
              placeholder="输入或选择标签"
              style={{ width: '100%' }}
              tokenSeparators={[',']}
              options={commonTags.map((t) => ({ value: t, label: t }))}
            />
          </Form.Item>

          <Form.Item name="status" label="状态" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="禁用" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
