# admin-platform 技术升级调研报告

- **日期**：2026-10-16
- **基线**：main 分支 `eb480e0`（2026-08-12，距今约 2 个月未更新）
- **性质**：只读调研，不改代码。所有版本号均已通过 npm registry / PyPI / 官方发布说明核实（截至 2026-10-16）

---

## 0. 结论速览

项目整体架构（Go 微服务 + Python AI 后端 + React 前端的多语言 monorepo）没有过时，技术选型依然主流。真正的差距集中在三处：

1. **工程化有窟窿**：仓库里有 55+ 个测试文件（前端 Vitest 7 个、admin-python pytest 33 个、Go 15 个、Playwright E2E 3 个），但**没有任何 CI 自动执行它们**；ESLint 8 已 EOL；两个 Python 包用 `>=` 约束且无 lockfile，构建不可复现。这是投入产出比最高的补强点——所有后续升级都需要这条回归防线。
2. **前端落后 2~3 个大版本**：React 18→19.3、Vite 5→8（底层换成 Rolldown）、antd 5→6、TypeScript 5.9→7（原生编译器，约 10 倍提速）、Vitest 2→5、react-router 6→8。echarts 6 已是最新，无需动。
3. **AI 栈处在 1.0 前夜**：LangChain/LangGraph 已到 1.x 稳定线（官方承诺 2.0 前无破坏性变更），项目还在 0.3/0.4；MCP 规范 2026-07-28 大改版（无状态核心，wire 级不兼容），SDK 已到 2.3.0，项目还在 1.6；智谱旗舰已到 GLM-5.3，项目 provider 只支持到 GLM-5.2。

**推荐实施顺序**（详见第 6 章路线图）：

| 阶段 | 内容 | 预估工作量 | 风险 |
|---|---|---|---|
| 0 | CI + Python 依赖锁定 + Node 版本钉住 | 2~3 人日 | 低 |
| 1 | 低风险刷新：Go 1.26 / gin / gorm、GLM-5.3 接入、oxlint | 2~3 人日 | 低 |
| 2 | 前端大版本：React 19 → antd 6 → Vite 8 + TS 7 + Vitest 5 → react-router 8 | 4~7 人日 | 中 |
| 3 | LangChain/LangGraph 0.x → 1.x | 3~5 人日 | 中 |
| 4 | MCP SDK 1.6 → 2.x（wire 不兼容，建议单独立项评估） | 3~5 人日 | 高 |

---

## 1. 项目现状快照

### 1.1 结构

多语言 monorepo，但**不是** npm workspace，也无 go.work，各目录独立管理依赖：

| 目录 | 技术 | 角色 | 端口 |
|---|---|---|---|
| admin-gateway | Go/Gin | API 网关（Kafka producer、Redis 缓存、JWT） | 8080 |
| admin-python | Python/FastAPI | 主后端：AI Agent、流水线、知识库 | 8081 |
| admin-generator / admin-deploy / admin-config | Go/Gin | 代码生成 / 部署 / 配置服务 | 8082/8083/8085 |
| admin-agent | Go/Gin | Agent/知识服务（GORM），疑似被 admin-python 取代 | — |
| admin-ws | Go/Gin | WebSocket 服务（Redis fanout） | — |
| admin-sandbox-controller / admin-egress-gateway | Go | 测评沙箱控制器 / 出口网关 | 8092/8093 |
| admin-common | Go | 共享库，经 `replace ../admin-common` 本地引用 | — |
| admin-frontend | React/TS/Vite | 前端 SPA | dev 3000 |
| admin-eval | Python/FastAPI | Agent 测评控制面 | 8091 |

基础设施：PostgreSQL 15 + pgvector、Redis 7、Kafka 3.9、ClickHouse 25.3、MinIO、OpenTelemetry Collector 0.123、Vault 1.19（`docker/docker-compose*.yml`）。

### 1.2 依赖现状 vs 最新版

**前端（admin-frontend，npm，有 lockfile）**

