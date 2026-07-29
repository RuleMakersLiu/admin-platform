---
id: backend_development
name: backend-development
description: "Generate backend code including APIs, database models, and business logic. 根据需求生成后端代码，包括 API 接口、数据库模型、业务逻辑层，支持 Java/Spring Boot、Go/Gin、Python/FastAPI、PHP/Laravel。"
version: 1.1.0
category: development
agent_type: BE
metadata:
  hermes:
    tags: [backend, code-generation, api, database, spring-boot, gin, fastapi, laravel]
    related_skills: [requirement-analysis, task-breakdown, code-review]
---

# 后端开发 (Backend Development)

## 概述

后端开发技能是 AI 平台中 Backend Developer (BE) Agent 的核心能力，负责根据需求文档和交付包自动生成完整的后端代码。本技能支持四种主流后端技术栈，遵循统一的分层架构模式和项目规范，确保生成的代码具备生产级别的质量。

### 技术栈支持

| 技术栈 | 框架 | ORM | 适用场景 |
|--------|------|-----|---------|
| Java | Spring Boot 2.x/3.x | MyBatis-Plus | 企业级应用、微服务 |
| Go | Gin | GORM | 高性能服务、API 网关 |
| Python | FastAPI | SQLAlchemy (async) | AI 平台、快速开发 |
| PHP | Laravel | Eloquent | Web 应用、BFF 转发层 |

### 核心能力

- 根据交付包中的 API 契约生成 RESTful 接口
- 根据字段定义生成数据库模型和建表 SQL
- 生成完整的分层架构代码（Controller → Service → Repository → Model）
- 自动集成多租户、统一响应格式、分页等横切关注点
- 生成数据库迁移脚本（如适用）

---

## 代码生成流程

### 步骤 1: 解析输入

接收来自 Pipeline 交付包阶段的结构化输入：

```
输入源:
  - requirement_output  — 需求文档 (PRD)
  - delivery_output     — 交付包（含 API 契约、Mock 数据、权限规则）
  - backend_tech        — 目标技术栈标识
  - 项目代码参考         — 从 Git 仓库提取的关键文件（如有关联后端项目）
```

需要从交付包中提取的关键信息：
1. **API 接口列表** — 路径、方法、参数、响应格式
2. **数据模型定义** — 字段名、类型、约束、关联关系
3. **业务规则** — 校验逻辑、状态流转、权限控制
4. **技术栈要求** — 框架版本、依赖管理方式

### 步骤 2: 确定技术栈并选择模板

根据 `backend_tech` 字段匹配技术栈，未指定时默认使用 Java/Spring Boot：

| backend_tech 值 | 匹配规则 | 选用技术栈 |
|-----------------|---------|-----------|
| `java`, `spring`, `spring-boot` | 包含任一关键词 | Java + Spring Boot + MyBatis-Plus |
| `go`, `gin`, `golang` | 包含任一关键词 | Go + Gin + GORM |
| `python`, `fastapi`, `flask` | 包含任一关键词 | Python + FastAPI + SQLAlchemy |
| `php`, `laravel` | 包含任一关键词 | PHP + Laravel + Eloquent |
| 未指定或为空 | — | Java + Spring Boot（默认） |

### 步骤 3: 生成数据库模型

根据交付包中的字段定义，生成对应技术栈的 Entity/Model 类：

1. 表名使用 snake_case，类名使用 PascalCase
2. 所有表必须包含 `tenant_id`（BIGINT）字段，用于多租户隔离
3. 所有表必须包含 `create_time` 和 `update_time`（BIGINT 毫秒时间戳）
4. 软删除使用 `is_deleted` 字段（INT, 默认 0）
5. 主键使用 BIGINT 自增 ID
6. 为外键和常用查询字段创建索引

### 步骤 4: 生成分层架构代码

按照 Controller → Service → Repository/DAO → Entity/Model 的分层模式生成代码：

1. **Entity/Model** — 数据库映射、字段定义、类型转换
2. **Repository/DAO** — 数据访问层，封装 CRUD 和自定义查询
3. **Service** — 业务逻辑层，事务管理、校验、业务规则
4. **Controller/Router** — API 入口，参数校验、响应封装
5. **DTO/VO/Schema** — 请求/响应数据传输对象（如适用）

### 步骤 5: 生成数据库建表 SQL

生成标准化的建表 SQL 脚本，包含：
- 字段定义和 COMMENT
- 主键和索引
- 多租户字段和默认值
- 字符集使用 `utf8mb4`
- 存储引擎使用 `InnoDB`

### 步骤 6: 汇总输出

将所有代码文件按标准 JSON 格式汇总输出（详见输出格式章节）。

---

## 架构模式

### 分层架构

统一采用四层架构模式，各层职责清晰分离：

```
┌─────────────────────────────────────────┐
│  Controller / Router / Handler          │  接收请求、参数校验、响应封装
├─────────────────────────────────────────┤
│  Service / ServiceImpl                  │  业务逻辑、事务管理、权限检查
├─────────────────────────────────────────┤
│  Repository / DAO / Mapper              │  数据访问、SQL 构建、ORM 操作
├─────────────────────────────────────────┤
│  Entity / Model                         │  数据库映射、字段定义
└─────────────────────────────────────────┘
```

各层间通过接口或 Protocol 解耦，上层依赖下层抽象而非具体实现。

