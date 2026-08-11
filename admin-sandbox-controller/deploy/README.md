# Sandbox deployment prerequisites

These manifests are a baseline, not proof of G1 acceptance.

Before enabling execution, platform and security owners must verify:

1. `RuntimeClass/kata` is installed on dedicated evaluation nodes and Kata hardware virtualization is active.
2. The CNI enforces ingress and egress NetworkPolicy; policy objects without enforcement do not count.
3. Kubelet/container runtime PID limits are configured and the fork-bomb G1 test proves enforcement. Kubernetes Pod specs do not provide a portable per-Pod `pids.max` field.
4. Admission verifies internal registry, SHA256 digest, vulnerability policy, and Sigstore signature. Controller validation alone is not sufficient.
5. Evaluation nodes cannot route to production networks, cloud metadata, Kubernetes control plane, or node management interfaces even if a NetworkPolicy fails.
6. `agent-eval-proxy` is a separately restricted namespace; only the registered proxy Pods use `eval.platform/proxy=true`.
7. The controller Role is namespace-scoped and cannot create Secrets, Roles, RoleBindings, Services, RuntimeClasses, or arbitrary namespaces.
8. Teardown verification and the kill-switch exercise have evidence attached to the G1 approval.

The controller's `/execute` endpoint remains fail-closed until the deployment adapter and all items above are approved.
