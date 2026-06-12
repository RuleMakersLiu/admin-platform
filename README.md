# Admin Platform - AI 驱动的项目生命周期管理平台

> 通过 6 个 AI Agent 协作，自动完成从需求分析、代码生成、测试到部署的完整开发流程。
> 支持 Java/PHP/Go/Python/Node.js 等多语言项目。

## 架构概览

```
┌──────────────────────────────────────────────────────┐
│            React Frontend (3000)                      │
│   Vite + Ant Design 5 + Zustand | 暗色科技风 UI       │
└──────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│            Go Gateway (8080)                          │
│   JWT 认证 → RBAC 权限 → 路由转发 → 限流 → 租户隔离   │
└──────────────────────────────────────────────────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
│  Python    │ │Go Generator│ │  Go Deploy  │ │  Python    │
│  Backend   │ │  (8082)    │ │   (8083)    │ │   Agent    │
│  (8081)    │ │ 代码生成   │ │ Docker部署  │ │  (8084)    │
│ AI Agents  │ │ 项目管理   │ │ CI/CD流水线  │ │  语音/技能  │
└────────────┘ └────────────┘ └────────────┘ └────────────┘
       │              │              │
       ▼              ▼              ▼
┌──────────────────────────────────────────────────────┐
│  PostgreSQL (5432) + Redis (6379)                     │
└──────────────────────────────────────────────────────┘
```

## 技术栈

| 服务 | 技术 | 端口 | 说明 |
|------|------|------|------|
| React 前端 | Vite + Ant Design 5 + Zustand | 3000 | 暗色科技风管理后台 |
| Go 网关 | Gin + JWT + Redis | 8080 | 统一入口，认证鉴权 |
| Python 后端 | FastAPI + SQLAlchemy | 8081 | 核心业务，AI Agent 编排 |
| Go 代码生成 | Gin + Claude API | 8082 | 项目模板，代码生成 |
| Go 部署 | Gin + Docker SDK | 8083 | 容器化部署流水线 |
| Go 配置中心 | Gin | 8085 | 系统配置管理 |
| PostgreSQL | 15+ | 5432 | 主数据库 |
| Redis | 7.x | 6379 | 缓存 + Session |

## 6 个 AI Agent

| Agent | 标识 | 职责 | 流水线阶段 |
|-------|------|------|-----------|
| 产品经理 | PM | 需求分析、PRD 文档 | requirement |
| 项目经理 | PJM | 任务拆分、API 契约、交付包 | delivery, commit |
| 前端开发 | FE | 前端页面开发 | frontend_dev, prototype |
| 后端开发 | BE | 后端 API 开发 | backend_dev |
| QA 工程师 | QA | 代码审查、自动化测试 | code_review, testing |
| 总结报告 | RPT | 进度汇总、日报 | report |

## 核心功能

### AI 开发流水线
- 从自然语言需求到可部署代码的全自动流程
- 11 个阶段：需求分析 → 页面设计 → 原型预览 → 交付包 → 前端开发 → 后端开发 → 代码审查 → 测试 → 提交 → 部署 → 报告
- 前端/后端并行开发（Fan-out 模式）
- 代码审查失败自动回退修复
- 每阶段可人工确认或自动执行

### 项目知识库
- 导入 Git 项目后自动分析架构（语言、框架、API 规范、权限模型）
- 项目级 Skill：沉淀页面识别、路由菜单、接口契约、权限模型、验证命令等项目规则
- 上下文工程：语义检索 + 项目知识注入 LLM prompt
- 项目关系图谱：维护前端、接口层、服务层、Core 等关联项目之间的 `uses_api` / `depends_on` 关系
- 图谱维护闭环：重新分析项目 → 生成项目关系图谱 → 多角色规则审查 → 持久化图谱维护报告

### 项目关系图谱
- 入口：系统管理 → 知识库 → 知识图谱
- 数据源：默认读取项目知识库 `ProjectKnowledge`，不混入流水线交付记录或普通知识条目
- 展示能力：节点拖拽、画布平移缩放、关系箭头、关系标签、节点详情、相邻关系高亮
- 手动维护：项目列表页提供“重建图谱”，默认基于当前已分析项目快速复核和重建关系
- 自动维护：单项目“分析”会重新读取项目源码、更新 Project Skill，并同步刷新项目关系图谱
- 审查规则：检查重复节点、孤立节点、前端到接口层、接口层到服务层、服务层到 Core 的关系完整性

