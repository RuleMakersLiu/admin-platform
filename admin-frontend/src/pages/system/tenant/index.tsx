import { useState, useEffect } from 'react'
import { Table, Card, Button, Space, Tag, message, Popconfirm, Modal, Form, Input, Switch } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import api from '@/services/api'

interface Tenant {
  id: number
  tenantName: string
  tenantCode: string
  status: number
  createTime: number
}

export default function TenantList() {
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<Tenant[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')

  // Modal states
  const [modalVisible, setModalVisible] = useState(false)
  const [modalLoading, setModalLoading] = useState(false)
  const [editingTenant, setEditingTenant] = useState<Tenant | null>(null)

  const [form] = Form.useForm()

  useEffect(() => {
    fetchData()
  }, [page, pageSize])

  const fetchData = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.append('page', String(page))
      params.append('page_size', String(pageSize))
      if (keyword) params.append('keyword', keyword)

      const result = await api.get(`/system/tenant/list?${params}`) as any
      setData(result?.list || [])
      setTotal(result?.total || 0)
    } catch (error) {
      console.error('获取租户列表失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = () => {
    setPage(1)
    fetchData()
  }

  const handleCreate = () => {
    setEditingTenant(null)
    form.resetFields()
    form.setFieldsValue({ status: 1 })
    setModalVisible(true)
  }

  const handleEdit = (record: Tenant) => {
    setEditingTenant(record)
    form.setFieldsValue({
      tenant_name: record.tenantName,
      status: record.status,
    })
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/system/tenant/${id}`)
      message.success('删除成功')
      fetchData()
    } catch (error: any) {
      message.error(error?.message || '删除失败')
    }
  }

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields()
      setModalLoading(true)

      if (editingTenant) {
        // 更新
        await api.put(`/system/tenant/${editingTenant.id}`, {
          tenant_name: values.tenant_name,
          status: values.status ? 1 : 0,
        })
        message.success('更新成功')
      } else {
        // 创建
        await api.post('/system/tenant', {
          tenant_name: values.tenant_name,
          tenant_code: values.tenant_code,
          status: values.status ? 1 : 0,
        })
        message.success('创建成功')
      }

      setModalVisible(false)
      fetchData()
    } catch (error: any) {
      if (error?.errorFields) {
        // Form validation error
      } else {
        message.error(error?.message || '操作失败')
      }
    } finally {
      setModalLoading(false)
    }
  }

  const columns: ColumnsType<Tenant> = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '租户名称', dataIndex: 'tenantName' },
    { title: '租户编码', dataIndex: 'tenantCode' },
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
      dataIndex: 'createTime',
      width: 160,
      render: (time) => time ? new Date(time).toLocaleString() : '-',
    },
    {
      title: '操作',
      width: 150,
      render: (_, record) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确定删除该租户吗？"
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

  return (
    <Card
      title="租户管理"
      extra={
        <Space>
          <Input.Search
            placeholder="搜索租户名称/编码"
            allowClear
            style={{ width: 200 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onSearch={handleSearch}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新增租户
          </Button>
        </Space>
      }
    >
      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
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

      <Modal
        title={editingTenant ? '编辑租户' : '新增租户'}
        open={modalVisible}
        onOk={handleModalOk}
        onCancel={() => setModalVisible(false)}
        confirmLoading={modalLoading}
        width={500}
      >
        <Form form={form} layout="vertical" initialValues={{ status: 1 }}>
          <Form.Item
            name="tenant_name"
            label="租户名称"
            rules={[{ required: true, message: '请输入租户名称' }]}
          >
            <Input placeholder="请输入租户名称" />
          </Form.Item>

          <Form.Item
            name="tenant_code"
            label="租户编码"
            rules={[
              { required: true, message: '请输入租户编码' },
              { pattern: /^[a-zA-Z0-9_]+$/, message: '编码只能包含字母、数字和下划线' },
            ]}
          >
            <Input placeholder="请输入租户编码" disabled={!!editingTenant} />
          </Form.Item>

          <Form.Item name="status" label="状态" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="禁用" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
