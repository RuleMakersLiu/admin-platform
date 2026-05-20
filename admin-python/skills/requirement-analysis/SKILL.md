---
id: requirement_analysis
name: requirement-analysis
description: "Analyze user requirements and generate structured PRD documents. 分析用户需求，生成结构化需求文档(PRD)。支持功能需求、非功能需求、用户故事等格式输出。"
version: 1.1.0
category: analysis
agent_type: PM
metadata:
  hermes:
    tags: [requirement, analysis, prd, product, user-stories, acceptance-criteria]
    related_skills: [task-breakdown, backend-development, frontend-development]
---

# 需求分析 (Requirement Analysis)

## 1. 概述 (Overview)

本 Skill 用于将用户的原始需求描述转化为结构化的产品需求文档 (PRD)。PM Agent 在接收到用户需求后，按照本 Skill 定义的方法论和模板进行系统性分析，最终输出标准化的 JSON 格式 PRD 文档，供下游 task-breakdown、backend-development、frontend-development 等 Skill 消费。

### 适用场景

- 用户提供了一段自然语言的需求描述，需要转化为结构化 PRD
- 需要对模糊的原始需求进行澄清、拆解和优先级排序
- 项目启动阶段，产品经理需要输出 PRD 文档供开发团队参考
- 需求变更时，需要更新已有 PRD 文档
- 多模块系统设计时，需要按模块分别输出 PRD

### 不适用场景

- 用户只是简单问答或咨询，不涉及具体功能开发
- 已有完整 PRD，只需要进行任务分解（此时应使用 task-breakdown Skill）
- 纯技术实现问题，不涉及需求层面分析

---

## 2. 需求分析流程 (Requirement Analysis Process)

PM Agent 应严格按照以下步骤执行需求分析。每一步都必须完成，不可跳过。

### Step 1: 利益相关者识别 (Stakeholder Identification)

分析需求涉及的利益相关者，明确：

- **最终用户 (End User)**: 谁会直接使用该功能？区分不同角色（如管理员、普通用户、访客等）
- **决策者 (Decision Maker)**: 谁定义需求的优先级和验收标准？
- **开发团队 (Development Team)**: 哪些角色参与实现（BE、FE、QA）？
- **运维人员 (Operations)**: 是否涉及部署、监控、运维需求？
- **外部系统 (External Systems)**: 是否需要与第三方系统集成？

输出格式：
```
stakeholders:
  - role: "角色名称"
    type: "end_user | decision_maker | developer | operator | external"
    description: "角色描述和参与方式"
```

### Step 2: 需求收集与分类 (Requirement Gathering)

将用户的原始描述拆解为具体需求条目，并分为两大类：

#### 功能需求 (Functional Requirements)

系统必须具备的功能行为。每条功能需求应满足：
- **原子性**: 一条需求只描述一个独立的功能点
- **可测试性**: 有明确的预期行为，可以被验证
- **无歧义**: 不包含"可能"、"大概"、"等"等模糊词汇
- **用户视角**: 从用户角度描述系统行为，而非技术实现

#### 非功能需求 (Non-functional Requirements)

系统的质量属性约束，按以下维度分类：

| 维度 | 说明 | 示例 |
|------|------|------|
| Performance (性能) | 响应时间、吞吐量、并发量 | API 响应时间 < 200ms |
| Security (安全) | 认证、授权、数据加密、审计 | 敏感字段 AES-256 加密存储 |
| Usability (可用性) | 易用性、学习曲线、无障碍 | 新用户 5 分钟内完成首次操作 |
| Reliability (可靠性) | 容错、恢复、可用率 | 系统可用率 99.9% |
| Scalability (可扩展性) | 水平扩展、数据增长 | 支持 10 万用户并发 |
| Compatibility (兼容性) | 浏览器、设备、系统版本 | 支持 Chrome 90+、Firefox 88+ |
| Maintainability (可维护性) | 代码质量、文档、日志 | 所有操作写入审计日志 |
| Localization (国际化) | 多语言、时区、货币 | 支持中文、英文切换 |

### Step 3: 用户故事编写 (User Story Writing)

使用标准格式编写用户故事：

**格式**: `As a <角色>, I want <功能>, so that <价值>.`

中文模板: `作为一个<角色>，我想要<功能>，以便于<价值>。`

编写规则：
1. 每个用户故事必须独立可交付，不依赖其他未完成的故事
2. 故事粒度适中：一个故事对应的开发工作量应在 1-3 天内
3. 如果故事过大，应拆分为多个子故事（使用 parent_id 关联）
4. 每个故事必须有唯一编号（格式：US-001, US-002...）
5. 故事描述中的"功能"部分应避免包含技术实现细节

### Step 4: 验收标准定义 (Acceptance Criteria)

为每个用户故事定义验收标准，使用 **Given-When-Then** 格式：

```
Given [前置条件/上下文]
When [用户操作/触发事件]
Then [预期结果/系统行为]
```

编写规则：
1. 每个用户故事至少有 2 条验收标准（正常流程 + 异常流程）
2. 验收标准必须覆盖所有边界条件
3. 验收标准必须完全可测试，不含主观判断
4. 使用具体的数据值而非模糊描述（如"返回 404 错误"而非"返回错误"）

示例：
```
AC-001:
  Given 用户已登录且拥有管理员权限
  When 用户点击"删除用户"按钮并确认
  Then 系统将目标用户标记为已删除（软删除）
  And 返回成功提示"用户已删除"
  And 操作记录写入审计日志

AC-002:
  Given 用户已登录但无管理员权限
  When 用户尝试删除用户
  Then 系统返回 403 Forbidden
  And 显示提示"您没有权限执行此操作"
```

### Step 5: 优先级评估 (Priority Assessment)

使用 **MoSCoW 方法** 对每条需求进行优先级分类：

| 优先级 | 标签 | 含义 | 指导原则 |
|--------|------|------|----------|
| P0 | MUST | 必须实现 | 核心功能，缺失则产品不可用 |
| P1 | SHOULD | 应该实现 | 重要功能，显著提升用户体验 |
| P2 | COULD | 可以实现 | 锦上添花功能，资源允许时实现 |
| P3 | WON'T | 暂不实现 | 明确排除的需求，记录以备后续 |

优先级评估维度：
- **业务价值**: 该需求对用户/业务的价值有多大？
- **技术风险**: 实现该需求的技术难度和风险？
- **依赖关系**: 是否有其他需求依赖于此需求？
- **时间约束**: 是否有上线时间要求？

### Step 6: 复杂度估算 (Complexity Estimation)

使用 **T-shirt 尺码** 进行复杂度评估：

| 尺寸 | 开发工时 | 说明 |
|------|----------|------|
| XS | 0.5 天 | 简单配置修改、文案调整 |
| S | 1-2 天 | 单表 CRUD、简单页面 |
| M | 3-5 天 | 多表关联、标准业务流程 |
| L | 1-2 周 | 复杂业务逻辑、第三方集成 |
| XL | 2-4 周 | 系统级架构、核心模块重构 |

