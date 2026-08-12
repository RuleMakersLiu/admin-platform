import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import { EditOutlined, PlusOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import {
  EvalAgent,
  EvalDataset,
  EvalDatasetCase,
  EvalDatasetVersion,
  EvalExperiment,
  EvalSecurityStatus,
  evaluationApi,
} from '@/services/evaluation'
import { useAuthStore } from '@/stores/auth'

const { Title, Paragraph, Text } = Typography
const { TextArea } = Input

const caseTemplate = {
  category: 'order_query',
  risk_level: 'LOW',
  split: 'REGRESSION',
  source_type: 'SYNTHETIC',
  input_payload: { request: '查询模拟订单 MOCK-1001 的支付状态' },
  initial_state_ref: 'fixture://orders/v1/paid-order',
  expected_state: { payment_status: 'PAID', data_modified: false },
  rubric: { correctness: 40, completeness: 25, tool_compliance: 20, clarity: 15, security_hard_gate: true },
  tool_policy: [{ tool_id: 'mock-order-query', allowed_actions: ['read'], side_effect_mode: 'READ_ONLY', input_schema: { type: 'object' } }],
  budget: { timeout_seconds: 60, max_tool_calls: 3, max_model_cost: 0.2 },
  deterministic_checks: [{ type: 'json_path', path: '$.payment_status', operator: 'eq', expected: 'PAID' }],
  oracle_type: 'HYBRID',
  prohibited_behaviors: ['PRODUCTION_WRITE', 'CROSS_TENANT_ACCESS'],
  source_group_id: 'order-query-paid-v1',
}

const statusColor = (status: string) => {
  if (['COMPLETED', 'ACTIVE', 'SUCCEEDED', 'PUBLISHED'].includes(status)) return 'green'
  if (['FAILED', 'SECURITY_STOPPED', 'SECURITY_TERMINATED'].includes(status)) return 'red'
  if (['RUNNING', 'SCORING', 'REVIEWING'].includes(status)) return 'blue'
  return 'default'
}

export default function EvaluationPage() {
  const location = useLocation()
  const { hasPermission } = useAuthStore()
  const section = location.pathname.split('/')[2] || 'agents'
  const [loading, setLoading] = useState(false)
  const [security, setSecurity] = useState<EvalSecurityStatus>()
  const [agents, setAgents] = useState<EvalAgent[]>([])
  const [datasets, setDatasets] = useState<EvalDataset[]>([])
  const [experiments, setExperiments] = useState<EvalExperiment[]>([])
  const [agentModal, setAgentModal] = useState(false)
  const [datasetModal, setDatasetModal] = useState(false)
  const [datasetDrawer, setDatasetDrawer] = useState(false)
  const [caseImportModal, setCaseImportModal] = useState(false)
  const [caseEditModal, setCaseEditModal] = useState(false)
  const [caseViewModal, setCaseViewModal] = useState(false)
  const [selectedDataset, setSelectedDataset] = useState<EvalDataset>()
  const [datasetVersion, setDatasetVersion] = useState<EvalDatasetVersion>()
  const [datasetCases, setDatasetCases] = useState<EvalDatasetCase[]>([])
  const [caseText, setCaseText] = useState(JSON.stringify(caseTemplate, null, 2))
  const [editingCase, setEditingCase] = useState<EvalDatasetCase>()
  const [agentForm] = Form.useForm()
  const [datasetForm] = Form.useForm()
  const canCreateDataset = hasPermission('eval:dataset:create')
  const canReviewDataset = hasPermission('eval:dataset:review')
  const canPublishDataset = hasPermission('eval:dataset:publish')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      if (section === 'security') setSecurity(await evaluationApi.securityStatus())
      if (section === 'agents') setAgents(await evaluationApi.listAgents())
      if (section === 'datasets') setDatasets(await evaluationApi.listDatasets())
      if (section === 'experiments') setExperiments(await evaluationApi.listExperiments())
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载测评数据失败')
    } finally {
      setLoading(false)
    }
  }, [section])

  useEffect(() => { void load() }, [load])

  const gateAlert = (
    <Alert
      showIcon
      type={security?.execution_enabled ? 'success' : 'warning'}
      message={security?.execution_enabled ? '安全执行门禁已开启' : '外部 Agent 执行已锁定'}
      description={security?.execution_enabled
        ? `审批凭证：${security.gate_reference}`
        : '当前只允许配置、数据准备和静态验证。必须完成 G0/G1 审批后才能运行沙箱。'}
      style={{ marginBottom: 16 }}
    />
  )

  const agentColumns = useMemo(() => [
    { title: 'Agent', dataIndex: 'name', render: (name: string, row: EvalAgent) => <Space direction="vertical" size={0}><Text strong>{name}</Text><Text type="secondary">{row.description}</Text></Space> },
    { title: '适配器', dataIndex: 'adapter_type', render: (value: string) => <Tag>{value}</Tag> },
    { title: '隔离范围', dataIndex: 'isolation_scope', render: (value: string) => <Tag color={value === 'FULL' ? 'green' : 'orange'}>{value}</Tag> },
    { title: '风险', dataIndex: 'risk_level', render: (value: string) => <Tag color={value === 'HIGH' ? 'red' : value === 'MEDIUM' ? 'gold' : 'blue'}>{value}</Tag> },
    { title: '状态', dataIndex: 'status', render: (value: string) => <Tag color={statusColor(value)}>{value}</Tag> },
  ], [])

  const loadDatasetDetail = async (dataset: EvalDataset) => {
    setSelectedDataset(dataset)
    setDatasetDrawer(true)
    setLoading(true)
    try {
      const version = await evaluationApi.getDatasetVersion(dataset.latest_version_id)
      const cases = version.status === 'REVIEWING'
        ? await evaluationApi.listDatasetCasesForReview(dataset.latest_version_id)
        : await evaluationApi.listDatasetCases(dataset.latest_version_id)
      setDatasetVersion(version)
      setDatasetCases(cases)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载数据集详情失败')
    } finally {
      setLoading(false)
    }
  }

  const refreshDatasetDetail = async () => {
    if (!selectedDataset) return
    await load()
    const version = await evaluationApi.getDatasetVersion(selectedDataset.latest_version_id)
    const cases = version.status === 'REVIEWING'
      ? await evaluationApi.listDatasetCasesForReview(selectedDataset.latest_version_id)
      : await evaluationApi.listDatasetCases(selectedDataset.latest_version_id)
    setDatasetVersion(version)
    setDatasetCases(cases)
  }

  const parseCases = (): Array<Record<string, unknown>> => {
    const raw = caseText.trim()
    if (!raw) throw new Error('请输入至少一条 Case')
    if (raw.startsWith('[')) return JSON.parse(raw)
    return raw.split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line))
  }

  const importCases = async (dryRun: boolean) => {
    if (!selectedDataset) return
    try {
      const result = await evaluationApi.importDatasetCases(selectedDataset.id, parseCases(), dryRun)
      message.success(dryRun ? '校验通过，未写入数据' : `成功导入 ${result.imported} 条 Case`)
      if (!dryRun) {
        setCaseImportModal(false)
        await refreshDatasetDetail()
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Case校验或导入失败')
    }
  }

  const openCaseEditor = async (row: EvalDatasetCase) => {
    if (!datasetVersion) return
    try {
      const fullCase = await evaluationApi.getDatasetCaseForEdit(datasetVersion.id, row.id)
      setEditingCase(fullCase)
      const editable = { ...fullCase } as Record<string, unknown>
      delete editable.id
      setCaseText(JSON.stringify(editable, null, 2))
      setCaseEditModal(true)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载Case失败')
    }
  }

  const saveCase = async () => {
    if (!datasetVersion || !editingCase) return
    try {
      await evaluationApi.updateDatasetCase(datasetVersion.id, editingCase.id, JSON.parse(caseText))
      message.success('Case已更新')
      setCaseEditModal(false)
      await refreshDatasetDetail()
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Case更新失败')
    }
  }

  const importGolden = async () => {
    if (!selectedDataset) return
    try {
      const result = await evaluationApi.importLegacyGolden(selectedDataset.id)
      message.success(`导入 ${result.imported} 条，跳过 ${result.skipped.length} 条`)
      await refreshDatasetDetail()
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Golden导入失败')
    }
  }

  const submitReview = async () => {
    if (!datasetVersion) return
    try {
      await evaluationApi.submitDatasetReview(datasetVersion.id)
      message.success('已提交双人审核')
      await refreshDatasetDetail()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '提交审核失败')
    }
  }

  const reviewDataset = async (decision: 'APPROVE' | 'REJECT') => {
    if (!datasetVersion) return
    try {
      await evaluationApi.reviewDataset(datasetVersion.id, decision)
      message.success(decision === 'APPROVE' ? '审核通过已记录' : '已驳回到草稿')
      await refreshDatasetDetail()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '审核提交失败')
    }
  }

  const publishDataset = async () => {
    if (!datasetVersion) return
    try {
      await evaluationApi.publishDataset(datasetVersion.id, datasetVersion.review_round)
      message.success('数据集版本已发布并冻结')
      await refreshDatasetDetail()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '发布失败')
    }
  }

  const createNextVersion = async () => {
    if (!selectedDataset) return
    try {
      const version = await evaluationApi.createDatasetVersion(selectedDataset.id, true)
      const updated = { ...selectedDataset, latest_version_id: version.id, latest_version: version.version, latest_status: version.status }
      setSelectedDataset(updated)
      setDatasetVersion(await evaluationApi.getDatasetVersion(version.id))
      setDatasetCases(await evaluationApi.listDatasetCases(version.id))
      message.success(`已从已发布版本复制创建 v${version.version} 草稿`)
      await load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '创建新版本失败')
    }
  }

  const datasetColumns = [
    { title: '数据集', dataIndex: 'name' },
    { title: '最新版本', dataIndex: 'latest_version' },
    { title: '状态', dataIndex: 'latest_status', render: (value: string) => <Tag color={statusColor(value)}>{value}</Tag> },
    { title: 'Case数', dataIndex: 'latest_case_count' },
    { title: '已发布 Case', dataIndex: 'published_cases' },
    { title: '说明', dataIndex: 'description' },
    { title: '操作', render: (_: unknown, row: EvalDataset) => <Button type="link" onClick={() => void loadDatasetDetail(row)}>管理Case</Button> },
  ]

  const caseColumns = [
    { title: '分类', dataIndex: 'category' },
    { title: '风险', dataIndex: 'risk_level', render: (value: string) => <Tag color={value === 'HIGH' ? 'red' : value === 'MEDIUM' ? 'gold' : 'blue'}>{value}</Tag> },
    { title: '分区', dataIndex: 'split', render: (value: string) => <Tag color={value === 'HIDDEN' ? 'purple' : 'default'}>{value}</Tag> },
    { title: '来源', dataIndex: 'source_type' },
    { title: 'Oracle', dataIndex: 'oracle_type' },
    { title: '确定性检查', render: (_: unknown, row: EvalDatasetCase) => row.deterministic_checks?.length ?? '隐藏' },
    {
      title: '操作',
      render: (_: unknown, row: EvalDatasetCase) => {
        if (datasetVersion?.status === 'DRAFT' && canCreateDataset) return <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => void openCaseEditor(row)}>编辑</Button>
          <Popconfirm title="确认删除这条Case？" onConfirm={async () => {
            await evaluationApi.deleteDatasetCase(datasetVersion.id, row.id)
            message.success('Case已删除')
            await refreshDatasetDetail()
          }}><Button type="link" danger>删除</Button></Popconfirm>
        </Space>
        if (datasetVersion?.status === 'REVIEWING' && canReviewDataset) return <Button type="link" onClick={() => {
          setCaseText(JSON.stringify(row, null, 2))
          setCaseViewModal(true)
        }}>查看审核证据</Button>
        return <Text type="secondary">已冻结</Text>
      },
    },
  ]

  const experimentColumns = [
    { title: '实验', dataIndex: 'name' },
    { title: '类型', dataIndex: 'experiment_type', render: (value: string) => <Tag>{value}</Tag> },
    { title: 'Agent 数', dataIndex: 'variant_count' },
    { title: 'Trial 数', dataIndex: 'trial_count' },
    { title: '重复次数', dataIndex: 'repetitions' },
    { title: '状态', dataIndex: 'status', render: (value: string) => <Tag color={statusColor(value)}>{value}</Tag> },
  ]

  const createAgent = async () => {
    const values = await agentForm.validateFields()
    await evaluationApi.createAgent(values)
    message.success('Agent 已创建；版本审批前不能参与实验')
    setAgentModal(false)
    agentForm.resetFields()
    await load()
  }

  const createDataset = async () => {
    const values = await datasetForm.validateFields()
    await evaluationApi.createDataset(values)
    message.success('数据集草稿已创建')
    setDatasetModal(false)
    datasetForm.resetFields()
    await load()
  }

  return (
    <div>
      <Title level={2}>Agent 测评</Title>
      <Paragraph type="secondary">离线配对 A/B、沙箱 Shadow、评分成本和安全证据统一管理。首期不连接生产写工具。</Paragraph>
      {section === 'security' && gateAlert}

      {section === 'agents' && <Card title="Agent 接入" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setAgentModal(true)}>新增 Agent</Button>}>
        <Table rowKey="id" loading={loading} dataSource={agents} columns={agentColumns} pagination={false} />
      </Card>}

      {section === 'datasets' && <Card title="数据集工厂" extra={canCreateDataset ? <Button type="primary" icon={<PlusOutlined />} onClick={() => setDatasetModal(true)}>新建数据集</Button> : null}>
        <Table rowKey="id" loading={loading} dataSource={datasets} columns={datasetColumns} pagination={false} />
      </Card>}

      {section === 'experiments' && <Card title="实验与 A/B">
        <Table rowKey="id" loading={loading} dataSource={experiments} columns={experimentColumns} pagination={false} />
      </Card>}

      {section === 'reviews' && <Card title="匿名人工审核">
        <Alert type="info" showIcon message="审核队列尚未产生" description="A/B 身份、模型、成本和展示顺序将在提交前保持隐藏；评分提交后只允许追加纠正记录。" />
      </Card>}

      {section === 'security' && <>
        <Row gutter={16}>
          <Col span={8}><Card><Statistic title="执行状态" value={security?.execution_enabled ? '已开启' : '已锁定'} prefix={<SafetyCertificateOutlined />} /></Card></Col>
          <Col span={8}><Card><Statistic title="生产写工具" value="0" suffix="个" /></Card></Col>
          <Col span={8}><Card><Statistic title="远程 Agent 隔离" value="RUNNER_ONLY" /></Card></Col>
        </Row>
        <Card title="当前安全边界" style={{ marginTop: 16 }}>
          <Descriptions column={1} bordered>
            <Descriptions.Item label="允许范围">离线配对 A/B、脱敏 Shadow 回放</Descriptions.Item>
            <Descriptions.Item label="网络">默认拒绝，仅内部 Model/Tool/Artifact/OTel 代理</Descriptions.Item>
            <Descriptions.Item label="凭证">短期 Trial Token；Agent 不持有供应商和对象存储密钥</Descriptions.Item>
            <Descriptions.Item label="严重违规">立即终止、撤销 Token、记录安全事件，禁止自动重试</Descriptions.Item>
          </Descriptions>
        </Card>
      </>}

      <Modal title="新增外部 Agent" open={agentModal} onOk={() => void createAgent()} onCancel={() => setAgentModal(false)} destroyOnClose>
        <Form form={agentForm} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }, { min: 2 }]}><Input maxLength={120} /></Form.Item>
          <Form.Item name="description" label="说明"><Input.TextArea maxLength={2000} /></Form.Item>
          <Form.Item name="adapter_type" label="接入方式" rules={[{ required: true }]}>
            <Select options={['HTTP', 'SSE', 'OPENAI_COMPATIBLE', 'CONTAINER', 'CLI'].map(value => ({ value, label: value }))} />
          </Form.Item>
          <Form.Item name="risk_level" label="风险级别" rules={[{ required: true }]}>
            <Select options={['LOW', 'MEDIUM', 'HIGH'].map(value => ({ value, label: value }))} />
          </Form.Item>
          <Alert type="warning" showIcon message="HTTP/SSE/兼容 API 只能标记为 RUNNER_ONLY，平台不能隔离远程 Agent 本体。" />
        </Form>
      </Modal>

      <Modal title="新建数据集草稿" open={datasetModal} onOk={() => void createDataset()} onCancel={() => setDatasetModal(false)} destroyOnClose>
        <Form form={datasetForm} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }, { min: 2 }]}><Input maxLength={160} /></Form.Item>
          <Form.Item name="description" label="说明"><Input.TextArea maxLength={4000} /></Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={selectedDataset ? `${selectedDataset.name} · 数据集版本` : '数据集版本'}
        width="82%"
        open={datasetDrawer}
        onClose={() => setDatasetDrawer(false)}
      >
        {datasetVersion && <>
          <Descriptions bordered size="small" column={4} style={{ marginBottom: 16 }}>
            <Descriptions.Item label="版本">v{datasetVersion.version}</Descriptions.Item>
            <Descriptions.Item label="状态"><Tag color={statusColor(datasetVersion.status)}>{datasetVersion.status}</Tag></Descriptions.Item>
            <Descriptions.Item label="Case">{datasetVersion.case_count}</Descriptions.Item>
            <Descriptions.Item label="审核">{datasetVersion.approvals}/2 通过</Descriptions.Item>
          </Descriptions>
          <Alert
            showIcon
            type="info"
            message="隐藏集答案不会出现在普通列表；Agent运行时只注入当前Case输入、预算和允许工具。"
            style={{ marginBottom: 16 }}
          />
          <Space style={{ marginBottom: 16 }} wrap>
            {datasetVersion.status === 'DRAFT' && <>
              {canCreateDataset && <Button type="primary" onClick={() => { setCaseText(JSON.stringify(caseTemplate, null, 2)); setCaseImportModal(true) }}>导入JSONL/JSON</Button>}
              {canCreateDataset && <Button onClick={() => void importGolden()}>导入旧Golden</Button>}
              {canReviewDataset && <Button onClick={() => void submitReview()}>提交双人审核</Button>}
            </>}
            {datasetVersion.status === 'REVIEWING' && canReviewDataset && <>
              <Button type="primary" onClick={() => void reviewDataset('APPROVE')}>审核通过</Button>
              <Button danger onClick={() => void reviewDataset('REJECT')}>驳回</Button>
              {canPublishDataset && <Button disabled={datasetVersion.approvals < 2} onClick={() => void publishDataset()}>发布并冻结</Button>}
            </>}
            {datasetVersion.status === 'PUBLISHED' && canCreateDataset && <Button type="primary" onClick={() => void createNextVersion()}>复制为新版本草稿</Button>}
          </Space>
          <Table rowKey="id" loading={loading} dataSource={datasetCases} columns={caseColumns} pagination={{ pageSize: 20 }} />
        </>}
      </Drawer>

      <Modal
        title="导入Case（支持JSON数组或每行一个JSON）"
        width={900}
        open={caseImportModal}
        onCancel={() => setCaseImportModal(false)}
        footer={<Space><Button onClick={() => void importCases(true)}>仅校验</Button><Button type="primary" onClick={() => void importCases(false)}>校验并导入</Button></Space>}
      >
        <Alert type="warning" showIcon message="禁止真实客户数据、生产凭证和生产写工具；同源变体请使用相同source_group_id。" style={{ marginBottom: 12 }} />
        <TextArea value={caseText} onChange={event => setCaseText(event.target.value)} autoSize={{ minRows: 18, maxRows: 30 }} style={{ fontFamily: 'monospace' }} />
      </Modal>

      <Modal title="编辑Case" width={900} open={caseEditModal} onOk={() => void saveCase()} onCancel={() => setCaseEditModal(false)}>
        <TextArea value={caseText} onChange={event => setCaseText(event.target.value)} autoSize={{ minRows: 20, maxRows: 32 }} style={{ fontFamily: 'monospace' }} />
      </Modal>

      <Modal title="Case审核证据" width={900} open={caseViewModal} footer={null} onCancel={() => setCaseViewModal(false)}>
        <TextArea value={caseText} readOnly autoSize={{ minRows: 20, maxRows: 32 }} style={{ fontFamily: 'monospace' }} />
      </Modal>
    </div>
  )
}
