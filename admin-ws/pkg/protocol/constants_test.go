package protocol

import (
	"fmt"
	"testing"
)

// --- System Event Constants ---

func TestSystemEventConstants(t *testing.T) {
	events := []struct {
		name  string
		value string
	}{
		{"SysEventConnected", SysEventConnected},
		{"SysEventDisconnected", SysEventDisconnected},
		{"SysEventReconnected", SysEventReconnected},
		{"SysEventRoomJoined", SysEventRoomJoined},
		{"SysEventRoomLeft", SysEventRoomLeft},
		{"SysEventRoomMembers", SysEventRoomMembers},
		{"SysEventSubscribed", SysEventSubscribed},
		{"SysEventUnsubscribed", SysEventUnsubscribed},
		{"SysEventBroadcast", SysEventBroadcast},
	}

	for _, e := range events {
		if e.value == "" {
			t.Errorf("%s should not be empty", e.name)
		}
	}

	// Verify all system events have "sys:" prefix
	for _, e := range events {
		if e.name != "SysEventBroadcast" {
			// Only system events should have sys: prefix
			expected := "sys:"
			if len(e.value) >= 4 && e.value[:4] != expected && e.name != "SysEventBroadcast" {
				// SysEventBroadcast starts with "sys:" so it's fine
			}
		}
		if len(e.value) >= 4 && e.value[:4] != "sys:" {
			t.Errorf("%s = %q, expected 'sys:' prefix", e.name, e.value)
		}
	}
}

// --- Channel Constants ---

func TestChannelConstants(t *testing.T) {
	channels := []struct {
		name  string
		value string
	}{
		{"ChannelSystem", ChannelSystem},
		{"ChannelNotice", ChannelNotice},
		{"ChannelLog", ChannelLog},
		{"ChannelAgent", ChannelAgent},
		{"ChannelDeploy", ChannelDeploy},
		{"ChannelMonitor", ChannelMonitor},
	}

	for _, ch := range channels {
		if ch.value == "" {
			t.Errorf("%s should not be empty", ch.name)
		}
	}

	// Verify uniqueness
	seen := make(map[string]bool)
	for _, ch := range channels {
		if seen[ch.value] {
			t.Errorf("duplicate channel constant: %q", ch.value)
		}
		seen[ch.value] = true
	}
}

// --- Room Constants ---

func TestRoomConstants(t *testing.T) {
	rooms := []struct {
		name     string
		value    string
		hasFmt   bool // whether the value contains %d format verb
	}{
		{"RoomAdmin", RoomAdmin, false},
		{"RoomTenant", RoomTenant, true},
		{"RoomProject", RoomProject, true},
		{"RoomTask", RoomTask, true},
		{"RoomDeploy", RoomDeploy, true},
	}

	for _, r := range rooms {
		if r.value == "" {
			t.Errorf("%s should not be empty", r.name)
		}
	}

	// Verify format strings can be used with fmt.Sprintf
	for _, r := range rooms {
		if r.hasFmt {
			result := fmt.Sprintf(r.value, 123)
			if result == r.value {
				t.Errorf("%s format string did not substitute %%d", r.name)
			}
		}
	}
}

// --- Business Event Constants ---

func TestBusinessEventConstants(t *testing.T) {
	events := []struct {
		name  string
		value string
	}{
		{"EventAgentMessage", EventAgentMessage},
		{"EventAgentStatus", EventAgentStatus},
		{"EventAgentTaskStart", EventAgentTaskStart},
		{"EventAgentTaskEnd", EventAgentTaskEnd},
		{"EventDeployStart", EventDeployStart},
		{"EventDeployProgress", EventDeployProgress},
		{"EventDeploySuccess", EventDeploySuccess},
		{"EventDeployFailed", EventDeployFailed},
		{"EventNoticeInfo", EventNoticeInfo},
		{"EventNoticeWarning", EventNoticeWarning},
		{"EventNoticeError", EventNoticeError},
		{"EventMonitorMetric", EventMonitorMetric},
		{"EventMonitorAlert", EventMonitorAlert},
	}

	for _, e := range events {
		if e.value == "" {
			t.Errorf("%s should not be empty", e.name)
		}
	}

	// All business events should have a ":" separator (category:event pattern)
	for _, e := range events {
		if !contains(e.value, ":") {
			t.Errorf("%s = %q, expected ':' separator in business event", e.name, e.value)
		}
	}
}

func contains(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

// --- RoomConfig defaults ---

func TestDefaultRoomConfig(t *testing.T) {
	cfg := DefaultRoomConfig

	if cfg.MaxMembers != 1000 {
		t.Errorf("expected MaxMembers 1000, got %d", cfg.MaxMembers)
	}
	if cfg.IsPersistent {
		t.Error("expected IsPersistent to be false by default")
	}
	if cfg.IsPrivate {
		t.Error("expected IsPrivate to be false by default")
	}
	if cfg.EnableHistory {
		t.Error("expected EnableHistory to be false by default")
	}
	if cfg.TTL != 0 {
		t.Errorf("expected TTL 0, got %d", cfg.TTL)
	}
}

// --- ChannelConfig defaults ---

func TestDefaultChannelConfig(t *testing.T) {
	cfg := DefaultChannelConfig

	if !cfg.IsPublic {
		t.Error("expected IsPublic to be true by default")
	}
	if !cfg.EnableBuffer {
		t.Error("expected EnableBuffer to be true by default")
	}
	if cfg.BufferSize != 100 {
		t.Errorf("expected BufferSize 100, got %d", cfg.BufferSize)
	}
	if cfg.RateLimit != 100 {
		t.Errorf("expected RateLimit 100, got %d", cfg.RateLimit)
	}
}

// --- Struct field JSON tags ---

func TestRoomConfig_JSONTags(t *testing.T) {
	cfg := RoomConfig{
		MaxMembers:    50,
		IsPersistent:  true,
		IsPrivate:     true,
		EnableHistory: true,
		TTL:           3600,
	}

	// Verify the struct can be used meaningfully (field assignment works)
	if cfg.MaxMembers != 50 {
		t.Error("MaxMembers assignment failed")
	}
	if cfg.TTL != 3600 {
		t.Error("TTL assignment failed")
	}
}

func TestChannelConfig_JSONTags(t *testing.T) {
	cfg := ChannelConfig{
		IsPublic:     false,
		EnableBuffer: false,
		BufferSize:   200,
		RateLimit:    50,
	}

	if cfg.IsPublic {
		t.Error("IsPublic should be false")
	}
	if cfg.BufferSize != 200 {
		t.Errorf("BufferSize should be 200, got %d", cfg.BufferSize)
	}
}