估算应考虑：
- 后端开发工作量（API、数据库、业务逻辑）
- 前端开发工作量（页面、交互、状态管理）
- 测试工作量（单元测试、集成测试）
- 文档和部署工作量

### Step 7: 风险识别 (Risk Identification)

识别需求实现过程中的潜在风险：

```
risks:
  - id: "RSK-001"
    description: "风险描述"
    probability: "high | medium | low"
    impact: "high | medium | low"
    mitigation: "缓解措施"
    category: "technical | business | resource | timeline"
```

常见风险类型：
- **技术风险**: 技术选型不确定、性能瓶颈、安全漏洞
- **业务风险**: 需求理解偏差、业务规则变更
- **资源风险**: 人力不足、技能缺失
- **时间风险**: 依赖外部系统、联调时间不足

---

## 3. PRD 文档模板 (PRD Document Template)

以下是 PM Agent 输出 PRD 时必须遵循的文档结构。每个章节都必须包含，不可省略。

### 3.1 文档头部

```
PRD 文档
标题: [需求标题]
版本: v1.0
作者: PM Agent
创建时间: [时间戳]
最后更新: [时间戳]
状态: draft | review | approved
```

### 3.2 背景与目标 (Background & Objectives)

- **项目背景**: 为什么需要做这个需求？解决什么问题？
- **业务目标**: 期望达成什么可衡量的业务指标？
- **目标用户**: 主要服务哪些用户群体？

### 3.3 范围定义 (Scope)

```
scope:
  in_scope:
    - "明确包含的功能点1"
    - "明确包含的功能点2"
  out_of_scope:
    - "明确排除的功能点1"
    - "明确排除的功能点2"
  assumptions:
    - "假设条件1"
    - "假设条件2"
```

### 3.4 用户故事表 (User Stories Table)

| ID | 用户故事 | 验收标准数 | 优先级 | 复杂度 | 状态 |
|----|----------|-----------|--------|--------|------|
| US-001 | As a... | 3 | P0 | M | draft |
| US-002 | As a... | 2 | P1 | S | draft |

### 3.5 功能需求表 (Functional Requirements Table)

| ID | 描述 | 关联用户故事 | 优先级 | 状态 |
|----|------|-------------|--------|------|
| FR-001 | 具体功能需求描述 | US-001 | P0 | draft |
| FR-002 | 具体功能需求描述 | US-001, US-002 | P1 | draft |

### 3.6 非功能需求 (Non-functional Requirements)

| ID | 维度 | 描述 | 指标 | 优先级 |
|----|------|------|------|--------|
| NFR-001 | Performance | API 响应时间 | < 200ms (P95) | P0 |
| NFR-002 | Security | 数据传输加密 | TLS 1.2+ | P0 |
| NFR-003 | Usability | 页面加载时间 | < 3s (首屏) | P1 |

### 3.7 数据模型 (Data Models)

对于涉及数据存储的需求，定义核心数据模型：

```json
{
  "model_name": "实体名称",
  "table_name": "表名",
  "description": "实体描述",
  "fields": [
    {
      "name": "字段名",
      "type": "数据类型",
      "required": true,
      "description": "字段说明",
      "constraints": "约束条件"
    }
  ],
  "indexes": [
    {
      "fields": ["字段列表"],
      "type": "unique | normal"
    }
  ]
}
```

注意：根据项目约定，所有业务表必须包含 `tenant_id` 字段用于多租户隔离，时间字段使用 BIGINT 毫秒时间戳。

### 3.8 API 契约 (API Contracts)

对于涉及前后端交互的需求，定义 API 接口：

```json
{
  "endpoint": "POST /api/v1/resource",
  "description": "接口描述",
  "auth_required": true,
  "permissions": ["required_permission"],
  "request": {
    "headers": {},
    "body": {
      "field_name": { "type": "string", "required": true, "description": "字段说明" }
    }
  },
  "response": {
    "200": { "code": 0, "message": "success", "data": {} },
    "400": { "code": 40000, "message": "参数错误" },
    "403": { "code": 40300, "message": "无权限" },
    "500": { "code": 50000, "message": "服务器错误" }
  }
}
```

### 3.9 UI/UX 规格 (UI/UX Specifications)

描述关键页面的交互流程和布局要求：

```
ui_spec:
  page: "页面名称"
  route: "/path/to/page"
  layout: "页面布局描述"
  components:
    - name: "组件名称"
      type: "组件类型（Table/Form/Modal/Chart等）"
      description: "组件功能描述"
      interactions:
        - trigger: "触发方式"
          action: "执行动作"
          response: "系统反馈"
```

### 3.10 依赖与约束 (Dependencies & Constraints)

```
dependencies:
  internal:
    - "依赖的内部模块或服务"
  external:
    - "依赖的外部系统或第三方服务"
  technical:
    - "技术栈约束"

constraints:
  - "约束条件1：如兼容性要求"
  - "约束条件2：如数据格式要求"
```

### 3.11 成功指标 (Success Metrics)

定义衡量需求交付成功的量化指标：

```json
{
  "success_metrics": [
    {
      "metric": "指标名称",
      "target": "目标值",
      "measurement_method": "测量方式",
      "measurement_frequency": "测量频率"
    }
  ]
}
```

---

## 4. 质量检查清单 (Quality Checklist)

PM Agent 在输出 PRD 前，必须逐项检查以下清单。任何一项不通过都应修正后再输出。

### 完整性检查

- [ ] PRD 包含所有必填章节（背景、范围、用户故事、功能需求、非功能需求）
- [ ] 每个功能需求都有对应的用户故事
- [ ] 每个用户故事都有至少 2 条验收标准
- [ ] 验收标准覆盖正常流程和异常流程
- [ ] 数据模型已定义（如涉及数据存储）
- [ ] API 契约已定义（如涉及前后端交互）

### 清晰性检查

- [ ] 所有需求描述无歧义，不包含"可能"、"大概"、"等"等模糊词
- [ ] 用户故事使用标准 As a... I want... So that... 格式
- [ ] 验收标准使用 Given-When-Then 格式，完全可测试
- [ ] 优先级和复杂度已分配到每个需求条目
- [ ] 范围定义清晰，In Scope 和 Out of Scope 无歧义

### 一致性检查

- [ ] 用户故事编号唯一且连续（US-001, US-002...）
- [ ] 功能需求编号唯一且连续（FR-001, FR-002...）
- [ ] 非功能需求编号唯一且连续（NFR-001, NFR-002...）
- [ ] 功能需求与用户故事的关联关系正确
- [ ] 数据模型字段与 API 契约参数一致
- [ ] 多租户约束已纳入（tenant_id 字段）
- [ ] 时间戳约定已遵循（BIGINT 毫秒）

### 边界条件检查

- [ ] 空数据场景已考虑（列表为空、字段为空）
- [ ] 大数据量场景已考虑（分页、虚拟滚动）
- [ ] 并发场景已考虑（乐观锁、幂等性）
- [ ] 错误处理已覆盖（网络错误、权限不足、数据冲突）
- [ ] 权限边界已定义（不同角色看到不同数据/操作）

