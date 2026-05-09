---
id: ai_upgrade_check
name: ai-upgrade-check
description: "检查最新的AI技术趋势并进行系统升级分析，生成技术升级建议报告。"
version: 1.0.0
category: knowledge
agent_type: SYSTEM
metadata:
  hermes:
    tags: [ai, upgrade, technology, analysis]
    related_skills: [knowledge-search]
---

# AI技术升级检查

## When to Use
- 需要定期检查 AI 技术栈的最新动态
- 需要评估当前系统是否需要技术升级
- 需要了解新发布的 AI 模型或工具

## Instructions
1. 收集当前系统使用的 AI 技术栈信息
2. 查询最新的 AI 技术趋势和发布动态
3. 对比当前版本和最新版本
4. 评估升级的必要性和风险
5. 生成升级建议报告

## Input
- 无必填输入参数（自动获取系统当前配置）

## Output
- `upgrade_report` (object): 升级分析报告，包含:
  - `current_stack`: 当前技术栈版本
  - `latest_versions`: 最新版本信息
  - `upgrade_recommendations`: 升级建议列表
  - `risk_assessment`: 风险评估
  - `action_items`: 行动项清单
