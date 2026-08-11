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

Apply `database/migrations/006_agent_evaluation_platform.up.sql` using the project's controlled migration process. The application database role must not be a PostgreSQL superuser, otherwise RLS is not an effective tenant boundary.

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
