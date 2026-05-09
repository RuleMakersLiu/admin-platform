---
id: knowledge_search
name: knowledge-search
description: "搜索本地知识库获取相关信息，支持按类别和关键词检索。"
version: 1.0.0
category: knowledge
agent_type: SYSTEM
metadata:
  hermes:
    tags: [knowledge, search, retrieval, rag]
    related_skills: [ai-upgrade-check]
---

# 知识库搜索

## When to Use
- 需要从知识库中检索相关信息
- 需要查找特定技术文档或最佳实践
- Agent 需要获取上下文知识来辅助决策

## Instructions
1. 接收搜索查询和可选的类别过滤
2. 在知识库中执行语义搜索
3. 返回最相关的结果（默认 top 5）
4. 结果包含内容摘要和来源引用

## Input
- `query` (string, required): 搜索查询关键词
- `category` (string, optional): 知识类别过滤
- `session_id` (string, optional): 会话 ID

## Output
- `results` (array): 搜索结果列表，每项包含:
  - `content`: 匹配的知识内容
  - `source`: 来源引用
  - `relevance_score`: 相关度评分
  - `category`: 知识类别
