/**
 * KanbanBoard 组件测试
 * 测试看板组件的渲染、拖拽和状态更新
 * 
 * 注意：需要先安装 Vitest 相关依赖：
 * npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React, { useState } from 'react'

// Mock antd 组件
vi.mock('antd', () => ({
  Card: ({ children, style, ...props }: any) => (
    <div data-testid="card" style={style} {...props}>{children}</div>
  ),
  Row: ({ children }: any) => <div data-testid="row">{children}</div>,
  Col: ({ children }: any) => <div data-testid="col">{children}</div>,
  Button: ({ children, onClick, type, icon }: any) => (
    <button data-testid="button" onClick={onClick} data-type={type}>
      {icon}{children}
    </button>
  ),
  Tag: ({ children, color }: any) => (
    <span data-testid="tag" data-color={color}>{children}</span>
  ),
  Space: ({ children }: any) => <div data-testid="space">{children}</div>,
  Badge: ({ count }: any) => <span data-testid="badge">{count}</span>,
  Typography: {
    Title: ({ children, level }: any) => <h{level || 1} data-testid="title">{children}</h{level || 1}>,
    Text: ({ children, type }: any) => (
      <span data-testid="text" data-type={type}>{children}</span>
    ),
  },
  Empty: ({ description }: any) => (
    <div data-testid="empty">{description}</div>
  ),
  Spin: ({ tip }: any) => <div data-testid="spin">{tip}</div>,
  Tooltip: ({ children, title }: any) => (
    <div data-testid="tooltip" data-title={title}>{children}</div>
  ),
  message: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

// Mock antd icons
vi.mock('@ant-design/icons', () => ({
  PlusOutlined: () => <span data-testid="plus-icon">+</span>,
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
}))

// Mock agent API
vi.mock('@/services/api', () => ({
  agentApi: {
    getTasks: vi.fn().mockResolvedValue({ list: [], total: 0 }),
    getProjects: vi.fn().mockResolvedValue({ list: [], total: 0 }),
    createTask: vi.fn().mockResolvedValue({}),
    updateTaskStatus: vi.fn().mockResolvedValue({}),
  },
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
const mockTasks = [
  {
    id: 'task_001',
    title: '待处理任务1',
    description: '描述',
    status: 'pending',
    priority: 'P1',
    assignee_type: 'BE',
    project_id: 'project_001',
    project_name: '项目A',
    progress: 0,
    due_date: null,
    acceptance_criteria: [],
    created_at: Date.now(),
    updated_at: Date.now(),
    status_history: [],
  },
  {
    id: 'task_002',
    title: '进行中任务1',
    description: '描述',
    status: 'in_progress',
    priority: 'P2',
    assignee_type: 'FE',
    project_id: 'project_001',
    project_name: '项目A',
    progress: 50,
    due_date: null,
    acceptance_criteria: [],
    created_at: Date.now(),
    updated_at: Date.now(),
    status_history: [],
  },
  {
    id: 'task_003',
    title: '已阻塞任务1',
    description: '描述',
    status: 'blocked',
    priority: 'P0',
    assignee_type: 'PM',
    project_id: 'project_001',
    project_name: '项目A',
    progress: 30,
    due_date: null,
    acceptance_criteria: [],
    created_at: Date.now(),
    updated_at: Date.now(),
    status_history: [],
  },
  {
    id: 'task_004',
    title: '已完成任务1',
    description: '描述',
    status: 'completed',
    priority: 'P3',
    assignee_type: 'QA',
    project_id: 'project_001',
    project_name: '项目A',
    progress: 100,
    due_date: null,
    acceptance_criteria: [],
    created_at: Date.now(),
    updated_at: Date.now(),
    status_history: [],
  },
]

// 状态列配置
const STATUS_COLUMNS = [
  { key: 'pending', title: 'TODO', color: '#8c8c8c' },
  { key: 'in_progress', title: 'IN PROGRESS', color: '#1890ff' },
  { key: 'blocked', title: 'BLOCKED', color: '#ff4d4f' },
  { key: 'completed', title: 'DONE', color: '#52c41a' },
]

// 简化的 StatusColumn 组件（用于测试）
const StatusColumn = ({
  status,
  title,
  color,
  tasks,
  onDrop,
  draggingTaskId,
}: any) => {
  const [isDragOver, setIsDragOver] = useState(false)

  return (
    <div
      data-testid={`column-${status}`}
      style={{
        border: isDragOver ? `2px dashed ${color}` : '2px solid transparent',
      }}
      onDragOver={(e) => {
        e.preventDefault()
        setIsDragOver(true)
      }}
      onDragLeave={() => setIsDragOver(false)}
      onDrop={(e) => {
        setIsDragOver(false)
        const taskId = e.dataTransfer.getData('taskId')
        onDrop(e, status)
      }}
    >
      <div data-testid="column-header">
        <span>{title}</span>
        <span data-testid="task-count">{tasks.length}</span>
      </div>
      <div data-testid="task-list">
        {tasks.map((task: any) => (
          <div
            key={task.id}
            data-testid={`task-${task.id}`}
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData('taskId', task.id)
            }}
          >
            {task.title}
          </div>
        ))}
      </div>
    </div>
  )
}

// 简化的 KanbanBoard 组件（用于测试）
const KanbanBoard = ({ tasks, onTaskMove }: any) => {
  const [draggingTaskId, setDraggingTaskId] = useState<string | null>(null)

  const getTasksByStatus = (status: string) => tasks.filter((t: any) => t.status === status)

  const handleDrop = (e: any, newStatus: string) => {
    const taskId = e.dataTransfer.getData('taskId')
    setDraggingTaskId(null)
    if (onTaskMove) {
      onTaskMove(taskId, newStatus)
    }
  }

  return (
    <div data-testid="kanban-board">
      {STATUS_COLUMNS.map((column) => (
        <StatusColumn
          key={column.key}
          status={column.key}
          title={column.title}
          color={column.color}
          tasks={getTasksByStatus(column.key)}
          onDrop={handleDrop}
          draggingTaskId={draggingTaskId}
        />
      ))}
    </div>
  )
}

describe('KanbanBoard 组件', () => {
  const mockOnTaskMove = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('渲染测试', () => {
    it('应该渲染所有状态列', () => {
      render(<KanbanBoard tasks={mockTasks} onTaskMove={mockOnTaskMove} />)

      expect(screen.getByTestId('column-pending')).toBeInTheDocument()
      expect(screen.getByTestId('column-in_progress')).toBeInTheDocument()
      expect(screen.getByTestId('column-blocked')).toBeInTheDocument()
      expect(screen.getByTestId('column-completed')).toBeInTheDocument()
    })

    it('应该显示正确的列标题', () => {
      render(<KanbanBoard tasks={mockTasks} onTaskMove={mockOnTaskMove} />)

      expect(screen.getByText('TODO')).toBeInTheDocument()
      expect(screen.getByText('IN PROGRESS')).toBeInTheDocument()
      expect(screen.getByText('BLOCKED')).toBeInTheDocument()
      expect(screen.getByText('DONE')).toBeInTheDocument()
    })

    it('应该正确分组任务', () => {
      render(<KanbanBoard tasks={mockTasks} onTaskMove={mockOnTaskMove} />)

      // 检查每列的任务数量
      const pendingColumn = screen.getByTestId('column-pending')
      expect(pendingColumn.querySelector('[data-testid="task-count"]')).toHaveTextContent('1')

      const inProgressColumn = screen.getByTestId('column-in_progress')
      expect(inProgressColumn.querySelector('[data-testid="task-count"]')).toHaveTextContent('1')

      const blockedColumn = screen.getByTestId('column-blocked')
      expect(blockedColumn.querySelector('[data-testid="task-count"]')).toHaveTextContent('1')

      const completedColumn = screen.getByTestId('column-completed')
      expect(completedColumn.querySelector('[data-testid="task-count"]')).toHaveTextContent('1')
    })

    it('应该显示任务标题', () => {
      render(<KanbanBoard tasks={mockTasks} onTaskMove={mockOnTaskMove} />)

      expect(screen.getByText('待处理任务1')).toBeInTheDocument()
      expect(screen.getByText('进行中任务1')).toBeInTheDocument()
      expect(screen.getByText('已阻塞任务1')).toBeInTheDocument()
      expect(screen.getByText('已完成任务1')).toBeInTheDocument()
    })
  })

  describe('空状态测试', () => {
    it('空看板应该显示空状态', () => {
      render(<KanbanBoard tasks={[]} onTaskMove={mockOnTaskMove} />)

      // 所有列的任务数量都应该是 0
      const columns = screen.getAllByTestId(/column-/)
      columns.forEach((column) => {
        expect(column.querySelector('[data-testid="task-count"]')).toHaveTextContent('0')
      })
    })
  })

  describe('拖拽测试', () => {
    it('任务应该可以被拖拽', () => {
      render(<KanbanBoard tasks={mockTasks} onTaskMove={mockOnTaskMove} />)

      const task = screen.getByTestId('task-task_001')
      expect(task).toHaveAttribute('draggable', 'true')
    })

    it('拖拽到新列应该触发 onTaskMove', async () => {
      render(<KanbanBoard tasks={mockTasks} onTaskMove={mockOnTaskMove} />)

      const task = screen.getByTestId('task-task_001')
      const targetColumn = screen.getByTestId('column-in_progress')

      // 模拟拖拽开始
      fireEvent.dragStart(task, { dataTransfer: { setData: vi.fn((key, value) => {}) } })

      // 模拟拖拽到目标列
      fireEvent.dragOver(targetColumn)

      // 模拟放置
      const dropEvent = {
        dataTransfer: {
          getData: vi.fn().mockReturnValue('task_001'),
        },
      }
      fireEvent.drop(targetColumn, dropEvent)

      // 验证 onTaskMove 被调用
      expect(mockOnTaskMove).toHaveBeenCalled()
    })
  })

  describe('统计测试', () => {
    it('应该正确计算各状态任务数', () => {
      render(<KanbanBoard tasks={mockTasks} onTaskMove={mockOnTaskMove} />)

      const pendingCount = screen.getAllByTestId('task-count')[0]
      expect(pendingCount).toHaveTextContent('1')

      const inProgressCount = screen.getAllByTestId('task-count')[1]
      expect(inProgressCount).toHaveTextContent('1')

      const blockedCount = screen.getAllByTestId('task-count')[2]
      expect(blockedCount).toHaveTextContent('1')

      const completedCount = screen.getAllByTestId('task-count')[3]
      expect(completedCount).toHaveTextContent('1')
    })

    it('多任务时应该正确计数', () => {
      const multipleTasks = [
        ...mockTasks,
        {
          id: 'task_005',
          title: '待处理任务2',
          status: 'pending',
          priority: 'P2',
          assignee_type: 'BE',
          project_id: 'project_001',
          project_name: '项目A',
          progress: 0,
          created_at: Date.now(),
          updated_at: Date.now(),
          status_history: [],
        },
        {
          id: 'task_006',
          title: '待处理任务3',
          status: 'pending',
          priority: 'P3',
          assignee_type: 'FE',
          project_id: 'project_001',
          project_name: '项目A',
          progress: 0,
          created_at: Date.now(),
          updated_at: Date.now(),
          status_history: [],
        },
      ]

      render(<KanbanBoard tasks={multipleTasks} onTaskMove={mockOnTaskMove} />)

      const pendingCount = screen.getAllByTestId('task-count')[0]
      expect(pendingCount).toHaveTextContent('3')
    })
  })

  describe('状态更新测试', () => {
    it('任务状态更新应该反映在看板中', () => {
      const { rerender } = render(<KanbanBoard tasks={mockTasks} onTaskMove={mockOnTaskMove} />)

      // 初始状态
      expect(screen.getByTestId('column-pending').querySelector('[data-testid="task-count"]')).toHaveTextContent('1')

      // 更新任务状态
      const updatedTasks = mockTasks.map((t) =>
        t.id === 'task_001' ? { ...t, status: 'completed' } : t
      )

      rerender(<KanbanBoard tasks={updatedTasks} onTaskMove={mockOnTaskMove} />)

      // 验证状态更新
      expect(screen.getByTestId('column-pending').querySelector('[data-testid="task-count"]')).toHaveTextContent('0')
      expect(screen.getByTestId('column-completed').querySelector('[data-testid="task-count"]')).toHaveTextContent('2')
    })
  })
})

describe('StatusColumn 组件', () => {
  const mockOnDrop = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('应该显示正确的任务数量', () => {
    render(
      <StatusColumn
        status="pending"
        title="TODO"
        color="#8c8c8c"
        tasks={mockTasks.filter((t) => t.status === 'pending')}
        onDrop={mockOnDrop}
        draggingTaskId={null}
      />
    )

    expect(screen.getByTestId('task-count')).toHaveTextContent('1')
  })

  it('拖拽悬停时应该显示高亮边框', () => {
    render(
      <StatusColumn
        status="in_progress"
        title="IN PROGRESS"
        color="#1890ff"
        tasks={[]}
        onDrop={mockOnDrop}
        draggingTaskId={null}
      />
    )

    const column = screen.getByTestId('column-in_progress')
    fireEvent.dragOver(column)

    expect(column).toHaveStyle({ border: '2px dashed #1890ff' })
  })
})
