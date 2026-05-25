import React, { useState, useEffect, useCallback } from 'react'
import {
  Input,
  Button,
  Select,
  Row,
  Col,
  Empty,
  message,
  Pagination,
  Space,
  Drawer,
  Modal,
  Form,
} from 'antd'
import {
  SearchOutlined,
  AppstoreOutlined,
  SortAscendingOutlined,
  FilterOutlined,
  ReloadOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import api from '@/services/api'
import SkillCard from './SkillCard'
import SkillDetail from './SkillDetail'
import RatingModal from './RatingModal'
import skillsMarketApi, { Skill, Category, SkillQueryParams } from '@/services/skills'

const { Option } = Select
const { Search } = Input

// 骨架屏卡片组件
const CardSkeleton: React.FC = () => (
  <div className="skill-card-skeleton">
    <div className="skeleton-header">
      <div className="skeleton-icon"></div>
      <div className="skeleton-tag"></div>
    </div>
    <div className="skeleton-title"></div>
    <div className="skeleton-desc"></div>
    <div className="skeleton-desc short"></div>
    <div className="skeleton-tags">
      <div className="skeleton-tag-item"></div>
      <div className="skeleton-tag-item"></div>
      <div className="skeleton-tag-item"></div>
    </div>
    <div className="skeleton-stats"></div>
    <div className="skeleton-footer"></div>
    <div className="skeleton-btn"></div>
  </div>
)

// 空状态组件
const EmptyState: React.FC<{ onReset: () => void }> = ({ onReset }) => (
  <div className="empty-state">
    <Empty
      image={Empty.PRESENTED_IMAGE_SIMPLE}
      description={
        <span>
          暂无技能数据
          <br />
          <Button type="link" onClick={onReset}>
            重置筛选条件
          </Button>
        </span>
      }
    />
  </div>
)

// 错误状态组件
const ErrorState: React.FC<{ onRetry: () => void }> = ({ onRetry }) => (
  <div className="error-state">
    <Empty
      image={Empty.PRESENTED_IMAGE_SIMPLE}
      description={
        <span>
          加载失败
          <br />
          <Button type="link" onClick={onRetry}>
            点击重试
          </Button>
        </span>
      }
    />
  </div>
)

// 排序选项
const sortOptions = [
  { value: 'newest', label: '最新发布' },
  { value: 'rating', label: '评分最高' },
  { value: 'downloads', label: '下载最多' },
]

const SkillMarketPage: React.FC = () => {
  // 筛选状态
  const [keyword, setKeyword] = useState('')
  const [debouncedKeyword, setDebouncedKeyword] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [sortBy, setSortBy] = useState<string>('newest')

  // 分页状态
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(12)

  // 数据状态
  const [skills, setSkills] = useState<Skill[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [categoriesLoading, setCategoriesLoading] = useState(false)
  const [error, setError] = useState(false)

  // 弹窗状态
  const [detailVisible, setDetailVisible] = useState(false)
  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)
  const [ratingVisible, setRatingVisible] = useState(false)
  const [ratingSkill, setRatingSkill] = useState<Skill | null>(null)

  // 移动端筛选抽屉
  const [filterDrawerVisible, setFilterDrawerVisible] = useState(false)

  // 技能管理
  const [manageVisible, setManageVisible] = useState(false)
  const [manageAction, setManageAction] = useState<'create' | 'edit' | 'delete'>('create')
  const [manageForm] = Form.useForm()
  const [managing, setManaging] = useState(false)

  // 加载分类
  useEffect(() => {
    fetchCategories()
  }, [])

  // 搜索防抖
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedKeyword(keyword)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [keyword])

  // 加载技能列表
  useEffect(() => {
    fetchSkills()
  }, [debouncedKeyword, selectedCategory, sortBy, page, pageSize])

  // 获取分类列表
  const fetchCategories = async () => {
    setCategoriesLoading(true)
    try {
      const result = await skillsMarketApi.getCategories()
      setCategories(result || [])
    } catch (err) {
      console.error('Failed to fetch categories:', err)
    } finally {
      setCategoriesLoading(false)
    }
  }

  // 获取技能列表
  const fetchSkills = async () => {
    setLoading(true)
    setError(false)
    try {
      const params: SkillQueryParams = {
        page,
        pageSize,
        sortBy: sortBy as any,
      }
      if (debouncedKeyword) {
        params.keyword = debouncedKeyword
      }
      if (selectedCategory && selectedCategory !== 'all') {
        params.category = selectedCategory
      }

      const result = await skillsMarketApi.getSkills(params)
      setSkills(result?.list || [])
      setTotal(result?.total || 0)
    } catch (err) {
      console.error('Failed to fetch skills:', err)
      setError(true)
    } finally {
      setLoading(false)
    }
  }

  // 处理技能点击
  const handleSkillClick = useCallback((skill: Skill) => {
    setSelectedSkillId(skill.id)
    setDetailVisible(true)
  }, [])

  // 处理下载
  const handleDownload = useCallback(async (skill: Skill) => {
    try {
      await skillsMarketApi.downloadSkill(skill.id)
      message.success('下载成功')
      // 更新列表中的下载状态
      setSkills(prev =>
        prev.map(s => (s.id === skill.id ? { ...s, isDownloaded: true } : s))
      )
    } catch (err: any) {
      message.error(err?.message || '下载失败')
    }
  }, [])

  // 处理评分
  const handleRate = useCallback((skill: Skill) => {
    setRatingSkill(skill)
    setRatingVisible(true)
  }, [])

  // 评分成功后刷新列表
  const handleRateSuccess = useCallback(() => {
    fetchSkills()
  }, [])

  // 重置筛选
  const handleReset = useCallback(() => {
    setKeyword('')
    setDebouncedKeyword('')
    setSelectedCategory('all')
    setSortBy('newest')
    setPage(1)
  }, [])

  // 渲染筛选栏
  const renderFilters = () => (
    <div className="filter-section">
      <Search
        placeholder="搜索技能名称、描述..."
        allowClear
        value={keyword}
        onChange={(e) => setKeyword(e.target.value)}
        style={{ width: '100%', maxWidth: 320 }}
        prefix={<SearchOutlined />}
      />

      <Space size={12} wrap>
        <Select
          value={selectedCategory}
          onChange={(val) => {
            setSelectedCategory(val)
            setPage(1)
          }}
          style={{ width: 140 }}
          loading={categoriesLoading}
        >
          <Option value="all">全部分类</Option>
          {categories.map((cat) => (
            <Option key={cat.id} value={cat.id}>
              {cat.name} ({cat.count})
            </Option>
          ))}
        </Select>

        <Select
          value={sortBy}
          onChange={(val) => {
            setSortBy(val)
            setPage(1)
          }}
          style={{ width: 130 }}
          suffixIcon={<SortAscendingOutlined />}
        >
          {sortOptions.map((opt) => (
            <Option key={opt.value} value={opt.value}>
              {opt.label}
            </Option>
          ))}
        </Select>

        <Button icon={<ReloadOutlined />} onClick={fetchSkills}>
          刷新
        </Button>

        <Button type="primary" icon={<PlusOutlined />} onClick={() => {
          setManageAction('create')
          manageForm.resetFields()
          setManageVisible(true)
        }}>
          新增技能
        </Button>

        <Button onClick={handleReset}>重置</Button>
      </Space>
    </div>
  )

  // 渲染分类侧边栏
  const renderCategorySidebar = () => (
    <div className="category-sidebar">
      <h3 className="sidebar-title">
        <AppstoreOutlined /> 技能分类
      </h3>
      <div className="category-list">
        <div
          className={`category-item ${selectedCategory === 'all' ? 'active' : ''}`}
          onClick={() => {
            setSelectedCategory('all')
            setPage(1)
          }}
        >
          <span className="category-name">全部分类</span>
          <span className="category-count">{categories.reduce((sum, c) => sum + c.count, 0)}</span>
        </div>
        {categories.map((cat) => (
          <div
            key={cat.id}
            className={`category-item ${selectedCategory === cat.id ? 'active' : ''}`}
            onClick={() => {
              setSelectedCategory(cat.id)
              setPage(1)
            }}
          >
            <span className="category-name">{cat.name}</span>
            <span className="category-count">{cat.count}</span>
          </div>
        ))}
      </div>
    </div>
  )

  // 渲染技能列表
  const renderSkillGrid = () => {
    if (loading) {
      return (
        <Row gutter={[16, 16]}>
          {Array.from({ length: pageSize }).map((_, idx) => (
            <Col key={idx} xs={24} sm={12} lg={8} xl={6}>
              <CardSkeleton />
            </Col>
          ))}
        </Row>
      )
    }

    if (error) {
      return <ErrorState onRetry={fetchSkills} />
    }

    if (skills.length === 0) {
      return <EmptyState onReset={handleReset} />
    }

    return (
      <Row gutter={[16, 16]}>
        {skills.map((skill) => (
          <Col key={skill.id} xs={24} sm={12} lg={8} xl={6}>
            <SkillCard
              skill={skill}
              onClick={handleSkillClick}
              onDownload={handleDownload}
              onEdit={async (skill) => {
                setManageAction('edit')
                manageForm.setFieldsValue({
                  name: skill.id || skill.name,
                  category: skill.category,
                  content: '加载中...',
                })
                setManageVisible(true)
                try {
                  const res = await api.get(`/skills/market/${skill.id}`)
                  const detail = res?.data || res
                  manageForm.setFieldsValue({
                    content: detail.content || detail.instructions || '',
                  })
                } catch {
                  manageForm.setFieldsValue({ content: '' })
                  message.warning('加载技能内容失败')
                }
              }}
              onDelete={(skill) => {
                setManageAction('delete')
                manageForm.setFieldsValue({ name: skill.id || skill.name })
                setManageVisible(true)
              }}
            />
          </Col>
        ))}
      </Row>
    )
  }

  // 渲染分页
  const renderPagination = () => {
    if (loading || error || skills.length === 0) return null

    return (
      <div className="pagination-wrapper">
        <Pagination
          current={page}
          pageSize={pageSize}
          total={total}
          showSizeChanger
          showQuickJumper
          showTotal={(t) => `共 ${t} 个技能`}
          onChange={(p, ps) => {
            setPage(p)
            setPageSize(ps)
          }}
          pageSizeOptions={['12', '24', '48', '96']}
        />
      </div>
    )
  }

  return (
    <div className="skill-market-page">
      {/* 页面头部 */}
      <div className="page-header">
        <h1>技能市场</h1>
        <p>发现和使用社区贡献的高质量技能，提升您的 AI 助手能力</p>
      </div>

      {/* 主体内容 */}
      <div className="page-content">
        {/* 侧边栏 - 桌面端 */}
        <aside className="sidebar-desktop">
          {renderCategorySidebar()}
        </aside>

        {/* 内容区域 */}
        <main className="main-content">
          {/* 筛选栏 */}
          {renderFilters()}

          {/* 移动端分类按钮 */}
          <Button
            className="mobile-filter-btn"
            icon={<FilterOutlined />}
            onClick={() => setFilterDrawerVisible(true)}
          >
            分类筛选
          </Button>

          {/* 技能网格 */}
          {renderSkillGrid()}

          {/* 分页 */}
          {renderPagination()}
        </main>
      </div>

      {/* 移动端筛选抽屉 */}
      <Drawer
        title="分类筛选"
        placement="left"
        open={filterDrawerVisible}
        onClose={() => setFilterDrawerVisible(false)}
        width={280}
      >
        {renderCategorySidebar()}
      </Drawer>

      {/* 技能详情弹窗 */}
      <SkillDetail
        visible={detailVisible}
        skillId={selectedSkillId}
        onClose={() => {
          setDetailVisible(false)
          setSelectedSkillId(null)
        }}
        onDownload={handleDownload}
        onRate={handleRate}
      />

      {/* 评分弹窗 */}
      <RatingModal
        visible={ratingVisible}
        skill={ratingSkill}
        onClose={() => {
          setRatingVisible(false)
          setRatingSkill(null)
        }}
        onSuccess={handleRateSuccess}
      />

      {/* 技能管理弹窗 */}
      <Modal
        title={manageAction === 'create' ? '新增技能' : manageAction === 'edit' ? '编辑技能' : '删除技能'}
        open={manageVisible}
        onCancel={() => setManageVisible(false)}
        onOk={async () => {
          if (manageAction === 'delete') {
            const name = manageForm.getFieldValue('name')
            try {
              await api.post('/skills/manage', { action: 'delete', name })
              message.success('删除成功')
              setManageVisible(false)
              fetchSkills()
              fetchCategories()
            } catch (e: any) {
              message.error(e?.response?.data?.detail || e?.message || '操作失败')
            }
            return
          }
          try {
            const values = await manageForm.validateFields()
            setManaging(true)
            await api.post('/skills/manage', {
              action: manageAction,
              name: values.name,
              content: values.content,
              category: values.category || '通用',
            })
            message.success(manageAction === 'create' ? '创建成功' : '编辑成功')
            setManageVisible(false)
            fetchSkills()
            fetchCategories()
          } catch (e: any) {
            if (e?.response?.data?.detail) {
              message.error(e.response.data.detail)
            }
          } finally {
            setManaging(false)
          }
        }}
        confirmLoading={managing}
        okText={manageAction === 'delete' ? '确认删除' : '保存'}
        okButtonProps={manageAction === 'delete' ? { danger: true } : {}}
        width={640}
        styles={{
          body: {
            background: '#ffffff',
            padding: 20,
            color: '#111827',
          },
        }}
      >
        <Form form={manageForm} layout="vertical">
          <Form.Item name="name" label={<span style={{ color: '#445066' }}>技能名称</span>}
            rules={[{ required: true, message: '请输入技能名称' }]}>
            <Input placeholder="例如：code_review" disabled={manageAction === 'edit'} />
          </Form.Item>
          {manageAction !== 'delete' && (
            <>
              <Form.Item name="category" label={<span style={{ color: '#445066' }}>分类</span>}>
                <Select placeholder="选择分类" allowClear>
                  <Select.Option value="knowledge">knowledge</Select.Option>
                  <Select.Option value="analysis">analysis</Select.Option>
                  <Select.Option value="report">report</Select.Option>
                  <Select.Option value="testing">testing</Select.Option>
                  <Select.Option value="coding">coding</Select.Option>
                  <Select.Option value="通用">通用</Select.Option>
                </Select>
              </Form.Item>
              <Form.Item name="content" label={<span style={{ color: '#445066' }}>技能内容（Markdown/指令）</span>}
                rules={[{ required: true, message: '请输入技能内容' }]}>
                <Input.TextArea rows={12} placeholder="输入技能的完整指令内容..." />
              </Form.Item>
            </>
          )}
          {manageAction === 'delete' && (
            <p style={{ color: '#ff7875' }}>确定要删除此技能吗？删除后无法恢复。</p>
          )}
        </Form>
      </Modal>

      <style>{`
        .skill-market-page {
          padding: 24px;
          min-height: 100vh;
          background: linear-gradient(180deg, #fbfdff 0%, #f6f8fc 100%);
        }
        .page-header {
          margin-bottom: 24px;
        }
        .page-header h1 {
          margin: 0 0 8px 0;
          font-size: 24px;
          font-weight: 600;
          color: #111827;
        }
        .page-header p {
          margin: 0;
          color: #667085;
          font-size: 14px;
        }
        .page-content {
          display: flex;
          gap: 24px;
        }
        .sidebar-desktop {
          width: 240px;
          flex-shrink: 0;
        }
        .main-content {
          flex: 1;
          min-width: 0;
        }
        .filter-section {
          display: flex;
          justify-content: space-between;
          align-items: center;
          flex-wrap: wrap;
          gap: 16px;
          margin-bottom: 24px;
          padding: 16px;
          background: #ffffff;
          border: 1px solid #e5eaf3;
          border-radius: 12px;
        }
        .mobile-filter-btn {
          display: none;
          margin-bottom: 16px;
        }
        .category-sidebar {
          background: #ffffff;
          border: 1px solid #e5eaf3;
          border-radius: 12px;
          padding: 16px;
        }
        .sidebar-title {
          margin: 0 0 16px 0;
          font-size: 16px;
          font-weight: 600;
          color: #111827;
        }
        .category-list {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .category-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 10px 12px;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s;
          color: #445066;
        }
        .category-item:hover {
          background: #f3f6ff;
        }
        .category-item.active {
          background: #edf3ff;
          color: #315cf6;
          border-left: 3px solid #315cf6;
        }
        .category-item.active .category-name {
          font-weight: 500;
        }
        .category-name {
          font-size: 14px;
        }
        .category-count {
          font-size: 12px;
          color: #667085;
        }
        .category-item.active .category-count {
          color: #315cf6;
        }
        .pagination-wrapper {
          display: flex;
          justify-content: center;
          margin-top: 24px;
          padding: 16px;
          background: #ffffff;
          border: 1px solid #e5eaf3;
          border-radius: 12px;
        }
        .empty-state,
        .error-state {
          display: flex;
          justify-content: center;
          align-items: center;
          min-height: 400px;
          background: #ffffff;
          border: 1px solid #e5eaf3;
          border-radius: 12px;
        }

        /* 骨架屏样式 */
        .skill-card-skeleton {
          background: #ffffff;
          border: 1px solid #e5eaf3;
          border-radius: 12px;
          padding: 16px;
          animation: skeleton-loading 1.4s ease infinite;
        }
        .skeleton-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 12px;
        }
        .skeleton-icon {
          width: 48px;
          height: 48px;
          background: #edf1f7;
          border-radius: 8px;
        }
        .skeleton-tag {
          width: 60px;
          height: 22px;
          background: #edf1f7;
          border-radius: 4px;
        }
        .skeleton-title {
          width: 70%;
          height: 20px;
          background: #edf1f7;
          border-radius: 4px;
          margin-bottom: 8px;
        }
        .skeleton-desc {
          width: 100%;
          height: 14px;
          background: #edf1f7;
          border-radius: 4px;
          margin-bottom: 6px;
        }
        .skeleton-desc.short {
          width: 60%;
        }
        .skeleton-tags {
          display: flex;
          gap: 6px;
          margin-bottom: 12px;
        }
        .skeleton-tag-item {
          width: 50px;
          height: 20px;
          background: #edf1f7;
          border-radius: 4px;
        }
        .skeleton-stats {
          height: 40px;
          background: #edf1f7;
          border-radius: 4px;
          margin-bottom: 12px;
        }
        .skeleton-footer {
          height: 20px;
          background: #edf1f7;
          border-radius: 4px;
          margin-bottom: 12px;
        }
        .skeleton-btn {
          height: 32px;
          background: #edf1f7;
          border-radius: 6px;
        }
        @keyframes skeleton-loading {
          0% { opacity: 1; }
          50% { opacity: 0.4; }
          100% { opacity: 1; }
        }

        /* 响应式布局 */
        @media (max-width: 992px) {
          .sidebar-desktop { display: none; }
          .mobile-filter-btn { display: inline-flex; }
          .page-content { flex-direction: column; }
        }
        @media (max-width: 576px) {
          .skill-market-page { padding: 16px; }
          .filter-section { flex-direction: column; align-items: stretch; }
          .filter-section .ant-input-search { max-width: 100% !important; }
        }
      `}</style>
    </div>
  )
}

export default SkillMarketPage
