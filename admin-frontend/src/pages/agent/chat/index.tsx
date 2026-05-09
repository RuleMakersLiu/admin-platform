import React, { useState, useEffect, useRef } from 'react'
import {
  Layout,
  Card,
  Input,
  Button,
  List,
  Avatar,
  Tag,
  Space,
  Typography,
  Select,
  Empty,
  Spin,
  message,
  Tooltip,
  theme,
} from 'antd'
import {
  SendOutlined,
  PlusOutlined,
  DeleteOutlined,
  RobotOutlined,
  UserOutlined,
  MessageOutlined,
  CopyOutlined,
  CheckOutlined,
  ReloadOutlined,
  ClearOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import 'highlight.js/styles/github-dark.css'
import { agentApi, agentTypeNames, agentTypeColors, AgentType } from '@/services/api'

const { Sider, Content } = Layout
const { TextArea } = Input
const { Text } = Typography
const { Option } = Select
const { useToken } = theme

// 分身头像配置
const agentAvatars: Record<AgentType, { emoji: string; bgColor: string }> = {
  PM: { emoji: '📊', bgColor: '#e6f7ff' },
  PJM: { emoji: '📋', bgColor: '#f9f0ff' },
  BE: { emoji: '⚙️', bgColor: '#f6ffed' },
  FE: { emoji: '🎨', bgColor: '#fff0f6' },
  QA: { emoji: '🔍', bgColor: '#fff7e6' },
  RPT: { emoji: '📈', bgColor: '#e6fffb' },
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  agent_type?: AgentType
  timestamp: number
}

interface Session {
  session_id: string
  title: string
  current_agent: string
  workflow_stage: string
  status: string
  message_count: number
  last_message_time: number
  create_time: number
}

// 代码块组件 - 带复制功能
const CodeBlock: React.FC<{ className?: string; children?: React.ReactNode }> = ({ className, children }) => {
  const [copied, setCopied] = useState(false)
  const match = /language-(\w+)/.exec(className || '')
  const language = match ? match[1] : ''

  const handleCopy = async () => {
    const code = String(children).replace(/\n$/, '')
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div style={{ position: 'relative', margin: '8px 0' }}>
      {language && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            padding: '4px 12px',
            background: '#1f2937',
            color: '#9ca3af',
            fontSize: 12,
            borderRadius: '6px 6px 0 0',
            fontFamily: 'monospace',
          }}
        >
          {language}
        </div>
      )}
      <Button
        type="text"
        size="small"
        icon={copied ? <CheckOutlined style={{ color: '#52c41a' }} /> : <CopyOutlined />}
        onClick={handleCopy}
        style={{
          position: 'absolute',
          top: 4,
          right: 4,
          color: '#9ca3af',
          zIndex: 10,
        }}
      />
      <pre
        className={className}
        style={{
          margin: 0,
          padding: language ? '32px 16px 16px' : '16px',
          borderRadius: 6,
          background: '#1f2937',
          overflow: 'auto',
        }}
      >
        <code className={className}>{children}</code>
      </pre>
    </div>
  )
}

