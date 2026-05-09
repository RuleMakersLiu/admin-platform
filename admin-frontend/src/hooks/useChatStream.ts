import { useCallback, useRef, useState } from 'react';
import { useChatStore } from '@/stores/chat';

interface UseChatStreamOptions {
  agentType?: string;
  onComplete?: (fullContent: string) => void;
  onError?: (error: string) => void;
}

export function useChatStream(options: UseChatStreamOptions = {}) {
  const { agentType = 'PM', onComplete, onError } = options;
  const [isStreaming, setIsStreaming] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const { addMessage, updateMessage, appendMessageContent, currentSessionId, settings } =
    useChatStore.getState();

  const sendMessage = useCallback(
    async (message: string) => {
      const store = useChatStore.getState();
      const sessionId = store.currentSessionId;
      if (!sessionId) return;

      const userMsgId = `msg_${Date.now()}_user`;
      const assistantMsgId = `msg_${Date.now()}_assistant`;

      store.addMessage({
        id: userMsgId,
        sessionId,
        type: 'user',
        content: message,
        status: 'completed',
        createdAt: Date.now(),
        metadata: { agentType },
      });

      store.addMessage({
        id: assistantMsgId,
        sessionId,
        type: 'assistant',
        content: '',
        status: 'streaming',
        createdAt: Date.now(),
        metadata: { agentType },
      });

      setIsStreaming(true);
      abortControllerRef.current = new AbortController();

      try {
        const token = useAuthStore_getToken();
        const response = await fetch('/api/chat/stream', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            message,
            session_id: sessionId,
            agent_type: agentType,
          }),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No reader available');

        const decoder = new TextDecoder();
        let fullContent = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const text = decoder.decode(value, { stream: true });
          const lines = text.split('\n');

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;

            try {
              const data = JSON.parse(line.slice(6));

              if (data.type === 'chunk' && data.content) {
                fullContent += data.content;
                store.appendMessageContent(assistantMsgId, data.content);
              } else if (data.type === 'done') {
                store.updateMessage(assistantMsgId, {
                  status: 'completed',
                  content: data.content || fullContent,
                });
              } else if (data.error) {
                store.updateMessage(assistantMsgId, {
                  status: 'error',
                  error: data.error,
                });
              }
            } catch {
              // skip malformed JSON
            }
          }
        }

        onComplete?.(fullContent);
      } catch (err: any) {
        if (err.name === 'AbortError') {
          store.updateMessage(assistantMsgId, { status: 'completed' });
        } else {
          const errorMsg = err.message || '发送失败';
          store.updateMessage(assistantMsgId, {
            status: 'error',
            error: errorMsg,
          });
          onError?.(errorMsg);
        }
      } finally {
        setIsStreaming(false);
        abortControllerRef.current = null;
      }
    },
    [agentType, onComplete, onError]
  );

  const cancel = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  return { sendMessage, cancel, isStreaming };
}

function useAuthStore_getToken(): string | null {
  try {
    const { useAuthStore } = require('@/stores/auth');
    return useAuthStore.getState().token;
  } catch {
    return null;
  }
}

export default useChatStream;
