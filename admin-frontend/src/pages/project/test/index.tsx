import React, { useState, useEffect, useRef } from 'react'
import { Card, Select, Button, Table, Tag, Space, Typography, message, Progress, Modal } from 'antd'
import {
  PlayCircleOutlined, StopOutlined, ReloadOutlined,
  CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined,
  BugOutlined, FileTextOutlined,
} from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import { generatorApi, deployApi } from '@/services/api'

const { Text, Title } = Typography

const STATUS_MAP: Record<number, { text: string; color: string; icon: React.ReactNode }> = {
  1: { text: '待执行', color: 'default', icon: null },
  2: { text: '执行中', color: 'processing', icon: <LoadingOutlined /> },
  3: { text: '成功', color: 'success', icon: <CheckCircleOutlined /> },
  4: { text: '失败', color: 'error', icon: <CloseCircleOutlined /> },
  5: { text: '已取消', color: 'warning', icon: <StopOutlined /> },
}

const TEST_TYPES = [
  { label: '单元测试', value: 'unit' },
  { label: '集成测试', value: 'integration' },
  { label: 'E2E测试', value: 'e2e' },
  { label: '自定义', value: 'custom' },
]

const ProjectTestPage: React.FC = () => {
  const [searchParams] = useSearchParams()
  const preselectedProjectId = searchParams.get('project_id')

  const [projects, setProjects] = useState<any[]>([])
  const [selectedProject, setSelectedProject] = useState<string | undefined>(preselectedProjectId || undefined)
  const [testTasks, setTestTasks] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [createLoading, setCreateLoading] = useState(false)
  const [logVisible, setLogVisible] = useState(false)
  const [logContent, setLogContent] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(false)
  const timerRef = useRef<any>(null)

  useEffect(() => {
    generatorApi.getProjects({ page: 1, page_size: 100 }).then((data: any) => {
      setProjects(data?.list || [])
    }).catch(() => {})
  }, [])

  useEffect(() => {
    fetchTestTasks()
  }, [page, selectedProject])

  useEffect(() => {
    if (autoRefresh) {
      timerRef.current = setInterval(fetchTestTasks, 3000)
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [autoRefresh, page, selectedProject])

  const fetchTestTasks = async () => {
    setLoading(true)
    try {
      const params: any = { page, page_size: 10 }
      if (selectedProject) params.project_id = selectedProject
      const data: any = await deployApi.getTestTasks(params)
      setTestTasks(data?.list || [])
      setTotal(data?.total || 0)

      // Auto-refresh if any task is running
      const hasRunning = (data?.list || []).some((t: any) => t.status === 2)
      if (hasRunning && !autoRefresh) setAutoRefresh(true)
      if (!hasRunning && autoRefresh) setAutoRefresh(false)
    } catch (e: any) {
      if (!autoRefresh && page === 1) {
        message.warning(e?.message || '测试服务暂时不可用')
      }
    }
    setLoading(false)
  }

  const handleCreateTest = async () => {
    if (!selectedProject) {
      message.warning('请选择项目')
      return
    }
    // 检查项目是否关联了仓库
    const proj = projects.find((p: any) => String(p.id) === selectedProject)
    if (proj && !proj.repo_url) {
      message.warning('请先在项目列表中关联 Git 仓库')
      return
    }
    setCreateLoading(true)
    try {
      const data: any = await deployApi.createTestTask({
        project_id: parseInt(selectedProject),
        type: 'unit',
      })
      message.success('测试任务创建成功，沙箱环境中执行中...')
      // Auto-execute
      await deployApi.executeTestTask(data.id)
      setAutoRefresh(true)
      fetchTestTasks()
    } catch (e: any) {
      message.error(e?.message || '创建失败')
    }
    setCreateLoading(false)
  }

  const handleViewLog = async (id: number) => {
    try {
      const data: any = await deployApi.getTestTaskLogs(id)
      setLogContent(data?.log || '暂无日志')
      setLogVisible(true)
    } catch { /* ignore */ }
  }

  const handleCancel = async (id: number) => {
    try {
      await deployApi.cancelTestTask(id)
      message.success('任务已取消')
      fetchTestTasks()
    } catch (e: any) {
      message.error(e?.message || '取消失败')
    }
  }

  const columns = [
    {
      title: '任务编号',
      dataIndex: 'task_no',
      key: 'task_no',
      render: (no: string) => <Text code style={{ fontSize: 12 }}>{no}</Text>,
    },
    {
      title: '项目ID',
      dataIndex: 'project_id',
      key: 'project_id',
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type: string) => <Tag>{TEST_TYPES.find(t => t.value === type)?.label || type}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: number) => {
        const info = STATUS_MAP[status] || { text: '未知', color: 'default', icon: null }
        return (
          <Tag icon={info.icon} color={info.color}>
            {info.text}
          </Tag>
        )
      },
    },
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      render: (p: number) => <Progress percent={p} size="small" style={{ width: 80 }} />,
    },
    {
      title: '通过/总计',
      key: 'cases',
      render: (_: any, record: any) => (
        <span>
          <span style={{ color: '#52c41a' }}>{record.passed_cases}</span>
          {' / '}
          <span style={{ color: '#ff4d4f' }}>{record.failed_cases}</span>
          {' / '}
          {record.total_cases}
        </span>
      ),
    },
    {
      title: '覆盖率',
      dataIndex: 'coverage',
      key: 'coverage',
      render: (cov: number | null) => cov != null ? `${cov.toFixed(1)}%` : '-',
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<FileTextOutlined />} onClick={() => handleViewLog(record.id)}>
            日志
          </Button>
          {record.status === 2 && (
            <Button size="small" danger icon={<StopOutlined />} onClick={() => handleCancel(record.id)}>
              取消
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0, color: '#111827' }}>
          <BugOutlined style={{ marginRight: 8 }} />
          测试中心
        </Title>
        <Space>
          <Select
            style={{ width: 240 }}
            placeholder="选择项目"
            value={selectedProject}
            onChange={setSelectedProject}
            options={projects.map((p: any) => ({ label: p.name, value: String(p.id) }))}
            allowClear
          />
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleCreateTest}
            loading={createLoading}
            disabled={!selectedProject}
          >
            运行测试
          </Button>
          <Button icon={<ReloadOutlined />} onClick={fetchTestTasks}>
            刷新
          </Button>
          {autoRefresh && (
            <Tag icon={<LoadingOutlined />} color="processing">
              自动刷新中
            </Tag>
          )}
        </Space>
      </div>

      <Card style={{
        background: '#ffffff',
        border: '1px solid #e5eaf3',
        borderRadius: 12,
      }}>
        <Table
          dataSource={testTasks}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 10,
            onChange: setPage,
            showTotal: t => `共 ${t} 个测试任务`,
          }}
        />
      </Card>

      <Modal
        title="测试日志"
        open={logVisible}
        onCancel={() => setLogVisible(false)}
        width={800}
        footer={null}
        styles={{
          body: { background: '#f8fafd', padding: 16, maxHeight: '70vh', overflow: 'auto' },
        }}
      >
        <pre style={{
          color: '#243044', fontSize: 12, whiteSpace: 'pre-wrap',
          fontFamily: 'monospace', lineHeight: 1.6, margin: 0,
        }}>
          {logContent}
        </pre>
      </Modal>
    </div>
  )
}

export default ProjectTestPage
