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
  BookOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  knowledgeService,
  knowledgeCategories,
  agentTypeOptions,
  commonTags,
  type Knowledge,
  type KnowledgeForm,
} from '@/services/knowledge'

const { Option } = Select
const { TextArea } = Input

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

  const handleDelete = useCallback(async (id: number) => {
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
    const found = knowledgeCategories.find((c) => c.value === category)
    return found?.label || category
  }

  // 获取分类颜色
  const getCategoryColor = (category: string) => {
    const colorMap: Record<string, string> = {
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

  // 渲染
  return (
    <Card
      title={
        <Space>
          <BookOutlined />
          知识库管理
        </Space>
      }
      extra={
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
      }
    >
      {/* 三态处理：加载中 */}
      {loading ? (
        <TableSkeleton />
      ) : /* 空状态 */
      !data.length ? (
        <Empty description="暂无知识条目" style={{ padding: '40px 0' }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            添加知识
          </Button>
        </Empty>
      ) : (
        /* 数据展示 */
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
