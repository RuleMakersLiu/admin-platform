import React, { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
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
  message,
  Popconfirm,
  Descriptions,
  Badge,
  Statistic,
  Row,
  Col,
  Skeleton,
  Empty,
  Typography,
  Tooltip,
  Dropdown,
  Progress,
} from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  SearchOutlined,
  EyeOutlined,
  FolderOutlined,
  BugOutlined,
  CheckCircleOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  CloseCircleOutlined,
  MoreOutlined,
  CalendarOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { agentApi, agentTypeNames, agentTypeColors, AgentType } from '@/services/api'

const { Option } = Select
const { Text, Title, Paragraph } = Typography
const { Search } = Input

// 项目状态类型
type ProjectStatus = 'pending' | 'active' | 'completed' | 'cancelled'

// 优先级类型
type Priority = 'P0' | 'P1' | 'P2' | 'P3'

// 项目接口定义
interface Project {
  id: string
  project_name: string
  project_code: string
  description: string
  status: ProjectStatus
  priority: Priority
  agent_type: AgentType
  task_count: number
  bug_count: number
  workflow_stage: string
  create_time: number
  update_time: number
  owner?: string
}

// 筛选状态
interface FilterState {
  keyword: string
  status: string
}

// 状态配置
const statusConfig: Record<ProjectStatus, { color: string; text: string; badge: 'default' | 'processing' | 'success' | 'error' | 'warning'; icon: React.ReactNode }> = {
  pending: { color: 'default', text: '待开始', badge: 'default', icon: <PauseCircleOutlined /> },
  active: { color: 'processing', text: '进行中', badge: 'processing', icon: <PlayCircleOutlined /> },
  completed: { color: 'success', text: '已完成', badge: 'success', icon: <CheckCircleOutlined /> },
  cancelled: { color: 'error', text: '已取消', badge: 'error', icon: <CloseCircleOutlined /> },
}

// 优先级配置
const priorityConfig: Record<Priority, { color: string; text: string }> = {
  P0: { color: 'red', text: 'P0-紧急' },
  P1: { color: 'orange', text: 'P1-高' },
  P2: { color: 'blue', text: 'P2-中' },
  P3: { color: 'default', text: 'P3-低' },
}

// 工作流阶段配置
const workflowStages: Record<string, { text: string; progress: number }> = {
  requirement: { text: '需求分析', progress: 10 },
  design: { text: '设计阶段', progress: 25 },
  development: { text: '开发阶段', progress: 50 },
  testing: { text: '测试阶段', progress: 75 },
  deployment: { text: '部署阶段', progress: 90 },
  completed: { text: '已完成', progress: 100 },
}

// 防抖 Hook
const useDebounce = <T,>(value: T, delay: number): T => {
  const [debouncedValue, setDebouncedValue] = useState(value)

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => {
      clearTimeout(handler)
    }
  }, [value, delay])

  return debouncedValue
}

// 骨架屏组件
const TableSkeleton: React.FC = () => (
  <div style={{ padding: '16px 0' }}>
    <Skeleton active paragraph={{ rows: 5 }} />
  </div>
)

// 空状态组件
const EmptyState: React.FC = () => (
  <Empty
    image={Empty.PRESENTED_IMAGE_SIMPLE}
    description="暂无项目数据"
    style={{ padding: '40px 0' }}
  />
)

// 错误状态组件
const ErrorState: React.FC<{ onRetry: () => void }> = ({ onRetry }) => (
  <div style={{ textAlign: 'center', padding: '40px 0' }}>
    <Empty description="加载失败" />
    <Button type="primary" onClick={onRetry} style={{ marginTop: 16 }}>
      重试
    </Button>
  </div>
)

