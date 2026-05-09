---
id: test_generation
name: test-generation
description: "根据需求和代码生成测试用例，支持单元测试、集成测试和 E2E 测试。"
version: 1.0.0
category: testing
agent_type: QA
metadata:
  hermes:
    tags: [testing, test-cases, unit-test, integration-test]
    related_skills: [code-review, backend-development, frontend-development]
---

# 测试用例生成

## When to Use
- 需要为新功能生成测试用例
- 需要对已有代码补充测试覆盖
- 需要生成 E2E 测试场景

## Instructions
1. 接收需求描述和待测代码
2. 分析代码功能和输入输出
3. 生成正向测试用例（Happy Path）
4. 生成边界条件测试用例
5. 生成异常情况测试用例
6. 覆盖安全测试场景
7. 输出结构化测试用例文档

## Input
- `requirement` (string, required): 需求描述
- `code` (string, optional): 待测代码内容
- `session_id` (string, optional): 会话 ID

## Output
- `test_cases` (array): 测试用例列表，每个用例包含:
  - `case_id`: 用例编号
  - `title`: 用例标题
  - `type`: 测试类型 (unit/integration/e2e)
  - `preconditions`: 前置条件
  - `steps`: 测试步骤
  - `expected_result`: 预期结果
  - `priority`: 优先级 (P0/P1/P2)
