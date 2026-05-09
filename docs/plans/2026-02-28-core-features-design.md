# 核心功能增强设计方案

**日期**: 2026-02-28
**状态**: 已批准
**方案**: A - 统一配置服务

---

## 一、需求概述

1. **大模型配置**: 支持任何 OpenAI 兼容 API 的完全自定义配置
2. **Git 平台配置**: 支持 GitLab + GitHub + Gitee 多平台
3. **项目角色体系**: 新建 Owner/Maintainer/Developer 角色体系
4. **HTTP Streaming**: 使用 HTTP 流式输出替代 SSE
5. **Deploy 服务完善**: 完成 Git pull/镜像推送/回滚等功能

---

## 二、架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    React Frontend (3000)                    │
│  系统管理: 用户/角色/菜单/租户/LLM配置/Git配置              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Go Gateway (8080)                        │
│              JWT验证 → 权限校验 → 路由转发                  │
└─────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│admin-python │ │admin-config │ │ admin-agent │ │admin-deploy │
│   (8081)    │ │   (8085)    │ │   (8084)    │ │   (8083)    │
│ 用户/权限   │ │ LLM/Git配置 │ │ AI分身系统  │ │ 部署管理    │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
```

---

## 三、数据库设计

### 3.1 大模型配置表 (sys_llm_config)

```sql
CREATE TABLE sys_llm_config (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL COMMENT '配置名称',
    provider VARCHAR(50) NOT NULL COMMENT '提供商: openai/anthropic/azure/custom',
    base_url VARCHAR(255) NOT NULL COMMENT 'API Base URL',
    api_key VARCHAR(255) NOT NULL COMMENT 'API Key (AES加密存储)',
    model_name VARCHAR(100) NOT NULL COMMENT '模型名称',
    max_tokens INT DEFAULT 4096 COMMENT '最大Token',
    temperature DECIMAL(3,2) DEFAULT 0.7 COMMENT '温度参数',
    extra_config JSON COMMENT '额外配置(headers/params)',
    is_default TINYINT DEFAULT 0 COMMENT '是否默认: 0否 1是',
    status TINYINT DEFAULT 1 COMMENT '状态: 0禁用 1启用',
    tenant_id BIGINT DEFAULT 0 COMMENT '租户ID',
    admin_id BIGINT NOT NULL COMMENT '创建者ID',
    create_time BIGINT NOT NULL COMMENT '创建时间(毫秒)',
    update_time BIGINT NOT NULL COMMENT '更新时间(毫秒)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='大模型配置表';
```

### 3.2 Git 平台配置表 (sys_git_config)

```sql
CREATE TABLE sys_git_config (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL COMMENT '配置名称',
    platform VARCHAR(20) NOT NULL COMMENT '平台: gitlab/github/gitee/gitea',
    base_url VARCHAR(255) NOT NULL COMMENT 'Git服务URL',
    access_token VARCHAR(255) NOT NULL COMMENT 'Access Token (AES加密)',
    webhook_secret VARCHAR(255) COMMENT 'Webhook密钥',
    ssh_key TEXT COMMENT 'SSH私钥(可选)',
    extra_config JSON COMMENT '额外配置',
    is_default TINYINT DEFAULT 0 COMMENT '是否默认',
    status TINYINT DEFAULT 1 COMMENT '状态: 0禁用 1启用',
    tenant_id BIGINT DEFAULT 0 COMMENT '租户ID',
    admin_id BIGINT NOT NULL COMMENT '创建者ID',
    create_time BIGINT NOT NULL COMMENT '创建时间(毫秒)',
    update_time BIGINT NOT NULL COMMENT '更新时间(毫秒)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Git平台配置表';
```

### 3.3 项目成员表 (sys_project_member)

```sql
CREATE TABLE sys_project_member (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    project_id BIGINT NOT NULL COMMENT '项目ID',
    project_type VARCHAR(20) NOT NULL COMMENT '项目类型: agent/deploy',
    admin_id BIGINT NOT NULL COMMENT '用户ID',
    role VARCHAR(20) NOT NULL COMMENT '角色: owner/maintainer/developer',
    permissions JSON COMMENT '细粒度权限列表',
    added_by BIGINT COMMENT '添加者ID',
    create_time BIGINT NOT NULL COMMENT '创建时间(毫秒)',
    update_time BIGINT NOT NULL COMMENT '更新时间(毫秒)',
    UNIQUE KEY uk_project_admin (project_id, project_type, admin_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目成员表';
```

### 3.4 项目表扩展

```sql
-- agent_project 扩展
ALTER TABLE agent_project ADD COLUMN git_config_id BIGINT DEFAULT 0 COMMENT 'Git配置ID';
ALTER TABLE agent_project ADD COLUMN llm_config_id BIGINT DEFAULT 0 COMMENT 'LLM配置ID';

-- deploy_project 扩展
ALTER TABLE deploy_project ADD COLUMN git_config_id BIGINT DEFAULT 0 COMMENT 'Git配置ID';
```

---

## 四、API 设计

### 4.1 LLM 配置 API (admin-config:8085)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/config/llm` | 获取LLM配置列表 |
| GET | `/api/config/llm/:id` | 获取单个配置 |
| POST | `/api/config/llm` | 创建配置 |
| PUT | `/api/config/llm/:id` | 更新配置 |
| DELETE | `/api/config/llm/:id` | 删除配置 |
| POST | `/api/config/llm/:id/test` | 测试连接 |
| POST | `/api/config/llm/:id/default` | 设为默认 |

### 4.2 Git 配置 API (admin-config:8085)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/config/git` | 获取Git配置列表 |
| GET | `/api/config/git/:id` | 获取单个配置 |
| POST | `/api/config/git` | 创建配置 |
| PUT | `/api/config/git/:id` | 更新配置 |
| DELETE | `/api/config/git/:id` | 删除配置 |
| POST | `/api/config/git/:id/test` | 测试连接 |
| POST | `/api/config/git/:id/default` | 设为默认 |
| GET | `/api/config/git/:id/repos` | 获取仓库列表 |

### 4.3 项目成员 API (admin-python:8081)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/project/member` | 获取项目成员列表 |
| POST | `/api/project/member` | 添加成员 |
| PUT | `/api/project/member/:id` | 更新成员角色 |
| DELETE | `/api/project/member/:id` | 移除成员 |
| GET | `/api/project/my` | 获取我的项目列表 |

### 4.4 HTTP Streaming API (admin-agent:8084)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/agent/chat/stream` | 流式对话 |
| POST | `/api/agent/chat` | 非流式对话(保留) |

---

## 五、权限设计

### 5.1 项目角色权限矩阵

| 权限 | Owner | Maintainer | Developer |
|------|-------|------------|-----------|
| 查看项目 | ✅ | ✅ | ✅ |
| 编辑项目配置 | ✅ | ✅ | ❌ |
| 添加/移除成员 | ✅ | ❌ | ❌ |
| 修改成员角色 | ✅ | ❌ | ❌ |
| 执行部署 | ✅ | ✅ | ❌ |
| 回滚部署 | ✅ | ✅ | ❌ |
| 查看日志 | ✅ | ✅ | ✅ |
| 删除项目 | ✅ | ❌ | ❌ |

### 5.2 前端菜单配置

```sql
-- 系统管理下新增菜单
INSERT INTO sys_menu (parent_id, name, path, component, permission, icon, type, visible, sort) VALUES
(1, '大模型配置', '/system/llm', 'system/llm/index', 'system_llm_list', 'robot', 1, 1, 50),
(1, 'Git配置', '/system/git', 'system/git/index', 'system_git_list', 'github', 1, 1, 51);
```

---

## 六、HTTP Streaming 实现

### 6.1 后端实现 (Go)

```go
// StreamChat 流式对话处理
func (h *Handler) StreamChat(c *gin.Context) {
    // 设置流式响应头
    c.Header("Content-Type", "text/event-stream")
    c.Header("Cache-Control", "no-cache")
    c.Header("Connection", "keep-alive")
    c.Header("Transfer-Encoding", "chunked")

    var req ChatRequest
    if err := c.ShouldBindJSON(&req); err != nil {
        c.SSEvent("error", gin.H{"message": "参数错误"})
        return
    }

    // 获取流式channel
    streamChan, err := h.service.StreamChat(c.Request.Context(), &req)
    if err != nil {
        c.SSEvent("error", gin.H{"message": err.Error()})
        return
    }

    // 流式输出
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

### 6.2 前端实现 (TypeScript)

```typescript
async function streamChat(message: string, sessionId: string) {
  const response = await fetch('/api/agent/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({ message, session_id: sessionId })
  });

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();

  while (reader) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        if (data.type === 'done') {
          return;
        }
        // 更新UI显示增量内容
        appendMessage(data.content);
      }
    }
  }
}
```

---

## 七、服务依赖

### 7.1 admin-config 服务 (新建)

```
admin-config/
├── cmd/
│   └── main.go
├── internal/
│   ├── config/
│   ├── handler/
│   │   ├── llm.go
│   │   └── git.go
│   ├── service/
│   │   ├── llm.go
│   │   └── git.go
│   ├── router/
│   └── middleware/
├── pkg/
│   └── crypto/          # AES加解密
└── config.yaml
```

### 7.2 端口分配

| 服务 | 端口 | 说明 |
|------|------|------|
| admin-frontend | 3000 | React前端 |
| admin-gateway | 8080 | API网关 |
| admin-python | 8081 | 用户权限服务 |
| admin-generator | 8082 | 代码生成 |
| admin-deploy | 8083 | 部署管理 |
| admin-agent | 8084 | AI分身系统 |
| admin-config | 8085 | **配置服务(新建)** |

---

## 八、实施优先级

| 优先级 | 模块 | 工作量 |
|--------|------|--------|
| P0 | 数据库 Schema 更新 | 0.5天 |
| P0 | admin-config 服务搭建 | 1天 |
| P0 | LLM 配置 CRUD + 前端页面 | 1天 |
| P0 | Git 配置 CRUD + 前端页面 | 1天 |
| P1 | HTTP Streaming 实现 | 1天 |
| P1 | 项目角色体系 | 1天 |
| P2 | Deploy 服务完善 | 1天 |
| P2 | 集成测试 | 0.5天 |

---

## 九、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| API Key 安全 | 高 | AES加密存储，传输使用HTTPS |
| 流式连接中断 | 中 | 前端实现重连机制 |
| 多平台 Git 差异 | 中 | 抽象统一接口，适配器模式 |

---

*设计文档版本: 1.0*
*批准时间: 2026-02-28*
