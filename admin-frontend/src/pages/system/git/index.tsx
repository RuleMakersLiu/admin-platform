import { useState, useEffect, useCallback } from 'react'
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
} from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ApiOutlined,
  StarOutlined,
  GithubOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { gitService, gitPlatforms, type GitConfig, type GitConfigForm } from '@/services/git'

const { Option } = Select
const { TextArea } = Input

// 骨架屏组件
const TableSkeleton = () => (
  <div style={{ padding: '16px 0' }}>
    <Skeleton active paragraph={{ rows: 5 }} />
  </div>
)

// 平台图标映射
const PlatformIcon = ({ platform }: { platform: string }) => {
  if (platform === 'github') return <GithubOutlined style={{ marginRight: 4 }} />
  return null
}

export default function GitConfigList() {
  // 状态定义
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<GitConfig[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [debouncedKeyword, setDebouncedKeyword] = useState('')

  // Modal states
  const [modalVisible, setModalVisible] = useState(false)
  const [modalLoading, setModalLoading] = useState(false)
  const [editingConfig, setEditingConfig] = useState<GitConfig | null>(null)
  const [testLoading, setTestLoading] = useState<number | null>(null)

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
  }, [page, pageSize, debouncedKeyword])

  const fetchData = async () => {
    setLoading(true)
    try {
      const result = (await gitService.list({
        page,
        page_size: pageSize,
        keyword: debouncedKeyword || undefined,
      })) as any
      setData(result?.list || result || [])
      setTotal(result?.total || (Array.isArray(result) ? result.length : 0))
    } catch (error) {
      console.error('获取 Git 配置列表失败:', error)
      setData([])
    } finally {
      setLoading(false)
    }
  }

  // 事件处理
  const handleSearch = useCallback(() => {
    setPage(1)
    fetchData()
  }, [])

  const handleCreate = useCallback(() => {
    setEditingConfig(null)
    form.resetFields()
    form.setFieldsValue({ status: 1 })
    setModalVisible(true)
  }, [form])

  const handleEdit = useCallback(async (record: GitConfig) => {
    try {
      const result = (await gitService.get(record.id)) as unknown as GitConfig
      setEditingConfig(result)
      form.setFieldsValue({
        name: result.name,
        platform: result.platform,
        base_url: result.base_url,
        access_token: result.access_token,
        webhook_secret: result.webhook_secret,
        ssh_key: result.ssh_key,
        status: result.status,
      })
      setModalVisible(true)
    } catch (error) {
      message.error('获取配置信息失败')
    }
  }, [form])

  const handleDelete = useCallback(async (id: number) => {
    try {
      await gitService.delete(id)
      message.success('删除成功')
      fetchData()
    } catch (error) {
      message.error('删除失败')
    }
  }, [])

  const handleTest = useCallback(async (id: number) => {
    setTestLoading(id)
    try {
      await gitService.test(id)
      message.success('连接测试成功')
      fetchData()
    } catch (error) {
      message.error('连接测试失败')
    } finally {
      setTestLoading(null)
    }
  }, [])

  const handleSetDefault = useCallback(async (id: number) => {
    try {
      await gitService.setDefault(id)
      message.success('已设为默认配置')
      fetchData()
    } catch (error) {
      message.error('设置默认失败')
    }
  }, [])

  const handleModalOk = useCallback(async () => {
    try {
      const values = await form.validateFields()
      setModalLoading(true)

      const submitData: GitConfigForm = {
        name: values.name,
        platform: values.platform,
        base_url: values.base_url,
        access_token: values.access_token,
        webhook_secret: values.webhook_secret,
        ssh_key: values.ssh_key,
        status: values.status ? 1 : 0,
      }

      if (editingConfig) {
        await gitService.update(editingConfig.id, submitData)
        message.success('更新成功')
      } else {
        await gitService.create(submitData)
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
  }, [editingConfig, form])

  // 表格列定义
  const columns: ColumnsType<GitConfig> = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '配置名称', dataIndex: 'name', width: 150 },
    {
      title: '平台',
      dataIndex: 'platform',
      width: 120,
      render: (platform) => {
        const found = gitPlatforms.find((p) => p.value === platform)
        return (
          <span>
            <PlatformIcon platform={platform} />
            {found?.label || platform}
          </span>
        )
      },
    },
    {
      title: 'Base URL',
      dataIndex: 'base_url',
      width: 200,
      ellipsis: true,
      render: (url) => (
        <Tooltip title={url}>
          <span>{url || '默认'}</span>
        </Tooltip>
      ),
    },
    {
      title: 'Access Token',
      dataIndex: 'access_token',
      width: 150,
      render: (token) => (
        <Tooltip title={token}>
          <span>{token ? `${token.slice(0, 8)}****` : '-'}</span>
        </Tooltip>
      ),
    },
    {
      title: '默认',
      dataIndex: 'is_default',
      width: 80,
      render: (isDefault) =>
        isDefault === 1 ? (
          <Tag color="gold" icon={<StarOutlined />}>
            默认
          </Tag>
        ) : (
          '-'
        ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (status) => (
        <Tag color={status === 1 ? 'green' : 'red'}>
          {status === 1 ? '启用' : '禁用'}
        </Tag>
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
      width: 220,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="测试连接">
            <Button
              type="link"
              size="small"
              icon={<ApiOutlined />}
              loading={testLoading === record.id}
              onClick={() => handleTest(record.id)}
            >
              测试
            </Button>
          </Tooltip>
          {record.is_default !== 1 && (
            <Popconfirm
              title="确定设为默认配置吗？"
              onConfirm={() => handleSetDefault(record.id)}
            >
              <Button type="link" size="small" icon={<StarOutlined />}>
                设为默认
              </Button>
            </Popconfirm>
          )}
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定删除该配置吗？"
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

  // 渲染
  return (
    <Card
      title="Git 配置管理"
      extra={
        <Space>
          <Input.Search
            placeholder="搜索配置名称"
            allowClear
            style={{ width: 200 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onSearch={handleSearch}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新增配置
          </Button>
        </Space>
      }
    >
      {/* 三态处理：加载中 */}
      {loading ? (
        <TableSkeleton />
      ) : /* 空状态 */
      !data.length ? (
        <Empty description="暂无 Git 配置" style={{ padding: '40px 0' }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            添加配置
          </Button>
        </Empty>
      ) : (
        /* 数据展示 */
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          scroll={{ x: 1300 }}
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

      {/* 新建/编辑弹窗 */}
      <Modal
        title={editingConfig ? '编辑 Git 配置' : '新增 Git 配置'}
        open={modalVisible}
        onOk={handleModalOk}
        onCancel={() => setModalVisible(false)}
        confirmLoading={modalLoading}
        width={600}
        destroyOnClose
      >
        <Form form={form} layout="vertical" initialValues={{ status: 1 }}>
          <Form.Item
            name="name"
            label="配置名称"
            rules={[{ required: true, message: '请输入配置名称' }]}
          >
            <Input placeholder="例如：公司 GitLab" />
          </Form.Item>

          <Form.Item
            name="platform"
            label="平台类型"
            rules={[{ required: true, message: '请选择平台类型' }]}
          >
            <Select placeholder="请选择平台类型">
              {gitPlatforms.map((p) => (
                <Option key={p.value} value={p.value}>
                  {p.label}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="base_url"
            label="Base URL"
            extra="自建平台需要填写完整地址，如 https://gitlab.company.com"
          >
            <Input placeholder="例如：https://gitlab.company.com" />
          </Form.Item>

          <Form.Item
            name="access_token"
            label="Access Token"
            rules={[{ required: true, message: '请输入 Access Token' }]}
            extra="在 Git 平台的设置中生成 Personal Access Token"
          >
            <Input.Password placeholder="请输入 Access Token" />
          </Form.Item>

          <Form.Item
            name="webhook_secret"
            label="Webhook Secret"
            extra="用于验证 Webhook 请求的密钥"
          >
            <Input.Password placeholder="请输入 Webhook Secret" />
          </Form.Item>

          <Form.Item
            name="ssh_key"
            label="SSH 私钥"
            extra="用于 SSH 方式克隆仓库的私钥"
          >
            <TextArea
              rows={4}
              placeholder="-----BEGIN RSA PRIVATE KEY-----&#10;...&#10;-----END RSA PRIVATE KEY-----"
              style={{ fontFamily: 'monospace' }}
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
