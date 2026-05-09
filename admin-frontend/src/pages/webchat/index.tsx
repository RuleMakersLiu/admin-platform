import React, { useEffect, useCallback, useState, useMemo } from 'react';
import { Layout, Badge, Tooltip, Button, Drawer, Typography, Space, message, Segmented } from 'antd';
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SettingOutlined,
  BulbOutlined,
  BulbFilled,
  ReloadOutlined,
  MessageOutlined,
  AppstoreOutlined,
  SplitCellsOutlined,
} from '@ant-design/icons';
import { SessionList, MessageList, ChatInput, CanvasPanel } from '@/components/chat';
import { useChatStore } from '@/stores/chat';
import { useWebSocket } from '@/services/websocket';
import { useThemeSwitch, useResponsive, useId } from '@/hooks/useChat';
import type { Message, Session } from '@/types/chat';
import { extractHtmlBlocks } from '@/utils/sanitize';
import './index.css';

const { Sider, Content, Header } = Layout;
const { Title } = Typography;

// WebChat 页面
const WebChatPage: React.FC = () => {
  // Store
  const {
    sessions,
    currentSessionId,
    connectionStatus,
    settings,
    sidebarCollapsed,
    addSession,
    updateSession,
    deleteSession,
    setCurrentSession,
    addMessage,
    updateMessage,
    appendMessageContent,
    getCurrentMessages,
    setConnectionStatus,
    setSidebarCollapsed,
  } = useChatStore();

  // Hooks
  const { theme, toggleTheme } = useThemeSwitch();
  const { isMobile } = useResponsive();
  const { isConnected, connect, wsManager } = useWebSocket();
  const generateUniqueId = useId();

  // 本地状态
  const [mobileDrawerVisible, setMobileDrawerVisible] = useState(false);
  const [layoutMode, setLayoutMode] = useState<'chat' | 'canvas' | 'split'>('chat');
  const [canvasFullscreen, setCanvasFullscreen] = useState(false);
  const currentMessages = getCurrentMessages();

  // 获取最新的 AI 消息用于 Canvas 预览
  const latestAiMessage = useMemo(() => {
    const aiMessages = currentMessages.filter((msg) => msg.type === 'assistant');
    return aiMessages.length > 0 ? aiMessages[aiMessages.length - 1] : null;
  }, [currentMessages]);

  // 检查最新消息是否包含可渲染的 HTML
  const hasHtmlContent = useMemo(() => {
    if (!latestAiMessage?.content) return false;
    const blocks = extractHtmlBlocks(latestAiMessage.content);
    return blocks.length > 0;
  }, [latestAiMessage]);

  // 连接状态指示器颜色
  const getStatusColor = () => {
    switch (connectionStatus) {
      case 'connected':
        return 'green';
      case 'connecting':
        return 'orange';
      case 'error':
        return 'red';
      default:
        return 'default';
    }
  };

  // 初始化 WebSocket 连接
  useEffect(() => {
    connect({
      onOpen: () => {
        setConnectionStatus('connected');
        message.success('WebSocket 已连接');
      },
      onClose: () => {
        setConnectionStatus('disconnected');
      },
      onError: () => {
        setConnectionStatus('error');
      },
      onMessage: (msg) => {
        console.log('收到消息:', msg);
      },
      onStream: (event) => {
        handleStreamEvent(event);
      },
    });
  }, []);

  // 处理流式事件
  const handleStreamEvent = useCallback(
    (event: any) => {
      switch (event.type) {
        case 'start':
          // 创建 AI 回复消息
          const aiMessageId = generateUniqueId();
          addMessage({
            id: aiMessageId,
            sessionId: currentSessionId!,
            type: 'assistant',
            content: '',
            status: 'streaming',
            createdAt: Date.now(),
          });
          break;

        case 'content':
          // 追加内容
          if (event.messageId) {
            appendMessageContent(event.messageId, event.content || '');
          }
          break;

        case 'complete':
          // 完成消息
          if (event.messageId) {
            updateMessage(event.messageId, { status: 'completed' });
          }
          break;

        case 'error':
          // 错误处理
          if (event.messageId) {
            updateMessage(event.messageId, {
              status: 'error',
              error: event.error,
            });
          }
          message.error(event.error || '生成回复失败');
          break;
      }
    },
    [currentSessionId, addMessage, appendMessageContent, updateMessage, generateUniqueId]
  );

  // 创建新会话
  const handleCreateSession = useCallback(() => {
    const newSession: Session = {
      id: generateUniqueId(),
      title: `新对话 ${sessions.length + 1}`,
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messageCount: 0,
    };

    addSession(newSession);

    // 发送 WebSocket 创建会话
    wsManager.createSession(newSession.title);

    if (isMobile) {
      setMobileDrawerVisible(false);
    }
  }, [sessions.length, addSession, wsManager, isMobile, generateUniqueId]);

  // 选择会话
  const handleSelectSession = useCallback(
    (sessionId: string) => {
      setCurrentSession(sessionId);
      if (isMobile) {
        setMobileDrawerVisible(false);
      }
    },
    [setCurrentSession, isMobile]
  );

  // 重命名会话
  const handleRenameSession = useCallback(
    (sessionId: string, title: string) => {
      updateSession(sessionId, { title, updatedAt: Date.now() });
      wsManager.renameSession(sessionId, title);
    },
    [updateSession, wsManager]
  );

  // 删除会话
  const handleDeleteSession = useCallback(
    (sessionId: string) => {
      deleteSession(sessionId);
      wsManager.deleteSession(sessionId);
    },
    [deleteSession, wsManager]
  );

  // 发送消息
  const handleSendMessage = useCallback(
    (content: string) => {
      if (!currentSessionId || !content.trim()) return;

      // 创建用户消息
      const userMessage: Message = {
        id: generateUniqueId(),
        sessionId: currentSessionId,
        type: 'user',
        content: content.trim(),
        status: 'completed',
        createdAt: Date.now(),
      };

      addMessage(userMessage);

      // 更新会话
      updateSession(currentSessionId, {
        updatedAt: Date.now(),
        messageCount: currentMessages.length + 1,
        lastMessage: content.slice(0, 50),
      });

      // 发送到 WebSocket
      if (settings.streamEnabled) {
        // 流式发送
        wsManager.sendChatMessage(currentSessionId, content, true);
      } else {
        // 非流式发送
        wsManager.sendChatMessage(currentSessionId, content, false);
      }
    },
    [
      currentSessionId,
      currentMessages.length,
      settings.streamEnabled,
      addMessage,
      updateSession,
      wsManager,
      generateUniqueId,
    ]
  );

  // 重试消息
  const handleRetry = useCallback(
    (messageId: string) => {
      const msg = currentMessages.find((m) => m.id === messageId);
      if (msg && msg.type === 'user') {
        handleSendMessage(msg.content);
      }
    },
    [currentMessages, handleSendMessage]
  );

  // 清空当前会话消息
  const handleClearMessages = useCallback(() => {
    if (currentSessionId) {
      // 这里可以调用清空消息的 API
      message.success('对话已清空');
    }
  }, [currentSessionId]);

  // 重新连接
  const handleReconnect = useCallback(() => {
    if (!isConnected) {
      connect({
        onOpen: () => {
          setConnectionStatus('connected');
          message.success('重新连接成功');
        },
      });
    }
  }, [isConnected, connect, setConnectionStatus]);

  // 侧边栏切换
  const toggleSidebar = () => {
    setSidebarCollapsed(!sidebarCollapsed);
  };

  // 移动端抽屉
  const toggleMobileDrawer = () => {
    setMobileDrawerVisible(!mobileDrawerVisible);
  };

  // 切换布局模式
  const handleLayoutModeChange = useCallback((mode: 'chat' | 'canvas' | 'split') => {
    setLayoutMode(mode);
  }, []);

  // Canvas 全屏切换
  const handleCanvasFullscreenChange = useCallback((fullscreen: boolean) => {
    setCanvasFullscreen(fullscreen);
  }, []);

  // 会话列表内容
  const sessionListContent = (
    <SessionList
      sessions={sessions}
      currentSessionId={currentSessionId}
      isLoading={false}
      onCreateSession={handleCreateSession}
      onSelectSession={handleSelectSession}
      onRenameSession={handleRenameSession}
      onDeleteSession={handleDeleteSession}
    />
  );

  return (
    <Layout className={`webchat-layout ${theme}`}>
      {/* 桌面端侧边栏 */}
      {!isMobile && (
        <Sider
          width={280}
          collapsible
          collapsed={sidebarCollapsed}
          onCollapse={setSidebarCollapsed}
          breakpoint="lg"
          className="webchat-sider"
          theme={theme === 'dark' ? 'dark' : 'light'}
        >
          {sessionListContent}
        </Sider>
      )}

      {/* 移动端抽屉 */}
      {isMobile && (
        <Drawer
          title="会话列表"
          placement="left"
          onClose={() => setMobileDrawerVisible(false)}
          open={mobileDrawerVisible}
          width={280}
          className="webchat-drawer"
        >
          {sessionListContent}
        </Drawer>
      )}

      {/* 主内容区 */}
      <Layout className="webchat-main">
        {/* 头部 */}
        <Header className="webchat-header">
          <div className="header-left">
            {isMobile && (
              <Button
                type="text"
                icon={<MenuUnfoldOutlined />}
                onClick={toggleMobileDrawer}
              />
            )}
            {!isMobile && (
              <Button
                type="text"
                icon={sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={toggleSidebar}
              />
            )}
            <Title level={4} className="header-title">
              {sessions.find((s) => s.id === currentSessionId)?.title || 'WebChat'}
            </Title>
          </div>

          <div className="header-right">
            <Space>
              {/* 布局模式切换 */}
              {hasHtmlContent && (
                <Segmented
                  value={layoutMode}
                  onChange={(value) => handleLayoutModeChange(value as 'chat' | 'canvas' | 'split')}
                  options={[
                    {
                      value: 'chat',
                      icon: <MessageOutlined />,
                      label: isMobile ? '' : '对话',
                    },
                    {
                      value: 'canvas',
                      icon: <AppstoreOutlined />,
                      label: isMobile ? '' : 'Canvas',
                    },
                    {
                      value: 'split',
                      icon: <SplitCellsOutlined />,
                      label: isMobile ? '' : '分屏',
                    },
                  ]}
                  size="small"
                />
              )}

              {/* 连接状态 */}
              <Tooltip title={`连接状态: ${connectionStatus}`}>
                <Badge
                  status={getStatusColor() as any}
                  text={isMobile ? '' : connectionStatus}
                />
              </Tooltip>

              {/* 重连按钮 */}
              {!isConnected && (
                <Tooltip title="重新连接">
                  <Button
                    type="text"
                    icon={<ReloadOutlined />}
                    onClick={handleReconnect}
                  />
                </Tooltip>
              )}

              {/* 主题切换 */}
              <Tooltip title={theme === 'dark' ? '切换亮色模式' : '切换暗色模式'}>
                <Button
                  type="text"
                  icon={theme === 'dark' ? <BulbFilled /> : <BulbOutlined />}
                  onClick={toggleTheme}
                />
              </Tooltip>

              {/* 设置 */}
              <Tooltip title="设置">
                <Button type="text" icon={<SettingOutlined />} />
              </Tooltip>
            </Space>
          </div>
        </Header>

        {/* 消息列表 / Canvas 区域 */}
        <Content className="webchat-content">
          {layoutMode === 'chat' && (
            <MessageList
              messages={currentMessages}
              isLoading={false}
              onRetry={handleRetry}
            />
          )}

          {layoutMode === 'canvas' && latestAiMessage && (
            <div className="webchat-canvas-container">
              <CanvasPanel
                content={latestAiMessage.content}
                contentType="markdown"
                showToolbar={true}
                showDeviceSwitcher={true}
                fullscreen={canvasFullscreen}
                onFullscreenChange={handleCanvasFullscreenChange}
                darkMode={theme === 'dark'}
                title="AI 生成内容预览"
              />
            </div>
          )}

          {layoutMode === 'split' && (
            <div className="webchat-split-container">
              <div className="webchat-split-chat">
                <MessageList
                  messages={currentMessages}
                  isLoading={false}
                  onRetry={handleRetry}
                />
              </div>
              <div className="webchat-split-canvas">
                {latestAiMessage ? (
                  <CanvasPanel
                    content={latestAiMessage.content}
                    contentType="markdown"
                    showToolbar={true}
                    showDeviceSwitcher={true}
                    fullscreen={canvasFullscreen}
                    onFullscreenChange={handleCanvasFullscreenChange}
                    darkMode={theme === 'dark'}
                    title="Canvas 预览"
                  />
                ) : (
                  <div className="webchat-canvas-empty">
                    <Typography.Text type="secondary">
                      暂无可预览的内容
                    </Typography.Text>
                  </div>
                )}
              </div>
            </div>
          )}
        </Content>

        {/* 输入区域 */}
        <div className="webchat-input-area">
          <ChatInput
            onSend={handleSendMessage}
            onClear={handleClearMessages}
            disabled={!isConnected || !currentSessionId}
            settings={settings}
          />
        </div>
      </Layout>
    </Layout>
  );
};

export default WebChatPage;
