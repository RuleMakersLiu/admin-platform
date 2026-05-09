# 核心功能增强实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 LLM配置、Git配置、HTTP Streaming、项目角色体系

**Architecture:** 新建 admin-config (Go) 统一管理配置，扩展 admin-agent 支持 HTTP Streaming，前端新增系统配置页面

**Tech Stack:** Go + Gin, React + Ant Design, MySQL

---

## Task 1: 数据库 Schema 更新

**Files:**
- Modify: `database/schema.sql`

**Step 1: 添加新表到 schema.sql 末尾**

```sql
-- =============================================
-- 核心功能增强 - 新增表
-- =============================================

-- 大模型配置表
DROP TABLE IF EXISTS `sys_llm_config`;
CREATE TABLE `sys_llm_config` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL COMMENT '配置名称',
  `provider` varchar(50) NOT NULL COMMENT '提供商: openai/anthropic/azure/custom',
  `base_url` varchar(255) NOT NULL COMMENT 'API Base URL',
  `api_key` varchar(255) NOT NULL COMMENT 'API Key (AES加密)',
  `model_name` varchar(100) NOT NULL COMMENT '模型名称',
  `max_tokens` int(11) DEFAULT 4096 COMMENT '最大Token',
  `temperature` decimal(3,2) DEFAULT 0.70 COMMENT '温度参数',
  `extra_config` json DEFAULT NULL COMMENT '额外配置',
  `is_default` tinyint(1) DEFAULT 0 COMMENT '是否默认',
  `status` tinyint(1) DEFAULT 1 COMMENT '状态: 0禁用 1启用',
  `tenant_id` bigint(20) DEFAULT 0 COMMENT '租户ID',
  `admin_id` bigint(20) NOT NULL COMMENT '创建者ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(毫秒)',
  PRIMARY KEY (`id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='大模型配置表';

