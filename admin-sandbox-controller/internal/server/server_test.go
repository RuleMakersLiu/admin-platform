package server

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func signedRequest(t *testing.T, path, body string, key []byte) *http.Request {
	t.Helper()
	request := httptest.NewRequest(http.MethodPost, path, bytes.NewBufferString(body))
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write([]byte(body))
	request.Header.Set("X-Spec-Signature", hex.EncodeToString(mac.Sum(nil)))
	return request
}

const validBody = `{"tenant_id":1,"trial_id":"11111111-1111-1111-1111-111111111111","attempt_no":1,"image_digest":"registry.local/eval/agent@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","case_external_id":"22222222-2222-2222-2222-222222222222","case_input":{"prompt":"test"},"policy":{"cpu_millis":2000,"memory_mb":2048,"pids_max":256,"timeout_seconds":600,"ephemeral_storage_mb":4096,"max_log_bytes":10485760,"max_artifact_bytes":104857600,"max_tool_calls":50,"max_model_cost":5,"network_policy":"INTERNAL_PROXY_ONLY","tool_scopes":[]}}`

func TestPlanRequiresSignatureAndRejectsUnknownFields(t *testing.T) {
	key := []byte(strings.Repeat("k", 32))
	server := &Server{SigningKey: key, AllowedRegistry: "registry.local"}
	unsigned := httptest.NewRecorder()
	server.Handler().ServeHTTP(unsigned, httptest.NewRequest(http.MethodPost, "/api/v1/trials/plan", bytes.NewBufferString(validBody)))
	if unsigned.Code != http.StatusUnauthorized {
		t.Fatalf("unsigned status=%d", unsigned.Code)
	}

	unknownBody := strings.TrimSuffix(validBody, "}") + `,"privileged":true}`
	unknown := httptest.NewRecorder()
	server.Handler().ServeHTTP(unknown, signedRequest(t, "/api/v1/trials/plan", unknownBody, key))
	if unknown.Code != http.StatusBadRequest {
		t.Fatalf("unknown-field status=%d body=%s", unknown.Code, unknown.Body.String())
	}
}

func TestExecuteFailsClosedBeforeGate(t *testing.T) {
	key := []byte(strings.Repeat("k", 32))
	server := &Server{SigningKey: key, AllowedRegistry: "registry.local", ExecutionEnabled: true}
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, signedRequest(t, "/api/v1/trials/execute", validBody, key))
	if response.Code != http.StatusLocked {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
}
