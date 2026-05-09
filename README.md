# 多智能体数字分身系统 - Admin Platform

基于 **Python + Go + React** 的多智能体协作平台，支持通过对话生成功能并完成打包发布。

## 技术栈

| 组件 | 技术 | 版本 | 端口 |
|------|------|------|------|
| **Python后端** | FastAPI + SQLAlchemy | 3.11+ | 8081 |
| **Go网关** | Gin | 1.21 | 8080 |
| **Go生成器** | Gin | 1.21 | 8082 |
| **Go部署** | Gin | 1.21 | 8083 |
| **Python Agent** | LangChain | 3.11+ | 8084 |
| **Go Config** | Gin | 1.21 | 8085 |
| **WebSocket** | Go + gorilla | 1.21 | 8086 |
| **React前端** | React + Ant Design | 18 + 5.x | 3000 |
| **PostgreSQL** | PostgreSQL | 15 | 5432 |
| **Redis** | Redis | 7.x | 6379 |

## 项目结构

```
admin-platform/
├── admin-python/          # Python后端 (FastAPI + AI Agents)
│   ├── app/               # 应用代码
│   │   ├── ai/            # AI分身 (PM/PJM/BE/FE/QA/RPT)
│   │   ├── api/           # API路由
│   │   ├── core/          # 核心配置
│   │   ├── messaging/     # 消息适配器 (Telegram/Discord/Slack/飞书)
│   │   └── services/      # 业务服务
│   └── tests/             # 测试
├── admin-gateway/         # Go网关 (JWT认证、权限校验、路由转发)
├── admin-generator/       # Go代码生成服务 (Claude API集成)
├── admin-deploy/          # Go部署服务 (Docker SDK)
├── admin-agent/           # Python智能体服务 (语音/技能市场)
├── admin-config/          # Go配置中心
├── admin-ws/              # Go WebSocket网关
├── admin-frontend/        # React前端 (Vite + Ant Design)
├── database/              # 数据库脚本
│   └── schema.sql         # 表结构
└── docker/                # Docker配置
    └── docker-compose.yml
```

## 快速开始

### 环境要求

- Python 3.11+
- Go 1.21+
- Node.js 18+
- PostgreSQL 15+
- Redis 7.x+
- Docker & Docker Compose (可选)

### 1. 初始化数据库

```bash
# PostgreSQL
psql -U postgres -f database/schema.sql
```

### 2. 启动后端服务

**Python后端:**
```bash
cd admin-python
pip install -e .
python -m app.main
```

**Go网关:**
```bash
cd admin-gateway
go mod tidy
go run cmd/main.go
```

**Go生成器:**
```bash
cd admin-generator
go mod tidy
go run cmd/server/main.go
```

**Go部署:**
```bash
cd admin-deploy
go mod tidy
go run cmd/server/main.go
```

### 3. 启动前端

```bash
cd admin-frontend
npm install
npm run dev      # Development
npm run build    # Production build
```

### 4. 使用Docker Compose (推荐)

```bash
cd docker
docker-compose up -d
```

## 默认账号

- 用户名: `admin`
- 密码: `admin123`
- Tenant ID: `1`

## 服务架构

```
┌─────────────────────────────────────────────┐
│         React Frontend (3000)               │
│         Vite + Ant Design + Zustand         │
└─────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│         Go Gateway (8080)                   │
│  JWT验证 → 权限校验 → 路由转发 → 限流       │
└─────────────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│Python Backend│ │Go Generator │ │ Go Deploy   │
│   (8081)    │ │   (8082)    │ │   (8083)    │
│  AI Agents  │ │  Code Gen   │ │  Pipeline   │
└─────────────┘ └─────────────┘ └─────────────┘
```

## 6个AI分身

| 分身 | 标识 | 职责 |
|------|------|------|
| 产品经理 | PM | 需求收集,输出PRD文档 |
| 项目经理 | PJM | 任务拆分、API契约定义 |
| 后端开发 | BE | 后端开发,BUG修复 |
| 前端开发 | FE | 前端开发,BUG修复 |
| 测试分身 | QA | 测试用例,BUG报告 |
| 总结分身 | RPT | 进度汇总,日报生成 |

## 核心功能

- ✅ 多智能体对话 (6个专业分身)
- ✅ 流式对话 (SSE实时输出)
- ✅ 项目管理 (卡片/表格视图)
- ✅ 任务管理 (Kanban看板)
- ✅ BUG跟踪 (状态流转)
- ✅ LLM配置 (多提供商+测试)
- ✅ Git配置 (多平台支持)
- ✅ 代码生成 (AI辅助)
- ✅ Docker部署 (容器管理)
- ✅ 用户认证 (JWT+租户隔离)
- ✅ 技能系统 (插件化技能架构)
- ✅ WebSocket网关 (实时双向通信)
- ✅ 多渠道消息 (Telegram/Discord/Slack/飞书)
- ✅ WebChat界面 (独立聊天页面)
- ✅ 语音能力 (TTS/STT)
- ✅ Canvas展示 (iframe沙箱渲染)
- ✅ 模型故障转移 (多LLM提供商自动切换)
- ✅ 技能市场 (技能分享/下载/评分)

## API文档

- **Python后端**: http://localhost:8081/docs (Swagger)
- **Go网关**: http://localhost:8080/api

## 访问地址

- **前端**: http://localhost:3000
- **网关 API**: http://localhost:8080/api
- **WebSocket**: ws://localhost:8080/ws/connect
- **技能市场**: http://localhost:3000/skills/market
- **WebChat**: http://localhost:3000/webchat

---

**更新时间：** 2026-03-08