### 多租户 (Multi-Tenancy)

所有业务表必须包含 `tenant_id` 字段，数据隔离在 Repository 层实现：

```
规则:
1. 每个表包含 tenant_id BIGINT NOT NULL DEFAULT 0 字段
2. 所有 SELECT 查询必须带 WHERE tenant_id = ? 条件
3. INSERT 时自动填充当前请求的 tenant_id
4. UPDATE/DELETE 同样受 tenant_id 约束
5. Repository 层方法签名必须包含 tenant_id 参数
6. 索引: 每个表必须有 idx_tenant_id 索引
```

多租户 ID 从 JWT Token 中提取，通过中间件注入到请求上下文，Service 层从上下文获取后传递给 Repository 层。

### 时间戳规范

所有时间字段使用 BIGINT 毫秒时间戳，不使用 DATETIME/TIMESTAMP：

```
字段约定:
- create_time BIGINT NOT NULL — 创建时间（毫秒时间戳）
- update_time BIGINT NOT NULL — 更新时间（毫秒时间戳）
- 其他时间字段同样使用 BIGINT（如 expire_time, last_login_time）

写入时:
  create_time = System.currentTimeMillis() / int(time.time() * 1000)
  update_time = 同上（每次更新时刷新）
```

### 分页规范

统一的分页查询参数和响应格式：

**请求参数:**
```
page     — 页码，从 1 开始（默认 1）
pageSize — 每页条数（默认 10，最大 100）
sort     — 排序字段（可选）
order    — 排序方向 asc/desc（可选，默认 desc 按 create_time）
```

**响应格式:**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "list": [],
    "total": 100,
    "page": 1,
    "pageSize": 10,
    "totalPages": 10
  }
}
```

### 统一响应格式

所有 API 接口必须返回统一的 JSON 响应结构：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

**错误码体系:**

| 错误码 | 含义 | 说明 |
|-------|------|------|
| 200 | 成功 | 请求处理成功 |
| 400 | 参数错误 | 请求参数校验失败 |
| 401 | 未认证 | Token 缺失或无效 |
| 403 | 无权限 | 无访问权限 |
| 404 | 不存在 | 资源不存在 |
| 500 | 服务器错误 | 内部异常 |

### 软删除

使用 `is_deleted` 字段标记删除状态，不物理删除数据：

```
is_deleted INT NOT NULL DEFAULT 0 COMMENT '是否删除: 0未删除 1已删除'

查询时: WHERE is_deleted = 0 AND tenant_id = ?
删除时: UPDATE SET is_deleted = 1, update_time = ? WHERE id = ? AND tenant_id = ?
```

---

## 框架特定规范

### Java / Spring Boot

**项目结构:**
```
src/main/java/com/{company}/{module}/
├── controller/
│   └── XxxController.java
├── service/
│   ├── XxxService.java              (接口)
│   └── impl/
│       └── XxxServiceImpl.java      (实现)
├── mapper/
│   └── XxxMapper.java               (MyBatis-Plus Mapper)
├── entity/
│   └── Xxx.java                     (数据库实体)
├── dto/
│   ├── XxxQueryDTO.java             (查询参数)
│   ├── XxxCreateDTO.java            (创建参数)
│   └── XxxUpdateDTO.java            (更新参数)
├── vo/
│   ├── XxxVO.java                   (列表展示)
│   └── XxxDetailVO.java             (详情展示)
└── config/
    └── MyBatisPlusConfig.java        (分页插件配置)
```

> 注：`pom.xml`（Spring Boot parent + Web + MyBatis-Plus + MySQL）、`@SpringBootApplication` 主类、`src/main/resources/application.yml`（MySQL datasource）由平台在代码写盘后**自动脚手架兜底**，LLM 只需专注业务代码（Controller/Service/Mapper/Entity/DTO/VO + 建表 SQL）。若 LLM 已生成这些文件则跳过。

**Controller 规范:**
```java
@RestController
@RequestMapping("/api/{module}")
public class XxxController {

    @Autowired
    private XxxService xxxService;

    @GetMapping("/list")
    public Result<PageResult<XxxVO>> list(
            @RequestParam(defaultValue = "1") Integer page,
            @RequestParam(defaultValue = "10") Integer pageSize,
            @RequestParam(required = false) String keyword,
            @RequestHeader("X-Tenant-Id") Long tenantId) {
        // ...
    }

    @PostMapping
    public Result<Void> create(@RequestBody @Valid XxxCreateDTO dto,
                                @RequestHeader("X-Tenant-Id") Long tenantId) {
        // ...
    }

    @PutMapping("/{id}")
    public Result<Void> update(@PathVariable Long id,
                                @RequestBody @Valid XxxUpdateDTO dto,
                                @RequestHeader("X-Tenant-Id") Long tenantId) {
        // ...
    }

    @DeleteMapping("/{id}")
    public Result<Void> delete(@PathVariable Long id,
                                @RequestHeader("X-Tenant-Id") Long tenantId) {
        // ...
    }
}
```

**Entity 规范:**
```java
@Data
@TableName("xxx_table")
public class Xxx {
    @TableId(type = IdType.AUTO)
    private Long id;

    private String name;
    private Integer status;
    private Long tenantId;
    private Long createTime;
    private Long updateTime;