-- Git平台配置表
DROP TABLE IF EXISTS `sys_git_config`;
CREATE TABLE `sys_git_config` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL COMMENT '配置名称',
  `platform` varchar(20) NOT NULL COMMENT '平台: gitlab/github/gitee/gitea',
  `base_url` varchar(255) NOT NULL COMMENT 'Git服务URL',
  `access_token` varchar(255) NOT NULL COMMENT 'Access Token (AES加密)',
  `webhook_secret` varchar(255) DEFAULT NULL COMMENT 'Webhook密钥',
  `ssh_key` text DEFAULT NULL COMMENT 'SSH私钥',
  `extra_config` json DEFAULT NULL COMMENT '额外配置',
  `is_default` tinyint(1) DEFAULT 0 COMMENT '是否默认',
  `status` tinyint(1) DEFAULT 1 COMMENT '状态',
  `tenant_id` bigint(20) DEFAULT 0 COMMENT '租户ID',
  `admin_id` bigint(20) NOT NULL COMMENT '创建者ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(毫秒)',
  PRIMARY KEY (`id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_platform` (`platform`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Git平台配置表';

-- 项目成员表
DROP TABLE IF EXISTS `sys_project_member`;
CREATE TABLE `sys_project_member` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `project_id` bigint(20) NOT NULL COMMENT '项目ID',
  `project_type` varchar(20) NOT NULL COMMENT '项目类型: agent/deploy',
  `admin_id` bigint(20) NOT NULL COMMENT '用户ID',
  `role` varchar(20) NOT NULL COMMENT '角色: owner/maintainer/developer',
  `permissions` json DEFAULT NULL COMMENT '细粒度权限',
  `added_by` bigint(20) DEFAULT NULL COMMENT '添加者ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(毫秒)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_project_admin` (`project_id`, `project_type`, `admin_id`),
  KEY `idx_admin_id` (`admin_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目成员表';

-- 菜单数据
INSERT INTO `sys_menu` (`parent_id`, `name`, `path`, `component`, `permission`, `icon`, `type`, `visible`, `sort`) VALUES
(1, '大模型配置', '/system/llm', 'system/llm/index', 'system_llm_list', 'RobotOutlined', 1, 1, 50),
(1, 'Git配置', '/system/git', 'system/git/index', 'system_git_list', 'GithubOutlined', 1, 1, 51);
```

**Step 2: Commit**

```bash
git add database/schema.sql
git commit -m "feat(db): add sys_llm_config, sys_git_config, sys_project_member tables"
```

---

## Task 2: 创建 admin-config 服务骨架

**Files:**
- Create: `admin-config/cmd/main.go`
- Create: `admin-config/config.yaml`
- Create: `admin-config/go.mod`
- Create: `admin-config/internal/config/config.go`
- Create: `admin-config/internal/router/router.go`

**Step 1: 创建目录结构**

```bash
mkdir -p admin-config/{cmd,internal/{config,handler,service,router,middleware,model},pkg/crypto}
```

**Step 2: 创建 go.mod**

```go
module admin-config

go 1.21

require (
	github.com/gin-gonic/gin v1.9.1
	github.com/go-sql-driver/mysql v1.7.1
	github.com/spf13/viper v1.18.2
	gorm.io/driver/mysql v1.5.2
	gorm.io/gorm v1.25.5
)
```

**Step 3: 创建 config.yaml**

```yaml
server:
  port: 8085

database:
  host: localhost
  port: 3306
  user: root
  password: root123
  dbname: admin_platform

redis:
  host: localhost
  port: 6379

crypto:
  aes_key: "your-32-byte-aes-key-here!!"
```

**Step 4: Commit**

```bash
git add admin-config/
git commit -m "feat(config): init admin-config service skeleton"
```

---

## Task 3: 实现 LLM 配置 CRUD

**Files:**
- Create: `admin-config/internal/model/llm_config.go`
- Create: `admin-config/internal/handler/llm.go`
- Create: `admin-config/internal/service/llm.go`
- Create: `admin-config/pkg/crypto/aes.go`

**Step 1: 创建 Model**

```go
// admin-config/internal/model/llm_config.go
package model

import "time"

type LLMConfig struct {
	ID          int64   `json:"id" gorm:"primaryKey"`
	Name        string  `json:"name" gorm:"size:100;not null"`
	Provider    string  `json:"provider" gorm:"size:50;not null"`
	BaseURL     string  `json:"base_url" gorm:"size:255;not null"`
	APIKey      string  `json:"-" gorm:"size:255;not null"` // 加密存储，不返回前端
	ModelName   string  `json:"model_name" gorm:"size:100;not null"`
	MaxTokens   int     `json:"max_tokens" gorm:"default:4096"`
	Temperature float64 `json:"temperature" gorm:"type:decimal(3,2);default:0.7"`
	ExtraConfig string  `json:"extra_config" gorm:"type:json"`
	IsDefault   int     `json:"is_default" gorm:"default:0"`
	Status      int     `json:"status" gorm:"default:1"`
	TenantID    int64   `json:"tenant_id" gorm:"default:0"`
	AdminID     int64   `json:"admin_id" gorm:"not null"`
	CreateTime  int64   `json:"create_time"`
	UpdateTime  int64   `json:"update_time"`
}

func (LLMConfig) TableName() string {
	return "sys_llm_config"
}

type LLMConfigCreate struct {
	Name        string  `json:"name" binding:"required"`
	Provider    string  `json:"provider" binding:"required"`
	BaseURL     string  `json:"base_url" binding:"required"`
	APIKey      string  `json:"api_key" binding:"required"`
	ModelName   string  `json:"model_name" binding:"required"`
	MaxTokens   int     `json:"max_tokens"`
	Temperature float64 `json:"temperature"`
	ExtraConfig string  `json:"extra_config"`
}

type LLMConfigUpdate struct {
	Name        string  `json:"name"`
	BaseURL     string  `json:"base_url"`
	APIKey      string  `json:"api_key"`
	ModelName   string  `json:"model_name"`
	MaxTokens   int     `json:"max_tokens"`
	Temperature float64 `json:"temperature"`
	ExtraConfig string  `json:"extra_config"`
	Status      *int    `json:"status"`
}
```

**Step 2: Commit**

```bash
git add admin-config/internal/model/
git commit -m "feat(config): add LLM config model"
```

---

## Task 4: 实现 Git 配置 CRUD

**Files:**
- Create: `admin-config/internal/model/git_config.go`
- Create: `admin-config/internal/handler/git.go`
- Create: `admin-config/internal/service/git.go`

**Step 1: 创建 Model**

```go
// admin-config/internal/model/git_config.go
package model

type GitConfig struct {
	ID            int64  `json:"id" gorm:"primaryKey"`
	Name          string `json:"name" gorm:"size:100;not null"`
	Platform      string `json:"platform" gorm:"size:20;not null"`
	BaseURL       string `json:"base_url" gorm:"size:255;not null"`
	AccessToken   string `json:"-" gorm:"size:255;not null"`
	WebhookSecret string `json:"webhook_secret,omitempty"`
	SSHKey        string `json:"-" gorm:"type:text"`
	ExtraConfig   string `json:"extra_config" gorm:"type:json"`
	IsDefault     int    `json:"is_default" gorm:"default:0"`
	Status        int    `json:"status" gorm:"default:1"`
	TenantID      int64  `json:"tenant_id" gorm:"default:0"`
	AdminID       int64  `json:"admin_id" gorm:"not null"`
	CreateTime    int64  `json:"create_time"`
	UpdateTime    int64  `json:"update_time"`
}

func (GitConfig) TableName() string {
	return "sys_git_config"
}

type GitConfigCreate struct {
	Name          string `json:"name" binding:"required"`
	Platform      string `json:"platform" binding:"required"`
	BaseURL       string `json:"base_url" binding:"required"`
	AccessToken   string `json:"access_token" binding:"required"`
	WebhookSecret string `json:"webhook_secret"`
	SSHKey        string `json:"ssh_key"`
}

type GitConfigUpdate struct {
	Name          string `json:"name"`
	BaseURL       string `json:"base_url"`
	AccessToken   string `json:"access_token"`
	WebhookSecret string `json:"webhook_secret"`
	SSHKey        string `json:"ssh_key"`
	Status        *int   `json:"status"`
}
```

**Step 2: Commit**

```bash
git add admin-config/internal/model/git_config.go
git commit -m "feat(config): add Git config model"
```

---

## Task 5: 前端 LLM 配置页面

**Files:**
- Create: `admin-frontend/src/pages/system/llm/index.tsx`
- Create: `admin-frontend/src/services/llm.ts`

**Step 1: 创建 Service**

```typescript
// admin-frontend/src/services/llm.ts
import request from '@/utils/request';

export const llmService = {
  list: (params?: any) => request.get('/api/config/llm', { params }),
  get: (id: number) => request.get(`/api/config/llm/${id}`),
  create: (data: any) => request.post('/api/config/llm', data),
  update: (id: number, data: any) => request.put(`/api/config/llm/${id}`, data),
  delete: (id: number) => request.delete(`/api/config/llm/${id}`),
  test: (id: number) => request.post(`/api/config/llm/${id}/test`),
  setDefault: (id: number) => request.post(`/api/config/llm/${id}/default`),
};
```

**Step 2: 创建页面组件 (简化版)**

```tsx
// admin-frontend/src/pages/system/llm/index.tsx
import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Select, InputNumber, Switch, message, Space, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, ApiOutlined, StarOutlined } from '@ant-design/icons';
import { llmService } from '@/services/llm';

const LLMConfigPage: React.FC = () => {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form] = Form.useForm();

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '配置名称', dataIndex: 'name' },
    { title: '提供商', dataIndex: 'provider' },
    { title: '模型', dataIndex: 'model_name' },
    { title: 'Base URL', dataIndex: 'base_url', ellipsis: true },
    { title: '默认', dataIndex: 'is_default', render: (v: number) => v ? '★' : '-' },
    { title: '状态', dataIndex: 'status', render: (v: number) => v ? '启用' : '禁用' },
    {
      title: '操作', width: 200, render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<ApiOutlined />} onClick={() => handleTest(record.id)}>测试</Button>
          <Button size="small" icon={<StarOutlined />} onClick={() => handleSetDefault(record.id)}>默认</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
          <Popconfirm title="确定删除?" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      )
    },
  ];

  useEffect(() => { fetchData(); }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await llmService.list();
      setData(res.data || []);
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async (id: number) => {
    try {
      await llmService.test(id);
      message.success('连接成功');
    } catch (e) {
      message.error('连接失败');
    }
  };

  const handleSetDefault = async (id: number) => {
    await llmService.setDefault(id);
    fetchData();
    message.success('已设为默认');
  };

  const handleEdit = (record: any) => {
    setEditingId(record.id);
    form.setFieldsValue(record);
    setModalVisible(true);
  };

  const handleDelete = async (id: number) => {
    await llmService.delete(id);
    fetchData();
    message.success('删除成功');
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    if (editingId) {
      await llmService.update(editingId, values);
    } else {
      await llmService.create(values);
    }
    setModalVisible(false);
    form.resetFields();
    setEditingId(null);
    fetchData();
    message.success('保存成功');
  };

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>新建配置</Button>
      </div>
      <Table columns={columns} dataSource={data} rowKey="id" loading={loading} />
      <Modal
        title={editingId ? '编辑配置' : '新建配置'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => { setModalVisible(false); form.resetFields(); setEditingId(null); }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="配置名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="provider" label="提供商" rules={[{ required: true }]}>
            <Select options={[
              { value: 'openai', label: 'OpenAI' },
              { value: 'anthropic', label: 'Anthropic' },
              { value: 'azure', label: 'Azure OpenAI' },
              { value: 'custom', label: '自定义' },
            ]} />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL" rules={[{ required: true }]}>
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>
          <Form.Item name="api_key" label="API Key" rules={[{ required: !editingId }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="model_name" label="模型名称" rules={[{ required: true }]}>
            <Input placeholder="gpt-4o / claude-3-5-sonnet-20241022" />
          </Form.Item>
          <Form.Item name="max_tokens" label="Max Tokens">
            <InputNumber min={1} max={128000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="temperature" label="Temperature">
            <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default LLMConfigPage;
```

**Step 3: Commit**

```bash
git add admin-frontend/src/pages/system/llm/ admin-frontend/src/services/llm.ts
git commit -m "feat(frontend): add LLM config page"
```

---

## Task 6: 前端 Git 配置页面

**Files:**
- Create: `admin-frontend/src/pages/system/git/index.tsx`
- Create: `admin-frontend/src/services/git.ts`

**Step 1: 创建页面 (复用 LLM 页面模式)**

```typescript
// admin-frontend/src/services/git.ts
import request from '@/utils/request';

export const gitService = {
  list: (params?: any) => request.get('/api/config/git', { params }),
  get: (id: number) => request.get(`/api/config/git/${id}`),
  create: (data: any) => request.post('/api/config/git', data),
  update: (id: number, data: any) => request.put(`/api/config/git/${id}`, data),
  delete: (id: number) => request.delete(`/api/config/git/${id}`),
  test: (id: number) => request.post(`/api/config/git/${id}/test`),
  setDefault: (id: number) => request.post(`/api/config/git/${id}/default`),
  repos: (id: number) => request.get(`/api/config/git/${id}/repos`),
};
```

**Step 2: Commit**

```bash
git add admin-frontend/src/pages/system/git/ admin-frontend/src/services/git.ts
git commit -m "feat(frontend): add Git config page"
```

---

## Task 7: admin-agent HTTP Streaming

**Files:**
- Modify: `admin-agent/internal/handler/chat.go`
- Modify: `admin-agent/internal/router/router.go`

**Step 1: 添加流式接口**

在 handler/chat.go 添加:

```go
// StreamChat HTTP流式对话
func StreamChat(c *gin.Context) {
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("Connection", "keep-alive")

	var req ChatRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.SSEvent("error", gin.H{"message": "参数错误"})
		return
	}

	streamChan, err := agentService.StreamChat(c.Request.Context(), &req)
	if err != nil {
		c.SSEvent("error", gin.H{"message": err.Error()})
		return
	}

	for {
		select {
		case chunk, ok := <-streamChan:
			if !ok {
				c.SSEvent("done", gin.H{})
				return
			}
			c.SSEvent("message", chunk)
			c.Writer.Flush()
		case <-c.Request.Context().Done():
			return
		}
	}
}
```

**Step 2: 添加路由**

```go
// router/router.go 添加
agent.POST("/chat/stream", handler.StreamChat)
```

**Step 3: Commit**

```bash
git add admin-agent/internal/
git commit -m "feat(agent): add HTTP streaming chat endpoint"
```

---

## Task 8: 前端流式对话组件

**Files:**
- Modify: `admin-frontend/src/pages/agent/chat/index.tsx`

**Step 1: 添加流式请求函数**

```typescript
const streamChat = async (message: string, sessionId: string, onChunk: (text: string) => void) => {
  const response = await fetch('/api/agent/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${localStorage.getItem('token')}`
    },
    body: JSON.stringify({ message, session_id: sessionId })
  });

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (reader) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          if (data.type === 'content') {
            onChunk(data.content);
          }
        } catch (e) {}
      }
    }
  }
};
```

**Step 2: Commit**

```bash
git add admin-frontend/src/pages/agent/chat/
git commit -m "feat(frontend): add streaming chat support"
```

---

## Task 9: 网关路由配置

**Files:**
- Modify: `admin-gateway/config.yaml`
- Modify: `admin-gateway/internal/router/router.go`

**Step 1: 添加 config 服务路由**

```yaml
# config.yaml 添加
services:
  config:
    host: localhost
    port: 8085
```

**Step 2: Commit**

```bash
git add admin-gateway/
git commit -m "feat(gateway): add admin-config routes"
```

---

## Task 10: 集成测试与启动

**Files:**
- Modify: `docker/docker-compose.yml`
- Modify: `start.sh`

**Step 1: 添加 admin-config 到 docker-compose**

**Step 2: 更新 start.sh 启动脚本**

**Step 3: 最终 Commit**

```bash
git add .
git commit -m "feat: core features complete - LLM config, Git config, HTTP streaming"
```

---

## 执行顺序

| 顺序 | Task | 依赖 | 分配角色 |
|------|------|------|---------|
| 1 | Task 1 | 无 | backend-dev-1 |
| 2 | Task 2, 3, 4 | Task 1 | backend-dev-1 |
| 5, 6 | Task 5, 6 | Task 3, 4 | frontend-dev-2 |
| 7, 8 | Task 7, 8 | 无 | backend-dev-3 |
| 9 | Task 9 | Task 2 | backend-dev-1 |
| 10 | Task 10 | All | backend-dev-5 |
