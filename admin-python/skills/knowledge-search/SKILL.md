---
id: knowledge_search
name: knowledge-search
description: "Search local knowledge base with semantic search and keyword matching for AI Agent context engineering. 搜索本地知识库获取相关信息，结合语义搜索和关键词匹配，为 AI Agent 提供上下文工程支持。"
version: 1.1.0
category: knowledge
agent_type: SYSTEM
metadata:
  hermes:
    tags: [knowledge, search, retrieval, rag, context-engineering, bm25]
    related_skills: [ai-upgrade-check]
---

# 知识库搜索

## 概述

为 AI Agent 提供项目上下文的知识检索能力。在流水线执行过程中，Agent 通过此技能获取：
- 项目架构信息（语言、框架、数据库、API 规范）
- 技术决策和约定（命名规范、分层模式、权限模型）
- 代码摘要和关键文件说明
- 依赖关系和集成点

## 上下文工程策略

### 语义检索 (Semantic Search)

采用 BM25 变体算法，结合以下加权因子：

1. **关键词匹配** (Jaccard Similarity)
   - 查询词与知识条目的关键词集合交集
   - 公式: `J(A,B) = |A∩B| / |A∪B|`

2. **逆文档频率** (IDF Weighting)
   - 常见词降低权重，稀有词提升权重
   - 减少通用术语的干扰

3. **类别相关性** (Category Boost)
   - 如果查询指定了类别，该类别的条目获得加权
   - 类别: architecture, api, database, security, convention, integration

### 上下文注入 (Context Injection)

检索到的知识按以下模板注入 Agent prompt：

```
## 项目上下文

### 架构概述
{project.architecture_summary}

### 技术栈
- 语言: {project.language}
- 框架: {project.framework}
- 数据库: {project.database}

### 相关知识
{for each relevant result:}
#### {result.title} ({result.category})
{result.content}

### 代码摘要
{for each relevant code summary:}
- `{summary.file_path}`: {summary.summary}
```

## 搜索流程

### 第一步：解析查询意图

分析用户查询中的：
- 技术关键词（框架名、类名、方法名）
- 概念关键词（"认证"、"分页"、"多租户"）
- 类别暗示（"数据库" → database, "API" → api）

### 第二步：执行搜索

```python
# 伪代码
results = knowledge_service.semantic_search(
    query=user_query,
    category=optional_category,
    limit=5
)
```

搜索范围：
1. `agent_knowledge` 表 - 结构化知识条目
2. `agent_code_summary` 表 - 代码文件摘要
3. 项目级知识 - 架构信息、技术栈、约定

### 第三步：结果排序和截断

- 按 BM25 相关性分数降序
- 截断到 top 5 条结果
- 每条结果包含：标题、类别、内容、相关性分数

### 第四步：格式化输出

将结果格式化为结构化文本，便于 Agent 理解：

```
搜索结果 (共 {total} 条，显示 {count} 条):

1. [architecture] 项目分层架构
   项目采用经典的分层架构: Controller → Service → Repository...
   相关度: 0.92

2. [convention] API 命名规范
   RESTful 风格，资源名用复数形式，操作用 HTTP 方法表示...
   相关度: 0.85
```

## 知识库内容结构

### 知识类别

| 类别 | 说明 | 示例 |
|------|------|------|
| architecture | 架构设计和分层模式 | 前后端分离、微服务架构 |
| api | API 规范和约定 | RESTful、错误码、分页 |
| database | 数据库设计和规范 | 表命名、索引策略、迁移 |
| security | 安全相关 | 认证流程、权限模型、加密 |
| convention | 编码约定 | 命名规范、注释规范、Git 规范 |
| integration | 集成和依赖 | 第三方服务、中间件、部署 |

### 知识条目格式

```json
{
  "title": "API 命名规范",
  "category": "convention",
  "content": "RESTful 风格...",
  "tags": ["api", "rest", "naming"],
  "source": "project_analysis",
  "project_id": "xxx"
}
```

## 使用指南

### Agent 使用示例

在流水线执行中，Agent 自动调用知识搜索：

```
场景: 后端开发 Agent 需要生成用户管理 API
1. 自动搜索: "用户 认证 API" → 获取项目认证规范
2. 自动搜索: "数据库 多租户" → 获取多租户数据隔离规则
3. 自动搜索: "API 响应格式" → 获取统一响应格式规范
4. 将搜索结果注入代码生成的 prompt 上下文
5. 生成的代码自动遵循项目约定
```

### 直接查询示例

```
输入: "这个项目怎么处理分页的？"
→ 搜索: "分页 pagination"
→ 返回: 项目的分页规范和实现示例

输入: "权限是怎么做的？"
→ 搜索: "权限 认证 RBAC 角色"
→ 返回: 权限模型和 RBAC 实现说明
```

## 输出格式

```json
{
  "results": [
    {
      "id": "know_xxx",
      "title": "API 命名规范",
      "category": "convention",
      "content": "...",
      "tags": ["api", "rest"],
      "relevance_score": 0.92,
      "source": "project_analysis"
    }
  ],
  "total": 15,
  "query": "用户查询内容",
  "context_text": "格式化后的完整上下文文本，可直接注入 prompt"
}
```

## 最佳实践

1. **查询优化**: 使用项目相关的技术术语而非自然语言
2. **类别过滤**: 明确指定类别可大幅提升结果相关性
3. **结果数量**: 默认 top 5，复杂查询可请求 top 10
4. **上下文截断**: 注入 prompt 时注意 token 限制，优先保留高相关度结果
5. **定期更新**: 项目代码变化后重新分析更新知识库

## 反模式

- 使用过于通用的查询词（如 "代码"、"功能"）
- 忽略类别过滤导致结果不相关
- 不检查返回结果的时效性（知识可能过时）
- 过度依赖知识库而忽略当前任务的具体需求
