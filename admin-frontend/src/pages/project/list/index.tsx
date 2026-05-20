import React, { useState, useEffect } from 'react'
import { Table, Tag, Button, Space, Modal, Typography, message, Tooltip, Progress, Card, Input, Form } from 'antd'
import {
  DeleteOutlined, EyeOutlined, ReloadOutlined, DownloadOutlined,
  BugOutlined, PlusOutlined, LinkOutlined, BranchesOutlined,
  BulbOutlined, CheckCircleOutlined, LoadingOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { generatorApi } from '@/services/api'
import api from '@/services/api'

const { Text } = Typography

const LANGUAGE_COLORS: Record<string, string> = {
  java: '#f89820', php: '#777BB4', node: '#339933',
  go: '#00ADD8', python: '#3776AB', javascript: '#F7DF1E',
}

const ProjectListPage: React.FC = () => {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [previewVisible, setPreviewVisible] = useState(false)
  const [previewFiles, setPreviewFiles] = useState<any[]>([])
  const [repoModalVisible, setRepoModalVisible] = useState(false)
  const [editingProject, setEditingProject] = useState<any>(null)
  const [repoForm] = Form.useForm()
  const [knowledgeMap, setKnowledgeMap] = useState<Record<number, string>>({})
  const [analyzingIds, setAnalyzingIds] = useState<Set<number>>(new Set())

  const fetchProjects = async (p = page) => {
    setLoading(true)
    try {
      const data: any = await generatorApi.getProjects({ page: p, page_size: 10 })
      setProjects(data?.list || [])
      setTotal(data?.total || 0)
    } catch { /* ignore */ }
    setLoading(false)
  }

  useEffect(() => { fetchProjects() }, [page])

  // 加载项目知识库状态
  const loadKnowledge = async (projectIds: number[]) => {
    const map: Record<number, string> = {}
    await Promise.all(projectIds.map(async (id) => {
      try {
        const res: any = await api.get(`/flow/projects/${id}/knowledge`)
        const d = res?.data
        if (d && d.analysis_status === 'done') map[id] = 'done'
        else if (d && d.analysis_status === 'analyzing') map[id] = 'analyzing'
        else map[id] = 'none'
      } catch { map[id] = 'none' }
    }))
    setKnowledgeMap(map)
  }

  useEffect(() => {
    if (projects.length > 0) loadKnowledge(projects.map((p: any) => p.id))
  }, [projects])

  const handleAnalyze = async (id: number) => {
    setAnalyzingIds(prev => new Set(prev).add(id))
    try {
      await api.post(`/flow/projects/${id}/analyze`)
      message.success('分析已启动，后台执行中')
      setTimeout(() => loadKnowledge([id]), 10000)
    } catch (e: any) {
      message.error(e?.message || '分析失败')
    } finally {
      setAnalyzingIds(prev => { const s = new Set(prev); s.delete(id); return s })
    }
  }

  const handleDelete = async (id: number) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除此项目吗？',
      okType: 'danger',
      onOk: async () => {
        try {
          await generatorApi.deleteProject(id)
          message.success('删除成功')
          fetchProjects()
        } catch (e: any) {
          message.error(e?.message || '删除失败')
        }
      },
    })
  }

  const handlePreview = async (id: number) => {
    try {
      const data: any = await generatorApi.previewProject(id)
      setPreviewFiles(data?.files || [])
      setPreviewVisible(true)
    } catch (e: any) {
      message.error(e?.message || '预览失败')
    }
  }

  const handleRegenerate = async (id: number) => {
    try {
      await generatorApi.regenerateProject(id)
      message.success('重新生成成功')
    } catch (e: any) {
      message.error(e?.message || '重新生成失败')
    }
  }

  const handleSetRepo = (record: any) => {
    setEditingProject(record)
    repoForm.setFieldsValue({
      repo_url: record.repo_url || '',
      branch: record.branch || 'main',
    })
    setRepoModalVisible(true)
  }

  const handleSaveRepo = async () => {
    if (!editingProject) return
    try {
      const values = await repoForm.validateFields()
      await generatorApi.updateProject(editingProject.id, values)
      message.success('仓库配置已保存')
      setRepoModalVisible(false)
      fetchProjects()
    } catch (e: any) {
      message.error(e?.message || '保存失败')
    }
  }

  const columns = [
    {
      title: '项目名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: any) => (
        <div>
          <div style={{ fontWeight: 600, color: '#e0e0e0' }}>{name}</div>
          <Text type="secondary" style={{ fontSize: 12 }}>{record.code}</Text>
        </div>
      ),
    },
    {
      title: '语言/框架',
      key: 'tech',
      render: (_: any, record: any) => {
        const lang = record.language && record.language !== 'unknown' ? record.language : ''
        const fw = record.framework && record.framework !== 'unknown' ? record.framework : ''
        if (!lang && !fw) return <Text type="secondary">未识别</Text>
        return (
          <Space>
            {lang && <Tag color={LANGUAGE_COLORS[lang]}>{lang}</Tag>}
            {fw && <Tag>{fw}</Tag>}
          </Space>
        )
      },
    },
    {
      title: 'Git 仓库',
      key: 'repo',
      render: (_: any, record: any) => {
        if (!record.repo_url) {
          return (
            <Button size="small" type="dashed" icon={<LinkOutlined />}
              onClick={() => handleSetRepo(record)}
              style={{ borderColor: 'rgba(250, 173, 20, 0.4)', color: '#faad14' }}
            >
              关联仓库
            </Button>
          )
        }
        return (
          <Tooltip title={`${record.repo_url} (${record.branch || 'main'})`}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}
              onClick={() => handleSetRepo(record)}>
              <BranchesOutlined style={{ color: '#52c41a', fontSize: 13 }} />
              <Text style={{ fontSize: 12, maxWidth: 180 }} ellipsis>
                {record.repo_url.replace(/^https?:\/\//, '')}
              </Text>
              <Tag style={{ fontSize: 11, margin: 0 }}>{record.branch || 'main'}</Tag>
            </div>
          </Tooltip>
        )
      },
    },
    {
      title: '测试通过率',
      key: 'test',
      render: (_: any, record: any) => {
        const rate = record.test_pass_rate
        if (rate == null) return <Text type="secondary">未测试</Text>
        const pct = Math.round(rate)
        return (
          <Tooltip title={`通过率 ${pct}%`}>
            <Progress
              percent={pct}
              size="small"
              status={pct >= 80 ? 'success' : pct >= 50 ? 'normal' : 'exception'}
              style={{ width: 100 }}
            />
          </Tooltip>
        )
      },
    },
    {
      title: '知识库',
      key: 'knowledge',
      width: 100,
      render: (_: any, record: any) => {
        const status = knowledgeMap[record.id]
        if (analyzingIds.has(record.id) || status === 'analyzing') {
          return <Tag icon={<LoadingOutlined spin />} color="processing">分析中</Tag>
        }
        if (status === 'done') {
          return <Tag icon={<CheckCircleOutlined />} color="success">已分析</Tag>
        }
        return (
          <Button size="small" icon={<BulbOutlined />} onClick={() => handleAnalyze(record.id)}>
            分析
          </Button>
        )
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_: any, record: any) => (
        <Space size={4}>
          <Tooltip title="下载代码">
            <Button size="small" icon={<DownloadOutlined />} onClick={() => generatorApi.downloadProject(record.id)} />
          </Tooltip>
          <Tooltip title="预览代码">
            <Button size="small" icon={<EyeOutlined />} onClick={() => handlePreview(record.id)} />
          </Tooltip>
          <Tooltip title="运行测试">
            <Button size="small" type={record.repo_url ? 'primary' : 'default'}
              icon={<BugOutlined />}
              disabled={!record.repo_url}
              onClick={() => navigate(`/project/test?project_id=${record.id}`)}
            />
          </Tooltip>
          <Tooltip title="关联仓库">
            <Button size="small" icon={<LinkOutlined />} onClick={() => handleSetRepo(record)} />
          </Tooltip>
          <Tooltip title="删除">
            <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record.id)} />
          </Tooltip>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0, color: '#e0e0e0' }}>项目列表</Typography.Title>
        <Space>
          <Button icon={<PlusOutlined />} type="primary" onClick={() => navigate('/project/create')}>
            创建项目
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => fetchProjects()}>
            刷新
          </Button>
        </Space>
      </div>

      <Card style={{
        background: 'rgba(15, 15, 25, 0.7)',
        border: '1px solid rgba(0, 212, 255, 0.15)',
        borderRadius: 12,
      }}>
        <Table
          dataSource={projects}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 10,
            onChange: setPage,
            showTotal: t => `共 ${t} 个项目`,
          }}
        />
      </Card>

      {/* 预览文件 */}
      <Modal
        title="项目文件预览"
        open={previewVisible}
        onCancel={() => setPreviewVisible(false)}
        width={720}
        footer={null}
        styles={{
          body: { background: '#111', padding: 16, maxHeight: '70vh', overflow: 'auto' },
        }}
      >
        {previewFiles.map((f: any) => (
          <div key={f.name} style={{ marginBottom: 16 }}>
            <div style={{ color: '#00d4ff', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
              {f.name}
            </div>
            <pre style={{
              color: '#e0e0e0', fontSize: 12, whiteSpace: 'pre-wrap',
              background: '#0a0a12', padding: 12, borderRadius: 8, margin: 0,
            }}>
              {f.content}
            </pre>
          </div>
        ))}
      </Modal>

      {/* 关联仓库 */}
      <Modal
        title="关联 Git 仓库"
        open={repoModalVisible}
        onCancel={() => setRepoModalVisible(false)}
        onOk={handleSaveRepo}
        okText="保存"
        width={560}
      >
        <div style={{ marginBottom: 16, padding: 12, background: 'rgba(0, 212, 255, 0.06)', borderRadius: 8, border: '1px solid rgba(0, 212, 255, 0.1)' }}>
          <Text style={{ color: '#888', fontSize: 13 }}>
            关联仓库后，平台可以从 GitLab 拉取代码并在独立沙箱中运行自动化测试。
            请确保已在「系统管理 → Git 配置」中配置了对应平台的 Access Token。
          </Text>
        </div>
        <Form form={repoForm} layout="vertical">
          <Form.Item name="repo_url" label="仓库地址"
            rules={[{ required: true, message: '请输入仓库地址' }]}
          >
            <Input placeholder="https://gitlab.company.com/group/project.git" />
          </Form.Item>
          <Form.Item name="branch" label="分支"
            rules={[{ required: true, message: '请输入分支名' }]}
          >
            <Input placeholder="main" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default ProjectListPage
