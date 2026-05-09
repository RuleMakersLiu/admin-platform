import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Session, Message, ChatSettings, ThemeMode, WSConnectionStatus } from '@/types/chat';

interface ChatState {
  // 会话列表
  sessions: Session[];
  currentSessionId: string | null;

  // 消息映射 (sessionId -> messages)
  messagesMap: Record<string, Message[]>;

  // 连接状态
  connectionStatus: WSConnectionStatus;

  // 聊天设置
  settings: ChatSettings;

  // 主题
  theme: ThemeMode;

  // UI 状态
  sidebarCollapsed: boolean;
  isLoading: boolean;

  // Actions - 会话管理
  setSessions: (sessions: Session[]) => void;
  addSession: (session: Session) => void;
  updateSession: (sessionId: string, updates: Partial<Session>) => void;
  deleteSession: (sessionId: string) => void;
  setCurrentSession: (sessionId: string | null) => void;

  // Actions - 消息管理
  setMessages: (sessionId: string, messages: Message[]) => void;
  addMessage: (message: Message) => void;
  updateMessage: (messageId: string, updates: Partial<Message>) => void;
  appendMessageContent: (messageId: string, content: string) => void;
  deleteMessages: (sessionId: string) => void;

  // Actions - 连接状态
  setConnectionStatus: (status: WSConnectionStatus) => void;

  // Actions - 设置
  updateSettings: (settings: Partial<ChatSettings>) => void;

  // Actions - 主题
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;

  // Actions - UI
  setSidebarCollapsed: (collapsed: boolean) => void;
  setIsLoading: (loading: boolean) => void;

  // Getters
  getCurrentSession: () => Session | null;
  getCurrentMessages: () => Message[];
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      // 初始状态
      sessions: [],
      currentSessionId: null,
      messagesMap: {},
      connectionStatus: 'disconnected',
      settings: {
        model: 'gpt-3.5-turbo',
        temperature: 0.7,
        maxTokens: 2000,
        streamEnabled: true,
      },
      theme: 'light',
      sidebarCollapsed: false,
      isLoading: false,

      // 会话管理
      setSessions: (sessions) => set({ sessions }),

      addSession: (session) => set((state) => ({
        sessions: [session, ...state.sessions],
        currentSessionId: session.id,
      })),

      updateSession: (sessionId, updates) => set((state) => ({
        sessions: state.sessions.map((s) =>
          s.id === sessionId ? { ...s, ...updates } : s
        ),
      })),

      deleteSession: (sessionId) => set((state) => {
        const newMessagesMap = { ...state.messagesMap };
        delete newMessagesMap[sessionId];

        const newSessions = state.sessions.filter((s) => s.id !== sessionId);
        const newCurrentSessionId =
          state.currentSessionId === sessionId
            ? newSessions[0]?.id || null
            : state.currentSessionId;

        return {
          sessions: newSessions,
          messagesMap: newMessagesMap,
          currentSessionId: newCurrentSessionId,
        };
      }),

      setCurrentSession: (sessionId) => set({ currentSessionId: sessionId }),

      // 消息管理
      setMessages: (sessionId, messages) => set((state) => ({
        messagesMap: {
          ...state.messagesMap,
          [sessionId]: messages,
        },
      })),

      addMessage: (message) => set((state) => {
        const sessionId = message.sessionId;
        const currentMessages = state.messagesMap[sessionId] || [];

        return {
          messagesMap: {
            ...state.messagesMap,
            [sessionId]: [...currentMessages, message],
          },
        };
      }),

      updateMessage: (messageId, updates) => set((state) => {
        const newMessagesMap = { ...state.messagesMap };

        for (const sessionId in newMessagesMap) {
          newMessagesMap[sessionId] = newMessagesMap[sessionId].map((msg) =>
            msg.id === messageId ? { ...msg, ...updates } : msg
          );
        }

        return { messagesMap: newMessagesMap };
      }),

      appendMessageContent: (messageId, content) => set((state) => {
        const newMessagesMap = { ...state.messagesMap };

        for (const sessionId in newMessagesMap) {
          newMessagesMap[sessionId] = newMessagesMap[sessionId].map((msg) =>
            msg.id === messageId
              ? { ...msg, content: msg.content + content }
              : msg
          );
        }

        return { messagesMap: newMessagesMap };
      }),

      deleteMessages: (sessionId) => set((state) => {
        const newMessagesMap = { ...state.messagesMap };
        delete newMessagesMap[sessionId];
        return { messagesMap: newMessagesMap };
      }),

      // 连接状态
      setConnectionStatus: (status) => set({ connectionStatus: status }),

      // 设置
      updateSettings: (newSettings) => set((state) => ({
        settings: { ...state.settings, ...newSettings },
      })),

      // 主题
      setTheme: (theme) => set({ theme }),

      toggleTheme: () => set((state) => ({
        theme: state.theme === 'light' ? 'dark' : 'light',
      })),

      // UI
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),

      setIsLoading: (loading) => set({ isLoading: loading }),

      // Getters
      getCurrentSession: () => {
        const state = get();
        return state.sessions.find((s) => s.id === state.currentSessionId) || null;
      },

      getCurrentMessages: () => {
        const state = get();
        if (!state.currentSessionId) return [];
        return state.messagesMap[state.currentSessionId] || [];
      },
    }),
    {
      name: 'webchat-storage',
      partialize: (state) => ({
        sessions: state.sessions,
        settings: state.settings,
        theme: state.theme,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
    }
  )
);

// 选择器 Hooks - 性能优化
export const useCurrentSession = () =>
  useChatStore((state) =>
    state.sessions.find((s) => s.id === state.currentSessionId) || null
  );

export const useCurrentMessages = () =>
  useChatStore((state) =>
    state.currentSessionId ? state.messagesMap[state.currentSessionId] || [] : []
  );

export const useTheme = () => useChatStore((state) => state.theme);

export const useConnectionStatus = () =>
  useChatStore((state) => state.connectionStatus);

export default useChatStore;
