import React, { useState } from 'react'
import { Modal, Rate, Input, message, Form, Avatar, List, Empty, Spin } from 'antd'
import { UserOutlined } from '@ant-design/icons'
import type { Skill, Rating } from '@/services/skills'
import skillsMarketApi from '@/services/skills'

const { TextArea } = Input

interface RatingModalProps {
  visible: boolean
  skill: Skill | null
  onClose: () => void
  onSuccess?: () => void
}

const RatingModal: React.FC<RatingModalProps> = ({ visible, skill, onClose, onSuccess }) => {
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)
  const [ratings, setRatings] = useState<Rating[]>([])
  const [ratingsLoading, setRatingsLoading] = useState(false)
  const [ratingsTotal, setRatingsTotal] = useState(0)
  const [activeTab, setActiveTab] = useState<'rate' | 'view'>('rate')

  // 加载评分记录
  const loadRatings = async () => {
    if (!skill) return
    setRatingsLoading(true)
    try {
      const result = await skillsMarketApi.getRatings(skill.id, { page: 1, pageSize: 10 })
      setRatings(result.list || [])
      setRatingsTotal(result.total || 0)
    } catch (error) {
      console.error('Failed to load ratings:', error)
    } finally {
      setRatingsLoading(false)
    }
  }

  // 处理弹窗打开
  const handleAfterOpenChange = (open: boolean) => {
    if (open && skill) {
      loadRatings()
      form.resetFields()
    }
  }

  // 提交评分
  const handleSubmit = async () => {
    if (!skill) return

    try {
      const values = await form.validateFields()
      setSubmitting(true)

      await skillsMarketApi.rateSkill(skill.id, {
        rating: values.rating,
        comment: values.comment,
      })

      message.success('评分成功')
      form.resetFields()
      onSuccess?.()
      onClose()
    } catch (error: any) {
      if (!error?.errorFields) {
        message.error(error?.message || '评分失败，请稍后重试')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp)
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString().slice(0, 5)
  }

  if (!skill) return null

  return (
    <Modal
      title="技能评分"
      open={visible}
      onCancel={onClose}
      afterOpenChange={handleAfterOpenChange}
      onOk={activeTab === 'rate' ? handleSubmit : undefined}
      okText={activeTab === 'rate' ? '提交评分' : undefined}
      confirmLoading={submitting}
      width={520}
      footer={activeTab === 'rate' ? undefined : null}
      destroyOnClose
    >
      {/* 技能信息 */}
      <div className="rating-skill-info">
        <div className="skill-icon">
          {skill.icon ? (
            <img src={skill.icon} alt={skill.name} />
          ) : (
            <div className="skill-icon-placeholder">
              {skill.name.charAt(0).toUpperCase()}
            </div>
          )}
        </div>
        <div className="skill-meta">
          <h4>{skill.name}</h4>
          <div className="rating-summary">
            <Rate disabled value={skill.rating} allowHalf />
            <span className="rating-value">{skill.rating.toFixed(1)}</span>
            <span className="rating-count">({skill.ratingCount} 评价)</span>
          </div>
        </div>
      </div>

      {/* Tab 切换 */}
      <div className="rating-tabs">
        <button
          className={`tab-btn ${activeTab === 'rate' ? 'active' : ''}`}
          onClick={() => setActiveTab('rate')}
        >
          发表评价
        </button>
        <button
          className={`tab-btn ${activeTab === 'view' ? 'active' : ''}`}
          onClick={() => {
            setActiveTab('view')
            loadRatings()
          }}
        >
          查看评价 ({ratingsTotal})
        </button>
      </div>

      {/* 评分表单 */}
      {activeTab === 'rate' && (
        <Form form={form} layout="vertical" className="rating-form">
          <Form.Item
            name="rating"
            label="评分"
            rules={[{ required: true, message: '请选择评分' }]}
          >
            <Rate allowHalf style={{ fontSize: 28 }} />
          </Form.Item>
          <Form.Item name="comment" label="评价内容（可选）">
            <TextArea
              placeholder="分享您的使用体验..."
              rows={4}
              maxLength={500}
              showCount
            />
          </Form.Item>
        </Form>
      )}

      {/* 评价列表 */}
      {activeTab === 'view' && (
        <div className="ratings-list">
          {ratingsLoading ? (
            <div className="ratings-loading">
              <Spin />
            </div>
          ) : ratings.length === 0 ? (
            <Empty description="暂无评价" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <List
              dataSource={ratings}
              renderItem={(item) => (
                <List.Item className="rating-item">
                  <div className="rating-item-content">
                    <div className="rating-item-header">
                      <Avatar size="small" icon={<UserOutlined />} />
                      <span className="user-name">{item.userName}</span>
                      <Rate disabled value={item.rating} style={{ fontSize: 12 }} />
                      <span className="rating-time">{formatTime(item.createTime)}</span>
                    </div>
                    {item.comment && (
                      <p className="rating-comment">{item.comment}</p>
                    )}
                  </div>
                </List.Item>
              )}
            />
          )}
        </div>
      )}

      <style>{`
        .rating-skill-info {
          display: flex;
          gap: 16px;
          padding: 16px;
          background: #f5f5f5;
          border-radius: 8px;
          margin-bottom: 20px;
        }
        .rating-skill-info .skill-icon {
          width: 56px;
          height: 56px;
          border-radius: 8px;
          overflow: hidden;
          flex-shrink: 0;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .rating-skill-info .skill-icon img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .rating-skill-info .skill-icon-placeholder {
          width: 100%;
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #fff;
          font-size: 24px;
          font-weight: bold;
        }
        .rating-skill-info .skill-meta h4 {
          margin: 0 0 8px 0;
          font-size: 16px;
          font-weight: 600;
        }
        .rating-skill-info .rating-summary {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .rating-skill-info .rating-value {
          font-weight: 600;
          color: #1f1f1f;
        }
        .rating-skill-info .rating-count {
          color: #999;
          font-size: 13px;
        }
        .rating-tabs {
          display: flex;
          border-bottom: 1px solid #f0f0f0;
          margin-bottom: 20px;
        }
        .tab-btn {
          padding: 8px 16px;
          border: none;
          background: none;
          font-size: 14px;
          color: #666;
          cursor: pointer;
          position: relative;
          transition: color 0.3s;
        }
        .tab-btn:hover {
          color: #1890ff;
        }
        .tab-btn.active {
          color: #1890ff;
          font-weight: 500;
        }
        .tab-btn.active::after {
          content: '';
          position: absolute;
          bottom: -1px;
          left: 0;
          right: 0;
          height: 2px;
          background: #1890ff;
        }
        .rating-form {
          padding: 0;
        }
        .ratings-list {
          max-height: 400px;
          overflow-y: auto;
        }
        .ratings-loading {
          display: flex;
          justify-content: center;
          padding: 40px 0;
        }
        .rating-item {
          padding: 12px 0 !important;
          border-bottom: 1px solid #f0f0f0;
        }
        .rating-item:last-child {
          border-bottom: none;
        }
        .rating-item-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
        }
        .rating-item-header .user-name {
          font-weight: 500;
          color: #1f1f1f;
        }
        .rating-item-header .rating-time {
          margin-left: auto;
          font-size: 12px;
          color: #999;
        }
        .rating-comment {
          margin: 0;
          color: #666;
          line-height: 1.6;
          font-size: 13px;
        }
      `}</style>
    </Modal>
  )
}

export default RatingModal
