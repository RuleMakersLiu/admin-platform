import React, { useEffect } from 'react';
import { Layout, Input, Select, Space, Badge, Tooltip, Button, Typography } from 'antd';
import {
  SearchOutlined,
  ReloadOutlined,
  WifiOutlined,
  DisconnectOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { useKanbanStore } from '@/stores/kanban';
import { useKanbanWebSocket } from '@/hooks/useKanbanWebSocket';
import AgentColumn from './AgentColumn';
import type { AgentType, Task, TaskStatus } from '@/types/kanban';
import './KanbanBoard.css';

const { Content, Header } = Layout;
const { Title } = Typography;

const KanbanBoard: React.FC = () => {
  // Store
  const {
    tasks,
    agents,
    connectionStatus,
    filterAgent,
    filterStatus,
    searchKeyword,
    setFilterAgent,
    setFilterStatus,
    setSearchKeyword,
    moveTask,
  } = useKanbanStore();

  // WebSocket
  const {
    isConnected,
    connect,
    disconnect,
    createTask,
    moveTask: moveTaskWS,
  } = useKanbanWebSocket({
    url: 'ws://localhost:8086/ws',
    reconnectInterval: 3000,
    maxReconnectAttempts: 5,
    heartbeatInterval: 30000,
  });

  // 初始化 WebSocket 连接
  useEffect(() => {
    connect({
      onOpen: () => {
        console.log('看板 WebSocket 已连接');
      },
      onClose: () => {
        console.log('看板 WebSocket 已断开');
      },
      onError: (error) => {
        console.error('看板 WebSocket 错误:', error);
      },
    });
  }, []);

  // 获取过滤后的任务

  // 按智能体分组任务
  const getAgentTasks = (agentId: AgentType): Task[] => {
    let agentTasks = tasks.filter((task) => task.assignedAgent === agentId);
    
    // 应用过滤
    if (filterStatus !== 'all') {
      agentTasks = agentTasks.filter((task) => task.status === filterStatus);
    }
    
    if (searchKeyword) {
      const keyword = searchKeyword.toLowerCase();
      agentTasks = agentTasks.filter(
        (task) =>
          task.title.toLowerCase().includes(keyword) ||
          task.description?.toLowerCase().includes(keyword)
      );
    }
    
    return agentTasks;
  };

  // 处理任务点击
  const handleTaskClick = (task: Task) => {
    console.log('点击任务:', task);
    // TODO: 打开任务详情抽屉或模态框
  };

  // 处理任务拖放
  const handleTaskDrop = (taskId: string, agentId: AgentType) => {
    moveTask(taskId, 'pending', agentId);
    moveTaskWS(taskId, 'pending', agentId);
    console.log(`任务 ${taskId} 移动到智能体 ${agentId}`);
  };

  // 处理创建任务
  const handleCreateTask = (agentId: AgentType) => {
    console.log('为智能体创建任务:', agentId);
    // TODO: 打开创建任务模态框
    const newTask = {
      title: '新任务',
      status: 'pending' as TaskStatus,
      priority: 'medium' as const,
      assignedAgent: agentId,
      createdBy: 'human' as const,
    };
    createTask(newTask);
  };

  // 连接状态配置
  const getConnectionConfig = () => {
    switch (connectionStatus) {
      case 'connected':
        return {
          icon: <WifiOutlined />,
          color: 'green',
          text: '已连接',
        };
      case 'connecting':
        return {
          icon: <LoadingOutlined />,
          color: 'orange',
          text: '连接中',
        };
      case 'error':
        return {
          icon: <DisconnectOutlined />,
          color: 'red',
          text: '连接错误',
        };
      default:
        return {
          icon: <DisconnectOutlined />,
          color: 'default',
          text: '未连接',
        };
    }
  };

  const connectionConfig = getConnectionConfig();

  // 重新连接
  const handleReconnect = () => {
    disconnect();
    setTimeout(() => {
      connect();
    }, 500);
  };

  // 智能体列表
  const agentList: AgentType[] = ['coordinator', 'pjm', 'be', 'fe', 'qa', 'rpt'];

  return (
    <Layout className="kanban-board">
      {/* 头部工具栏 */}
      <Header className="kanban-header">
        <div className="header-left">
          <Title level={4} className="header-title">
            AI 协作看板
          </Title>
          <Badge
            status={connectionConfig.color as any}
            text={
              <Space size={4}>
                {connectionConfig.icon}
                <span>{connectionConfig.text}</span>
              </Space>
            }
          />
        </div>

        <div className="header-right">
          <Space size={12}>
            {/* 搜索框 */}
            <Input
              placeholder="搜索任务..."
              prefix={<SearchOutlined />}
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              style={{ width: 200 }}
              allowClear
            />

            {/* 状态过滤 */}
            <Select
              placeholder="状态筛选"
              value={filterStatus}
              onChange={setFilterStatus}
              style={{ width: 120 }}
              options={[
                { label: '全部状态', value: 'all' },
                { label: '待处理', value: 'pending' },
                { label: '进行中', value: 'in_progress' },
                { label: '待审核', value: 'review' },
                { label: '已完成', value: 'completed' },
              ]}
            />

            {/* 智能体过滤 */}
            <Select
              placeholder="智能体筛选"
              value={filterAgent}
              onChange={setFilterAgent}
              style={{ width: 120 }}
              options={[
                { label: '全部智能体', value: 'all' },
                { label: '协调者', value: 'coordinator' },
                { label: '项目经理', value: 'pjm' },
                { label: '后端开发', value: 'be' },
                { label: '前端开发', value: 'fe' },
                { label: '测试工程师', value: 'qa' },
                { label: '报告专员', value: 'rpt' },
              ]}
            />

            {/* 重新连接按钮 */}
            {!isConnected && (
              <Tooltip title="重新连接">
                <Button
                  type="text"
                  icon={<ReloadOutlined />}
                  onClick={handleReconnect}
                />
              </Tooltip>
            )}
          </Space>
        </div>
      </Header>

      {/* 看板主体 */}
      <Content className="kanban-content">
        <div className="kanban-columns">
          {agentList.map((agentId) => (
            <AgentColumn
              key={agentId}
              agent={agents[agentId]}
              tasks={getAgentTasks(agentId)}
              onTaskClick={handleTaskClick}
              onTaskDrop={handleTaskDrop}
              onCreateTask={handleCreateTask}
            />
          ))}
        </div>
      </Content>
    </Layout>
  );
};

export default KanbanBoard;
