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
  InputNumber,
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
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { llmService, llmProviders, type LLMConfig, type LLMConfigForm } from '@/services/llm'

const { Option } = Select

// 骨架屏组件
const TableSkeleton = () => (
  <div style={{ padding: '16px 0' }}>
    <Skeleton active paragraph={{ rows: 5 }} />
  </div>
)

export default function LLMConfigList() {
  // 状态定义
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<LLMConfig[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [debouncedKeyword, setDebouncedKeyword] = useState('')

  // Modal states
  const [modalVisible, setModalVisible] = useState(false)
  const [modalLoading, setModalLoading] = useState(false)
  const [editingConfig, setEditingConfig] = useState<LLMConfig | null>(null)
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
      const result = (await llmService.list({
        page,
        page_size: pageSize,
        keyword: debouncedKeyword || undefined,
      })) as any
      setData(result?.list || result || [])
      setTotal(result?.total || (Array.isArray(result) ? result.length : 0))
    } catch (error) {
      console.error('获取 LLM 配置列表失败:', error)
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
    form.setFieldsValue({
      status: 1,
      max_tokens: 4096,
      temperature: 0.7,
    })
    setModalVisible(true)
  }, [form])

  const handleEdit = useCallback(async (record: LLMConfig) => {
    try {
      const result = (await llmService.get(record.id)) as unknown as LLMConfig
      setEditingConfig(result)
      form.setFieldsValue({
        name: result.name,
        provider: result.provider,
        base_url: result.base_url,
        api_key: result.api_key,
        model_name: result.model_name,
        max_tokens: result.max_tokens,
        temperature: result.temperature,
        status: result.status,
      })
      setModalVisible(true)
    } catch (error) {
      message.error('获取配置信息失败')
    }
  }, [form])

  const handleDelete = useCallback(async (id: number) => {
    try {
      await llmService.delete(id)
      message.success('删除成功')
      fetchData()
    } catch (error) {
      message.error('删除失败')
    }
  }, [])

  const handleTest = useCallback(async (id: number) => {
    setTestLoading(id)
    try {
      await llmService.test(id)
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
      await llmService.setDefault(id)
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

      const submitData: LLMConfigForm = {
        name: values.name,
        provider: values.provider,
        base_url: values.base_url,
        api_key: values.api_key,
        model_name: values.model_name,
        max_tokens: values.max_tokens,
        temperature: values.temperature,
        status: values.status ? 1 : 0,
      }

      if (editingConfig) {
        await llmService.update(editingConfig.id, submitData)
        message.success('更新成功')
      } else {
        await llmService.create(submitData)
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
  const columns: ColumnsType<LLMConfig> = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '配置名称', dataIndex: 'name', width: 150 },
    {
      title: '提供商',
      dataIndex: 'provider',
      width: 120,
      render: (provider) => {
        const found = llmProviders.find((p) => p.value === provider)
        return found?.label || provider
      },
    },
    { title: '模型', dataIndex: 'model_name', width: 180 },
    {
      title: 'Base URL',
      dataIndex: 'base_url',
      width: 200,
      ellipsis: true,
      render: (url) => (
        <Tooltip title={url}>
          <span>{url || '-'}</span>
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
      title="LLM 配置管理"
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
        <Empty description="暂无 LLM 配置" style={{ padding: '40px 0' }}>
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
          scroll={{ x: 1400 }}
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
        title={editingConfig ? '编辑 LLM 配置' : '新增 LLM 配置'}
        open={modalVisible}
        onOk={handleModalOk}
        onCancel={() => setModalVisible(false)}
        confirmLoading={modalLoading}
        width={600}
        destroyOnClose
      >
        <Form form={form} layout="vertical" initialValues={{ status: 1, max_tokens: 4096, temperature: 0.7 }}>
          <Form.Item
            name="name"
            label="配置名称"
            rules={[{ required: true, message: '请输入配置名称' }]}
          >
            <Input placeholder="例如：OpenAI 生产环境" />
          </Form.Item>

          <Form.Item
            name="provider"
            label="提供商"
            rules={[{ required: true, message: '请选择提供商' }]}
          >
            <Select placeholder="请选择提供商">
              {llmProviders.map((p) => (
                <Option key={p.value} value={p.value}>
                  {p.label}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="base_url"
            label="Base URL"
            extra="部分提供商需要自定义 API 地址，如 Azure、Ollama 等"
          >
            <Input placeholder="例如：https://api.openai.com/v1" />
          </Form.Item>

          <Form.Item
            name="api_key"
            label="API Key"
            rules={[{ required: true, message: '请输入 API Key' }]}
          >
            <Input.Password placeholder="请输入 API Key" />
          </Form.Item>

          <Form.Item
            name="model_name"
            label="模型名称"
            rules={[{ required: true, message: '请输入模型名称' }]}
          >
            <Input placeholder="例如：gpt-4、claude-3-opus-20240229" />
          </Form.Item>

          <Form.Item
            name="max_tokens"
            label="最大 Token 数"
            tooltip="控制生成的最大 token 数量"
          >
            <InputNumber min={1} max={128000} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            name="temperature"
            label="Temperature"
            tooltip="控制输出的随机性，0-2 之间，值越大越随机"
          >
            <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item name="status" label="状态" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="禁用" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
