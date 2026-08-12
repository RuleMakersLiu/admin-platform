# Agent Evaluation Developer Guide

The first delivery is a fail-closed control-plane foundation. Read [implementation-status.md](./implementation-status.md) before deployment; do not interpret generated Kata YAML as G1 evidence.

## Components

- `admin-eval` (`8091`): tenant-scoped metadata, experiment gate, deterministic scoring/statistics/review domain.
- `admin-sandbox-controller` (`8092`): signed spec validation and fixed Kata resource planning. Kubernetes mutation is intentionally unavailable before G1.
- `admin-egress-gateway` (`8093`): registered model/tool/remote-Agent destinations, scoped Trial tokens, SSRF protection, Vault-file credentials, and Redis atomic budgets.
- Existing `admin-gateway`: `/api/eval/*` JWT/RBAC entry point; reconstructs identity headers and adds the internal service token.
- Existing React frontend: `/evaluation/*` pages.

## Safe local verification

Local verification does not run Agent code:

```text
cd admin-eval
set PYTHONPATH=%CD%
python -m pytest tests -q

cd admin-sandbox-controller
go test ./...

cd admin-egress-gateway
go test ./...

cd admin-frontend
npm run build

docker compose -f docker/docker-compose.eval.yml config --quiet
```

## Local startup script

`./start.sh all` now starts the local evaluation infrastructure plus `admin-eval`, `admin-sandbox-controller`, and `admin-egress-gateway`. It generates an ephemeral shared internal token for Gateway and `admin-eval`, but always overrides all execution gates to `false`.

Database changes remain explicit:

```text
./start.sh eval-migrate
./start.sh all
```

The migration action applies `006`, legacy Golden table `009`, and dataset workflow `018` with `ON_ERROR_STOP=1`. It does not run automatically during `all`, so startup cannot silently modify a database. Individual service actions are `eval`, `sandbox-controller`, `egress`, and `eval-infra`. A standalone `eval` requires an explicitly supplied `EVAL_INTERNAL_SERVICE_TOKEN` shared with the Gateway.

Apply `database/migrations/006_agent_evaluation_platform.up.sql` and then `database/migrations/018_agent_eval_dataset_workflow.up.sql` using the project's controlled migration process. Apply `009_eval_golden_case.up.sql` before using legacy Pipeline Golden import. The application database role must not be a PostgreSQL superuser, otherwise RLS is not an effective tenant boundary.

## Dataset and Golden workflow

1. Open `/evaluation/datasets` and create a dataset. Version 1 starts as `DRAFT`.
2. Open **Manage Cases** and import a JSON array or JSONL. Start from [dataset-case-template.jsonl](./dataset-case-template.jsonl).
3. Run **Validate only** before importing. PII/credential patterns, prohibited tool side effects, invalid budgets, duplicate content and missing deterministic checks are rejected.
4. Optionally import enabled legacy Pipeline Golden cases. The converter removes `reference_output` from Agent input and keeps it evaluator-side.
5. Edit cases while the version is `DRAFT`. Database triggers reject case mutation after review starts.
6. Submit review. Release validation requires both `REGRESSION` and `HIDDEN` splits and rejects one source family crossing splits.
7. Two distinct reviewers other than the dataset creator must approve the same review round.
8. Publish the version. Its content hash and case count are frozen; create the next version by cloning the published version.

Normal case-list responses redact all HIDDEN inputs, fixtures, expected state, rubric, tool policy, budget, deterministic checks and prohibited-behavior details. Full hidden evidence is available only through the dataset-review permission path and every such read is audited. There is no hidden-set download endpoint.

The public `/api/eval/*` route is dispatched by an explicit allowlist: Agent control-plane paths go to `admin-eval`; legacy `/eval/golden-cases` and `/eval/metrics` remain on `admin-python`.

## Required secrets and gates

- Gateway and `admin-eval` share `EVAL_INTERNAL_SERVICE_TOKEN` (minimum 32 random characters).
- Sandbox specs use `SANDBOX_SPEC_SIGNING_KEY` (minimum 32 random characters).
- Egress Trial tokens use `EGRESS_TRIAL_SIGNING_KEY` (minimum 32 random characters).
- Provider credentials are rendered by Vault Agent into memory-backed files; only file paths are configured.
- Never store these values in YAML, `.env`, PostgreSQL, logs, traces, or images.

The three execution switches ship as false. An approval reference is an additional deployment gate, not proof by itself. G0/G1 evidence and security-cluster admission remain mandatory.

## References

- [Kata Containers](https://katacontainers.io/)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [OWASP Agentic AI threats and mitigations](https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/)
