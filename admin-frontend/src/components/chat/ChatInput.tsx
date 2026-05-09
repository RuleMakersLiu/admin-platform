import React, { memo, useState, useRef, useCallback, useEffect } from 'react';
import { Input, Button, Tooltip, Dropdown, Space, Typography } from 'antd';
import {
  SendOutlined,
  SettingOutlined,
  ClearOutlined,
  AudioOutlined,
  BulbOutlined,
  StopOutlined,
} from '@ant-design/icons';
import type { ChatSettings } from '@/types/chat';
import { useKeyboardShortcut } from '@/hooks/useChat';
import './ChatInput.css';

const { TextArea } = Input;
const { Text } = Typography;

// 聊天输入组件 Props
interface ChatInputProps {
  onSend: (message: string) => void;
  onCancel?: () => void;
  onClear?: () => void;
  disabled?: boolean;
  isStreaming?: boolean;
  placeholder?: string;
  maxLength?: number;
  settings?: ChatSettings;
  onSettingsChange?: (settings: ChatSettings) => void;
}

// 快捷建议
const QUICK_SUGGESTIONS = [
  { key: 'explain', label: '解释这段代码', prompt: '请解释以下代码的功能和逻辑：\n' },
  { key: 'optimize', label: '优化性能', prompt: '请优化以下代码的性能：\n' },
  { key: 'refactor', label: '重构代码', prompt: '请重构以下代码，提高可读性和可维护性：\n' },
  { key: 'test', label: '编写测试', prompt: '请为以下代码编写单元测试：\n' },
  { key: 'document', label: '添加注释', prompt: '请为以下代码添加详细注释：\n' },
];

const ChatInput: React.FC<ChatInputProps> = memo(({
  onSend,
  onCancel,
  onClear,
  disabled = false,
  isStreaming = false,
  placeholder = '输入消息，按 Enter 发送，Shift + Enter 换行',
  maxLength = 4000,
  settings,
  onSettingsChange,
}) => {
  const [message, setMessage] = useState('');
  const [isComposing, setIsComposing] = useState(false);
  const textAreaRef = useRef<HTMLTextAreaElement>(null);

  // 发送消息
  const handleSend = useCallback(() => {
    const trimmedMessage = message.trim();
    if (trimmedMessage && !disabled) {
      onSend(trimmedMessage);
      setMessage('');
      textAreaRef.current?.focus();
    }
  }, [message, disabled, onSend]);

  // 键盘快捷键 - Enter 发送
  useKeyboardShortcut('Enter', handleSend, { ctrl: false, shift: false });

  // 处理按键
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  // 输入法组合开始
  const handleCompositionStart = () => {
    setIsComposing(true);
  };

  // 输入法组合结束
  const handleCompositionEnd = () => {
    setIsComposing(false);
  };

  // 快捷建议点击
  const handleSuggestionClick = useCallback((prompt: string) => {
    setMessage(prompt);
    textAreaRef.current?.focus();
  }, []);

  // 设置菜单
  const settingsMenu = {
    items: [
      {
        key: 'model',
        label: '模型',
        children: [
          { key: 'glm-4-flash', label: 'GLM-4 Flash' },
          { key: 'glm-4-plus', label: 'GLM-4 Plus' },
          { key: 'glm-4', label: 'GLM-4' },
        ],
        onClick: ({ key }: { key: string }) => {
          onSettingsChange?.({ ...settings!, model: key });
        },
      },
      {
        key: 'temperature',
        label: `温度: ${settings?.temperature || 0.7}`,
      },
      {
        key: 'stream',
        label: '流式输出',
        icon: settings?.streamEnabled ? <BulbOutlined /> : null,
        onClick: () => {
          onSettingsChange?.({ ...settings!, streamEnabled: !settings?.streamEnabled });
        },
      },
    ],
  };

  // 自动调整高度
  useEffect(() => {
    if (textAreaRef.current) {
      textAreaRef.current.style.height = 'auto';
      textAreaRef.current.style.height = `${Math.min(textAreaRef.current.scrollHeight, 200)}px`;
    }
  }, [message]);

  const canSend = message.trim().length > 0 && !disabled;

  return (
    <div className="chat-input-container">
      {/* 快捷建议 */}
      <div className="quick-suggestions">
        <Text type="secondary" className="suggestions-label">
          快捷指令:
        </Text>
        <div className="suggestions-list">
          {QUICK_SUGGESTIONS.map((suggestion) => (
            <Button
              key={suggestion.key}
              type="text"
              size="small"
              onClick={() => handleSuggestionClick(suggestion.prompt)}
              className="suggestion-btn"
            >
              {suggestion.label}
            </Button>
          ))}
        </div>
      </div>

      {/* 输入区域 */}
      <div className="chat-input-wrapper">
        <TextArea
          ref={textAreaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          onCompositionStart={handleCompositionStart}
          onCompositionEnd={handleCompositionEnd}
          placeholder={placeholder}
          disabled={disabled}
          maxLength={maxLength}
          autoSize={{ minRows: 1, maxRows: 6 }}
          className="chat-textarea"
        />

        {/* 操作按钮 */}
        <div className="chat-input-actions">
          <Space>
            {onClear && (
              <Tooltip title="清空对话">
                <Button
                  type="text"
                  icon={<ClearOutlined />}
                  onClick={onClear}
                  disabled={disabled}
                />
              </Tooltip>
            )}

            {settings && onSettingsChange && (
              <Dropdown menu={settingsMenu} trigger={['click']} placement="topLeft">
                <Button type="text" icon={<SettingOutlined />} disabled={disabled} />
              </Dropdown>
            )}

            <Tooltip title="语音输入（开发中）">
              <Button type="text" icon={<AudioOutlined />} disabled />
            </Tooltip>
          </Space>

          <Tooltip title={isStreaming ? '停止生成' : canSend ? '发送消息' : '请输入内容'}>
            <Button
              type="primary"
              icon={isStreaming ? <StopOutlined /> : <SendOutlined />}
              onClick={isStreaming ? onCancel : handleSend}
              disabled={!isStreaming && !canSend}
              danger={isStreaming}
              className="send-button"
            />
          </Tooltip>
        </div>
      </div>

      {/* 字数统计 */}
      {message.length > 0 && (
        <div className="char-count">
          <Text type="secondary">
            {message.length} / {maxLength}
          </Text>
        </div>
      )}
    </div>
  );
});

ChatInput.displayName = 'ChatInput';

export default ChatInput;
