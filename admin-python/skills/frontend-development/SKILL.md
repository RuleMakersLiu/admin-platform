---
id: frontend_development
name: frontend-development
description: "根据需求生成前端页面代码，支持 React + Ant Design 5 组件开发。"
version: 1.0.0
category: development
agent_type: FE
metadata:
  hermes:
    tags: [frontend, react, ant-design, code-generation]
    related_skills: [requirement-analysis, ui-preview, code-review]
---

# 前端开发

## When to Use
- 需要根据需求生成前端页面代码
- 需要创建 React 组件和页面
- 需要实现表单、列表、详情等标准页面

## Instructions
1. 接收需求描述和 UI 规范（如有）
2. 分析页面类型（列表页 / 详情页 / 表单页 / 仪表盘）
3. 生成页面组件代码（React + TypeScript）
4. 使用 Ant Design 5 组件库
5. 实现状态管理（Zustand）
6. 生成 API 调用层代码
7. 确保路径别名 `@/` 映射正确

## Input
- `requirement` (string, required): 需求描述
- `ui_spec` (string, optional): UI 设计规范或描述
- `session_id` (string, optional): 会话 ID

## Output
- `code` (object): 生成的前端代码，包含:
  - `page`: 页面组件代码
  - `components`: 子组件代码
  - `service`: API 调用层代码
  - `store`: 状态管理代码
