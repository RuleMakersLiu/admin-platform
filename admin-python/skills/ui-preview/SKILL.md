---
id: ui_preview
name: ui-preview
description: "根据需求描述生成 UI 预览 HTML，使用 Ant Design 风格，可直接在浏览器中预览。"
version: 1.0.0
category: development
agent_type: FE
metadata:
  hermes:
    tags: [ui, preview, html, design]
    related_skills: [frontend-development, requirement-analysis]
---

# UI预览生成

## When to Use
- 需要快速生成 UI 原型预览
- 需要可视化地确认页面布局
- 设计评审时需要快速产出 HTML 预览

## Instructions
1. 接收需求描述
2. 分析页面布局结构（头部、侧边栏、内容区等）
3. 使用 Ant Design 风格编写 HTML
4. 包含 CDN 引用的 React 和 Ant Design 资源
5. 生成可直接在浏览器中运行的 HTML 文件
6. 确保响应式布局

## Input
- `requirement` (string, required): 需求描述或 UI 设计说明
- `session_id` (string, optional): 会话 ID

## Output
- `html` (string): 完整的 HTML 文件内容，可直接在浏览器中打开预览
