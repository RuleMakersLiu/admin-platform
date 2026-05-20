---
id: task_breakdown
name: task-breakdown
description: "Break down requirements into development tasks with dependency analysis and estimation. 将需求文档分解为具体的开发任务，包含前后端任务分配、依赖关系和工时估算。"
version: 1.1.0
category: analysis
agent_type: PJM
metadata:
  hermes:
    tags: [task, breakdown, planning, wbs, estimation, gantt]
    related_skills: [requirement-analysis, backend-development, frontend-development]
---

# 任务分解 (Task Breakdown)

## 概述

Task Breakdown 是项目经理分身 (PJM Agent) 的核心能力，负责将结构化的需求文档（PRD）拆解为可执行、可追踪、可交付的开发任务集合。输出的是一个完整的 **Delivery Package（交付包）**，其中包含任务列表、API 契约、数据库变更、依赖关系图和工时估算。

本 Skill 在 Pipeline 流水线中的位置：

```
requirement-analysis → task-breakdown → backend-development / frontend-development → test-generation → code-review → deploy
        (PM)                 (PJM)                    (BE / FE)                       (QA)              (QA)         (Deploy)
```

### 核心目标

1. **可执行性**：每个任务粒度控制在 2-8 小时，确保单一开发者可以在一个工作日内完成
2. **可追踪性**：每个任务有明确的输入、输出和验收标准
3. **可并行性**：通过依赖分析识别可并行执行的任务，最大化开发效率
4. **契约先行**：在编码开始前定义 API Contract 和数据库 Schema，确保前后端解耦

---

## 何时使用

- 需求分析阶段已完成，PRD 文档已就绪
- 项目经理需要制定 Sprint 计划和任务分配
- 需要识别功能模块之间的依赖关系
- 需要为前后端开发提供统一的 API 契约
- Pipeline 流水线从 requirement 阶段进入 planning 阶段

### 前置条件

- 已有结构化需求文档（由 requirement-analysis Skill 输出）
- 需求文档中包含明确的用户故事和验收标准
- 技术栈已确定（如 Spring Boot + Vue 2 / FastAPI + React）

### 不适用场景

- 需求尚未澄清或存在重大歧义（应先使用 requirement-analysis）
- 纯探索性任务或 PoC（Proof of Concept）
- 仅需 Bug 修复，不涉及新功能开发

---

## 任务分解方法论

### 1. WBS (Work Breakdown Structure)

采用自顶向下的分解策略，按照以下层级展开：

```
项目 (Project)
└── 功能模块 (Feature Module)
    ├── 后端任务 (Backend Task)
    ├── 前端任务 (Frontend Task)
    ├── 测试任务 (QA Task)
    └── 部署任务 (DevOps Task)
```

**分解步骤**：

1. **第一层**：按业务功能模块划分（如用户管理、权限管理、数据报表）
2. **第二层**：每个模块按技术层次划分（后端 / 前端 / 测试）
3. **第三层**：每个技术任务拆分为具体开发项（API 接口 / 数据库表 / 页面组件）

### 2. MECE 原则 (Mutually Exclusive, Collectively Exhaustive)

任务分解必须满足 MECE 原则：

- **互斥性 (Mutually Exclusive)**：不同任务之间没有功能重叠，每个功能点只出现在一个任务中
- **完备性 (Collectively Exhaustive)**：所有任务合在一起覆盖需求文档的全部功能点

**验证方法**：
- 将所有任务的描述合并，检查是否覆盖 PRD 中的每一条功能需求
- 检查任意两个任务之间是否存在共同的代码文件或数据库表变更
- 确认没有功能需求被遗漏

### 3. 任务粒度标准

| 指标 | 标准范围 | 说明 |
|------|---------|------|
| 单任务工时 | 2-8 小时 | 超过 8h 应继续拆分，低于 2h 应考虑合并 |
| 涉及文件数 | 1-5 个 | 超过 5 个文件说明职责过多 |
| API 接口数 | 1-3 个 | 单任务不宜涉及过多接口 |
| 数据库表 | 1-2 张 | 超过 2 张表应拆分为独立的数据建模任务 |
| UI 页面 | 1 个 | 每个页面对应一个前端任务 |

**粒度判断决策树**：

```
任务描述是否可以在一句话内说清楚？
├── 否 → 拆分为多个子任务
└── 是 → 是否可以在 8 小时内完成？
    ├── 否 → 按技术层次拆分（数据层 → 逻辑层 → 接口层 → 展示层）
    └── 是 → 是否涉及多个不相关的功能点？
        ├── 是 → 按功能点拆分
        └── 否 → 粒度合适，作为独立任务
```

### 4. 角色分配规则

| 角色 | 代号 | 职责范围 | 任务类型标记 |
|------|------|---------|-------------|
| Backend Developer | BE | API 接口、数据库模型、业务逻辑、中间件 | `backend` |
| Frontend Developer | FE | 页面组件、路由配置、状态管理、API 调用层 | `frontend` |
| QA Engineer | QA | 测试用例编写、集成测试、E2E 测试 | `testing` |
| DevOps | DevOps | 部署配置、环境搭建、CI/CD | `devops` |

**分配原则**：

- 前后端分离：后端任务和前端任务严格分开，通过 API 契约解耦
- 一个任务只分配给一个角色（避免模糊边界）
- QA 任务依赖于对应的后端 / 前端开发任务完成

---

## 依赖分析

### 1. 依赖类型

| 依赖类型 | 代号 | 含义 | 示例 |
|---------|------|------|------|
| Finish-to-Start (FS) | `FS` | 前置任务完成后，后续任务才能开始 | 数据库模型创建完成 → API 接口开发开始 |
| Start-to-Start (SS) | `SS` | 前置任务开始后，后续任务即可开始 | 后端 API 设计开始 → 前端页面设计开始 |
| Finish-to-Finish (FF) | `FF` | 前置和后续任务同时完成 | 前端联调完成 → 集成测试完成 |

**默认依赖类型为 FS**，除非有明确的并行或同步需求。

### 2. 依赖关系建模规则

```
数据库建模 → API 接口开发 → API 联调测试
     ↓              ↓              ↓
数据库迁移    前端页面开发    E2E 测试
                  ↑
             API 契约定义
```

