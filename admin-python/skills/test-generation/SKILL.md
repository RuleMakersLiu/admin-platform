---
id: test_generation
name: test-generation
description: "Generate executable test scripts for unit, integration, and E2E testing. 根据需求和代码生成可执行的测试脚本，支持单元测试、集成测试和E2E测试。"
version: 1.1.0
category: testing
agent_type: QA
metadata:
  hermes:
    tags: [testing, test-cases, unit-test, integration-test, e2e, pytest, junit]
    related_skills: [code-review, backend-development, frontend-development]
---

# 测试脚本生成 (Test Generation)

## 概述

本 Skill 由 QA Agent 驱动，通过 LLM 分析需求文档、源代码和 Code Review 结果，
自动生成**可执行的测试脚本**（而非静态的测试用例文档）。输出的测试脚本可被
`test_runner` Pipeline Skill 直接执行，形成「生成 → 执行 → 反馈 → 修复」的闭环。

核心能力：

- **需求驱动**：从 PRD / 用户故事中提取可测试的场景
- **代码感知**：分析函数签名、分支逻辑、错误路径，生成高覆盖率测试
- **多语言支持**：Java / Go / Python / JavaScript / TypeScript / PHP
- **分层生成**：单元测试 (Unit) / 集成测试 (Integration) / 端到端测试 (E2E)
- **结构化输出**：JSON `code_files` 格式，由 `code_writer` Skill 写入工作区

---

## 测试金字塔 (Testing Pyramid)

测试生成遵循经典金字塔比例，确保测试套件在速度与覆盖率之间取得平衡：

```
          ┌──────────┐
          │  E2E 10% │   ← 全链路用户流程（慢、脆弱、高价值）
          ├──────────┤
          │ 集成 20% │   ← API 接口、数据库交互、外部服务
          ├──────────┤
          │ 单元 70% │   ← 函数、方法、纯逻辑（快、稳定、低成本）
          └──────────┘
```

### 单元测试 (Unit Tests) — 70%

- **测试目标**：独立的函数、方法、工具类、纯逻辑组件
- **隔离策略**：使用 Mock / Stub 替代外部依赖（数据库、HTTP、文件系统）
- **命名规范**：`test_<function>_<scenario>_<expected_result>`
- **执行速度**：单个用例 < 100ms
- **覆盖要求**：
  - 正常输入和返回值
  - 空值 / None / nil / null 边界
  - 非法参数类型
  - 数值溢出 / 下溢
  - 字符串边界（空串、超长串、特殊字符）

### 集成测试 (Integration Tests) — 20%

- **测试目标**：API 接口端到端、数据库 CRUD、缓存交互、消息队列
- **隔离策略**：使用内存数据库 (H2 / SQLite)、Testcontainers、Mock Server
- **覆盖要求**：
  - HTTP 状态码覆盖 (200 / 201 / 400 / 401 / 403 / 404 / 500)
  - 请求参数校验（必填字段、类型、长度、格式）
  - 认证 / 授权流程（有效 Token、过期 Token、无权限角色）
  - 数据库事务（创建、更新、删除、唯一约束冲突）
  - 分页 / 排序 / 过滤

### 端到端测试 (E2E Tests) — 10%

- **测试目标**：完整用户业务流程（登录 → 操作 → 验证结果）
- **工具链**：Cypress / Playwright / Selenium
- **覆盖场景**：
  - 核心业务主流程 (Happy Path)
  - 关键分支流程
  - 跨系统交互（前端 → 网关 → 后端 → 数据库）

---

## 测试生成流程 (Test Generation Process)

### 阶段 1：需求分析 → 测试场景识别

```
输入: PRD 文档、用户故事、API 契约 (OpenAPI)
输出: 测试场景清单 (scenarios)
```

1. 提取所有功能点，每个功能点生成至少 3 个测试场景（正向 / 边界 / 异常）
2. 识别功能间的依赖关系，规划集成测试用例
3. 标记优先级：
   - **P0**：核心业务流程，必须覆盖
   - **P1**：重要功能，高优先级覆盖
   - **P2**：边缘场景，建议覆盖
4. 估算覆盖率目标：P0 必须 100%，P1 目标 80%+，P2 目标 50%+

### 阶段 2：代码分析 → 未覆盖路径发现

```
输入: 后端代码、前端代码、Code Review 结果
输出: 补充测试场景 + 代码路径映射
```

1. 解析函数签名：识别参数类型、返回值、异常声明
2. 分析分支逻辑：if / else / switch / try-catch 的每个分支
3. 检查 Code Review 中标记的问题，生成回归测试
4. 识别外部依赖点：数据库操作、HTTP 调用、文件 IO → 标记为 Mock 点

### 阶段 3：测试代码生成

```
输入: 测试场景清单 + 代码路径映射
输出: 可执行测试脚本文件 (code_files)
```

生成规则：

1. **Setup / Teardown**：
   - 每个测试类/文件包含 `setup` 方法初始化测试数据
   - 每个测试类/文件包含 `teardown` 方法清理状态
   - 使用 fixture / `@BeforeEach` / `setUp` 等框架机制
2. **Mock 策略**：
   - 数据库 → 内存数据库或 Mock Repository
   - HTTP 调用 → Mock Server 或 `responses` / `nock` / `httptest`
   - 时间依赖 → 注入可控的 Clock / 时间 Mock
   - 随机数 → 固定种子或 Mock