| 包 | 当前锁定 | 最新（2026-10-16） | 差距 |
|---|---|---|---|
| react / react-dom | 18.3.1 | **19.3.1** | 1 个大版本 |
| antd | 5.29.3 | **6.6.6** | 1 个大版本（6.0 发布于 2025-11-22） |
| vite | 5.4.21 | **8.3.4** | 3 个大版本（底层换 Rolldown） |
| @vitejs/plugin-react | 4.7.0 | 6.1.2 | 2 个大版本 |
| typescript | 5.9.3 | **7.0.2**（npm latest tag） | 2 个大版本（原生 Go 编译器） |
| vitest | 2.1.9 | **5.0.5** | 3 个大版本 |
| eslint | 8.57.1（已 EOL） | 10.12.0 | 2 个大版本 |
| react-router-dom | 6.30.4 | react-router **8.4.0**（包已合并改名） | 2 个大版本 |
| zustand | 4.5.7 | 5.0.15 | 1 个大版本 |
| echarts / echarts-for-react | 6.1.0 / 3.0.6 | 6.1.0 / 3.0.6 | **已是最新，无需动** |
| @tanstack/react-query | 未使用 | 5.104.3 | 建议新引入 |
| oxlint | 未使用 | 1.88.0 | 建议新引入（可选） |

**Python（admin-python / admin-eval，`>=` 约束，无 lockfile）**

| 包 | pyproject 约束 | 最新 | 备注 |
|---|---|---|---|
| fastapi | >=0.109.0 | 0.143.2 | 无 lockfile，实际安装版本不确定 |
| langchain | >=0.3.0 | **1.4.6** | 1.0 于 2025-10-22 发布 |
| langgraph | >=0.4.0 | **1.2.15** | 同上 |
| mcp | >=1.6.0 | **2.3.0** | 对应 2026-07-28 规范，wire 不兼容 |
| anthropic | >=0.49.0 | 1.15.0 | |
| uvicorn | >=0.27.0 | 0.54.0 | |
| asyncpg | >=0.29.0 | 0.32.0 | |
| zhipuai（官方 SDK） | 未使用（自研 provider） | 2.1.5 | 参考 |

**Go（9 个 module，go 1.24）**

| 库 | 当前 | 最新 | 备注 |
|---|---|---|---|
| Go toolchain | 1.24（admin-deploy 钉住 1.24.5） | **1.26**（2026-02-10 发布） | Green Tea GC 默认开启 |
| gin | v1.9.1 | **v1.12.0**（2026-02-28） | |
| gorm + driver/postgres | v1.25.5 / v1.5.x | **v1.31.2**（2026-06） | |
| docker client | v24.0.7 / v25.0.6 | v28.x | 跨多个大版本，API 有变化 |
| go-redis/v9、sarama、jwt/v5 等 | 2024 年版本 | 各有更新 | 低风险刷新 |

### 1.3 工程化缺口（探索确认）

- **零 CI**：无 `.github/workflows`、无 Makefile，`start.sh` 无 test 子命令，55+ 个测试全靠本地手跑
- **ESLint 8 + 旧版 `.eslintrc.cjs`**：ESLint 8 已停止维护，typescript-eslint 6 同步过时
- **前端无服务端状态缓存层**：无 React Query，数据获取全手写 axios + zustand 耦合
- **前后端契约手写**：FastAPI 天然产出 OpenAPI schema，但前端 TS 类型全是手写（`src/services/api.ts`）
- **Python 无 lockfile**：`>=` 约束 + 每次 fresh install 拉最新，构建不可复现（这轮调研发现 FastAPI 已到 0.143.x，说明线上实际跑的版本可能远超 pyproject 声明的下限）
- **无 Node 版本钉住**：无 .nvmrc / engines（Dockerfile 用 node:22-alpine）
- **前端两套测试风格并存**：Vitest + 裸 node 脚本跑 `.mjs`
- **admin-python 的 ruff/black/mypy strict 配了但没有强制执行点**（无 pre-commit、无 CI）

---

## 2. 方向一：工程化补强（P0，先做）

