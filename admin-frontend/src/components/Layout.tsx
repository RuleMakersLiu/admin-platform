import { useEffect, useMemo, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Avatar, Dropdown, Layout as AntLayout, Menu } from 'antd'
import {
  AppstoreOutlined,
  BookOutlined,
  BugOutlined,
  CodeOutlined,
  FolderOutlined,
  GithubOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlusCircleOutlined,
  RobotOutlined,
  RocketOutlined,
  SettingOutlined,
  SwapOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import {
  DEVELOPER_PORTAL_PERMISSIONS,
  PIPELINE_PAGE_PERMISSIONS,
  canUseDeveloperPortal,
  canUsePipelineWorkbench,
  canUseProductPortal,
  saveLastPortalPath,
  useAuthStore,
} from '@/stores/auth'
import { authApi } from '@/services/api'
import ProfileModal from '@/components/ProfileModal'
import './Layout.css'

const { Header, Sider, Content } = AntLayout

interface MenuItem {
  key: string
  icon?: React.ReactNode
  label: string
  permission?: string | string[]
  children?: MenuItem[]
}

const menuItems: MenuItem[] = [
  {
    key: '/project',
    icon: <CodeOutlined />,
    label: '项目管理',
    children: [
      { key: '/project/access', label: '项目接入', icon: <ImportIcon />, permission: DEVELOPER_PORTAL_PERMISSIONS },
      { key: '/project/create', label: '项目创建', icon: <PlusCircleOutlined /> },
      { key: '/project/list', label: '项目列表', icon: <FolderOutlined />, permission: 'project:list:list' },
      { key: '/project/test', label: '测试中心', icon: <BugOutlined />, permission: 'project:test:list' },
    ],
  },
  {
    key: '/pipeline',
    icon: <RocketOutlined />,
    label: '开发流水线',
    children: [
      { key: '/pipeline/development', label: '开发流水线', icon: <ThunderboltOutlined />, permission: PIPELINE_PAGE_PERMISSIONS },
    ],
  },
  {
    key: '/system',
    icon: <SettingOutlined />,
    label: '系统管理',
    children: [
      { key: '/system/admin', label: '用户管理', permission: 'system:admin:list' },
      { key: '/system/group', label: '角色管理', permission: 'system:group:list' },
      { key: '/system/menu', label: '菜单管理', permission: 'system:menu:list' },
      { key: '/system/tenant', label: '租户管理', permission: 'system:tenant:list' },
      { key: '/system/llm', label: 'LLM 配置', icon: <RobotOutlined />, permission: 'system:llm:list' },
      { key: '/system/git', label: 'Git 配置', icon: <GithubOutlined />, permission: 'system:git:list' },
      { key: '/system/knowledge', label: '知识库', icon: <BookOutlined />, permission: 'system:knowledge:list' },
    ],
  },
  {
    key: '/skills/market',
    icon: <ThunderboltOutlined />,
    label: '技能市场',
    permission: 'skills:market:list',
  },
]

function ImportIcon() {
  return <AppstoreOutlined />
}

const iconMap: Record<string, React.ReactNode> = {
  setting: <SettingOutlined />,
  user: <UserOutlined />,
  team: <UserOutlined />,
  menu: <SettingOutlined />,
  code: <CodeOutlined />,
  plus: <PlusCircleOutlined />,
  folder: <FolderOutlined />,
  experiment: <BugOutlined />,
  robot: <RobotOutlined />,
  bug: <BugOutlined />,
  rocket: <RocketOutlined />,
  thunderbolt: <ThunderboltOutlined />,
  RobotOutlined: <RobotOutlined />,
  GithubOutlined: <GithubOutlined />,
  BookOutlined: <BookOutlined />,
  CodeOutlined: <CodeOutlined />,
  AppstoreOutlined: <AppstoreOutlined />,
  RocketOutlined: <RocketOutlined />,
  ThunderboltOutlined: <ThunderboltOutlined />,
}

const hiddenServerMenuPaths = new Set(['/portal-select', '/developer', '/product'])

const filterStaticMenus = (items: MenuItem[], hasAnyPermission: (permissions: string[]) => boolean): MenuItem[] => (
  items
    .map((item) => ({
      ...item,
      children: item.children ? filterStaticMenus(item.children, hasAnyPermission) : undefined,
    }))
    .filter((item) => {
      const permissions = Array.isArray(item.permission) ? item.permission : item.permission ? [item.permission] : []
      return item.children?.length || !permissions.length || hasAnyPermission(permissions)
    })
)

const transformServerMenus = (items: any[]): MenuItem[] => (
  (items || [])
    .filter((item) => item.path && !hiddenServerMenuPaths.has(item.path))
    .map((item) => ({
      key: item.path,
      icon: iconMap[item.icon] || <SettingOutlined />,
      label: item.menuName || item.name,
      permission: item.permission,
      children: transformServerMenus(item.children || []),
    }))
    .map((item) => ({
      ...item,
      children: item.children?.length ? item.children : undefined,
    }))
)

const getTopMenuLabel = (items: MenuItem[], pathname: string) => {
  const firstKey = `/${pathname.split('/')[1] || ''}`
  const top = items.find((item) => item.key === firstKey || item.children?.some((child) => child.key === pathname))
  return top?.label || '仪表盘'
}

export default function LayoutComponent() {
  const [collapsed, setCollapsed] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [openMenuKeys, setOpenMenuKeys] = useState<string[]>([])
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout, hasAnyPermission, setUser } = useAuthStore()
  const [serverMenus, setServerMenus] = useState<MenuItem[]>([])

  useEffect(() => {
    let mounted = true
    authApi.getInfo()
      .then((info: any) => {
        if (mounted) {
          setUser({
            adminId: info.adminId,
            username: info.username,
            realName: info.realName || info.username,
            tenantId: info.tenantId,
            groupName: info.groupName,
            isSuper: Boolean(info.isSuper),
            permissions: info.permissions || [],
          })
        }
      })
      .catch(() => undefined)
    authApi.getMenus()
      .then((items: any) => {
        if (mounted) setServerMenus(transformServerMenus(Array.isArray(items) ? items : []))
      })
      .catch(() => {
        if (mounted) setServerMenus([])
      })
    return () => {
      mounted = false
    }
  }, [setUser])

  const visibleMenuItems = useMemo(() => {
    if (serverMenus.length) return serverMenus
    return filterStaticMenus(menuItems, hasAnyPermission)
  }, [serverMenus, hasAnyPermission])

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

  const portalSwitchItems: MenuProps['items'] = [
    canUseDeveloperPortal(user) && { key: 'portal:/project/access', icon: <CodeOutlined />, label: '项目接入' },
    (canUseProductPortal(user) || canUsePipelineWorkbench(user)) && {
      key: 'portal:/pipeline/development',
      icon: <ThunderboltOutlined />,
      label: '开发流水线',
    },
  ].filter(Boolean) as MenuProps['items']

  const userMenuItems: MenuProps['items'] = [
    portalSwitchItems && portalSwitchItems.length > 1
      ? { key: 'portal-group', type: 'group', label: '工作门户', children: portalSwitchItems }
      : null,
    portalSwitchItems && portalSwitchItems.length > 1 ? { type: 'divider' } : null,
    { key: 'profile', icon: <UserOutlined />, label: '个人中心' },
    { type: 'divider' },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
  ].filter(Boolean) as MenuProps['items']

  const handleUserMenuClick: MenuProps['onClick'] = ({ key }) => {
    const value = String(key)
    if (value.startsWith('portal:')) {
      const path = value.replace('portal:', '')
      saveLastPortalPath(user, path)
      navigate(path)
      return
    }
    if (key === 'profile') {
      setProfileOpen(true)
    } else if (key === 'logout') {
      handleLogout()
    }
  }

  const selectedKeys = [location.pathname]
  const activeRootKey = `/${location.pathname.split('/')[1] || ''}`

  useEffect(() => {
    if (!collapsed && activeRootKey !== '/') {
      setOpenMenuKeys((keys) => keys.includes(activeRootKey) ? keys : [...keys, activeRootKey])
    }
  }, [activeRootKey, collapsed])

  return (
    <AntLayout className="tech-layout">
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        className="tech-sider"
        width={240}
        collapsedWidth={80}
      >
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

        <Menu
          theme="light"
          mode="inline"
          selectedKeys={selectedKeys}
          openKeys={collapsed ? [] : openMenuKeys}
          onOpenChange={(keys) => setOpenMenuKeys(keys)}
          items={visibleMenuItems as any}
          onClick={handleMenuClick}
          className="tech-menu"
        />

        <div className="tech-sider-footer">
          <div className="tech-status-dot"></div>
          {!collapsed && <span className="tech-status-text">系统运行中</span>}
        </div>
      </Sider>

      <AntLayout className="tech-main">
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
                {getTopMenuLabel(visibleMenuItems, location.pathname)}
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
                  <span className="tech-user-role">{user?.groupName || '管理员'}</span>
                </div>
                {portalSwitchItems && portalSwitchItems.length > 1 && <SwapOutlined className="tech-portal-switch-icon" />}
              </div>
            </Dropdown>
          </div>
        </Header>

        <Content className="tech-content">
          <div className="tech-content-inner">
            <Outlet />
          </div>
        </Content>
      </AntLayout>

      <ProfileModal open={profileOpen} onClose={() => setProfileOpen(false)} />
    </AntLayout>
  )
}
