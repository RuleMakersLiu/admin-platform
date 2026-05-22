import { useState, useEffect, type Key } from 'react'
import { Table, Card, Button, Space, Tag, message, Popconfirm, Modal, Form, Input, Switch, Tree, Alert } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'

interface Group {
  id: number
  groupName: string
  power: string[] | string
  powerText?: string
  isSuper?: boolean
  status: number
  createTime: number
}

export default function GroupList() {
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<Group[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')

  // Modal states
  const [modalVisible, setModalVisible] = useState(false)
  const [modalLoading, setModalLoading] = useState(false)
  const [editingGroup, setEditingGroup] = useState<Group | null>(null)
  const [permissionTree, setPermissionTree] = useState<any[]>([])
  const [checkedPermissions, setCheckedPermissions] = useState<Key[]>([])
  const { hasPermission } = useAuthStore()
  const canCreate = hasPermission('system:group:create')
  const canEdit = hasPermission('system:group:edit')
  const canDelete = hasPermission('system:group:delete')

  const [form] = Form.useForm()

  useEffect(() => {
    fetchData()
    fetchPermissionTree()
  }, [page, pageSize])

  const fetchData = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.append('page', String(page))
      params.append('page_size', String(pageSize))
      if (keyword) params.append('keyword', keyword)

      const result = await api.get(`/system/group/list?${params}`) as any
      setData(result?.list || [])
      setTotal(result?.total || 0)
    } catch (error) {
      console.error('获取角色列表失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchPermissionTree = async () => {
    try {
      const result = await api.get('/system/permission/tree') as any[]
      setPermissionTree(result || [])
    } catch (error) {
      setPermissionTree([])
    }
  }

  const parsePower = (power: Group['power']) => {
    if (Array.isArray(power)) return power
    if (!power) return []
    try {
      return JSON.parse(power)
    } catch {
      return String(power).split(',').map((item) => item.trim()).filter(Boolean)
    }
  }

  const handleSearch = () => {
    setPage(1)
    fetchData()
  }

  const handleCreate = () => {
    setEditingGroup(null)
    form.resetFields()
    setCheckedPermissions([])
    form.setFieldsValue({ status: 1 })
    setModalVisible(true)
  }

  const handleEdit = (record: Group) => {
    setEditingGroup(record)
    setCheckedPermissions(parsePower(record.power))
    form.setFieldsValue({
      group_name: record.groupName,
      status: record.status,
    })
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/system/group/${id}`)
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

      if (editingGroup) {
        // 更新
        await api.put(`/system/group/${editingGroup.id}`, {
          group_name: values.group_name,
          power: checkedPermissions,
          status: values.status ? 1 : 0,
        })
        message.success('更新成功')
      } else {
        // 创建
        await api.post('/system/group', {
          group_name: values.group_name,
          power: checkedPermissions,
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
        // Form validation error
      } else {
        message.error('操作失败')
      }
    } finally {
      setModalLoading(false)
    }
  }

  const columns: ColumnsType<Group> = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '角色名称', dataIndex: 'groupName' },
    {
      title: '权限数',
      dataIndex: 'power',
      width: 100,
      render: (power) => <Tag color="blue">{parsePower(power).filter((item: string) => item !== '*').length}</Tag>,
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
      dataIndex: 'createTime',
      width: 160,
      render: (time) => time ? new Date(time).toLocaleString() : '-',
    },
    {
      title: '操作',
      width: 150,
      render: (_, record) => (
        <Space>
          {canEdit && (
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
              编辑
            </Button>
          )}
          {canDelete && (
            <Popconfirm
              title="确定删除该角色吗？"
              onConfirm={() => handleDelete(record.id)}
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Card
      title="角色管理"
      extra={
        <Space>
          <Input.Search
            placeholder="搜索角色名称"
            allowClear
            style={{ width: 200 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onSearch={handleSearch}
          />
          {canCreate && (
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
              新增角色
            </Button>
          )}
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
        title={editingGroup ? '编辑角色' : '新增角色'}
        open={modalVisible}
        onOk={handleModalOk}
        onCancel={() => setModalVisible(false)}
        confirmLoading={modalLoading}
        width={720}
      >
        <Form form={form} layout="vertical" initialValues={{ status: 1 }}>
          <Form.Item
            name="group_name"
            label="角色名称"
            rules={[{ required: true, message: '请输入角色名称' }]}
          >
            <Input placeholder="请输入角色名称" />
          </Form.Item>

          <Form.Item label="权限配置">
            <Alert
              type="info"
              showIcon
              message="按菜单和按钮勾选权限"
              description="保存后会写入角色 power，并同步给网关做接口鉴权；超级管理员角色可使用 * 通配权限。"
              style={{ marginBottom: 12 }}
            />
            <Tree
              checkable
              selectable={false}
              treeData={permissionTree}
              checkedKeys={checkedPermissions}
              onCheck={(keys) => setCheckedPermissions(Array.isArray(keys) ? keys : keys.checked)}
              height={320}
              defaultExpandAll
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
