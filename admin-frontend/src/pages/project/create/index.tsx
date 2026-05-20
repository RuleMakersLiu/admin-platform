import React, { useState, useEffect } from 'react'
import { Steps, Card, Input, Button, Form, Space, Typography, message, Spin, Tag, Modal, Select } from 'antd'
import {
  CodeOutlined, AppstoreOutlined, SettingOutlined, RocketOutlined,
  JavaOutlined, Html5Outlined, CheckCircleOutlined,
  ImportOutlined, BranchesOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { generatorApi, systemApi } from '@/services/api'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

const LANGUAGE_ICONS: Record<string, React.ReactNode> = {
  java: <JavaOutlined />,
  php: <CodeOutlined />,
  node: <CodeOutlined />,
  go: <CodeOutlined />,
  python: <CodeOutlined />,
  javascript: <Html5Outlined />,
}

const LANGUAGE_COLORS: Record<string, string> = {
  java: '#f89820',
  php: '#777BB4',
  node: '#339933',
  go: '#00ADD8',
  python: '#3776AB',
  javascript: '#F7DF1E',
}

interface Template {
  id: number
  name: string
  code: string
  language: string
  framework: string
  description: string
  icon: string
  variables: string
}

interface TemplateVariable {
  name: string
  label: string
  type: string
  default: string
  required: boolean
}

const ProjectCreatePage: React.FC = () => {
  const navigate = useNavigate()
  const [current, setCurrent] = useState(0)
  const [templates, setTemplates] = useState<Template[]>([])
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null)
  const [variables, setVariables] = useState<Record<string, string>>({})
  const [templateVars, setTemplateVars] = useState<TemplateVariable[]>([])
  const [loading, setLoading] = useState(false)
  const [projectName, setProjectName] = useState('')
  const [projectCode, setProjectCode] = useState('')
  const [projectDesc, setProjectDesc] = useState('')
  const [generatedFiles, setGeneratedFiles] = useState<Record<string, string>>({})
  const [previewVisible, setPreviewVisible] = useState(false)
  const [previewFile, setPreviewFile] = useState<{ name: string; content: string } | null>(null)

  // Git import state
  const [importMode, setImportMode] = useState(false)
  const [importUrl, setImportUrl] = useState('')
  const [importBranch, setImportBranch] = useState('main')
  const [importLoading, setImportLoading] = useState(false)
  const [importedProject, setImportedProject] = useState<any>(null)
  const [gitConfigs, setGitConfigs] = useState<any[]>([])
  const [selectedGitConfig, setSelectedGitConfig] = useState<string | undefined>(undefined)

  useEffect(() => {
    generatorApi.getTemplates().then((data: any) => {
      setTemplates(Array.isArray(data) ? data : [])
    }).catch(() => {})
    systemApi.getGitConfigs().then((data: any) => {
      const list = Array.isArray(data) ? data : data?.data?.list || data?.list || []
      setGitConfigs(list)
    }).catch(() => {})
  }, [])

  const handleSelectTemplate = (template: Template) => {
    setSelectedTemplate(template)
    let vars: TemplateVariable[] = []
    try {
      vars = template.variables ? JSON.parse(template.variables) : []
    } catch { /* ignore */ }

    const hidden = ['ProjectName', 'ArtifactId', 'ModuleName']
    const visibleVars = vars.filter(v => !hidden.includes(v.name))
    setTemplateVars(visibleVars)

    const defaults: Record<string, string> = {}
    vars.forEach(v => { defaults[v.name] = v.default })
    setVariables(defaults)
    setCurrent(1)
  }

  const handleCreate = async () => {
    if (!selectedTemplate) return
    if (!projectName.trim()) {
      message.warning('请输入项目名称')
      return
    }

    const finalVars = { ...variables }
    finalVars['ProjectName'] = projectName
    if (selectedTemplate.language === 'java') {
      finalVars['ArtifactId'] = finalVars['ArtifactId'] || projectCode
      const groupId = finalVars['GroupId'] || 'com.example'
      finalVars['PackageName'] = `${groupId}.${projectCode.replace(/-/g, '')}`
      finalVars['PackagePath'] = `${groupId.replace(/\./g, '/')}/${projectCode.replace(/-/g, '')}`
    }
    if (selectedTemplate.language === 'go') {
      finalVars['ModuleName'] = finalVars['ModuleName'] || `github.com/example/${projectCode}`
    }

    setLoading(true)
    try {
      const data: any = await generatorApi.createProject({
        name: projectName,
        code: projectCode || projectName.toLowerCase().replace(/\s+/g, '-'),
        description: projectDesc,
        template_id: selectedTemplate.id,
        variables: finalVars,
      })

      const files = data?.files || {}
      setGeneratedFiles(files)
      setCurrent(2)
      message.success('项目创建成功')
    } catch (e: any) {
      message.error(e?.message || '创建失败')
    } finally {
      setLoading(false)
    }
  }

  const handleImport = async () => {
    if (!projectName.trim()) {
      message.warning('请输入项目名称')
      return
    }
    if (!importUrl.trim()) {
      message.warning('请输入仓库地址')
      return
    }

    setImportLoading(true)
    try {
      const data: any = await generatorApi.importProject({
        name: projectName,
        code: projectCode || projectName.toLowerCase().replace(/\s+/g, '-'),
        description: projectDesc,
        repo_url: importUrl,
        branch: importBranch || 'main',
        git_config_id: selectedGitConfig ? Number(selectedGitConfig) : undefined,
      })

      setImportedProject(data)
      setCurrent(2)
      message.success('项目导入成功')
    } catch (e: any) {
      message.error(e?.message || '导入失败')
    } finally {
      setImportLoading(false)
    }
  }

  const handlePreviewFile = (name: string, content: string) => {
    setPreviewFile({ name, content })
    setPreviewVisible(true)
  }

  const resetForm = () => {
    setCurrent(0)
    setSelectedTemplate(null)
    setGeneratedFiles({})
    setProjectName('')
    setProjectCode('')
    setProjectDesc('')
    setImportUrl('')
    setImportBranch('main')
    setImportedProject(null)
  }

  const steps = [
    { title: '选择方式', icon: <AppstoreOutlined /> },
    { title: '配置项目', icon: <SettingOutlined /> },
    { title: importMode ? '导入完成' : '生成完成', icon: <CheckCircleOutlined /> },
  ]

  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>
      <Steps current={current} items={steps.map(s => ({ title: s.title, icon: s.icon }))} style={{ marginBottom: 32 }} />

      {/* Step 0: 选择方式 */}
      {current === 0 && (
        <div>
          <Title level={4} style={{ textAlign: 'center', marginBottom: 24, color: '#e0e0e0' }}>
            选择项目创建方式
          </Title>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, maxWidth: 800, margin: '0 auto' }}>
            {/* 从模板创建 */}
            <Card
              hoverable
              onClick={() => { setImportMode(false); setCurrent(1) }}
              style={{
                background: 'rgba(15, 15, 25, 0.85)',
                border: '1px solid rgba(0, 212, 255, 0.15)',
                borderRadius: 12,
                textAlign: 'center',
                padding: '24px 0',
              }}
            >
              <AppstoreOutlined style={{ fontSize: 48, color: '#00d4ff', marginBottom: 16 }} />
              <div style={{ fontWeight: 600, fontSize: 18, color: '#e0e0e0', marginBottom: 8 }}>
                从模板创建
              </div>
              <Text style={{ color: '#888' }}>
                选择项目模板，配置参数，自动生成项目代码
              </Text>
            </Card>

            {/* 从 Git 导入 */}
            <Card
              hoverable
              onClick={() => { setImportMode(true); setCurrent(1) }}
              style={{
                background: 'rgba(15, 15, 25, 0.85)',
                border: '1px solid rgba(82, 196, 26, 0.15)',
                borderRadius: 12,
                textAlign: 'center',
                padding: '24px 0',
              }}
            >
              <ImportOutlined style={{ fontSize: 48, color: '#52c41a', marginBottom: 16 }} />
              <div style={{ fontWeight: 600, fontSize: 18, color: '#e0e0e0', marginBottom: 8 }}>
                从 Git 导入
              </div>
              <Text style={{ color: '#888' }}>
                输入 Git 仓库地址，自动识别语言框架，导入已有项目
              </Text>
            </Card>
          </div>
        </div>
      )}

      {/* Step 1a: 模板选择（模板模式） */}
      {current === 1 && !importMode && !selectedTemplate && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
            <Button onClick={() => setCurrent(0)}>返回</Button>
            <Title level={4} style={{ margin: '0 0 0 16', color: '#e0e0e0' }}>选择项目模板</Title>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
            {templates.map(t => (
              <Card
                key={t.id}
                hoverable
                onClick={() => handleSelectTemplate(t)}
                style={{
                  background: 'rgba(15, 15, 25, 0.85)',
                  border: '1px solid rgba(0, 212, 255, 0.15)',
                  borderRadius: 12,
                  cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                  <div style={{
                    width: 40, height: 40, borderRadius: 8,
                    background: `${LANGUAGE_COLORS[t.language] || '#00d4ff'}20`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 20, color: LANGUAGE_COLORS[t.language] || '#00d4ff',
                  }}>
                    {LANGUAGE_ICONS[t.language] || <CodeOutlined />}
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, color: '#e0e0e0' }}>{t.name}</div>
                    <Space size={4}>
                      <Tag color={LANGUAGE_COLORS[t.language]} style={{ margin: 0 }}>{t.language}</Tag>
                      <Tag style={{ margin: 0 }}>{t.framework}</Tag>
                    </Space>
                  </div>
                </div>
                <Paragraph style={{ color: '#888', fontSize: 13, marginBottom: 0 }} ellipsis={{ rows: 2 }}>
                  {t.description}
                </Paragraph>
              </Card>
            ))}
          </div>
          {templates.length === 0 && (
            <div style={{ textAlign: 'center', padding: 60 }}>
              <Spin tip="加载模板中..."><div style={{padding:60,textAlign:"center"}} /></Spin>
            </div>
          )}
        </div>
      )}

      {/* Step 1b: 模板配置（模板模式） */}
      {current === 1 && !importMode && selectedTemplate && (
        <div style={{ maxWidth: 640, margin: '0 auto' }}>
          <Card style={{ background: 'rgba(15, 15, 25, 0.85)', border: '1px solid rgba(0, 212, 255, 0.15)', borderRadius: 12 }}>
            <Title level={4} style={{ color: '#e0e0e0', marginBottom: 24 }}>
              配置项目 - {selectedTemplate.name}
            </Title>

            <Form layout="vertical">
              <Form.Item label={<Text style={{ color: '#aaa' }}>项目名称</Text>} required>
                <Input
                  size="large"
                  placeholder="输入项目名称"
                  value={projectName}
                  onChange={e => {
                    setProjectName(e.target.value)
                    setProjectCode(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))
                  }}
                />
              </Form.Item>

              <Form.Item label={<Text style={{ color: '#aaa' }}>项目编码</Text>}>
                <Input
                  value={projectCode}
                  onChange={e => setProjectCode(e.target.value)}
                  placeholder="project-code"
                />
              </Form.Item>

              <Form.Item label={<Text style={{ color: '#aaa' }}>项目描述</Text>}>
                <TextArea
                  rows={2}
                  value={projectDesc}
                  onChange={e => setProjectDesc(e.target.value)}
                  placeholder="简要描述项目"
                />
              </Form.Item>

              {templateVars.map(v => (
                <Form.Item
                  key={v.name}
                  label={<Text style={{ color: '#aaa' }}>{v.label}</Text>}
                  required={v.required}
                >
                  <Input
                    value={variables[v.name] || ''}
                    onChange={e => setVariables(prev => ({ ...prev, [v.name]: e.target.value }))}
                    placeholder={v.default || v.label}
                  />
                </Form.Item>
              ))}
            </Form>

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24 }}>
              <Button onClick={() => { setSelectedTemplate(null); }}>返回选择模板</Button>
              <Button type="primary" size="large" onClick={handleCreate} loading={loading} icon={<RocketOutlined />}>
                生成项目
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Step 1c: Git 导入配置 */}
      {current === 1 && importMode && (
        <div style={{ maxWidth: 640, margin: '0 auto' }}>
          <Card style={{ background: 'rgba(15, 15, 25, 0.85)', border: '1px solid rgba(82, 196, 26, 0.15)', borderRadius: 12 }}>
            <Title level={4} style={{ color: '#e0e0e0', marginBottom: 16 }}>
              从 Git 导入项目
            </Title>

            <div style={{
              padding: 12, marginBottom: 20, borderRadius: 8,
              background: 'rgba(82, 196, 26, 0.06)',
              border: '1px solid rgba(82, 196, 26, 0.15)',
            }}>
              <Text style={{ color: '#888', fontSize: 13 }}>
                输入 Git 仓库地址，系统将自动克隆代码并识别项目语言和框架。
                请确保已在「系统管理 → Git 配置」中配置了对应平台的 Access Token。
              </Text>
            </div>

            <Form layout="vertical">
              <Form.Item label={<Text style={{ color: '#aaa' }}>项目名称</Text>} required>
                <Input
                  size="large"
                  placeholder="输入项目名称"
                  value={projectName}
                  onChange={e => {
                    setProjectName(e.target.value)
                    setProjectCode(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))
                  }}
                />
              </Form.Item>

              <Form.Item label={<Text style={{ color: '#aaa' }}>项目编码</Text>}>
                <Input
                  value={projectCode}
                  onChange={e => setProjectCode(e.target.value)}
                  placeholder="project-code"
                />
              </Form.Item>

              <Form.Item label={<Text style={{ color: '#aaa' }}>项目描述</Text>}>
                <TextArea
                  rows={2}
                  value={projectDesc}
                  onChange={e => setProjectDesc(e.target.value)}
                  placeholder="简要描述项目"
                />
              </Form.Item>

              <Form.Item label={<Text style={{ color: '#aaa' }}>Git 仓库地址</Text>} required>
                <Input
                  size="large"
                  placeholder="https://gitlab.company.com/group/project.git"
                  value={importUrl}
                  onChange={e => setImportUrl(e.target.value)}
                  prefix={<BranchesOutlined style={{ color: '#666' }} />}
                />
              </Form.Item>

              <Form.Item label={<Text style={{ color: '#aaa' }}>分支</Text>}>
                <Input
                  placeholder="main"
                  value={importBranch}
                  onChange={e => setImportBranch(e.target.value)}
                />
              </Form.Item>

              <Form.Item label={<Text style={{ color: '#aaa' }}>Git 凭证配置</Text>}>
                <Select
                  placeholder="选择 Git 凭证（用于克隆私有仓库）"
                  value={selectedGitConfig}
                  onChange={setSelectedGitConfig}
                  allowClear
                  style={{ width: '100%' }}
                  options={gitConfigs.map((g: any) => ({
                    label: `${g.name} (${g.platform})`,
                    value: String(g.id),
                  }))}
                />
              </Form.Item>
            </Form>

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24 }}>
              <Button onClick={() => setCurrent(0)}>返回</Button>
              <Button
                type="primary"
                size="large"
                onClick={handleImport}
                loading={importLoading}
                icon={<ImportOutlined />}
                style={{ background: '#52c41a', borderColor: '#52c41a' }}
              >
                导入项目
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Step 2: 完成（模板生成） */}
      {current === 2 && !importMode && (
        <div>
          <Card style={{
            background: 'linear-gradient(135deg, rgba(82, 196, 26, 0.08), rgba(0, 212, 255, 0.06))',
            border: '1px solid rgba(82, 196, 26, 0.25)',
            borderRadius: 12, marginBottom: 24,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <CheckCircleOutlined style={{ fontSize: 28, color: '#52c41a' }} />
              <div>
                <Title level={4} style={{ color: '#52c41a', margin: 0 }}>
                  项目生成成功
                </Title>
                <Text style={{ color: '#888' }}>
                  {projectName} — 已生成 {Object.keys(generatedFiles).length} 个文件
                </Text>
              </div>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                <Button type="primary" onClick={() => navigate('/project/list')}>
                  查看项目列表
                </Button>
                <Button onClick={() => navigate('/project/test')}>
                  运行测试
                </Button>
                <Button onClick={resetForm}>
                  继续创建
                </Button>
              </div>
            </div>
          </Card>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
            {Object.entries(generatedFiles).map(([name, content]) => (
              <Card
                key={name}
                size="small"
                hoverable
                onClick={() => handlePreviewFile(name, content)}
                style={{
                  background: 'rgba(15, 15, 25, 0.85)',
                  border: '1px solid rgba(0, 212, 255, 0.1)',
                  borderRadius: 8,
                  cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <CodeOutlined style={{ color: '#00d4ff' }} />
                  <Text code style={{ fontSize: 12 }}>{name}</Text>
                  <Text type="secondary" style={{ fontSize: 11, marginLeft: 'auto' }}>
                    {content.length} chars
                  </Text>
                </div>
              </Card>
            ))}
          </div>

          <Modal
            title={previewFile?.name}
            open={previewVisible}
            onCancel={() => setPreviewVisible(false)}
            width={720}
            footer={null}
            styles={{
              body: { background: '#111', padding: 16, maxHeight: '70vh', overflow: 'auto' },
            }}
          >
            <pre style={{ color: '#e0e0e0', fontSize: 13, whiteSpace: 'pre-wrap', margin: 0 }}>
              {previewFile?.content}
            </pre>
          </Modal>
        </div>
      )}

      {/* Step 2: 完成（Git 导入） */}
      {current === 2 && importMode && importedProject && (
        <div>
          <Card style={{
            background: 'linear-gradient(135deg, rgba(82, 196, 26, 0.08), rgba(0, 212, 255, 0.06))',
            border: '1px solid rgba(82, 196, 26, 0.25)',
            borderRadius: 12, marginBottom: 24,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <CheckCircleOutlined style={{ fontSize: 28, color: '#52c41a' }} />
              <div>
                <Title level={4} style={{ color: '#52c41a', margin: 0 }}>
                  项目导入成功
                </Title>
                <Text style={{ color: '#888' }}>
                  {importedProject.name} — 已从 Git 仓库导入
                </Text>
              </div>
            </div>
          </Card>

          <Card style={{
            background: 'rgba(15, 15, 25, 0.85)',
            border: '1px solid rgba(0, 212, 255, 0.15)',
            borderRadius: 12, marginBottom: 24,
          }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div>
                <Text type="secondary">项目名称</Text>
                <div style={{ color: '#e0e0e0', fontWeight: 600 }}>{importedProject.name}</div>
              </div>
              <div>
                <Text type="secondary">项目编码</Text>
                <div style={{ color: '#e0e0e0' }}>{importedProject.code}</div>
              </div>
              <div>
                <Text type="secondary">语言</Text>
                <div>
                  <Tag color={LANGUAGE_COLORS[importedProject.language]}>{importedProject.language}</Tag>
                </div>
              </div>
              <div>
                <Text type="secondary">框架</Text>
                <div><Tag>{importedProject.framework}</Tag></div>
              </div>
              <div>
                <Text type="secondary">Git 仓库</Text>
                <div style={{ color: '#e0e0e0', fontSize: 13, wordBreak: 'break-all' }}>
                  <BranchesOutlined style={{ color: '#52c41a', marginRight: 4 }} />
                  {importedProject.repo_url}
                </div>
              </div>
              <div>
                <Text type="secondary">分支</Text>
                <div><Tag>{importedProject.branch}</Tag></div>
              </div>
            </div>
          </Card>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
            <Button type="primary" onClick={() => navigate('/project/list')}>
              查看项目列表
            </Button>
            <Button onClick={() => navigate(`/project/test?project_id=${importedProject.id}`)}>
              运行测试
            </Button>
            <Button onClick={resetForm}>
              继续创建
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

export default ProjectCreatePage
