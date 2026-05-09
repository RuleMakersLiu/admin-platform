import { useState, useEffect } from 'react'
import { Table, Card, Button, Space, Tag, message, Popconfirm, Modal, Form, Input, Select, Switch } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import api from '@/services/api'

const { Option } = Select

interface Admin {
  id: number
  username: string
  realName: string
  email: string
  phone: string
  adminGroupId: number
  groupName: string
  tenantId?: number
  tenantName?: string
  status: number
  lastLoginTime: number
  createTime: number
}

interface Group {
  id: number
  groupName: string
}

interface Tenant {
  id: number
  name: string
  code: string
}

export default function AdminList() {
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<Admin[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')

  // Modal states
  const [modalVisible, setModalVisible] = useState(false)
  const [modalLoading, setModalLoading] = useState(false)
  const [editingAdmin, setEditingAdmin] = useState<Admin | null>(null)
  const [groups, setGroups] = useState<Group[]>([])
  const [tenants, setTenants] = useState<Tenant[]>([])

  const [form] = Form.useForm()

  useEffect(() => {
    fetchData()
    fetchGroups()
    fetchTenants()
  }, [page, pageSize])

  const fetchData = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.append('page', String(page))
      params.append('page_size', String(pageSize))
      if (keyword) params.append('keyword', keyword)

      const result = await api.get(`/system/admin/list?${params}`) as any
      setData(result?.list || [])
      setTotal(result?.total || 0)
    } catch (error) {
      console.error('获取用户列表失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchGroups = async () => {
    try {
      const result = await api.get('/system/group/all') as any
      setGroups(result || [])
    } catch (error) {
      console.error('获取角色列表失败:', error)
    }
  }

  const fetchTenants = async () => {
    try {
      const result = await api.get('/system/tenant/all') as any
      setTenants(result || [])
    } catch (error) {
      console.error('获取租户列表失败:', error)
    }
  }

  const handleSearch = () => {
    setPage(1)
    fetchData()
  }

  const handleCreate = () => {
    setEditingAdmin(null)
    form.resetFields()
    form.setFieldsValue({ status: 1, admin_group_id: undefined })
    setModalVisible(true)
  }

  const handleEdit = async (record: Admin) => {
    try {
      const result = await api.get(`/system/admin/${record.id}`) as any
      setEditingAdmin(result)
      form.setFieldsValue({
        username: result.username,
        real_name: result.realName,
        phone: result.phone,
        email: result.email,
        admin_group_id: result.adminGroupId,
        tenant_id: result.tenantId || 1,
        status: result.status,
      })
      setModalVisible(true)
    } catch (error) {
      message.error('获取用户信息失败')
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/system/admin/${id}`)
      message.success('删除成功')
      fetchData()
    } catch (error) {
      message.error('删除失败')
    }
  }

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields()
      setModalLoading(true)

      if (editingAdmin) {
        // 更新
        await api.put(`/system/admin/${editingAdmin.id}`, {
          real_name: values.real_name,
          phone: values.phone,
          email: values.email,
          admin_group_id: values.admin_group_id,
          status: values.status ? 1 : 0,
          password: values.password || undefined,
        })
        message.success('更新成功')
      } else {
        // 创建
        await api.post('/system/admin', {
          username: values.username,
          password: values.password,
          real_name: values.real_name,
          phone: values.phone,
          email: values.email,
          admin_group_id: values.admin_group_id,
          tenant_id: values.tenant_id || 1,
          status: values.status ? 1 : 0,
        })
        message.success('创建成功')
      }

      setModalVisible(false)
      fetchData()
    } catch (error: any) {
      if (error?.message) {
        message.error(error.message)
      } else if (error?.errorFields) {
        // Form validation error, ignore
      } else {
        message.error('操作失败')
      }
    } finally {
      setModalLoading(false)
    }
  }

  const columns: ColumnsType<Admin> = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '用户名', dataIndex: 'username' },
    { title: '姓名', dataIndex: 'realName' },
    { title: '邮箱', dataIndex: 'email' },
    { title: '手机', dataIndex: 'phone' },
    { title: '角色', dataIndex: 'groupName' },
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
            title="确定删除该用户吗？"
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
      title="用户管理"
      extra={
        <Space>
          <Input.Search
            placeholder="搜索用户名/姓名"
            allowClear
            style={{ width: 200 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onSearch={handleSearch}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新增用户
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
        title={editingAdmin ? '编辑用户' : '新增用户'}
        open={modalVisible}
        onOk={handleModalOk}
        onCancel={() => setModalVisible(false)}
        confirmLoading={modalLoading}
        width={500}
      >
        <Form form={form} layout="vertical" initialValues={{ status: 1 }}>
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input placeholder="请输入用户名" disabled={!!editingAdmin} />
          </Form.Item>

          <Form.Item
            name="password"
            label="密码"
            rules={editingAdmin ? [] : [{ required: true, message: '请输入密码' }]}
          >
            <Input.Password placeholder={editingAdmin ? '不修改请留空' : '请输入密码'} />
          </Form.Item>

          <Form.Item
            name="real_name"
            label="姓名"
            rules={[{ required: true, message: '请输入姓名' }]}
          >
            <Input placeholder="请输入姓名" />
          </Form.Item>

          <Form.Item name="phone" label="手机">
            <Input placeholder="请输入手机号" />
          </Form.Item>

          <Form.Item name="email" label="邮箱">
            <Input placeholder="请输入邮箱" />
          </Form.Item>

          <Form.Item
            name="admin_group_id"
            label="角色"
            rules={[{ required: true, message: '请选择角色' }]}
          >
            <Select placeholder="请选择角色">
              {groups.map((g) => (
                <Option key={g.id} value={g.id}>
                  {g.groupName}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="tenant_id"
            label="租户"
            rules={[{ required: true, message: '请选择租户' }]}
          >
            <Select placeholder="请选择租户">
              {tenants.map((t) => (
                <Option key={t.id} value={t.id}>
                  {t.name}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item name="status" label="状态" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="禁用" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