---

## 5. 输出格式 (Output Format)

PM Agent 必须严格按照以下 JSON 结构输出分析结果。不可增减顶层字段。

```json
{
  "prd": {
    "title": "PRD 标题",
    "version": "1.0",
    "status": "draft",
    "background": {
      "project_background": "项目背景描述",
      "business_objectives": ["目标1", "目标2"],
      "target_users": [
        {
          "role": "角色名称",
          "description": "角色描述"
        }
      ]
    },
    "scope": {
      "in_scope": ["范围项1", "范围项2"],
      "out_of_scope": ["排除项1", "排除项2"],
      "assumptions": ["假设1", "假设2"]
    },
    "user_stories": [
      {
        "id": "US-001",
        "story": "作为一个<角色>，我想要<功能>，以便于<价值>",
        "acceptance_criteria": [
          {
            "id": "AC-001",
            "given": "前置条件",
            "when": "触发操作",
            "then": "预期结果"
          }
        ],
        "priority": "P0",
        "complexity": "M",
        "status": "draft",
        "parent_id": null,
        "tags": ["标签1", "标签2"]
      }
    ],
    "functional_requirements": [
      {
        "id": "FR-001",
        "description": "功能需求描述",
        "related_stories": ["US-001"],
        "priority": "P0",
        "status": "draft"
      }
    ],
    "non_functional_requirements": [
      {
        "id": "NFR-001",
        "category": "performance",
        "description": "非功能需求描述",
        "metric": "量化指标",
        "priority": "P0"
      }
    ],
    "data_models": [
      {
        "model_name": "实体名称",
        "table_name": "表名",
        "description": "实体描述",
        "fields": [
          {
            "name": "字段名",
            "type": "数据类型",
            "required": true,
            "description": "字段说明",
            "constraints": "约束条件"
          }
        ],
        "indexes": [
          {
            "fields": ["字段列表"],
            "type": "unique"
          }
        ]
      }
    ],
    "api_contracts": [
      {
        "endpoint": "POST /api/v1/resource",
        "description": "接口描述",
        "auth_required": true,
        "permissions": ["permission_code"],
        "request_body": {
          "field": { "type": "string", "required": true, "description": "说明" }
        },
        "response": {
          "200": { "code": 0, "message": "success", "data": {} },
          "400": { "code": 40000, "message": "参数错误" }
        }
      }
    ],
    "ui_specs": [
      {
        "page": "页面名称",
        "route": "/path",
        "layout": "布局描述",
        "components": [
          {
            "name": "组件名",
            "type": "Table",
            "description": "描述",
            "interactions": [
              { "trigger": "触发", "action": "动作", "response": "反馈" }
            ]
          }
        ]
      }
    ],
    "risks": [
      {
        "id": "RSK-001",
        "description": "风险描述",
        "probability": "medium",
        "impact": "high",
        "mitigation": "缓解措施",
        "category": "technical"
      }
    ],
    "success_metrics": [
      {
        "metric": "指标名称",
        "target": "目标值",
        "measurement_method": "测量方式",
        "measurement_frequency": "测量频率"
      }
    ],
    "dependencies": {
      "internal": ["内部依赖"],
      "external": ["外部依赖"],
      "technical": ["技术依赖"]
    },
    "stakeholders": [
      {
        "role": "角色",
        "type": "end_user",
        "description": "描述"
      }
    ]
  }
}
```

---

## 6. 示例 (Examples)

### Example 1: 创建一个用户管理模块

**输入**: "创建一个用户管理模块，支持用户增删改查、角色分配和权限管理。"

**输出**:

```json
{
  "prd": {
    "title": "用户管理模块 PRD",
    "version": "1.0",
    "status": "draft",
    "background": {
      "project_background": "系统需要统一的用户管理模块来管理人员账号、角色和权限，确保系统安全性和操作可追溯。当前系统缺乏集中化的用户管理能力，导致权限管理分散、审计困难。",
      "business_objectives": [
        "实现集中化的用户全生命周期管理",
        "支持灵活的角色与权限分配机制",
        "确保所有用户操作可审计追溯"
      ],
      "target_users": [
        { "role": "超级管理员", "description": "拥有所有权限，可管理所有用户、角色和系统配置" },
        { "role": "普通管理员", "description": "管理本租户下的用户和角色分配" },
        { "role": "普通用户", "description": "使用系统功能的终端用户" }
      ]
    },
    "scope": {
      "in_scope": [
        "用户列表查看（支持搜索、筛选、分页）",
        "创建新用户",
        "编辑用户信息",
        "删除用户（软删除）",
        "启用/禁用用户账号",
        "角色分配与管理",
        "权限查看（基于角色的权限列表）",
        "操作审计日志记录"
      ],
      "out_of_scope": [
        "用户自助注册流程",
        "第三方登录集成（OAuth/SSO）",
        "用户行为分析和统计报表",
        "密码复杂度策略配置"
      ],
      "assumptions": [
        "用户管理为多租户模式，管理员只能管理本租户用户",
        "权限系统基于 RBAC 模型（角色-权限）",
        "删除操作均为软删除，数据保留用于审计"
      ]
    },
    "user_stories": [
      {
        "id": "US-001",
        "story": "作为一个管理员，我想要查看用户列表并支持搜索和筛选，以便于快速找到目标用户进行管理",
        "acceptance_criteria": [
          {
            "id": "AC-001",
            "given": "管理员已登录并拥有用户管理权限",
            "when": "访问用户管理页面",
            "then": "显示用户列表，包含用户名、姓名、角色、状态、创建时间等列，默认按创建时间倒序排列，每页显示 20 条"
          },
          {
            "id": "AC-002",
            "given": "用户列表页已加载",
            "when": "在搜索框输入关键词并搜索",
            "then": "列表按用户名、姓名模糊匹配进行过滤，实时更新结果"
          },
          {
            "id": "AC-003",
            "given": "用户列表数据量超过 20 条",
            "when": "用户点击分页控件切换页码",
            "then": "加载对应页数据，URL 参数同步更新，支持前后端分页"
          },
          {
            "id": "AC-004",
            "given": "管理员查看用户列表",
            "when": "系统中无用户数据",
            "then": "显示空状态提示'暂无用户数据'和创建用户引导按钮"
          }
        ],
        "priority": "P0",
        "complexity": "M",
        "status": "draft",
        "parent_id": null,
        "tags": ["user-management", "list", "search"]
      },
      {
        "id": "US-002",
        "story": "作为一个管理员，我想要创建新用户并分配角色，以便于为团队成员开通系统账号",
        "acceptance_criteria": [
          {
            "id": "AC-005",
            "given": "管理员已登录并拥有用户管理权限",
            "when": "点击'新增用户'按钮",
            "then": "弹出新增用户表单，包含用户名（必填）、姓名（必填）、邮箱（必填）、手机号（选填）、角色选择（必填）字段"
          },
          {
            "id": "AC-006",
            "given": "管理员填写新增用户表单",
            "when": "用户名已存在时提交表单",
            "then": "提示'用户名已存在'，表单不关闭，用户名字段标红"
          },
          {
            "id": "AC-007",
            "given": "管理员填写新增用户表单",
            "when": "邮箱格式不正确时提交表单",
            "then": "提示'请输入正确的邮箱格式'，邮箱字段标红"
          },
          {
            "id": "AC-008",
            "given": "管理员填写完整且有效的用户信息",
            "when": "点击确认提交",
            "then": "创建用户成功，初始密码通过邮件发送给用户，列表自动刷新显示新用户，操作记录写入审计日志"
          }
        ],
        "priority": "P0",
        "complexity": "M",
        "status": "draft",
        "parent_id": null,
        "tags": ["user-management", "create", "role-assignment"]
      },
      {
        "id": "US-003",
        "story": "作为一个管理员，我想要编辑用户信息，以便于及时更新用户的资料和角色分配",
        "acceptance_criteria": [
          {
            "id": "AC-009",
            "given": "管理员已登录并选中一个用户",
            "when": "点击'编辑'按钮",
            "then": "弹出编辑表单，预填充用户当前信息（用户名不可修改）"
          },
          {
            "id": "AC-010",
            "given": "管理员修改用户信息并提交",
            "when": "修改成功",
            "then": "提示'用户信息已更新'，列表刷新显示更新后的数据，操作记录写入审计日志"
          }
        ],
        "priority": "P0",
        "complexity": "S",
        "status": "draft",
        "parent_id": null,
        "tags": ["user-management", "update"]
      },
      {
        "id": "US-004",
        "story": "作为一个管理员，我想要删除用户，以便于清理离职或无效账号",
        "acceptance_criteria": [
          {
            "id": "AC-011",
            "given": "管理员选中一个用户",
            "when": "点击'删除'按钮",
            "then": "弹出二次确认对话框'确认删除用户 XXX？此操作不可撤销'"
          },
          {
            "id": "AC-012",
            "given": "管理员确认删除操作",
            "when": "删除成功",
            "then": "用户状态变为已删除（软删除），从列表中移除，操作记录写入审计日志"
          },
          {
            "id": "AC-013",
            "given": "管理员尝试删除自己",
            "when": "点击删除",
            "then": "提示'不能删除当前登录用户'，操作被阻止"
          }
        ],
        "priority": "P1",
        "complexity": "S",
        "status": "draft",
        "parent_id": null,
        "tags": ["user-management", "delete"]
      },
      {
        "id": "US-005",
        "story": "作为一个管理员，我想要启用或禁用用户账号，以便于临时限制用户访问而不删除数据",
        "acceptance_criteria": [
          {
            "id": "AC-014",
            "given": "管理员选中一个已启用的用户",
            "when": "点击'禁用'按钮",
            "then": "用户状态变为禁用，该用户无法登录系统，提示'用户已禁用'"
          },
          {
            "id": "AC-015",
            "given": "被禁用的用户尝试登录",
            "when": "输入正确的用户名和密码",
            "then": "提示'账号已被禁用，请联系管理员'，登录失败"
          }
        ],
        "priority": "P1",
        "complexity": "S",
        "status": "draft",
        "parent_id": null,
        "tags": ["user-management", "status-toggle"]
      },
      {
        "id": "US-006",
        "story": "作为一个管理员，我想要查看操作审计日志，以便于追溯所有用户管理操作",
        "acceptance_criteria": [
          {
            "id": "AC-016",
            "given": "管理员访问审计日志页面",
            "when": "页面加载完成",
            "then": "显示操作日志列表，包含操作人、操作类型、操作对象、操作时间、IP 地址等信息"
          },
          {
            "id": "AC-017",
            "given": "管理员查看审计日志",
            "when": "按时间范围筛选",
            "then": "显示指定时间范围内的操作记录，支持按操作类型和操作人进一步筛选"
          }
        ],
        "priority": "P2",
        "complexity": "M",
        "status": "draft",
        "parent_id": null,
        "tags": ["audit", "logging"]
      }
    ],
    "functional_requirements": [
      {
        "id": "FR-001",
        "description": "用户列表查询：支持分页、按用户名/姓名搜索、按角色/状态筛选",
        "related_stories": ["US-001"],
        "priority": "P0",
        "status": "draft"
      },
      {
        "id": "FR-002",
        "description": "用户创建：支持填写基本信息并分配角色，用户名唯一性校验，邮箱格式校验",
        "related_stories": ["US-002"],
        "priority": "P0",
        "status": "draft"
      },
      {
        "id": "FR-003",
        "description": "用户编辑：支持修改姓名、邮箱、手机号、角色，用户名不可修改",
        "related_stories": ["US-003"],
        "priority": "P0",
        "status": "draft"
      },
      {
        "id": "FR-004",
        "description": "用户删除：软删除，不可删除自己，需二次确认",
        "related_stories": ["US-004"],
        "priority": "P1",
        "status": "draft"
      },
      {
        "id": "FR-005",
        "description": "用户启用/禁用：状态切换，禁用用户无法登录",
        "related_stories": ["US-005"],
        "priority": "P1",
        "status": "draft"
      },
      {
        "id": "FR-006",
        "description": "操作审计日志：记录所有用户管理操作（创建、编辑、删除、启用/禁用）",
        "related_stories": ["US-006"],
        "priority": "P2",
        "status": "draft"
      }
    ],
    "non_functional_requirements": [
      {
        "id": "NFR-001",
        "category": "performance",
        "description": "用户列表查询响应时间",
        "metric": "API 响应 < 200ms（1万条数据量下，P95）",
        "priority": "P0"
      },
      {
        "id": "NFR-002",
        "category": "security",
        "description": "密码存储安全",
        "metric": "使用 bcrypt 加密存储，cost factor >= 10",
        "priority": "P0"
      },
      {
        "id": "NFR-003",
        "category": "security",
        "description": "接口认证与授权",
        "metric": "所有 API 需要 JWT Token 验证，按角色权限控制访问",
        "priority": "P0"
      },
      {
        "id": "NFR-004",
        "category": "reliability",
        "description": "数据隔离",
        "metric": "多租户数据严格隔离，通过 tenant_id 过滤所有查询",
        "priority": "P0"
      },
      {
        "id": "NFR-005",
        "category": "usability",
        "description": "页面加载性能",
        "metric": "用户管理页面首屏加载 < 2s",
        "priority": "P1"
      }
    ],
    "data_models": [
      {
        "model_name": "SysAdmin",
        "table_name": "sys_admin",
        "description": "系统管理员/用户表",
        "fields": [
          { "name": "id", "type": "BIGSERIAL", "required": true, "description": "主键ID", "constraints": "PRIMARY KEY" },
          { "name": "tenant_id", "type": "BIGINT", "required": true, "description": "租户ID", "constraints": "NOT NULL, INDEX" },
          { "name": "username", "type": "VARCHAR(64)", "required": true, "description": "用户名", "constraints": "UNIQUE per tenant" },
          { "name": "password", "type": "VARCHAR(256)", "required": true, "description": "密码（bcrypt加密）", "constraints": "NOT NULL" },
          { "name": "real_name", "type": "VARCHAR(64)", "required": false, "description": "真实姓名" },
          { "name": "email", "type": "VARCHAR(128)", "required": true, "description": "邮箱", "constraints": "UNIQUE per tenant" },
          { "name": "phone", "type": "VARCHAR(20)", "required": false, "description": "手机号" },
          { "name": "avatar", "type": "VARCHAR(512)", "required": false, "description": "头像URL" },
          { "name": "status", "type": "SMALLINT", "required": true, "description": "状态：1-启用 2-禁用 3-已删除", "constraints": "DEFAULT 1" },
          { "name": "group_id", "type": "BIGINT", "required": false, "description": "所属用户组ID", "constraints": "FK -> sys_admin_group.id" },
          { "name": "create_time", "type": "BIGINT", "required": true, "description": "创建时间（毫秒时间戳）" },
          { "name": "update_time", "type": "BIGINT", "required": true, "description": "更新时间（毫秒时间戳）" }
        ],
        "indexes": [
          { "fields": ["tenant_id", "username"], "type": "unique" },
          { "fields": ["tenant_id", "email"], "type": "unique" },
          { "fields": ["tenant_id", "status"], "type": "normal" }
        ]
      }
    ],
    "api_contracts": [
      {
        "endpoint": "GET /api/v1/admin/users",
        "description": "获取用户列表（分页）",
        "auth_required": true,
        "permissions": ["admin:user:list"],
        "request_body": {},
        "response": {
          "200": {
            "code": 0,
            "message": "success",
            "data": {
              "list": [],
              "total": 0,
              "page": 1,
              "page_size": 20
            }
          }
        }
      },
      {
        "endpoint": "POST /api/v1/admin/users",
        "description": "创建用户",
        "auth_required": true,
        "permissions": ["admin:user:create"],
        "request_body": {
          "username": { "type": "string", "required": true, "description": "用户名" },
          "real_name": { "type": "string", "required": false, "description": "真实姓名" },
          "email": { "type": "string", "required": true, "description": "邮箱" },
          "phone": { "type": "string", "required": false, "description": "手机号" },
          "group_id": { "type": "integer", "required": true, "description": "用户组ID" }
        },
        "response": {
          "200": { "code": 0, "message": "创建成功", "data": { "id": 1 } },
          "400": { "code": 40000, "message": "用户名已存在" }
        }
      },
      {
        "endpoint": "PUT /api/v1/admin/users/{id}",
        "description": "更新用户信息",
        "auth_required": true,
        "permissions": ["admin:user:update"],
        "request_body": {
          "real_name": { "type": "string", "required": false, "description": "真实姓名" },
          "email": { "type": "string", "required": false, "description": "邮箱" },
          "phone": { "type": "string", "required": false, "description": "手机号" },
          "group_id": { "type": "integer", "required": false, "description": "用户组ID" }
        },
        "response": {
          "200": { "code": 0, "message": "更新成功" },
          "404": { "code": 40400, "message": "用户不存在" }
        }
      },
      {
        "endpoint": "DELETE /api/v1/admin/users/{id}",
        "description": "删除用户（软删除）",
        "auth_required": true,
        "permissions": ["admin:user:delete"],
        "request_body": {},
        "response": {
          "200": { "code": 0, "message": "删除成功" },
          "403": { "code": 40300, "message": "不能删除当前登录用户" }
        }
      }
    ],
    "risks": [
      {
        "id": "RSK-001",
        "description": "并发创建用户时可能出现用户名冲突",
        "probability": "medium",
        "impact": "medium",
        "mitigation": "数据库层面使用唯一索引约束，应用层做好并发校验和友好提示",
        "category": "technical"
      },
      {
        "id": "RSK-002",
        "description": "删除用户后关联数据的完整性问题",
        "probability": "low",
        "impact": "high",
        "mitigation": "采用软删除策略，保留数据关联完整性；定期清理已删除用户的关联数据",
        "category": "technical"
      }
    ],
    "success_metrics": [
      {
        "metric": "用户创建成功率",
        "target": "> 99%",
        "measurement_method": "统计创建用户API调用成功率",
        "measurement_frequency": "每周"
      },
      {
        "metric": "列表查询响应时间",
        "target": "P95 < 200ms",
        "measurement_method": "APM监控",
        "measurement_frequency": "实时"
      }
    ]
  }
}
```

