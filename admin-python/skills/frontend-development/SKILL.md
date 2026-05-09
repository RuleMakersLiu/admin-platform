---
id: frontend_development
name: frontend-development
description: "根据需求生成前端页面代码，使用 Vue 2 + antd-vue 1.x 组件开发。"
version: 1.0.0
category: development
agent_type: FE
metadata:
  hermes:
    tags: [frontend, vue2, antd-vue, code-generation]
    related_skills: [requirement-analysis, ui-preview, code-review]
---

# 前端开发

## When to Use
- 需要根据需求生成前端页面代码
- 需要创建 Vue 2 组件和页面
- 需要实现表单、列表、详情等标准页面

## Instructions
1. 接收需求描述和 UI 规范（如有）
2. 分析页面类型（列表页 / 详情页 / 表单页 / 仪表盘）
3. 生成 .vue 单文件组件代码
4. 使用 antd-vue 1.x 组件: a-table, a-form, a-modal, a-card, a-button, a-input, a-select, a-date-picker 等
5. 使用 Vue 2 Options API (data, methods, computed, watch, mounted)
6. 使用 axios 进行 API 调用
7. 使用 scoped style 编写样式

## Input
- `requirement` (string, required): 需求描述
- `ui_spec` (string, optional): UI 设计规范或描述
- `session_id` (string, optional): 会话 ID

## Output
- `code` (object): 生成的前端代码，包含:
  - `page`: .vue 页面组件代码
  - `components`: 子组件代码
  - `api`: API 调用层代码
  - `router`: 路由配置代码
