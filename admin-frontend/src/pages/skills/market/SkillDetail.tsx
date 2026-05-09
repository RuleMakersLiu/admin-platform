import React, { useState, useEffect } from 'react'
import {
  Modal,
  Button,
  Tag,
  Descriptions,
  Spin,
  message,
  Space,
  Divider,
  Typography,
  Tabs,
} from 'antd'
import {
  DownloadOutlined,
  UserOutlined,
  StarOutlined,
  ClockCircleOutlined,
  TagOutlined,
  CheckCircleOutlined,
  CalendarOutlined,
  CodeOutlined,
} from '@ant-design/icons'
import type { Skill } from '@/services/skills'
import skillsMarketApi from '@/services/skills'

const { Paragraph, Text } = Typography

interface SkillDetailProps {
  visible: boolean
  skillId: string | null
  onClose: () => void
  onDownload?: (skill: Skill) => void
  onRate?: (skill: Skill) => void
}

const categoryColors: Record<string, string> = {
  coding: 'blue',
  analysis: 'green',
  writing: 'orange',
  translation: 'purple',
  productivity: 'cyan',
  automation: 'magenta',
  other: 'default',
}

const SkillDetail: React.FC<SkillDetailProps> = ({
  visible,
  skillId,
  onClose,
  onDownload,
  onRate,
}) => {
  const [skill, setSkill] = useState<Skill | null>(null)
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)

  // 加载技能详情
  useEffect(() => {
    if (visible && skillId) {
      fetchSkillDetail()
    }
    return () => {
      setSkill(null)
    }
  }, [visible, skillId])

  const fetchSkillDetail = async () => {
    if (!skillId) return
    setLoading(true)
    try {
      const result = await skillsMarketApi.getSkillDetail(skillId)
      setSkill(result)
    } catch (error) {
      message.error('获取技能详情失败')
      onClose()
    } finally {
      setLoading(false)
    }
  }

  // 下载技能
  const handleDownload = async () => {
    if (!skill) return
    setDownloading(true)
    try {
      await skillsMarketApi.downloadSkill(skill.id)
      message.success('下载成功')
      setSkill({ ...skill, isDownloaded: true })
      onDownload?.(skill)
    } catch (error: any) {
      message.error(error?.message || '下载失败')
    } finally {
      setDownloading(false)
    }
  }

  // 处理评分
  const handleRate = () => {
    if (skill) {
      onRate?.(skill)
    }
  }

  const formatTime = (timestamp: number) => {
    return new Date(timestamp).toLocaleString()
  }

  const renderLoading = () => (
    <div className="detail-loading">
      <Spin size="large" />
    </div>
  )

  const renderContent = () => {
    if (!skill) return null

    return (
      <div className="skill-detail-content">
        {/* 头部信息 */}
        <div className="detail-header">
          <div className="skill-icon-large">
            {skill.icon ? (
              <img src={skill.icon} alt={skill.name} />
            ) : (
              <div className="skill-icon-placeholder-large">
                {skill.name.charAt(0).toUpperCase()}
              </div>
            )}
          </div>
          <div className="header-info">
            <h2>{skill.name}</h2>
            <div className="header-meta">
              <Tag color={categoryColors[skill.category] || 'default'}>
                {skill.categoryName}
              </Tag>
              <span className="version">v{skill.version}</span>
            </div>
            <div className="header-stats">
              <Space size={16}>
                <span className="stat-item">
                  <StarOutlined style={{ color: '#faad14' }} />
                  <span className="stat-value">{skill.rating.toFixed(1)}</span>
                  <span className="stat-label">({skill.ratingCount} 评价)</span>
                </span>
                <span className="stat-item">
                  <DownloadOutlined />
                  <span className="stat-value">{skill.downloadCount}</span>
                  <span className="stat-label">次下载</span>
                </span>
              </Space>
            </div>
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="detail-actions">
          <Button
            type={skill.isDownloaded ? 'default' : 'primary'}
            size="large"
            icon={skill.isDownloaded ? <CheckCircleOutlined /> : <DownloadOutlined />}
            onClick={handleDownload}
            loading={downloading}
            disabled={skill.isDownloaded}
          >
            {skill.isDownloaded ? '已下载' : '下载技能'}
          </Button>
          <Button size="large" icon={<StarOutlined />} onClick={handleRate}>
            评分评价
          </Button>
        </div>

        <Divider />

        {/* 详情标签页 */}
        <Tabs
          defaultActiveKey="description"
          items={[
            {
              key: 'description',
              label: '技能描述',
              children: (
                <div className="detail-section">
                  <div className="section-content">
                    <Paragraph style={{ fontSize: 14, lineHeight: 1.8, margin: 0 }}>
                      {skill.longDescription || skill.description}
                    </Paragraph>
                  </div>
                </div>
              ),
            },
            {
              key: 'info',
              label: '详细信息',
              children: (
                <div className="detail-section">
                  <Descriptions column={2} labelStyle={{ width: 100 }}>
                    <Descriptions.Item
                      label={<><UserOutlined /> 作者</>}
                    >
                      {skill.author}
                    </Descriptions.Item>
                    <Descriptions.Item
                      label={<><CodeOutlined /> 版本</>}
                    >
                      v{skill.version}
                    </Descriptions.Item>
                    <Descriptions.Item
                      label={<><CalendarOutlined /> 发布时间</>}
                    >
                      {formatTime(skill.createTime)}
                    </Descriptions.Item>
                    <Descriptions.Item
                      label={<><ClockCircleOutlined /> 更新时间</>}
                    >
                      {formatTime(skill.updateTime)}
                    </Descriptions.Item>
                    <Descriptions.Item label="技能ID" span={2}>
                      <Text copyable style={{ fontFamily: 'monospace' }}>
                        {skill.id}
                      </Text>
                    </Descriptions.Item>
                  </Descriptions>

                  {skill.tags && skill.tags.length > 0 && (
                    <div className="tags-section">
                      <h4><TagOutlined /> 标签</h4>
                      <div className="tags-list">
                        {skill.tags.map((tag) => (
                          <Tag key={tag}>{tag}</Tag>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ),
            },
          ]}
        />

        <style>{`
          .detail-loading {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 300px;
          }
          .skill-detail-content {
            padding: 8px 0;
          }
          .detail-header {
            display: flex;
            gap: 24px;
            margin-bottom: 24px;
          }
          .skill-icon-large {
            width: 96px;
            height: 96px;
            border-radius: 16px;
            overflow: hidden;
            flex-shrink: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
          }
          .skill-icon-large img {
            width: 100%;
            height: 100%;
            object-fit: cover;
          }
          .skill-icon-placeholder-large {
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-size: 40px;
            font-weight: bold;
          }
          .header-info h2 {
            margin: 0 0 8px 0;
            font-size: 24px;
            font-weight: 600;
          }
          .header-meta {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 12px;
          }
          .header-meta .version {
            color: #666;
            font-size: 14px;
          }
          .header-stats {
            margin-top: 8px;
          }
          .stat-item {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            color: #666;
          }
          .stat-item .stat-value {
            font-weight: 600;
            color: #1f1f1f;
          }
          .stat-item .stat-label {
            color: #999;
            font-size: 13px;
          }
          .detail-actions {
            display: flex;
            gap: 12px;
            margin-bottom: 8px;
          }
          .detail-section {
            padding: 8px 0;
          }
          .section-content {
            background: #fafafa;
            padding: 16px;
            border-radius: 8px;
          }
          .tags-section {
            margin-top: 24px;
          }
          .tags-section h4 {
            margin-bottom: 12px;
            color: #666;
            font-weight: 500;
          }
          .tags-list {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
          }
        `}</style>
      </div>
    )
  }

  return (
    <Modal
      title={null}
      open={visible}
      onCancel={onClose}
      footer={null}
      width={720}
      centered
      destroyOnClose
    >
      {loading ? renderLoading() : renderContent()}
    </Modal>
  )
}

export default SkillDetail
