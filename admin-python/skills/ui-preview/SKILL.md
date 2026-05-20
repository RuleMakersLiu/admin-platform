---
id: ui_preview
name: ui-preview
description: "Generate UI preview HTML from requirement descriptions with Vue 2 + antd-vue 1.x. 根据需求描述生成 UI 预览 HTML，使用 Vue 2 + antd-vue 1.x 风格，支持暗色主题和响应式布局。"
version: 1.1.0
category: development
agent_type: FE
metadata:
  hermes:
    tags: [ui, preview, html, vue, antd-vue, prototype, wireframe]
    related_skills: [frontend-development, requirement-analysis]
---

# UI 预览生成

## 概述

将自然语言需求快速转化为可视化 HTML 原型。生成的 HTML 文件：
- 基于 Vue 2.7 + antd-vue 1.7.8，通过 CDN 加载
- 单文件，可直接在浏览器中运行
- 包含 mock 数据和完整 CRUD 交互
- 支持暗色科技风主题

## 使用场景

- 需求评审阶段快速产出可视化原型
- 设计评审时需要即时展示页面布局
- 客户演示时展示页面交互效果
- 开发前的页面结构确认

## 生成流程

### 第一步：分析页面类型

根据需求识别页面类型：

| 页面类型 | 布局特征 | 核心组件 |
|---------|---------|---------|
| 列表页 | 搜索栏 + 数据表格 + 分页 | a-table, a-form, a-pagination |
| 表单页 | 表单 + 提交/取消按钮 | a-form, a-input, a-select |
| 详情页 | 信息展示 + 操作按钮 | a-descriptions, a-card |
| 仪表盘 | 统计卡片 + 图表 | a-card, a-statistic, a-chart |
| 设置页 | Tab 切换 + 表单分组 | a-tabs, a-form |
| 对话页 | 消息列表 + 输入框 | a-list, a-input, a-button |

### 第二步：构建 HTML 骨架

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>页面标题</title>
  <!-- CDN 引用 -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/ant-design-vue@1.7.8/dist/antd.min.css">
  <script src="https://cdn.jsdelivr.net/npm/vue@2.7.14/dist/vue.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/ant-design-vue@1.7.8/dist/antd.min.js"></script>
</head>
<body>
  <div id="app">
    <a-layout>
      <a-layout-header>...</a-layout-header>
      <a-layout-content>...</a-layout-content>
    </a-layout>
  </div>
  <script>
    new Vue({
      el: '#app',
      data() { return { ... } },
      methods: { ... }
    })
  </script>
</body>
</html>
```

### 第三步：填充组件和数据

1. **布局组件**: a-layout (header + sider + content + footer)
2. **导航组件**: a-menu, a-breadcrumb
3. **数据展示**: a-table (带排序/筛选/分页)
4. **表单组件**: a-form (带验证规则)
5. **反馈组件**: a-modal, a-message, a-notification
6. **数据填充**: 内置 5-10 条 mock 数据

### 第四步：添加交互逻辑

- **CRUD 操作**: 新增/编辑弹窗 + 删除确认
- **搜索筛选**: 关键词搜索 + 下拉筛选 + 重置
- **分页**: 切换页码和每页条数
- **排序**: 表头点击排序
- **响应式**: 窗口缩小自动折叠侧边栏

## 样式规范

### 暗色科技风主题

```css
/* 主色调 */
--primary: #00d4ff;
--bg-dark: #0a0a0f;
--bg-card: rgba(15, 15, 25, 0.8);
--border: rgba(0, 212, 255, 0.15);
--text-primary: #e0e0e0;
--text-secondary: #888;

/* 全局样式 */
body {
  background: #0a0a0f;
  color: #e0e0e0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* 卡片样式 */
.ant-card {
  background: rgba(15, 15, 25, 0.8) !important;
  border: 1px solid rgba(0, 212, 255, 0.15) !important;
  border-radius: 12px;
}

/* 表格样式 */
.ant-table {
  background: transparent !important;
  color: #e0e0e0;
}

/* 按钮样式 */
.ant-btn-primary {
  background: #00d4ff;
  border-color: #00d4ff;
}
```

### 布局规范

- 页面内边距: 24px
- 卡片间距: 16px
- 圆角: 8-12px
- 阴影: 0 4px 20px rgba(0, 212, 255, 0.1)

## CDN 引用清单

必须包含以下 CDN（版本固定）：

```html
<!-- Vue 2.7 -->
<script src="https://cdn.jsdelivr.net/npm/vue@2.7.14/dist/vue.min.js"></script>

<!-- antd-vue 1.7.8 -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/ant-design-vue@1.7.8/dist/antd.min.css">
<script src="https://cdn.jsdelivr.net/npm/ant-design-vue@1.7.8/dist/antd.min.js"></script>

<!-- 可选: 图表 -->
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>

<!-- 可选: 图标 -->
<script src="https://cdn.jsdelivr.net/npm/@ant-design/icons@4.0.0/dist/index.umd.min.js"></script>
```

## 注意事项

1. **沙箱安全**: 生成的 HTML 在 iframe sandbox 中预览，需设置 `allow-scripts`
2. **内容安全策略**: 不使用 inline event handlers (onclick 等)，改用 Vue 事件绑定
3. **字体加载**: CDN 加载可能较慢，设置 fallback 字体
4. **响应式**: 使用 antd 的 Row/Col 栅格系统确保移动端适配
5. **性能**: 避免大量 mock 数据 (>100条)，保持渲染流畅

## 输出格式

```json
{
  "html": "<!DOCTYPE html>...",
  "page_type": "list|form|detail|dashboard|settings",
  "components_used": ["a-table", "a-form", "a-modal"],
  "mock_data_count": 10
}
```

## 示例

### 示例 1: 用户管理列表页

需求: "创建一个用户管理页面，支持搜索、新增、编辑、删除用户，显示用户名、角色、状态、创建时间"

生成要点:
- 顶部搜索栏: 用户名输入框 + 角色下拉 + 状态选择 + 搜索/重置按钮
- 操作按钮: 新增用户 (primary) + 批量删除 (danger)
- 数据表格: 列 = 用户名/邮箱/角色/状态/创建时间/操作
- 操作列: 编辑链接 + 删除链接 + 禁用/启用开关
- 新增/编辑弹窗: 表单 = 用户名/邮箱/密码/角色/状态
- 删除确认: Modal.confirm 提示
- Mock 数据: 10 条不同状态的用户数据

### 示例 2: 数据看板仪表盘

需求: "设计一个运营数据仪表盘，展示今日用户数、订单量、收入、转化率，以及近7天趋势图"

生成要点:
- 顶部统计卡片: 4 个 a-card + a-statistic (带图标和趋势箭头)
- 中间区域: echarts 折线图 (近7天趋势) + 柱状图 (分类统计)
- 底部区域: 最近订单表格 + 热门商品排行
- 时间筛选: 今日/本周/本月 tab 切换
- 自动刷新: 每 30 秒刷新数据 (模拟)
