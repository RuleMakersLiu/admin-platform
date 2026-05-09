---
id: progress_report
name: progress-report
description: "生成项目进度总结报告，包含任务完成情况、里程碑状态和风险分析。"
version: 1.0.0
category: report
agent_type: RPT
metadata:
  hermes:
    tags: [report, progress, summary, milestone]
    related_skills: [task-breakdown, requirement-analysis]
---

# 进度报告

## When to Use
- 需要生成每日/每周/每月项目进度报告
- 需要汇总各角色的任务完成情况
- 项目里程碑节点需要产出进度总结

## Instructions
1. 接收项目数据（任务列表、完成状态等）
2. 统计任务完成率和进度百分比
3. 分析各角色的任务分布和完成情况
4. 识别延期任务和阻塞项
5. 评估风险和问题
6. 生成结构化进度报告

## Input
- `project_data` (string, required): 项目数据（JSON 格式，包含任务列表和状态）
- `session_id` (string, optional): 会话 ID

## Output
- `report` (object): 进度报告，包含:
  - `title`: 报告标题
  - `period`: 报告周期
  - `summary`: 总体进度摘要
  - `task_stats`: 任务统计（总数/已完成/进行中/待开始）
  - `milestones`: 里程碑状态
  - `risks`: 风险和问题列表
  - `next_steps`: 下一步计划
