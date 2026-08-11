package policy

import (
	"errors"
	"fmt"
	"regexp"
	"strings"
)

const (
	RuntimeClass      = "kata"
	EvaluationNS      = "agent-eval"
	NetworkPolicyName = "INTERNAL_PROXY_ONLY"
	MaxCPUMillis      = 4000
	MaxMemoryMB       = 8192
	MaxPIDs           = 512
	MaxTimeoutSeconds = 1800
	MaxEphemeralMB    = 8192
	MaxLogBytes       = 20 * 1024 * 1024
	MaxArtifactBytes  = 200 * 1024 * 1024
	MaxToolCalls      = 200
	MaxModelCostUSD   = 50.0
)

var (
	digestPattern = regexp.MustCompile(`^[a-z0-9][a-z0-9./_-]*@sha256:[a-f0-9]{64}$`)
	idPattern     = regexp.MustCompile(`^[a-f0-9-]{36}$`)
)

// TrialExecutionSpec is deliberately narrow. It contains no raw Kubernetes,
// host, privilege, service-account, runtime-class, or arbitrary network fields.
type TrialExecutionSpec struct {
	TenantID       int64                  `json:"tenant_id"`
	TrialID        string                 `json:"trial_id"`
	AttemptNo      int                    `json:"attempt_no"`
	ImageDigest    string                 `json:"image_digest"`
	CaseExternalID string                 `json:"case_external_id"`
	CaseInput      map[string]interface{} `json:"case_input"`
	Policy         SandboxPolicy          `json:"policy"`
}

type SandboxPolicy struct {
	CPUMillis          int      `json:"cpu_millis"`
	MemoryMB           int      `json:"memory_mb"`
	PIDsMax            int      `json:"pids_max"`
	TimeoutSeconds     int      `json:"timeout_seconds"`
	EphemeralStorageMB int      `json:"ephemeral_storage_mb"`
	MaxLogBytes        int64    `json:"max_log_bytes"`
	MaxArtifactBytes   int64    `json:"max_artifact_bytes"`
	MaxToolCalls       int      `json:"max_tool_calls"`
	MaxModelCost       float64  `json:"max_model_cost"`
	NetworkPolicy      string   `json:"network_policy"`
	ToolScopes         []string `json:"tool_scopes"`
}

func (s TrialExecutionSpec) Validate(allowedRegistry string) error {
	if s.TenantID <= 0 || s.AttemptNo <= 0 {
		return errors.New("tenant_id and attempt_no must be positive")
	}
	if !idPattern.MatchString(s.TrialID) || !idPattern.MatchString(s.CaseExternalID) {
		return errors.New("trial_id and case_external_id must be UUIDs")
	}
	if !digestPattern.MatchString(s.ImageDigest) {
		return errors.New("image must be pinned to a sha256 digest")
	}
	registry := strings.TrimSuffix(strings.ToLower(strings.TrimSpace(allowedRegistry)), "/")
	if registry == "" || !strings.HasPrefix(s.ImageDigest, registry+"/") {
		return errors.New("image registry is not allowed")
	}
	if s.CaseInput == nil {
		return errors.New("exactly one case input is required")
	}
	return s.Policy.Validate()
}

func (p SandboxPolicy) Validate() error {
	checks := []struct {
		name  string
		value int64
		max   int64
	}{
		{"cpu_millis", int64(p.CPUMillis), MaxCPUMillis},
		{"memory_mb", int64(p.MemoryMB), MaxMemoryMB},
		{"pids_max", int64(p.PIDsMax), MaxPIDs},
		{"timeout_seconds", int64(p.TimeoutSeconds), MaxTimeoutSeconds},
		{"ephemeral_storage_mb", int64(p.EphemeralStorageMB), MaxEphemeralMB},
		{"max_log_bytes", p.MaxLogBytes, MaxLogBytes},
		{"max_artifact_bytes", p.MaxArtifactBytes, MaxArtifactBytes},
		{"max_tool_calls", int64(p.MaxToolCalls), MaxToolCalls},
	}
	for _, check := range checks {
		if check.value <= 0 || check.value > check.max {
			return fmt.Errorf("%s must be between 1 and %d", check.name, check.max)
		}
	}
	if p.MaxModelCost <= 0 || p.MaxModelCost > MaxModelCostUSD {
		return fmt.Errorf("max_model_cost must be between 0 and %.2f", MaxModelCostUSD)
	}
	if p.NetworkPolicy != NetworkPolicyName {
		return errors.New("only INTERNAL_PROXY_ONLY network policy is permitted")
	}
	for _, scope := range p.ToolScopes {
		if strings.Contains(strings.ToUpper(scope), "PRODUCTION") {
			return errors.New("production tool scopes are prohibited")
		}
	}
	return nil
}
