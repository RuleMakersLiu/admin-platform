---
id: contract_prober
name: contract-prober
description: "活契约探针（4c）：对运行中的后端 backend_runner 发 HTTP 探针，按契约三层断言（status<400 / JSON / result.list 或 detail dict）校验接口是否真起、真响应。后端未就绪 fail-open。"
version: 1.0.0
category: testing
agent_type: SYSTEM
metadata:
  hermes:
    tags: [backend, contract, probe, sandbox, http, code-review, pipeline]
    related_skills: [code-review, real-frontend-preview]
---

# Contract Prober（活契约探针）

SYSTEM 类 skill（纯 Python，不调 LLM）。由流水线 `code_review` 阶段在「起后端」后自动调用，对 `backend_runner_service` 真实起服务的 Java 后端逐个探针 delivery 的 `endpoints[]`，把契约不一致写回 review 结果、自动触发既有 fix-loop。

## 工作方式

1. 取 `backend_runner_service.direct_backend_url(pipeline_id)`（调用即刷新 `last_active`，防被后台 reaper 回收）；后端未就绪 → 返回 `skipped`（fail-open，不判失败、不误触发 fix-loop）。
2. 对每个 endpoint（`path` / `method` / `expects_list`）发 HTTP，三层断言（抽自历史死代码 `_smoke_test_generated_apis`）：
   - HTTP status < 400
   - Content-Type 含 `application/json`
   - list 类接口（`expects_list=true`）要返回 `result.list` 数组；detail 类要返回对象
3. path SSRF 防护：拒绝 `://` / `..` / `@` / 空格。
4. 返回 `{passed, skipped, results:[{path,method,status,ok,issue}], summary}`。

## 触发位置

`flow_manager._execute_stage_skill` 的 `code_review` 分支：full 模式（workspace 有 pom.xml）→ 起后端 → 探针 → 未过则追加 `field_mismatches` 并置 `review_passed=False`，自然命中既有 code_review fix-loop（重试生成）。

## 适用范围

- **full 模式**（含 `backend_dev`）：后端是 pipeline 产物，起后探针。
- **frontend_contract_review 模式**（无 `backend_dev`）：无后端可起，fail-open 跳过探针；但仍享受 delivery `endpoints[]` 结构化。该模式要支持活探针需 clone 参考后端项目（长期方案）。

## 安全

- env 隔离：探针进程走 `sanitized_env`，不继承 admin 凭据。
- path 校验防 SSRF。
- 后端沙箱 DB 权限隔离（per-pipeline 库，sandbox user 无 FILE/SHUTDOWN 全局权）。
