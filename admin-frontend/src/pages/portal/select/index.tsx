import { Button, Space, Typography } from 'antd'
import { CodeOutlined, RocketOutlined, SwapOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { canUseDeveloperPortal, canUseProductPortal, saveLastPortalPath, useAuthStore } from '@/stores/auth'

const { Title, Text } = Typography

export default function PortalSelect() {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const developer = canUseDeveloperPortal(user)
  const product = canUseProductPortal(user)

  const enterPortal = (path: string) => {
    saveLastPortalPath(user, path)
    navigate(path)
  }

  return (
    <div className="workbench-page portal-select-page">
      <div className="workbench-narrow">
        <Space align="center" size={12} className="workbench-title-row">
          <SwapOutlined className="workbench-title-icon" />
          <div>
            <Title level={3} style={{ margin: 0 }}>选择工作门户</Title>
            <Text className="muted-text">根据当前账号权限进入项目接入或需求开发工作流。</Text>
          </div>
        </Space>

        <div className="portal-choice-grid">
          <div className="workbench-card portal-choice-card">
            <CodeOutlined className="portal-choice-icon portal-choice-icon-blue" />
            <Title level={4}>项目接入</Title>
            <Text className="muted-text">导入 Git 项目，触发项目解析，编辑并确认项目级 Skill。</Text>
            <div style={{ marginTop: 24 }}>
              <Button type="primary" disabled={!developer} onClick={() => enterPortal('/project/access')}>进入项目接入</Button>
            </div>
          </div>

          <div className="workbench-card portal-choice-card">
            <RocketOutlined className="portal-choice-icon portal-choice-icon-green" />
            <Title level={4}>需求开发</Title>
            <Text className="muted-text">选择已确认 Skill 的项目，输入需求并生成预览、前端代码、API 契约和审查报告。</Text>
            <div style={{ marginTop: 24 }}>
              <Button type="primary" disabled={!product} onClick={() => enterPortal('/pipeline/requirement')}>进入需求开发</Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
