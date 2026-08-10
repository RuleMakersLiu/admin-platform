"""前端开发——完整 Vue/React 代码。"""

FRONTEND_DEV_PROMPT = """基于以下需求文档、页面设计、原型预览和 API 契约，生成完整、可运行、边界清晰的前端代码。

需求文档:
{{requirement_output}}

页面设计:
{{page_design_output}}

原型预览参考:
{{prototype_output}}

交付包中的 API 接口定义:
{{delivery_output}}

## 目标技术栈
{{frontend_tech}}

请根据以上技术栈生成对应的前端代码。

## 前端实现边界
- 必须严格遵循页面设计和交付包 API 契约，不得擅自改字段、接口、权限 key 和页面形态。
- 必须复用目标前端项目的目录、路由、API 封装、组件库、权限指令和样式规范。
- 不确定是否存在的组件/工具不要引用；优先使用基础组件和本文件内可维护方法。
- 只输出本需求相关文件；不输出静态演示页或与真实项目脱节的 mock wrapper。
- uni-app/小程序项目不要按普通 Web 后台生成；monorepo 项目必须输出目标应用真实页面路径，例如 `apps/<app>/pages/**/index.vue`，并按 H5 可预览要求补齐页面内 mock/兜底状态。
- 禁止引用未验证的 API 命名导出或权限 helper。使用 `@hc-agent/http`、`hasPermission`、`v-action` 等能力前必须来自 Project Skill/代码参考；否则使用当前文件内可运行的最小 helper 或与页面字段一致的预览 mock，保证首屏不报错。

**技术栈判断规则**:
- 如果技术栈包含 `vue`、`react`、`javascript`、`typescript` 等 → 生成对应前端框架代码
- 如果技术栈包含 `php` → 这通常是 BFF/API 转发层，生成 PHP 控制器代码：
  - 接收前端请求 → 转发到后端 Java API → 返回响应
  - 使用 curl 或 Guzzle 调用后端接口
  - 处理参数转换、鉴权、日志等中间件逻辑
- 如果未指定技术栈 → 默认使用 Vue 3 + Ant Design Vue + TypeScript

输出要求:
- 每个代码块前用 `### 文件: 路径/文件名` 标注
- 用对应语言的代码块包裹（```vue, ```js, ```ts, ```php, ```jsx, ```tsx 等）
- 前端框架项目：包含列表页、表单/弹窗组件、API 服务、路由配置
- PHP 转发层项目：包含 Controller（接收+转发）、Service（业务逻辑）、Middleware（鉴权/日志）、路由配置
- 必须实现加载、空数据、搜索无结果、无权限、接口异常、重复提交、删除二次确认等状态
- 所有事件方法、表单校验、API 调用、字段兜底都必须完整实现
- 列表页必须保证分页字段一致；详情/表单页必须保证对象字段默认值安全
- mock 数据、页面字段、API service 字段和交付包字段必须一致

在所有代码之后，请用以下 JSON 格式汇总文件列表:
```json
[
  {"path": "src/views/List.vue", "content": "完整文件内容"},
  {"path": "src/api/module.js", "content": "完整文件内容"}
]
```"""