**典型依赖链**：

1. **数据层先行**：`db_schema` → `model_code` → `repository_code`
2. **接口层依赖数据层**：`repository_code` → `service_code` → `controller_code`
3. **前端依赖接口契约**：`api_contract` → `frontend_page` → `frontend_integration`
4. **测试依赖开发完成**：`backend_complete` + `frontend_complete` → `integration_test`

### 3. 关键路径识别 (Critical Path)

关键路径是项目中最长的依赖链，决定了项目的最短完成时间。

**识别步骤**：

1. 构建任务依赖图（有向无环图 DAG）
2. 计算每个任务的最早开始时间 (ES) 和最晚开始时间 (LS)
3. 关键路径上的任务满足 ES = LS（没有浮动时间）
4. 关键路径上的任何延迟都会导致项目整体延期

**输出**：`critical_path` 数组，包含关键路径上的任务 ID 序列。

### 4. 并行执行策略 (Fan-out Pattern)

识别可并行执行的任务组，最大化开发效率。

**并行模式**：

```
                    ┌─ BE: 用户管理 API
API 契约定义 ──────┤
                    ├─ BE: 权限管理 API
                    │
                    ├─ FE: 用户管理页面
                    └─ FE: 权限管理页面
```

**并行条件**：
- 任务之间无依赖关系
- 任务分配给不同角色（避免同一角色资源冲突）
- 任务不涉及同一数据库表或代码文件

---

## 工时估算指南

### 1. T-shirt 尺寸到工时映射

| 尺寸 | 缩写 | 工时范围 | 典型场景 |
|------|------|---------|---------|
| Extra Small | XS | 1-2h | 配置变更、简单 CRUD 接口、文案修改 |
| Small | S | 2-4h | 单表 CRUD + 简单验证、基础表单页面 |
| Medium | M | 4-8h | 多表关联查询、复杂表单 + 校验规则 |
| Large | L | 8-16h | 拆分为 2-3 个 M 任务 |
| Extra Large | XL | 16h+ | 拆分为 3+ 个 M 任务，需重新评估 |

### 2. 复杂度因素评估

估算工时时需考虑以下复杂度因素：

#### 后端复杂度

| 因素 | 权重 | 说明 |
|------|------|------|
| API 端点数量 | +1h / endpoint | 每个端点需独立的请求验证、逻辑处理、错误处理 |
| 数据库表变更 | +2h / 新表 | 建模、迁移脚本、Seed 数据 |
| 字段数量 | +0.5h / 10个字段 | Model 定义、验证规则、序列化 |
| 业务逻辑复杂度 | +2-4h | 状态机、审批流、多步操作 |
| 第三方集成 | +4-8h / 集成点 | SDK 接入、鉴权、错误处理、重试机制 |
| 权限控制 | +1h / 权限规则 | RBAC、数据权限、字段级权限 |
| 缓存策略 | +2h | Redis 缓存设计、失效策略 |
| 异步处理 | +3h | 消息队列、定时任务、WebSocket |

#### 前端复杂度

| 因素 | 权重 | 说明 |
|------|------|------|
| UI 组件数量 | +1h / 复杂组件 | Table、Form、Modal 等交互组件 |
| 表单字段数量 | +0.5h / 10个字段 | 表单布局、验证规则、联动 |
| 页面路由数 | +0.5h / 路由 | 路由配置、导航集成 |
| 状态管理 | +2h | 全局状态、跨组件通信 |
| API 调用数量 | +0.5h / API | 请求封装、Loading 状态、错误处理 |
| 响应式适配 | +2h | 移动端 / 平板适配 |
| 图表/可视化 | +3h / 图表 | ECharts / D3 集成 |

### 3. 缓冲策略 (Buffer)

| 场景 | 缓冲比例 | 说明 |
|------|---------|------|
| 熟悉技术栈，有参考实现 | 10-20% | 标准开发缓冲 |
| 熟悉技术栈，新业务逻辑 | 20-30% | 需要额外理解和设计时间 |
| 新技术栈，有文档支持 | 30-50% | 学习曲线 + 试错时间 |
| 新技术栈，无参考实现 | 50-80% | 大量试错和调试时间 |

**缓冲应用方式**：

```
估算工时 = 基础工时 x (1 + 缓冲比例)
```

---

## 交付包结构 (Delivery Package)

Task Breakdown 的核心输出是一个完整的 Delivery Package，包含以下部分：

### 1. API Contract 定义

采用 OpenAPI 3.0 / Swagger 风格定义接口契约，确保前后端解耦开发。

每个 API Contract 包含：

```json
{
  "contract_id": "API-001",
  "name": "用户列表查询接口",
  "method": "GET",
  "path": "/api/users",
  "description": "分页查询系统用户列表，支持按角色和状态过滤",
  "request": {
    "query_params": [
      {"name": "page", "type": "integer", "required": false, "default": 1},
      {"name": "page_size", "type": "integer", "required": false, "default": 20},
      {"name": "keyword", "type": "string", "required": false, "description": "搜索关键词"},
      {"name": "role_id", "type": "integer", "required": false, "description": "角色筛选"},
      {"name": "status", "type": "integer", "required": false, "description": "状态筛选"}
    ]
  },
  "response": {
    "200": {
      "type": "object",
      "properties": {
        "list": {
          "type": "array",
          "items": {"$ref": "#/components/schemas/UserVO"}
        },
        "total": {"type": "integer"},
        "page": {"type": "integer"},
        "page_size": {"type": "integer"}
      }
    }
  },
  "auth_required": true,
  "permissions": ["user:list"],
  "related_task_ids": ["TASK-BE-001", "TASK-FE-001"]
}
```

### 2. 数据库 Schema 变更

记录所有需要新增或修改的数据库对象：

