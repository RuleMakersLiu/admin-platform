import { useState, useEffect } from 'react'
import { Table, Card, Button, Space, Tag, message, Popconfirm, Modal, Form, Input, Select, InputNumber, Switch } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'

const { Option } = Select

interface Menu {
  id: number
  parentId: number
  menuName: string
  menuType: number
  path: string
  component: string
  permission: string
  icon: string
  sort: number
  status: number
  visible: number
  children?: Menu[]
}

export default function MenuList() {
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<Menu[]>([])

  // Modal states
  const [modalVisible, setModalVisible] = useState(false)
  const [modalLoading, setModalLoading] = useState(false)
  const [editingMenu, setEditingMenu] = useState<Menu | null>(null)
  const { hasPermission } = useAuthStore()
  const canCreate = hasPermission('system:menu:create')
  const canEdit = hasPermission('system:menu:edit')
  const canDelete = hasPermission('system:menu:delete')

  const [form] = Form.useForm()

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    setLoading(true)
    try {
      const result = await api.get('/system/menu/list') as any[]
      // Build tree structure
      const tree = buildTree(result || [])
      setData(tree)
    } catch (error) {
      console.error('获取菜单列表失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const buildTree = (items: Menu[], parentId: number = 0): Menu[] => {
    return items
      .filter(item => item.parentId === parentId)
      .map(item => ({
        ...item,
        children: buildTree(items, item.id),
      }))
      .sort((a, b) => a.sort - b.sort)
  }

  const handleCreate = () => {
    setEditingMenu(null)
    form.resetFields()
    form.setFieldsValue({ status: 1, visible: 1, menu_type: 2, sort: 0, parent_id: 0 })
    setModalVisible(true)
  }

  const handleEdit = (record: Menu) => {
    setEditingMenu(record)
    form.setFieldsValue({
      parent_id: record.parentId,
      menu_name: record.menuName,
      menu_type: record.menuType,
      path: record.path,
      component: record.component,
      permission: record.permission,
      icon: record.icon,
      sort: record.sort,
      status: record.status,
      visible: record.visible,
    })
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/system/menu/${id}`)
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

      if (editingMenu) {
        await api.put(`/system/menu/${editingMenu.id}`, {
          menu_name: values.menu_name,
          menu_type: values.menu_type,
          path: values.path,
          component: values.component,
          permission: values.permission,
          icon: values.icon,
          sort: values.sort,
          status: values.status ? 1 : 0,
          visible: values.visible ? 1 : 0,
        })
        message.success('更新成功')
      } else {
        await api.post('/system/menu', {
          parent_id: values.parent_id,
          menu_name: values.menu_name,
          menu_type: values.menu_type,
          path: values.path,
          component: values.component,
          permission: values.permission,
          icon: values.icon,
          sort: values.sort,
          status: values.status ? 1 : 0,
          visible: values.visible ? 1 : 0,
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

  const columns: ColumnsType<Menu> = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    {
      title: '菜单名称',
      dataIndex: 'menuName',
      width: 200,
    },
    {
      title: '类型',
      dataIndex: 'menuType',
      width: 80,
      render: (type) => {
        const config: Record<number, { color: string; text: string }> = {
          1: { color: 'blue', text: '目录' },
          2: { color: 'green', text: '菜单' },
          3: { color: 'orange', text: '按钮' },
        }
        const c = config[type] || { color: 'default', text: '未知' }
        return <Tag color={c.color}>{c.text}</Tag>
      },
    },
    { title: '路径', dataIndex: 'path', width: 150, ellipsis: true },
    { title: '权限标识', dataIndex: 'permission', width: 150, ellipsis: true },
    { title: '图标', dataIndex: 'icon', width: 100 },
    { title: '排序', dataIndex: 'sort', width: 80 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: (status) => (
        <Tag color={status === 1 ? 'green' : 'red'}>
          {status === 1 ? '启用' : '禁用'}
        </Tag>
      ),
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
              title="确定删除该菜单吗？"
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

  // Flatten tree for parent select
  const flattenMenus = (items: Menu[]): Menu[] => {
    const result: Menu[] = []
    const flatten = (list: Menu[]) => {
      list.forEach(item => {
        result.push(item)
        if (item.children?.length) {
          flatten(item.children)
        }
      })
    }
    flatten(items)
    return result
  }

  return (
    <Card
      title="菜单管理"
      extra={
        canCreate && (
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新增菜单
          </Button>
        )
      }
    >
      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        pagination={false}
        defaultExpandAllRows
      />

      <Modal
        title={editingMenu ? '编辑菜单' : '新增菜单'}
        open={modalVisible}
        onOk={handleModalOk}
        onCancel={() => setModalVisible(false)}
        confirmLoading={modalLoading}
        width={550}
      >
        <Form form={form} layout="vertical" initialValues={{ status: 1, visible: 1, menu_type: 2, sort: 0, parent_id: 0 }}>
          <Form.Item name="parent_id" label="上级菜单">
            <Select placeholder="请选择上级菜单">
              <Option value={0}>顶级菜单</Option>
              {flattenMenus(data).map(m => (
                <Option key={m.id} value={m.id}>{m.menuName}</Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="menu_name"
            label="菜单名称"
            rules={[{ required: true, message: '请输入菜单名称' }]}
          >
            <Input placeholder="请输入菜单名称" />
          </Form.Item>

          <Form.Item name="menu_type" label="菜单类型" rules={[{ required: true }]}>
            <Select placeholder="请选择菜单类型">
              <Option value={1}>目录</Option>
              <Option value={2}>菜单</Option>
              <Option value={3}>按钮</Option>
            </Select>
          </Form.Item>

          <Form.Item name="path" label="路由路径">
            <Input placeholder="请输入路由路径，如 /system/admin" />
          </Form.Item>

          <Form.Item name="component" label="组件路径">
            <Input placeholder="请输入组件路径，如 system/admin/index" />
          </Form.Item>

          <Form.Item name="permission" label="权限标识">
            <Input placeholder="请输入权限标识，如 system:admin:view" />
          </Form.Item>

          <Form.Item name="icon" label="图标">
            <Input placeholder="请输入图标名称" />
          </Form.Item>

          <Form.Item name="sort" label="排序">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item name="status" label="状态" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="禁用" />
          </Form.Item>

          <Form.Item name="visible" label="菜单可见" valuePropName="checked">
            <Switch checkedChildren="显示" unCheckedChildren="隐藏" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
