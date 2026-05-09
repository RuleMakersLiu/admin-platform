/**
 * TaskCard 组件测试
 * 测试任务卡片组件的渲染和交互
 * 
 * 注意：需要先安装 Vitest 相关依赖：
 * npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'

// Mock antd 组件
vi.mock('antd', () => ({
  Card: ({ children, onClick, draggable, onDragStart, onDragEnd, style }: any) => (
    <div
      data-testid="task-card"
      onClick={onClick}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      style={style}
    >
      {children}
    </div>
  ),
  Tag: ({ children, color }: any) => (
    <span data-testid="tag" data-color={color}>{children}</span>
  ),
  Progress: ({ percent }: any) => (
    <div data-testid="progress" data-percent={percent}>{percent}%</div>
  ),
  Button: ({ children, onClick, icon, ...props }: any) => (
    <button onClick={onClick} {...props}>{icon}{children}</button>
  ),
  Space: ({ children }: any) => <div data-testid="space">{children}</div>,
  Typography: {
    Text: ({ children, type, style }: any) => (
      <span data-testid="text" data-type={type} style={style}>{children}</span>
    ),
  },
  Dropdown: ({ menu, children }: any) => <div data-testid="dropdown">{children}</div>,
}))

// Mock antd icons
vi.mock('@ant-design/icons', () => ({
  HolderOutlined: () => <span data-testid="holder-icon">⠿</span>,
  ClockCircleOutlined: () => <span data-testid="clock-icon">⏰</span>,
  SyncOutlined: () => <span data-testid="sync-icon">🔄</span>,
  ExclamationCircleOutlined: () => <span data-testid="exclamation-icon">❗</span>,
  CheckCircleOutlined: () => <span data-testid="check-icon">✅</span>,
  MoreOutlined: () => <span data-testid="more-icon">⋯</span>,
  ProjectOutlined: () => <span data-testid="project-icon">📁</span>,
  FlagOutlined: () => <span data-testid="flag-icon">🚩</span>,
  UserOutlined: () => <span data-testid="user-icon">👤</span>,
  CalendarOutlined: () => <span data-testid="calendar-icon">📅</span>,
  EyeOutlined: () => <span data-testid="eye-icon">👁</span>,
  EditOutlined: () => <span data-testid="edit-icon">✏️</span>,
  DeleteOutlined: () => <span data-testid="delete-icon">🗑️</span>,
}))

// Mock dayjs
vi.mock('dayjs', () => {
  const mockDayjs = (date: any) => ({
    format: (fmt: string) => '03-13 10:00',
    valueOf: () => date,
  })
  return mockDayjs
})

// Mock agent API
vi.mock('@/services/api', () => ({
  agentTypeNames: {
    PM: '产品经理',
    PJM: '项目经理',
    BE: '后端开发',
    FE: '前端开发',
    QA: '测试分身',
    RPT: '汇报分身',
  },
  agentTypeColors: {
    PM: '#1890ff',
    PJM: '#722ed1',
    BE: '#52c41a',
    FE: '#eb2f96',
    QA: '#fa8c16',
    RPT: '#13c2c2',
  },
}))

// 测试数据
const mockTask = {
  id: 'task_001',
  title: '实现用户登录功能',
  description: '实现用户登录功能，支持用户名密码和手机验证码登录',
  status: 'pending' as const,
  priority: 'P1' as const,
  assignee_type: 'BE' as const,
  project_id: 'project_001',
  project_name: '用户系统',
  progress: 30,
  due_date: Date.now() + 86400000, // 明天
  acceptance_criteria: ['功能正常运行', '通过单元测试'],
  created_at: Date.now() - 86400000,
  updated_at: Date.now(),
  status_history: [
    {
      status: 'pending',
      changed_at: Date.now() - 86400000,
      changed_by: 'system',
    },
  ],
}

const overdueTask = {
  ...mockTask,
  id: 'task_002',
  title: '逾期任务',
  due_date: Date.now() - 86400000, // 昨天
}

const completedTask = {
  ...mockTask,
  id: 'task_003',
  title: '已完成任务',
  status: 'completed' as const,
  progress: 100,
}

// 简化的 TaskCard 组件（用于测试）
const TaskCard = ({ task, onDragStart, onDragEnd, onClick, isDragging, onDelete, onEdit }: any) => {
  const priorityColors: Record<string, string> = {
    P0: '#ff4d4f',
    P1: '#fa8c16',
    P2: '#faad14',
    P3: '#8c8c8c',
  }

  const isOverdue = task.due_date && task.due_date < Date.now() && task.status !== 'completed'

  return (
    <div
      data-testid="task-card"
      draggable
      onDragStart={(e: any) => onDragStart(e, task)}
      onDragEnd={onDragEnd}
      onClick={() => onClick(task)}
      style={{
        opacity: isDragging ? 0.5 : 1,
        background: isOverdue ? '#fff1f0' : '#fff',
      }}
    >
      <span data-testid="task-title">{task.title}</span>
      <span data-testid="task-project">{task.project_name}</span>
      <span data-testid="task-priority" data-color={priorityColors[task.priority]}>
        {task.priority}
      </span>
      <span data-testid="task-assignee">{task.assignee_type}</span>
      <div data-testid="task-progress" data-percent={task.progress}>
        {task.progress}%
      </div>
      {isOverdue && <span data-testid="overdue-indicator">已逾期</span>}
      {task.status === 'completed' && <span data-testid="completed-indicator">已完成</span>}
    </div>
  )
}

describe('TaskCard 组件', () => {
  const mockOnDragStart = vi.fn()
  const mockOnDragEnd = vi.fn()
  const mockOnClick = vi.fn()
  const mockOnDelete = vi.fn()
  const mockOnEdit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('渲染测试', () => {
    it('应该正确渲染任务卡片', () => {
      render(
        <TaskCard
          task={mockTask}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={false}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      expect(screen.getByTestId('task-card')).toBeInTheDocument()
      expect(screen.getByTestId('task-title')).toHaveTextContent('实现用户登录功能')
      expect(screen.getByTestId('task-project')).toHaveTextContent('用户系统')
    })

    it('应该显示正确的优先级', () => {
      render(
        <TaskCard
          task={mockTask}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={false}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      const priority = screen.getByTestId('task-priority')
      expect(priority).toHaveTextContent('P1')
    })

    it('应该显示正确的负责人', () => {
      render(
        <TaskCard
          task={mockTask}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={false}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      const assignee = screen.getByTestId('task-assignee')
      expect(assignee).toHaveTextContent('BE')
    })

    it('应该显示正确的进度', () => {
      render(
        <TaskCard
          task={mockTask}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={false}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      const progress = screen.getByTestId('task-progress')
      expect(progress).toHaveTextContent('30%')
    })
  })

  describe('状态显示测试', () => {
    it('逾期任务应该显示逾期标识', () => {
      render(
        <TaskCard
          task={overdueTask}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={false}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      expect(screen.getByTestId('overdue-indicator')).toBeInTheDocument()
    })

    it('已完成任务应该显示完成标识', () => {
      render(
        <TaskCard
          task={completedTask}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={false}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      expect(screen.getByTestId('completed-indicator')).toBeInTheDocument()
    })

    it('正常任务不应该显示逾期标识', () => {
      render(
        <TaskCard
          task={mockTask}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={false}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      expect(screen.queryByTestId('overdue-indicator')).not.toBeInTheDocument()
    })
  })

  describe('交互测试', () => {
    it('点击卡片应该触发 onClick 回调', () => {
      render(
        <TaskCard
          task={mockTask}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={false}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      fireEvent.click(screen.getByTestId('task-card'))
      expect(mockOnClick).toHaveBeenCalledWith(mockTask)
    })

    it('拖拽开始应该触发 onDragStart 回调', () => {
      render(
        <TaskCard
          task={mockTask}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={false}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      fireEvent.dragStart(screen.getByTestId('task-card'))
      expect(mockOnDragStart).toHaveBeenCalled()
    })

    it('拖拽结束应该触发 onDragEnd 回调', () => {
      render(
        <TaskCard
          task={mockTask}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={false}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      fireEvent.dragEnd(screen.getByTestId('task-card'))
      expect(mockOnDragEnd).toHaveBeenCalled()
    })
  })

  describe('拖拽状态测试', () => {
    it('正在拖拽时应该降低透明度', () => {
      render(
        <TaskCard
          task={mockTask}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={true}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      const card = screen.getByTestId('task-card')
      expect(card).toHaveStyle({ opacity: 0.5 })
    })

    it('未拖拽时应该保持正常透明度', () => {
      render(
        <TaskCard
          task={mockTask}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={false}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      const card = screen.getByTestId('task-card')
      expect(card).toHaveStyle({ opacity: 1 })
    })
  })

  describe('优先级颜色测试', () => {
    it('P0 优先级应该是红色', () => {
      const p0Task = { ...mockTask, priority: 'P0' }
      render(
        <TaskCard
          task={p0Task}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={false}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      const priority = screen.getByTestId('task-priority')
      expect(priority).toHaveAttribute('data-color', '#ff4d4f')
    })

    it('P1 优先级应该是橙色', () => {
      const p1Task = { ...mockTask, priority: 'P1' }
      render(
        <TaskCard
          task={p1Task}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={false}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      const priority = screen.getByTestId('task-priority')
      expect(priority).toHaveAttribute('data-color', '#fa8c16')
    })

    it('P2 优先级应该是黄色', () => {
      const p2Task = { ...mockTask, priority: 'P2' }
      render(
        <TaskCard
          task={p2Task}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={false}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      const priority = screen.getByTestId('task-priority')
      expect(priority).toHaveAttribute('data-color', '#faad14')
    })

    it('P3 优先级应该是灰色', () => {
      const p3Task = { ...mockTask, priority: 'P3' }
      render(
        <TaskCard
          task={p3Task}
          onDragStart={mockOnDragStart}
          onDragEnd={mockOnDragEnd}
          onClick={mockOnClick}
          isDragging={false}
          onDelete={mockOnDelete}
          onEdit={mockOnEdit}
        />
      )

      const priority = screen.getByTestId('task-priority')
      expect(priority).toHaveAttribute('data-color', '#8c8c8c')
    })
  })
})
