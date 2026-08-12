# Agent Evaluation Implementation Status

Updated: 2026-08-12

This file prevents a service skeleton from being mistaken for a completed security boundary.

## Implemented and testable now

- Security threat model, boundary ADR, G0/G1 acceptance checklist, permission matrix, and hard prohibitions.
- PostgreSQL control-plane schema with tenant RLS, immutable started experiments, append-only human reviews, dual approval constraints, idempotency keys, and soft-archive fields.
- `admin-eval` authenticated control API for Agent, versioned dataset and experiment metadata.
- Dataset JSON/JSONL import, bounded Case validation, PII/credential scanning, exact duplicate rejection, source-family split leakage prevention, legacy Pipeline Golden conversion, DRAFT-only editing, append-only two-person review, immutable publish and published-version cloning.
- HIDDEN Case redaction on ordinary list APIs; full author/reviewer reads use separate permission paths and generate audit records. Hidden-set download remains unavailable.
- Gateway RBAC route and trusted-header reconstruction; caller-supplied tenant/admin/internal headers are removed. A single explicit dispatcher preserves legacy Pipeline Golden/metrics routes while allowlisting Agent control-plane paths.
- Fixed Kata Job, ConfigMap, and NetworkPolicy generation with digest/registry/resource/tool-scope validation.
- Registered-destination egress proxy with Trial-token audience/scope/expiry checks, DNS and connect-time IP validation, redirect denial, body limits, and Redis atomic budgets.
- Deterministic score ordering, security hard gate, cost missing-value semantics, Wilson interval, exact paired McNemar, stratified bootstrap, Holm adjustment, Pareto frontier, paired randomized scheduling, and blind A/B order proof.
- React pages for Agent intake, dataset Case import/edit, legacy Golden import, review/publish/version workflow, experiments, review boundary, and security boundary.
- Local-only Kafka, ClickHouse, MinIO, OTel, and Vault integration configuration.

## Deliberately fail-closed

- `EVAL_EXECUTION_ENABLED`, `SANDBOX_EXECUTION_ENABLED`, and `EGRESS_EXECUTION_ENABLED` default to false.
- The sandbox `/execute` endpoint does not mutate Kubernetes yet; it returns a locked/not-installed response.
- Egress cannot open without an approval reference and reachable Redis atomic budget ledger.
- No production-write tool registration exists.
- No hidden-set export or raw artifact download endpoint exists.

## Required before G1

- Implement the controller Kubernetes deployment adapter using the namespace-scoped Role, plus create/rollback/teardown proof.
- Integrate registry vulnerability scanning and signature admission, with evidence keyed by image digest.
- Implement short-lived Trial-token issuance/revocation and kill-switch propagation.
- Implement artifact upload proxy, canonical path/symlink checks, secret scan, malware scan, quarantine, and bounded MinIO upload.
- Prove CNI NetworkPolicy enforcement, node-level routing deny, Kata isolation, per-Pod PID enforcement, and all G1 attack cases in the dedicated security cluster.

## Required before G2/G3

- Kafka workers, ClickHouse writer/replay, scoring workers, judge namespace, human-review assignment/arbitration, and Trial evidence drill-down.
- Vault production auth and rotation; provider usage reconciliation.
- Full fault-injection, 500-sandbox concurrency, 100k-Trial/day load, cancel/kill-switch SLO tests.
- Security operations runbook, alert routing, on-call training, and signed G0/G1/G2/G3 approvals.

Until those items pass, this repository contains a secure control-plane foundation, not a production-ready untrusted-code evaluation platform.