### 多语言代码生成
- Java Spring Boot + MyBatis-Plus
- PHP（BFF/API 转发层或 Laravel）
- Go Gin 微服务
- Python FastAPI
- Node.js / Vue / React 前端

### 项目管理
- 项目导入（Git clone + 自动检测语言框架）
- 代码预览、下载、测试
- 关联 Git 配置、LLM 配置、知识库

### 技能市场
- 内置 16 个技能（需求分析、代码审查、部署等）
- 支持新增、编辑、删除技能
- 技能自动被 AI Agent 调用

### 系统管理
- 多租户数据隔离（tenant_id）
- RBAC 权限体系（用户组 + 菜单权限）
- LLM 多提供商配置（智谱/Anthropic/OpenAI）
- Git 多平台配置（GitLab/GitHub/Gitee）

## 快速开始

### 环境要求

- Python 3.11+
- Go 1.21+
- Node.js 18+
- PostgreSQL 15+
- Redis 7.x+

### 1. 初始化数据库

```bash
psql -U postgres -f database/schema.sql
```

### 2. 启动后端服务

```bash
# Python 后端 (AI Agents + 核心业务)
cd admin-python
pip install -e .
python -m app.main

# Go 网关
cd admin-gateway && go mod tidy && go run cmd/main.go

# Go 代码生成
cd admin-generator && go mod tidy && go run cmd/server/main.go

# Go 部署服务
cd admin-deploy && go mod tidy && go run cmd/server/main.go
```

### 3. 启动前端

```bash
cd admin-frontend
npm install
npm run dev
```

### 4. Docker Compose 一键启动

```bash
cd docker && docker-compose up -d
```

### 5. 访问系统

- 前端：http://localhost:3000
- API 文档：http://localhost:8081/docs
- 默认账号：`admin` / `admin123`

## 项目结构

```
admin-platform/
├── admin-python/          # Python 后端
│   └── app/
│       ├── ai/            # AI Agent 核心
│       │   ├── flow_manager.py   # 流水线引擎
│       │   ├── agents.py         # Agent 工厂
│       │   ├── skills.py         # 技能注册表
│       │   └── mcp_server.py     # MCP 协议
│       ├── api/           # API 路由
│       ├── core/          # 数据库、配置
│       ├── models/        # ORM 模型
│       ├── services/      # 业务逻辑
│       │   └── knowledge_service.py  # 知识库 + 语义搜索
│       └── skills/        # 技能定义 (SKILL.md)
├── admin-gateway/         # Go 网关 (JWT/权限/限流)
├── admin-generator/       # Go 代码生成 (模板/项目)
├── admin-deploy/          # Go 部署 (Docker/CI/CD)
├── admin-frontend/        # React 前端
│   └── src/
│       ├── pages/         # 页面
│       │   ├── pipeline/  # AI 开发流水线
│       │   ├── project/   # 项目管理
│       │   ├── skills/    # 技能市场
│       │   └── webchat/   # AI 对话
│       ├── services/      # API 服务
│       └── utils/         # 工具函数
├── database/
│   └── schema.sql         # 数据库建表脚本
└── docker/
    └── docker-compose.yml # 容器编排
```

## 使用指南

### 创建 AI 开发流水线

1. 进入「开发流水线」页面
2. 输入需求描述，例如："创建一个用户管理模块，支持增删改查和角色分配"
3. 可选：关联后端项目（Java/Go/Python）和前端项目（Vue/React/PHP）
4. 点击"启动流水线"
5. AI 自动完成：需求分析 → 页面设计 → 原型 → 代码 → 测试
6. 每阶段可人工审核确认，也可自动执行

### 导入项目

1. 进入「项目列表」页面
2. 点击"导入项目"
3. 输入 Git 仓库地址和分支
4. 系统自动检测语言和框架
5. 点击"分析"按钮，AI 自动分析项目架构

### 技能管理

1. 进入「技能市场」页面
2. 浏览分类和技能列表
3. 点击"新增技能"创建自定义技能
4. 技能会被 AI Agent 自动发现和使用

## API 端点

| 路径前缀 | 服务 | 说明 |
|---------|------|------|
| `/api/auth` | Gateway | 登录认证 |
| `/api/flow` | Python | AI 流水线 |
| `/api/skills` | Python | 技能系统 |
| `/api/system` | Gateway | 系统配置 |
| `/generator` | Generator | 代码生成 |
| `/deploy` | Deploy | 部署管理 |
| `/ws` | WebSocket | 实时通信 |

## License

MIT