```json
{
  "change_id": "DB-001",
  "type": "create_table",
  "table_name": "biz_order",
  "description": "订单主表，存储订单基本信息",
  "columns": [
    {"name": "id", "type": "BIGINT", "nullable": false, "primary_key": true, "auto_increment": true},
    {"name": "order_no", "type": "VARCHAR(64)", "nullable": false, "unique": true, "comment": "订单编号"},
    {"name": "user_id", "type": "BIGINT", "nullable": false, "index": true, "comment": "下单用户ID"},
    {"name": "total_amount", "type": "DECIMAL(12,2)", "nullable": false, "default": "0.00", "comment": "订单总金额"},
    {"name": "status", "type": "TINYINT", "nullable": false, "default": "0", "comment": "订单状态: 0待支付 1已支付 2已发货 3已完成 4已取消"},
    {"name": "tenant_id", "type": "BIGINT", "nullable": false, "index": true, "comment": "租户ID"},
    {"name": "create_time", "type": "BIGINT", "nullable": false, "comment": "创建时间(毫秒时间戳)"},
    {"name": "update_time", "type": "BIGINT", "nullable": false, "comment": "更新时间(毫秒时间戳)"},
    {"name": "is_deleted", "type": "INT", "nullable": false, "default": "0", "comment": "逻辑删除标记"}
  ],
  "indexes": [
    {"name": "idx_tenant_user", "columns": ["tenant_id", "user_id"]},
    {"name": "idx_order_no", "columns": ["order_no"], "unique": true}
  ],
  "migration_sql": "CREATE TABLE biz_order (...);",
  "related_task_ids": ["TASK-BE-001"]
}
```

**约定**：
- 所有业务表必须包含 `tenant_id`（多租户隔离）
- 时间字段统一使用 `BIGINT` 毫秒时间戳（`create_time`、`update_time`）
- 软删除字段 `is_deleted` 默认为 0

### 3. 前端页面列表与组件树

```json
{
  "page_id": "PAGE-001",
  "name": "用户管理列表页",
  "route": "/system/users",
  "permission": "system:user:list",
  "components": {
    "UserTable": {
      "type": "a-table",
      "features": ["search", "pagination", "sort", "filter"],
      "columns": ["用户名", "姓名", "角色", "状态", "创建时间", "操作"],
      "actions": ["编辑", "删除", "重置密码"]
    },
    "UserFormModal": {
      "type": "a-modal",
      "trigger": "新建/编辑按钮",
      "fields": ["username", "realname", "password", "role_id", "email", "phone", "status"]
    }
  },
  "api_calls": [
    {"name": "getUserList", "contract_id": "API-001"},
    {"name": "createUser", "contract_id": "API-002"},
    {"name": "updateUser", "contract_id": "API-003"},
    {"name": "deleteUser", "contract_id": "API-004"}
  ],
  "related_task_ids": ["TASK-FE-001"]
}
```

### 4. 后端服务列表

```json
{
  "service_id": "SVC-001",
  "name": "UserService",
  "module": "system",
  "description": "用户管理业务逻辑层",
  "methods": [
    {
      "name": "get_user_list",
      "signature": "async def get_user_list(tenant_id: int, page: int, page_size: int, keyword: str = None) -> Dict",
      "description": "分页查询用户列表",
      "returns": "PaginatedResult[UserVO]",
      "related_contract": "API-001"
    },
    {
      "name": "create_user",
      "signature": "async def create_user(tenant_id: int, user_data: UserCreateDTO) -> UserVO",
      "description": "创建新用户",
      "validations": ["用户名唯一性校验", "密码强度校验", "角色有效性校验"],
      "returns": "UserVO",
      "related_contract": "API-002"
    }
  ],
  "dependencies": ["UserRepository", "RoleRepository", "PasswordHasher"],
  "related_task_ids": ["TASK-BE-002"]
}
```

---

## 输出格式

Task Breakdown Skill 的输出为 JSON 结构的 Delivery Package：