3. **断言规范**：
   - 每个测试至少 1 个断言
   - 使用语义化断言（`assertEqual` / `shouldBe` / `expect(x).toEqual(y)`）
   - 错误消息包含上下文信息
4. **测试隔离**：
   - 测试之间无依赖，可独立运行
   - 测试执行顺序不影响结果
   - 不依赖外部环境（网络、文件路径、时区）

### 阶段 4：结构化输出

生成的测试脚本以 JSON `code_files` 格式输出，供 `code_writer` Skill 写入
工作区的 `tests/` 子目录。详见下方「输出格式」章节。

---

## 语言 / 框架模板 (Language/Framework Templates)

### Java — JUnit 5 + Mockito + Spring Boot Test

**依赖**：

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.mockito</groupId>
    <artifactId>mockito-core</artifactId>
    <scope>test</scope>
</dependency>
```

**模板结构**：

```java
package com.example.module;

import org.junit.jupiter.api.*;
import org.mockito.*;
import org.springframework.boot.test.context.*;
import org.springframework.test.web.servlet.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
class XxxControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private XxxService xxxService;

    @BeforeEach
    void setUp() {
        // 初始化测试数据
    }

    @Test
    @DisplayName("创建XXX - 正常流程 - 返回200")
    void createXxx_whenValidInput_returns200() throws Exception {
        // Given
        when(xxxService.create(any())).thenReturn(expectedResult);

        // When & Then
        mockMvc.perform(post("/api/xxx")
                .contentType("application/json")
                .content(requestBody))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value(200));
    }

    @Test
    @DisplayName("创建XXX - 缺少必填字段 - 返回400")
    void createXxx_whenMissingRequiredField_returns400() throws Exception {
        // ...
    }

    @AfterEach
    void tearDown() {
        // 清理
    }
}
```

**单元测试模板 (Service 层)**：

```java
@ExtendWith(MockitoExtension.class)
class XxxServiceTest {

    @Mock
    private XxxRepository xxxRepository;

    @InjectMocks
    private XxxServiceImpl xxxService;

    @Test
    @DisplayName("查询ByID - 记录存在 - 返回正确数据")
    void findById_whenExists_returnsData() {
        when(xxxRepository.findById(1L)).thenReturn(Optional.of(entity));

        XxxDTO result = xxxService.findById(1L);

        Assertions.assertNotNull(result);
        Assertions.assertEquals("expected", result.getName());
    }

    @Test
    @DisplayName("查询ByID - 记录不存在 - 抛出异常")
    void findById_whenNotExists_throwsException() {
        when(xxxRepository.findById(999L)).thenReturn(Optional.empty());

        Assertions.assertThrows(
            BusinessException.class,
            () -> xxxService.findById(999L)
        );
    }
}
```

### Go — testing + testify + httptest

**模板结构**：

```go
package handler

import (
    "bytes"
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "testing"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/mock"
    "github.com/stretchr/testify/suite"
)

// --- 单元测试 ---

func TestXxxService_Create(t *testing.T) {
    tests := []struct {
        name        string
        input       CreateXxxRequest
        setupMock   func(*MockXxxRepo)
        wantErr     bool
        errContains string
    }{
        {
            name:    "正常创建 - 返回成功",
            input:   CreateXxxRequest{Name: "test", Status: 1},
            setupMock: func(m *MockXxxRepo) {
                m.On("Create", mock.Anything).Return(int64(1), nil)
            },
            wantErr: false,
        },
        {
            name:        "名称为空 - 返回校验错误",
            input:       CreateXxxRequest{Name: "", Status: 1},
            wantErr:     true,
            errContains: "name is required",
        },
        {
            name:    "名称超长 - 返回校验错误",
            input:   CreateXxxRequest{Name: strings.Repeat("a", 256), Status: 1},
            wantErr: true,
        },
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            repo := new(MockXxxRepo)
            if tt.setupMock != nil {
                tt.setupMock(repo)
            }
            svc := NewXxxService(repo)

            result, err := svc.Create(tt.input)

            if tt.wantErr {
                assert.Error(t, err)
                if tt.errContains != "" {
                    assert.Contains(t, err.Error(), tt.errContains)
                }
            } else {
                assert.NoError(t, err)
                assert.NotNil(t, result)
            }
        })
    }
}

// --- API 集成测试 (httptest) ---

func TestXxxHandler_CreateAPI(t *testing.T) {
    router := setupTestRouter()

    body, _ := json.Marshal(map[string]interface{}{
        "name": "test-item",
    })

    req := httptest.NewRequest(http.MethodPost, "/api/xxx", bytes.NewReader(body))
    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("Authorization", "Bearer "+testToken)

    w := httptest.NewRecorder()
    router.ServeHTTP(w, req)

    assert.Equal(t, http.StatusOK, w.Code)

    var resp map[string]interface{}
    json.Unmarshal(w.Body.Bytes(), &resp)
    assert.Equal(t, float64(200), resp["code"])
}
```

### Python — pytest + pytest-asyncio + httpx

**依赖**：

```txt
pytest>=7.0
pytest-asyncio>=0.21
pytest-cov>=4.0
httpx>=0.24
pytest-mock>=3.10
```

**conftest.py 模板**：

```python
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import get_db, async_session_maker


