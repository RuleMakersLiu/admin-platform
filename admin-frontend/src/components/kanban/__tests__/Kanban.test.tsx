/**
 * Kanban Board Tests
 * 看板组件测试
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { TaskCard } from '@/components/kanban';
import type { Task } from '@/types/kanban';

// Mock task data
const mockTask: Task = {
  id: 'test-task-1',
  title: '测试任务',
  description: '这是一个测试任务',
  status: 'in_progress',
  priority: 'high',
  assignedAgent: 'be',
  createdBy: 'human',
  createdAt: Date.now() - 3600000,
  updatedAt: Date.now() - 1800000,
  progress: 60,
  tags: ['测试', '后端'],
};

describe('Kanban Components', () => {
  describe('TaskCard', () => {
    it('should render task card with correct information', () => {
      render(
        <BrowserRouter>
          <TaskCard task={mockTask} />
        </BrowserRouter>
      );

      // 检查任务标题是否显示
      expect(screen.getByText('测试任务')).toBeInTheDocument();
      
      // 检查任务 ID 是否显示（前6位）
      expect(screen.getByText(/#test-t/)).toBeInTheDocument();
    });

    it('should display task priority tag', () => {
      render(
        <BrowserRouter>
          <TaskCard task={mockTask} />
        </BrowserRouter>
      );

      // 检查优先级标签
      expect(screen.getByText(/高/)).toBeInTheDocument();
    });

    it('should display task tags', () => {
      render(
        <BrowserRouter>
          <TaskCard task={mockTask} />
        </BrowserRouter>
      );

      // 检查任务标签
      expect(screen.getByText('测试')).toBeInTheDocument();
      expect(screen.getByText('后端')).toBeInTheDocument();
    });

    it('should show progress bar for in-progress tasks', () => {
      const { container } = render(
        <BrowserRouter>
          <TaskCard task={mockTask} />
        </BrowserRouter>
      );

      // 检查进度条是否存在
      const progressBar = container.querySelector('.ant-progress');
      expect(progressBar).toBeInTheDocument();
    });
  });
});