```json
{
  "delivery_package": {
    "project_name": "项目名称",
    "source_requirement_id": "REQ-xxx",
    "created_by": "PJM",
    "created_at": 1716163200000,

    "tasks": [
      {
        "task_id": "TASK-BE-001",
        "task_code": "BE-USER-CRUD",
        "title": "用户管理 CRUD API 开发",
        "description": "实现用户管理的增删改查接口，包括分页查询、新建用户、编辑用户、删除用户、重置密码等 API 端点",
        "task_type": "backend",
        "assignee": "BE",
        "dependencies": ["TASK-DB-001"],
        "dependency_type": "FS",
        "estimated_hours": 6.0,
        "buffer_percentage": 20,
        "total_hours": 7.2,
        "priority": "P0",
        "status": "pending",
        "acceptance_criteria": [
          "GET /api/users 返回分页数据，支持关键词搜索和角色筛选",
          "POST /api/users 创建用户并返回完整用户信息",
          "PUT /api/users/:id 更新用户信息",
          "DELETE /api/users/:id 软删除用户",
          "所有接口包含 tenant_id 数据隔离",
          "所有接口包含 JWT 权限校验"
        ],
        "related_contracts": ["API-001", "API-002", "API-003", "API-004"],
        "related_db_changes": ["DB-001"],
        "tags": ["user-management", "crud", "api"]
      },
      {
        "task_id": "TASK-FE-001",
        "task_code": "FE-USER-PAGE",
        "title": "用户管理前端页面开发",
        "description": "开发用户管理列表页面，包含用户列表展示、搜索筛选、新建/编辑弹窗、删除确认等交互",
        "task_type": "frontend",
        "assignee": "FE",
        "dependencies": ["API-CONTRACT-001"],
        "dependency_type": "FS",
        "estimated_hours": 8.0,
        "buffer_percentage": 20,
        "total_hours": 9.6,
        "priority": "P0",
        "status": "pending",
        "acceptance_criteria": [
          "用户列表页面正确展示分页数据",
          "搜索和筛选功能正常工作",
          "新建用户弹窗表单验证完整",
          "编辑用户弹窗正确回填数据",
          "删除用户有确认提示",
          "操作成功/失败有消息提示"
        ],
        "related_contracts": ["API-001", "API-002", "API-003", "API-004"],
        "related_pages": ["PAGE-001"],
        "tags": ["user-management", "page", "form"]
      },
      {
        "task_id": "TASK-QA-001",
        "task_code": "QA-USER-TEST",
        "title": "用户管理模块测试用例",
        "description": "编写用户管理模块的单元测试和集成测试用例",
        "task_type": "testing",
        "assignee": "QA",
        "dependencies": ["TASK-BE-001", "TASK-FE-001"],
        "dependency_type": "FS",
        "estimated_hours": 4.0,
        "buffer_percentage": 20,
        "total_hours": 4.8,
        "priority": "P1",
        "status": "pending",
        "acceptance_criteria": [
          "覆盖所有 CRUD 操作的 Happy Path",
          "包含边界条件测试（空数据、超长输入、特殊字符）",
          "包含权限校验测试（未登录、无权限）",
          "测试覆盖率 > 80%"
        ],
        "related_task_ids": ["TASK-BE-001", "TASK-FE-001"],
        "tags": ["user-management", "testing"]
      }
    ],

    "api_contracts": [
      {
        "contract_id": "API-001",
        "name": "用户列表查询",
        "method": "GET",
        "path": "/api/users",
        "description": "分页查询用户列表",
        "request": { "query_params": [] },
        "response": { "200": { "type": "object" } },
        "auth_required": true,
        "permissions": ["user:list"]
      },
      {
        "contract_id": "API-002",
        "name": "创建用户",
        "method": "POST",
        "path": "/api/users",
        "description": "创建新用户",
        "request": { "body": {} },
        "response": { "200": { "type": "object" } },
        "auth_required": true,
        "permissions": ["user:create"]
      },
      {
        "contract_id": "API-003",
        "name": "更新用户",
        "method": "PUT",
        "path": "/api/users/:id",
        "description": "更新用户信息",
        "request": { "body": {} },
        "response": { "200": { "type": "object" } },
        "auth_required": true,
        "permissions": ["user:update"]
      },
      {
        "contract_id": "API-004",
        "name": "删除用户",
        "method": "DELETE",
        "path": "/api/users/:id",
        "description": "软删除用户",
        "request": {},
        "response": { "200": { "type": "object" } },
        "auth_required": true,
        "permissions": ["user:delete"]
      }
    ],

    "db_changes": [
      {
        "change_id": "DB-001",
        "type": "create_table",
        "table_name": "sys_user",
        "columns": [],
        "indexes": [],
        "migration_sql": ""
      }
    ],

    "dependencies": [
      {
        "from_task": "TASK-DB-001",
        "to_task": "TASK-BE-001",
        "type": "FS",
        "description": "数据库表创建完成后才能开始 API 开发"
      },
      {
        "from_task": "TASK-BE-001",
        "to_task": "TASK-FE-001",
        "type": "SS",
        "description": "API 契约定义完成后前端即可开始页面开发（SS 依赖：后端开始后前端即可开始）"
      },
      {
        "from_task": "TASK-BE-001",
        "to_task": "TASK-QA-001",
        "type": "FS",
        "description": "后端开发完成后才能编写集成测试"
      },
      {
        "from_task": "TASK-FE-001",
        "to_task": "TASK-QA-001",
        "type": "FS",
        "description": "前端开发完成后才能编写 E2E 测试"
      }
    ],

    "pages": [
      {
        "page_id": "PAGE-001",
        "name": "用户管理",
        "route": "/system/users",
        "components": [],
        "api_calls": []
      }
    ],

    "services": [
      {
        "service_id": "SVC-001",
        "name": "UserService",
        "methods": []
      }
    ],

    "estimated_hours": {
      "total": 22.0,
      "buffer_total": 4.4,
      "grand_total": 26.4,
      "by_role": {
        "BE": 7.2,
        "FE": 9.6,
        "QA": 4.8,
        "DevOps": 0.0
      }
    },

    "critical_path": [
      "TASK-DB-001",
      "TASK-BE-001",
      "TASK-QA-001"
    ],

    "parallel_groups": [
      {
        "group_id": "PARALLEL-001",
        "tasks": ["TASK-BE-001", "TASK-FE-001"],
        "condition": "API 契约定义完成后可并行开发",
        "estimated_parallel_hours": 9.6
      }
    ]
  }
}
```

---

## 完整示例

### 示例一：电商订单管理模块

**需求概要**：开发电商系统的订单管理模块，包括订单列表、订单详情、发货处理和退款处理功能。

**输入**：结构化需求文档（由 requirement-analysis 输出的 PRD）

**输出 Delivery Package**：

