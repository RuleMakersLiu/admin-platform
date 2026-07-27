import React, { useEffect, useCallback, useState, useMemo } from 'react';
import { Layout, Badge, Tooltip, Button, Typography, Space, message, Segmented, Drawer } from 'antd';
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SettingOutlined,
  BulbOutlined,
  BulbFilled,
  MessageOutlined,
  AppstoreOutlined,
  SplitCellsOutlined,
} from '@ant-design/icons';
import { SessionList, MessageList, ChatInput, CanvasPanel } from '@/components/chat';
import { useChatStore } from '@/stores/chat';
import { useChatStream } from '@/hooks/useChatStream';
import { useThemeSwitch, useResponsive, useId } from '@/hooks/useChat';
import type { Attachment, Session } from '@/types/chat';
import { extractHtmlBlocks } from '@/utils/sanitize';
import './index.css';

const { Sider, Content, Header } = Layout;
const { Title } = Typography;

// WebChat 页面 —— 走 Python SSE 后端 /api/chat/stream（多模态：图片/文档/语音 均在此链路）
const WebChatPage: React.FC = () => {
  // Store
  const {
    sessions,
    currentSessionId,
    settings,
    sidebarCollapsed,
    addSession,
    updateSession,
    deleteSession,
    setCurrentSession,
    getCurrentMessages,
    setSidebarCollapsed,
  } = useChatStore();

  // Hooks
  const { theme, toggleTheme } = useThemeSwitch();
  const { isMobile } = useResponsive();
  const { sendMessage, cancel, isStreaming } = useChatStream({
    onError: (err) => message.error(err || '生成回复失败'),
  });
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

  // 没有会话时自动创建一个，避免用户面对空状态无法输入
  useEffect(() => {
    if (sessions.length === 0) {
      const newSession: Session = {
        id: generateUniqueId(),
        title: `新对话 ${sessions.length + 1}`,
        createdAt: Date.now(),
        updatedAt: Date.now(),
        messageCount: 0,
      };
      addSession(newSession);
      setCurrentSession(newSession.id);
    } else if (!currentSessionId) {
      setCurrentSession(sessions[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 会话是否就绪（SSE 无需维持长连接，选了会话即可对话）
  const chatReady = !!currentSessionId;

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
    setCurrentSession(newSession.id);
    if (isMobile) {
      setMobileDrawerVisible(false);
    }
  }, [sessions.length, addSession, setCurrentSession, isMobile, generateUniqueId]);

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

  // 重命名会话（仅本地，SSE 后端按 session_id 维持上下文）
  const handleRenameSession = useCallback(
    (sessionId: string, title: string) => {
      updateSession(sessionId, { title, updatedAt: Date.now() });
    },
    [updateSession]
  );

  // 删除会话
  const handleDeleteSession = useCallback(
    (sessionId: string) => {
      deleteSession(sessionId);
    },
    [deleteSession]
  );

  // 发送消息（走 SSE /api/chat/stream，附件随消息一同发送）
  const handleSendMessage = useCallback(
    (content: string, attachments?: Attachment[]) => {
      if (!currentSessionId || (!content.trim() && !(attachments && attachments.length))) return;

      sendMessage(content, attachments);

      // 更新会话摘要
      updateSession(currentSessionId, {
        updatedAt: Date.now(),
        messageCount: currentMessages.length + 1,
        lastMessage: content.slice(0, 50) || (attachments?.length ? `[附件×${attachments.length}]` : ''),
      });
    },
    [currentSessionId, currentMessages.length, sendMessage, updateSession]
  );

  // 重试消息
  const handleRetry = useCallback(
    (messageId: string) => {
      const msg = currentMessages.find((m) => m.id === messageId);
      if (msg && msg.type === 'user') {
        sendMessage(msg.content, msg.attachments);
      }
    },
    [currentMessages, sendMessage]
  );

  // 清空当前会话消息
  const handleClearMessages = useCallback(() => {
    if (currentSessionId) {
      message.success('对话已清空');
    }
  }, [currentSessionId]);

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

              {/* 就绪状态 */}
              <Tooltip title={chatReady ? '已就绪：可发送消息（含附件）' : '未选择会话'}>
                <Badge status={chatReady ? 'success' : 'default'} text={isMobile ? '' : chatReady ? '就绪' : '待选会话'} />
              </Tooltip>

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
            onCancel={cancel}
            onClear={handleClearMessages}
            disabled={!chatReady}
            isStreaming={isStreaming}
            settings={settings}
          />
        </div>
      </Layout>
    </Layout>
  );
};

export default WebChatPage;
