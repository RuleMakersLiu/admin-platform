import { Component } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Result, Spin } from 'antd'
import {
  DEVELOPER_PORTAL_PERMISSIONS,
  PIPELINE_WORKBENCH_PERMISSIONS,
  PRODUCT_PORTAL_PERMISSIONS,
  canUsePipelineWorkbench,
  canUseProductPortal,
  resolveLandingPath,
  useAuthStore,
} from '@/stores/auth'
import Layout from '@/components/Layout'
import Login from '@/pages/login'
import AdminList from '@/pages/system/admin'
import GroupList from '@/pages/system/group'
import MenuList from '@/pages/system/menu'
import TenantList from '@/pages/system/tenant'
import AgentChat from '@/pages/agent/chat'
import AgentProject from '@/pages/agent/project'
import AgentBug from '@/pages/agent/bug'
import LLMConfig from '@/pages/system/llm'
import GitConfig from '@/pages/system/git'
import KnowledgeList from '@/pages/system/knowledge'
import WebChatPage from '@/pages/webchat'
import SkillMarketPage from '@/pages/skills/market'
import KanbanPage from '@/pages/kanban'
import PipelinePage from '@/pages/pipeline'
import ProjectCreate from '@/pages/project/create'
import ProjectList from '@/pages/project/list'
import ProjectTest from '@/pages/project/test'
import PortalSelect from '@/pages/portal/select'
import DeveloperPortal from '@/pages/portal/developer'
import ProductPortal from '@/pages/portal/product'

class ErrorBoundary extends Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, color: '#ff4d4f', background: '#1a1a2e', minHeight: '100vh' }}>
          <h2>页面渲染错误</h2>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, background: '#111', padding: 16, borderRadius: 8, color: '#ff7875' }}>
            {this.state.error.message}
            {'\n'}
            {this.state.error.stack}
          </pre>
          <button onClick={() => this.setState({ error: null })} style={{ marginTop: 16, padding: '8px 24px', cursor: 'pointer' }}>
            重试
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function LoadingGate() {
  return (
    <div style={{ minHeight: 240, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Spin />
    </div>
  )
}

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { token } = useAuthStore()
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

function PermissionRoute({ permissions, children }: { permissions: string | string[]; children: React.ReactNode }) {
  const { user, hasAnyPermission } = useAuthStore()
  if (!user) return <LoadingGate />

  const required = Array.isArray(permissions) ? permissions : [permissions]
  if (!hasAnyPermission(required)) {
    return <Result status="403" title="无权限访问" subTitle="当前角色没有该页面权限，请联系管理员分配权限。" />
  }
  return <>{children}</>
}

const withPermission = (permissions: string | string[], element: React.ReactNode) => (
  <PermissionRoute permissions={permissions}>{element}</PermissionRoute>
)

function IndexRedirect() {
  const { user } = useAuthStore()
  if (!user) return <LoadingGate />
  return <Navigate to={resolveLandingPath(user)} replace />
}

function RedirectWithSearch({ to }: { to: string }) {
  const location = useLocation()
  return <Navigate to={`${to}${location.search}${location.hash}`} replace />
}

function PipelineRedirect() {
  const location = useLocation()
  const { user } = useAuthStore()
  if (!user) return <LoadingGate />

  const params = new URLSearchParams(location.search)
  const target = params.has('id')
    ? '/pipeline/development'
    : canUseProductPortal(user)
      ? '/pipeline/requirement'
      : canUsePipelineWorkbench(user)
        ? '/pipeline/development'
        : resolveLandingPath(user)

  return <Navigate to={`${target}${location.search}${location.hash}`} replace />
}

function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <PrivateRoute>
                <Layout />
              </PrivateRoute>
            }
          >
            <Route path="system">
              <Route path="admin" element={withPermission('system:admin:list', <AdminList />)} />
              <Route path="group" element={withPermission('system:group:list', <GroupList />)} />
              <Route path="menu" element={withPermission('system:menu:list', <MenuList />)} />
              <Route path="tenant" element={withPermission('system:tenant:list', <TenantList />)} />
              <Route path="llm" element={withPermission('system:llm:list', <LLMConfig />)} />
              <Route path="git" element={withPermission('system:git:list', <GitConfig />)} />
              <Route path="knowledge" element={withPermission('system:knowledge:list', <KnowledgeList />)} />
            </Route>

            <Route path="agent">
              <Route path="chat" element={<AgentChat />} />
              <Route path="project" element={<AgentProject />} />
              <Route path="bug" element={<AgentBug />} />
            </Route>

            <Route path="project">
              <Route path="access" element={withPermission(DEVELOPER_PORTAL_PERMISSIONS, <DeveloperPortal />)} />
              <Route path="create" element={<ProjectCreate />} />
              <Route path="list" element={<ProjectList />} />
              <Route path="test" element={<ProjectTest />} />
            </Route>

            <Route path="portal-select" element={<PortalSelect />} />
            <Route path="developer" element={<RedirectWithSearch to="/project/access" />} />
            <Route path="product" element={<RedirectWithSearch to="/pipeline/requirement" />} />

            <Route path="webchat" element={<WebChatPage />} />
            <Route path="kanban" element={<KanbanPage />} />

            <Route path="pipeline">
              <Route index element={<PipelineRedirect />} />
              <Route path="requirement" element={withPermission(PRODUCT_PORTAL_PERMISSIONS, <ProductPortal />)} />
              <Route path="development" element={withPermission(PIPELINE_WORKBENCH_PERMISSIONS, <PipelinePage />)} />
              <Route path="advanced" element={<RedirectWithSearch to="/pipeline/development" />} />
            </Route>

            <Route path="skills">
              <Route path="market" element={withPermission('skills:market:list', <SkillMarketPage />)} />
            </Route>

            <Route path="" element={<IndexRedirect />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  )
}

export default App
