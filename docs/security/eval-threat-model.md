# Agent Evaluation Threat Model

Status: `DRAFT - G0 NOT APPROVED`

This document defines the security model for the Agent evaluation subsystem. External Agent execution must remain disabled until G0 is approved and the G1 sandbox tests pass.

## Protected assets

- Tenant data and identity context.
- Hidden evaluation cases, expected state, rubrics, and judge prompts.
- Model, tool, registry, object storage, and platform credentials.
- Kubernetes nodes, API server, control plane services, and other Trial workloads.
- Evaluation evidence, cost ledger, scores, and audit records.

## Trust boundaries

1. The existing Gateway authenticates the user and derives `tenant_id`; callers cannot supply it in a request body.
2. `admin-eval` is control plane only. It does not receive Kubernetes credentials.
3. `admin-sandbox-controller` accepts a signed `TrialExecutionSpec` and creates only platform-owned templates in evaluation namespaces.
4. Agent workloads have no Kubernetes service account token and can reach only internal proxies.
5. Model, tool, remote Agent, telemetry, and artifact traffic passes through dedicated proxies.
6. Evaluators run only after the Agent sandbox is destroyed and never share Agent credentials or writable state.

## Threats and mandatory controls

| Threat | Mandatory control | Failure action |
|---|---|---|
| Container escape or host access | Kata runtime, Restricted Pod Security, no host namespaces/mounts, non-root, seccomp, AppArmor, drop all capabilities | Terminate Trial and revoke token |
| SSRF and metadata access | Registered destinations only, DNS and resolved-IP validation, redirect disabled, RFC1918/link-local deny | Deny request and emit security event |
| Cross-tenant access | Gateway-derived tenant, tenant-scoped queries, PostgreSQL RLS, scoped Trial token | Return 403 and emit security event |
| Hidden set extraction | One Case per Trial, random external Case ID, expected state and rubric stored outside Agent namespace | Terminate Trial on probing |
| Prompt injection/tool abuse | Schema-validated tool calls, explicit scopes, read/mock/sandbox-write modes only | Deny tool call; severe events terminate Trial |
| Resource exhaustion | CPU, memory, PID, ephemeral storage, log, artifact, time, model and tool-call budgets | Kill workload and classify separately |
| Credential theft/replay | Short-lived audience-bound Trial tokens, secrets held by proxies, immediate revocation | Return 401, revoke Trial, emit event |
| Malicious artifacts | Canonical path validation, no symlink traversal, size/type limits, secret and malware scanning | Reject artifact and quarantine evidence |
| Judge prompt injection | Treat Agent output as quoted data, no judge tools, versioned rubric, deterministic checks first | Preserve deterministic score; flag review |

## Risk classification

- `LOW`: text-only remote API without tools. Isolation scope is still `RUNNER_ONLY`.
- `MEDIUM`: controlled read-only or mock tools.
- `HIGH`: third-party code, browser automation, or multi-tool Agent. Kata and G1 are mandatory.
- `PROHIBITED`: host access, production credentials, privileged execution, arbitrary network access, or production writes.

## Hard prohibitions

The API and policy types intentionally do not expose privileged containers, host paths, host network/PID/IPC, custom service accounts, custom runtime classes, added capabilities, arbitrary Pod YAML, arbitrary URLs, or production-write tools. These are code-level constraints, not feature flags.

## Approval gates

- **G0**: threat model, boundary ADR, permission matrix, prohibited capability list, and acceptance checklist approved.
- **G1**: sandbox attack suite passes; external Agent execution may then be enabled in a dedicated security cluster.
- **G2**: security, failure-recovery, and load tests pass without unresolved Critical/High findings.
- **G3**: operational rehearsal, auditability, reproducibility, credential isolation, and teardown proof pass.
