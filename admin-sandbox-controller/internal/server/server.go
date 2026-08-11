package server

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"

	"admin-sandbox-controller/internal/manifest"
	"admin-sandbox-controller/internal/policy"
)

type Server struct {
	SigningKey       []byte
	AllowedRegistry  string
	ExecutionEnabled bool
	GateReference    string
}

func FromEnvironment() *Server {
	enabled, _ := strconv.ParseBool(os.Getenv("SANDBOX_EXECUTION_ENABLED"))
	return &Server{
		SigningKey:       []byte(os.Getenv("SANDBOX_SPEC_SIGNING_KEY")),
		AllowedRegistry:  os.Getenv("SANDBOX_ALLOWED_REGISTRY"),
		ExecutionEnabled: enabled,
		GateReference:    strings.TrimSpace(os.Getenv("SANDBOX_APPROVED_GATE_REFERENCE")),
	}
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", s.health)
	mux.HandleFunc("POST /api/v1/trials/plan", s.plan)
	mux.HandleFunc("POST /api/v1/trials/execute", s.execute)
	return mux
}

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"status": "ok", "service": "admin-sandbox-controller",
		"execution_enabled": s.executionGateOpen(), "runtime_class": policy.RuntimeClass,
	})
}

func (s *Server) plan(w http.ResponseWriter, r *http.Request) {
	spec, ok := s.authenticateAndDecode(w, r)
	if !ok {
		return
	}
	bundle, err := manifest.Build(spec)
	if err != nil {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, bundle)
}

func (s *Server) execute(w http.ResponseWriter, r *http.Request) {
	_, ok := s.authenticateAndDecode(w, r)
	if !ok {
		return
	}
	if !s.executionGateOpen() {
		writeJSON(w, http.StatusLocked, map[string]string{
			"error": "sandbox execution is locked until G0/G1 approval",
		})
		return
	}
	// Kubernetes mutation is intentionally not enabled in the foundation release.
	// It is added only after the generated manifest passes the G1 attack suite.
	writeJSON(w, http.StatusNotImplemented, map[string]string{
		"error": "G1 deployment adapter is not installed",
	})
}

func (s *Server) authenticateAndDecode(w http.ResponseWriter, r *http.Request) (policy.TrialExecutionSpec, bool) {
	var spec policy.TrialExecutionSpec
	body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 1024*1024))
	if err != nil {
		writeJSON(w, http.StatusRequestEntityTooLarge, map[string]string{"error": "request body too large"})
		return spec, false
	}
	if len(s.SigningKey) < 32 {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "signing key is not configured"})
		return spec, false
	}
	provided, err := hex.DecodeString(r.Header.Get("X-Spec-Signature"))
	if err != nil {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid signature"})
		return spec, false
	}
	mac := hmac.New(sha256.New, s.SigningKey)
	_, _ = mac.Write(body)
	if !hmac.Equal(provided, mac.Sum(nil)) {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid signature"})
		return spec, false
	}
	decoder := json.NewDecoder(strings.NewReader(string(body)))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&spec); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid execution spec"})
		return spec, false
	}
	if err := spec.Validate(s.AllowedRegistry); err != nil {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"error": err.Error()})
		return spec, false
	}
	return spec, true
}

func (s *Server) executionGateOpen() bool {
	return s.ExecutionEnabled && s.GateReference != ""
}

func writeJSON(w http.ResponseWriter, status int, value interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
