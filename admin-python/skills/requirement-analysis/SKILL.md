---
id: requirement_analysis
name: requirement-analysis
description: "分析用户需求，生成结构化需求文档(PRD)。支持功能需求、非功能需求、用户故事等格式输出。"
version: 1.0.0
category: analysis
agent_type: PM
metadata:
  hermes:
    tags: [requirement, analysis, prd, product]
    related_skills: [task-breakdown, backend-development, frontend-development]
---

# 需求分析

## When to Use
- 用户提供了一段需求描述，需要转化为结构化的需求文档
- 需要对原始需求进行澄清、拆解和优先级排序
- 产品经理需要输出 PRD 文档供开发团队参考

## Instructions
1. 接收用户的原始需求描述
2. 识别功能需求和非功能需求
3. 编写用户故事（As a... I want... So that...）
4. 定义验收标准（Acceptance Criteria）
5. 评估优先级和复杂度
6. 输出结构化 PRD 文档

## Input
- `user_request` (string, required): 用户的原始需求描述
- `session_id` (string, optional): 会话 ID，用于上下文关联

## Output
- `requirement_doc` (object): 结构化需求文档，包含:
  - `title`: 需求标题
  - `background`: 需求背景
  - `functional_requirements`: 功能需求列表
  - `non_functional_requirements`: 非功能需求列表
  - `user_stories`: 用户故事列表
  - `acceptance_criteria`: 验收标准
  - `priority`: 优先级 (P0/P1/P2/P3)
  - `complexity`: 复杂度评估