// 项目卡片组件
const ProjectCard: React.FC<{
  project: Project
  onView: (project: Project) => void
  onEdit: (project: Project) => void
  onDelete: (id: string) => void
  onStatusChange: (id: string, status: ProjectStatus) => void
}> = ({ project, onView, onEdit, onDelete, onStatusChange }) => {
  const priorityConf = priorityConfig[project.priority]
  const statusConf = statusConfig[project.status]
  const workflowConf = workflowStages[project.workflow_stage] || { text: project.workflow_stage, progress: 0 }

  // 获取可流转的状态
  const getNextStatus = (): ProjectStatus | null => {
    switch (project.status) {
      case 'pending': return 'active'
      case 'active': return 'completed'
      default: return null
    }
  }

  const nextStatus = getNextStatus()

  const menuItems = [
    {
      key: 'view',
      icon: <EyeOutlined />,
      label: '查看详情',
      onClick: () => onView(project),
    },
    {
      key: 'edit',
      icon: <EditOutlined />,
      label: '编辑',
      onClick: () => onEdit(project),
    },
    { type: 'divider' as const },
    {
      key: 'delete',
      icon: <DeleteOutlined />,
      label: '删除',
      danger: true,
      onClick: () => onDelete(project.id),
    },
  ]

  return (
    <Card
      hoverable
      style={{
        height: '100%',
        borderRadius: 12,
        borderLeft: `4px solid ${priorityConf.color}`,
        boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
      }}
      styles={{ body: { padding: 16 } }}
    >
      {/* 头部 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Text
            strong
            style={{ fontSize: 16, display: 'block' }}
            ellipsis
          >
            {project.project_name}
          </Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {project.project_code}
          </Text>
        </div>
        <Dropdown menu={{ items: menuItems }} trigger={['click']}>
          <Button type="text" icon={<MoreOutlined />} />
        </Dropdown>
      </div>

      {/* 标签 */}
      <div style={{ marginBottom: 12 }}>
        <Space size={4} wrap>
          <Tag color={statusConf.color} icon={statusConf.icon}>
            {statusConf.text}
          </Tag>
          <Tag color={priorityConf.color}>{project.priority}</Tag>
          <Tag color={agentTypeColors[project.agent_type]}>
            {agentTypeNames[project.agent_type] || project.agent_type}
          </Tag>
        </Space>
      </div>

      {/* 描述 */}
      <Paragraph
        ellipsis={{ rows: 2 }}
        style={{ fontSize: 13, color: '#666', marginBottom: 12, minHeight: 44 }}
      >
        {project.description || '暂无描述'}
      </Paragraph>

      {/* 进度条 */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>{workflowConf.text}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{workflowConf.progress}%</Text>
        </div>
        <Progress
          percent={workflowConf.progress}
          size="small"
          showInfo={false}
          strokeColor={{
            '0%': '#1890ff',
            '100%': '#52c41a',
          }}
        />
      </div>

      {/* 统计 */}
      <Row gutter={16} style={{ marginBottom: 12 }}>
        <Col span={12}>
          <Statistic
            title={<span style={{ fontSize: 12, color: '#8c8c8c' }}>任务</span>}
            value={project.task_count || 0}
            prefix={<FolderOutlined style={{ color: '#1890ff' }} />}
            valueStyle={{ fontSize: 18 }}
          />
        </Col>
        <Col span={12}>
          <Statistic
            title={<span style={{ fontSize: 12, color: '#8c8c8c' }}>BUG</span>}
            value={project.bug_count || 0}
            prefix={<BugOutlined style={{ color: project.bug_count > 0 ? '#ff4d4f' : '#52c41a' }} />}
            valueStyle={{ fontSize: 18, color: project.bug_count > 0 ? '#ff4d4f' : '#52c41a' }}
          />
        </Col>
      </Row>

      {/* 时间 */}
      <div style={{ marginBottom: 12, fontSize: 12, color: '#8c8c8c' }}>
        <CalendarOutlined style={{ marginRight: 4 }} />
        {project.create_time ? new Date(project.create_time).toLocaleDateString() : '-'}
      </div>

      {/* 状态流转按钮 */}
      {nextStatus && (
        <Button
          type="primary"
          block
          icon={statusConfig[nextStatus].icon}
          onClick={() => onStatusChange(project.id, nextStatus)}
          style={{ borderRadius: 8 }}
        >
          {project.status === 'pending' ? '开始项目' : '完成项目'}
        </Button>
      )}
    </Card>
  )
}

// 项目详情内容
const ProjectDetail: React.FC<{ project: Project | null }> = ({ project }) => {
  if (!project) return null

  const workflowConf = workflowStages[project.workflow_stage] || { text: project.workflow_stage, progress: 0 }

  return (
    <div>
      <Descriptions bordered column={2} size="small">
        <Descriptions.Item label="项目名称" span={2}>
          {project.project_name}
        </Descriptions.Item>
        <Descriptions.Item label="项目编码">{project.project_code}</Descriptions.Item>
        <Descriptions.Item label="优先级">
          <Tag color={priorityConfig[project.priority]?.color}>
            {priorityConfig[project.priority]?.text || project.priority}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="状态">
          <Tag color={statusConfig[project.status]?.color} icon={statusConfig[project.status]?.icon}>
            {statusConfig[project.status]?.text || project.status}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="负责分身">
          <Tag color={agentTypeColors[project.agent_type]}>
            {agentTypeNames[project.agent_type] || project.agent_type}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="当前阶段" span={2}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Text>{workflowConf.text}</Text>
            <Progress
              percent={workflowConf.progress}
              size="small"
              strokeColor={{ '0%': '#1890ff', '100%': '#52c41a' }}
            />
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="描述" span={2}>
          {project.description || '暂无描述'}
        </Descriptions.Item>
        <Descriptions.Item label="创建时间">
          {project.create_time ? new Date(project.create_time).toLocaleString() : '-'}
        </Descriptions.Item>
        <Descriptions.Item label="更新时间">
          {project.update_time ? new Date(project.update_time).toLocaleString() : '-'}
        </Descriptions.Item>
      </Descriptions>

      <Row gutter={16} style={{ marginTop: 24 }}>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title="任务数量"
              value={project.task_count || 0}
              prefix={<FolderOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title="BUG数量"
              value={project.bug_count || 0}
              prefix={<BugOutlined />}
              valueStyle={{ color: project.bug_count > 0 ? '#ff4d4f' : '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title="完成进度"
              value={workflowConf.progress}
              suffix="%"
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}

const AgentProject: React.FC = () => {
  // 1. 路由参数
  const [searchParams, setSearchParams] = useSearchParams()

  // 2. 状态定义
  const [filters, setFilters] = useState<FilterState>({
    keyword: searchParams.get('keyword') ?? '',
    status: searchParams.get('status') ?? 'all',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [data, setData] = useState<Project[]>([])
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  })
  const [viewMode, setViewMode] = useState<'table' | 'card'>('card')

  // Modal 状态
  const [modalVisible, setModalVisible] = useState(false)
  const [modalLoading, setModalLoading] = useState(false)
  const [editingProject, setEditingProject] = useState<Project | null>(null)
  const [detailVisible, setDetailVisible] = useState(false)
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)

  const [form] = Form.useForm()

  // 防抖搜索
  const debouncedKeyword = useDebounce(filters.keyword, 300)

  // 3. 数据获取
  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, string | number> = {
        page: pagination.current,
        page_size: pagination.pageSize,
      }
      if (debouncedKeyword) {
        params.keyword = debouncedKeyword
      }
      if (filters.status && filters.status !== 'all') {
        params.status = filters.status
      }

      const response = await agentApi.getProjects(params as any) as any
      setData(response?.list || [])
      setPagination(prev => ({
        ...prev,
        total: response?.total || 0,
      }))
    } catch (err) {
      setError(err as Error)
      console.error('加载项目列表失败:', err)
    } finally {
      setLoading(false)
    }
  }, [debouncedKeyword, filters.status, pagination.current, pagination.pageSize])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // 4. 事件处理
  const handleFilterChange = useCallback((newFilters: Partial<FilterState>) => {
    const updated = { ...filters, ...newFilters }
    setFilters(updated)
    setPagination(prev => ({ ...prev, current: 1 }))

    // 同步到 URL
    const params = new URLSearchParams()
    if (updated.keyword) params.set('keyword', updated.keyword)
    if (updated.status && updated.status !== 'all') params.set('status', updated.status)
    setSearchParams(params)
  }, [filters, setSearchParams])

  const handleTableChange = (newPagination: any) => {
    setPagination(prev => ({
      ...prev,
      current: newPagination.current,
      pageSize: newPagination.pageSize,
    }))
  }

  const handleCreate = () => {
    setEditingProject(null)
    form.resetFields()
    form.setFieldsValue({
      priority: 'P2',
      agent_type: 'PM',
    })
    setModalVisible(true)
  }

  const handleEdit = (record: Project) => {
    setEditingProject(record)
    form.setFieldsValue({
      project_name: record.project_name,
      description: record.description,
      priority: record.priority,
      agent_type: record.agent_type,
    })
    setModalVisible(true)
  }

  const handleView = (record: Project) => {
    setSelectedProject(record)
    setDetailVisible(true)
  }

  const handleDelete = async (id: string) => {
    try {
      await agentApi.deleteProject(id)
      message.success('删除成功')
      fetchData()
    } catch (err) {
      message.error('删除失败')
    }
  }

  const handleStatusChange = async (id: string, status: ProjectStatus) => {
    try {
      await agentApi.updateProject(id, { status })
      message.success(`项目已${status === 'active' ? '启动' : '完成'}`)
      fetchData()
    } catch (err) {
      message.error('状态更新失败')
    }
  }

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields()
      setModalLoading(true)

      if (editingProject) {
        await agentApi.updateProject(editingProject.id, {
          project_name: values.project_name,
          description: values.description,
          priority: values.priority,
          agent_type: values.agent_type,
        })
        message.success('更新成功')
      } else {
        await agentApi.createProject({
          project_name: values.project_name,
          description: values.description,
          priority: values.priority,
        })
        message.success('创建成功')
      }

      setModalVisible(false)
      fetchData()
    } catch (err) {
      console.error('保存失败:', err)
      message.error('保存失败')
    } finally {
      setModalLoading(false)
    }
  }

  // 表格列定义
  const columns: ColumnsType<Project> = [
    {
      title: '项目名称',
      dataIndex: 'project_name',
      key: 'project_name',
      width: 200,
      ellipsis: true,
      render: (text, record) => (
        <Tooltip title={text}>
          <a onClick={() => handleView(record)}>{text}</a>
        </Tooltip>
      ),
    },
    {
      title: '项目编码',
      dataIndex: 'project_code',
      key: 'project_code',
      width: 120,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: ProjectStatus) => (
        <Tag color={statusConfig[status]?.color || 'default'} icon={statusConfig[status]?.icon}>
          {statusConfig[status]?.text || status}
        </Tag>
      ),
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 100,
      render: (priority: Priority) => (
        <Tag color={priorityConfig[priority]?.color || 'default'}>
          {priorityConfig[priority]?.text || priority}
        </Tag>
      ),
    },
    {
      title: '负责分身',
      dataIndex: 'agent_type',
      key: 'agent_type',
      width: 120,
      render: (agentType: AgentType) => (
        <Tag color={agentTypeColors[agentType]}>
          {agentTypeNames[agentType] || agentType}
        </Tag>
      ),
    },
    {
      title: '当前阶段',
      dataIndex: 'workflow_stage',
      key: 'workflow_stage',
      width: 120,
      render: (stage: string) => workflowStages[stage]?.text || stage,
    },
    {
      title: '任务/Bug',
      key: 'counts',
      width: 100,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="任务数">
            <Text>
              <FolderOutlined /> {record.task_count || 0}
            </Text>
          </Tooltip>
          <Tooltip title="Bug数">
            <Text type={record.bug_count > 0 ? 'danger' : 'secondary'}>
              <BugOutlined /> {record.bug_count || 0}
            </Text>
          </Tooltip>
        </Space>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'create_time',
      key: 'create_time',
      width: 160,
      render: (time: number) => (time ? new Date(time).toLocaleString() : '-'),
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleView(record)}
          >
            查看
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定删除该项目吗?"
            description="删除后数据将无法恢复"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // 5. 渲染
  return (
    <div style={{ padding: 24 }}>
      {/* 页面标题 */}
      <Title level={4} style={{ marginBottom: 24 }}>
        项目管理
      </Title>

      {/* 筛选区域 */}
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col flex="auto">
            <Space size="middle">
              <Search
                placeholder="搜索项目名称/编码"
                allowClear
                style={{ width: 280 }}
                value={filters.keyword}
                onChange={(e) => handleFilterChange({ keyword: e.target.value })}
                onSearch={(value) => handleFilterChange({ keyword: value })}
                enterButton={<SearchOutlined />}
              />
              <Select
                value={filters.status}
                onChange={(value) => handleFilterChange({ status: value })}
                style={{ width: 140 }}
              >
                <Option value="all">全部状态</Option>
                <Option value="pending">
                  <Badge status="default" text="待开始" />
                </Option>
                <Option value="active">
                  <Badge status="processing" text="进行中" />
                </Option>
                <Option value="completed">
                  <Badge status="success" text="已完成" />
                </Option>
                <Option value="cancelled">
                  <Badge status="error" text="已取消" />
                </Option>
              </Select>
            </Space>
          </Col>
          <Col>
            <Space>
              <Segmented
                value={viewMode}
                onChange={(value) => setViewMode(value as 'table' | 'card')}
                options={[
                  { value: 'card', icon: <AppstoreOutlined /> },
                  { value: 'table', icon: <UnorderedListOutlined /> },
                ]}
              />
              <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
                新建项目
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* 数据展示 */}
      {error ? (
        <ErrorState onRetry={fetchData} />
      ) : loading ? (
        <TableSkeleton />
      ) : data.length === 0 ? (
        <EmptyState />
      ) : viewMode === 'card' ? (
        <Row gutter={[16, 16]}>
          {data.map((project) => (
            <Col xs={24} sm={12} md={8} lg={6} key={project.id}>
              <ProjectCard
                project={project}
                onView={handleView}
                onEdit={handleEdit}
                onDelete={handleDelete}
                onStatusChange={handleStatusChange}
              />
            </Col>
          ))}
        </Row>
      ) : (
        <Card>
          <Table
            columns={columns}
            dataSource={data}
            rowKey="id"
            loading={loading}
            pagination={{
              ...pagination,
              showSizeChanger: true,
              showQuickJumper: true,
              showTotal: (total) => `共 ${total} 条`,
              pageSizeOptions: ['10', '20', '50', '100'],
            }}
            onChange={handleTableChange}
            scroll={{ x: 1300 }}
            size="middle"
          />
        </Card>
      )}

      {/* 创建/编辑项目 Modal */}
      <Modal
        title={editingProject ? '编辑项目' : '新建项目'}
        open={modalVisible}
        onOk={handleModalOk}
        onCancel={() => setModalVisible(false)}
        confirmLoading={modalLoading}
        width={520}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            priority: 'P2',
            agent_type: 'PM',
          }}
        >
          <Form.Item
            name="project_name"
            label="项目名称"
            rules={[{ required: true, message: '请输入项目名称' }]}
          >
            <Input placeholder="请输入项目名称" maxLength={100} />
          </Form.Item>

          <Form.Item name="description" label="项目描述">
            <Input.TextArea
              placeholder="请输入项目描述"
              rows={4}
              maxLength={500}
              showCount
            />
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="priority"
                label="优先级"
                rules={[{ required: true, message: '请选择优先级' }]}
              >
                <Select placeholder="请选择优先级">
                  {Object.entries(priorityConfig).map(([key, config]) => (
                    <Option key={key} value={key}>
                      <Tag color={config.color} style={{ marginRight: 0 }}>
                        {config.text}
                      </Tag>
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="agent_type"
                label="负责分身"
                rules={[{ required: true, message: '请选择负责分身' }]}
              >
                <Select placeholder="请选择负责分身">
                  {Object.entries(agentTypeNames).map(([key, name]) => (
                    <Option key={key} value={key}>
                      <Space>
                        <span style={{ color: agentTypeColors[key as AgentType] }}></span>
                        {name}
                      </Space>
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* 项目详情 Modal */}
      <Modal
        title="项目详情"
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDetailVisible(false)}>
            关闭
          </Button>,
          <Button
            key="edit"
            type="primary"
            onClick={() => {
              setDetailVisible(false)
              if (selectedProject) {
                handleEdit(selectedProject)
              }
            }}
          >
            编辑
          </Button>,
        ]}
        width={720}
      >
        <ProjectDetail project={selectedProject} />
      </Modal>
    </div>
  )
}

// Segmented 组件（如果 Antd 版本不支持）
const Segmented: React.FC<{
  value: string
  onChange: (value: string) => void
  options: { value: string; icon: React.ReactNode }[]
}> = ({ value, onChange, options }) => (
  <Space.Compact>
    {options.map((option) => (
      <Button
        key={option.value}
        type={value === option.value ? 'primary' : 'default'}
        icon={option.icon}
        onClick={() => onChange(option.value)}
      />
    ))}
  </Space.Compact>
)

export default AgentProject