    @TableLogic
    private Integer isDeleted;
}
```

**Service 规范:**
- 接口与实现分离（XxxService 接口 + XxxServiceImpl 实现类）
- 使用 `@Transactional` 管理事务
- 参数校验在 Service 层进行业务级校验
- tenant_id 由 Controller 传入，不依赖 ThreadLocal

**依赖版本参考:**
- Spring Boot 2.7.x / 3.x
- MyBatis-Plus 3.5.x
- Lombok（@Data, @Builder 等）
- JSR-303 Validation（@Valid, @NotNull 等）

### Go / Gin

**项目结构:**
```
├── cmd/
│   └── main.go
├── internal/
│   ├── config/
│   │   └── config.go
│   ├── handler/
│   │   └── xxx_handler.go
│   ├── service/
│   │   └── xxx_service.go
│   ├── repository/
│   │   └── xxx_repository.go
│   ├── model/
│   │   └── xxx.go
│   ├── middleware/
│   │   ├── auth.go
│   │   └── tenant.go
│   └── router/
│       └── router.go
├── pkg/
│   ├── response/
│   │   └── response.go              (统一响应)
│   └── pagination/
│       └── pagination.go            (分页工具)
└── config.yaml
```

**Handler 规范:**
```go
type XxxHandler struct {
    svc *service.XxxService
}

func (h *XxxHandler) List(c *gin.Context) {
    tenantID := middleware.GetTenantID(c)
    page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
    pageSize, _ := strconv.Atoi(c.DefaultQuery("pageSize", "10"))

    result, total, err := h.svc.List(c.Request.Context(), tenantID, page, pageSize)
    if err != nil {
        response.Error(c, http.StatusInternalServerError, err.Error())
        return
    }
    response.Success(c, gin.H{
        "list":       result,
        "total":      total,
        "page":       page,
        "pageSize":   pageSize,
    })
}
```

**Model 规范:**
```go
type Xxx struct {
    ID         int64  `gorm:"primaryKey;autoIncrement" json:"id"`
    Name       string `gorm:"size:100;not null" json:"name"`
    Status     int    `gorm:"default:1" json:"status"`
    TenantID   int64  `gorm:"index;not null;default:0" json:"tenantId"`
    CreateTime int64  `gorm:"not null" json:"createTime"`
    UpdateTime int64  `gorm:"not null" json:"updateTime"`
    IsDeleted  int    `gorm:"default:0" json:"-"`
}
```

**中间件链:**
```
请求 → Logger → Recovery → CORS → Auth(JWT) → Tenant(注入tenant_id) → Handler
```

**Repository 规范:**
- 所有查询必须带 `tenant_id` 条件
- 使用 GORM 的 Scopes 机制封装多租户和软删除过滤
- 分页使用 `pkg/pagination` 工具封装

### Python / FastAPI

**项目结构:**
```
├── app/
│   ├── api/
│   │   ├── __init__.py
│   │   └── xxx.py                    (Router)
│   ├── models/
│   │   ├── __init__.py
│   │   └── xxx.py                    (SQLAlchemy Model)
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── xxx.py                    (Pydantic Schema)
│   ├── services/
│   │   ├── __init__.py
│   │   └── xxx_service.py
│   ├── core/
│   │   ├── config.py
│   │   └── database.py
│   └── main.py
├── alembic/
│   └── versions/                     (数据库迁移)
├── requirements.txt
└── pyproject.toml
```

**Router 规范:**
```python
from fastapi import APIRouter, Depends, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/{module}", tags=["{module}"])

@router.get("/list", response_model=PageResponse[XxxVO])
async def list_items(
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    keyword: str = Query(None),
    tenant_id: int = Header(..., alias="X-Tenant-Id"),
    db: AsyncSession = Depends(get_db),
):
    result = await XxxService.list(db, tenant_id, page, pageSize, keyword)
    return PageResponse(data=result)
```

**Model 规范:**
```python
from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class Xxx(Base):
    __tablename__ = "xxx_table"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[int] = mapped_column(Integer, default=1)
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)
```

**Schema 规范:**
```python
from pydantic import BaseModel, Field
from typing import Optional

class XxxCreate(BaseModel):
    name: str = Field(..., max_length=100, description="名称")
    description: Optional[str] = Field(None, description="描述")

class XxxUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None

class XxxVO(BaseModel):
    id: int
    name: str
    status: int
    create_time: int
    update_time: int

    class Config:
        from_attributes = True
```

**Service 规范:**
- 使用 async/await 异步编程模型
- 所有数据库操作通过 AsyncSession
- 时间戳使用 `int(time.time() * 1000)` 生成
- Service 是无状态的纯函数集合（不依赖全局状态）

### PHP / Laravel

**项目结构:**
```
app/
├── Http/
│   ├── Controllers/
│   │   └── XxxController.php
│   ├── Requests/
│   │   ├── StoreXxxRequest.php       (创建验证)
│   │   └── UpdateXxxRequest.php      (更新验证)
│   └── Resources/
│       └── XxxResource.php           (API Resource 转换)
├── Models/
│   └── Xxx.php
├── Services/
│   └── XxxService.php
└── Repositories/
    └── XxxRepository.php
database/
├── migrations/
│   └── 2026_01_01_000000_create_xxx_table.php
routes/
└── api.php
```

**Controller 规范:**
```php
class XxxController extends Controller
{
    public function __construct(
        private XxxService $xxxService
    ) {}

