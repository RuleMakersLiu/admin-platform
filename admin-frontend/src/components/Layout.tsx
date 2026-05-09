import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout as AntLayout, Menu, Dropdown, Avatar } from 'antd'
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SettingOutlined,
  LogoutOutlined,
  UserOutlined,
  RocketOutlined,
  RobotOutlined,
  GithubOutlined,
  BookOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/services/api'
import type { MenuProps } from 'antd'
import './Layout.css'

const { Header, Sider, Content } = AntLayout

interface MenuItem {
  key: string
  icon?: React.ReactNode
  label: string
  children?: MenuItem[]
}

const menuItems: MenuItem[] = [
  {
    key: '/system',
    icon: <SettingOutlined />,
    label: '系统管理',
    children: [
      { key: '/system/admin', label: '用户管理' },
      { key: '/system/group', label: '角色管理' },
      { key: '/system/menu', label: '菜单管理' },
      { key: '/system/tenant', label: '租户管理' },
      { key: '/system/llm', label: 'LLM 配置', icon: <RobotOutlined /> },
      { key: '/system/git', label: 'Git 配置', icon: <GithubOutlined /> },
      { key: '/system/knowledge', label: '知识库', icon: <BookOutlined /> },
    ],
  },
  {
    key: '/pipeline',
    icon: <RocketOutlined />,
    label: '开发流水线',
  },
  {
    key: '/skills/market',
    icon: <ThunderboltOutlined />,
    label: '技能市场',
  },
]

export default function LayoutComponent() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    navigate(key)
  }

  const handleLogout = async () => {
    try {
      await authApi.logout()
    } finally {
      logout()
      navigate('/login')
    }
  }

  const userMenuItems: MenuProps['items'] = [
    { key: 'profile', icon: <UserOutlined />, label: '个人中心' },
    { type: 'divider' },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
  ]

  const handleUserMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key === 'logout') {
      handleLogout()
    }
  }

  // 获取当前选中的菜单
  const selectedKeys = [location.pathname]
  const openKeys = ['/' + location.pathname.split('/')[1]]

  return (
    <AntLayout className="tech-layout">
      {/* 侧边栏 */}
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        className="tech-sider"
        width={240}
        collapsedWidth={80}
      >
        {/* Logo区域 */}
        <div className="tech-logo-area">
          <div className="tech-logo-icon-wrapper">
            <RocketOutlined className="tech-logo-icon" />
          </div>
          {!collapsed && (
            <div className="tech-logo-text">
              <span className="tech-logo-title">ADMIN</span>
              <span className="tech-logo-subtitle">MANAGEMENT</span>
            </div>
          )}
        </div>

        {/* 菜单 */}
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={selectedKeys}
          defaultOpenKeys={openKeys}
          items={menuItems as any}
          onClick={handleMenuClick}
          className="tech-menu"
        />

        {/* 侧边栏底部装饰 */}
        <div className="tech-sider-footer">
          <div className="tech-status-dot"></div>
          {!collapsed && <span className="tech-status-text">系统运行中</span>}
        </div>
      </Sider>

      {/* 主内容区 */}
      <AntLayout className="tech-main">
        {/* 头部 */}
        <Header className="tech-header">
          <div className="tech-header-left">
            <span
              className="tech-collapse-btn"
              onClick={() => setCollapsed(!collapsed)}
            >
              {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            </span>
            <div className="tech-breadcrumb">
              <span className="tech-breadcrumb-item">首页</span>
              <span className="tech-breadcrumb-separator">/</span>
              <span className="tech-breadcrumb-item active">
                {menuItems.find(item => item.key === '/' + location.pathname.split('/')[1])?.label || '仪表盘'}
              </span>
            </div>
          </div>

          <div className="tech-header-right">
            <Dropdown
              menu={{ items: userMenuItems, onClick: handleUserMenuClick }}
              placement="bottomRight"
            >
              <div className="tech-user-dropdown">
                <div className="tech-avatar-wrapper">
                  <Avatar
                    icon={<UserOutlined />}
                    className="tech-avatar"
                  />
                  <div className="tech-avatar-status"></div>
                </div>
                <div className="tech-user-info">
                  <span className="tech-user-name">{user?.realName || user?.username}</span>
                  <span className="tech-user-role">管理员</span>
                </div>
              </div>
            </Dropdown>
          </div>
        </Header>

        {/* 内容区 */}
        <Content className="tech-content">
          <div className="tech-content-inner">
            <Outlet />
          </div>
        </Content>
      </AntLayout>
    </AntLayout>
  )
}
