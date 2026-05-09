import React from 'react'
import { Card, Tag, Button, Tooltip, Space } from 'antd'
import {
  DownloadOutlined,
  StarOutlined,
  UserOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons'
import type { Skill } from '@/services/skills'

interface SkillCardProps {
  skill: Skill
  onDownload?: (skill: Skill) => void
  onClick?: (skill: Skill) => void
  loading?: boolean
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

const SkillCard: React.FC<SkillCardProps> = ({ skill, onDownload, onClick, loading }) => {
  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation()
    onDownload?.(skill)
  }

  const handleClick = () => {
    onClick?.(skill)
  }

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days === 0) return '今天'
    if (days === 1) return '昨天'
    if (days < 7) return `${days}天前`
    if (days < 30) return `${Math.floor(days / 7)}周前`
    if (days < 365) return `${Math.floor(days / 30)}个月前`
    return `${Math.floor(days / 365)}年前`
  }

  return (
    <Card
      hoverable
      className="skill-card"
      onClick={handleClick}
      styles={{
        body: { padding: '16px' },
      }}
    >
      {/* 头部：图标和分类 */}
      <div className="skill-card-header">
        <div className="skill-icon">
          {skill.icon ? (
            <img src={skill.icon} alt={skill.name} />
          ) : (
            <div className="skill-icon-placeholder">
              {skill.name.charAt(0).toUpperCase()}
            </div>
          )}
        </div>
        <Tag color={categoryColors[skill.category] || 'default'}>
          {skill.categoryName}
        </Tag>
      </div>

      {/* 标题和描述 */}
      <h3 className="skill-card-title" title={skill.name}>
        {skill.name}
      </h3>
      <p className="skill-card-description" title={skill.description}>
        {skill.description}
      </p>

      {/* 标签 */}
      {skill.tags && skill.tags.length > 0 && (
        <div className="skill-card-tags">
          {skill.tags.slice(0, 3).map((tag) => (
            <Tag key={tag} className="skill-tag">
              {tag}
            </Tag>
          ))}
          {skill.tags.length > 3 && (
            <Tag className="skill-tag">+{skill.tags.length - 3}</Tag>
          )}
        </div>
      )}

      {/* 统计信息 */}
      <div className="skill-card-stats">
        <Space size={4}>
          <StarOutlined style={{ color: '#faad14' }} />
          <span className="stat-value">{skill.rating.toFixed(1)}</span>
          <span className="stat-label">({skill.ratingCount})</span>
        </Space>
        <Space size={4}>
          <DownloadOutlined />
          <span className="stat-value">{skill.downloadCount}</span>
        </Space>
      </div>

      {/* 底部：作者和时间 */}
      <div className="skill-card-footer">
        <Space size={4}>
          <UserOutlined />
          <span className="author-name">{skill.author}</span>
        </Space>
        <Tooltip title={new Date(skill.updateTime).toLocaleString()}>
          <Space size={4}>
            <ClockCircleOutlined />
            <span>{formatTime(skill.updateTime)}</span>
          </Space>
        </Tooltip>
      </div>

      {/* 下载按钮 */}
      <div className="skill-card-actions">
        <Button
          type={skill.isDownloaded ? 'default' : 'primary'}
          icon={skill.isDownloaded ? <CheckCircleOutlined /> : <DownloadOutlined />}
          onClick={handleDownload}
          loading={loading}
          disabled={skill.isDownloaded}
          block
        >
          {skill.isDownloaded ? '已下载' : '下载'}
        </Button>
      </div>

      <style>{`
        .skill-card {
          height: 100%;
          display: flex;
          flex-direction: column;
          border-radius: 8px;
          transition: all 0.3s ease;
        }
        .skill-card:hover {
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
          transform: translateY(-2px);
        }
        .skill-card-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 12px;
        }
        .skill-icon {
          width: 48px;
          height: 48px;
          border-radius: 8px;
          overflow: hidden;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .skill-icon img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .skill-icon-placeholder {
          width: 100%;
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #fff;
          font-size: 24px;
          font-weight: bold;
        }
        .skill-card-title {
          margin: 0 0 8px 0;
          font-size: 16px;
          font-weight: 600;
          color: #1f1f1f;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .skill-card-description {
          margin: 0 0 12px 0;
          font-size: 13px;
          color: #666;
          line-height: 1.5;
          height: 40px;
          overflow: hidden;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
        }
        .skill-card-tags {
          margin-bottom: 12px;
          display: flex;
          flex-wrap: wrap;
          gap: 4px;
        }
        .skill-tag {
          margin: 0;
          font-size: 11px;
          padding: 0 6px;
          height: 20px;
          line-height: 20px;
          background: #f5f5f5;
          border: none;
          color: #666;
        }
        .skill-card-stats {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 8px 0;
          border-top: 1px solid #f0f0f0;
          border-bottom: 1px solid #f0f0f0;
          margin-bottom: 12px;
        }
        .stat-value {
          font-weight: 500;
          color: #1f1f1f;
        }
        .stat-label {
          color: #999;
          font-size: 12px;
        }
        .skill-card-footer {
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 12px;
          color: #999;
          margin-bottom: 12px;
        }
        .author-name {
          max-width: 100px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .skill-card-actions {
          margin-top: auto;
        }
      `}</style>
    </Card>
  )
}

export default SkillCard