// Markdown 渲染组件
const MarkdownContent: React.FC<{ content: string }> = ({ content }) => {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight]}
      components={{
        code: ({ className, children }) => {
          const isInline = !className
          if (isInline) {
            return (
              <code
                style={{
                  background: '#f5f5f5',
                  padding: '2px 6px',
                  borderRadius: 4,
                  fontFamily: 'monospace',
                  fontSize: 13,
                }}
              >
                {children}
              </code>
            )
          }
          return <CodeBlock className={className}>{children}</CodeBlock>
        },
        pre: ({ children }) => <>{children}</>,
        p: ({ children }) => <p style={{ margin: '8px 0' }}>{children}</p>,
        ul: ({ children }) => <ul style={{ paddingLeft: 20, margin: '8px 0' }}>{children}</ul>,
        ol: ({ children }) => <ol style={{ paddingLeft: 20, margin: '8px 0' }}>{children}</ol>,
        li: ({ children }) => <li style={{ margin: '4px 0' }}>{children}</li>,
        h1: ({ children }) => <h1 style={{ fontSize: 20, margin: '16px 0 8px' }}>{children}</h1>,
        h2: ({ children }) => <h2 style={{ fontSize: 18, margin: '14px 0 8px' }}>{children}</h2>,
        h3: ({ children }) => <h3 style={{ fontSize: 16, margin: '12px 0 6px' }}>{children}</h3>,
        blockquote: ({ children }) => (
          <blockquote
            style={{
              borderLeft: '4px solid #1890ff',
              paddingLeft: 16,
              margin: '8px 0',
              color: '#666',
            }}
          >
            {children}
          </blockquote>
        ),
        table: ({ children }) => (
          <div style={{ overflowX: 'auto', margin: '8px 0' }}>
            <table
              style={{
                borderCollapse: 'collapse',
                width: '100%',
                border: '1px solid #e8e8e8',
              }}
            >
              {children}
            </table>
          </div>
        ),
        th: ({ children }) => (
          <th style={{ border: '1px solid #e8e8e8', padding: '8px 12px', background: '#fafafa' }}>
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td style={{ border: '1px solid #e8e8e8', padding: '8px 12px' }}>{children}</td>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  )
}

// 消息气泡组件
const MessageBubble: React.FC<{
  message: Message
  isUser: boolean
}> = ({ message, isUser }) => {
  const { token } = useToken()
  const agentType = message.agent_type as AgentType
  const agentAvatar = agentType ? agentAvatars[agentType] : null
  const agentColor = agentType ? agentTypeColors[agentType] : '#87d068'

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        marginBottom: 16,
      }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: isUser ? 'row-reverse' : 'row',
          alignItems: 'flex-start',
          maxWidth: '85%',
          gap: 12,
        }}
      >
        {/* 头像 */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 4,
          }}
        >
          <Avatar
            size={36}
            icon={isUser ? <UserOutlined /> : <RobotOutlined />}
            style={{
              backgroundColor: isUser ? token.colorPrimary : agentColor,
              boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
            }}
          >
            {!isUser && agentAvatar && (
              <span style={{ fontSize: 18 }}>{agentAvatar.emoji}</span>
            )}
          </Avatar>
        </div>

        {/* 消息内容 */}
        <div
          style={{
            background: isUser ? token.colorPrimaryBg : '#fff',
            borderRadius: 12,
            padding: '12px 16px',
            boxShadow: '0 1px 2px rgba(0,0,0,0.06)',
            border: `1px solid ${isUser ? token.colorPrimaryBorder : '#e8e8e8'}`,
          }}
        >
          {/* 分身标签 */}
          {!isUser && agentType && (
            <Tag
              color={agentColor}
              style={{
                marginBottom: 8,
                borderRadius: 4,
                fontSize: 11,
              }}
            >
              {agentTypeNames[agentType]}
            </Tag>
          )}

          {/* 消息正文 */}
          <div
            style={{
              fontSize: 14,
              lineHeight: 1.6,
              color: '#333',
            }}
          >
            {isUser ? (
              <div style={{ whiteSpace: 'pre-wrap' }}>{message.content}</div>
            ) : (
              <MarkdownContent content={message.content} />
            )}
          </div>

          {/* 时间戳 */}
          <div
            style={{
              fontSize: 11,
              color: '#999',
              marginTop: 8,
              textAlign: isUser ? 'right' : 'left',
            }}
          >
            {new Date(message.timestamp).toLocaleTimeString()}
          </div>
        </div>
      </div>
    </div>
  )
}