    public function index(Request $request): JsonResponse
    {
        $tenantId = $request->header('X-Tenant-Id');
        $result = $this->xxxService->list(
            $tenantId,
            $request->input('page', 1),
            $request->input('pageSize', 10),
            $request->input('keyword')
        );
        return $this->success($result);
    }

    public function store(StoreXxxRequest $request): JsonResponse
    {
        $tenantId = $request->header('X-Tenant-Id');
        $this->xxxService->create($tenantId, $request->validated());
        return $this->success();
    }
}
```

**Model 规范:**
```php
class Xxx extends Model
{
    protected $table = 'xxx_table';

    protected $fillable = [
        'name', 'status', 'tenant_id', 'create_time', 'update_time',
    ];

    protected $casts = [
        'id' => 'integer',
        'tenant_id' => 'integer',
        'create_time' => 'integer',
        'update_time' => 'integer',
        'is_deleted' => 'integer',
    ];

    // 软删除使用 is_deleted 字段而非 Laravel SoftDeletes
    public function scopeNotDeleted($query)
    {
        return $query->where('is_deleted', 0);
    }

    public function scopeTenant($query, $tenantId)
    {
        return $query->where('tenant_id', $tenantId);
    }
}
```

**Form Request 验证:**
```php
class StoreXxxRequest extends FormRequest
{
    public function rules(): array
    {
        return [
            'name' => 'required|string|max:100',
            'description' => 'nullable|string',
            'status' => 'nullable|integer|in:0,1',
        ];
    }
}
```

### PHP BFF 模式

当技术栈包含 PHP 作为 BFF（Backend For Frontend）层时，PHP 不直接操作数据库，而是作为 API 网关转发请求到后端 Java 服务：

**架构:**
```
前端 → PHP BFF (Laravel) → Java 后端 (Spring Boot API)
         │                      │
         ├─ 鉴权/JWT 校验       ├─ 业务逻辑
         ├─ 参数转换/聚合       ├─ 数据库操作
         ├─ 日志记录            └─ 核心数据处理
         └─ 响应格式化
```

**BFF Controller 规范:**
```php
class XxxController extends Controller
{
    private BackendApiClient $apiClient;

    public function __construct(BackendApiClient $apiClient)
    {
        $this->apiClient = $apiClient;
    }

    public function index(Request $request): JsonResponse
    {
        $token = $request->header('Authorization');
        $tenantId = $request->header('X-Tenant-Id');

        // 转发到后端 Java API
        $response = $this->apiClient->get('/api/xxx/list', [
            'headers' => [
                'Authorization' => $token,
                'X-Tenant-Id' => $tenantId,
            ],
            'query' => $request->only(['page', 'pageSize', 'keyword']),
        ]);

        return $this->success($response['data']);
    }
}
```

**BFF Service 规范:**
```php
class BackendApiClient
{
    private HttpClient $http;
    private string $baseUrl;

    public function __construct()
    {
        $this->http = Http::timeout(30);
        $this->baseUrl = config('services.backend.url'); // 如 http://java-api:8081
    }

    public function get(string $uri, array $options = []): array
    {
        $response = $this->http->withHeaders($options['headers'] ?? [])
            ->get($this->baseUrl . $uri, $options['query'] ?? []);

        if ($response->failed()) {
            Log::error("Backend API error: {$uri}", [
                'status' => $response->status(),
                'body' => $response->body(),
            ]);
            throw new BackendApiException('后端服务调用失败');
        }

        return $response->json();
    }

    public function post(string $uri, array $data, array $options = []): array
    {
        $response = $this->http->withHeaders($options['headers'] ?? [])
            ->post($this->baseUrl . $uri, $data);

        return $response->json();
    }
}
```

**BFF 注意事项:**
- 不包含 Eloquent Model 和数据库迁移
- 不直接操作数据库，所有数据来自后端 API
- 使用 Laravel Http Client 或 Guzzle 调用后端接口
- 处理参数格式转换（前端 camelCase ↔ 后端 snake_case）
- 统一异常处理和日志记录
- 保持后端 API 的原始响应格式（code/msg/data）

---

## API 设计标准

### RESTful 约定

```
GET    /api/{module}/list          — 分页查询列表
GET    /api/{module}/{id}          — 根据 ID 获取详情
POST   /api/{module}               — 新增
PUT    /api/{module}/{id}          — 全量更新
PATCH  /api/{module}/{id}          — 部分更新
DELETE /api/{module}/{id}          — 删除（软删除）
PUT    /api/{module}/{id}/status   — 状态变更
```

### URL 命名规范

- 模块名使用小写字母 + 短横线分隔（kebab-case）：`/api/user-group/list`
- 路径参数使用复数形式或业务名词
- 避免在 URL 中使用动词，用 HTTP Method 表达操作语义

### 请求参数规范

**Query 参数（GET 请求）:**
```
page=1&pageSize=10&keyword=xxx&status=1&sort=create_time&order=desc
```

**Body 参数（POST/PUT 请求）:**
- 使用 JSON 格式（Content-Type: application/json）
- 字段名使用 camelCase（与前端保持一致）
- 必填字段在 DTO/Schema 中标注 @NotNull / required

**Header 参数:**
```
Authorization: Bearer <token>       — JWT 认证令牌
X-Tenant-Id: 1                      — 租户 ID
Content-Type: application/json       — 请求体格式
```

### 统一响应封装

**成功响应:**
```json
{
  "code": 200,
  "message": "success",
  "data": { ... }
}
```

**分页响应:**
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "list": [ ... ],
    "total": 100,
    "page": 1,
    "pageSize": 10,
    "totalPages": 10
  }
}
```

