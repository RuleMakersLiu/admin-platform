import React from 'react';
import { Card, Tag, Progress, Tooltip, Space, Typography } from 'antd';
import {
  ClockCircleOutlined,
  UserOutlined,
  FlagOutlined,
  CheckCircleOutlined,
  SyncOutlined,
  EyeOutlined,
  PauseCircleOutlined,
} from '@ant-design/icons';
import type { Task, TaskPriority, TaskStatus } from '@/types/kanban';
import { AGENT_NAMES, PRIORITY_COLORS } from '@/types/kanban';
import './TaskCard.css';

const { Text, Paragraph } = Typography;

interface TaskCardProps {
  task: Task;
  onClick?: () => void;
  draggable?: boolean;
  onDragStart?: (e: React.DragEvent, taskId: string) => void;
}

const TaskCard: React.FC<TaskCardProps> = ({
  task,
  onClick,
  draggable = true,
  onDragStart,
}) => {
  // 格式化时间
  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    
    if (diff < 60000) return '刚刚';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
    return date.toLocaleDateString();
  };

  // 获取状态图标
  const getStatusIcon = (status: TaskStatus) => {
    switch (status) {
      case 'pending':
        return <PauseCircleOutlined style={{ color: '#8c8c8c' }} />;
      case 'in_progress':
        return <SyncOutlined spin style={{ color: '#1890ff' }} />;
      case 'review':
        return <EyeOutlined style={{ color: '#faad14' }} />;
      case 'completed':
        return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
      default:
        return null;
    }
  };

  // 获取优先级标签
  const getPriorityTag = (priority: TaskPriority) => {
    const labels: Record<TaskPriority, string> = {
      low: '低',
      medium: '中',
      high: '高',
      urgent: '紧急',
    };
    return (
      <Tag color={PRIORITY_COLORS[priority]}>
        <FlagOutlined /> {labels[priority]}
      </Tag>
    );
  };

  // 处理拖拽开始
  const handleDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData('taskId', task.id);
    e.dataTransfer.effectAllowed = 'move';
    onDragStart?.(e, task.id);
  };

  return (
    <Card
      className={`task-card task-card-${task.status}`}
      size="small"
      hoverable
      onClick={onClick}
      draggable={draggable}
      onDragStart={handleDragStart}
    >
      {/* 头部：状态 + 优先级 */}
      <div className="task-card-header">
        <Space size={4}>
          {getStatusIcon(task.status)}
          <Text strong className="task-card-id">
            #{task.id.slice(0, 6)}
          </Text>
        </Space>
        {getPriorityTag(task.priority)}
      </div>

      {/* 标题 */}
      <Paragraph
        className="task-card-title"
        ellipsis={{ rows: 2 }}
        strong
      >
        {task.title}
      </Paragraph>

      {/* 描述 */}
      {task.description && (
        <Paragraph
          className="task-card-description"
          ellipsis={{ rows: 2 }}
          type="secondary"
        >
          {task.description}
        </Paragraph>
      )}

      {/* 进度条 */}
      {task.status === 'in_progress' && task.progress !== undefined && (
        <div className="task-card-progress">
          <Progress
            percent={task.progress}
            size="small"
            status={task.progress === 100 ? 'success' : 'active'}
          />
        </div>
      )}

      {/* 标签 */}
      {task.tags && task.tags.length > 0 && (
        <div className="task-card-tags">
          {task.tags.slice(0, 3).map((tag, index) => (
            <Tag key={index} className="task-tag">
              {tag}
            </Tag>
          ))}
          {task.tags.length > 3 && (
            <Tag className="task-tag">+{task.tags.length - 3}</Tag>
          )}
        </div>
      )}

      {/* 底部：指派人 + 时间 */}
      <div className="task-card-footer">
        <Space size={8}>
          {task.assignedAgent && (
            <Tooltip title={AGENT_NAMES[task.assignedAgent]}>
              <Tag icon={<UserOutlined />} color="blue">
                {AGENT_NAMES[task.assignedAgent]}
              </Tag>
            </Tooltip>
          )}
          <Text type="secondary" className="task-card-time">
            <ClockCircleOutlined /> {formatTime(task.updatedAt)}
          </Text>
        </Space>
      </div>
    </Card>
  );
};

export default TaskCard;
