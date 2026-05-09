import { useCallback, useEffect, useRef, useState } from 'react';
import { message } from 'antd';
import { useKanbanStore } from '@/stores/kanban';
import type { 
  KanbanWSMessage, 
  Task, 
  AgentType,
} from '@/types/kanban';

interface UseKanbanWebSocketOptions {
  url?: string;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  heartbeatInterval?: number;
}

interface WebSocketCallbacks {
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
  onMessage?: (data: any) => void;
}

export const useKanbanWebSocket = (options: UseKanbanWebSocketOptions = {}) => {
  const {
    url = 'ws://localhost:8086/ws',
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
    heartbeatInterval = 30000, // 30秒心跳
  } = options;

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const heartbeatTimerRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
  
  const [isConnected, setIsConnected] = useState(false);

  const {
    setTasks,
    addTask,
    updateTask,
    deleteTask,
    moveTask,
    setAgents,
    updateAgent,
    updateAgentStatus,
    setConnectionStatus,
  } = useKanbanStore();

  // 清理定时器
  const clearTimers = useCallback(() => {
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  // 启动心跳
  const startHeartbeat = useCallback(() => {
    clearTimers();
    
    heartbeatTimerRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: 'kanban.heartbeat',
          timestamp: Date.now(),
        }));
      }
    }, heartbeatInterval);
  }, [heartbeatInterval, clearTimers]);

  // 处理收到的消息
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data: KanbanWSMessage = JSON.parse(event.data);
      console.log('[Kanban WS] 收到消息:', data);

      switch (data.type) {
        case 'kanban.sync':
          // 全量同步
          if (data.payload.tasks) {
            setTasks(data.payload.tasks);
          }
          if (data.payload.agents) {
            setAgents(data.payload.agents);
          }
          break;

        case 'task.created':
          addTask(data.payload as Task);
          message.success('新任务已创建');
          break;

        case 'task.updated':
          const updatedTaskId = data.payload.taskId;
          updateTask(updatedTaskId, data.payload.updates);
          break;

        case 'task.deleted':
          deleteTask(data.payload.taskId);
          message.info('任务已删除');
          break;

        case 'task.moved':
          const movedTaskId = data.payload.taskId;
          moveTask(movedTaskId, data.payload.newStatus, data.payload.newAgent);
          break;

        case 'agent.status_changed':
          const { agentId, status } = data.payload;
          updateAgentStatus(agentId, status);
          break;

        case 'agent.assigned':
          const { agentId: aid, taskId: tid } = data.payload;
          updateTask(tid, { assignedAgent: aid });
          updateAgent(aid, { currentTask: tid });
          break;

        case 'error':
          message.error(data.payload.message || '发生错误');
          console.error('[Kanban WS] 错误:', data.payload);
          break;

        default:
          console.log('[Kanban WS] 未知消息类型:', data.type);
      }
    } catch (error) {
      console.error('[Kanban WS] 解析消息失败:', error);
    }
  }, [setTasks, addTask, updateTask, deleteTask, moveTask, setAgents, updateAgent, updateAgentStatus]);

  // 连接 WebSocket
  const connect = useCallback((callbacks?: WebSocketCallbacks) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[Kanban WS] 已连接，跳过');
      return;
    }

    setConnectionStatus('connecting');
    console.log('[Kanban WS] 正在连接:', url);

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[Kanban WS] 连接成功');
        setIsConnected(true);
        setConnectionStatus('connected');
        reconnectAttemptsRef.current = 0;
        
        // 启动心跳
        startHeartbeat();
        
        // 请求初始数据
        ws.send(JSON.stringify({
          type: 'kanban.sync',
          timestamp: Date.now(),
        }));

        callbacks?.onOpen?.();
      };

      ws.onclose = (event) => {
        console.log('[Kanban WS] 连接关闭:', event.code, event.reason);
        setIsConnected(false);
        setConnectionStatus('disconnected');
        clearTimers();

        // 尝试重连
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++;
          console.log(`[Kanban WS] 尝试重连 (${reconnectAttemptsRef.current}/${maxReconnectAttempts})`);
          
          reconnectTimerRef.current = setTimeout(() => {
            connect(callbacks);
          }, reconnectInterval);
        } else {
          console.log('[Kanban WS] 达到最大重连次数');
          message.error('WebSocket 连接失败，请刷新页面重试');
        }

        callbacks?.onClose?.();
      };

      ws.onerror = (error) => {
        console.error('[Kanban WS] 连接错误:', error);
        setConnectionStatus('error');
        callbacks?.onError?.(error);
      };

      ws.onmessage = handleMessage;

    } catch (error) {
      console.error('[Kanban WS] 创建连接失败:', error);
      setConnectionStatus('error');
    }
  }, [url, reconnectInterval, maxReconnectAttempts, setConnectionStatus, startHeartbeat, clearTimers, handleMessage]);

  // 断开连接
  const disconnect = useCallback(() => {
    clearTimers();
    reconnectAttemptsRef.current = maxReconnectAttempts; // 阻止重连
    
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    setIsConnected(false);
    setConnectionStatus('disconnected');
    console.log('[Kanban WS] 已断开连接');
  }, [clearTimers, setConnectionStatus]);

  // 发送消息
  const send = useCallback((type: string, payload: any) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      console.warn('[Kanban WS] 未连接，无法发送消息');
      return false;
    }

    const message: KanbanWSMessage = {
      type: type as any,
      payload,
      timestamp: Date.now(),
    };

    wsRef.current.send(JSON.stringify(message));
    console.log('[Kanban WS] 发送消息:', message);
    return true;
  }, []);

  // 创建任务
  const createTask = useCallback((task: Partial<Task>) => {
    return send('task.create', task);
  }, [send]);

  // 更新任务
  const updateTaskWS = useCallback((taskId: string, updates: Partial<Task>) => {
    return send('task.update', { taskId, updates });
  }, [send]);

  // 移动任务
  const moveTaskWS = useCallback((taskId: string, newStatus: Task['status'], newAgent?: AgentType) => {
    return send('task.move', { taskId, newStatus, newAgent });
  }, [send]);

  // 删除任务
  const deleteTaskWS = useCallback((taskId: string) => {
    return send('task.delete', { taskId });
  }, [send]);

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    connect,
    disconnect,
    send,
    createTask,
    updateTask: updateTaskWS,
    moveTask: moveTaskWS,
    deleteTask: deleteTaskWS,
  };
};

export default useKanbanWebSocket;
