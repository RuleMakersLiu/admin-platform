package policy

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/url"
	"strings"
	"time"
)

type Destination struct {
	ID             string  `json:"id"`
	Kind           string  `json:"kind"`
	URL            string  `json:"url"`
	SecretRef      string  `json:"secret_ref"`
	SideEffectMode string  `json:"side_effect_mode"`
	FixedCostUSD   float64 `json:"fixed_cost_usd"`
	MaxBodyBytes   int64   `json:"max_body_bytes"`
}

type Registry struct{ Items map[string]Destination }

func ParseRegistry(raw string) (Registry, error) {
	var list []Destination
	if err := json.Unmarshal([]byte(raw), &list); err != nil {
		return Registry{}, fmt.Errorf("decode destinations: %w", err)
	}
	registry := Registry{Items: make(map[string]Destination, len(list))}
	for _, item := range list {
		if err := item.Validate(); err != nil {
			return Registry{}, fmt.Errorf("destination %q: %w", item.ID, err)
		}
		if _, exists := registry.Items[item.ID]; exists {
			return Registry{}, fmt.Errorf("duplicate destination %q", item.ID)
		}
		registry.Items[item.ID] = item
	}
	return registry, nil
}

func (d Destination) Validate() error {
	if d.ID == "" || strings.ContainsAny(d.ID, "/\\ ") {
		return errors.New("invalid id")
	}
	if d.Kind != "MODEL" && d.Kind != "TOOL" && d.Kind != "REMOTE_AGENT" {
		return errors.New("invalid kind")
	}
	parsed, err := url.Parse(d.URL)
	if err != nil || parsed.Scheme != "https" || parsed.Hostname() == "" || parsed.User != nil || parsed.Fragment != "" {
		return errors.New("destination must be an https URL without userinfo or fragment")
	}
	if d.Kind == "TOOL" {
		switch d.SideEffectMode {
		case "READ_ONLY", "MOCK_WRITE", "SANDBOX_WRITE":
		default:
			return errors.New("production or unspecified tool side effects are prohibited")
		}
	} else if d.SideEffectMode != "" {
		return errors.New("side effect mode is valid only for tools")
	}
	if d.FixedCostUSD < 0 || d.MaxBodyBytes <= 0 || d.MaxBodyBytes > 10*1024*1024 {
		return errors.New("invalid cost or body limit")
	}
	return nil
}

func ValidateResolvedDestination(ctx context.Context, rawURL string, resolver *net.Resolver) error {
	parsed, err := url.Parse(rawURL)
	if err != nil || parsed.Scheme != "https" {
		return errors.New("invalid destination URL")
	}
	lookupCtx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	addresses, err := resolver.LookupIPAddr(lookupCtx, parsed.Hostname())
	if err != nil || len(addresses) == 0 {
		return errors.New("destination DNS resolution failed")
	}
	for _, address := range addresses {
		if forbiddenIP(address.IP) {
			return fmt.Errorf("destination resolves to prohibited IP %s", address.IP)
		}
	}
	return nil
}

// SafeDialContext validates the exact resolved IP immediately before dialing,
// preventing a second unchecked DNS lookup and DNS-rebinding bypass.
func SafeDialContext(resolver *net.Resolver) func(context.Context, string, string) (net.Conn, error) {
	dialer := &net.Dialer{Timeout: 5 * time.Second, KeepAlive: 30 * time.Second}
	return func(ctx context.Context, network, address string) (net.Conn, error) {
		host, port, err := net.SplitHostPort(address)
		if err != nil {
			return nil, errors.New("invalid upstream address")
		}
		addresses, err := resolver.LookupIPAddr(ctx, host)
		if err != nil || len(addresses) == 0 {
			return nil, errors.New("upstream DNS resolution failed")
		}
		var lastErr error
		for _, candidate := range addresses {
			if forbiddenIP(candidate.IP) {
				return nil, errors.New("upstream resolved to prohibited IP")
			}
			connection, dialErr := dialer.DialContext(ctx, network, net.JoinHostPort(candidate.IP.String(), port))
			if dialErr == nil {
				return connection, nil
			}
			lastErr = dialErr
		}
		return nil, lastErr
	}
}

func forbiddenIP(ip net.IP) bool {
	if ip == nil || ip.IsUnspecified() || ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() || ip.IsMulticast() {
		return true
	}
	if ip4 := ip.To4(); ip4 != nil {
		// Carrier-grade NAT and benchmarking/documentation ranges are not valid external providers.
		return ip4[0] == 100 && ip4[1] >= 64 && ip4[1] <= 127 || ip4[0] == 198 && (ip4[1] == 18 || ip4[1] == 19)
	}
	return false
}
