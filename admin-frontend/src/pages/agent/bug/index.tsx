import React, { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Card,
  Table,
  Button,
  Space,
  Tag,
  Input,
  Select,
  Modal,
  Form,
  Typography,
  Tooltip,
  Drawer,
  Timeline,
  Empty,
  Spin,
  message,
  Popconfirm,
  Badge,
  Row,
  Col,
  Descriptions,
  theme,
} from 'antd'
import {
  PlusOutlined,
  BugOutlined,
  SearchOutlined,
  ReloadOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  CloseCircleOutlined,
  UserOutlined,
  DeleteOutlined,
  ThunderboltOutlined,
  WarningOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useSearchParams } from 'react-router-dom'
import { agentApi } from '@/services/api'

const { Option } = Select
const { TextArea } = Input
const { Text, Title, Paragraph } = Typography
const { useToken } = theme

// Bug 严重程度类型
type BugSeverity = 'critical' | 'high' | 'medium' | 'low'

// Bug 状态类型
type BugStatus = 'open' | 'in_progress' | 'fixed' | 'verified' | 'closed'

// Bug 数据接口
interface Bug {
  id: string
  title: string
  description: string
  steps_to_reproduce: string
  expected_behavior: string
  actual_behavior: string
  severity: BugSeverity
  status: BugStatus
  project_id: string
  project_name: string
  assignee: string
  assignee_name: string
  resolution_note: string
  create_time: number
  update_time: number
  status_history: StatusHistoryItem[]
}

// 状态历史记录
interface StatusHistoryItem {
  status: BugStatus
  operator: string
  operator_name: string
  note: string
  timestamp: number
}

// 项目接口
interface Project {
  id: string
  project_name: string
}

// 筛选状态
interface FilterState {
  keyword: string
  status: string
  severity: string
  projectId: string
  sortBy: string
}

// 严重程度配置 - 中文
const severityConfig: Record<BugSeverity, { color: string; text: string; bgColor: string; icon: React.ReactNode; blinking?: boolean }> = {
  critical: {
    color: '#ff4d4f',
    text: '严重',
    bgColor: '#fff1f0',
    icon: <ThunderboltOutlined />,
    blinking: true,
  },
  high: {
    color: '#fa8c16',
    text: '高',
    bgColor: '#fff7e6',
    icon: <WarningOutlined />,
  },
  medium: {
    color: '#faad14',
    text: '中',
    bgColor: '#fffbe6',
    icon: <ExclamationCircleOutlined />,
  },
  low: {
    color: '#8c8c8c',
    text: '低',
    bgColor: '#fafafa',
    icon: <InfoCircleOutlined />,
  },
}

// 状态配置 - 中文
const statusConfig: Record<BugStatus, { color: string; text: string; icon: React.ReactNode }> = {
  open: { color: '#1890ff', text: '待处理', icon: <ExclamationCircleOutlined /> },
  in_progress: { color: '#fa8c16', text: '处理中', icon: <ClockCircleOutlined /> },
  fixed: { color: '#52c41a', text: '已修复', icon: <CheckCircleOutlined /> },
  verified: { color: '#13c2c2', text: '已验证', icon: <CheckCircleOutlined /> },
  closed: { color: '#8c8c8c', text: '已关闭', icon: <CloseCircleOutlined /> },
}

// 状态流转配置
const statusTransitions: Record<BugStatus, { next: BugStatus[]; action: string }> = {
  open: { next: ['in_progress'], action: '开始处理' },
  in_progress: { next: ['fixed'], action: '标记已修复' },
  fixed: { next: ['verified'], action: '验证通过' },
  verified: { next: ['closed'], action: '关闭' },
  closed: { next: [], action: '' },
}

// 闪烁动画样式
const blinkingStyles = `
  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
  }
  .blinking-badge {
    animation: blink 1s infinite;
  }
`

