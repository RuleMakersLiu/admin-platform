import { Component } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'
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

// Error Boundary
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

// 路由守卫
function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { token } = useAuthStore()
  return token ? <>{children}</> : <Navigate to="/login" replace />
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
          {/* 系统管理 */}
          <Route path="system">
            <Route path="admin" element={<AdminList />} />
            <Route path="group" element={<GroupList />} />
            <Route path="menu" element={<MenuList />} />
            <Route path="tenant" element={<TenantList />} />
            <Route path="llm" element={<LLMConfig />} />
            <Route path="git" element={<GitConfig />} />
            <Route path="knowledge" element={<KnowledgeList />} />
          </Route>
          {/* 智能分身 */}
          <Route path="agent">
            <Route path="chat" element={<AgentChat />} />
            <Route path="project" element={<AgentProject />} />
            <Route path="bug" element={<AgentBug />} />
          </Route>
          {/* WebChat */}
          <Route path="webchat" element={<WebChatPage />} />
          {/* 看板 */}
          <Route path="kanban" element={<KanbanPage />} />
          {/* 开发流水线 */}
          <Route path="pipeline" element={<PipelinePage />} />
          {/* 技能市场 */}
          <Route path="skills">
            <Route path="market" element={<SkillMarketPage />} />
          </Route>
          <Route path="" element={<Navigate to="/system/admin" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
    </ErrorBoundary>
  )
}

export default App