### Example 2: 实现文件上传和在线预览

**输入**: "实现文件上传和在线预览功能，支持常见文件格式。"

**输出**:

```json
{
  "prd": {
    "title": "文件上传与在线预览 PRD",
    "version": "1.0",
    "status": "draft",
    "background": {
      "project_background": "平台各业务模块需要统一的文件上传和预览能力，当前各模块独立实现文件处理，存在重复开发、格式支持不一致、存储策略不统一等问题。需要一个通用的文件管理服务来统一处理文件上传、存储和预览。",
      "business_objectives": [
        "提供统一的文件上传服务，支持多格式文件",
        "实现浏览器端在线预览，无需下载即可查看文件内容",
        "建立统一的文件存储和管理规范"
      ],
      "target_users": [
        { "role": "普通用户", "description": "上传和预览自己关联的文件" },
        { "role": "管理员", "description": "管理所有文件，包括查看、删除和存储配额管理" }
      ]
    },
    "scope": {
      "in_scope": [
        "拖拽/点击文件上传（单文件和多文件批量上传）",
        "上传进度显示和断点续传",
        "文件类型校验（白名单机制）",
        "文件大小限制（可配置）",
        "图片格式在线预览（JPG/PNG/GIF/WebP/SVG）",
        "PDF 文件在线预览",
        "Office 文件在线预览（Word/Excel/PPT）",
        "纯文本/代码文件在线预览（含语法高亮）",
        "视频文件在线播放（MP4/WebM）",
        "文件下载",
        "文件列表管理（查看、删除、搜索）"
      ],
      "out_of_scope": [
        "文件协同编辑（如在线编辑 Word/Excel）",
        "文件版本管理",
        "文件分享和外链功能",
        "OCR 文字识别",
        "音视频转码和压缩",
        "水印功能"
      ],
      "assumptions": [
        "文件存储使用对象存储服务（如 MinIO/S3）",
        "Office 文件预览基于服务端转换（转为 PDF 后预览）",
        "单个文件大小上限默认 100MB，可按租户配置",
        "支持的最大批量上传数量为 20 个文件"
      ]
    },
    "user_stories": [
      {
        "id": "US-001",
        "story": "作为一个用户，我想要通过拖拽或点击的方式上传文件，以便于将文件保存到系统中",
        "acceptance_criteria": [
          {
            "id": "AC-001",
            "given": "用户在支持文件上传的页面",
            "when": "将文件拖拽到上传区域或点击选择文件",
            "then": "文件开始上传，显示上传进度条、文件名和文件大小"
          },
          {
            "id": "AC-002",
            "given": "用户上传文件时",
            "when": "文件类型不在允许的白名单中",
            "then": "提示'不支持的文件格式'，列出支持的格式列表，文件不被上传"
          },
          {
            "id": "AC-003",
            "given": "用户上传文件时",
            "when": "文件大小超过限制",
            "then": "提示'文件大小超过限制（最大XX MB）'，文件不被上传"
          },
          {
            "id": "AC-004",
            "given": "用户批量上传多个文件",
            "when": "部分文件校验不通过",
            "then": "显示校验失败的文件列表和原因，校验通过的文件正常上传"
          },
          {
            "id": "AC-005",
            "given": "上传过程中网络中断",
            "when": "网络恢复后用户重新上传同一文件",
            "then": "从断点处继续上传，无需重新上传已完成的部分（文件大于 5MB 时启用分片上传）"
          }
        ],
        "priority": "P0",
        "complexity": "L",
        "status": "draft",
        "parent_id": null,
        "tags": ["upload", "drag-drop", "batch"]
      },
      {
        "id": "US-002",
        "story": "作为一个用户，我想要在线预览已上传的文件，以便于快速查看文件内容而无需下载",
        "acceptance_criteria": [
          {
            "id": "AC-006",
            "given": "用户在文件列表中查看图片类型文件",
            "when": "点击文件名或预览按钮",
            "then": "在弹窗/新标签页中显示图片，支持缩放和左右翻页浏览"
          },
          {
            "id": "AC-007",
            "given": "用户预览 PDF 文件",
            "when": "点击预览",
            "then": "在浏览器中直接渲染 PDF 内容，支持翻页、缩放、全屏"
          },
          {
            "id": "AC-008",
            "given": "用户预览 Office 文件（Word/Excel/PPT）",
            "when": "点击预览",
            "then": "服务端将文件转换为 PDF 后在浏览器中预览，首次预览等待时间 < 5s"
          },
          {
            "id": "AC-009",
            "given": "用户预览代码/文本文件",
            "when": "点击预览",
            "then": "以代码编辑器样式展示内容，支持语法高亮和行号显示"
          },
          {
            "id": "AC-010",
            "given": "用户预览视频文件",
            "when": "点击预览",
            "then": "在浏览器中直接播放视频，支持播放/暂停、进度条、音量控制"
          },
          {
            "id": "AC-011",
            "given": "用户预览不支持的文件格式",
            "when": "点击预览",
            "then": "显示'该文件格式暂不支持在线预览'提示，提供下载按钮"
          }
        ],
        "priority": "P0",
        "complexity": "L",
        "status": "draft",
        "parent_id": null,
        "tags": ["preview", "pdf", "office", "image"]
      },
      {
        "id": "US-003",
        "story": "作为一个用户，我想要下载已上传的文件，以便于在本地使用",
        "acceptance_criteria": [
          {
            "id": "AC-012",
            "given": "用户在文件列表中",
            "when": "点击下载按钮",
            "then": "浏览器开始下载文件，文件名为原始上传文件名"
          }
        ],
        "priority": "P1",
        "complexity": "XS",
        "status": "draft",
        "parent_id": null,
        "tags": ["download"]
      },
      {
        "id": "US-004",
        "story": "作为一个管理员，我想要管理文件列表，以便于维护系统中的文件资源",
        "acceptance_criteria": [
          {
            "id": "AC-013",
            "given": "管理员在文件管理页面",
            "when": "页面加载",
            "then": "显示文件列表，包含文件名、类型、大小、上传者、上传时间，支持按类型和上传时间筛选"
          },
          {
            "id": "AC-014",
            "given": "管理员选中文件",
            "when": "点击删除",
            "then": "弹出确认对话框，确认后删除文件记录和存储文件，操作记录写入审计日志"
          }
        ],
        "priority": "P1",
        "complexity": "M",
        "status": "draft",
        "parent_id": null,
        "tags": ["file-management", "admin"]
      }
    ],
    "functional_requirements": [
      {
        "id": "FR-001",
        "description": "文件上传：支持拖拽/点击上传，支持批量上传（最多20个），文件类型白名单校验，文件大小限制校验",
        "related_stories": ["US-001"],
        "priority": "P0",
        "status": "draft"
      },
      {
        "id": "FR-002",
        "description": "断点续传：文件大于 5MB 时自动启用分片上传，支持网络中断后恢复",
        "related_stories": ["US-001"],
        "priority": "P1",
        "status": "draft"
      },
      {
        "id": "FR-003",
        "description": "图片预览：支持 JPG/PNG/GIF/WebP/SVG 格式，浏览器端直接渲染，支持缩放和翻页",
        "related_stories": ["US-002"],
        "priority": "P0",
        "status": "draft"
      },
      {
        "id": "FR-004",
        "description": "PDF 预览：使用 PDF.js 在浏览器端渲染，支持翻页、缩放、全屏",
        "related_stories": ["US-002"],
        "priority": "P0",
        "status": "draft"
      },
      {
        "id": "FR-005",
        "description": "Office 预览：服务端使用 LibreOffice 将 Word/Excel/PPT 转换为 PDF 后预览",
        "related_stories": ["US-002"],
        "priority": "P1",
        "status": "draft"
      },
      {
        "id": "FR-006",
        "description": "文本/代码预览：支持语法高亮，使用 highlight.js 或 Prism.js",
        "related_stories": ["US-002"],
        "priority": "P1",
        "status": "draft"
      },
      {
        "id": "FR-007",
        "description": "视频播放：使用 HTML5 video 标签，支持 MP4/WebM",
        "related_stories": ["US-002"],
        "priority": "P2",
        "status": "draft"
      },
      {
        "id": "FR-008",
        "description": "文件下载：支持下载原始文件，保持原始文件名",
        "related_stories": ["US-003"],
        "priority": "P1",
        "status": "draft"
      },
      {
        "id": "FR-009",
        "description": "文件列表管理：支持按文件名搜索、按类型和时间筛选、删除文件",
        "related_stories": ["US-004"],
        "priority": "P1",
        "status": "draft"
      }
    ],
    "non_functional_requirements": [
      {
        "id": "NFR-001",
        "category": "performance",
        "description": "文件上传性能",
        "metric": "100MB 文件上传完成时间 < 30s（100Mbps 网络环境）",
        "priority": "P0"
      },
      {
        "id": "NFR-002",
        "category": "performance",
        "description": "预览响应时间",
        "metric": "图片/PDF 预览打开 < 2s，Office 预览（首次转换后缓存）< 5s",
        "priority": "P0"
      },
      {
        "id": "NFR-003",
        "category": "security",
        "description": "文件安全",
        "metric": "上传文件重命名为 UUID 存储防止路径遍历；文件类型通过 magic bytes 校验而非仅扩展名",
        "priority": "P0"
      },
      {
        "id": "NFR-004",
        "category": "reliability",
        "description": "上传可靠性",
        "metric": "分片上传支持断点续传，网络中断后可恢复；上传失败自动重试 3 次",
        "priority": "P1"
      },
      {
        "id": "NFR-005",
        "category": "scalability",
        "description": "存储扩展性",
        "metric": "使用对象存储（S3 兼容），支持水平扩展，单租户默认配额 10GB",
        "priority": "P1"
      },
      {
        "id": "NFR-006",
        "category": "compatibility",
        "description": "浏览器兼容性",
        "metric": "支持 Chrome 90+、Firefox 88+、Edge 90+、Safari 14+",
        "priority": "P1"
      }
    ],
    "data_models": [
      {
        "model_name": "FileInfo",
        "table_name": "sys_file",
        "description": "文件信息表",
        "fields": [
          { "name": "id", "type": "BIGSERIAL", "required": true, "description": "主键ID", "constraints": "PRIMARY KEY" },
          { "name": "tenant_id", "type": "BIGINT", "required": true, "description": "租户ID", "constraints": "NOT NULL, INDEX" },
          { "name": "original_name", "type": "VARCHAR(256)", "required": true, "description": "原始文件名" },
          { "name": "storage_key", "type": "VARCHAR(512)", "required": true, "description": "存储路径（UUID命名）" },
          { "name": "file_type", "type": "VARCHAR(64)", "required": true, "description": "文件MIME类型" },
          { "name": "file_extension", "type": "VARCHAR(16)", "required": true, "description": "文件扩展名" },
          { "name": "file_size", "type": "BIGINT", "required": true, "description": "文件大小（字节）" },
          { "name": "uploader_id", "type": "BIGINT", "required": true, "description": "上传者ID", "constraints": "FK -> sys_admin.id" },
          { "name": "biz_type", "type": "VARCHAR(64)", "required": false, "description": "业务类型（关联模块标识）" },
          { "name": "biz_id", "type": "BIGINT", "required": false, "description": "业务关联ID" },
          { "name": "preview_status", "type": "SMALLINT", "required": true, "description": "预览状态：0-未转换 1-转换中 2-已就绪 3-转换失败", "constraints": "DEFAULT 0" },
          { "name": "preview_key", "type": "VARCHAR(512)", "required": false, "description": "预览文件存储路径（转换后的PDF）" },
          { "name": "create_time", "type": "BIGINT", "required": true, "description": "创建时间（毫秒时间戳）" },
          { "name": "update_time", "type": "BIGINT", "required": true, "description": "更新时间（毫秒时间戳）" }
        ],
        "indexes": [
          { "fields": ["tenant_id", "biz_type", "biz_id"], "type": "normal" },
          { "fields": ["tenant_id", "uploader_id"], "type": "normal" },
          { "fields": ["tenant_id", "create_time"], "type": "normal" }
        ]
      }
    ],
    "api_contracts": [
      {
        "endpoint": "POST /api/v1/files/upload",
        "description": "文件上传（multipart/form-data）",
        "auth_required": true,
        "permissions": ["file:upload"],
        "request_body": {
          "file": { "type": "file", "required": true, "description": "文件内容" },
          "biz_type": { "type": "string", "required": false, "description": "业务类型" },
          "biz_id": { "type": "integer", "required": false, "description": "业务关联ID" }
        },
        "response": {
          "200": { "code": 0, "message": "上传成功", "data": { "id": 1, "url": "/api/v1/files/1/download" } },
          "400": { "code": 40000, "message": "不支持的文件格式" },
          "413": { "code": 41300, "message": "文件大小超过限制" }
        }
      },
      {
        "endpoint": "GET /api/v1/files/{id}/preview",
        "description": "获取文件预览信息",
        "auth_required": true,
        "permissions": ["file:preview"],
        "request_body": {},
        "response": {
          "200": { "code": 0, "message": "success", "data": { "preview_type": "pdf", "preview_url": "/api/v1/files/1/preview/data" } },
          "202": { "code": 20200, "message": "文件正在转换中，请稍后重试" }
        }
      },
      {
        "endpoint": "GET /api/v1/files/{id}/download",
        "description": "文件下载",
        "auth_required": true,
        "permissions": ["file:download"],
        "request_body": {},
        "response": {
          "200": "文件二进制流（Content-Disposition: attachment）",
          "404": { "code": 40400, "message": "文件不存在" }
        }
      },
      {
        "endpoint": "DELETE /api/v1/files/{id}",
        "description": "删除文件",
        "auth_required": true,
        "permissions": ["file:delete"],
        "request_body": {},
        "response": {
          "200": { "code": 0, "message": "删除成功" },
          "404": { "code": 40400, "message": "文件不存在" }
        }
      }
    ],
    "risks": [
      {
        "id": "RSK-001",
        "description": "大文件上传可能占用大量服务器内存和带宽",
        "probability": "high",
        "impact": "medium",
        "mitigation": "使用分片上传和流式处理，避免全量加载到内存；配置上传速率限制",
        "category": "technical"
      },
      {
        "id": "RSK-002",
        "description": "Office 文件转换为 PDF 可能失败或格式不完整",
        "probability": "medium",
        "impact": "medium",
        "mitigation": "设置转换超时（30s）；转换失败时提供降级方案（提示下载查看）；对转换失败的文件记录日志便于排查",
        "category": "technical"
      },
      {
        "id": "RSK-003",
        "description": "恶意文件上传（病毒、脚本注入）",
        "probability": "medium",
        "impact": "high",
        "mitigation": "文件类型通过 magic bytes 双重校验；文件重命名为 UUID 存储；图片预览使用 sandbox iframe 隔离",
        "category": "security"
      },
      {
        "id": "RSK-004",
        "description": "存储空间快速增长导致成本上升",
        "probability": "high",
        "impact": "low",
        "mitigation": "按租户设置存储配额；定期清理无效文件；考虑生命周期管理策略",
        "category": "business"
      }
    ],
    "success_metrics": [
      {
        "metric": "上传成功率",
        "target": "> 99.5%",
        "measurement_method": "统计上传 API 成功/失败比例",
        "measurement_frequency": "每天"
      },
      {
        "metric": "预览可用率",
        "target": "图片/PDF > 99.9%，Office > 95%",
        "measurement_method": "统计预览请求成功/失败比例",
        "measurement_frequency": "每天"
      },
      {
        "metric": "用户满意度",
        "target": "上传和预览流程无技术投诉",
        "measurement_method": "用户反馈跟踪",
        "measurement_frequency": "每月"
      }
    ]
  }
}
```