```json
{
  "delivery_package": {
    "project_name": "电商订单管理模块",
    "tasks": [
      {
        "task_id": "TASK-DB-001",
        "task_code": "DB-ORDER-SCHEMA",
        "title": "订单相关表结构设计与迁移",
        "description": "创建订单主表 biz_order、订单明细表 biz_order_item、订单日志表 biz_order_log，设计索引和关联关系",
        "task_type": "backend",
        "assignee": "BE",
        "dependencies": [],
        "dependency_type": "FS",
        "estimated_hours": 4.0,
        "buffer_percentage": 20,
        "total_hours": 4.8,
        "priority": "P0",
        "status": "pending",
        "acceptance_criteria": [
          "biz_order 表包含 tenant_id、订单号、用户ID、金额、状态等字段",
          "biz_order_item 表关联订单主表，包含商品ID、数量、单价等字段",
          "biz_order_log 表记录订单状态变更日志",
          "所有表包含 create_time (BIGINT 毫秒)、update_time、is_deleted 字段",
          "索引覆盖 tenant_id + status 组合查询"
        ],
        "tags": ["database", "order", "schema"]
      },
      {
        "task_id": "TASK-BE-001",
        "task_code": "BE-ORDER-LIST",
        "title": "订单列表查询 API",
        "description": "实现订单列表分页查询接口，支持按订单号、状态、时间范围、用户ID 等条件筛选，返回订单摘要信息",
        "task_type": "backend",
        "assignee": "BE",
        "dependencies": ["TASK-DB-001"],
        "dependency_type": "FS",
        "estimated_hours": 4.0,
        "buffer_percentage": 20,
        "total_hours": 4.8,
        "priority": "P0",
        "status": "pending",
        "acceptance_criteria": [
          "GET /api/orders 返回分页数据，默认按创建时间倒序",
          "支持按 order_no 精确查询",
          "支持按 status 列表筛选（可多选）",
          "支持按 create_time 时间范围筛选",
          "返回字段包含订单号、金额、状态、商品数量、创建时间",
          "所有查询强制带 tenant_id 条件"
        ],
        "related_contracts": ["API-ORD-001"],
        "related_db_changes": ["DB-001"],
        "tags": ["order", "api", "query"]
      },
      {
        "task_id": "TASK-BE-002",
        "task_code": "BE-ORDER-DETAIL",
        "title": "订单详情 API",
        "description": "实现订单详情查询接口，返回订单基本信息、商品明细列表、状态变更日志",
        "task_type": "backend",
        "assignee": "BE",
        "dependencies": ["TASK-DB-001"],
        "dependency_type": "FS",
        "estimated_hours": 3.0,
        "buffer_percentage": 20,
        "total_hours": 3.6,
        "priority": "P0",
        "status": "pending",
        "acceptance_criteria": [
          "GET /api/orders/:id 返回订单完整信息",
          "包含 order_items 明细列表（商品名、规格、数量、单价、小计）",
          "包含 order_logs 状态变更记录",
          "非本租户订单返回 404"
        ],
        "related_contracts": ["API-ORD-002"],
        "tags": ["order", "api", "detail"]
      },
      {
        "task_id": "TASK-BE-003",
        "task_code": "BE-ORDER-SHIP",
        "title": "订单发货处理 API",
        "description": "实现订单发货接口，更新订单状态为已发货，记录物流单号，写入状态变更日志",
        "task_type": "backend",
        "assignee": "BE",
        "dependencies": ["TASK-DB-001"],
        "dependency_type": "FS",
        "estimated_hours": 3.0,
        "buffer_percentage": 20,
        "total_hours": 3.6,
        "priority": "P1",
        "status": "pending",
        "acceptance_criteria": [
          "POST /api/orders/:id/ship 接受物流公司和物流单号参数",
          "仅状态为已支付的订单可发货，否则返回业务错误",
          "发货后状态变更为已发货(2)",
          "自动写入状态变更日志"
        ],
        "related_contracts": ["API-ORD-003"],
        "tags": ["order", "api", "ship"]
      },
      {
        "task_id": "TASK-BE-004",
        "task_code": "BE-ORDER-REFUND",
        "title": "订单退款处理 API",
        "description": "实现订单退款接口，校验退款金额不超过实付金额，更新订单状态为已退款，记录退款日志",
        "task_type": "backend",
        "assignee": "BE",
        "dependencies": ["TASK-DB-001"],
        "dependency_type": "FS",
        "estimated_hours": 5.0,
        "buffer_percentage": 30,
        "total_hours": 6.5,
        "priority": "P1",
        "status": "pending",
        "acceptance_criteria": [
          "POST /api/orders/:id/refund 接受退款金额和退款原因",
          "退款金额不得超过订单实付金额",
          "仅已支付/已发货状态的订单可退款",
          "退款后状态变更为已退款(5)",
          "记录退款日志包含退款金额、操作人、时间"
        ],
        "related_contracts": ["API-ORD-004"],
        "tags": ["order", "api", "refund"]
      },
      {
        "task_id": "TASK-FE-001",
        "task_code": "FE-ORDER-LIST-PAGE",
        "title": "订单列表页面开发",
        "description": "开发订单管理列表页面，包含订单数据表格、多条件搜索、状态标签、快捷操作按钮",
        "task_type": "frontend",
        "assignee": "FE",
        "dependencies": ["API-CONTRACT-ORD"],
        "dependency_type": "SS",
        "estimated_hours": 8.0,
        "buffer_percentage": 20,
        "total_hours": 9.6,
        "priority": "P0",
        "status": "pending",
        "acceptance_criteria": [
          "表格展示订单号、金额、状态(标签色)、商品数、下单时间",
          "搜索栏支持订单号搜索、状态多选筛选、时间范围选择",
          "状态列使用 Tag 组件，不同状态对应不同颜色",
          "操作列包含查看详情、发货、退款按钮（按状态动态显示）",
          "分页组件正确工作"
        ],
        "related_contracts": ["API-ORD-001"],
        "related_pages": ["PAGE-ORD-001"],
        "tags": ["order", "page", "table"]
      },
      {
        "task_id": "TASK-FE-002",
        "task_code": "FE-ORDER-DETAIL-PAGE",
        "title": "订单详情页面开发",
        "description": "开发订单详情页面，展示订单基本信息、商品明细表格、状态流转时间线、发货/退款操作",
        "task_type": "frontend",
        "assignee": "FE",
        "dependencies": ["API-CONTRACT-ORD"],
        "dependency_type": "SS",
        "estimated_hours": 6.0,
        "buffer_percentage": 20,
        "total_hours": 7.2,
        "priority": "P0",
        "status": "pending",
        "acceptance_criteria": [
          "顶部展示订单基础信息卡片（订单号、金额、状态、用户信息）",
          "中部展示商品明细表格（商品名、规格、数量、单价、小计）",
          "底部展示状态变更时间线（Timeline 组件）",
          "发货按钮弹出物流信息填写弹窗",
          "退款按钮弹出退款金额和原因填写弹窗",
          "退款金额不可超过订单实付金额（前端校验）"
        ],
        "related_contracts": ["API-ORD-002", "API-ORD-003", "API-ORD-004"],
        "related_pages": ["PAGE-ORD-002"],
        "tags": ["order", "page", "detail"]
      },
      {
        "task_id": "TASK-QA-001",
        "task_code": "QA-ORDER-TEST",
        "title": "订单模块测试用例",
        "description": "编写订单模块的单元测试和集成测试，覆盖 CRUD 操作、状态流转、退款校验等场景",
        "task_type": "testing",
        "assignee": "QA",
        "dependencies": ["TASK-BE-001", "TASK-BE-002", "TASK-BE-003", "TASK-BE-004", "TASK-FE-001", "TASK-FE-002"],
        "dependency_type": "FS",
        "estimated_hours": 6.0,
        "buffer_percentage": 20,
        "total_hours": 7.2,
        "priority": "P1",
        "status": "pending",
        "acceptance_criteria": [
          "订单列表查询的 Happy Path 和边界条件覆盖",
          "订单详情查询的正确性验证",
          "发货操作的正常流程和异常流程（重复发货、未支付发货）",
          "退款金额校验（超额退款、负数退款、零元退款）",
          "E2E 测试覆盖从下单到发货到退款的完整流程"
        ],
        "tags": ["order", "testing"]
      }
    ],

    "api_contracts": [
      {"contract_id": "API-ORD-001", "name": "订单列表查询", "method": "GET", "path": "/api/orders"},
      {"contract_id": "API-ORD-002", "name": "订单详情查询", "method": "GET", "path": "/api/orders/:id"},
      {"contract_id": "API-ORD-003", "name": "订单发货", "method": "POST", "path": "/api/orders/:id/ship"},
      {"contract_id": "API-ORD-004", "name": "订单退款", "method": "POST", "path": "/api/orders/:id/refund"}
    ],

    "db_changes": [
      {"change_id": "DB-001", "type": "create_table", "table_name": "biz_order"},
      {"change_id": "DB-002", "type": "create_table", "table_name": "biz_order_item"},
      {"change_id": "DB-003", "type": "create_table", "table_name": "biz_order_log"}
    ],

    "dependencies": [
      {"from_task": "TASK-DB-001", "to_task": "TASK-BE-001", "type": "FS"},
      {"from_task": "TASK-DB-001", "to_task": "TASK-BE-002", "type": "FS"},
      {"from_task": "TASK-DB-001", "to_task": "TASK-BE-003", "type": "FS"},
      {"from_task": "TASK-DB-001", "to_task": "TASK-BE-004", "type": "FS"},
      {"from_task": "API-CONTRACT-ORD", "to_task": "TASK-FE-001", "type": "SS"},
      {"from_task": "API-CONTRACT-ORD", "to_task": "TASK-FE-002", "type": "SS"},
      {"from_task": "TASK-BE-001", "to_task": "TASK-QA-001", "type": "FS"},
      {"from_task": "TASK-FE-002", "to_task": "TASK-QA-001", "type": "FS"}
    ],

    "estimated_hours": {
      "total": 39.0,
      "buffer_total": 8.5,
      "grand_total": 47.5,
      "by_role": {
        "BE": 23.3,
        "FE": 16.8,
        "QA": 7.2,
        "DevOps": 0.0
      }
    },

    "critical_path": [
      "TASK-DB-001",
      "TASK-BE-004",
      "TASK-QA-001"
    ],

    "parallel_groups": [
      {
        "group_id": "PARALLEL-001",
        "description": "数据库完成后，后端各接口并行开发",
        "tasks": ["TASK-BE-001", "TASK-BE-002", "TASK-BE-003", "TASK-BE-004"],
        "estimated_parallel_hours": 6.5
      },
      {
        "group_id": "PARALLEL-002",
        "description": "API 契约定义后，前后端可并行",
        "tasks": ["TASK-BE-001", "TASK-FE-001"],
        "estimated_parallel_hours": 9.6
      }
    ]
  }
}
```

