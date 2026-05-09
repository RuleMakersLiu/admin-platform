---
id: ui_preview
name: ui-preview
description: "根据需求描述生成 UI 预览 HTML，使用 Vue 2 + antd-vue 1.x 风格，可直接在浏览器中预览。"
version: 1.0.0
category: development
agent_type: FE
metadata:
  hermes:
    tags: [ui, preview, html, vue, antd-vue]
    related_skills: [frontend-development, requirement-analysis]
---

# UI预览生成

## When to Use
- 需要快速生成 UI 原型预览
- 需要可视化地确认页面布局
- 设计评审时需要快速产出 HTML 预览

## Instructions
1. 接收需求描述
2. 分析页面布局结构（a-layout: header + sider + content）
3. 使用 Vue 2 + antd-vue 1.x 组件编写单 HTML 文件
4. 通过 CDN 引入 Vue 2.7、antd-vue 1.7.8 及对应 CSS
5. 使用 a-table, a-form, a-modal, a-card, a-button 等组件
6. 包含 mock 数据和完整 CRUD 交互
7. 生成可直接在浏览器中运行的 HTML 文件
8. 确保页面精致美观：合理间距、阴影、圆角

## CDN Resources
- Vue 2: `https://cdn.jsdelivr.net/npm/vue@2.7.16/dist/vue.min.js`
- antd-vue CSS: `https://cdn.jsdelivr.net/npm/ant-design-vue@1.7.8/dist/antd.min.css`
- antd-vue JS: `https://cdn.jsdelivr.net/npm/ant-design-vue@1.7.8/dist/antd.min.js`
- moment.js: `https://cdn.jsdelivr.net/npm/moment@2.29.4/min/moment.min.js`

## Input
- `requirement` (string, required): 需求描述或 UI 设计说明
- `session_id` (string, optional): 会话 ID

## Output
- `html` (string): 完整的 HTML 文件内容，可直接在浏览器中打开预览
