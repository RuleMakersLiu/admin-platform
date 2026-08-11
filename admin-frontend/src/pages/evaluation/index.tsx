import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import { PlusOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import {
  EvalAgent,
  EvalDataset,
  EvalExperiment,
  EvalSecurityStatus,
  evaluationApi,
} from '@/services/evaluation'

const { Title, Paragraph, Text } = Typography

const statusColor = (status: string) => {
  if (['COMPLETED', 'ACTIVE', 'SUCCEEDED', 'PUBLISHED'].includes(status)) return 'green'
  if (['FAILED', 'SECURITY_STOPPED', 'SECURITY_TERMINATED'].includes(status)) return 'red'
  if (['RUNNING', 'SCORING', 'REVIEWING'].includes(status)) return 'blue'
  return 'default'
}

export default function EvaluationPage() {
  const location = useLocation()
  const section = location.pathname.split('/')[2] || 'agents'
  const [loading, setLoading] = useState(false)
  const [security, setSecurity] = useState<EvalSecurityStatus>()
  const [agents, setAgents] = useState<EvalAgent[]>([])
  const [datasets, setDatasets] = useState<EvalDataset[]>([])
  const [experiments, setExperiments] = useState<EvalExperiment[]>([])
  const [agentModal, setAgentModal] = useState(false)
  const [datasetModal, setDatasetModal] = useState(false)
  const [agentForm] = Form.useForm()
  const [datasetForm] = Form.useForm()

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

  const datasetColumns = [
    { title: '数据集', dataIndex: 'name' },
    { title: '最新版本', dataIndex: 'latest_version' },
    { title: '已发布 Case', dataIndex: 'published_cases' },
    { title: '说明', dataIndex: 'description' },
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

      {section === 'datasets' && <Card title="数据集工厂" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setDatasetModal(true)}>新建数据集</Button>}>
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
    </div>
  )
}
