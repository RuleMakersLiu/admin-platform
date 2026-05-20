---
id: progress_report
name: progress-report
description: "Generate project progress reports with task completion, milestone status, and risk analysis. 生成项目进度总结报告，包含任务完成情况、里程碑状态和风险分析。支持日报、周报、里程碑报告等多种格式。"
version: 1.1.0
category: report
agent_type: RPT
metadata:
  hermes:
    tags: [report, progress, summary, milestone, risk-analysis, daily-report]
    related_skills: [task-breakdown, requirement-analysis]
---

# 进度报告

## 概述

在 AI 开发流水线的每个阶段完成后，自动生成结构化的进度报告。报告包含：
- 整体进度百分比和阶段状态
- 各角色（PM/PJM/BE/FE/QA）任务完成情况
- 代码产出统计（文件数、代码行数、语言分布）
- 风险项和阻塞问题
- 下一步行动计划

## 报告类型

### 日报 (Daily Report)

流水线执行过程中的即时状态报告：

```
# 流水线进度日报 - {date}

## 基本信息
- 流水线 ID: pipe_xxx
- 需求概述: {user_request_summary}
- 启动时间: {start_time}
- 当前阶段: {current_stage}

## 阶段完成情况
| 阶段 | 状态 | 耗时 | Agent |
|------|------|------|-------|
| 需求分析 | ✅ 完成 | 45s | PM |
| 页面设计 | ✅ 完成 | 30s | FE |
| 原型预览 | ✅ 完成 | 60s | FE |
| 交付包 | ✅ 完成 | 25s | PJM |
| 前端开发 | 🔄 进行中 | - | FE |
| 后端开发 | 🔄 进行中 | - | BE |
| 代码审查 | ⏳ 待开始 | - | QA |
| 测试 | ⏳ 待开始 | - | QA |

## 代码产出统计
- 总文件数: {file_count}
- 代码行数: {line_count}
- 语言分布: Java 60%, Vue 30%, SQL 10%

## 风险项
- 无

## 下一步
- 等待前端开发和后端开发完成
- 进入代码审查阶段
```

### 阶段报告 (Stage Report)

每个阶段完成后的详细报告：

```
# {stage_name} 阶段报告

## 阶段概述
- 执行 Agent: {agent_type}
- 开始时间: {start_time}
- 结束时间: {end_time}
- 执行耗时: {duration_ms}ms

## 产出物
{列出本阶段产出的所有文件和内容}

## 质量指标
- 代码文件数: {count}
- 通过/未通过审查: {pass}/{fail}
- 测试覆盖率: {coverage}%

## 问题和备注
{记录发现的问题和特殊处理}
```

### 里程碑报告 (Milestone Report)

流水线完成后的最终汇总：

```
# 项目完成报告

## 项目概述
- 需求: {user_request}
- 开始时间: {create_time}
- 完成时间: {complete_time}
- 总耗时: {total_duration}

## 交付清单
### 前端文件
{列出所有前端文件及路径}

### 后端文件
{列出所有后端文件及路径}

### 测试文件
{列出所有测试文件及路径}

### 数据库变更
{列出所有 SQL 变更}

## 质量报告
- 代码审查结果: {pass/fail}
- 审查轮次: {rounds}
- 测试用例数: {test_count}
- 测试通过率: {pass_rate}%

## AI Agent 协作记录
| Agent | 阶段 | 执行次数 | 产出 |
|-------|------|---------|------|
| PM | requirement | 1 | 需求文档 |
| PJM | delivery | 1 | 交付包 + API 契约 |
| FE | frontend_dev | 1 | 3 个 Vue 组件 |
| BE | backend_dev | 1 | 4 个 Java 类 |
| QA | code_review | 2 | 审查报告 + 修复建议 |
| QA | testing | 1 | 12 个测试用例 |

## 风险回顾
{记录整个过程中遇到的风险和解决方式}
```

## 报告生成流程

### 第一步：收集数据

从流水线状态中收集：
- `pipeline.stages` - 各阶段状态和结果
- `pipeline.code_files` - 代码产出
- `pipeline.errors` - 错误记录
- `pipeline.logs` - 执行日志

### 第二步：统计分析

```python
# 计算指标
total_stages = len(stages)
completed = sum(1 for s in stages.values() if s["status"] == "completed")
progress_pct = (completed / total_stages) * 100

# 代码统计
file_count = len(code_files)
line_count = sum(len(f["content"].splitlines()) for f in code_files)
languages = Counter(f["language"] for f in code_files)
```

### 第三步：生成报告

根据报告类型选择模板，填充数据，生成 Markdown 格式报告。

### 第四步：风险评估

自动识别以下风险：
- **延期风险**: 某阶段执行时间超过预估的 200%
- **质量风险**: 代码审查失败超过 2 轮
- **阻塞风险**: 依赖的前序阶段未完成
- **技术风险**: 使用了项目知识库中标记为高风险的技术

## 输出格式

```json
{
  "report": {
    "type": "daily|stage|milestone",
    "pipeline_id": "pipe_xxx",
    "timestamp": 1234567890000,
    "progress": {
      "percentage": 65,
      "current_stage": "code_review",
      "completed_stages": ["requirement", "prototype", "delivery", "frontend_dev", "backend_dev"],
      "pending_stages": ["testing", "commit"]
    },
    "statistics": {
      "total_files": 12,
      "total_lines": 850,
      "languages": {"java": 500, "vue": 300, "sql": 50},
      "stages_completed": 5,
      "stages_total": 8
    },
    "risks": [
      {"level": "medium", "description": "后端开发耗时较长", "suggestion": "考虑拆分为更小的任务"}
    ],
    "next_actions": ["执行代码审查", "修复审查发现的问题"]
  }
}
```

## 最佳实践

1. **实时更新**: 每个阶段完成即生成报告，不等流水线全部结束
2. **数据驱动**: 所有结论基于实际数据，不做主观推测
3. **可操作**: 风险项必须附带建议的解决方案
4. **简洁明了**: 日报不超过一屏，里程碑报告不超过 3 屏
5. **中文输出**: 面向中文用户，技术术语保留英文

## 反模式

- 报告内容过于冗长，淹没了关键信息
- 只报喜不报忧，隐藏风险和问题
- 缺少数据支撑的进度评估
- 忽略 Agent 协作记录，不利于后续优化
- 报告格式不统一，难以对比不同流水线的进展
