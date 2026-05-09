import { useAuthStore } from '@/stores/auth';
import type { WSConnectionStatus, WSMessage, StreamEvent } from '@/types/chat';

// WebSocket 配置
const WS_BASE_URL = import.meta.env.VITE_WS_URL || `ws://${window.location.host}/ws`;

// WebSocket 事件回调
interface WSCallbacks {
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
  onMessage?: (message: WSMessage) => void;
  onStream?: (event: StreamEvent) => void;
}

// WebSocket 管理类
class WebSocketManager {
  private ws: WebSocket | null = null;
  private callbacks: WSCallbacks = {};
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private pingInterval: number | null = null;
  private isManualClose = false;

  // 连接 WebSocket
  connect(callbacks: WSCallbacks = {}): Promise<void> {
    return new Promise((resolve, reject) => {
      this.callbacks = callbacks;
      this.isManualClose = false;

      const token = useAuthStore.getState().token;
      if (!token) {
        reject(new Error('未登录，无法连接'));
        return;
      }

      const wsUrl = `${WS_BASE_URL}?token=${token}`;

      try {
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
          console.log('[WebSocket] 连接成功');
          this.reconnectAttempts = 0;
          this.startPing();
          this.callbacks.onOpen?.();
          resolve();
        };

        this.ws.onclose = (event) => {
          console.log('[WebSocket] 连接关闭', event.code, event.reason);
          this.stopPing();
          this.callbacks.onClose?.();

          // 自动重连
          if (!this.isManualClose && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`[WebSocket] 尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
            setTimeout(() => {
              this.connect(this.callbacks);
            }, this.reconnectDelay * this.reconnectAttempts);
          }
        };

        this.ws.onerror = (error) => {
          console.error('[WebSocket] 连接错误', error);
          this.callbacks.onError?.(error);
          reject(error);
        };

        this.ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            // 处理流式消息
            if (data.type === 'message.stream') {
              this.callbacks.onStream?.({
                type: 'content',
                content: data.payload.content,
                messageId: data.payload.messageId,
              });
            } else if (data.type === 'message.complete') {
              this.callbacks.onStream?.({
                type: 'complete',
                messageId: data.payload.messageId,
              });
            } else if (data.type === 'message.error') {
              this.callbacks.onStream?.({
                type: 'error',
                error: data.payload.error,
              });
            } else {
              this.callbacks.onMessage?.(data);
            }
          } catch (err) {
            console.error('[WebSocket] 消息解析失败', err);
          }
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  // 发送消息
  send<T = any>(type: string, payload: T): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.error('[WebSocket] 连接未建立');
      return false;
    }

    const message: WSMessage<T> = {
      type: type as any,
      payload,
      timestamp: Date.now(),
    };

    this.ws.send(JSON.stringify(message));
    return true;
  }

  // 发送聊天消息
  sendChatMessage(sessionId: string, content: string, stream = true): boolean {
    return this.send('message.send', {
      sessionId,
      content,
      stream,
    });
  }

  // 创建会话
  createSession(title?: string): boolean {
    return this.send('session.create', { title });
  }

  // 删除会话
  deleteSession(sessionId: string): boolean {
    return this.send('session.delete', { sessionId });
  }

  // 重命名会话
  renameSession(sessionId: string, title: string): boolean {
    return this.send('session.rename', { sessionId, title });
  }

  // 开始心跳
  private startPing(): void {
    this.pingInterval = window.setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.send('ping', {});
      }
    }, 30000); // 30秒一次心跳
  }

  // 停止心跳
  private stopPing(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  // 断开连接
  disconnect(): void {
    this.isManualClose = true;
    this.stopPing();

    if (this.ws) {
      this.ws.close(1000, '用户主动断开');
      this.ws = null;
    }
  }

  // 获取连接状态
  getStatus(): WSConnectionStatus {
    if (!this.ws) return 'disconnected';

    switch (this.ws.readyState) {
      case WebSocket.CONNECTING:
        return 'connecting';
      case WebSocket.OPEN:
        return 'connected';
      case WebSocket.CLOSING:
      case WebSocket.CLOSED:
        return 'disconnected';
      default:
        return 'error';
    }
  }

  // 是否已连接
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// 单例模式
export const wsManager = new WebSocketManager();

// React Hook - 使用 WebSocket
import { useState, useEffect, useCallback, useRef } from 'react';

export const useWebSocket = () => {
  const [status, setStatus] = useState<WSConnectionStatus>('disconnected');
  const callbacksRef = useRef<WSCallbacks>({});

  const connect = useCallback((callbacks: WSCallbacks = {}) => {
    callbacksRef.current = callbacks;
    setStatus('connecting');

    return wsManager.connect({
      ...callbacks,
      onOpen: () => {
        setStatus('connected');
        callbacks.onOpen?.();
      },
      onClose: () => {
        setStatus('disconnected');
        callbacks.onClose?.();
      },
      onError: (error) => {
        setStatus('error');
        callbacks.onError?.(error);
      },
    });
  }, []);

  const disconnect = useCallback(() => {
    wsManager.disconnect();
    setStatus('disconnected');
  }, []);

  const send = useCallback(<T = any,>(type: string, payload: T) => {
    return wsManager.send(type, payload);
  }, []);

  useEffect(() => {
    return () => {
      // 组件卸载时不断开连接，保持全局单例
    };
  }, []);

  return {
    status,
    isConnected: status === 'connected',
    connect,
    disconnect,
    send,
    wsManager,
  };
};

export default wsManager;