**关键路径分析**：

- 最长链路：`DB Schema(4.8h)` → `退款API(6.5h)` → `测试(7.2h)` = 18.5h
- 并行压缩后，实际项目工期约为 18.5h（关键路径长度）
- 如果后端仅一人开发，后端串行工期为 23.3h，项目工期将延长至 30.5h

---

### 示例二：博客内容管理系统

**需求概要**：开发博客 CMS 的文章管理模块，支持 Markdown 编辑、文章分类、标签管理、发布/草稿状态管理。

**任务分解**：

```json
{
  "delivery_package": {
    "project_name": "博客内容管理 - 文章模块",
    "tasks": [
      {
        "task_id": "TASK-DB-001",
        "task_code": "DB-CMS-SCHEMA",
        "title": "文章相关表结构设计",
        "description": "创建文章表 biz_article、分类表 biz_category、标签表 biz_tag、文章-标签关联表 biz_article_tag",
        "task_type": "backend",
        "assignee": "BE",
        "dependencies": [],
        "estimated_hours": 3.0,
        "buffer_percentage": 20,
        "total_hours": 3.6,
        "priority": "P0",
        "status": "pending",
        "acceptance_criteria": [
          "biz_article 表支持 title、content(TEXT)、summary、cover_image、status、category_id 字段",
          "biz_category 表支持 name、sort_order、parent_id（支持二级分类）",
          "biz_tag 表支持 name 字段，name 唯一索引",
          "biz_article_tag 关联表包含 article_id 和 tag_id 联合唯一索引",
          "所有表遵循多租户和 BIGINT 时间戳规范"
        ],
        "tags": ["database", "cms", "schema"]
      },
      {
        "task_id": "TASK-BE-001",
        "task_code": "BE-ARTICLE-CRUD",
        "title": "文章 CRUD API 开发",
        "description": "实现文章的创建、查询、更新、删除接口，支持 Markdown 内容存储和预览",
        "task_type": "backend",
        "assignee": "BE",
        "dependencies": ["TASK-DB-001"],
        "dependency_type": "FS",
        "estimated_hours": 6.0,
        "buffer_percentage": 20,
        "total_hours": 7.2,
        "priority": "P0",
        "status": "pending",
        "acceptance_criteria": [
          "POST /api/articles 创建文章（自动生成摘要）",
          "GET /api/articles 分页查询，支持按分类、标签、状态、关键词筛选",
          "GET /api/articles/:id 返回文章详情（含分类名和标签列表）",
          "PUT /api/articles/:id 更新文章",
          "DELETE /api/articles/:id 软删除",
          "文章内容存储原始 Markdown，查询时可选返回 HTML 渲染结果"
        ],
        "tags": ["article", "api", "crud"]
      },
      {
        "task_id": "TASK-BE-002",
        "task_code": "BE-CATEGORY-TAG",
        "title": "分类与标签管理 API",
        "description": "实现分类的树形 CRUD 和标签的 CRUD 接口",
        "task_type": "backend",
        "assignee": "BE",
        "dependencies": ["TASK-DB-001"],
        "dependency_type": "FS",
        "estimated_hours": 4.0,
        "buffer_percentage": 20,
        "total_hours": 4.8,
        "priority": "P1",
        "status": "pending",
        "acceptance_criteria": [
          "GET /api/categories 返回树形结构分类列表",
          "POST/PUT/DELETE /api/categories 分类增删改",
          "GET /api/tags 标签列表（支持搜索）",
          "POST/DELETE /api/tags 标签增删",
          "分类删除时检查是否有文章引用"
        ],
        "tags": ["category", "tag", "api"]
      },
      {
        "task_id": "TASK-FE-001",
        "task_code": "FE-ARTICLE-EDITOR",
        "title": "Markdown 文章编辑器页面",
        "description": "开发文章编辑页面，集成 Markdown 编辑器（实时预览）、分类选择、标签多选、封面图上传、发布/草稿切换",
        "task_type": "frontend",
        "assignee": "FE",
        "dependencies": ["API-CONTRACT-CMS"],
        "dependency_type": "SS",
        "estimated_hours": 8.0,
        "buffer_percentage": 30,
        "total_hours": 10.4,
        "priority": "P0",
        "status": "pending",
        "acceptance_criteria": [
          "Markdown 编辑器支持实时预览（左右分栏）",
          "支持插入图片（上传到服务器）",
          "分类下拉选择器（支持二级分类）",
          "标签多选器（支持搜索已有标签、新建标签）",
          "封面图上传预览",
          "保存草稿 / 发布按钮",
          "编辑已有文章时自动回填所有字段"
        ],
        "tags": ["article", "editor", "markdown"]
      },
      {
        "task_id": "TASK-FE-002",
        "task_code": "FE-ARTICLE-LIST",
        "title": "文章列表管理页面",
        "description": "开发文章列表页面，展示文章卡片或表格，支持筛选、搜索、批量操作",
        "task_type": "frontend",
        "assignee": "FE",
        "dependencies": ["API-CONTRACT-CMS"],
        "dependency_type": "SS",
        "estimated_hours": 5.0,
        "buffer_percentage": 20,
        "total_hours": 6.0,
        "priority": "P0",
        "status": "pending",
        "acceptance_criteria": [
          "表格展示标题、分类、标签、状态、发布时间",
          "支持按分类、标签、状态筛选",
          "支持标题关键词搜索",
          "批量删除和批量修改状态操作",
          "点击标题跳转编辑页面"
        ],
        "tags": ["article", "list", "page"]
      },
      {
        "task_id": "TASK-FE-003",
        "task_code": "FE-CATEGORY-MGMT",
        "title": "分类与标签管理页面",
        "description": "开发分类管理页面（树形表格，支持拖拽排序）和标签管理页面",
        "task_type": "frontend",
        "assignee": "FE",
        "dependencies": ["API-CONTRACT-CMS"],
        "dependency_type": "SS",
        "estimated_hours": 4.0,
        "buffer_percentage": 20,
        "total_hours": 4.8,
        "priority": "P1",
        "status": "pending",
        "acceptance_criteria": [
          "分类页面使用树形表格展示层级关系",
          "支持新增、编辑、删除分类",
          "标签页面使用表格 + 搜索展示",
          "标签支持新增和删除",
          "引用中的分类/标签删除时给出警告"
        ],
        "tags": ["category", "tag", "page"]
      },
      {
        "task_id": "TASK-QA-001",
        "task_code": "QA-CMS-TEST",
        "title": "CMS 模块测试",
        "description": "编写文章管理模块的测试用例，覆盖 CRUD、Markdown 处理、分类树、标签关联等场景",
        "task_type": "testing",
        "assignee": "QA",
        "dependencies": ["TASK-BE-001", "TASK-BE-002", "TASK-FE-001", "TASK-FE-002", "TASK-FE-003"],
        "dependency_type": "FS",
        "estimated_hours": 5.0,
        "buffer_percentage": 20,
        "total_hours": 6.0,
        "priority": "P1",
        "status": "pending",
        "acceptance_criteria": [
          "文章 CRUD 各接口 Happy Path 测试",
          "Markdown 内容 XSS 注入测试",
          "分类树形结构正确性测试（含二级分类）",
          "标签关联/取消关联正确性测试",
          "发布/草稿状态切换测试"
        ],
        "tags": ["cms", "testing"]
      }
    ],

    "api_contracts": [
      {"contract_id": "API-CMS-001", "name": "文章列表查询", "method": "GET", "path": "/api/articles"},
      {"contract_id": "API-CMS-002", "name": "文章详情", "method": "GET", "path": "/api/articles/:id"},
      {"contract_id": "API-CMS-003", "name": "创建文章", "method": "POST", "path": "/api/articles"},
      {"contract_id": "API-CMS-004", "name": "更新文章", "method": "PUT", "path": "/api/articles/:id"},
      {"contract_id": "API-CMS-005", "name": "删除文章", "method": "DELETE", "path": "/api/articles/:id"},
      {"contract_id": "API-CMS-006", "name": "分类列表(树)", "method": "GET", "path": "/api/categories"},
      {"contract_id": "API-CMS-007", "name": "标签列表", "method": "GET", "path": "/api/tags"}
    ],

    "db_changes": [
      {"change_id": "DB-001", "type": "create_table", "table_name": "biz_article"},
      {"change_id": "DB-002", "type": "create_table", "table_name": "biz_category"},
      {"change_id": "DB-003", "type": "create_table", "table_name": "biz_tag"},
      {"change_id": "DB-004", "type": "create_table", "table_name": "biz_article_tag"}
    ],

    "dependencies": [
      {"from_task": "TASK-DB-001", "to_task": "TASK-BE-001", "type": "FS"},
      {"from_task": "TASK-DB-001", "to_task": "TASK-BE-002", "type": "FS"},
      {"from_task": "API-CONTRACT-CMS", "to_task": "TASK-FE-001", "type": "SS"},
      {"from_task": "API-CONTRACT-CMS", "to_task": "TASK-FE-002", "type": "SS"},
      {"from_task": "API-CONTRACT-CMS", "to_task": "TASK-FE-003", "type": "SS"},
      {"from_task": "TASK-BE-001", "to_task": "TASK-QA-001", "type": "FS"},
      {"from_task": "TASK-FE-001", "to_task": "TASK-QA-001", "type": "FS"}
    ],

    "estimated_hours": {
      "total": 35.0,
      "buffer_total": 6.8,
      "grand_total": 41.8,
      "by_role": {
        "BE": 15.6,
        "FE": 21.2,
        "QA": 6.0,
        "DevOps": 0.0
      }
    },

    "critical_path": [
      "TASK-DB-001",
      "TASK-BE-001",
      "TASK-QA-001"
    ],

    "parallel_groups": [
      {
        "group_id": "PARALLEL-001",
        "description": "数据库完成后，后端两模块并行开发",
        "tasks": ["TASK-BE-001", "TASK-BE-002"],
        "estimated_parallel_hours": 7.2
      },
      {
        "group_id": "PARALLEL-002",
        "description": "API 契约后，前端三页面并行开发",
        "tasks": ["TASK-FE-001", "TASK-FE-002", "TASK-FE-003"],
        "estimated_parallel_hours": 10.4
      }
    ]
  }
}
```

