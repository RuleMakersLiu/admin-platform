# ADR: Agent Evaluation Security Boundary

Decision status: `PROPOSED`

## Decision

The platform uses three separately deployable services:

- `admin-eval` owns metadata, experiment state, scoring orchestration, review, and reports. It has no Kubernetes permission.
- `admin-sandbox-controller` validates a narrow execution specification and creates only fixed Kata Job templates.
- `admin-egress-gateway` owns model/tool/remote-Agent credentials, destination policy, budgets, audit, and cost events.

Production evaluation uses Kubernetes with Kata Containers. The existing Docker implementation remains a local functional test utility and is not a security boundary.

## Non-negotiable boundaries

- All sandbox ingress and egress are denied by default.
- Agent Pods have `automountServiceAccountToken: false`.
- Images are internal-registry, digest-pinned, scanned, and signature-verified before execution.
- A Trial receives exactly one Case and short-lived Trial credentials.
- Agent workloads never receive provider, Vault, MinIO, judge, or long-lived platform credentials.
- Production databases, caches, queues, tools, and write actions are outside the evaluation data plane.
- Remote HTTP Agents are reported as `RUNNER_ONLY`; the platform does not claim to isolate remote infrastructure.
- A security termination is never automatically retried.

## Permission matrix

| Role | Allowed | Explicitly denied |
|---|---|---|
| Evaluation viewer | View Agents, experiments, reports, permitted artifacts | Create/run/cancel, hidden set, raw sensitive artifacts |
| Dataset editor | Create draft cases and datasets | Publish own hidden case without independent review |
| Experiment operator | Create/run approved experiments, cancel own tenant Trials | Change sandbox policy, security unlock, production tools |
| Reviewer | Submit append-only blind review | Agent identity/cost before review, raw artifact download |
| Arbiter | Add correction/arbitration record | Rewrite original review |
| Security administrator | Approve high-risk versions, kill switch, hidden-set dual approval | Bypass hard sandbox constraints |
| Sandbox controller | Create/delete fixed resources in eval namespaces | Secrets, arbitrary Pods, cluster-wide resources |
| Egress gateway | Resolve secret refs and proxy approved destinations | Expose credentials or arbitrary URL proxying |

## Operational default

`EVAL_EXECUTION_ENABLED=false` and `SANDBOX_EXECUTION_ENABLED=false` are the shipped defaults. Enabling either does not override G0/G1; deployment admission must also provide an approved gate reference.
