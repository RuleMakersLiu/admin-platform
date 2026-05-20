---
id: code_review
name: code-review
description: "Review code quality, security, and best practices with actionable improvement suggestions. 审查代码质量、安全性和最佳实践，提供改进建议和修复方案。支持多语言代码审查。"
version: 1.1.0
category: testing
agent_type: QA
metadata:
  hermes:
    tags: [code-review, quality, security, best-practices, owasp]
    related_skills: [backend-development, frontend-development, test-generation]
---

# 代码审查 (Code Review)

## 概述 (Overview)

本 Skill 为 QA Agent 提供自动化代码审查能力，覆盖多语言、多框架项目的质量保障。审查范围包括代码正确性、安全性、性能、可维护性、错误处理和并发安全六大维度。审查结果以结构化 JSON 格式输出，支持与 CI/CD 流水线集成，也可作为 PR Review 的辅助工具。

本审查基于 OWASP Top 10、CWE/SANS Top 25 以及各语言社区的最佳实践，确保代码在生产环境中的安全性和可靠性。

### 适用场景

- 提交代码前需要进行质量审查
- PR/MR 合并前的自动化审查环节
- 需要检查代码中的安全隐患（SQL 注入、XSS、CSRF 等）
- 需要验证代码是否符合项目编码规范
- 上线前的安全审计和合规检查
- 重构后的回归质量验证
- 第三方依赖引入后的风险评估

### 审查流程

1. 接收待审查的代码和对应的需求描述
2. 识别代码语言和技术栈，加载对应的审查规则集
3. 按六大维度逐一扫描代码
4. 按语言特定规则进行深度检查
5. 执行安全审计 Checklist
6. 汇总问题、计算评分、生成审查报告

---

## 输入 (Input)

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | 是 | 待审查的代码内容，支持多文件以 `--- FILE: path ---` 分隔 |
| `requirement` | string | 否 | 对应的需求描述，用于上下文参考 |
| `language` | string | 否 | 代码语言（自动检测，可手动指定） |
| `review_focus` | string | 否 | 审查重点：`all`、`security`、`performance`、`quality`，默认 `all` |
| `severity_threshold` | string | 否 | 最低报告级别：`info`、`minor`、`major`、`critical`，默认 `minor` |
| `session_id` | string | 否 | 会话 ID |

---

## 审查维度 (Review Dimensions)

### 1. 正确性 (Correctness)

检查代码逻辑是否正确实现需求，重点关注以下问题：

- **逻辑错误**：条件判断是否与需求语义一致，分支覆盖是否完整
- **Off-by-one 错误**：循环边界、数组索引、分页计算中的常见错误
- **Null/Undefined 处理**：是否对所有可能为空的值进行了防御性检查
- **类型安全**：隐式类型转换是否会导致意外行为（如 `==` vs `===`）
- **返回值检查**：函数调用返回值是否被正确处理
- **边界条件**：空集合、零值、最大值、负数等边界情况是否覆盖
- **数据一致性**：读写操作是否保持数据一致性
- **资源释放**：文件句柄、数据库连接、网络连接是否确保关闭

**常见错误模式：**

```
# 错误：缺少空值检查
user = get_user(user_id)
return user.name  # 如果 user 为 None 则崩溃

# 正确：防御性编程
user = get_user(user_id)
if user is None:
    raise UserNotFoundError(f"User {user_id} not found")
return user.name
```

### 2. 安全性 (Security)