---

## 反模式与常见错误

### 1. 粒度过粗

**错误表现**：一个任务覆盖了整个模块（如"完成用户管理模块"），工时估算 40+ 小时。

**问题**：
- 无法准确追踪进度（任务进行到 50% 时实际不清楚完成了多少）
- 无法并行开发
- 风险集中，延迟影响难以评估

**正确做法**：将模块按技术层次和功能点拆分为 2-8 小时的原子任务。

### 2. 粒度过细

**错误表现**：将一个简单的 CRUD 接口拆成 5 个任务（定义 Model → 写 Repository → 写 Service → 写 Controller → 写测试），每个 0.5 小时。

**问题**：
- 任务管理成本高于开发成本
- 依赖关系爆炸，增加协调复杂度
- 小任务的上下文切换开销占比过大

**正确做法**：一个标准 CRUD 接口（Model + Repository + Service + Controller）合并为一个任务，工时 3-4 小时。

### 3. 遗漏集成任务

**错误表现**：只列出后端和前端各自的任务，忽略了前后端联调、接口对接的集成任务。

**问题**：
- 后端接口和前端页面对接时发现字段名不一致、数据结构不匹配
- 缺少联调阶段导致延期

**正确做法**：
- 在 API 契约中明确定义字段名、数据类型和嵌套结构
- 为复杂接口预留 1-2 小时的联调任务
- 前端开发时可基于 Mock 数据先行，后端完成后对接替换

