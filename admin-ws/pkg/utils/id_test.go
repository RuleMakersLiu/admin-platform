package utils

import (
	"strings"
	"testing"
)

// --- GenerateID tests ---

func TestGenerateID_NotEmpty(t *testing.T) {
	id := GenerateID()
	if id == "" {
		t.Error("GenerateID returned empty string")
	}
}

func TestGenerateID_Unique(t *testing.T) {
	ids := make(map[string]bool)
	for i := 0; i < 1000; i++ {
		id := GenerateID()
		if ids[id] {
			t.Fatalf("GenerateID produced duplicate ID: %q", id)
		}
		ids[id] = true
	}
}

func TestGenerateID_Format(t *testing.T) {
	id := GenerateID()

	// The format is: hex(8 random bytes) + unix nano timestamp
	// 8 bytes = 16 hex chars, followed by digits
	// Should only contain hex chars and digits
	for _, ch := range id {
		if !isHexDigit(ch) {
			t.Errorf("GenerateID contains unexpected character %q in %q", ch, id)
		}
	}
}

func TestGenerateID_Length(t *testing.T) {
	id := GenerateID()

	// 8 bytes hex = 16 chars + at least 1 digit for timestamp
	if len(id) < 17 {
		t.Errorf("GenerateID too short: %d chars in %q", len(id), id)
	}
}

// --- GenerateSessionID tests ---

func TestGenerateSessionID_NotEmpty(t *testing.T) {
	id := GenerateSessionID()
	if id == "" {
		t.Error("GenerateSessionID returned empty string")
	}
}

func TestGenerateSessionID_Unique(t *testing.T) {
	ids := make(map[string]bool)
	for i := 0; i < 1000; i++ {
		id := GenerateSessionID()
		if ids[id] {
			t.Fatalf("GenerateSessionID produced duplicate ID: %q", id)
		}
		ids[id] = true
	}
}

func TestGenerateSessionID_IsHexEncoded(t *testing.T) {
	id := GenerateSessionID()

	// 16 bytes -> 32 hex characters
	if len(id) != 32 {
		t.Errorf("expected session ID length 32, got %d: %q", len(id), id)
	}

	for _, ch := range id {
		if !isHexDigit(ch) {
			t.Errorf("GenerateSessionID contains non-hex character %q in %q", ch, id)
		}
	}
}

func TestGenerateSessionID_Lowercase(t *testing.T) {
	id := GenerateSessionID()

	// hex.EncodeToString produces lowercase hex
	if id != strings.ToLower(id) {
		t.Errorf("GenerateSessionID should be lowercase, got: %q", id)
	}
}

// --- Concurrency safety (basic) ---

func TestGenerateID_Concurrent(t *testing.T) {
	const goroutines = 100
	results := make(chan string, goroutines)

	for i := 0; i < goroutines; i++ {
		go func() {
			results <- GenerateID()
		}()
	}

	ids := make(map[string]bool)
	for i := 0; i < goroutines; i++ {
		id := <-results
		if ids[id] {
			t.Errorf("concurrent GenerateID produced duplicate: %q", id)
		}
		ids[id] = true
	}
}

func TestGenerateSessionID_Concurrent(t *testing.T) {
	const goroutines = 100
	results := make(chan string, goroutines)

	for i := 0; i < goroutines; i++ {
		go func() {
			results <- GenerateSessionID()
		}()
	}

	ids := make(map[string]bool)
	for i := 0; i < goroutines; i++ {
		id := <-results
		if ids[id] {
			t.Errorf("concurrent GenerateSessionID produced duplicate: %q", id)
		}
		ids[id] = true
	}
}

// helper
func isHexDigit(ch rune) bool {
	return (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f') || (ch >= 'A' && ch <= 'F')
}