const AgentChat: React.FC = () => {
  const [sessions, setSessions] = useState<Session[]>([])
  const [currentSession, setCurrentSession] = useState<Session | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false) // 流式响应中
  const [agentType, setAgentType] = useState<AgentType>('PM')
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const streamingMsgIdRef = useRef<string | null>(null) // 当前流式消息 ID

  // 加载会话列表
  useEffect(() => {
    loadSessions()
  }, [])

  // 滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const loadSessions = async () => {
    setSessionsLoading(true)
    try {
      const data = await agentApi.getSessions() as any
      setSessions(data?.list || [])
    } catch (error) {
      console.error('加载会话失败:', error)
    } finally {
      setSessionsLoading(false)
    }
  }

  const loadSessionHistory = async (sessionId: string) => {
    setLoading(true)
    try {
      const data = await agentApi.getSessionHistory(sessionId) as any
      const history = (data?.messages || []).map((msg: any, index: number) => ({
        id: `msg-${index}`,
        role: msg.role,
        content: msg.content,
        agent_type: msg.agent_type,
        timestamp: Date.now() - index * 1000,
      }))
      setMessages(history.reverse())
    } catch (error) {
      console.error('加载历史消息失败:', error)
      setMessages([])
    } finally {
      setLoading(false)
    }
  }

  const createNewSession = async () => {
    try {
      const session = await agentApi.createSession({ title: '新对话' }) as any
      setSessions([session, ...sessions])
      setCurrentSession(session)
      setMessages([])
      message.success('新对话已创建')
    } catch (error) {
      message.error('创建会话失败')
    }
  }

  const deleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await agentApi.deleteSession(sessionId)
      setSessions(sessions.filter(s => s.session_id !== sessionId))
      if (currentSession?.session_id === sessionId) {
        setCurrentSession(null)
        setMessages([])
      }
      message.success('删除成功')
    } catch (error) {
      message.error('删除失败')
    }
  }

  // 使用流式 API 发送消息
  const sendMessageStream = async () => {
    if (!inputValue.trim() || loading || streaming) return

    const sessionId = currentSession?.session_id || `sess-${Date.now()}`

    // 添加用户消息
    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: inputValue,
      timestamp: Date.now(),
    }
    setMessages(prev => [...prev, userMsg])
    const userInput = inputValue
    setInputValue('')
    setLoading(true)
    setStreaming(true)

    // 创建一个占位的助手消息
    const assistantMsgId = `stream-${Date.now()}`
    streamingMsgIdRef.current = assistantMsgId
    const assistantMsg: Message = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      agent_type: agentType,
      timestamp: Date.now(),
    }
    setMessages(prev => [...prev, assistantMsg])

    try {
      await agentApi.chatStream(
        {
          session_id: sessionId,
          message: userInput,
          agent_type: agentType,
        },
        {
          onStart: () => {
            // 流式开始，可以在这里做一些初始化
          },
          onContent: (content) => {
            // 实时更新消息内容
            setMessages(prev =>
              prev.map(msg =>
                msg.id === assistantMsgId
                  ? { ...msg, content: msg.content + content }
                  : msg
              )
            )
          },
          onComplete: (response) => {
            // 流式完成
            setStreaming(false)
            setLoading(false)

            // 更新消息的 agent_type（如果后端返回了不同的类型）
            if (response?.agent_type) {
              setMessages(prev =>
                prev.map(msg =>
                  msg.id === assistantMsgId
                    ? { ...msg, agent_type: response.agent_type as AgentType }
                    : msg
                )
              )
            }

            // 更新当前会话
            if (!currentSession) {
              const newSession: Session = {
                session_id: sessionId,
                title: userInput.slice(0, 20),
                current_agent: response?.agent_type || agentType,
                workflow_stage: 'requirement',
                status: 'active',
                message_count: 2,
                create_time: Date.now(),
                last_message_time: Date.now(),
              }
              setCurrentSession(newSession)
              setSessions(prev => [newSession, ...prev])
            }

            streamingMsgIdRef.current = null
            inputRef.current?.focus()
          },
          onError: (error) => {
            message.error(`发送消息失败: ${error}`)
            setStreaming(false)
            setLoading(false)
            // 移除失败的占位消息
            setMessages(prev => prev.filter(msg => msg.id !== assistantMsgId))
            streamingMsgIdRef.current = null
          },
        }
      )
    } catch (error) {
      message.error('发送消息失败')
      setStreaming(false)
      setLoading(false)
      // 移除失败的占位消息
      setMessages(prev => prev.filter(msg => msg.id !== assistantMsgId))
      streamingMsgIdRef.current = null
    }
  }

  const sendMessage = async () => {
    // 使用流式 API
    await sendMessageStream()
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const clearMessages = () => {
    setMessages([])
    message.success('对话已清空')
  }

  return (
    <Layout style={{ height: 'calc(100vh - 64px)', background: '#f5f5f5' }}>
      <Sider width={300} theme="light" style={{ borderRight: '1px solid #e8e8e8' }}>
        {/* 新建对话按钮 */}
        <div style={{ padding: '16px', borderBottom: '1px solid #f0f0f0' }}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            block
            onClick={createNewSession}
            style={{ height: 40, borderRadius: 8 }}
          >
            新建对话
          </Button>
        </div>

        {/* 会话列表 */}
        <div style={{ height: 'calc(100% - 72px)', overflow: 'auto' }}>
          <Spin spinning={sessionsLoading}>
            {sessions.length === 0 ? (
              <Empty
                style={{ marginTop: 60 }}
                description="暂无对话"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ) : (
              <List
                dataSource={sessions}
                style={{ padding: '8px' }}
                renderItem={(session) => (
                  <List.Item
                    onClick={() => {
                      setCurrentSession(session)
                      loadSessionHistory(session.session_id)
                    }}
                    style={{
                      cursor: 'pointer',
                      background: currentSession?.session_id === session.session_id ? '#e6f7ff' : 'transparent',
                      borderRadius: 8,
                      padding: '12px',
                      marginBottom: 4,
                      transition: 'all 0.2s',
                    }}
                    actions={[
                      <Tooltip key="delete" title="删除">
                        <Button
                          type="text"
                          size="small"
                          icon={<DeleteOutlined />}
                          danger
                          onClick={(e) => deleteSession(session.session_id, e)}
                        />
                      </Tooltip>,
                    ]}
                  >
                    <List.Item.Meta
                      avatar={
                        <Avatar
                          icon={<MessageOutlined />}
                          style={{
                            backgroundColor: agentTypeColors[session.current_agent as AgentType] || '#1890ff',
                          }}
                        />
                      }
                      title={
                        <Text
                          ellipsis
                          style={{
                            fontSize: 14,
                            fontWeight: currentSession?.session_id === session.session_id ? 600 : 400,
                          }}
                        >
                          {session.title || '未命名对话'}
                        </Text>
                      }
                      description={
                        <Space size={4}>
                          <Tag
                            color={agentTypeColors[session.current_agent as AgentType]}
                            style={{ margin: 0, fontSize: 11 }}
                          >
                            {agentTypeNames[session.current_agent as AgentType] || session.current_agent}
                          </Tag>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {session.message_count}条
                          </Text>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Spin>
        </div>
      </Sider>

      <Content style={{ display: 'flex', flexDirection: 'column' }}>
        {/* 顶部工具栏 */}
        <Card
          size="small"
          style={{ margin: '16px 16px 0', borderRadius: 8 }}
          styles={{ body: { padding: '12px 16px' } }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Space>
              <Text strong>当前分身:</Text>
              <Select value={agentType} onChange={setAgentType} style={{ width: 150 }}>
                {Object.entries(agentTypeNames).map(([key, name]) => (
                  <Option key={key} value={key}>
                    <Space>
                      <span style={{ color: agentTypeColors[key as AgentType] }}>
                        {agentAvatars[key as AgentType].emoji}
                      </span>
                      {name}
                    </Space>
                  </Option>
                ))}
              </Select>
            </Space>
            <Space>
              {messages.length > 0 && (
                <Tooltip title="清空对话">
                  <Button icon={<ClearOutlined />} onClick={clearMessages} />
                </Tooltip>
              )}
              <Tooltip title="刷新会话">
                <Button icon={<ReloadOutlined />} onClick={loadSessions} />
              </Tooltip>
            </Space>
          </div>
        </Card>

        {/* 消息区域 */}
        <div
          style={{
            flex: 1,
            overflow: 'auto',
            padding: '16px',
            background: 'linear-gradient(180deg, #f5f5f5 0%, #fafafa 100%)',
          }}
        >
          {messages.length === 0 ? (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
              }}
            >
              <div style={{ fontSize: 64, marginBottom: 24 }}>
                {agentAvatars[agentType].emoji}
              </div>
              <Text type="secondary" style={{ fontSize: 16, marginBottom: 8 }}>
                开始与 {agentTypeNames[agentType]} 对话
              </Text>
              <Text type="secondary" style={{ fontSize: 13 }}>
                输入您的需求，AI 分身将为您提供专业帮助
              </Text>
            </div>
          ) : (
            <div style={{ maxWidth: 900, margin: '0 auto' }}>
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} isUser={msg.role === 'user'} />
              ))}
              {/* 流式响应时的打字指示器 - 只在等待响应时显示，流式开始后隐藏 */}
              {loading && !streaming && (
                <div style={{ textAlign: 'center', padding: 20 }}>
                  <Spin tip={`${agentTypeNames[agentType]} 思考中...`} />
                </div>
              )}
              {/* 流式响应中的光标动画 */}
              {streaming && (
                <div style={{ textAlign: 'center', padding: 8 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    正在输入中...
                  </Text>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* 输入区域 */}
        <Card
          style={{ margin: '0 16px 16px', borderRadius: 8 }}
          styles={{ body: { padding: '12px 16px' } }}
        >
          <Space.Compact style={{ width: '100%' }}>
            <TextArea
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="输入消息，按 Enter 发送，Shift+Enter 换行"
              autoSize={{ minRows: 2, maxRows: 6 }}
              style={{
                flex: 1,
                borderRadius: '8px 0 0 8px',
                resize: 'none',
              }}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              loading={loading}
              onClick={sendMessage}
              style={{
                height: 'auto',
                borderRadius: '0 8px 8px 0',
                minWidth: 80,
              }}
              disabled={!inputValue.trim()}
            >
              发送
            </Button>
          </Space.Compact>
          <div style={{ marginTop: 8, textAlign: 'right' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              支持 Markdown 格式 | 代码块使用 ```语言 包裹
            </Text>
          </div>
        </Card>
      </Content>
    </Layout>
  )
}

export default AgentChat