// 严重程度徽章组件
const SeverityBadge: React.FC<{ severity: BugSeverity }> = ({ severity }) => {
  const config = severityConfig[severity]
  return (
    <span
      className={config.blinking ? 'blinking-badge' : ''}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 10px',
        borderRadius: 12,
        backgroundColor: config.bgColor,
        color: config.color,
        fontWeight: 600,
        fontSize: 12,
        border: `1px solid ${config.color}33`,
      }}
    >
      {config.icon}
      {config.text}
    </span>
  )
}

// 状态徽章组件
const StatusBadge: React.FC<{ status: BugStatus }> = ({ status }) => {
  const config = statusConfig[status]
  return (
    <Tag
      color={config.color}
      icon={config.icon}
      style={{ borderRadius: 12, padding: '2px 10px' }}
    >
      {config.text}
    </Tag>
  )
}

// 骨架屏组件
const TableSkeleton: React.FC = () => (
  <div style={{ padding: '24px 0' }}>
    <Spin tip="加载中...">
      <div style={{ height: 300 }} />
    </Spin>
  </div>
)

// 空状态组件
const EmptyState: React.FC<{ onReset: () => void }> = ({ onReset }) => (
  <Empty
    image={Empty.PRESENTED_IMAGE_SIMPLE}
    description={
      <span>
        暂无 BUG 数据
        <Button type="link" onClick={onReset}>
          重置筛选
        </Button>
      </span>
    }
  />
)

// 错误状态组件
const ErrorState: React.FC<{ onRetry: () => void }> = ({ onRetry }) => (
  <Empty
    image={Empty.PRESENTED_IMAGE_SIMPLE}
    description={
      <span>
        加载失败
        <Button type="link" onClick={onRetry}>
          重试
        </Button>
      </span>
    }
  />
)

