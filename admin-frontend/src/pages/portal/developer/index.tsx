import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Form, Input, Select, Space, Spin, Table, Tag, Typography, message } from 'antd'
import { BranchesOutlined, CheckCircleOutlined, ImportOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import { generatorApi, systemApi } from '@/services/api'
import { pipelineApi, type ProjectSkill } from '@/services/pipeline'
import { saveLastPortalPath, useAuthStore } from '@/stores/auth'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

const skillStatusColor: Record<string, string> = {
  analyzing: 'processing',
  draft: 'warning',
  confirmed: 'success',
  failed: 'error',
}

const normalizeProjects = (data: any) => {
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.list)) return data.list
  if (Array.isArray(data?.items)) return data.items
  if (Array.isArray(data?.records)) return data.records
  if (Array.isArray(data?.data?.list)) return data.data.list
  if (Array.isArray(data?.data?.records)) return data.data.records
  return []
}

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

export default function DeveloperPortal() {
  const [form] = Form.useForm()
  const { user } = useAuthStore()
  const [projects, setProjects] = useState<any[]>([])
  const [gitConfigs, setGitConfigs] = useState<any[]>([])
  const [selectedProject, setSelectedProject] = useState<any>(null)
  const [skill, setSkill] = useState<ProjectSkill | null>(null)
  const [loadingProjects, setLoadingProjects] = useState(false)
  const [importing, setImporting] = useState(false)
  const [skillLoading, setSkillLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const loadProjects = async () => {
    setLoadingProjects(true)
    try {
      const data = await generatorApi.getProjects()
      setProjects(normalizeProjects(data))
    } finally {
      setLoadingProjects(false)
    }
  }

  const loadSkill = async (projectId: string | number) => {
    setSkillLoading(true)
    try {
      const data = await pipelineApi.getProjectSkill(projectId)
      setSkill(data)
      return data
    } finally {
      setSkillLoading(false)
    }
  }

  const pollSkill = async (projectId: string | number) => {
    for (let i = 0; i < 24; i += 1) {
      await sleep(2500)
      const next = await loadSkill(projectId)
      if (next && ['draft', 'confirmed', 'failed'].includes(next.skill_status)) return
    }
  }

  useEffect(() => {
    loadProjects().catch(() => undefined)
    systemApi.getGitConfigs()
      .then((data: any) => {
        const list = Array.isArray(data) ? data : data?.list || data?.data?.list || []
        setGitConfigs(list)
      })
      .catch(() => setGitConfigs([]))
  }, [])

  useEffect(() => {
    saveLastPortalPath(user, '/project/access')
  }, [user])

  const selectedProjectId = useMemo(
    () => selectedProject?.id || selectedProject?.project_id,
    [selectedProject],
  )

  const handleImport = async () => {
    const values = await form.validateFields()
    setImporting(true)
    try {
      const data: any = await generatorApi.importProject({
        name: values.name,
        code: values.code,
        description: values.description,
        repo_url: values.repo_url,
        branch: values.branch || 'main',
        git_config_id: values.git_config_id,
      })
      const project = data?.project || data
      const projectId = project?.id || project?.project_id
      if (!projectId) throw new Error('项目已导入，但返回结果缺少 project_id')

      setSelectedProject(project)
      setSkill({
        project_id: Number(projectId),
        project_name: project.name || values.name,
        repo_url: values.repo_url,
        language: project.language || '',
        framework: project.framework || '',
        project_brief: values.description || '',
        skill_content: '',
        skill_status: 'analyzing',
        skill_version: 1,
        analysis_status: 'analyzing',
      })
      message.success('项目导入成功，已开始分析')
      await pipelineApi.analyzeProject(projectId)
      loadProjects().catch(() => undefined)
      await pollSkill(projectId)
    } catch (error: any) {
      message.error(error?.message || '项目导入失败')
    } finally {
      setImporting(false)
    }
  }

  const handleProjectSelect = async (project: any) => {
    setSelectedProject(project)
    const projectId = project.id || project.project_id
    if (!projectId) return
    await loadSkill(projectId)
  }

  const handleAnalyze = async () => {
    if (!selectedProjectId) return
    setSkill((prev) => prev ? { ...prev, skill_status: 'analyzing', analysis_status: 'analyzing' } : prev)
    await pipelineApi.analyzeProject(selectedProjectId)
    message.success('已重新触发项目分析')
    await pollSkill(selectedProjectId)
  }

  const handleSave = async () => {
    if (!selectedProjectId || !skill) return
    setSaving(true)
    try {
      const next = await pipelineApi.updateProjectSkill(selectedProjectId, {
        project_brief: skill.project_brief,
        skill_content: skill.skill_content,
      })
      setSkill(next)
      message.success('项目 Skill 已保存为草稿')
    } catch (error: any) {
      message.error(error?.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleConfirm = async () => {
    if (!selectedProjectId) return
    const next = await pipelineApi.confirmProjectSkill(selectedProjectId)
    setSkill(next)
    message.success('项目 Skill 已确认，产品门户现在可以使用')
  }

  return (
    <div className="workbench-page">
      <Space align="start" className="workbench-title-row workbench-title-row-between">
        <div>
          <Title level={3} style={{ margin: 0 }}>项目接入</Title>
          <Text type="secondary">导入项目后自动解析源码，生成项目级上下文 Skill，确认后开放给产品流水线。</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => loadProjects()}>刷新项目</Button>
      </Space>

      <div className="workbench-grid">
        <div className="workbench-card" style={{ background: '#fff', border: '1px solid #e5eaf3', borderRadius: 8, padding: 20 }}>
          <Title level={4}>导入 Git 项目</Title>
          <Form form={form} layout="vertical" initialValues={{ branch: 'main' }}>
            <Form.Item name="name" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
              <Input placeholder="例如 Admin Portal" />
            </Form.Item>
            <Form.Item name="code" label="项目编码" rules={[{ required: true, message: '请输入项目编码' }]}>
              <Input placeholder="例如 admin-portal" />
            </Form.Item>
            <Form.Item name="description" label="项目简介" rules={[{ required: true, message: '请输入项目简介' }]}>
              <TextArea rows={4} placeholder="描述业务场景、目标用户、现有模块和开发约束" />
            </Form.Item>
            <Form.Item name="repo_url" label="Git 仓库地址" rules={[{ required: true, message: '请输入 Git 仓库地址' }]}>
              <Input prefix={<BranchesOutlined />} placeholder="https://git.example.com/team/project.git" />
            </Form.Item>
            <Form.Item name="branch" label="分支">
              <Input placeholder="main" />
            </Form.Item>
            <Form.Item name="git_config_id" label="Git 凭证">
              <Select
                allowClear
                placeholder="公开仓库可不选"
                options={gitConfigs.map((item) => ({ label: item.name || item.config_name || item.id, value: item.id }))}
              />
            </Form.Item>
            <Button type="primary" block icon={<ImportOutlined />} loading={importing} onClick={handleImport}>
              导入并生成项目 Skill
            </Button>
          </Form>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="workbench-card" style={{ background: '#fff', border: '1px solid #e5eaf3', borderRadius: 8, padding: 20 }}>
            <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 12 }}>
              <Title level={4} style={{ margin: 0 }}>已接入项目</Title>
              <Text type="secondary">{projects.length} 个项目</Text>
            </Space>
            <Table
              size="small"
              rowKey={(row) => String(row.id || row.project_id || row.code)}
              loading={loadingProjects}
              dataSource={projects}
              pagination={{ pageSize: 5 }}
              onRow={(record) => ({ onClick: () => handleProjectSelect(record) })}
              columns={[
                { title: '名称', dataIndex: 'name', render: (value, row: any) => value || row.project_name },
                { title: '编码', dataIndex: 'code', width: 150 },
                { title: '框架', dataIndex: 'framework', width: 130, render: (value) => value || '-' },
              ]}
            />
          </div>

          <div className="workbench-card" style={{ background: '#fff', border: '1px solid #e5eaf3', borderRadius: 8, padding: 20, minHeight: 420 }}>
            {!selectedProject && <Alert type="info" showIcon message="选择或导入一个项目后，可查看并确认项目级 Skill。" />}
            {selectedProject && (
              <Spin spinning={skillLoading}>
                <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 12 }} align="start">
                  <div>
                    <Title level={4} style={{ margin: 0 }}>{selectedProject.name || selectedProject.project_name}</Title>
                    <Paragraph type="secondary" style={{ marginBottom: 0 }}>{selectedProject.description || skill?.project_brief}</Paragraph>
                  </div>
                  <Space>
                    <Tag color={skillStatusColor[skill?.skill_status || ''] || 'default'}>{skill?.skill_status || 'unavailable'}</Tag>
                    <Button onClick={handleAnalyze}>重新分析</Button>
                  </Space>
                </Space>

                {skill?.analysis_error && (
                  <Alert type="error" showIcon message="项目分析失败" description={skill.analysis_error} style={{ marginBottom: 12 }} />
                )}

                <Text strong>项目简介</Text>
                <TextArea
                  rows={3}
                  value={skill?.project_brief || ''}
                  onChange={(event) => setSkill((prev) => prev ? { ...prev, project_brief: event.target.value } : prev)}
                  style={{ marginTop: 8, marginBottom: 12 }}
                />

                <Text strong>项目级 Skill Markdown</Text>
                <TextArea
                  rows={16}
                  value={skill?.skill_content || ''}
                  onChange={(event) => setSkill((prev) => prev ? { ...prev, skill_content: event.target.value } : prev)}
                  placeholder="等待分析生成项目级 Skill"
                  style={{ marginTop: 8, fontFamily: 'monospace' }}
                />

                <Space style={{ marginTop: 16 }}>
                  <Button icon={<SaveOutlined />} loading={saving} disabled={!skill?.skill_content} onClick={handleSave}>保存草稿</Button>
                  <Button type="primary" icon={<CheckCircleOutlined />} disabled={!skill?.skill_content || skill.skill_status === 'confirmed'} onClick={handleConfirm}>
                    确认启用
                  </Button>
                </Space>
              </Spin>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