@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def client():
    """异步测试客户端"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_client(client):
    """带认证的测试客户端"""
    response = await client.post("/api/auth/login", json={
        "username": "admin",
        "password": "admin123",
    })
    token = response.json()["data"]["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def mock_db(mocker):
    """Mock 数据库 Session"""
    session = mocker.MagicMock()
    return session
```

**单元测试模板**：

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.xxx_service import XxxService


class TestXxxService:
    """XxxService 单元测试"""

    @pytest.fixture
    def service(self, mock_db):
        return XxxService(mock_db)

    @pytest.mark.asyncio
    async def test_create_xxx_success(self, service, mock_db):
        """正常创建 - 返回成功"""
        # Arrange
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        ))
        mock_db.commit = AsyncMock()

        # Act
        result = await service.create(name="test-item", tenant_id=1)

        # Assert
        assert result is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_xxx_duplicate_name_raises(self, service, mock_db):
        """名称重复 - 抛出异常"""
        # Arrange
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=MagicMock(id=1))
        ))

        # Act & Assert
        with pytest.raises(ValueError, match="已存在"):
            await service.create(name="duplicate", tenant_id=1)

    @pytest.mark.asyncio
    async def test_create_xxx_empty_name_raises(self, service, mock_db):
        """名称为空 - 参数校验失败"""
        with pytest.raises(ValueError, match="名称不能为空"):
            await service.create(name="", tenant_id=1)

    @pytest.mark.asyncio
    async def test_create_xxx_long_name_raises(self, service, mock_db):
        """名称超长 - 参数校验失败"""
        with pytest.raises(ValueError, match="名称长度"):
            await service.create(name="a" * 256, tenant_id=1)
```

**API 集成测试模板**：

```python
import pytest
from httpx import AsyncClient


class TestXxxAPI:
    """Xxx API 集成测试"""

    @pytest.mark.asyncio
    async def test_create_xxx_200(self, auth_client: AsyncClient):
        """POST /api/xxx - 正常创建返回200"""
        response = await auth_client.post("/api/xxx", json={
            "name": "test-item",
            "status": 1,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["id"] is not None

    @pytest.mark.asyncio
    async def test_create_xxx_missing_field_400(self, auth_client: AsyncClient):
        """POST /api/xxx - 缺少必填字段返回400"""
        response = await auth_client.post("/api/xxx", json={})
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_xxx_unauthorized_401(self, client: AsyncClient):
        """POST /api/xxx - 无Token返回401"""
        response = await client.post("/api/xxx", json={"name": "test"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_xxx_pagination(self, auth_client: AsyncClient):
        """GET /api/xxx - 分页查询"""
        response = await auth_client.get("/api/xxx?page=1&pageSize=10")
        assert response.status_code == 200
        data = response.json()
        assert "list" in data["data"]
        assert "total" in data["data"]

    @pytest.mark.asyncio
    async def test_delete_xxx_not_found_404(self, auth_client: AsyncClient):
        """DELETE /api/xxx/99999 - 不存在返回404"""
        response = await auth_client.delete("/api/xxx/99999")
        assert response.status_code == 404
```

### JavaScript / TypeScript — Jest + React Testing Library + Cypress

**Jest 单元测试模板**：

```javascript
// tests/unit/xxxService.test.js
const { XxxService } = require('@/services/xxxService');
const { api } = require('@/services/api');

jest.mock('@/services/api');

describe('XxxService', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('getList', () => {
    test('正常获取列表 - 返回数据', async () => {
      api.get.mockResolvedValue({
        data: { code: 200, data: { list: [{ id: 1 }], total: 1 } },
      });

      const result = await XxxService.getList({ page: 1, pageSize: 10 });

      expect(api.get).toHaveBeenCalledWith('/api/xxx', {
        params: { page: 1, pageSize: 10 },
      });
      expect(result.list).toHaveLength(1);
    });

    test('网络异常 - 抛出错误', async () => {
      api.get.mockRejectedValue(new Error('Network Error'));

      await expect(XxxService.getList({})).rejects.toThrow('Network Error');
    });
  });

  describe('create', () => {
    test('名称为空 - 校验失败', () => {
      expect(() => XxxService.validate({ name: '' })).toThrow(
        '名称不能为空'
      );
    });
  });
});
```

**React 组件测试模板**：

```tsx
// tests/components/XxxList.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { XxxList } from '@/pages/xxx/XxxList';

jest.mock('@/services/xxxService');

describe('XxxList 组件', () => {
  test('渲染列表 - 显示数据', async () => {
    const mockList = [
      { id: 1, name: '项目A', status: 1 },
      { id: 2, name: '项目B', status: 0 },
    ];
    require('@/services/xxxService').XxxService.getList.mockResolvedValue({
      list: mockList,
      total: 2,
    });

    render(<XxxList />);

    await waitFor(() => {
      expect(screen.getByText('项目A')).toBeInTheDocument();
      expect(screen.getByText('项目B')).toBeInTheDocument();
    });
  });

  test('点击新增按钮 - 弹窗出现', async () => {
    render(<XxxList />);

    const addButton = screen.getByRole('button', { name: /新增/i });
    fireEvent.click(addButton);

    await waitFor(() => {
      expect(screen.getByText(/新增XXX/i)).toBeInTheDocument();
    });
  });
});
```

**Cypress E2E 测试模板**：

```javascript
// cypress/e2e/xxx_flow.cy.js
describe('XXX 管理流程', () => {
  beforeEach(() => {
    cy.login('admin', 'admin123');
    cy.visit('/xxx');
  });

  it('完整 CRUD 流程', () => {
    // 创建
    cy.get('[data-testid="btn-add"]').click();
    cy.get('[data-testid="input-name"]').type('测试项目');
    cy.get('[data-testid="btn-submit"]').click();
    cy.contains('操作成功').should('be.visible');
    cy.contains('测试项目').should('be.visible');

    // 编辑
    cy.contains('测试项目')
      .parents('tr')
      .find('[data-testid="btn-edit"]')
      .click();
    cy.get('[data-testid="input-name"]').clear().type('修改后名称');
    cy.get('[data-testid="btn-submit"]').click();
    cy.contains('修改后名称').should('be.visible');

    // 删除
    cy.contains('修改后名称')
      .parents('tr')
      .find('[data-testid="btn-delete"]')
      .click();
    cy.get('.ant-modal-confirm-btns .ant-btn-primary').click();
    cy.contains('修改后名称').should('not.exist');
  });

  it('搜索过滤', () => {
    cy.get('[data-testid="search-input"]').type('不存在的名称');
    cy.get('[data-testid="btn-search"]').click();
    cy.get('.ant-table-placeholder').should('be.visible');
  });
});
```

---

## 测试用例分类 (Test Case Categories)

### 1. 正常流程 (Happy Path)

| 场景 | 说明 | 优先级 |
|------|------|--------|
| 标准输入创建 | 使用合法参数创建资源，验证返回结构和状态码 | P0 |
| 标准查询 | 分页查询返回正确的列表和总数 | P0 |
| 标准更新 | 更新已有资源，验证更新后数据 | P0 |
| 标准删除 | 删除已有资源，验证删除后不可查询 | P0 |
| 关联操作 | 主从表关联创建，验证级联关系 | P1 |

### 2. 边界条件 (Boundary Conditions)

| 场景 | 说明 | 优先级 |
|------|------|--------|
| 空字符串 | 必填字段传空串，验证校验拦截 | P0 |
| 最大长度 | 字段传最大允许长度，验证不截断 | P1 |
| 超大长度 | 字段超长，验证校验报错 | P1 |
| 数值零值 | 数值字段传 0，验证业务逻辑正确处理 | P1 |
| 数值溢出 | 传 Integer.MAX_VALUE 等极端值 | P2 |
| 分页边界 | page=0 / page=超大值 / pageSize=0 | P1 |
| Unicode | 中英日韩特殊字符、Emoji | P2 |

### 3. 异常处理 (Error Handling)

| 场景 | 说明 | 优先级 |
|------|------|--------|
| 必填字段缺失 | 缺少必填字段，返回 400 + 明确错误信息 | P0 |
| 类型错误 | 字符串字段传数字，验证类型校验 | P1 |
| 唯一约束冲突 | 重复创建相同唯一键，返回 409 或业务错误 | P0 |
| 外键约束 | 关联资源不存在，验证业务校验 | P1 |
| 并发冲突 | 乐观锁版本冲突，验证并发处理 | P2 |
| 数据库连接失败 | 模拟 DB 异常，验证降级/重试/错误返回 | P2 |

### 4. 安全测试 (Security Tests)

| 场景 | 说明 | 优先级 |
|------|------|--------|
| SQL 注入 | 参数传入 `' OR 1=1 --`，验证参数化查询 | P0 |
| XSS | 字符串字段传入 `<script>alert(1)</script>`，验证转义 | P0 |
| 越权访问 | 用户 A 操作用户 B 的资源，验证租户隔离 | P0 |
| Token 过期 | 使用过期 Token 请求，返回 401 | P0 |
| 无效 Token | 使用篡改 Token 请求，返回 401 | P0 |
| 无权限操作 | 普通用户执行管理员操作，返回 403 | P0 |
| 敏感数据泄露 | 接口返回是否包含密码、密钥等敏感字段 | P1 |
| IDOR | 修改资源 ID 尝试越权，验证权限校验 | P1 |

### 5. 性能测试 (Performance Tests)

| 场景 | 说明 | 优先级 |
|------|------|--------|
| 大数据量分页 | 10 万条数据下分页查询响应时间 | P2 |
| 批量操作 | 批量创建 / 批量删除性能 | P2 |
| 并发读写 | 同一资源并发读写的正确性 | P2 |
| N+1 查询 | 列表查询是否存在 N+1 问题 | P2 |

---

## 输出格式 (Output Format)

测试生成的最终输出是一个 JSON 结构，包含**测试计划**和**代码文件**两部分：

```json
{
  "test_plan": {
    "total_cases": 24,
    "unit_tests": 16,
    "integration_tests": 6,
    "e2e_tests": 2,
    "coverage_target": "80%",
    "scenarios": [
      {
        "case_id": "TC-001",
        "title": "创建XXX - 正常流程 - 返回200",
        "type": "integration",
        "priority": "P0",
        "preconditions": "已登录管理员账号",
        "expected_result": "返回code=200，data包含id字段"
      },
      {
        "case_id": "TC-002",
        "title": "创建XXX - 名称为空 - 返回400",
        "type": "integration",
        "priority": "P0",
        "preconditions": "已登录管理员账号",
        "expected_result": "返回code=400，msg包含校验错误信息"
      }
    ],
    "risks": [
      "批量操作接口未做幂等性校验",
      "列表查询未加 tenant_id 过滤，存在越权风险"
    ]
  },
  "code_files": [
    {
      "path": "tests/test_xxx_service.py",
      "content": "完整的 pytest 测试代码...",
      "language": "python"
    },
    {
      "path": "tests/test_xxx_api.py",
      "content": "完整的 API 集成测试代码...",
      "language": "python"
    },
    {
      "path": "tests/conftest.py",
      "content": "共享 fixture 定义...",
      "language": "python"
    }
  ],
  "bug_details": "发现的潜在问题列表...",
  "tests_passed": true,
  "coverage_estimate": "82%"
}
```

### 文件命名规范

| 语言 | 单元测试 | 集成测试 | E2E 测试 |
|------|---------|---------|----------|
| Java | `XxxServiceTest.java` | `XxxControllerTest.java` | `XxxFlowIT.java` |
| Go | `xxx_service_test.go` | `xxx_handler_test.go` | `xxx_e2e_test.go` |
| Python | `test_xxx_service.py` | `test_xxx_api.py` | `test_xxx_flow.py` |
| TypeScript | `xxxService.test.ts` | `xxxApi.test.ts` | `xxxFlow.cy.ts` |

### 文件放置路径

```
tests/
├── conftest.py              # 共享 fixture
├── unit/                    # 单元测试
│   ├── test_xxx_service.py
│   └── test_xxx_util.py
├── integration/             # 集成测试
│   ├── test_xxx_api.py
│   └── test_xxx_db.py
└── e2e/                     # 端到端测试
    └── test_xxx_flow.py
```

> Pipeline Skill `code_writer` 会将 `testing` 阶段的 `code_files` 自动写入
> 工作区的 `tests/` 子目录。如果文件路径已经以 `tests/` 开头则保持原样，
> 否则自动添加 `tests/` 前缀。

---

## 完整示例 (Examples)

### 示例 1：用户管理模块 — Python pytest

**需求摘要**：管理员 CRUD 用户账号，支持分页查询、状态启用/禁用。

**后端代码关键结构**：

```python
# app/api/admin.py
@router.post("/api/admin/create")
async def create_admin(data: AdminCreateRequest, db: Session, tenant_id: int):
    ...

@router.get("/api/admin/list")
async def list_admins(page: int, pageSize: int, db: Session, tenant_id: int):
    ...

@router.put("/api/admin/{admin_id}/status")
async def update_status(admin_id: int, status: int, db: Session, tenant_id: int):
    ...
```

**生成的测试脚本**：

```python
# tests/integration/test_admin_api.py
import pytest
from httpx import AsyncClient


class TestAdminCreateAPI:
    """管理员创建接口测试"""

    @pytest.mark.asyncio
    async def test_create_admin_success(self, auth_client: AsyncClient):
        """TC-001: 正常创建管理员 - 返回200"""
        response = await auth_client.post("/api/admin/create", json={
            "username": "newadmin",
            "password": "Test@12345",
            "real_name": "测试管理员",
            "phone": "13800138000",
            "group_id": 2,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["id"] > 0
        assert data["data"]["username"] == "newadmin"

    @pytest.mark.asyncio
    async def test_create_admin_duplicate_username(self, auth_client: AsyncClient):
        """TC-002: 用户名重复 - 返回业务错误"""
        # 先创建一个
        await auth_client.post("/api/admin/create", json={
            "username": "dup_user",
            "password": "Test@12345",
            "real_name": "重复用户",
        })
        # 再次创建同名
        response = await auth_client.post("/api/admin/create", json={
            "username": "dup_user",
            "password": "Test@12345",
            "real_name": "另一个用户",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["code"] != 200  # 业务错误码

    @pytest.mark.asyncio
    async def test_create_admin_empty_username(self, auth_client: AsyncClient):
        """TC-003: 用户名为空 - 返回400"""
        response = await auth_client.post("/api/admin/create", json={
            "username": "",
            "password": "Test@12345",
        })
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_admin_sql_injection(self, auth_client: AsyncClient):
        """TC-004: SQL注入 - 参数化查询防御"""
        response = await auth_client.post("/api/admin/create", json={
            "username": "admin' OR '1'='1",
            "password": "Test@12345",
            "real_name": "注入测试",
        })
        # 不应该返回所有用户或导致异常
        assert response.status_code in (200, 400)

    @pytest.mark.asyncio
    async def test_create_admin_unauthorized(self, client: AsyncClient):
        """TC-005: 无Token创建 - 返回401"""
        response = await client.post("/api/admin/create", json={
            "username": "noauth",
            "password": "Test@12345",
        })
        assert response.status_code == 401


class TestAdminListAPI:
    """管理员列表接口测试"""

    @pytest.mark.asyncio
    async def test_list_admins_default_pagination(self, auth_client: AsyncClient):
        """TC-006: 默认分页查询 - 返回列表"""
        response = await auth_client.get("/api/admin/list?page=1&pageSize=10")
        assert response.status_code == 200
        data = response.json()
        assert "list" in data["data"]
        assert "total" in data["data"]
        assert isinstance(data["data"]["list"], list)

    @pytest.mark.asyncio
    async def test_list_admins_large_page(self, auth_client: AsyncClient):
        """TC-007: 超大页码 - 返回空列表"""
        response = await auth_client.get("/api/admin/list?page=99999&pageSize=10")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["list"] == []

    @pytest.mark.asyncio
    async def test_list_admins_tenant_isolation(self, auth_client: AsyncClient):
        """TC-008: 租户隔离 - 不返回其他租户数据"""
        response = await auth_client.get("/api/admin/list?page=1&pageSize=100")
        assert response.status_code == 200
        data = response.json()
        # 所有记录的 tenant_id 应与当前用户一致
        for item in data["data"]["list"]:
            assert item.get("tenant_id") is not None


class TestAdminStatusAPI:
    """管理员状态切换接口测试"""

    @pytest.mark.asyncio
    async def test_disable_admin_success(self, auth_client: AsyncClient):
        """TC-009: 禁用管理员 - 返回成功"""
        # 先创建一个管理员
        create_resp = await auth_client.post("/api/admin/create", json={
            "username": "to_disable",
            "password": "Test@12345",
        })
        admin_id = create_resp.json()["data"]["id"]

        response = await auth_client.put(
            f"/api/admin/{admin_id}/status",
            json={"status": 0},
        )
        assert response.status_code == 200
        assert response.json()["code"] == 200

    @pytest.mark.asyncio
    async def test_disable_nonexistent_admin(self, auth_client: AsyncClient):
        """TC-010: 禁用不存在的管理员 - 返回404"""
        response = await auth_client.put(
            "/api/admin/99999/status",
            json={"status": 0},
        )
        assert response.status_code == 404
```

**对应的 JSON 输出**：

```json
{
  "test_plan": {
    "total_cases": 10,
    "unit_tests": 0,
    "integration_tests": 10,
    "e2e_tests": 0,
    "coverage_target": "85%",
    "scenarios": [
      {"case_id": "TC-001", "title": "正常创建管理员", "type": "integration", "priority": "P0"},
      {"case_id": "TC-002", "title": "用户名重复", "type": "integration", "priority": "P0"},
      {"case_id": "TC-003", "title": "用户名为空", "type": "integration", "priority": "P0"},
      {"case_id": "TC-004", "title": "SQL注入防御", "type": "integration", "priority": "P0"},
      {"case_id": "TC-005", "title": "无Token创建", "type": "integration", "priority": "P0"},
      {"case_id": "TC-006", "title": "默认分页查询", "type": "integration", "priority": "P0"},
      {"case_id": "TC-007", "title": "超大页码", "type": "integration", "priority": "P1"},
      {"case_id": "TC-008", "title": "租户隔离", "type": "integration", "priority": "P0"},
      {"case_id": "TC-009", "title": "禁用管理员", "type": "integration", "priority": "P0"},
      {"case_id": "TC-010", "title": "禁用不存在管理员", "type": "integration", "priority": "P1"}
    ],
    "risks": [
      "创建接口未对密码复杂度做校验",
      "列表查询未验证 tenant_id 参数是否被篡改"
    ]
  },
  "code_files": [
    {
      "path": "tests/integration/test_admin_api.py",
      "content": "... (上方完整代码) ...",
      "language": "python"
    }
  ],
  "tests_passed": true,
  "coverage_estimate": "85%"
}
```

### 示例 2：订单管理模块 — Go testing

**需求摘要**：创建订单、查询订单详情、取消订单，支持多租户数据隔离。

**后端代码关键结构**：

```go
// internal/handler/order.go
func (h *OrderHandler) CreateOrder(c *gin.Context) { ... }
func (h *OrderHandler) GetOrder(c *gin.Context)    { ... }
func (h *OrderHandler) CancelOrder(c *gin.Context)  { ... }

// internal/service/order.go
func (s *OrderService) Create(ctx context.Context, req CreateOrderReq, tenantID int64) (*Order, error) { ... }
func (s *OrderService) GetByID(ctx context.Context, orderID, tenantID int64) (*Order, error) { ... }
func (s *OrderService) Cancel(ctx context.Context, orderID, tenantID int64) error { ... }
```

**生成的测试脚本**：

```go
// tests/order_service_test.go
package tests

import (
    "context"
    "errors"
    "testing"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/mock"
    "github.com/stretchr/testify/require"
)

// --- Mock ---

type MockOrderRepo struct {
    mock.Mock
}

func (m *MockOrderRepo) Create(ctx context.Context, order *Order) (int64, error) {
    args := m.Called(ctx, order)
    return args.Get(0).(int64), args.Error(1)
}

func (m *MockOrderRepo) GetByID(ctx context.Context, id, tenantID int64) (*Order, error) {
    args := m.Called(ctx, id, tenantID)
    if args.Get(0) == nil {
        return nil, args.Error(1)
    }
    return args.Get(0).(*Order), args.Error(1)
}

func (m *MockOrderRepo) UpdateStatus(ctx context.Context, id int64, status int) error {
    args := m.Called(ctx, id, status)
    return args.Error(0)
}

// --- 单元测试 ---

func TestOrderService_Create_Success(t *testing.T) {
    /* TC-001: 正常创建订单 */
    repo := new(MockOrderRepo)
    repo.On("Create", mock.Anything, mock.AnythingOfType("*Order")).Return(int64(1), nil)
    svc := NewOrderService(repo)

    req := CreateOrderReq{
        ProductID: "P001",
        Quantity:  2,
        Amount:    99.9,
    }

    order, err := svc.Create(context.Background(), req, 1)

    require.NoError(t, err)
    assert.Equal(t, int64(1), order.ID)
    assert.Equal(t, int64(1), order.TenantID)
    repo.AssertExpectations(t)
}

func TestOrderService_Create_ZeroQuantity_Error(t *testing.T) {
    /* TC-002: 数量为0 - 返回错误 */
    repo := new(MockOrderRepo)
    svc := NewOrderService(repo)

    req := CreateOrderReq{ProductID: "P001", Quantity: 0, Amount: 99.9}

    _, err := svc.Create(context.Background(), req, 1)

    assert.Error(t, err)
    assert.Contains(t, err.Error(), "数量")
}

func TestOrderService_Create_NegativeAmount_Error(t *testing.T) {
    /* TC-003: 金额为负数 - 返回错误 */
    repo := new(MockOrderRepo)
    svc := NewOrderService(repo)

    req := CreateOrderReq{ProductID: "P001", Quantity: 1, Amount: -10.0}

    _, err := svc.Create(context.Background(), req, 1)

    assert.Error(t, err)
}

func TestOrderService_Create_RepoError(t *testing.T) {
    /* TC-004: 数据库异常 - 返回错误 */
    repo := new(MockOrderRepo)
    repo.On("Create", mock.Anything, mock.AnythingOfType("*Order")).
        Return(int64(0), errors.New("connection refused"))
    svc := NewOrderService(repo)

    req := CreateOrderReq{ProductID: "P001", Quantity: 1, Amount: 10.0}

    _, err := svc.Create(context.Background(), req, 1)

    assert.Error(t, err)
    assert.Contains(t, err.Error(), "connection refused")
}

func TestOrderService_GetByID_TenantIsolation(t *testing.T) {
    /* TC-005: 租户隔离 - 查询其他租户订单返回错误 */
    repo := new(MockOrderRepo)
    // 租户2 查询租户1 的订单 → repo 返回 nil
    repo.On("GetByID", mock.Anything, int64(100), int64(2)).
        Return(nil, ErrOrderNotFound)
    svc := NewOrderService(repo)

    _, err := svc.GetByID(context.Background(), 100, 2)

    assert.ErrorIs(t, err, ErrOrderNotFound)
}

func TestOrderService_Cancel_AlreadyCancelled(t *testing.T) {
    /* TC-006: 重复取消 - 返回错误 */
    repo := new(MockOrderRepo)
    repo.On("GetByID", mock.Anything, int64(1), int64(1)).Return(&Order{
        ID:     1,
        Status: StatusCancelled,
    }, nil)
    svc := NewOrderService(repo)

    err := svc.Cancel(context.Background(), 1, 1)

    assert.Error(t, err)
    assert.Contains(t, err.Error(), "已取消")
}

func TestOrderService_Cancel_Success(t *testing.T) {
    /* TC-007: 正常取消订单 */
    repo := new(MockOrderRepo)
    repo.On("GetByID", mock.Anything, int64(1), int64(1)).Return(&Order{
        ID:     1,
        Status: StatusPending,
    }, nil)
    repo.On("UpdateStatus", mock.Anything, int64(1), StatusCancelled).Return(nil)
    svc := NewOrderService(repo)

    err := svc.Cancel(context.Background(), 1, 1)

    assert.NoError(t, err)
    repo.AssertExpectations(t)
}

// --- API 集成测试 ---

func TestOrderAPI_CreateOrder_200(t *testing.T) {
    /* TC-008: API 创建订单 - 返回200 */
    router := setupTestRouter()

    body := `{"product_id":"P001","quantity":2,"amount":99.9}`
    req := httptest.NewRequest(http.MethodPost, "/api/orders", strings.NewReader(body))
    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("X-Tenant-ID", "1")
    req.Header.Set("Authorization", "Bearer "+testToken)

    w := httptest.NewRecorder()
    router.ServeHTTP(w, req)

    assert.Equal(t, http.StatusOK, w.Code)

    var resp map[string]interface{}
    json.Unmarshal(w.Body.Bytes(), &resp)
    assert.Equal(t, float64(200), resp["code"])
}

func TestOrderAPI_CreateOrder_NoAuth_401(t *testing.T) {
    /* TC-009: 无Token创建订单 - 返回401 */
    router := setupTestRouter()

    req := httptest.NewRequest(http.MethodPost, "/api/orders", strings.NewReader(`{}`))
    req.Header.Set("Content-Type", "application/json")

    w := httptest.NewRecorder()
    router.ServeHTTP(w, req)

    assert.Equal(t, http.StatusUnauthorized, w.Code)
}

func TestOrderAPI_GetOrder_NotFound_404(t *testing.T) {
    /* TC-010: 查询不存在订单 - 返回404 */
    router := setupTestRouter()

    req := httptest.NewRequest(http.MethodGet, "/api/orders/99999", nil)
    req.Header.Set("Authorization", "Bearer "+testToken)

    w := httptest.NewRecorder()
    router.ServeHTTP(w, req)

    assert.Equal(t, http.StatusNotFound, w.Code)
}
```

---

## 最佳实践 (Best Practices)

### 测试命名 (Naming Convention)

**原则**：测试名称应自文档化，读起来像自然语言描述。

| 格式 | 示例 |
|------|------|
| Python | `test_create_xxx_duplicate_name_raises_value_error` |
| Java | `createXxx_whenDuplicateName_throwsBusinessException` |
| Go | `TestOrderService_Create_DuplicateProductID_Error` |
| JS/TS | `create order with duplicate name should throw error` |

推荐使用三段式命名：`方法名_条件描述_预期结果`

### 测试隔离 (Test Isolation)

1. **不依赖执行顺序**：任何单个测试可独立运行
2. **不共享可变状态**：每个测试自行准备数据 (Given-When-Then)
3. **不依赖外部服务**：网络、时间、随机数全部 Mock
4. **测试数据自包含**：在测试内部创建，不在 fixture 中硬编码全局数据
5. **清理副作用**：使用事务回滚或 teardown 清理写入的数据

### 确定性 (Determinism)

1. **时间可控**：注入 Clock / 使用 `freezegun` / Go 的 `faketime`
2. **随机数可控**：固定随机种子或 Mock 随机数生成器
3. **ID 可控**：使用确定的测试 ID，不依赖自增 ID
4. **并发可控**：集成测试中避免依赖并发时序

### 测试数据管理 (Test Data)

1. **Builder 模式**：创建测试数据的工厂方法
   ```python
   def build_admin(**overrides):
       defaults = {"username": "test_admin", "password": "Test@123"}
       defaults.update(overrides)
       return defaults
   ```
2. **最小化数据**：每个测试只创建必要的数据，避免大量无用 fixture
3. **语义化数据**：测试数据应表达业务含义而非随机字符
   - 好的命名：`active_admin`、`expired_token`、`order_with_3_items`
   - 避免的命名：`test1`、`aaa`、`123`

### 断言规范 (Assertion Guidelines)

1. **断言具体的值**而非模糊的布尔判断
   ```python
   # 不好
   assert result
   # 好
   assert result.code == 200
   assert result.data.name == "expected_name"
   ```
2. **错误消息包含上下文**
   ```python
   assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
   ```
3. **每条测试 1-3 个断言**，避免「全能测试」
4. **先断言状态**，再断言数据
   ```python
   assert response.status_code == 200
   data = response.json()
   assert data["code"] == 200
   assert data["data"]["id"] > 0
   ```

### 多租户测试 (Multi-Tenancy)

本平台所有业务表包含 `tenant_id`，测试必须覆盖租户隔离：

1. **正常操作**：传入正确 `tenant_id`，验证只返回本租户数据
2. **越权防御**：尝试操作其他租户数据，验证返回 403 或空结果
3. **数据不泄露**：列表/搜索接口不返回其他租户的数据
4. **关联数据隔离**：创建资源时 `tenant_id` 与当前用户一致

### Mock 使用原则 (Mocking Principles)

1. **只 Mock 外部依赖**：数据库、HTTP 调用、文件系统、消息队列
2. **不 Mock 被测对象自身的方法**：这会导致测试失去意义
3. **Mock 返回值贴近真实结构**：不要返回 `{"a": 1}` 这种无意义数据
4. **验证 Mock 调用**：`repo.AssertCalled(t, "Create", ...)` 确保方法确实被调用
5. **优先使用接口 Mock**：Go 中 Mock 接口而非结构体；Java 中使用 `@MockBean`

### 持续改进 (Continuous Improvement)

1. **失败测试优先修复**：测试失败时立即修复，不要标记 `@Skip`
2. **定期审查覆盖率**：目标 P0 场景 100%，整体 80%+
3. **回归测试**：Bug 修复后必须补充回归测试，防止同类问题复发
4. **删除过时测试**：功能废弃时同步删除对应测试，避免维护负担
5. **测试即文档**：测试用例是新成员理解系统行为的最佳文档

---

## 输入 (Input)

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `requirement` | string | 是 | 需求描述或 PRD 文档 |
| `code` | string | 否 | 待测源代码内容 |
| `language` | string | 否 | 目标语言 (java/go/python/javascript/typescript) |
| `framework` | string | 否 | 目标测试框架 (junit5/pytest/jest/testing) |
| `test_types` | array | 否 | 需要生成的测试类型 [`unit`, `integration`, `e2e`]，默认全部 |
| `session_id` | string | 否 | 会话 ID，用于上下文关联 |
| `tenant_id` | integer | 否 | 租户 ID，用于多租户测试数据隔离 |

## 输出 (Output)

| 字段 | 类型 | 说明 |
|------|------|------|
| `test_plan` | object | 测试计划，包含用例清单和覆盖率目标 |
| `code_files` | array | 可执行的测试脚本文件列表 |
| `bug_details` | string | 分析过程中发现的潜在 Bug |
| `tests_passed` | boolean | 静态分析是否通过（无语法错误、无逻辑矛盾） |
| `coverage_estimate` | string | 预估覆盖率 |

---

## 与 Pipeline Skill 的协作

本 Skill 在 DevPipeline 的 `testing` 阶段被 QA Agent 调用，与其他 Skill 协作：

```
代码审查 (code_review)
    ↓ 审查通过
测试生成 (test_generation / 本 Skill)  ← LLM 生成测试脚本
    ↓ code_files
文件写入 (code_writer)                 ← 写入 tests/ 目录
    ↓ 文件就绪
测试执行 (test_runner)                 ← 实际运行测试，返回通过/失败
    ↓ 结果反馈
测试失败 → 回退修复                    ← 自动回退到开发阶段
测试通过 → 代码提交 (git_commit)       ← 继续流水线
```

关键交互点：

1. **code_writer**：将 `code_files` 写入工作区的 `tests/` 子目录
2. **test_runner**：执行已写入的测试脚本，返回实际执行结果
3. **Dockerfile 生成**：为测试环境自动生成包含测试依赖的 Dockerfile
4. **失败回退**：如果 `test_runner` 报告失败，PipelineManager 自动回退到
   开发阶段并附带 Bug 详情作为修复反馈（最多重试 3 次）