const AgentBug: React.FC = () => {
  // URL 参数
  const [searchParams, setSearchParams] = useSearchParams()
  const { token } = useToken()

  // 状态定义
  const [filters, setFilters] = useState<FilterState>({
    keyword: searchParams.get('keyword') ?? '',
    status: searchParams.get('status') ?? '',
    severity: searchParams.get('severity') ?? '',
    projectId: searchParams.get('projectId') ?? '',
    sortBy: searchParams.get('sortBy') ?? 'create_time',
  })

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [data, setData] = useState<Bug[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [total, setTotal] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)

  // 弹窗状态
  const [createModalVisible, setCreateModalVisible] = useState(false)
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false)
  const [resolveModalVisible, setResolveModalVisible] = useState(false)
  const [selectedBug, setSelectedBug] = useState<Bug | null>(null)

  // 表单
  const [createForm] = Form.useForm()
  const [resolveForm] = Form.useForm()

  // 防抖搜索关键词
  const [searchInput, setSearchInput] = useState(filters.keyword)

  // 加载项目列表
  useEffect(() => {
    loadProjects()
  }, [])

  // 加载 Bug 列表
  useEffect(() => {
    loadData()
  }, [filters, currentPage, pageSize])

  // 防抖搜索
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput !== filters.keyword) {
        setFilters(prev => ({ ...prev, keyword: searchInput }))
        setCurrentPage(1)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [searchInput])

  // 同步 URL 参数
  useEffect(() => {
    const params = new URLSearchParams()
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.set(key, value)
    })
    setSearchParams(params)
  }, [filters])

  const loadProjects = async () => {
    try {
      const result = await agentApi.getProjects() as any
      setProjects(result?.list || [])
    } catch (err) {
      console.error('加载项目列表失败:', err)
    }
  }

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await agentApi.getBugs({
        ...filters,
        page: currentPage,
        page_size: pageSize,
      }) as any
      setData(result?.list || [])
      setTotal(result?.total || 0)
    } catch (err) {
      setError(err as Error)
      message.error('加载 BUG 列表失败')
    } finally {
      setLoading(false)
    }
  }

  const handleFilterChange = useCallback((key: keyof FilterState, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }))
    setCurrentPage(1)
  }, [])

  const handleResetFilters = useCallback(() => {
    setFilters({
      keyword: '',
      status: '',
      severity: '',
      projectId: '',
      sortBy: 'create_time',
    })
    setSearchInput('')
    setCurrentPage(1)
  }, [])

  const handleCreateBug = async (values: any) => {
    try {
      await agentApi.createBug(values)
      message.success('BUG 创建成功')
      setCreateModalVisible(false)
      createForm.resetFields()
      loadData()
    } catch (err) {
      message.error('创建 BUG 失败')
    }
  }

  const handleUpdateStatus = async (bugId: string, status: BugStatus) => {
    try {
      await agentApi.updateBugStatus(bugId, { status })
      message.success('状态更新成功')
      loadData()
      if (selectedBug?.id === bugId) {
        setSelectedBug(prev => prev ? { ...prev, status } : null)
      }
    } catch (err) {
      message.error('状态更新失败')
    }
  }

  const handleResolveBug = async (values: { resolution_note: string }) => {
    if (!selectedBug) return
    try {
      await agentApi.updateBugStatus(selectedBug.id, {
        status: 'fixed',
        fix_note: values.resolution_note,
      })
      message.success('BUG 已修复')
      setResolveModalVisible(false)
      resolveForm.resetFields()
      loadData()
    } catch (err) {
      message.error('操作失败')
    }
  }

  const handleViewDetail = (bug: Bug) => {
    setSelectedBug(bug)
    setDetailDrawerVisible(true)
  }

  const handleDeleteBug = async (bugId: string) => {
    try {
      await agentApi.deleteBug(bugId)
      message.success('BUG 已删除')
      loadData()
    } catch (err) {
      message.error('删除失败')
    }
  }

  // 统计数据
  const bugStats = useMemo(() => ({
    total,
    open: data.filter(b => b.status === 'open').length,
    critical: data.filter(b => b.severity === 'critical').length,
    inProgress: data.filter(b => b.status === 'in_progress').length,
  }), [data, total])

  // 表格列定义
  const columns: ColumnsType<Bug> = useMemo(() => [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 80,
      render: (id: string) => <Text code style={{ fontSize: 11 }}>{id.slice(-8)}</Text>,
    },
    {
      title: '标题',
      dataIndex: 'title',
      ellipsis: true,
      render: (title: string, record) => (
        <Space>
          <BugOutlined style={{ color: severityConfig[record.severity].color }} />
          <a onClick={() => handleViewDetail(record)}>{title}</a>
        </Space>
      ),
    },
    {
      title: '严重程度',
      dataIndex: 'severity',
      width: 100,
      render: (severity: BugSeverity) => <SeverityBadge severity={severity} />,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (status: BugStatus) => <StatusBadge status={status} />,
    },
    {
      title: '项目',
      dataIndex: 'project_name',
      width: 140,
      ellipsis: true,
    },
    {
      title: '负责人',
      dataIndex: 'assignee_name',
      width: 100,
      render: (name: string) => (
        <Space size={4}>
          <UserOutlined style={{ fontSize: 12 }} />
          <Text style={{ fontSize: 13 }}>{name || '未分配'}</Text>
        </Space>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'create_time',
      width: 140,
      sorter: true,
      render: (time: number) => <Text style={{ fontSize: 12 }}>{new Date(time).toLocaleString()}</Text>,
    },
    {
      title: '操作',
      width: 160,
      fixed: 'right',
      render: (_, record) => {
        const transition = statusTransitions[record.status]
        return (
          <Space size="small">
            <Tooltip title="查看详情">
              <Button
                type="link"
                size="small"
                icon={<EyeOutlined />}
                onClick={() => handleViewDetail(record)}
              />
            </Tooltip>
            {transition.next.length > 0 && (
              <Button
                type="link"
                size="small"
                onClick={() => handleUpdateStatus(record.id, transition.next[0])}
              >
                {transition.action}
              </Button>
            )}
            <Popconfirm
              title="确定删除此 BUG 吗？"
              onConfirm={() => handleDeleteBug(record.id)}
              okText="确定"
              cancelText="取消"
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Space>
        )
      },
    },
  ], [])

  // 渲染筛选面板
  const renderFilterPanel = () => (
    <Card style={{ marginBottom: 16, borderRadius: 12 }}>
      <Row gutter={[16, 16]} align="middle">
        <Col xs={24} sm={12} md={8} lg={6}>
          <Input
            placeholder="搜索标题或描述"
            prefix={<SearchOutlined />}
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            allowClear
            style={{ borderRadius: 8 }}
          />
        </Col>
        <Col xs={24} sm={12} md={4} lg={3}>
          <Select
            placeholder="状态"
            value={filters.status || undefined}
            onChange={value => handleFilterChange('status', value ?? '')}
            allowClear
            style={{ width: '100%' }}
          >
            {Object.entries(statusConfig).map(([key, config]) => (
              <Option key={key} value={key}>
                <Tag color={config.color} style={{ margin: 0, borderRadius: 8 }}>{config.text}</Tag>
              </Option>
            ))}
          </Select>
        </Col>
        <Col xs={24} sm={12} md={4} lg={3}>
          <Select
            placeholder="严重程度"
            value={filters.severity || undefined}
            onChange={value => handleFilterChange('severity', value ?? '')}
            allowClear
            style={{ width: '100%' }}
          >
            {Object.entries(severityConfig).map(([key]) => (
              <Option key={key} value={key}>
                <SeverityBadge severity={key as BugSeverity} />
              </Option>
            ))}
          </Select>
        </Col>
        <Col xs={24} sm={12} md={4} lg={4}>
          <Select
            placeholder="所属项目"
            value={filters.projectId || undefined}
            onChange={value => handleFilterChange('projectId', value ?? '')}
            allowClear
            style={{ width: '100%' }}
          >
            {projects.map(project => (
              <Option key={project.id} value={project.id}>
                {project.project_name}
              </Option>
            ))}
          </Select>
        </Col>
        <Col xs={24} sm={12} md={4} lg={3}>
          <Select
            placeholder="排序"
            value={filters.sortBy}
            onChange={value => handleFilterChange('sortBy', value)}
            style={{ width: '100%' }}
          >
            <Option value="create_time">创建时间</Option>
            <Option value="severity">严重程度</Option>
            <Option value="update_time">更新时间</Option>
          </Select>
        </Col>
        <Col xs={24} sm={24} md={4} lg={5}>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadData}>
              刷新
            </Button>
            <Button onClick={handleResetFilters}>
              重置
            </Button>
          </Space>
        </Col>
      </Row>
    </Card>
  )

  // 渲染创建 Bug 弹窗
  const renderCreateModal = () => (
    <Modal
      title={<span><BugOutlined style={{ marginRight: 8, color: token.colorPrimary }} />创建 BUG</span>}
      open={createModalVisible}
      onCancel={() => {
        setCreateModalVisible(false)
        createForm.resetFields()
      }}
      onOk={() => createForm.submit()}
      width={700}
    >
      <Form
        form={createForm}
        layout="vertical"
        onFinish={handleCreateBug}
      >
        <Form.Item
          name="title"
          label="标题"
          rules={[{ required: true, message: '请输入 BUG 标题' }]}
        >
          <Input placeholder="简要描述 BUG" maxLength={200} showCount />
        </Form.Item>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="project_id"
              label="所属项目"
              rules={[{ required: true, message: '请选择项目' }]}
            >
              <Select placeholder="选择项目">
                {projects.map(project => (
                  <Option key={project.id} value={project.id}>
                    {project.project_name}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="severity"
              label="严重程度"
              rules={[{ required: true, message: '请选择严重程度' }]}
            >
              <Select placeholder="选择严重程度">
                {Object.entries(severityConfig).map(([key]) => (
                  <Option key={key} value={key}>
                    <SeverityBadge severity={key as BugSeverity} />
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
        </Row>

        <Form.Item name="description" label="描述">
          <TextArea placeholder="详细描述 BUG 情况" rows={3} maxLength={2000} showCount />
        </Form.Item>

        <Form.Item name="steps_to_reproduce" label="复现步骤">
          <TextArea
            placeholder="1. 进入...页面&#10;2. 点击...按钮&#10;3. 出现错误"
            rows={4}
            maxLength={2000}
            showCount
          />
        </Form.Item>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="expected_behavior" label="预期行为">
              <TextArea placeholder="期望的正常行为" rows={2} maxLength={500} showCount />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="actual_behavior" label="实际行为">
              <TextArea placeholder="实际出现的错误行为" rows={2} maxLength={500} showCount />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item name="assignee" label="负责人">
          <Input placeholder="指派给谁处理" />
        </Form.Item>
      </Form>
    </Modal>
  )

  // 渲染解决 Bug 弹窗
  const renderResolveModal = () => (
    <Modal
      title={<span><CheckCircleOutlined style={{ marginRight: 8, color: '#52c41a' }} />标记已修复</span>}
      open={resolveModalVisible}
      onCancel={() => {
        setResolveModalVisible(false)
        resolveForm.resetFields()
      }}
      onOk={() => resolveForm.submit()}
    >
      <Form form={resolveForm} layout="vertical" onFinish={handleResolveBug}>
        <Form.Item
          name="resolution_note"
          label="修复说明"
          rules={[{ required: true, message: '请填写修复说明' }]}
        >
          <TextArea placeholder="描述如何修复的此 BUG" rows={4} maxLength={2000} showCount />
        </Form.Item>
      </Form>
    </Modal>
  )

  // 渲染 Bug 详情抽屉
  const renderDetailDrawer = () => {
    if (!selectedBug) return null

    const transition = statusTransitions[selectedBug.status]

    return (
      <Drawer
        title={
          <Space>
            <BugOutlined style={{ color: severityConfig[selectedBug.severity].color }} />
            BUG 详情
          </Space>
        }
        placement="right"
        width={600}
        onClose={() => setDetailDrawerVisible(false)}
        open={detailDrawerVisible}
        footer={
          <Space>
            {transition.next.length > 0 && (
              <Button
                type="primary"
                icon={statusConfig[transition.next[0]].icon}
                onClick={() => {
                  if (transition.next[0] === 'fixed') {
                    setDetailDrawerVisible(false)
                    setResolveModalVisible(true)
                  } else {
                    handleUpdateStatus(selectedBug.id, transition.next[0])
                  }
                }}
              >
                {transition.action}
              </Button>
            )}
            <Button onClick={() => setDetailDrawerVisible(false)}>关闭</Button>
          </Space>
        }
      >
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          {/* 基本信息 */}
          <Card size="small" title="基本信息" style={{ borderRadius: 8 }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="ID">
                <Text code>{selectedBug.id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="标题">
                <Text strong>{selectedBug.title}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="严重程度">
                <SeverityBadge severity={selectedBug.severity} />
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <StatusBadge status={selectedBug.status} />
              </Descriptions.Item>
              <Descriptions.Item label="项目">
                {selectedBug.project_name}
              </Descriptions.Item>
              <Descriptions.Item label="负责人">
                <Space>
                  <UserOutlined />
                  {selectedBug.assignee_name || '未分配'}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {new Date(selectedBug.create_time).toLocaleString()}
              </Descriptions.Item>
              <Descriptions.Item label="更新时间">
                {new Date(selectedBug.update_time).toLocaleString()}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          {/* 描述 */}
          {selectedBug.description && (
            <Card size="small" title="描述" style={{ borderRadius: 8 }}>
              <Paragraph style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
                {selectedBug.description}
              </Paragraph>
            </Card>
          )}

          {/* 复现步骤 */}
          {selectedBug.steps_to_reproduce && (
            <Card size="small" title="复现步骤" style={{ borderRadius: 8 }}>
              <Paragraph
                style={{
                  whiteSpace: 'pre-wrap',
                  margin: 0,
                  fontFamily: 'monospace',
                  background: '#f5f5f5',
                  padding: 12,
                  borderRadius: 8,
                }}
              >
                {selectedBug.steps_to_reproduce}
              </Paragraph>
            </Card>
          )}

          {/* 预期 vs 实际 */}
          <Card size="small" title="行为对比" style={{ borderRadius: 8 }}>
            <Row gutter={16}>
              <Col span={12}>
                <Text type="secondary" style={{ fontSize: 12 }}>预期行为:</Text>
                <Paragraph
                  style={{
                    marginTop: 8,
                    padding: 12,
                    background: '#f6ffed',
                    borderRadius: 8,
                    border: '1px solid #b7eb8f',
                  }}
                >
                  {selectedBug.expected_behavior || '-'}
                </Paragraph>
              </Col>
              <Col span={12}>
                <Text type="secondary" style={{ fontSize: 12 }}>实际行为:</Text>
                <Paragraph
                  style={{
                    marginTop: 8,
                    padding: 12,
                    background: '#fff2f0',
                    borderRadius: 8,
                    border: '1px solid #ffccc7',
                  }}
                >
                  {selectedBug.actual_behavior || '-'}
                </Paragraph>
              </Col>
            </Row>
          </Card>

          {/* 解决说明 */}
          {selectedBug.resolution_note && (
            <Card size="small" title="解决说明" style={{ borderRadius: 8 }}>
              <Paragraph style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
                {selectedBug.resolution_note}
              </Paragraph>
            </Card>
          )}

          {/* 状态时间线 */}
          {selectedBug.status_history && selectedBug.status_history.length > 0 && (
            <Card size="small" title="状态历史" style={{ borderRadius: 8 }}>
              <Timeline
                items={selectedBug.status_history.map((item) => ({
                  color: statusConfig[item.status]?.color || 'gray',
                  children: (
                    <div>
                      <Space>
                        <StatusBadge status={item.status} />
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {new Date(item.timestamp).toLocaleString()}
                        </Text>
                      </Space>
                      <div style={{ marginTop: 4, color: '#8c8c8c', fontSize: 12 }}>
                        by {item.operator_name || item.operator}
                      </div>
                      {item.note && (
                        <div style={{ marginTop: 4, color: '#595959' }}>{item.note}</div>
                      )}
                    </div>
                  ),
                }))}
              />
            </Card>
          )}
        </Space>
      </Drawer>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      {/* 注入闪烁动画样式 */}
      <style>{blinkingStyles}</style>

      {/* 页面标题和操作 */}
      <Card
        style={{ marginBottom: 16, borderRadius: 12 }}
        styles={{ body: { padding: '16px 24px' } }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <BugOutlined style={{ fontSize: 24, color: token.colorPrimary }} />
            <Title level={4} style={{ margin: 0 }}>BUG 管理</Title>
            <Badge count={total} style={{ backgroundColor: token.colorPrimary, borderRadius: 8 }} />
          </Space>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalVisible(true)}
            style={{ borderRadius: 8 }}
          >
            创建 BUG
          </Button>
        </div>

        {/* 统计信息 */}
        <Row gutter={24} style={{ marginTop: 16 }}>
          <Col>
            <Space>
              <Badge status="error" />
              <Text type="secondary">严重: {bugStats.critical}</Text>
            </Space>
          </Col>
          <Col>
            <Space>
              <Badge status="processing" />
              <Text type="secondary">待处理: {bugStats.open}</Text>
            </Space>
          </Col>
          <Col>
            <Space>
              <Badge status="warning" />
              <Text type="secondary">处理中: {bugStats.inProgress}</Text>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* 筛选面板 */}
      {renderFilterPanel()}

      {/* 数据表格 */}
      <Card style={{ borderRadius: 12 }}>
        {error ? (
          <ErrorState onRetry={loadData} />
        ) : loading ? (
          <TableSkeleton />
        ) : data.length === 0 ? (
          <EmptyState onReset={handleResetFilters} />
        ) : (
          <Table
            columns={columns}
            dataSource={data}
            rowKey="id"
            loading={loading}
            scroll={{ x: 1200 }}
            pagination={{
              current: currentPage,
              pageSize,
              total,
              showSizeChanger: true,
              showQuickJumper: true,
              showTotal: (total) => `共 ${total} 条`,
              onChange: (page, size) => {
                setCurrentPage(page)
                setPageSize(size)
              },
            }}
          />
        )}
      </Card>

      {/* 弹窗 */}
      {renderCreateModal()}
      {renderResolveModal()}
      {renderDetailDrawer()}
    </div>
  )
}

export default AgentBug
