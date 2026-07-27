import React, { memo, useState, useRef, useCallback } from 'react';
import { Input, Button, Tooltip, Dropdown, Space, Typography, Tag } from 'antd';
import {
  SendOutlined,
  SettingOutlined,
  ClearOutlined,
  AudioOutlined,
  BulbOutlined,
  StopOutlined,
  PaperClipOutlined,
} from '@ant-design/icons';
import type { Attachment, ChatSettings } from '@/types/chat';
import { useKeyboardShortcut } from '@/hooks/useChat';
import './ChatInput.css';

const { TextArea } = Input;
const { Text } = Typography;

// 附件限制
const MAX_ATTACHMENTS = 5;
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const ACCEPTED_TYPES = 'image/*,.pdf,.docx,.xlsx,.pptx,.txt,.md,.csv,.json,audio/*';

// 聊天输入组件 Props
interface ChatInputProps {
  onSend: (message: string, attachments?: Attachment[]) => void;
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

const readFileAsDataUri = (file: File): Promise<Attachment> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () =>
      resolve({ mime: file.type, filename: file.name, data_uri: String(reader.result) });
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });

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
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const textAreaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 发送消息
  const handleSend = useCallback(() => {
    const trimmedMessage = message.trim();
    if ((trimmedMessage || attachments.length) && !disabled) {
      onSend(trimmedMessage, attachments);
      setMessage('');
      setAttachments([]);
      textAreaRef.current?.focus();
    }
  }, [message, attachments, disabled, onSend]);

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

  // 附件选择
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    e.target.value = ''; // 允许重复选择同一文件
    const room = MAX_ATTACHMENTS - attachments.length;
    for (const file of files.slice(0, room)) {
      if (file.size > MAX_FILE_SIZE) continue; // 跳过超大文件
      try {
        const att = await readFileAsDataUri(file);
        setAttachments((prev) => [...prev, att]);
      } catch {
        /* 忽略读取失败 */
      }
    }
  };

  const removeAttachment = (idx: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== idx));
  };

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

  // NOTE: 高度自适应由 antd TextArea 的 autoSize={{ minRows, maxRows }} 负责。
  // 切勿手动设置 ref.style.height —— Input.TextArea 的 ref 是 antd 组件实例（非 DOM 节点），
  // 直接访问 .style 会抛 "Cannot set properties of undefined (setting 'height')" 并白屏整个聊天输入区。

  const canSend = (message.trim().length > 0 || attachments.length > 0) && !disabled;

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

      {/* 附件预览 */}
      {attachments.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
          {attachments.map((att, idx) => (
            <Tag
              key={`${att.filename}-${idx}`}
              closable
              onClose={() => removeAttachment(idx)}
              color="blue"
              icon={<PaperClipOutlined />}
            >
              {att.filename || att.mime || '附件'}
            </Tag>
          ))}
        </div>
      )}

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

            <Tooltip title={`添加附件（图片 / 文档 / 语音，最多 ${MAX_ATTACHMENTS} 个）`}>
              <Button
                type="text"
                icon={<PaperClipOutlined />}
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled || attachments.length >= MAX_ATTACHMENTS}
              />
            </Tooltip>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={ACCEPTED_TYPES}
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />

            <Tooltip title="语音输入（开发中）">
              <Button type="text" icon={<AudioOutlined />} disabled />
            </Tooltip>
          </Space>

          <Tooltip title={isStreaming ? '停止生成' : canSend ? '发送消息' : '请输入内容或添加附件'}>
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
