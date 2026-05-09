import React, { useState } from 'react';
import { Card, Badge, Avatar, Typography, Space, Dropdown, Tag, Empty, Button } from 'antd';
import {
  MoreOutlined,
  PlusOutlined,
  RobotOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import type { Agent, Task, AgentType } from '@/types/kanban';
import TaskCard from './TaskCard';
import './AgentColumn.css';

const { Text, Title } = Typography;

interface AgentColumnProps {
  agent: Agent;
  tasks: Task[];
  onTaskClick?: (task: Task) => void;
  onTaskDrop?: (taskId: string, agentId: AgentType) => void;
  onCreateTask?: (agentId: AgentType) => void;
}

const AgentColumn: React.FC<AgentColumnProps> = ({
  agent,
  tasks,
  onTaskClick,
  onTaskDrop,
  onCreateTask,
}) => {
  const [isDragOver, setIsDragOver] = useState(false);

  // 获取状态图标和颜色
  const getStatusConfig = (status: Agent['status']) => {
    switch (status) {
      case 'idle':
        return {
          icon: <ClockCircleOutlined />,
          color: '#8c8c8c',
          text: '空闲',
        };
      case 'working':
        return {
          icon: <LoadingOutlined />,
          color: '#1890ff',
          text: '工作中',
        };
      case 'waiting':
        return {
          icon: <ExclamationCircleOutlined />,
          color: '#faad14',
          text: '等待中',
        };
      case 'error':
        return {
          icon: <ExclamationCircleOutlined />,
          color: '#ff4d4f',
          text: '异常',
        };
      default:
        return {
          icon: <ClockCircleOutlined />,
          color: '#8c8c8c',
          text: '未知',
        };
    }
  };

  const statusConfig = getStatusConfig(agent.status);

  // 计算统计数据
  const stats = {
    total: tasks.length,
    pending: tasks.filter((t) => t.status === 'pending').length,
    inProgress: tasks.filter((t) => t.status === 'in_progress').length,
    review: tasks.filter((t) => t.status === 'review').length,
    completed: tasks.filter((t) => t.status === 'completed').length,
  };

  // 处理拖拽进入
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setIsDragOver(true);
  };

  // 处理拖拽离开
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  // 处理放置
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    
    const taskId = e.dataTransfer.getData('taskId');
    if (taskId && onTaskDrop) {
      onTaskDrop(taskId, agent.id);
    }
  };

  // 下拉菜单
  const menuItems = [
    {
      key: 'create',
      icon: <PlusOutlined />,
      label: '创建任务',
      onClick: () => onCreateTask?.(agent.id),
    },
    {
      key: 'details',
      icon: <RobotOutlined />,
      label: '查看详情',
    },
  ];

  return (
    <div
      className={`agent-column ${isDragOver ? 'agent-column-drag-over' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* 智能体头部 */}
      <Card className="agent-header" size="small">
        <div className="agent-header-top">
          <Space>
            <Badge
              dot
              color={statusConfig.color}
            >
              <Avatar
                size={40}
                icon={<RobotOutlined />}
                className="agent-avatar"
                style={{ backgroundColor: statusConfig.color }}
              />
            </Badge>
            <div>
              <Title level={5} className="agent-name">
                {agent.name}
              </Title>
              <Space size={4}>
                <Tag color={statusConfig.color} className="agent-status-tag">
                  {statusConfig.icon} {statusConfig.text}
                </Tag>
                {agent.load > 0 && (
                  <Text type="secondary" className="agent-load">
                    负载: {agent.load}%
                  </Text>
                )}
              </Space>
            </div>
          </Space>

          <Dropdown menu={{ items: menuItems }} trigger={['click']}>
            <Button type="text" icon={<MoreOutlined />} size="small" />
          </Dropdown>
        </div>

        {/* 任务统计 */}
        <div className="agent-stats">
          <Space size={8} wrap>
            <Tag className="stat-tag">
              共 {stats.total}
            </Tag>
            {stats.inProgress > 0 && (
              <Tag color="processing" className="stat-tag">
                进行中 {stats.inProgress}
              </Tag>
            )}
            {stats.completed > 0 && (
              <Tag color="success" className="stat-tag">
                <CheckCircleOutlined /> {stats.completed}
              </Tag>
            )}
          </Space>
        </div>

        {/* 专长标签 */}
        <div className="agent-specialties">
          {agent.specialties.slice(0, 3).map((specialty, index) => (
            <Tag key={index} className="specialty-tag">
              {specialty}
            </Tag>
          ))}
        </div>
      </Card>

      {/* 任务列表 */}
      <div className="agent-tasks">
        {tasks.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无任务"
            className="empty-tasks"
          />
        ) : (
          tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              onClick={() => onTaskClick?.(task)}
            />
          ))
        )}
      </div>

      {/* 添加任务按钮 */}
      <Button
        type="dashed"
        block
        icon={<PlusOutlined />}
        className="add-task-btn"
        onClick={() => onCreateTask?.(agent.id)}
      >
        添加任务
      </Button>
    </div>
  );
};

export default AgentColumn;
