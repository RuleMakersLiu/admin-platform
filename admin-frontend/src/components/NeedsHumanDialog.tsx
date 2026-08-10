/**
 * 人工介入对话框（GitHub PR Review 风格）。
 * 全屏 Modal：左侧文件树 + 右侧 CodeMirror 编辑器 + 底部操作栏。
 */
import { useState, useEffect, useMemo } from 'react'
import { Modal, Button, Input, Space, Tag, Typography, message } from 'antd'
import {
  CheckCircleOutlined, ReloadOutlined, DownloadOutlined, SaveOutlined,
  FileTextOutlined, CodeOutlined,
} from '@ant-design/icons'
import CodeEditor from './CodeEditor'

const { Text, Title } = Typography
const { TextArea } = Input

export interface NeedsHumanDialogProps {
  open: boolean
  onClose: () => void
  pipelineId: string
  stageName: string
  reason: string
  issues: string[]
  fileHints: string[]
  codeFiles: Record<string, string>
  onApprove: () => void
  onRetry: (feedback: string) => void
  onDownload: () => void
  onSaveCode: (files: Record<string, string>) => Promise<void>
  loading?: boolean
}

export default function NeedsHumanDialog({
  open, onClose, pipelineId, stageName, reason, issues = [],
  codeFiles = {}, onApprove, onRetry, onDownload, onSaveCode, loading = false,
}: NeedsHumanDialogProps) {
  const [selectedFile, setSelectedFile] = useState('')
  const [editedFiles, setEditedFiles] = useState<Record<string, string>>({})
  const [feedback, setFeedback] = useState('')
  const [saving, setSaving] = useState(false)

  const fileEntries = useMemo(
    () => Object.entries(codeFiles).slice(0, 30), [codeFiles]
  )

  useEffect(() => {
    if (open && fileEntries.length > 0 && !selectedFile) {
      setSelectedFile(fileEntries[0][0])
    }
    if (!open) {
      setSelectedFile('')
      setEditedFiles({})
      setFeedback('')
    }
  }, [open])

  const currentContent = (() => {
    const entry = fileEntries.find(([p]) => p === selectedFile)
    if (!entry) return ''
    return editedFiles[selectedFile] ?? String(entry[1])
  })()

  const handleSave = async () => {
    if (!selectedFile || !pipelineId) return
    setSaving(true)
    try {
      await onSaveCode({ [selectedFile]: editedFiles[selectedFile] ?? currentContent })
      message.success(`${selectedFile.split('/').pop()} 已保存`)
    } catch {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleSaveAll = async () => {
    setSaving(true)
    try {
      const toSave: Record<string, string> = {}
      for (const [p, c] of fileEntries)
        toSave[p] = editedFiles[p] ?? String(c)
      await onSaveCode(toSave)
      message.success(`已保存 ${fileEntries.length} 个文件`)
    } catch {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width="92%"
      style={{ top: 20 }}
      styles={{ body: { padding: 0 } }}
      destroyOnClose
    >
      {/* 顶部信息栏 */}
      <div style={{
        padding: '16px 24px', borderBottom: '1px solid #f0f0f0',
        background: 'linear-gradient(135deg, #fff5f5 0%, #fff 100%)',
      }}>
        <Space align="start">
          <span style={{ fontSize: 24 }}>🔴</span>
          <div>
            <Title level={5} style={{ margin: 0 }}>
              人工介入 · {stageName} 阶段
            </Title>
            <Text type="secondary" style={{ fontSize: 13 }}>{reason}</Text>
          </div>
        </Space>
        {issues.length > 0 && (
          <div style={{ marginTop: 8, maxHeight: 80, overflow: 'auto' }}>
            {issues.slice(0, 5).map((issue, i) => (
              <div key={i} style={{ fontSize: 12, color: '#666', marginBottom: 2 }}>
                <Tag color="orange" style={{ fontSize: 11 }}>问题{i + 1}</Tag>
                {issue.length > 100 ? issue.slice(0, 100) + '...' : issue}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 主体：左侧文件 + 右侧编辑器 */}
      <div style={{ display: 'flex', height: 'calc(85vh - 200px)', minHeight: 400 }}>
        {/* 文件列表 */}
        <div style={{
          width: 240, minWidth: 240, borderRight: '1px solid #f0f0f0',
          overflow: 'auto', background: '#fafbfc',
        }}>
          <div style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0' }}>
            <Text strong style={{ fontSize: 12 }}>
              <FileTextOutlined /> 生成文件（{fileEntries.length}）
            </Text>
          </div>
          {fileEntries.map(([path]) => {
            const name = path.split('/').pop() || path
            const dir = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : ''
            const isActive = path === selectedFile
            const isEdited = editedFiles[path] !== undefined
            return (
              <div
                key={path}
                onClick={() => setSelectedFile(path)}
                style={{
                  padding: '6px 12px', cursor: 'pointer', fontSize: 12,
                  background: isActive ? '#e6f4ff' : 'transparent',
                  borderLeft: isActive ? '3px solid #1677ff' : '3px solid transparent',
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}
              >
                <span>
                  <CodeOutlined style={{ marginRight: 4, color: '#999' }} />
                  {name}
                  {dir && <span style={{ color: '#bbb', marginLeft: 4, fontSize: 10 }}>{dir}</span>}
                </span>
                {isEdited && <Tag color="blue" style={{ fontSize: 10, margin: 0, lineHeight: '16px' }}>已改</Tag>}
              </div>
            )
          })}
        </div>

        {/* 代码编辑器 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{
            padding: '6px 12px', borderBottom: '1px solid #f0f0f0',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            background: '#fafbfc',
          }}>
            <Text code style={{ fontSize: 12 }}>{selectedFile}</Text>
            <Space size="small">
              <Button size="small" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
                保存
              </Button>
              <Button size="small" loading={saving} onClick={handleSaveAll}>全部保存</Button>
            </Space>
          </div>
          <div style={{ flex: 1, overflow: 'hidden' }}>
            {selectedFile ? (
              <CodeEditor
                key={selectedFile}
                value={currentContent}
                filename={selectedFile}
                height="100%"
                onChange={(val) => {
                  setEditedFiles(prev => ({ ...prev, [selectedFile]: val }))
                }}
              />
            ) : (
              <div style={{ padding: 40, textAlign: 'center', color: '#999' }}>
                选择左侧文件查看代码
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 底部操作栏 */}
      <div style={{
        padding: '12px 24px', borderTop: '1px solid #f0f0f0',
        background: '#fafbfc',
      }}>
        <TextArea
          rows={1}
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="带反馈重生成时填写修改意见；通过可不填"
          style={{ marginBottom: 8 }}
        />
        <Space>
          <Button type="primary" icon={<CheckCircleOutlined />} loading={loading} onClick={onApprove}>
            通过并继续
          </Button>
          <Button danger icon={<ReloadOutlined />} loading={loading} onClick={() => onRetry(feedback)}>
            带反馈重生成
          </Button>
          <Button icon={<DownloadOutlined />} onClick={onDownload}>
            下载代码
          </Button>
        </Space>
      </div>
    </Modal>
  )
}