### 2.1 CI 流水线（GitHub Actions）

**现状**：55+ 测试文件零自动执行。**这是全项目投入产出比最高的一项。**

**方案**：`.github/workflows/ci.yml`，按语言分 job：

- `frontend`：node 22 + npm ci → oxlint/eslint → vitest run → tsc 类型检查
- `python`（matrix: admin-python, admin-eval）：uv sync → ruff → mypy（admin-python 已配 strict）→ pytest
- `go`（matrix 或 go.work 一次搞定）：`go build ./... && go test ./...`
- `e2e`：Playwright，可先标记为 nightly/手动触发（依赖整套基础设施起容器，进 CI 门槛较高，可后置）

**注意点**：admin-python 部分测试依赖外网（GLM API）和基础设施（pgvector/redis），需要区分单测和集成测试标记；前端裸 `.mjs` 测试脚本建议趁机并入 vitest。

- 工作量：**1.5~2 人日**
- 风险：低（纯新增，不动现有代码）
- 优先级：**P0**

### 2.2 Lint 工具链：ESLint 8 → 三条路线对比

| 路线 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| **oxlint + oxfmt**（Rust，1.88.0） | 50~100 倍速度；自带 `@oxlint/migrate` 迁移工具；2026 年社区迁移主流方向之一 | 规则覆盖不如 ESLint 插件生态全；第二套心智 | **推荐**。项目 ESLint 规则集很简单（typescript-eslint + react-hooks），迁移面小 |
| Biome 2.x | lint + format 一体 | 项目已用 Prettier 且满意，一体化收益有限 | 备选 |
| ESLint 10 flat config | 兼容性最好、插件最全 | 依旧是性能短板；.eslintrc.cjs 仍需重写为 flat config | 保守选项 |

**配套**：加 pre-commit（或 lefthook）把 ruff/oxlint/gofmt 变成强制执行点，补上「配了但没人跑」的缺口。

- 工作量：0.5~1 人日
- 风险：低
- 优先级：**P0**（ESLint 8 EOL 是明确的维护风险）

### 2.3 Python 依赖锁定（uv + uv.lock）

**现状**：两个 pyproject 全 `>=` 约束、无 lockfile——本轮调研的 FastAPI 版本漂移（0.109 → 0.143）就是直接证据。另外 admin-eval 的 Dockerfile 是 python:3.11-slim + pip，构建慢。