### 4. 循环依赖

**错误表现**：任务 A 依赖任务 B，任务 B 又依赖任务 A。

**问题**：无法确定执行顺序，导致死锁。

**正确做法**：
- 依赖图必须是 DAG（有向无环图）
- 如果发现循环依赖，将共同依赖的部分提取为独立的前置任务
- 检查方法：对依赖图执行拓扑排序，若无法完成则存在环

### 5. 忽略非功能需求

**错误表现**：只分解业务功能任务，忽略了权限校验、日志记录、错误处理、性能优化等非功能需求。

**问题**：
- 安全漏洞（缺少权限校验）
- 运维困难（缺少日志）
- 性能瓶颈（缺少索引和缓存设计）

**正确做法**：
- 在每个后端任务的验收标准中包含权限校验和错误处理要求
- 在 DB Changes 中明确索引设计
- 为涉及敏感数据的模块增加安全审查任务

### 6. 前后端耦合依赖

**错误表现**：前端任务直接依赖后端任务的完成（FS 依赖），导致前端必须等后端开发完才能开始。

**问题**：串行执行导致工期延长，浪费前端开发者的等待时间。

**正确做法**：
- 引入 API Contract 作为中间产物
- 前端依赖 API Contract 的定义（SS 依赖），而非后端实现
- API Contract 在任务分解阶段就确定，前端基于契约和 Mock 数据并行开发
- 后端实现完成后仅需联调替换 Mock

### 7. 估算过于乐观

**错误表现**：所有任务都按理想情况估算，不考虑联调、调试、需求变更等不确定因素。

**问题**：实际工时远超估算，项目频繁延期。

**正确做法**：
- 按 T-shirt 尺寸估算后加上缓冲系数
- 对新领域或不熟悉的技术栈使用 30-50% 的缓冲
- 定期回顾估算与实际的偏差，校准估算模型

### 8. 忽略数据迁移和兼容性

**错误表现**：只考虑新表和新字段的创建，忽略了已有数据的迁移和向后兼容。

**问题**：
- 上线后旧数据不兼容新结构
- 缺少回滚方案

**正确做法**：
- DB Changes 中标注每个变更的兼容性影响
- 涉及已有表结构变更时，增加数据迁移任务
- 为高风险 Schema 变更准备回滚 SQL

---

## Input

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `requirement_doc` | string | 是 | 需求文档内容（JSON 或文本格式的 PRD） |
| `session_id` | string | 否 | 会话 ID，用于关联上下文 |
| `tech_stack` | object | 否 | 技术栈配置，如 `{"backend": "fastapi", "frontend": "react"}` |
| `team_size` | object | 否 | 团队配置，如 `{"BE": 2, "FE": 2, "QA": 1}` |

## Output

| 参数 | 类型 | 说明 |
|------|------|------|
| `delivery_package` | object | 完整的交付包，包含 tasks、api_contracts、db_changes、dependencies、pages、services、estimated_hours、critical_path、parallel_groups |

---

## 与 Pipeline 集成

在 DevPipeline 流水线中，本 Skill 在 `planning` 阶段被调用：

```
用户请求 → requirement-analysis(PM) → task-breakdown(PJM) → 代码生成(BE/FE) → 测试(QA) → 部署
```

**阶段数据存储**：分解结果写入 `dev_pipeline.stages_data` 的 `planning` 字段，供后续阶段读取。

**下游消费**：
- `backend-development` Skill 读取 `api_contracts` 和 `db_changes` 生成后端代码
- `frontend-development` Skill 读取 `pages` 和 `api_contracts` 生成前端代码
- `test-generation` Skill 读取 `tasks` 中的 `acceptance_criteria` 生成测试用例
- `progress-report` Skill 读取 `tasks` 的状态生成进度报告
