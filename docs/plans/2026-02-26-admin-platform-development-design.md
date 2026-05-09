# Admin Platform 完整开发设计

## 概述

本文档描述了 Admin Platform 后台管理系统的完整开发计划，采用分层并行开发策略，分三个阶段完成所有功能模块。

## 开发策略

**方案 A：分层并行**

按技术层并行开发，每个模块的后端+前端一起完成后再做下一个模块。

**优点**：
- 每个模块完成后立即可用
- 可以边开发边测试
- 接口契约可以边做边调整
- 风险可控

## 阶段划分

### 阶段1: 系统管理模块

**目标**：完成用户、角色、菜单、租户的完整 CRUD 功能

| 功能 | 后端 API | 前端页面 | 优先级 |
|------|----------|----------|--------|
| 用户管理 | SystemAdminController | AdminList | P0 |
| 角色管理 | SystemGroupController | GroupList | P0 |
| 菜单管理 | SystemMenuController | MenuList | P1 |
| 租户管理 | SystemTenantController | TenantList | P1 |

**关键技术点**：
- 菜单动态加载（根据用户权限过滤）
- 角色权限配置（树形权限选择）
- 多租户数据隔离

### 阶段2: 代码生成模块

**目标**：完成基于 Claude API 的对话式代码生成功能

| 功能 | 后端 API | 前端页面 | 优先级 |
|------|----------|----------|--------|
| 功能配置 | GeneratorConfigController | GeneratorConfig | P0 |
| 字段配置 | GeneratorFieldController | - | P0 |
| Claude 集成 | GeneratorChatController | GeneratorChat | P0 |
| 代码预览/下载 | GeneratorPreviewController | - | P1 |

**关键技术点**：
- Claude API 流式响应
- 代码模板引擎
- 实时对话界面

### 阶段3: 部署管理模块

**目标**：完成 Docker 容器化部署管理功能

| 功能 | 后端 API | 前端页面 | 优先级 |
|------|----------|----------|--------|
| 项目配置 | DeployProjectController | DeployProject | P0 |
| 部署任务 | DeployTaskController | DeployTask | P0 |
| 容器管理 | DeployContainerController | - | P1 |
| 日志查看 | DeployLogController | - | P1 |

**关键技术点**：
- Docker SDK 集成
- 任务异步执行
- 实时日志流

## 技术架构

```
┌──────────────────────────────────────────────────────────────┐
│                    前端 (React + Ant Design)                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐            │
│  │ 系统管理 │ │ 代码生成 │ │ 部署管理 │ │ 通用组件 │            │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘            │
│       │           │           │           │                  │
│       └───────────┴─────┬─────┴───────────┘                  │
│                         │ API (axios)                        │
└─────────────────────────┼────────────────────────────────────┘
                          │
┌─────────────────────────┼────────────────────────────────────┐
│                    网关 (Go + Gin)                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ JWT认证 → 权限校验 → 路由转发 → 限流                    │   │
│  └──────────────────────────────────────────────────────┘   │
│           │              │              │                    │
└───────────┼──────────────┼──────────────┼────────────────────┘
            │              │              │
     ┌──────▼──────┐ ┌─────▼─────┐ ┌──────▼──────┐
     │Python Backend│ │    Go     │ │     Go      │
     │   (8081)    │ │ Generator │ │   Deploy    │
     │             │ │   (8082)  │ │   (8083)    │
     └──────┬──────┘ └─────┬─────┘ └──────┬──────┘
            │              │              │
     ┌──────▼──────────────▼──────────────▼──────┐
     │         MySQL + Redis                      │
     └────────────────────────────────────────────┘
```

## API 设计规范

### 统一响应格式

```json
{
  "code": 200,
  "message": "success",
  "data": {},
  "timestamp": 1772088000000
}
```

### 错误码定义

| 错误码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未登录/Token过期 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

### 接口路径规范

| 模块 | 路径前缀 | 示例 |
|------|----------|------|
| 认证 | `/api/auth/*` | `/api/auth/login` |
| 系统管理 | `/api/system/*` | `/api/system/admin/list` |
| 代码生成 | `/api/generator/*` | `/api/generator/config/list` |
| 部署管理 | `/api/deploy/*` | `/api/deploy/project/list` |

### CRUD 接口规范

```
GET    /{module}/{entity}/list      # 列表查询（支持分页、筛选）
GET    /{module}/{entity}/{id}      # 详情查询
POST   /{module}/{entity}           # 新增
PUT    /{module}/{entity}/{id}      # 更新
DELETE /{module}/{entity}/{id}      # 删除
```

## 性能要求

| 指标 | 目标值 |
|------|--------|
| API 响应时间 | < 200ms (P95) |
| 列表页加载 | < 1s |
| 并发用户数 | 100+ |
| 数据库查询 | < 50ms |

## 技术栈

### 后端
- **Python**: FastAPI + SQLAlchemy
- **Go**: Gin + GORM
- **数据库**: MySQL 8.0
- **缓存**: Redis 7

### 前端
- **框架**: React 18 + TypeScript
- **UI**: Ant Design 5
- **状态**: Zustand
- **构建**: Vite

## 部署架构

```yaml
services:
  frontend:
    image: nginx
    ports: ["3000:80"]

  gateway:
    image: admin-gateway
    ports: ["8080:8080"]

  backend:
    image: admin-python
    ports: ["8081:8081"]

  generator:
    image: admin-generator
    ports: ["8082:8082"]

  deploy:
    image: admin-deploy
    ports: ["8083:8083"]

  mysql:
    image: mysql:8.0
    ports: ["3306:3306"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
```