---

## 7. 反模式与常见错误 (Anti-patterns)

PM Agent 在分析需求和生成 PRD 时，必须避免以下常见错误。每一条反模式都附带了正确的做法说明。

### 7.1 混淆需求与实现细节

**错误做法**: 在需求描述中包含具体技术实现方案。

```json
// 错误
{
  "description": "使用 Redis 缓存用户数据，设置 30 分钟过期时间，使用 Spring Data Redis 作为客户端"
}

// 正确
{
  "description": "用户列表查询响应时间 < 200ms，支持 1 万条数据量下的快速分页查询"
}
```

**原则**: 需求描述"做什么"和"做到什么程度"，而非"怎么做"。技术实现方案由开发 Agent 在后续阶段决定。

### 7.2 验收标准模糊

**错误做法**: 验收标准包含主观判断词汇。

```json
// 错误
{
  "then": "页面加载速度要快"
}

// 正确
{
  "then": "页面首屏加载时间 < 3s（在 4G 网络环境下，Chrome 最新版）"
}
```

**原则**: 验收标准必须完全可量化、可测试。使用具体数值代替"快"、"好"、"流畅"等主观词汇。

### 7.3 缺少异常流程处理

**错误做法**: 只定义正常流程，忽略错误场景。

```json
// 错误 - 只有正常流程
{
  "acceptance_criteria": [
    {
      "given": "用户提交表单",
      "when": "点击保存按钮",
      "then": "数据保存成功"
    }
  ]
}

// 正确 - 包含异常流程
{
  "acceptance_criteria": [
    {
      "given": "用户填写完整有效信息",
      "when": "点击保存按钮",
      "then": "数据保存成功，提示'保存成功'，返回列表页"
    },
    {
      "given": "用户未填写必填项",
      "when": "点击保存按钮",
      "then": "表单不提交，必填字段标红显示'此项为必填'"
    },
    {
      "given": "用户提交时服务器异常",
      "when": "点击保存按钮",
      "then": "提示'保存失败，请稍后重试'，表单数据保留不丢失"
    },
    {
      "given": "用户提交时网络断开",
      "when": "点击保存按钮",
      "then": "提示'网络连接失败'，表单数据保留不丢失"
    }
  ]
}
```

