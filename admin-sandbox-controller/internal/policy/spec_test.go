package policy

import "testing"

func validSpec() TrialExecutionSpec {
	return TrialExecutionSpec{
		TenantID:       1,
		TrialID:        "11111111-1111-1111-1111-111111111111",
		AttemptNo:      1,
		ImageDigest:    "registry.local/eval/agent@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		CaseExternalID: "22222222-2222-2222-2222-222222222222",
		CaseInput:      map[string]interface{}{"prompt": "test"},
		Policy: SandboxPolicy{
			CPUMillis: 2000, MemoryMB: 2048, PIDsMax: 256, TimeoutSeconds: 600,
			EphemeralStorageMB: 4096, MaxLogBytes: 10485760, MaxArtifactBytes: 104857600,
			MaxToolCalls: 50, MaxModelCost: 5, NetworkPolicy: NetworkPolicyName,
		},
	}
}

func TestValidSpec(t *testing.T) {
	if err := validSpec().Validate("registry.local"); err != nil {
		t.Fatal(err)
	}
}

func TestMutableTagRejected(t *testing.T) {
	spec := validSpec()
	spec.ImageDigest = "registry.local/eval/agent:latest"
	if err := spec.Validate("registry.local"); err == nil {
		t.Fatal("expected mutable tag rejection")
	}
}

func TestProductionScopeRejected(t *testing.T) {
	spec := validSpec()
	spec.Policy.ToolScopes = []string{"PRODUCTION_WRITE:refund"}
	if err := spec.Validate("registry.local"); err == nil {
		t.Fatal("expected production scope rejection")
	}
}

func TestResourceCeilingRejected(t *testing.T) {
	spec := validSpec()
	spec.Policy.PIDsMax = MaxPIDs + 1
	if err := spec.Validate("registry.local"); err == nil {
		t.Fatal("expected PID ceiling rejection")
	}
}
