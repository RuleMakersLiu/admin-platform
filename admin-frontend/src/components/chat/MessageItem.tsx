import React, { memo } from 'react';
import { Avatar, Typography, Button, Tooltip, Spin, Alert } from 'antd';
import {
  UserOutlined,
  RobotOutlined,
  InfoCircleOutlined,
  CopyOutlined,
  CheckOutlined,
  ReloadOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import type { Message } from '@/types/chat';
import MarkdownRenderer from '@/utils/markdown';
import { useClipboard } from '@/hooks/useChat';
import dayjs from 'dayjs';
import './MessageItem.css';

const { Text, Paragraph } = Typography;

// 消息项组件 Props
interface MessageItemProps {
  message: Message;
  onRetry?: (messageId: string) => void;
  onDelete?: (messageId: string) => void;
}

// 用户消息组件
const UserMessage: React.FC<{
  message: Message;
  onDelete?: (messageId: string) => void;
}> = memo(({ message, onDelete }) => {
  const { copy, copied } = useClipboard();

  return (
    <div className="message-item user-message">
      <div className="message-avatar">
        <Avatar icon={<UserOutlined />} className="user-avatar" />
      </div>
      <div className="message-content">
        <div className="message-header">
          <Text strong>你</Text>
          <Text type="secondary" className="message-time">
            {dayjs(message.createdAt).format('HH:mm')}
          </Text>
        </div>
        <div className="message-body">
          <Paragraph className="message-text">{message.content}</Paragraph>
        </div>
        <div className="message-actions">
          <Tooltip title={copied ? '已复制' : '复制'}>
            <Button
              type="text"
              size="small"
              icon={copied ? <CheckOutlined /> : <CopyOutlined />}
              onClick={() => copy(message.content)}
            />
          </Tooltip>
          {onDelete && (
            <Tooltip title="删除">
              <Button
                type="text"
                size="small"
                icon={<DeleteOutlined />}
                onClick={() => onDelete(message.id)}
              />
            </Tooltip>
          )}
        </div>
      </div>
    </div>
  );
});

UserMessage.displayName = 'UserMessage';

// AI 消息组件
const AIMessage: React.FC<{
  message: Message;
  onRetry?: (messageId: string) => void;
  onDelete?: (messageId: string) => void;
}> = memo(({ message, onRetry, onDelete }) => {
  const { copy, copied } = useClipboard();
  const isStreaming = message.status === 'streaming';
  const isError = message.status === 'error';

  return (
    <div className="message-item ai-message">
      <div className="message-avatar">
        <Avatar icon={<RobotOutlined />} className="ai-avatar" />
      </div>
      <div className="message-content">
        <div className="message-header">
          <Text strong>AI 助手</Text>
          {message.metadata?.model && (
            <Text type="secondary" className="message-model">
              {message.metadata.model}
            </Text>
          )}
          <Text type="secondary" className="message-time">
            {dayjs(message.createdAt).format('HH:mm')}
          </Text>
        </div>

        <div className="message-body">
          {isError ? (
            <Alert
              message="出错了"
              description={message.error || '生成回复时发生错误'}
              type="error"
              showIcon
            />
          ) : (
            <MarkdownRenderer content={message.content} />
          )}

          {isStreaming && (
            <div className="streaming-indicator">
              <Spin size="small" />
              <Text type="secondary">正在生成...</Text>
            </div>
          )}
        </div>

        {!isStreaming && (
          <div className="message-actions">
            <Tooltip title={copied ? '已复制' : '复制'}>
              <Button
                type="text"
                size="small"
                icon={copied ? <CheckOutlined /> : <CopyOutlined />}
                onClick={() => copy(message.content)}
              />
            </Tooltip>
            {isError && onRetry && (
              <Tooltip title="重试">
                <Button
                  type="text"
                  size="small"
                  icon={<ReloadOutlined />}
                  onClick={() => onRetry(message.id)}
                />
              </Tooltip>
            )}
            {onDelete && (
              <Tooltip title="删除">
                <Button
                  type="text"
                  size="small"
                  icon={<DeleteOutlined />}
                  onClick={() => onDelete(message.id)}
                />
              </Tooltip>
            )}
          </div>
        )}
      </div>
    </div>
  );
});

AIMessage.displayName = 'AIMessage';

// 系统消息组件
const SystemMessage: React.FC<{ message: Message }> = memo(({ message }) => (
  <div className="message-item system-message">
    <div className="system-message-content">
      <InfoCircleOutlined className="system-icon" />
      <Text type="secondary">{message.content}</Text>
    </div>
  </div>
));

SystemMessage.displayName = 'SystemMessage';

// 消息项组件
const MessageItem: React.FC<MessageItemProps> = ({
  message,
  onRetry,
  onDelete,
}) => {
  switch (message.type) {
    case 'user':
      return <UserMessage message={message} onDelete={onDelete} />;
    case 'assistant':
      return <AIMessage message={message} onRetry={onRetry} onDelete={onDelete} />;
    case 'system':
      return <SystemMessage message={message} />;
    default:
      return null;
  }
};

export default memo(MessageItem);
