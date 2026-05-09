---
id: backend_development
name: backend-development
description: "根据需求生成后端代码，包括 API 接口、数据库模型、业务逻辑层，支持多种技术栈。"
version: 1.0.0
category: development
agent_type: BE
metadata:
  hermes:
    tags: [backend, code-generation, api, database]
    related_skills: [requirement-analysis, task-breakdown, code-review]
---

# 后端开发

## When to Use
- 需要根据需求生成后端 API 代码
- 需要创建数据库模型和迁移脚本
- 需要实现业务逻辑层代码

## Instructions
1. 接收需求描述和 API 契约（如有）
2. 分析技术栈要求（Spring Boot / FastAPI / Gin / Laravel）
3. 生成数据库模型（Entity/Model）
4. 生成 API 接口（Controller/Router）
5. 生成业务逻辑层（Service）
6. 生成数据访问层（Repository/DAO）
7. 确保代码符合项目规范（多租户、时间戳 BIGINT 毫秒等）

## Input
- `requirement` (string, required): 需求描述
- `api_contract` (string, optional): API 契约定义（OpenAPI 格式）
- `session_id` (string, optional): 会话 ID

## Output
- `code` (object): 生成的代码文件集合，包含:
  - `model`: 数据模型代码
  - `controller`: API 控制器代码
  - `service`: 业务逻辑代码
  - `repository`: 数据访问层代码
  - `migration`: 数据库迁移脚本（如适用）