**错误响应:**
```json
{
  "code": 400,
  "message": "参数校验失败: name 不能为空",
  "data": null
}
```

**校验错误详情:**
```json
{
  "code": 400,
  "message": "参数校验失败",
  "data": {
    "errors": [
      {"field": "name", "message": "名称不能为空"},
      {"field": "email", "message": "邮箱格式不正确"}
    ]
  }
}
```

---

## 数据库规范

### 表名和字段名

```
表名:   snake_case, 小写, 使用下划线分隔
        示例: sys_admin, gen_function_config, deploy_task

字段名: snake_case, 小写, 使用下划线分隔
        示例: tenant_id, create_time, is_deleted, user_name

Java 字段: camelCase
        示例: tenantId, createTime, isDeleted, userName

Go 字段: PascalCase (导出)
        示例: TenantID, CreateTime, IsDeleted, UserName

Python 字段: snake_case (SQLAlchemy mapped_column)
        示例: tenant_id, create_time, is_deleted

PHP 字段: snake_case (Eloquent)
        示例: tenant_id, create_time, is_deleted
```

### 标准字段

每个业务表必须包含以下标准字段：

```sql
`id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
`tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
`create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
`update_time` bigint(20) NOT NULL COMMENT '更新时间(时间戳毫秒)',
`is_deleted` int(11) NOT NULL DEFAULT 0 COMMENT '是否删除: 0未删除 1已删除',
PRIMARY KEY (`id`),
KEY `idx_tenant_id` (`tenant_id`)
```

### 索引策略

```
1. 主键索引:  id (BIGINT AUTO_INCREMENT)
2. 租户索引:  idx_tenant_id (每个表必须有)
3. 唯一索引:  uk_xxx (业务唯一约束，通常组合 tenant_id)
4. 外键索引:  idx_xxx_id (外键字段)
5. 状态索引:  idx_status (常用筛选字段)
6. 时间索引:  idx_create_time (常用排序字段)
7. 组合索引:  按查询频率设计，遵循最左前缀原则
```

### 建表 SQL 模板

```sql
DROP TABLE IF EXISTS `{table_name}`;
CREATE TABLE `{table_name}` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  -- 业务字段 --
  `name` varchar(100) NOT NULL COMMENT '名称',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 0禁用 1启用',
  -- 标准字段 --
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(时间戳毫秒)',
  `is_deleted` int(11) NOT NULL DEFAULT 0 COMMENT '是否删除: 0未删除 1已删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_name_tenant` (`name`, `tenant_id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_status` (`status`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='{表注释}';
```

### 数据库迁移脚本

对于支持 Migration 的框架（Laravel、FastAPI/Alembic），同时生成迁移文件：

- Laravel: `database/migrations/YYYY_MM_DD_HHMMSS_create_xxx_table.php`
- Python/Alembic: `alembic/versions/xxx_create_xxx_table.py`
- Java/MyBatis-Plus: 生成 SQL 脚本文件 `sql/xxx_table.sql`

---

## 输出格式

### 代码文件汇总

在所有代码之后，必须使用以下 JSON 格式汇总生成的所有文件。这个 JSON 会被 Pipeline 解析器自动提取：

```json
[
  {
    "path": "src/main/java/com/example/module/controller/XxxController.java",
    "content": "完整文件内容",
    "language": "java"
  },
  {
    "path": "src/main/java/com/example/module/service/XxxService.java",
    "content": "完整文件内容",
    "language": "java"
  },
  {
    "path": "src/main/java/com/example/module/service/impl/XxxServiceImpl.java",
    "content": "完整文件内容",
    "language": "java"
  },
  {
    "path": "src/main/java/com/example/module/mapper/XxxMapper.java",
    "content": "完整文件内容",
    "language": "java"
  },
  {
    "path": "src/main/java/com/example/module/entity/Xxx.java",
    "content": "完整文件内容",
    "language": "java"
  },
  {
    "path": "src/main/java/com/example/module/dto/XxxCreateDTO.java",
    "content": "完整文件内容",
    "language": "java"
  },
  {
    "path": "src/main/java/com/example/module/vo/XxxVO.java",
    "content": "完整文件内容",
    "language": "java"
  },
  {
    "path": "sql/xxx_table.sql",
    "content": "完整建表SQL",
    "language": "sql"
  }
]
```

### 文件路径规范

| 技术栈 | 路径前缀 | 示例 |
|--------|---------|------|
| Java | `src/main/java/com/{company}/{module}/` | `src/main/java/com/example/system/controller/AdminController.java` |
| Go | `internal/` | `internal/handler/admin_handler.go` |
| Python | `app/` | `app/api/admin.py` |
| PHP | `app/Http/` + `app/Models/` + `app/Services/` | `app/Http/Controllers/AdminController.php` |
| SQL | `sql/` | `sql/sys_admin.sql` |
| Migration | `database/migrations/` | `database/migrations/2026_01_01_create_admin_table.php` |

### Markdown 格式输出（Fallback）

每个代码文件在 JSON 汇总之前，也应以 Markdown 代码块格式输出，方便人工阅读：

```
### 文件: src/main/java/com/example/module/controller/XxxController.java
```java
// 完整代码内容
```