**原则**: 每个用户故事至少覆盖 1 条正常流程 + 1 条异常流程。常见的异常场景包括：输入校验失败、权限不足、网络错误、服务器异常、数据冲突、并发操作。

### 7.4 忽略非功能需求

**错误做法**: 只关注功能需求，不考虑性能、安全、可用性等非功能需求。

```json
// 错误 - 完全没有非功能需求
{
  "non_functional_requirements": []
}

// 正确 - 至少考虑性能和安全
{
  "non_functional_requirements": [
    {
      "id": "NFR-001",
      "category": "performance",
      "description": "API 响应时间",
      "metric": "P95 < 200ms",
      "priority": "P0"
    },
    {
      "id": "NFR-002",
      "category": "security",
      "description": "接口认证",
      "metric": "所有 API 需要 JWT Token 验证",
      "priority": "P0"
    }
  ]
}
```

**原则**: 每份 PRD 必须包含至少 1 条性能需求和 1 条安全需求。根据业务场景补充其他维度的非功能需求。

### 7.5 需求粒度过大或过小

**错误做法**: 一个用户故事包含多个不相关功能，或拆分过细导致管理成本过高。

```json
// 错误 - 粒度过大
{
  "story": "作为一个用户，我想要使用完整的CRM系统，以便于管理客户关系"
}

// 错误 - 粒度过小
{
  "story": "作为一个用户，我想要点击按钮时按钮颜色变蓝，以便于知道我点击了"
}

// 正确 - 适中的粒度
{
  "story": "作为一个销售人员，我想要查看客户列表并按行业筛选，以便于快速找到目标客户"
}
```

