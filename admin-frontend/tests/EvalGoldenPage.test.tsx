import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import EvalGoldenPage from '@/pages/eval-golden'

// 屏蔽真实网络：mock http 服务
vi.mock('@/services/api', () => ({
  http: {
    get: vi.fn().mockResolvedValue([]),
    post: vi.fn().mockResolvedValue({ overall_score: 80, per_criterion: [], summary: '' }),
    put: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}))

describe('EvalGoldenPage（评测 Golden Cases 管理页）', () => {
  it('挂载并渲染标题与「新建/刷新」按钮（不崩溃）', () => {
    render(<EvalGoldenPage />)
    expect(screen.getByText('评测 Golden Cases')).toBeInTheDocument()
    expect(screen.getByText('新建')).toBeInTheDocument()
    expect(screen.getByText('刷新')).toBeInTheDocument()
  })

  it('渲染表格容器（列头：名称/分类/启用）', async () => {
    render(<EvalGoldenPage />)
    expect(await screen.findByText('名称')).toBeInTheDocument()
    expect(screen.getByText('分类')).toBeInTheDocument()
    expect(screen.getByText('启用')).toBeInTheDocument()
  })
})
