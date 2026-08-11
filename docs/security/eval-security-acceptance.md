# Agent Evaluation Security Acceptance Checklist

Every item requires evidence linked to a build, image digest, policy version, and test run. A checkbox without evidence is not acceptance.

## G0 - design approval

- [ ] Product owner approves offline-only v1 scope.
- [ ] Security approves the threat model and prohibited capabilities.
- [ ] Platform owner approves namespace, RBAC, NetworkPolicy, RuntimeClass, and registry boundaries.
- [ ] Data owner approves de-identification and hidden-set access workflow.
- [ ] Cost owner approves per-Trial and per-experiment hard budgets.
- [ ] Two-person approval is implemented for hidden-set export, high-risk policy, and raw artifact download.

## G1 - sandbox boundary

- [ ] Host `/proc` and `/sys` access is blocked.
- [ ] Docker/containerd sockets and host paths are absent.
- [ ] ServiceAccount token and Kubernetes API access are blocked.
- [ ] Privilege escalation, capabilities, host network/PID/IPC are blocked.
- [ ] Fork bomb, PID exhaustion, memory, disk, log, and timeout limits terminate the Trial.
- [ ] Public internet, cloud metadata, RFC1918, cluster DNS abuse, and cross-Trial traffic are blocked.
- [ ] Image digest, vulnerability threshold, and signature verification fail closed.
- [ ] Teardown removes workload, policy, service, and temporary volume; residual resources alert and are never reused.

## Data and evaluator boundary

- [ ] Only the current Case is injected.
- [ ] Expected state, rubric, judge prompt, and hidden metadata are absent from the Agent Pod.
- [ ] Artifact paths are canonicalized and symlinks cannot escape the collection root.
- [ ] Artifacts are size/type checked, secret scanned, malware scanned, and quarantined on failure.
- [ ] Evaluator runs after sandbox destruction in a separate namespace and has no tools.
- [ ] Agent output is delimited as untrusted evidence in judge prompts.

## Runtime and incident handling

- [ ] Expired, replayed, cross-tenant, wrong-audience, and over-budget tokens fail closed.
- [ ] Kill switch revokes all Trial tokens and blocks proxy access within 60 seconds.
- [ ] Cancel stops all related resources within 30 seconds.
- [ ] `SECURITY_TERMINATED` is never retried.
- [ ] Security events cannot be diluted into ordinary failure metrics.
- [ ] No production credential appears in environment variables, logs, traces, database, or artifacts.