**原则**: 一个用户故事应对应 1-5 天的开发工作量。如果故事过大（L/XL），应拆分为多个子故事。如果故事过小（XS 且非关键），考虑合并到相关故事中。

### 7.6 缺少边界条件

**错误做法**: 没有考虑空数据、大数据量、特殊字符等边界情况。

```json
// 错误 - 没有边界条件
{
  "description": "用户输入搜索关键词后显示搜索结果"
}

// 正确 - 包含边界条件说明
{
  "description": "用户输入搜索关键词后显示搜索结果。需处理：空关键词时显示全部数据；关键词超过100字符时截断；搜索无结果时显示空状态提示；特殊字符（SQL注入/XSS）需转义处理"
}
```

**原则**: 对于每个涉及用户输入的功能，必须考虑空值、超长、特殊字符、SQL 注入、XSS 等边界条件。对于数据展示功能，必须考虑空列表、大数据量分页等场景。

### 7.7 优先级分配不当

**错误做法**: 所有需求都标记为 P0，或者没有区分优先级的依据。

```json
// 错误 - 全部 P0
{
  "functional_requirements": [
    { "id": "FR-001", "priority": "P0" },
    { "id": "FR-002", "priority": "P0" },
    { "id": "FR-003", "priority": "P0" },
    { "id": "FR-004", "priority": "P0" },
    { "id": "FR-005", "priority": "P0" }
  ]
}

// 正确 - 按业务价值和技术依赖合理分配
{
  "functional_requirements": [
    { "id": "FR-001", "priority": "P0", "description": "核心功能，缺失则不可用" },
    { "id": "FR-002", "priority": "P0", "description": "其他P0需求的前置依赖" },
    { "id": "FR-003", "priority": "P1", "description": "重要但非核心" },
    { "id": "FR-004", "priority": "P2", "description": "锦上添花" },
    { "id": "FR-005", "priority": "P3", "description": "明确延期到下一版本" }
  ]
}
```

**原则**: P0 需求应控制在总需求数量的 30% 以内。P0 意味着"没有这个功能产品就不能发布"，不是"这个功能很重要"。区分"必须"和"重要"。

---

## 8. 输入说明 (Input)

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_request` | string | 是 | 用户的原始需求描述（自然语言） |
| `session_id` | string | 否 | 会话 ID，用于上下文关联和多轮对话 |
| `project_context` | string | 否 | 项目上下文信息（技术栈、已有模块等），有助于生成更贴合实际的 PRD |
| `existing_prd` | object | 否 | 已有 PRD 文档（用于需求变更场景），Agent 在此基础上更新 |

## 9. 输出说明 (Output)

PM Agent 执行完成后，返回以下结构：

```json
{
  "skill_id": "requirement_analysis",
  "status": "completed",
  "output": {
    "prd": { "...如第5节定义的完整JSON结构..." }
  }
}
```

下游消费方：
- **task-breakdown Skill**: 读取 `prd` 字段，拆解为开发任务
- **backend-development Skill**: 读取 `data_models`、`api_contracts` 字段，生成后端代码
- **frontend-development Skill**: 读取 `ui_specs`、`user_stories` 字段，生成前端代码
- **test-generation Skill**: 读取 `acceptance_criteria` 字段，生成测试用例

---

## 10. 版本历史 (Changelog)

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| 1.0.0 | 2024-04-25 | 初始版本，基础需求分析能力 |
| 1.1.0 | 2025-05-20 | 完善分析流程方法论；增加 PRD 模板；增加质量检查清单；增加反模式指南；增加详细示例；丰富元数据标签 |
