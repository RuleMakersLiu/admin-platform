package server

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"admin-egress-gateway/internal/budget"
	"admin-egress-gateway/internal/policy"
	"admin-egress-gateway/internal/token"
)

type Server struct {
	SigningKey        []byte
	Registry          policy.Registry
	Budget            budget.Store
	DistributedBudget bool
	ExecutionEnabled  bool
	GateReference     string
	Client            *http.Client
	Resolver          *net.Resolver
}

func FromEnvironment() (*Server, error) {
	registry, err := policy.ParseRegistry(os.Getenv("EGRESS_DESTINATIONS_JSON"))
	if err != nil {
		return nil, err
	}
	enabled, _ := strconv.ParseBool(os.Getenv("EGRESS_EXECUTION_ENABLED"))
	client := &http.Client{
		Timeout:       60 * time.Second,
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return errors.New("redirects are prohibited") },
		Transport: &http.Transport{
			Proxy: nil, DialContext: policy.SafeDialContext(net.DefaultResolver),
			TLSHandshakeTimeout: 5 * time.Second, ResponseHeaderTimeout: 55 * time.Second,
			MaxIdleConns: 100, MaxIdleConnsPerHost: 20,
		},
	}
	var budgetStore budget.Store = budget.NewMemoryStore()
	distributedBudget := false
	if os.Getenv("EGRESS_BUDGET_STORE") == "redis" {
		database, _ := strconv.Atoi(os.Getenv("EGRESS_REDIS_DB"))
		redisStore := budget.NewRedisStore(os.Getenv("EGRESS_REDIS_ADDRESS"), os.Getenv("EGRESS_REDIS_PASSWORD"), database)
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		if err := redisStore.Ping(ctx); err != nil {
			return nil, errors.New("distributed budget ledger unavailable")
		}
		budgetStore = redisStore
		distributedBudget = true
	}
	return &Server{
		SigningKey: []byte(os.Getenv("EGRESS_TRIAL_SIGNING_KEY")), Registry: registry,
		Budget: budgetStore, DistributedBudget: distributedBudget, ExecutionEnabled: enabled,
		GateReference: strings.TrimSpace(os.Getenv("EGRESS_APPROVED_GATE_REFERENCE")),
		Client:        client, Resolver: net.DefaultResolver,
	}, nil
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", s.health)
	mux.HandleFunc("POST /v1/model/{id}", s.proxy("MODEL"))
	mux.HandleFunc("POST /v1/tool/{id}", s.proxy("TOOL"))
	mux.HandleFunc("POST /v1/agent/{id}", s.proxy("REMOTE_AGENT"))
	return mux
}

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"status": "ok", "service": "admin-egress-gateway", "execution_enabled": s.gateOpen(),
		"distributed_budget": s.DistributedBudget,
	})
}

func (s *Server) proxy(kind string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !s.gateOpen() {
			writeJSON(w, http.StatusLocked, map[string]string{"error": "egress is locked until G0/G1 approval and distributed budget ledger"})
			return
		}
		claims, err := s.authenticate(r)
		if err != nil {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": err.Error()})
			return
		}
		id := r.PathValue("id")
		destination, exists := s.Registry.Items[id]
		if !exists || destination.Kind != kind {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "destination not registered"})
			return
		}
		scopePrefix := strings.ToLower(kind)
		if kind == "REMOTE_AGENT" {
			scopePrefix = "agent"
		}
		scope := scopePrefix + ":" + id
		if !claims.Allows(scope) {
			writeJSON(w, http.StatusForbidden, map[string]string{"error": "trial scope denied"})
			return
		}
		if err := policy.ValidateResolvedDestination(r.Context(), destination.URL, s.Resolver); err != nil {
			writeJSON(w, http.StatusForbidden, map[string]string{"error": "destination policy denied"})
			return
		}
		body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, destination.MaxBodyBytes))
		if err != nil {
			writeJSON(w, http.StatusRequestEntityTooLarge, map[string]string{"error": "request body too large"})
			return
		}
		var credential string
		// Credentials are resolved from SecretRef by the deployment's Vault agent.
		// The registry URL and caller headers can never select or override a credential.
		if destination.SecretRef != "" {
			secretPath := os.Getenv("EGRESS_SECRET_FILE_" + strings.ToUpper(strings.ReplaceAll(destination.ID, "-", "_")))
			secretBytes, readErr := os.ReadFile(secretPath)
			if readErr != nil || len(secretBytes) == 0 || len(secretBytes) > 16*1024 {
				writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "destination credential unavailable"})
				return
			}
			credential = strings.TrimSpace(string(secretBytes))
		}
		ttl := time.Until(time.Unix(claims.Expires, 0))
		calls, cost, err := s.Budget.Charge(r.Context(), claims.JTI, destination.FixedCostUSD, claims.MaxCalls, claims.MaxCost, ttl)
		if err != nil {
			status := http.StatusForbidden
			if errors.Is(err, budget.ErrExceeded) {
				status = http.StatusPaymentRequired
				_ = s.Budget.Revoke(r.Context(), claims.JTI, ttl)
			}
			writeJSON(w, status, map[string]string{"error": err.Error()})
			return
		}
		upstream, err := http.NewRequestWithContext(r.Context(), http.MethodPost, destination.URL, bytes.NewReader(body))
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "upstream request failed"})
			return
		}
		upstream.Header.Set("Content-Type", "application/json")
		upstream.Header.Set("X-Eval-Trial-Id", claims.TrialID)
		if credential != "" {
			upstream.Header.Set("Authorization", "Bearer "+credential)
		}
		response, err := s.Client.Do(upstream)
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "upstream unavailable"})
			return
		}
		defer response.Body.Close()
		responseBody, err := io.ReadAll(io.LimitReader(response.Body, destination.MaxBodyBytes+1))
		if err != nil || int64(len(responseBody)) > destination.MaxBodyBytes {
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": "upstream response exceeded policy"})
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Eval-Usage-Calls", strconv.Itoa(calls))
		w.Header().Set("X-Eval-Usage-Cost", strconv.FormatFloat(cost, 'f', 6, 64))
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.WriteHeader(response.StatusCode)
		_, _ = w.Write(responseBody)
	}
}

func (s *Server) authenticate(r *http.Request) (token.Claims, error) {
	value := r.Header.Get("Authorization")
	if !strings.HasPrefix(value, "Bearer ") {
		return token.Claims{}, errors.New("missing trial token")
	}
	return token.Verify(strings.TrimPrefix(value, "Bearer "), s.SigningKey, time.Now())
}

func (s *Server) gateOpen() bool {
	// Memory budget accounting cannot safely support multiple replicas. Keep the
	// data plane locked until a distributed atomic budget store is selected.
	return s.ExecutionEnabled && s.GateReference != "" && s.DistributedBudget
}

func writeJSON(w http.ResponseWriter, status int, value interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