### 文件: sql/xxx_table.sql
```sql
-- 完整 SQL 内容
```
```

---

## 完整示例

### 示例 1: Java/Spring Boot — 用户组管理模块

**输入需求:** 需要一个用户组管理功能，支持用户组的增删改查，包含组名称、父级组、层级路径、权限列表、排序、状态等字段。

**输出文件:**

### 文件: src/main/java/com/example/system/controller/AdminGroupController.java
```java
package com.example.system.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.example.common.Result;
import com.example.common.PageResult;
import com.example.system.dto.AdminGroupCreateDTO;
import com.example.system.dto.AdminGroupUpdateDTO;
import com.example.system.dto.AdminGroupQueryDTO;
import com.example.system.service.AdminGroupService;
import com.example.system.vo.AdminGroupVO;
import com.example.system.vo.AdminGroupDetailVO;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.validation.Valid;

@RestController
@RequestMapping("/api/admin-group")
public class AdminGroupController {

    @Autowired
    private AdminGroupService adminGroupService;

    @GetMapping("/list")
    public Result<PageResult<AdminGroupVO>> list(
            @Validated AdminGroupQueryDTO query,
            @RequestHeader("X-Tenant-Id") Long tenantId) {
        query.setTenantId(tenantId);
        PageResult<AdminGroupVO> result = adminGroupService.list(query);
        return Result.success(result);
    }

    @GetMapping("/{id}")
    public Result<AdminGroupDetailVO> detail(
            @PathVariable Long id,
            @RequestHeader("X-Tenant-Id") Long tenantId) {
        AdminGroupDetailVO detail = adminGroupService.getDetail(id, tenantId);
        return Result.success(detail);
    }

    @PostMapping
    public Result<Void> create(
            @RequestBody @Valid AdminGroupCreateDTO dto,
            @RequestHeader("X-Tenant-Id") Long tenantId) {
        dto.setTenantId(tenantId);
        adminGroupService.create(dto);
        return Result.success();
    }

    @PutMapping("/{id}")
    public Result<Void> update(
            @PathVariable Long id,
            @RequestBody @Valid AdminGroupUpdateDTO dto,
            @RequestHeader("X-Tenant-Id") Long tenantId) {
        adminGroupService.update(id, tenantId, dto);
        return Result.success();
    }

    @DeleteMapping("/{id}")
    public Result<Void> delete(
            @PathVariable Long id,
            @RequestHeader("X-Tenant-Id") Long tenantId) {
        adminGroupService.delete(id, tenantId);
        return Result.success();
    }
}
```

### 文件: src/main/java/com/example/system/entity/AdminGroup.java
```java
package com.example.system.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

@Data
@TableName("sys_admin_group")
public class AdminGroup {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String name;

    private Long parentId;

    private String path;

    private String power;

    private Integer isSuper;

    private Long tenantId;

    private Integer sort;

    private Integer status;

    private Long createTime;

    private Long updateTime;

    @TableLogic
    private Integer isDeleted;
}
```

### 文件: sql/sys_admin_group.sql
```sql
DROP TABLE IF EXISTS `sys_admin_group`;
CREATE TABLE `sys_admin_group` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `name` varchar(50) NOT NULL COMMENT '组名称',
  `parent_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '父级ID',
  `path` varchar(500) NOT NULL DEFAULT '0' COMMENT '层级路径(如: 0,1,2)',
  `power` text COMMENT '权限标识列表(JSON数组)',
  `is_super` tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否超级管理员: 0否 1是',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `sort` int(11) NOT NULL DEFAULT 0 COMMENT '排序',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '状态: 0禁用 1启用',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(时间戳毫秒)',
  `is_deleted` int(11) NOT NULL DEFAULT 0 COMMENT '是否删除: 0未删除 1已删除',
  PRIMARY KEY (`id`),
  KEY `idx_parent_id` (`parent_id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_path` (`path`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='管理员组表';
```

### JSON 汇总:
```json
[
  {"path": "src/main/java/com/example/system/controller/AdminGroupController.java", "content": "...", "language": "java"},
  {"path": "src/main/java/com/example/system/entity/AdminGroup.java", "content": "...", "language": "java"},
  {"path": "src/main/java/com/example/system/service/AdminGroupService.java", "content": "...", "language": "java"},
  {"path": "src/main/java/com/example/system/service/impl/AdminGroupServiceImpl.java", "content": "...", "language": "java"},
  {"path": "src/main/java/com/example/system/mapper/AdminGroupMapper.java", "content": "...", "language": "java"},
  {"path": "src/main/java/com/example/system/dto/AdminGroupCreateDTO.java", "content": "...", "language": "java"},
  {"path": "src/main/java/com/example/system/dto/AdminGroupUpdateDTO.java", "content": "...", "language": "java"},
  {"path": "src/main/java/com/example/system/dto/AdminGroupQueryDTO.java", "content": "...", "language": "java"},
  {"path": "src/main/java/com/example/system/vo/AdminGroupVO.java", "content": "...", "language": "java"},
  {"path": "src/main/java/com/example/system/vo/AdminGroupDetailVO.java", "content": "...", "language": "java"},
  {"path": "sql/sys_admin_group.sql", "content": "...", "language": "sql"}
]
```

