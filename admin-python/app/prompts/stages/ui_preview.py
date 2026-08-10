"""UI 预览——静态 HTML 后台页面。"""

UI_PREVIEW_PROMPT = """根据需求文档，生成一个静态管理后台页面预览。

## 需求文档
{{requirement_output}}

## 前端技术栈
{{frontend_tech}}

## 用户需求
{{user_request}}

## 输出要求
- 只输出一个 ```html 代码块，不要在代码块前后写任何文字说明
- HTML 必须完整输出，不能被截断，控制在 360 行以内
- `<body>` 必须包含 `data-preview-ready="true"`，主内容容器必须使用 `id="preview-root"`，便于系统自动检查预览是否可用

## 技术方案
纯静态 HTML，不需要 Vue/React/JS，只引入 antd CSS：
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/ant-design-vue@1.7.8/dist/antd.min.css">
用 antd CSS 类名（.ant-btn, .ant-table, .ant-input 等）模拟组件外观。

## 实现要求
1. 纯静态 HTML + CSS，不需要 <script>
2. 第一屏必须是后台工作台，不要做 landing page：左侧菜单、标题区、搜索筛选、主表格、关键操作按钮齐全
3. 主列表页 + 新增/编辑弹窗静态样式 + 删除确认静态样式 + 无权限/空数据/加载中/异常状态
4. 表格放 5 条 mock 数据（中文），状态用 tag 展示，列和字段要贴合需求
5. 必须展示权限效果：菜单/页面/按钮/数据范围至少 3 类；无权限按钮要 disabled 并解释原因
6. 视觉风格要像成熟管理后台：信息密度适中、对齐清晰、颜色克制，避免大面积霓虹、渐变球、营销 hero 和占位文案
7. 所有文字使用中文"""
