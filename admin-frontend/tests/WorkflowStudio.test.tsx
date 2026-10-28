import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import WorkflowStudio from '@/pages/workflow'

// React Flow 依赖 ResizeObserver / DOMMatrixReadOnly，jsdom 需补桩
beforeAll(() => {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  global.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver
  // @ts-expect-error 仅测试环境的部分实现
  global.DOMMatrixReadOnly = class { }
})

const { REGISTRY, DEF } = vi.hoisted(() => ({
  REGISTRY: [
    { type: 'start', name: '开始', category: '基础', fields: [], supports_branch: false, allow_delete: false },
    { type: 'llm', name: 'LLM 节点', category: '智能体', fields: [], supports_branch: false, allow_delete: true },
    { type: 'condition', name: '条件分支', category: '流程控制', fields: [], supports_branch: true, allow_delete: true },
    { type: 'human_input', name: '人工输入', category: '流程控制', fields: [], supports_branch: true, allow_delete: true },
    { type: 'end', name: '结束', category: '基础', fields: [], supports_branch: false, allow_delete: false },
  ],
  DEF: {
    workflow_id: 'wf_test1', name: '冒烟工作流', description: '', status: 'draft', version: 1,
    dsl: {
      version: 1,
      nodes: [
        { id: 'start', type: 'start', name: '开始', config: {}, position: { x: 0, y: 0 } },
        { id: 'end', type: 'end', name: '结束', config: {}, position: { x: 400, y: 0 } },
      ],
      edges: [{ from: 'start', to: 'end' }],
    },
  },
}))

vi.mock('@/services/api', () => ({
  workflowApi: {
    listNodeTypes: vi.fn().mockResolvedValue(REGISTRY),
    listDefinitions: vi.fn().mockResolvedValue([DEF]),
    getDefinition: vi.fn().mockResolvedValue(DEF),
    createDefinition: vi.fn().mockResolvedValue(DEF),
    updateDefinition: vi.fn().mockResolvedValue(DEF),
    publishDefinition: vi.fn().mockResolvedValue(DEF),
    startRun: vi.fn().mockResolvedValue({ run_id: 'run_1', status: 'running' }),
    getRun: vi.fn().mockResolvedValue({
      run_id: 'run_1', workflow_id: 'wf_test1', status: 'completed',
      inputs: {}, outputs: { end: { summary: {} } }, error: '',
      waiting_node: '', waiting_message: '',
    }),
    resumeRun: vi.fn().mockResolvedValue({ run_id: 'run_1', status: 'running' }),
  },
}))

describe('WorkflowStudio（工作流编排画布）', () => {
  it('渲染标题、节点面板与画布节点', async () => {
    render(<WorkflowStudio />)
    expect(screen.getByText('工作流编排', { selector: '.ant-card-head-title *' })).toBeInTheDocument()
    await waitFor(() => {
      // 左侧面板出现注册表节点类型
      expect(screen.getByText('LLM 节点')).toBeInTheDocument()
      expect(screen.getByText('条件分支')).toBeInTheDocument()
    })
    // 画布上渲染出 DSL 里的开始/结束节点卡片（面板里同名，用 getAll）
    await waitFor(() => {
      expect(screen.getAllByText('开始').length).toBeGreaterThanOrEqual(2)
      expect(screen.getAllByText('结束').length).toBeGreaterThanOrEqual(2)
    })
  })
})