### 示例 2: Python/FastAPI — 知识库管理模块

**输入需求:** 需要一个知识库管理功能，支持知识条目的创建、编辑、删除、列表查询和搜索，包含标题、内容、分类、标签、来源、版本等字段。

**输出文件:**

### 文件: app/models/knowledge.py
```python
"""知识库模型"""
import time
from typing import Optional
from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Knowledge(Base):
    """知识库模型"""
    __tablename__ = "agent_knowledge"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    knowledge_id: Mapped[str] = mapped_column(String(64), unique=True)
    project_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(64))
    tags: Mapped[Optional[str]] = mapped_column(String(255))
    source: Mapped[Optional[str]] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, default=1)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding_status: Mapped[str] = mapped_column(String(32), default="pending")
    create_time: Mapped[int] = mapped_column(
        BigInteger, default=lambda: int(time.time() * 1000)
    )
    update_time: Mapped[int] = mapped_column(
        BigInteger, default=lambda: int(time.time() * 1000)
    )
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)
```

### 文件: app/schemas/knowledge.py
```python
"""知识库 Pydantic Schemas"""
from pydantic import BaseModel, Field
from typing import Optional


class KnowledgeCreate(BaseModel):
    title: str = Field(..., max_length=255, description="标题")
    content: str = Field(..., description="内容")
    category: Optional[str] = Field(None, max_length=64, description="分类")
    tags: Optional[str] = Field(None, max_length=255, description="标签")
    source: Optional[str] = Field(None, max_length=255, description="来源")


class KnowledgeUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    content: Optional[str] = None
    category: Optional[str] = Field(None, max_length=64)
    tags: Optional[str] = None
    source: Optional[str] = None


class KnowledgeVO(BaseModel):
    id: int
    knowledge_id: str
    title: str
    content: str
    category: Optional[str]
    tags: Optional[str]
    source: Optional[str]
    version: int
    view_count: int
    embedding_status: str
    create_time: int
    update_time: int

    class Config:
        from_attributes = True


class KnowledgeQuery(BaseModel):
    page: int = Field(1, ge=1)
    pageSize: int = Field(10, ge=1, le=100)
    keyword: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
```

### 文件: app/api/knowledge.py
```python
"""知识库 API 路由"""
from fastapi import APIRouter, Depends, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.knowledge import KnowledgeCreate, KnowledgeUpdate, KnowledgeVO, KnowledgeQuery
from app.services.knowledge_service import KnowledgeService
from app.common.response import success, PageResponse

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/list")
async def list_knowledge(
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    keyword: str = Query(None),
    category: str = Query(None),
    tenant_id: int = Header(..., alias="X-Tenant-Id"),
    db: AsyncSession = Depends(get_db),
):
    query = KnowledgeQuery(
        page=page, pageSize=pageSize, keyword=keyword, category=category
    )
    items, total = await KnowledgeService.list(db, tenant_id, query)
    return success(data={"list": items, "total": total, "page": page, "pageSize": pageSize})


@router.get("/{knowledge_id}")
async def get_knowledge(
    knowledge_id: str,
    tenant_id: int = Header(..., alias="X-Tenant-Id"),
    db: AsyncSession = Depends(get_db),
):
    item = await KnowledgeService.get_by_id(db, knowledge_id, tenant_id)
    return success(data=item)


@router.post
async def create_knowledge(
    dto: KnowledgeCreate,
    tenant_id: int = Header(..., alias="X-Tenant-Id"),
    db: AsyncSession = Depends(get_db),
):
    await KnowledgeService.create(db, tenant_id, dto)
    return success()


@router.put("/{knowledge_id}")
async def update_knowledge(
    knowledge_id: str,
    dto: KnowledgeUpdate,
    tenant_id: int = Header(..., alias="X-Tenant-Id"),
    db: AsyncSession = Depends(get_db),
):
    await KnowledgeService.update(db, knowledge_id, tenant_id, dto)
    return success()


@router.delete("/{knowledge_id}")
async def delete_knowledge(
    knowledge_id: str,
    tenant_id: int = Header(..., alias="X-Tenant-Id"),
    db: AsyncSession = Depends(get_db),
):
    await KnowledgeService.delete(db, knowledge_id, tenant_id)
    return success()
```

