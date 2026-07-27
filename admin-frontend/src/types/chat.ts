// 聊天消息类型
export type MessageType = 'user' | 'assistant' | 'system';

// 消息状态
export type MessageStatus = 'pending' | 'streaming' | 'completed' | 'error';

// 单条消息
export interface Message {
  id: string;
  sessionId: string;
  type: MessageType;
  content: string;
  status: MessageStatus;
  createdAt: number;
  error?: string;
  attachments?: Attachment[];
  metadata?: {
    model?: string;
    tokens?: number;
    agentType?: string;
    [key: string]: any;
  };
}

// 多模态附件（图像 / 文档 / 语音）
export interface Attachment {
  type?: 'image' | 'document' | 'audio'; // 留空则后端按 mime/扩展名自动判断
  mime: string;
  filename: string;
  data_uri: string; // data:<mime>;base64,<payload>
}

// 会话
export interface Session {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
  lastMessage?: string;
  metadata?: {
    model?: string;
    projectId?: string;
    [key: string]: any;
  };
}

// WebSocket 连接状态
export type WSConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

// WebSocket 消息类型
export type WSMessageType =
  | 'session.create'
  | 'session.delete'
  | 'session.rename'
  | 'message.send'
  | 'message.stream'
  | 'message.complete'
  | 'message.error'
  | 'ping'
  | 'pong';

// WebSocket 消息结构
export interface WSMessage<T = any> {
  type: WSMessageType;
  payload: T;
  timestamp: number;
}

// 流式消息事件
export interface StreamEvent {
  type: 'start' | 'content' | 'complete' | 'error';
  content?: string;
  messageId?: string;
  error?: string;
}

// 聊天设置
export interface ChatSettings {
  model: string;
  temperature: number;
  maxTokens: number;
  streamEnabled: boolean;
}

// 主题类型
export type ThemeMode = 'light' | 'dark';