基于 OWASP Top 10 的全面安全审查，详见下方 [安全审计 Checklist](#安全审计-checklist-security-audit-checklist) 章节。

### 3. 性能 (Performance)

识别影响系统性能的代码问题：

- **N+1 查询**：循环内执行数据库查询，应使用 JOIN 或批量查询
- **内存泄漏**：未清理的缓存、未移除的事件监听器、闭包中的意外引用
- **不必要的循环**：可用集合操作（map/filter/reduce）替代的 for 循环
- **缺失索引**：高频查询字段缺少数据库索引
- **大量数据加载**：未分页的全量数据加载
- **重复计算**：循环内重复执行相同计算，应提取到循环外
- **同步阻塞**：高并发场景下使用同步 I/O 替代异步 I/O
- **序列化开销**：不必要的大对象序列化/反序列化

**N+1 查询示例：**

```python
# 错误：N+1 查询
for order in orders:
    user = db.query(User).filter(User.id == order.user_id).first()
    print(user.name)

# 正确：批量查询
user_ids = [order.user_id for order in orders]
users = db.query(User).filter(User.id.in_(user_ids)).all()
user_map = {u.id: u for u in users}
for order in orders:
    print(user_map[order.user_id].name)
```

### 4. 可维护性 (Maintainability)

- **命名规范**：变量、函数、类命名是否符合语言惯例（snake_case / camelCase / PascalCase）
- **函数长度**：单函数不超过 50 行，超过应拆分为子函数
- **类职责**：遵循单一职责原则 (SRP)，避免 God Class
- **DRY 原则**：是否存在重复代码，应提取为公共函数或工具类
- **魔法数字**：硬编码的数字和字符串应提取为常量
- **注释质量**：注释是否描述了"为什么"而非"做什么"
- **代码复杂度**：圈复杂度不超过 10，嵌套不超过 4 层
- **模块耦合**：模块间依赖是否合理，是否可以解耦

**复杂度评估标准：**

| 圈复杂度 | 评级 | 建议 |
|----------|------|------|
| 1-5 | 良好 | 代码清晰易读 |
| 6-10 | 可接受 | 考虑简化部分逻辑 |
| 11-15 | 较差 | 建议重构拆分 |
| 16+ | 危险 | 必须重构 |

### 5. 错误处理 (Error Handling)

- **异常捕获粒度**：避免空 `except` / `catch (Exception)`，应捕获具体异常类型
- **错误信息**：错误消息是否包含足够的上下文信息用于定位问题
- **优雅降级**：核心功能异常时是否有 fallback 方案
- **事务回滚**：数据库操作失败时是否正确回滚事务
- **日志记录**：异常是否被正确记录（包含堆栈信息）
- **用户反馈**：是否向前端返回友好的错误信息（不暴露内部实现细节）
- **重试机制**：网络请求等可恢复错误是否有重试策略
- **超时处理**：外部调用是否设置合理的超时时间

**异常处理示例：**

```python
# 错误：空 except 吞掉异常
try:
    result = api.call()
except:
    pass  # 异常被静默忽略

# 正确：精确捕获 + 日志 + 降级
try:
    result = api.call(timeout=5)
except ConnectionError as e:
    logger.error(f"API call failed: {e}", exc_info=True)
    result = get_cached_result()  # 降级方案
except TimeoutError:
    logger.warning("API call timed out")
    result = get_default_result()
```

### 6. 并发安全 (Concurrency)

- **竞态条件 (Race Condition)**：共享变量的并发读写是否有同步机制
- **死锁 (Deadlock)**：多锁场景下是否保证加锁顺序一致
- **线程安全**：全局变量、类成员变量在多线程环境下的安全性
- **Goroutine 泄漏**：Go 语言中未正确退出的 Goroutine
- **数据库锁**：悲观锁/乐观锁使用是否正确
- **分布式锁**：分布式环境下的锁竞争处理
- **幂等性**：接口是否支持重复调用而不产生副作用

---

## 语言特定检查 (Language-Specific Checks)

### Java / Spring Boot

| 检查项 | 说明 | 严重级别 |
|--------|------|----------|
| `@Transactional` 作用域 | 避免在 Controller 层使用事务；事务方法内避免调用 RPC | major |
| DTO 使用 | Controller 层应使用 DTO 而非直接暴露 Entity | minor |
| Lombok 陷阱 | `@Data` 在 Entity 上会生成 equals/hashCode 导致 JPA 问题 | major |
| 线程池配置 | 禁止使用 `Executors.newFixedThreadPool()`，应自定义 ThreadPoolExecutor | critical |
| Optional 使用 | 避免 `Optional.get()` 不检查，应使用 `orElse` / `orElseThrow` | major |
| Stream 操作 | 避免在 Stream 中执行有副作用的操作 | minor |
| JSON 序列化 | 避免循环引用导致无限递归 | major |
| 敏感字段 | 密码、密钥等字段必须标注 `@JsonIgnore` 或使用 DTO 过滤 | critical |
| 日志脱敏 | 日志中禁止输出用户密码、身份证号、手机号等敏感信息 | critical |
| 异常转换 | 捕获 Checked Exception 后应转换为业务异常并保留 cause | major |

**Java 常见问题示例：**

```java
// 错误：@Data 在 JPA Entity 上
@Data
@Entity
public class User {
    @Id
    private Long id;
    private String name;
    @OneToMany(mappedBy = "user")
    private List<Order> orders;
}
// 问题：hashCode/equals 会包含 orders 集合，可能导致 StackOverflow

// 正确：使用 @Getter @Setter + 手动实现 equals/hashCode
@Getter
@Setter
@Entity
public class User {
    @Id
    private Long id;
    private String name;

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof User)) return false;
        return id != null && id.equals(((User) o).getId());
    }

    @Override
    public int hashCode() {
        return getClass().hashCode();
    }
}
```

### Go / Gin

| 检查项 | 说明 | 严重级别 |
|--------|------|----------|
| Goroutine 泄漏 | 启动的 Goroutine 必须有退出机制（context cancellation / done channel） | critical |
| Context 传递 | 所有函数链路必须传递 `context.Context` | major |
| Error Wrapping | 使用 `fmt.Errorf("xxx: %w", err)` 包装错误，保留错误链 | minor |
| Channel 方向 | 声明 channel 参数时指定方向（`chan<-` / `<-chan`） | minor |
| Defer 资源关闭 | 文件、数据库连接等资源必须用 `defer` 确保关闭 | critical |
| Mutex 复制 | `sync.Mutex` / `sync.WaitGroup` 禁止值复制 | critical |
| Map 并发 | `map` 不是并发安全的，写操作需要加锁或使用 `sync.Map` | critical |
| Slice 内存泄漏 | 大 Slice 切片后如只引用小部分，应 copy 到新 Slice | major |
| Gin 中间件顺序 | 认证中间件必须在授权中间件之前 | critical |
| HTTP 超时 | HTTP Client 必须设置 Timeout | major |

**Go 常见问题示例：**

```go
// 错误：缺少 context 传递和退出机制
func processData(ch <-chan Data) {
    for data := range ch {
        go func(d Data) {
            result := heavyProcess(d)  // 如果 heavyProcess 永远不返回，Goroutine 泄漏
            saveResult(result)
        }(data)
    }
}

// 正确：使用 context 控制生命周期
func processData(ctx context.Context, ch <-chan Data) {
    for data := range ch {
        select {
        case <-ctx.Done():
            log.Println("process canceled:", ctx.Err())
            return
        default:
            go func(d Data) {
                defer recoverPanic()
                result, err := heavyProcess(ctx, d)
                if err != nil {
                    log.Printf("process failed: %v", err)
                    return
                }
                saveResult(result)
            }(data)
        }
    }
}
```

### Python / FastAPI

| 检查项 | 说明 | 严重级别 |
|--------|------|----------|
| Type Hints | 公共函数必须标注参数和返回值类型 | minor |
| async/await 正确性 | `async def` 函数内禁止调用同步阻塞 I/O | major |
| SQLAlchemy Session | Session 生命周期必须通过 `yield` 依赖注入管理 | critical |
| Pydantic 模型 | API 输入输出必须使用 Pydantic Model 而非原始 dict | major |
| 路径遍历 | 文件操作必须校验路径，禁止直接拼接用户输入 | critical |
| 命令注入 | 禁止使用 `os.system()` / `subprocess.shell=True` | critical |
| PICKLE 反序列化 | 禁止对不可信数据使用 `pickle.loads()` | critical |
| 全局状态 | FastAPI 应用中避免使用全局可变状态 | major |
| 异常映射 | 业务异常应映射为 HTTP 状态码，而非全部返回 500 | major |
| 依赖注入 | 数据库连接等资源通过 FastAPI Depends 管理 | major |

**Python 常见问题示例：**

```python
# 错误：在 async 函数中执行同步阻塞操作
async def get_users():
    users = db.query(User).all()  # 同步数据库调用阻塞事件循环
    return users

# 正确：使用 async session 或 run_in_executor
async def get_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    return result.scalars().all()
```

```python
# 错误：Session 生命周期管理不当
@app.get("/users/{user_id}")
def get_user(user_id: int):
    session = SessionLocal()
    user = session.query(User).get(user_id)
    # 如果这里抛异常，session 永远不会关闭
    session.close()
    return user

# 正确：使用 yield 依赖注入
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    return db.query(User).get(user_id)
```

### Vue / React

| 检查项 | 说明 | 严重级别 |
|--------|------|----------|
| Key Prop | 列表渲染必须使用稳定唯一的 `key`，禁止使用数组索引 | major |
| useEffect 依赖 | `useEffect` 的依赖数组必须完整，避免 stale closure | major |
| 内存泄漏 | 组件卸载时必须清理定时器、事件监听、Subscription | critical |
| 不必要的重渲染 | 使用 `useMemo` / `useCallback` / `React.memo` 优化 | minor |
| dangerouslySetInnerHTML | 必须对内容进行 XSS 消毒后再渲染 | critical |
| State 直接修改 | 禁止直接修改 state（React），必须使用 setState / reducer | major |
| Prop Drilling | 超过 3 层的 Props 传递应使用 Context / 状态管理 | minor |
| 条件渲染中的 Hook | 禁止在条件语句中使用 Hook（违反 Hook 规则） | critical |
| 受控/非受控组件 | 表单组件的受控状态应保持一致，避免混合使用 | major |
| 事件处理函数 | 事件处理函数应避免在渲染时创建新引用 | minor |

**React 常见问题示例：**

```tsx
// 错误：useEffect 依赖不完整 + 内存泄漏
function UserList({ groupId }: { groupId: string }) {
    const [users, setUsers] = useState([]);

    useEffect(() => {
        fetch(`/api/groups/${groupId}/users`)
            .then(res => res.json())
            .then(data => setUsers(data));
        // 缺少 AbortController 和 cleanup
    }, []); // 缺少 groupId 依赖

    return <ul>{users.map(u => <li>{u.name}</li>)}</ul>; // 缺少 key
}

// 正确：完整依赖 + 清理 + key
function UserList({ groupId }: { groupId: string }) {
    const [users, setUsers] = useState<User[]>([]);

    useEffect(() => {
        const controller = new AbortController();
        fetch(`/api/groups/${groupId}/users`, { signal: controller.signal })
            .then(res => res.json())
            .then(data => setUsers(data))
            .catch(err => {
                if (err.name !== 'AbortError') console.error(err);
            });
        return () => controller.abort();
    }, [groupId]);

    return <ul>{users.map(u => <li key={u.id}>{u.name}</li>)}</ul>;
}
```

---

## 安全审计 Checklist (Security Audit Checklist)

以下 Checklist 基于 OWASP Top 10 (2021) 编制，每项为必查项：

### A01 - 权限控制失效 (Broken Access Control)

- [ ] API 端点是否要求认证（JWT / Session 验证）
- [ ] 是否实现了 RBAC/ABAC 权限校验（非仅前端隐藏）
- [ ] 水平越权：用户能否访问其他用户的数据（如修改 URL 中的 user_id）
- [ ] 垂直越权：普通用户能否访问管理员接口
- [ ] CORS 配置是否禁止了 `Access-Control-Allow-Origin: *`
- [ ] 目录遍历攻击是否被防护

### A02 - 加密机制失败 (Cryptographic Failures)

- [ ] 密码是否使用 bcrypt / scrypt / argon2 哈希存储（禁止 MD5/SHA1）
- [ ] 敏感数据传输是否使用 HTTPS/TLS
- [ ] JWT Secret 是否足够复杂（至少 256 位），是否定期轮换
- [ ] 敏感配置（数据库密码、API Key）是否从环境变量读取，而非硬编码
- [ ] 日志中是否记录了敏感信息（密码、Token、身份证号）
- [ ] 数据库中敏感字段是否加密存储

### A03 - 注入攻击 (Injection)

- [ ] SQL 查询是否全部使用参数化查询（禁止字符串拼接 SQL）
- [ ] 是否存在 OS Command Injection 风险（`os.system` / `exec` / `eval`）
- [ ] 模板引擎是否存在 SSTI（Server-Side Template Injection）风险
- [ ] LDAP / XML / XPath 查询是否参数化
- [ ] 用户输入是否经过校验和转义

### A04 - 不安全设计 (Insecure Design)

- [ ] 是否实现了限流（Rate Limiting）防止暴力破解
- [ ] 文件上传是否校验文件类型、大小、内容（非仅后缀名）
- [ ] 是否存在业务逻辑漏洞（如支付金额篡改、条件竞争）
- [ ] 安全关键操作是否需要二次验证（如修改密码需验证旧密码）

### A05 - 安全配置错误 (Security Misconfiguration)

- [ ] 生产环境是否关闭了 DEBUG 模式和详细错误信息
- [ ] 默认密码和默认账户是否已修改
- [ ] HTTP 响应头是否配置了安全相关 Header（X-Content-Type-Options, X-Frame-Options, CSP）
- [ ] 未使用的功能和接口是否已禁用
- [ ] 云存储 Bucket / 数据库是否禁止了公开访问

### A06 - 易受攻击和过时的组件 (Vulnerable and Outdated Components)

- [ ] 依赖版本是否存在已知 CVE 漏洞
- [ ] 是否使用了不再维护的库
- [ ] 是否锁定了依赖版本（package-lock.json / go.sum / requirements.txt）

### A07 - 身份识别和身份验证失败 (Identification and Authentication Failures)

- [ ] 是否实现了密码复杂度策略
- [ ] 是否有登录失败锁定机制（防暴力破解）
- [ ] Session 管理是否安全（HttpOnly、Secure、SameSite Cookie）
- [ ] Token 是否有过期时间和刷新机制
- [ ] 注销是否正确使 Token/Session 失效

### A08 - 软件和数据完整性失败 (Software and Data Integrity Failures)

- [ ] CI/CD 管道是否有未授权的写入权限
- [ ] 自动更新是否验证了签名
- [ ] 反序列化数据是否来自可信来源

### A09 - 安全日志和监控失败 (Security Logging and Monitoring Failures)

- [ ] 登录失败、权限拒绝等安全事件是否被记录
- [ ] 日志是否包含足够的上下文（用户 ID、IP、时间、操作）
- [ ] 是否配置了异常告警机制

### A10 - 服务端请求伪造 (SSRF)

- [ ] 用户提供的 URL 是否在校验后才进行服务端请求
- [ ] 是否限制了请求目标（禁止内网 IP、localhost）
- [ ] DNS Rebinding 攻击是否被防护

---

## 输出格式 (Output Format)

审查结果以结构化 JSON 格式输出：

```json
{
  "review_result": {
    "verdict": "pass|fail|conditional_pass",
    "score": 85,
    "files_reviewed": ["src/api/user.py", "src/models/user.py"],
    "language": "python",
    "framework": "fastapi",
    "issues": [
      {
        "id": "ISSUE-001",
        "severity": "critical",
        "category": "security",
        "file": "src/api/user.py",
        "line": 42,
        "column": 15,
        "rule": "SQL_INJECTION",
        "message": "SQL 查询使用字符串拼接，存在 SQL 注入风险",
        "code_snippet": "db.execute(f\"SELECT * FROM users WHERE id = {user_id}\")",
        "suggestion": "使用参数化查询: db.execute(\"SELECT * FROM users WHERE id = :id\", {\"id\": user_id})",
        "cwe": "CWE-89",
        "owasp": "A03:2021-Injection"
      },
      {
        "id": "ISSUE-002",
        "severity": "major",
        "category": "error_handling",
        "file": "src/api/user.py",
        "line": 55,
        "rule": "BROAD_EXCEPTION",
        "message": "使用了空 except 捕获所有异常，异常被静默忽略",
        "code_snippet": "try:\n    user = get_user(id)\nexcept:\n    pass",
        "suggestion": "捕获具体异常类型并记录日志: except NotFoundError as e: logger.warning(...)"
      }
    ],
    "summary": "代码整体结构清晰，但存在 1 个 SQL 注入高危问题和 1 个异常处理问题。建议修复安全问题后重新审查。",
    "strengths": [
      "API 接口遵循 RESTful 规范",
      "使用 Pydantic Model 进行数据校验",
      "函数命名清晰，注释完整"
    ],
    "recommendations": [
      "将 SQL 查询替换为 SQLAlchemy ORM 操作或参数化查询",
      "补充异常处理逻辑，避免空 except",
      "为高频查询接口添加 Redis 缓存",
      "添加 API 限流中间件防止滥用"
    ],
    "statistics": {
      "total_issues": 2,
      "critical": 1,
      "major": 1,
      "minor": 0,
      "info": 0,
      "lines_reviewed": 128,
      "files_reviewed": 2
    },
    "security_audit": {
      "owasp_top_10_passed": ["A01", "A04", "A05", "A06", "A09", "A10"],
      "owasp_top_10_failed": ["A03"],
      "owasp_top_10_not_applicable": ["A02", "A07", "A08"]
    }
  }
}
```

### 评分规则

| 评分范围 | 等级 | 判定 |
|----------|------|------|
| 90-100 | A | pass - 代码质量优秀，可直接合并 |
| 75-89 | B | conditional_pass - 代码良好，有少量需改进的点 |
| 60-74 | C | conditional_pass - 代码合格，但有较明显的问题需修复 |
| 40-59 | D | fail - 代码质量较差，需较多修改 |
| 0-39 | F | fail - 代码存在严重问题，必须重写 |

**扣分规则：**

- critical 问题：每个 -20 分
- major 问题：每个 -10 分
- minor 问题：每个 -3 分
- info 问题：每个 -0 分（仅提示）

### Verdict 判定逻辑

- `fail`：存在任何 critical 级别问题，或评分低于 60
- `conditional_pass`：存在 major 级别问题但无 critical，且评分 >= 60
- `pass`：无 critical 和 major 问题，且评分 >= 75

---

## 审查示例 (Review Examples)

### 示例 1：Python API 安全审查

**输入代码：**

```python
@app.get("/api/users")
def list_users(request: Request, keyword: str = None):
    query = "SELECT * FROM sys_admin WHERE tenant_id = " + request.headers.get("X-Tenant-ID")
    if keyword:
        query += f" AND name LIKE '%{keyword}%'"
    results = db.execute(query)
    admins = [format_admin(r) for r in results]
    return {"data": admins, "password": DB_PASSWORD}
```

**审查结果摘要：**

| 问题 | 严重级别 | 规则 | 说明 |
|------|----------|------|------|
| SQL 注入 | critical | SQL_INJECTION | 通过 `keyword` 参数和 Header 注入 SQL |
| 敏感信息泄露 | critical | SENSITIVE_EXPOSE | API 响应中包含数据库密码 |
| 缺少认证 | critical | MISSING_AUTH | 接口未验证 JWT Token |
| 缺少分页 | major | MISSING_PAGINATION | 全量查询无分页，可能导致性能问题 |

**评分：** 20/100 (F) - **Verdict: fail**

**建议修复方案：**

```python
@app.get("/api/users")
@require_auth
@rate_limit(max_requests=100, window=60)
def list_users(
    request: Request,
    keyword: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant_id = current_user.tenant_id  # 从 JWT 中获取，不从 Header 读取
    query = select(Admin).where(Admin.tenant_id == tenant_id)
    if keyword:
        query = query.where(Admin.name.ilike(f"%{keyword}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    results = db.scalars(
        query.offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"data": [a.to_dict() for a in results], "total": total}
```

### 示例 2：Go 并发安全审查

**输入代码：**

```go
var userCache = make(map[int]*User)
var mu sync.Mutex

func GetUser(id int) *User {
    mu.Lock()
    user, ok := userCache[id]
    mu.Unlock()
    if ok {
        return user
    }

    user = fetchUserFromDB(id)
    userCache[id] = user  // 未加锁写入 map
    return user
}
```

**审查结果摘要：**

| 问题 | 严重级别 | 规则 | 说明 |
|------|----------|------|------|
| Map 并发写入 | critical | CONCURRENT_MAP_WRITE | 写入 map 未加锁，存在并发 panic |
| Cache Stampede | major | CACHE_THUNDERING_HERD | 高并发下可能多次查询 DB |
| 缺少 nil 检查 | major | NIL_CHECK | `fetchUserFromDB` 返回 nil 时未处理 |

**评分：** 45/100 (D) - **Verdict: fail**

**建议修复方案：**

```go
var userCache = make(map[int]*User)
var mu sync.RWMutex

func GetUser(ctx context.Context, id int) (*User, error) {
    // 读锁检查缓存
    mu.RLock()
    user, ok := userCache[id]
    mu.RUnlock()
    if ok {
        return user, nil
    }

    // 写锁防止 Cache Stampede（Double-Check Locking）
    mu.Lock()
    defer mu.Unlock()

    // 二次检查，避免重复查询
    if user, ok = userCache[id]; ok {
        return user, nil
    }

    user, err := fetchUserFromDB(ctx, id)
    if err != nil {
        return nil, fmt.Errorf("fetch user %d: %w", id, err)
    }
    if user == nil {
        return nil, ErrUserNotFound
    }
    userCache[id] = user
    return user, nil
}
```

---

## 反模式清单 (Anti-Patterns)

以下反模式在审查中应特别关注：

### 通用反模式

| 反模式 | 说明 | 严重级别 |
|--------|------|----------|
| God Function | 单个函数超过 100 行或承担过多职责 | major |
| Copy-Paste Programming | 重复代码块超过 5 行且出现 2 次以上 | minor |
| Magic Number | 代码中出现未解释的硬编码数字 | minor |
| Golden Hammer | 不考虑场景过度使用某种技术（如所有地方都用 Redis） | minor |
| Premature Optimization | 没有性能指标支撑的"优化"代码 | minor |
| Spaghetti Code | 控制流混乱，GOTO 式的层层嵌套 if-else | major |
| Lava Flow | 废弃代码保留在代码库中"以防万一" | minor |
| Boat Anchor | 引入了但未使用的依赖或代码 | minor |
| Hard Code | 配置信息（IP、端口、密钥）硬编码在代码中 | critical |
| TODO Debt | 积累大量未处理的 TODO / FIXME / HACK 注释 | minor |

### 安全反模式

| 反模式 | 说明 | 严重级别 |
|--------|------|----------|
| Security by Obscurity | 依赖隐藏实现来保障安全（如隐藏管理路径） | critical |
| Trust Boundary Violation | 不验证外部输入就信任使用 | critical |
| Logging Sensitive Data | 在日志中记录密码、Token、个人信息 | critical |
| Rolling Your Own Crypto | 自行实现加密算法而非使用标准库 | critical |
| Insecure Defaults | 使用组件的默认安全配置 | major |

### 并发反模式

| 反模式 | 说明 | 严重级别 |
|--------|------|----------|
| Double-Checked Locking (错误实现) | 锁的双检实现不正确（尤其在不安全的语言中） | critical |
| Busy Waiting | 循环中 sleep 轮询而非使用事件/条件变量 | major |
| Synchronous in Async Context | 在 async 函数中调用阻塞操作 | major |
| Shared Mutable State | 多线程/协程共享可变状态而不同步 | critical |

### 数据库反模式

| 反模式 | 说明 | 严重级别 |
|--------|------|----------|
| N+1 Query | 循环中逐条查询关联数据 | major |
| SELECT * | 查询不需要的字段浪费带宽和内存 | minor |
| Missing Transaction | 需要事务的操作未使用事务 | critical |
| Implicit Type Conversion | WHERE 条件中字段类型不匹配导致索引失效 | major |
| God Table | 单表字段超过 30 个，应拆分 | minor |

---

## 项目特定审查规则 (Project-Specific Rules)

基于本项目的架构约定，额外检查以下规则：

### 多租户 (Multi-Tenancy)

- [ ] 所有业务查询必须包含 `tenant_id` 过滤条件
- [ ] `tenant_id` 必须从 JWT Token 中获取，禁止从请求参数中读取
- [ ] 跨租户数据访问必须被阻止

### 时间戳约定

- [ ] 时间字段必须使用 BIGINT 毫秒格式（`create_time`, `update_time`）
- [ ] 禁止使用 DATETIME / TIMESTAMP 类型存储时间

### API 规范

- [ ] API 路由必须以 `/api` 为前缀
- [ ] 响应格式必须包含 `code`、`message`、`data` 字段
- [ ] 分页接口必须支持 `page` 和 `page_size` 参数

### 权限系统

- [ ] API 端点必须通过 Gateway 的权限校验
- [ ] 权限标识必须与 `sys_menu.permission` 对应
- [ ] 用户组权限通过 `sys_admin_group.power` JSON 数组管理

---

## 与其他 Skill 的协作

| 协作 Skill | 协作方式 |
|------------|----------|
| `backend-development` | 审查 BE Agent 生成的后端代码 |
| `frontend-development` | 审查 FE Agent 生成的前端代码 |
| `test-generation` | 当审查发现问题时，触发测试用例生成以覆盖相关场景 |
| `requirement-analysis` | 根据需求文档验证代码实现的完整性 |
| `task-breakdown` | 审查结果中 major/critical 问题可拆分为新任务 |

---

## 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| 1.0.0 | 2025-04-25 | 初始版本，基础代码审查能力 |
| 1.1.0 | 2025-05-20 | 新增多语言特定检查、OWASP 安全审计 Checklist、反模式清单、评分体系、项目特定规则 |
