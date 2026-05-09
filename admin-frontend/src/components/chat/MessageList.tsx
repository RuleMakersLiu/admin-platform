import React, { memo, useEffect, useRef } from 'react';
import { Spin, Alert } from 'antd';
import { RobotOutlined } from '@ant-design/icons';
import type { Message } from '@/types/chat';
import MessageItem from './MessageItem';
import { useScrollToBottom } from '@/hooks/useChat';
import './MessageList.css';

// 消息列表 Props
interface MessageListProps {
  messages: Message[];
  isLoading?: boolean;
  error?: string;
  onRetry?: (messageId: string) => void;
  onDeleteMessage?: (messageId: string) => void;
  hasMore?: boolean;
  onLoadMore?: () => void;
}

// 消息列表组件
const MessageList: React.FC<MessageListProps> = ({
  messages,
  isLoading = false,
  error,
  onRetry,
  onDeleteMessage,
  hasMore = false,
  onLoadMore,
}) => {
  const { containerRef, scrollToBottom } = useScrollToBottom([messages]);
  const loadingRef = useRef(false);

  // 滚动到底部
  useEffect(() => {
    if (messages.length > 0) {
      const lastMessage = messages[messages.length - 1];
      // 新消息或流式输出时自动滚动
      if (lastMessage.status === 'streaming' || lastMessage.status === 'pending') {
        scrollToBottom(false);
      }
    }
  }, [messages, scrollToBottom]);

  // 滚动加载更多
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop } = e.currentTarget;

    // 滚动到顶部时加载更多
    if (scrollTop < 50 && hasMore && !loadingRef.current && onLoadMore) {
      loadingRef.current = true;
      onLoadMore();
      setTimeout(() => {
        loadingRef.current = false;
      }, 1000);
    }
  };

  // 空状态
  if (!isLoading && messages.length === 0) {
    return (
      <div className="message-list-empty">
        <RobotOutlined className="empty-icon" />
        <h3>开始对话</h3>
        <p>输入消息开始与 AI 助手对话</p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="message-list"
      onScroll={handleScroll}
    >
      {/* 加载更多指示器 */}
      {hasMore && (
        <div className="load-more-indicator">
          <Spin size="small" />
          <span>加载更多...</span>
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <Alert
          message="加载失败"
          description={error}
          type="error"
          showIcon
          closable
          className="message-list-error"
        />
      )}

      {/* 消息列表 */}
      {messages.map((message) => (
        <MessageItem
          key={message.id}
          message={message}
          onRetry={onRetry}
          onDelete={onDeleteMessage}
        />
      ))}

      {/* 加载中 */}
      {isLoading && (
        <div className="message-list-loading">
          <Spin />
        </div>
      )}
    </div>
  );
};

export default memo(MessageList);
