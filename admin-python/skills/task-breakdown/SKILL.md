---
id: task_breakdown
name: task-breakdown
description: "将需求文档分解为具体的开发任务，包含前后端任务分配、依赖关系和工时估算。"
version: 1.0.0
category: analysis
agent_type: PJM
metadata:
  hermes:
    tags: [task, breakdown, planning, wbs]
    related_skills: [requirement-analysis, backend-development, frontend-development]
---

# 任务分解

## When to Use
- 已有需求文档，需要拆解为可执行的开发任务
- 项目经理需要制定开发计划和任务分配
- 需要识别任务之间的依赖关系

## Instructions
1. 接收需求文档作为输入
2. 按功能模块拆解为独立任务
3. 为每个任务分配执行角色（BE/FE/QA）
4. 识别任务间的依赖关系
5. 估算每个任务的工时
6. 输出任务列表（WBS）

## Input
- `requirement_doc` (string, required): 需求文档内容（可以是 JSON 或文本格式）
- `session_id` (string, optional): 会话 ID

## Output
- `tasks` (array): 任务列表，每个任务包含:
  - `task_id`: 任务编号
  - `title`: 任务标题
  - `description`: 任务描述
  - `assignee`: 分配角色 (BE/FE/QA)
  - `dependencies`: 依赖的任务 ID 列表
  - `estimated_hours`: 预估工时
  - `priority`: 优先级
  - `status`: 初始状态 (pending)
