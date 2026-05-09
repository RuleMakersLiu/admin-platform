---
id: code_review
name: code-review
description: "审查代码质量、安全性和最佳实践，提供改进建议和修复方案。"
version: 1.0.0
category: testing
agent_type: QA
metadata:
  hermes:
    tags: [code-review, quality, security, best-practices]
    related_skills: [backend-development, frontend-development, test-generation]
---

# 代码审查

## When to Use
- 提交代码前需要进行质量审查
- 需要检查代码中的安全隐患
- 需要验证代码是否符合项目规范
- Code Review 流程中的自动化审查环节

## Instructions
1. 接收待审查的代码和对应的需求描述
2. 检查代码质量（命名规范、代码结构、可读性）
3. 检查安全性问题（SQL 注入、XSS、敏感信息泄露等）
4. 检查是否遵循项目最佳实践
5. 检查错误处理和边界情况
6. 输出审查结果和改进建议

## Input
- `code` (string, required): 待审查的代码内容
- `requirement` (string, optional): 对应的需求描述，用于上下文参考
- `session_id` (string, optional): 会话 ID

## Output
- `review_result` (object): 审查结果，包含:
  - `score`: 代码质量评分 (0-100)
  - `issues`: 发现的问题列表
  - `suggestions`: 改进建议列表
  - `security_issues`: 安全问题列表
  - `summary`: 审查总结
