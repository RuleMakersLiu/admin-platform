package policy

import (
	"context"
	"net"
	"testing"
)

func TestProductionWriteDestinationRejected(t *testing.T) {
	_, err := ParseRegistry(`[{"id":"refund","kind":"TOOL","url":"https://example.com/tool","side_effect_mode":"PRODUCTION_WRITE","fixed_cost_usd":0,"max_body_bytes":1024}]`)
	if err == nil {
		t.Fatal("expected production write rejection")
	}
}

func TestArbitraryInsecureURLRejected(t *testing.T) {
	_, err := ParseRegistry(`[{"id":"model","kind":"MODEL","url":"http://127.0.0.1/model","fixed_cost_usd":0.01,"max_body_bytes":1024}]`)
	if err == nil {
		t.Fatal("expected insecure URL rejection")
	}
}

func TestPrivateAndMetadataIPsRejectedAfterResolution(t *testing.T) {
	for _, target := range []string{"https://127.0.0.1/model", "https://169.254.169.254/latest/meta-data", "https://10.0.0.1/tool"} {
		if err := ValidateResolvedDestination(context.Background(), target, net.DefaultResolver); err == nil {
			t.Fatalf("expected %s to be rejected", target)
		}
	}
}
