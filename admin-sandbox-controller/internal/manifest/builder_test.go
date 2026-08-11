package manifest

import (
	"encoding/json"
	"strings"
	"testing"

	"admin-sandbox-controller/internal/policy"
)

func TestManifestContainsMandatorySandboxControls(t *testing.T) {
	spec := policy.TrialExecutionSpec{
		TenantID: 1, TrialID: "11111111-1111-1111-1111-111111111111", AttemptNo: 1,
		ImageDigest:    "registry.local/eval/agent@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		CaseExternalID: "22222222-2222-2222-2222-222222222222", CaseInput: map[string]interface{}{"prompt": "test"},
		Policy: policy.SandboxPolicy{CPUMillis: 2000, MemoryMB: 2048, PIDsMax: 256, TimeoutSeconds: 600, EphemeralStorageMB: 4096, MaxLogBytes: 10485760, MaxArtifactBytes: 104857600, MaxToolCalls: 50, MaxModelCost: 5, NetworkPolicy: policy.NetworkPolicyName},
	}
	bundle, err := Build(spec)
	if err != nil {
		t.Fatal(err)
	}
	raw, _ := json.Marshal(bundle)
	text := string(raw)
	for _, expected := range []string{`"runtimeClassName":"kata"`, `"automountServiceAccountToken":false`, `"readOnlyRootFilesystem":true`, `"allowPrivilegeEscalation":false`, `"appArmorProfile":{"type":"RuntimeDefault"}`, `"drop":["ALL"]`, `"hostNetwork":false`, `"policyTypes":["Ingress","Egress"]`} {
		if !strings.Contains(text, expected) {
			t.Errorf("missing mandatory control %s", expected)
		}
	}
	for _, forbidden := range []string{"hostPath", "docker.sock", "serviceAccountName"} {
		if strings.Contains(text, forbidden) {
			t.Errorf("forbidden field %s present", forbidden)
		}
	}
}
