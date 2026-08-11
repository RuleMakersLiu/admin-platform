package manifest

import (
	"encoding/json"
	"fmt"
	"strings"

	"admin-sandbox-controller/internal/policy"
)

type Resource map[string]interface{}

type Bundle struct {
	ConfigMap     Resource `json:"config_map"`
	NetworkPolicy Resource `json:"network_policy"`
	Job           Resource `json:"job"`
}

func Build(spec policy.TrialExecutionSpec) (Bundle, error) {
	caseJSON, err := json.Marshal(map[string]interface{}{
		"case_id": spec.CaseExternalID,
		"input":   spec.CaseInput,
	})
	if err != nil {
		return Bundle{}, fmt.Errorf("marshal case input: %w", err)
	}
	if len(caseJSON) > 512*1024 {
		return Bundle{}, fmt.Errorf("case input exceeds 512 KiB")
	}
	shortID := strings.ReplaceAll(spec.TrialID, "-", "")[:12]
	name := "trial-" + shortID
	labels := map[string]interface{}{
		"app.kubernetes.io/name":       "agent-eval-trial",
		"app.kubernetes.io/managed-by": "admin-sandbox-controller",
		"eval.platform/trial-id":       spec.TrialID,
		"eval.platform/tenant-id":      fmt.Sprintf("%d", spec.TenantID),
	}

	configMap := Resource{
		"apiVersion": "v1", "kind": "ConfigMap",
		"metadata":  map[string]interface{}{"name": name + "-input", "namespace": policy.EvaluationNS, "labels": labels},
		"immutable": true,
		"data":      map[string]interface{}{"case.json": string(caseJSON)},
	}

	networkPolicy := Resource{
		"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
		"metadata": map[string]interface{}{"name": name + "-egress", "namespace": policy.EvaluationNS, "labels": labels},
		"spec": map[string]interface{}{
			"podSelector": map[string]interface{}{"matchLabels": map[string]interface{}{"eval.platform/trial-id": spec.TrialID}},
			"policyTypes": []interface{}{"Ingress", "Egress"},
			"ingress":     []interface{}{},
			"egress": []interface{}{
				map[string]interface{}{
					"to": []interface{}{map[string]interface{}{
						"namespaceSelector": map[string]interface{}{"matchLabels": map[string]interface{}{"kubernetes.io/metadata.name": "agent-eval-proxy"}},
						"podSelector":       map[string]interface{}{"matchLabels": map[string]interface{}{"eval.platform/proxy": "true"}},
					}},
					"ports": []interface{}{
						map[string]interface{}{"protocol": "TCP", "port": 8443},
						map[string]interface{}{"protocol": "TCP", "port": 4317},
					},
				},
			},
		},
	}

	cpu := fmt.Sprintf("%dm", spec.Policy.CPUMillis)
	memory := fmt.Sprintf("%dMi", spec.Policy.MemoryMB)
	storage := fmt.Sprintf("%dMi", spec.Policy.EphemeralStorageMB)
	job := Resource{
		"apiVersion": "batch/v1", "kind": "Job",
		"metadata": map[string]interface{}{"name": name, "namespace": policy.EvaluationNS, "labels": labels},
		"spec": map[string]interface{}{
			"backoffLimit":            0,
			"activeDeadlineSeconds":   spec.Policy.TimeoutSeconds,
			"ttlSecondsAfterFinished": 300,
			"template": map[string]interface{}{
				"metadata": map[string]interface{}{"labels": labels},
				"spec": map[string]interface{}{
					"runtimeClassName":             policy.RuntimeClass,
					"automountServiceAccountToken": false,
					"enableServiceLinks":           false,
					"hostNetwork":                  false, "hostPID": false, "hostIPC": false,
					"restartPolicy": "Never",
					"securityContext": map[string]interface{}{
						"runAsNonRoot":   true,
						"runAsUser":      10001,
						"runAsGroup":     10001,
						"fsGroup":        10001,
						"seccompProfile": map[string]interface{}{"type": "RuntimeDefault"},
					},
					"containers": []interface{}{map[string]interface{}{
						"name": "agent", "image": spec.ImageDigest, "imagePullPolicy": "IfNotPresent",
						"securityContext": map[string]interface{}{
							"allowPrivilegeEscalation": false,
							"readOnlyRootFilesystem":   true,
							"privileged":               false,
							"appArmorProfile":          map[string]interface{}{"type": "RuntimeDefault"},
							"capabilities":             map[string]interface{}{"drop": []interface{}{"ALL"}},
						},
						"resources": map[string]interface{}{
							"requests": map[string]interface{}{"cpu": cpu, "memory": memory, "ephemeral-storage": storage},
							"limits":   map[string]interface{}{"cpu": cpu, "memory": memory, "ephemeral-storage": storage},
						},
						"env": []interface{}{
							map[string]interface{}{"name": "EVAL_TRIAL_ID", "value": spec.TrialID},
							map[string]interface{}{"name": "EVAL_PROXY_URL", "value": "https://admin-egress-gateway.agent-eval-proxy.svc:8443"},
						},
						"volumeMounts": []interface{}{
							map[string]interface{}{"name": "case-input", "mountPath": "/eval/input", "readOnly": true},
							map[string]interface{}{"name": "work", "mountPath": "/eval/work"},
							map[string]interface{}{"name": "tmp", "mountPath": "/tmp"},
						},
					}},
					"volumes": []interface{}{
						map[string]interface{}{"name": "case-input", "configMap": map[string]interface{}{"name": name + "-input", "defaultMode": 0440}},
						map[string]interface{}{"name": "work", "emptyDir": map[string]interface{}{"sizeLimit": storage}},
						map[string]interface{}{"name": "tmp", "emptyDir": map[string]interface{}{"medium": "Memory", "sizeLimit": "128Mi"}},
					},
				},
			},
		},
	}
	return Bundle{ConfigMap: configMap, NetworkPolicy: networkPolicy, Job: job}, nil
}
