import React, { memo, useState, useCallback } from 'react';
import {
  List,
  Button,
  Input,
  Modal,
  Dropdown,
  Empty,
  Spin,
  Typography,
  Tooltip,
  Space,
} from 'antd';
import {
  PlusOutlined,
  MessageOutlined,
  EditOutlined,
  DeleteOutlined,
  MoreOutlined,
} from '@ant-design/icons';
import type { Session } from '@/types/chat';
import { useSearch } from '@/hooks/useChat';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

const { Text } = Typography;

// 会话列表项组件
interface SessionItemProps {
  session: Session;
  isActive: boolean;
  onSelect: (sessionId: string) => void;
  onRename: (sessionId: string, title: string) => void;
  onDelete: (sessionId: string) => void;
}

const SessionItem: React.FC<SessionItemProps> = memo(
  ({ session, isActive, onSelect, onRename, onDelete }) => {
    const [renameVisible, setRenameVisible] = useState(false);
    const [newTitle, setNewTitle] = useState(session.title);

    const handleRename = useCallback(() => {
      if (newTitle.trim() && newTitle !== session.title) {
        onRename(session.id, newTitle.trim());
      }
      setRenameVisible(false);
    }, [newTitle, session.id, session.title, onRename]);

    const handleDelete = useCallback(() => {
      Modal.confirm({
        title: '确认删除',
        content: `确定要删除会话 "${session.title}" 吗？删除后无法恢复。`,
        okText: '删除',
        cancelText: '取消',
        okButtonProps: { danger: true },
        onOk: () => onDelete(session.id),
      });
    }, [session.id, session.title, onDelete]);

    const menuItems = [
      {
        key: 'rename',
        icon: <EditOutlined />,
        label: '重命名',
        onClick: () => setRenameVisible(true),
      },
      {
        type: 'divider' as const,
      },
      {
        key: 'delete',
        icon: <DeleteOutlined />,
        label: '删除',
        danger: true,
        onClick: handleDelete,
      },
    ];

    return (
      <>
        <List.Item
          className={`session-item ${isActive ? 'active' : ''}`}
          onClick={() => onSelect(session.id)}
          actions={[
            <Dropdown
              key="menu"
              menu={{ items: menuItems }}
              trigger={['click']}
              placement="bottomRight"
            >
              <Button
                type="text"
                size="small"
                icon={<MoreOutlined />}
                className="session-menu-btn"
                onClick={(e) => e.stopPropagation()}
              />
            </Dropdown>,
          ]}
        >
          <List.Item.Meta
            avatar={<MessageOutlined className="session-icon" />}
            title={
              <Text ellipsis className="session-title">
                {session.title}
              </Text>
            }
            description={
              <Space direction="vertical" size={0} className="session-meta">
                <Text type="secondary" className="session-time">
                  {dayjs(session.updatedAt).fromNow()}
                </Text>
                {session.lastMessage && (
                  <Text type="secondary" ellipsis className="session-preview">
                    {session.lastMessage}
                  </Text>
                )}
              </Space>
            }
          />
        </List.Item>

        <Modal
          title="重命名会话"
          open={renameVisible}
          onOk={handleRename}
          onCancel={() => {
            setRenameVisible(false);
            setNewTitle(session.title);
          }}
          okText="确定"
          cancelText="取消"
        >
          <Input
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onPressEnter={handleRename}
            placeholder="请输入新的会话名称"
            autoFocus
          />
        </Modal>
      </>
    );
  }
);

SessionItem.displayName = 'SessionItem';

// 会话列表组件 Props
interface SessionListProps {
  sessions: Session[];
  currentSessionId: string | null;
  isLoading?: boolean;
  onCreateSession: () => void;
  onSelectSession: (sessionId: string) => void;
  onRenameSession: (sessionId: string, title: string) => void;
  onDeleteSession: (sessionId: string) => void;
}

// 会话列表组件
const SessionList: React.FC<SessionListProps> = ({
  sessions,
  currentSessionId,
  isLoading = false,
  onCreateSession,
  onSelectSession,
  onRenameSession,
  onDeleteSession,
}) => {
  const { keyword, setKeyword, debouncedKeyword } = useSearch(300);

  // 过滤会话列表
  const filteredSessions = sessions.filter((session) =>
    session.title.toLowerCase().includes(debouncedKeyword.toLowerCase())
  );

  return (
    <div className="session-list-container">
      {/* 搜索和新建 */}
      <div className="session-list-header">
        <Input.Search
          placeholder="搜索会话..."
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          allowClear
          className="session-search"
        />
        <Tooltip title="新建会话">
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={onCreateSession}
            className="create-session-btn"
          />
        </Tooltip>
      </div>

      {/* 会话列表 */}
      <div className="session-list-content">
        {isLoading ? (
          <div className="session-list-loading">
            <Spin />
          </div>
        ) : filteredSessions.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={keyword ? '未找到匹配的会话' : '暂无会话'}
            className="session-list-empty"
          />
        ) : (
          <List
            dataSource={filteredSessions}
            renderItem={(session) => (
              <SessionItem
                key={session.id}
                session={session}
                isActive={session.id === currentSessionId}
                onSelect={onSelectSession}
                onRename={onRenameSession}
                onDelete={onDeleteSession}
              />
            )}
            className="session-list"
          />
        )}
      </div>
    </div>
  );
};

export default memo(SessionList);
