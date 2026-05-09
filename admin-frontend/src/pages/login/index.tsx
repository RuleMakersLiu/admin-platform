import { useState } from 'react'
import { Form, Input, Button, message } from 'antd'
import { UserOutlined, LockOutlined, RocketOutlined } from '@ant-design/icons'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/services/api'
import './login.css'

interface LoginForm {
  username: string
  password: string
}

export default function Login() {
  const [loading, setLoading] = useState(false)
  const { setToken, setUser } = useAuthStore()

  const onFinish = async (values: LoginForm) => {
    setLoading(true)
    try {
      const data: any = await authApi.login({
        username: values.username,
        password: values.password,
        tenantId: 1, // 默认租户ID，实际租户由后端根据用户分配返回
      })
      setToken(data.token)
      // 获取用户信息
      const userInfo: any = await authApi.getInfo()
      setUser({
        adminId: userInfo.adminId,
        username: userInfo.username,
        realName: userInfo.realName || userInfo.username,
        tenantId: userInfo.tenantId,
        permissions: userInfo.permissions || [],
      })
      message.success('登录成功')
      // 使用硬导航确保页面刷新后能正确读取 persist 存储的 token
      window.location.href = '/'
    } catch (error) {
      // 错误已在拦截器处理
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="tech-login-container">
      {/* 动态背景 */}
      <div className="tech-bg">
        <div className="tech-grid"></div>
        <div className="tech-orbs">
          <div className="orb orb-1"></div>
          <div className="orb orb-2"></div>
          <div className="orb orb-3"></div>
        </div>
      </div>

      {/* 登录卡片 */}
      <div className="tech-login-card">
        <div className="tech-card-glow"></div>
        <div className="tech-card-content">
          {/* Logo区域 */}
          <div className="tech-logo">
            <RocketOutlined className="tech-logo-icon" />
            <h1 className="tech-title">ADMIN PLATFORM</h1>
            <p className="tech-subtitle">Next Generation Management System</p>
          </div>

          {/* 表单区域 */}
          <Form
            name="login"
            initialValues={{ username: 'admin' }}
            onFinish={onFinish}
            size="large"
            layout="vertical"
          >
            <Form.Item
              name="username"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input
                prefix={<UserOutlined className="tech-input-icon" />}
                placeholder="用户名"
                className="tech-input"
              />
            </Form.Item>
            <Form.Item
              name="password"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password
                prefix={<LockOutlined className="tech-input-icon" />}
                placeholder="密码"
                className="tech-input"
              />
            </Form.Item>
            <Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                block
                className="tech-login-btn"
              >
                {loading ? '正在验证...' : '进入系统'}
              </Button>
            </Form.Item>
          </Form>

          {/* 底部装饰 */}
          <div className="tech-footer">
            <div className="tech-line"></div>
            <span className="tech-footer-text">SECURE ACCESS</span>
            <div className="tech-line"></div>
          </div>
        </div>
      </div>

      {/* 角落装饰 */}
      <div className="tech-corner tech-corner-tl"></div>
      <div className="tech-corner tech-corner-tr"></div>
      <div className="tech-corner tech-corner-bl"></div>
      <div className="tech-corner tech-corner-br"></div>
    </div>
  )
}