### 文件: sql/agent_knowledge.sql
```sql
DROP TABLE IF EXISTS `agent_knowledge`;
CREATE TABLE `agent_knowledge` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `knowledge_id` varchar(64) NOT NULL COMMENT '知识条目ID',
  `project_id` bigint(20) DEFAULT NULL COMMENT '项目ID',
  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',
  `title` varchar(255) NOT NULL COMMENT '标题',
  `content` text NOT NULL COMMENT '内容',
  `category` varchar(64) DEFAULT NULL COMMENT '分类',
  `tags` varchar(255) DEFAULT NULL COMMENT '标签',
  `source` varchar(255) DEFAULT NULL COMMENT '来源',
  `version` int(11) NOT NULL DEFAULT 1 COMMENT '版本号',
  `view_count` int(11) NOT NULL DEFAULT 0 COMMENT '查看次数',
  `embedding_status` varchar(32) NOT NULL DEFAULT 'pending' COMMENT '向量化状态',
  `create_time` bigint(20) NOT NULL COMMENT '创建时间(时间戳毫秒)',
  `update_time` bigint(20) NOT NULL COMMENT '更新时间(时间戳毫秒)',
  `is_deleted` int(11) NOT NULL DEFAULT 0 COMMENT '是否删除: 0未删除 1已删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_knowledge_id` (`knowledge_id`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_category` (`category`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库表';
```

### JSON 汇总:
```json
[
  {"path": "app/models/knowledge.py", "content": "...", "language": "python"},
  {"path": "app/schemas/knowledge.py", "content": "...", "language": "python"},
  {"path": "app/api/knowledge.py", "content": "...", "language": "python"},
  {"path": "app/services/knowledge_service.py", "content": "...", "language": "python"},
  {"path": "sql/agent_knowledge.sql", "content": "...", "language": "sql"}
]
```

---

## 输入 (Input)

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `requirement_output` | string | 是 | 需求文档 (PRD)，包含功能需求、用户故事、验收标准 |
| `delivery_output` | string | 是 | 交付包，包含 API 契约、字段定义、Mock 数据、权限规则 |
| `backend_tech` | string | 否 | 目标技术栈标识，未指定则默认 Java/Spring Boot |
| `session_id` | string | 否 | Pipeline 会话 ID |
| `fix_feedback` | string | 否 | Code Review 或测试阶段的修复反馈 |
| `project_context` | string | 否 | 从 Git 仓库提取的项目代码参考 |

## 输出 (Output)

| 字段 | 类型 | 说明 |
|------|------|------|
| `output` | string | 完整的 Markdown 格式输出（含代码块和 JSON 汇总） |
| `code_files` | dict | 自动解析的文件映射 `{path: content}` |
| `structured_output` | dict | 解析后的结构化数据 |

---

## 反模式 (Anti-Patterns)

以下是代码生成时必须避免的常见错误：

### 数据库相关

1. **忘记 tenant_id** — 所有业务表必须包含 tenant_id 字段，查询时必须带 tenant_id 条件
2. **使用 DATETIME 时间类型** — 时间字段必须使用 BIGINT 毫秒时间戳，不使用 DATE/DATETIME/TIMESTAMP
3. **物理删除** — 禁止使用 DELETE 物理删除数据，必须使用 is_deleted 软删除
4. **缺少索引** — tenant_id、外键、status、create_time 等常用字段必须建立索引
5. **表名使用大写或驼峰** — 表名和字段名必须使用 snake_case 小写
6. **缺少字段注释** — 每个字段必须有 COMMENT，说明字段含义和取值范围

### API 相关

7. **不一致的响应格式** — 所有接口必须返回 `{code, message, data}` 统一格式，不能有例外
8. **分页参数从 0 开始** — page 参数从 1 开始，不是 0
9. **未校验参数** — 请求参数必须进行校验（@Valid / Pydantic / Form Request）
10. **GET 请求包含 Request Body** — GET 请求参数使用 Query 参数，不使用 Request Body
11. **缺少认证信息** — 所有业务接口必须接收并验证 Authorization 和 X-Tenant-Id
12. **硬编码错误信息** — 错误消息应使用错误码 + 可配置消息，不要硬编码中文提示

### 架构相关

13. **Controller 包含业务逻辑** — Controller 只做参数接收和响应封装，业务逻辑在 Service 层
14. **Service 直接操作 SQL** — Service 调用 Repository/Mapper，不直接编写 SQL 字符串
15. **缺少 DTO/VO 转换** — 不要直接返回 Entity/Model 给前端，使用 DTO/VO/Schema 隔离
16. **Service 层依赖 Request 对象** — Service 层方法应接收纯参数，不依赖 HTTP Request 对象
17. **跨租户数据访问** — 查询时必须同时过滤 `tenant_id` 和 `is_deleted`，不能只过滤其一

### 安全相关

18. **SQL 注入** — 禁止拼接 SQL 字符串，必须使用参数化查询或 ORM
19. **敏感信息明文存储** — 密码必须 BCrypt 加密，Token 必须有过期时间
20. **未做权限检查** — 接口级别和按钮级别的权限检查都不能遗漏
21. **异常堆栈直接返回** — 生产环境禁止将异常堆栈信息返回给前端

### 代码质量

22. **魔法数字** — 状态值、类型值等使用常量或枚举定义，不直接使用数字字面量
23. **缺少日志** — 关键操作（增删改）必须记录操作日志
24. **事务未管理** — 涉及多表操作的方法必须使用事务（@Transactional / db.begin()）
25. **忽略并发问题** — 更新操作应考虑乐观锁或 CAS 机制，避免脏写

---

## 质量检查清单

生成代码后，按以下清单自查：

- [ ] 所有表包含 tenant_id、create_time、update_time、is_deleted 字段
- [ ] 所有查询带 tenant_id 和 is_deleted 过滤
- [ ] 时间字段使用 BIGINT 毫秒时间戳
- [ ] API 返回统一的 `{code, message, data}` 格式
- [ ] 分页使用 page/pageSize 参数（page 从 1 开始）
- [ ] Controller 不包含业务逻辑
- [ ] Service 层不依赖 HTTP 对象
- [ ] 建表 SQL 包含索引和 COMMENT
- [ ] 参数校验完整（必填、长度、格式）
- [ ] 软删除替代物理删除
- [ ] 输出包含 JSON 汇总文件列表