**方案**：引入 [uv](https://docs.astral.sh/uv/)，把 `>=` 收敛为确定版本 + 生成 uv.lock；Dockerfile 改 uv 装依赖（缓存层友好，镜像构建显著提速）。这也让第 3 章 AI 栈的「可控升级」成为可能——没有 lockfile 的大版本升级等于赌博。

- 工作量：0.5~1 人日
- 风险：低（收敛版本时需跑一遍 pytest 验证）
- 优先级：**P0**

### 2.4 go.work 统一 9 个 Go module

**现状**：admin-common 靠各模块 `replace ../admin-common` 引用，本地引用关系散落。

**方案**：根目录 `go.work` + `go.work.sum`，删除各 go.mod 中的 replace 指令；CI 里一个 job 用 `go work` 一次构建全部模块。同时把 toolchain 统一到 1.26。

- 工作量：0.5 人日
- 风险：低
- 优先级：**P1**

### 2.5 OpenAPI 类型生成（前后端契约）

**现状**：FastAPI 天然产出 `/openapi.json`，但前端 `src/services/api.ts` 的 TS 类型全部手写，接口变更无编译期防护。

**方案**：`openapi-typescript`（轻量，只生成类型）或 orval（连 query hooks 一起生成，与 3.7 的 TanStack Query 协同更好）。从 admin-python 导出 schema 进仓库，前端 npm script 重新生成。

- 工作量：1~2 人日
- 风险：低~中（存量接口的 schema 需要补全 response_model 声明才有效果）
- 优先级：**P1**（若决定引入 TanStack Query 则一并做，用 orval）

### 2.6 其他小项

- `.nvmrc` / package.json engines 钉 Node 22（与 Dockerfile 一致）：0.1 人日
- 前端裸 `.mjs` 测试并入 vitest：0.5 人日
- admin-agent 遗留评估：无 Dockerfile、start.sh 未接入，功能疑似已被 admin-python 覆盖，建议确认后归档（这属于项目决策，不在升级范畴）

---

## 3. 方向二：前端技术栈升级

**升级顺序有硬约束**（源自 peerDependencies 实测）：

```
antd 6（react>=18，可最先或与 React 19 同步）
  → React 19（19.3.1）
    → react-router 8（要求 react>=19.2.7，必须最后）
Vite 8 + Vitest 5 + @vitejs/plugin-react 6 作为一组同步升
TypeScript 7 放在 lint 迁移之后（@typescript-eslint 6 不支持 TS7；换 oxlint 则无此约束）
```

### 3.1 React 18.3.1 → 19.3.1

- **收益**：Actions/use API/`useOptimistic` 等新范式（对聊天流式 UI、看板这类交互密集页面有实际价值）；函数组件 ref 直传（`forwardRef` 不再需要）；官方编译器生态（React Compiler 可选，逐步引入）
- **风险**：中低。项目很干净——无 class 组件（仅 1 个合理的 ErrorBoundary）、无 CRA 遗留、无 moment.js。主要工作在第三方库 peer 兼容：antd 6 已支持 React 19；echarts-for-react（react>=16 ✓）、@uiw/react-codemirror（react>=17 ✓）、react-router-dom 6（对 React 19 兼容性一般，但反正要升 v8）
- **工作量**：1~2 人日
- **优先级**：**P1**

### 3.2 antd 5.29.3 → 6.6.6

- **收益**：v6 是技术性升级（样式/主题生成机制大改、包体更小），组件 API 大体兼容 v5；6.5 起内置 AI 相关的 DESIGN.md 与新图标，对本项目这种 AI 平台是顺手的红利
- **风险**：中低。官方提供 [V5→V6 迁移指南](https://ant.design/docs/react/migration-v6)，需要过一遍项目内的 antd 用法（主题定制、message/notification 静态方法等是常见破坏点）
- **工作量**：1~2 人日
- **优先级**：**P1**

### 3.3 Vite 5.4 → 8.3 + Vitest 2 → 5 + plugin-react 6

- **收益**：Vite 8 底层用 Rolldown（Rust）替换 Rollup/esbuild，社区实测构建时间下降 50%~87%；Vitest 5 与 Vite 8 peer 兼容（实测 `vite: ^6.4.0 || ^7.0.0 || ^8.0.0`）
- **风险**：中。**`build.rollupOptions.output.manualChunks` 在 Vite 8 不再支持**，需改写为 Rolldown 的 `advancedChunks`——项目 `vite.config.ts` 里正好用了 manualChunks 做分包，这是本项的主要迁移点。官方建议可先经 `rolldown-vite` 中间态过渡，但从 v5 直接升也可行，逐项核对 v6→v7→v8 的迁移说明即可。另注意个别插件对 Rolldown 的兼容性（项目仅用 @vitejs/plugin-react，官方已适配）
- **工作量**：1~2 人日
- **优先级**：**P1**

### 3.4 TypeScript 5.9 → 7.0（原生编译器 tsgo）

- **收益**：编译器/语言服务原生 Go 重写，官方口径约 10 倍提速。项目 `build` 脚本是 `tsc && vite build` 串行——tsc 全量类型检查正是构建瓶颈，TS7 直接改善；顺带解决「tsc 与 vite 串行拖慢构建」的老问题（也可换 `vite-plugin-checker` 并行，但 TS7 之后可能不再需要）
- **风险**：中。有 breaking changes（装饰器/模块解析选项等边缘行为），需对照官方升级说明逐条核对 tsconfig；生态工具（如 @typescript-eslint）对 TS7 支持参差——**若 2.2 已换 oxlint 则无此顾虑**
- **工作量**：0.5~1 人日
- **优先级**：**P2**（快感的收益，放 lint 迁移之后做）

### 3.5 react-router-dom 6.30 → react-router 8.4

- **收益**：v7 起包合并（react-router-dom 停更，统一为 react-router），v8 当前 8.4.0。长期停留 v6 会持续累积迁移债
- **风险**：中。**实测 peer 要求 react>=19.2.7**，必须排在 React 19 之后；v6→v7→v8 两跳迁移，主要变化在 loader/action 数据 API 与框架模式，纯 SPA 声明式路由的用法迁移面不大
- **工作量**：1~2 人日
- **优先级**：**P2**

### 3.6 zustand 4.5 → 5.0

- **收益**：性能与 TS 类型改进；v5 是当前主流（与 TanStack Query 各管一半：zustand 管 UI 状态、Query 管服务端状态）
- **风险**：低。项目 3 个 store（auth/chat/kanban）用法常规
- **工作量**：0.5 人日
- **优先级**：**P1**

### 3.7 引入 TanStack Query 5.104（新依赖）

- **收益**：当前「手写 axios + 手动 setState + zustand 混存服务端数据」的模式缺少缓存、自动重取、请求去重和加载态管理——对看板/流水线监控这类轮询型页面收益直接；配合 orval 可从 OpenAPI 直接生成 query hooks（见 2.5）
- **风险**：中。属于架构级渐进改造，不是简单换库；建议先在新页面/流水线监控页试点，存量页面按模块渐进
- **工作量**：试点 2~3 人日，全面推广另计
- **优先级**：**P2**（价值高但可拆散慢慢做）

### 3.8 无需动的

echarts 6.1.0 / echarts-for-react 3.0.6 已是最新；dayjs、dompurify、react-markdown 全家均为当前主流版本。

---

## 4. 方向三：AI 技术栈升级（admin-python）

### 4.1 LangChain 0.3 → 1.4.6 / LangGraph 0.4 → 1.2.15

- **背景**：两者于 2025-10-22 同步到达 1.0，官方承诺 2.0 前不做破坏性变更；LangGraph 1.0 支持窗口到 2026-12（0.x 线已临近维护终点）
- **收益**：留在受支持的稳定线上；1.x 的 `create_agent` 标准 API、生产级持久化/可观测性改进
- **破坏性变更核对**（对照官方迁移指南）：
  - 放弃 Python 3.9 —— 项目 requires-python >=3.11，**不受影响** ✓
  - LangChain v1 更改了 chat model 返回类型 —— **这是本项目的主要影响面**：`glm_provider.py` 的自研 ChatGLM 类是 LangChain 风格实现，`agents.py` 的多 provider 分发、`eval_judge.py`、`model_router.py` 都消费这些返回类型，需要逐一适配
  - LangGraph v1 大体向后兼容 —— `pipeline_graph.py` 的 StateGraph + `interrupt()`（human-in-the-loop）+ MemorySaver 用法预计基本保留，按迁移指南核对
- **前置条件**：必须先完成 2.3 的 uv lockfile——1.x 的传递依赖（langchain-core、langchain-anthropic 1.x 等）需要锁定后逐个验证
- **工作量**：3~5 人日（含 33 个 pytest 回归）
- **风险**：中
- **优先级**：**P1**（0.x 维护窗口 2026-12 到期，有时间压力）

### 4.2 MCP SDK 1.6 → 2.3.0（2026-07-28 规范）——风险最高，建议单独立项

- **背景**：MCP 2026-07-28 规范是发布以来最大改版：**无状态协议核心**（会话/握手机制移除）、Multi Round-Trip Requests、header 路由；sampling/roots/logging 被弃用；写路径需要显式幂等键。社区普遍反馈**wire 级双向不兼容**，多数 server 需要重构而非升级
- **影响面**：`app/ai/mcp_server.py` 暴露 stdio + SSE 双 transport 与 list_skills/search_knowledge/get_pipeline_status/stream_chat 等工具——SSE transport 与无状态新模型的映射、stream_chat 工具在无握手协议下的形态，都需要设计层面的重估，不是改 import 就完事
- **建议**：不要与其他升级混在一起。先摸清现有 MCP 客户端是谁、能否同步升级（双向不兼容意味着新旧客户端无法混用），再决定升级或双栈过渡
- **工作量**：3~5 人日（评估 + 重构）
- **风险**：高
- **优先级**：**P2，单独立项**

### 4.3 智谱 GLM-5.3 接入（快速胜利）

- **现状**：`glm_provider.py` 直连 open.bigmodel.cn，支持 GLM-4/4-Plus/4-Flash/5/5.1/5.2；当前官网旗舰已是 **GLM-5.3**，GLM-5.2 起支持 1M 上下文
- **方案**：provider 的模型清单加 GLM-5.3（自研 httpx provider 的好处：不受官方 SDK 版本节奏约束，改配置即可）；模型路由 `model_router.py` 按需把 coding/agent 任务切到 5.3。官方 SDK zhipuai 2.1.5 可作参考但不必引入
- **工作量**：0.5 人日（含冒烟验证）
- **风险**：低
- **优先级**：**P1**

### 4.4 顺带刷新

anthropic 0.49 → 1.15（随 langchain-anthropic 1.x 自然升级）、uvicorn/asyncpg 小版本刷新——在 uv lock 收敛时一并对齐。

---

## 5. 方向四：Go 后端升级

### 5.1 Go 1.24 → 1.26

- **收益**：Green Tea GC 默认启用（高核机器 GC 暂停显著降低）、小对象分配提速、cgo 开销降低——对 ws/gateway 这类长连接高并发服务是纯性能红利；1.26 的实验性 `runtime/secret` 包与本项目 Vault/egress-gateway 的密钥管理方向契合，可保持关注
- **风险**：低（Go 向后兼容承诺；主要核对 9 个 module 的 go.mod toolchain 统一，admin-deploy 钉了 1.24.5 需同步）
- **工作量**：0.5 人日
- **优先级**：**P1**

### 5.2 gin 1.9.1 → 1.12.0

- **收益/风险**：bug fix + 性能改进；跨 3 个 minor，API 兼容（gin 无 semver-major），过一遍 release notes 即可。新版要求 Go 1.24+，与 5.1 顺序无冲突
- **工作量**：0.5 人日（全服务回归）
- **优先级**：**P1**

### 5.3 gorm 1.25.5 → 1.31.2

- **收益/风险**：6 个 minor 的累积修复；GORM 升级历来平滑，重点回归 admin-agent/admin-config/admin-generator/admin-deploy 四个用到 GORM 的服务
- **工作量**：0.5 人日
- **优先级**：**P1**

### 5.4 docker client v24/v25 → v28.x

- **风险**：中。跨多个大版本，client API 有废弃调整（admin-agent、admin-deploy 受影响），且这两个服务直接操作 docker.sock，建议单独分支充分测试沙箱场景
- **工作量**：1~2 人日
- **优先级**：**P2**

### 5.5 其他

go-redis v9.4 → v9 最新、jwt/v5、sarama 1.43 → 最新：低风险刷新，与 5.2 一批做。

---

## 6. 实施路线图

**总原则**：先建防线（CI/lockfile），再动依赖；每一阶段以现有 55+ 测试 + E2E 作为回归门槛；所有升级在独立分支完成。

### 阶段 0：防线（P0，2~3 人日）
1. GitHub Actions CI（frontend / python / go 三个 job）
2. uv + uv.lock 锁定两个 Python 包
3. .nvmrc + engines 钉 Node 22
4. 验证：CI 在 main 上全绿

### 阶段 1：低风险刷新（P0/P1，2~3 人日）
1. oxlint + oxfmt 替换 ESLint 8 + pre-commit 钩子
2. Go 1.26 toolchain 统一 + go.work
3. gin 1.12 / gorm 1.31 / go-redis 等刷新
4. GLM-5.3 接入（provider 清单 + 冒烟）
5. 验证：CI + 各服务启动冒烟 + 沙箱/部署流程手测

### 阶段 2：前端大版本（P1/P2，4~7 人日，按依赖顺序）
1. antd 5 → 6（可先行，React 18 即可）
2. zustand 4 → 5
3. React 18 → 19.3
4. Vite 8 + @vitejs/plugin-react 6 + Vitest 5（manualChunks → advancedChunks 是主要迁移点）
5. TypeScript 7（在 oxlint 之后无生态包袱）
6. react-router 6 → 8（最后，依赖 React ≥19.2.7）
7. TanStack Query 试点（新页面或流水线监控页）+ orval 类型生成
8. 验证：vitest 全量 + Playwright E2E 3 个 spec + 手工过关键页面

### 阶段 3：LangChain/LangGraph 1.x（P1，3~5 人日）
1. 前置：阶段 0 的 uv.lock 已就位
2. langchain/langgraph/langchain-anthropic/langchain-openai 升到 1.x 并锁定
3. 适配自研 ChatGLM provider 的返回类型 + agents/eval_judge/model_router 消费端
4. 核对 pipeline_graph.py 的 interrupt/MemorySaver 行为
5. 验证：admin-python 33 个 pytest + 一条完整流水线端到端跑通

### 阶段 4：MCP SDK v2（P2，单独立项）
1. 盘点现有 MCP 客户端及其升级能力（wire 双向不兼容，无法混用）
2. 决策：直接升级 vs 双栈过渡
3. mcp_server.py 按 v2 无状态模型重构（stdio/SSE transport 重新设计）
4. 验证：MCP 客户端联调

### 超出本次范围、值得后续关注
- 基础设施镜像版本（Redis 7、Kafka 3.9、ClickHouse 25.3 均有更新线，升级涉及数据兼容性，建议另行评估）
- admin-agent 遗留服务的去留决策

---

## 7. 参考资料

- [Vite 8 官方迁移指南](https://vite.dev/guide/migration) / [Vite 8 发布说明](https://vite.dev/blog/announcing-vite8)
- [React 19 升级指南](https://react.dev/blog/2024/04/25/react-19-upgrade-guide)
- [Ant Design V5→V6 迁移指南](https://ant.design/docs/react/migration-v6) / [官方 Changelog](https://ant.design/changelog)
- [TypeScript 7.0 发布公告](https://devblogs.microsoft.com/typescript/announcing-typescript-7) / [InfoQ 报道](https://www.infoq.com/news/2026/08/typescript-7-released)
- [LangChain & LangGraph 1.0 公告](https://www.langchain.com/blog/langchain-langgraph-1dot0) / [LangGraph v1 迁移指南](https://docs.langchain.com/oss/python/migrate/langgraph-v1) / [LangChain v1 迁移指南](https://docs.langchain.com/oss/python/migrate/langchain-v1)
- [MCP 2026-07-28 规范公告](https://blog.modelcontextprotocol.io/posts/2026-07-28) / [MCP Python SDK v1→v2 迁移指南](https://py.sdk.modelcontextprotocol.io/migration) / [Cloudflare: The Next Generation of MCP](https://blog.cloudflare.com/mcp-v2)
- [Go 1.26 Release Notes](https://go.dev/doc/go1.26) / [gin Releases](https://github.com/gin-gonic/gin/releases) / [GORM Releases](https://github.com/go-gorm/gorm/releases)
- [FastAPI Release Notes](https://fastapi.tiangolo.com/release-notes)
- [智谱 GLM-5.2 发布](https://z.ai/blog/glm-5.2) / [GLM 模型发布记录](https://docs.bigmodel.cn/cn/update/new-releases)
- [Oxlint 文档](https://oxc.rs/docs/guide/usage/linter) / [ESLint vs Biome vs Oxlint 2026 对比](https://www.pkgpulse.com/guides/biome-vs-eslint-vs-oxlint-2026)
- [TanStack Query 文档](https://tanstack.com/query/latest)
