import { useState } from 'react'
import { Modal, Form, Input, message, Descriptions, Divider } from 'antd'
import { useAuthStore } from '@/stores/auth'
import api from '@/services/api'

interface ProfileModalProps {
  open: boolean
  onClose: () => void
}

const ProfileModal: React.FC<ProfileModalProps> = ({ open, onClose }) => {
  const { user, setUser } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()

  const handleSave = async () => {
    if (!user) return
    try {
      const values = await form.validateFields()
      setLoading(true)
      const data: Record<string, any> = {}
      if (values.real_name) data.real_name = values.real_name
      if (values.phone) data.phone = values.phone
      if (values.email) data.email = values.email
      if (values.new_password) data.password = values.new_password

      await api.put(`/system/admin/${user.adminId}`, data)
      message.success('保存成功')

      if (values.real_name) {
        setUser({ ...user, realName: values.real_name })
      }
      onClose()
    } catch (e: any) {
      if (e?.message) message.error(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      title="个人中心"
      open={open}
      onCancel={onClose}
      onOk={handleSave}
      okText="保存"
      confirmLoading={loading}
      width={520}
    >
      <Descriptions column={1} size="small" style={{ marginBottom: 16 }}>
        <Descriptions.Item label="用户名">{user?.username}</Descriptions.Item>
        <Descriptions.Item label="租户 ID">{user?.tenantId}</Descriptions.Item>
      </Descriptions>

      <Divider style={{ margin: '12px 0' }} />

      <Form
        form={form}
        layout="vertical"
        initialValues={{
          real_name: user?.realName || '',
          phone: '',
          email: '',
        }}
      >
        <Form.Item name="real_name" label="姓名">
          <Input placeholder="请输入姓名" />
        </Form.Item>
        <Form.Item name="phone" label="手机号">
          <Input placeholder="请输入手机号" />
        </Form.Item>
        <Form.Item name="email" label="邮箱">
          <Input placeholder="请输入邮箱" />
        </Form.Item>
        <Divider style={{ margin: '12px 0' }}>修改密码</Divider>
        <Form.Item name="new_password" label="新密码"
          rules={[{ min: 6, message: '密码至少6位' }]}
        >
          <Input.Password placeholder="留空则不修改" />
        </Form.Item>
        <Form.Item name="confirm_password" label="确认密码"
          dependencies={['new_password']}
          rules={[
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || !getFieldValue('new_password') || getFieldValue('new_password') === value) {
                  return Promise.resolve()
                }
                return Promise.reject(new Error('两次密码不一致'))
              },
            }),
          ]}
        >
          <Input.Password placeholder="再次输入新密码" />
        </Form.Item>
      </Form>
    </Modal>
  )
}

export default ProfileModal
