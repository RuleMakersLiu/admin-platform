package token

import (
	"testing"
	"time"
)

func TestTokenAudienceExpiryAndScope(t *testing.T) {
	now := time.Now()
	claims := Claims{TenantID: 1, TrialID: "trial", Audience: Audience, Scopes: []string{"model:test"}, Expires: now.Add(time.Minute).Unix(), IssuedAt: now.Unix(), JTI: "jti", MaxCalls: 2, MaxCost: 1}
	raw, err := Sign(claims, []byte("12345678901234567890123456789012"))
	if err != nil {
		t.Fatal(err)
	}
	parsed, err := Verify(raw, []byte("12345678901234567890123456789012"), now)
	if err != nil {
		t.Fatal(err)
	}
	if !parsed.Allows("model:test") || parsed.Allows("tool:refund") {
		t.Fatal("scope validation failed")
	}
	if _, err := Verify(raw, []byte("12345678901234567890123456789012"), now.Add(2*time.Minute)); err == nil {
		t.Fatal("expected expiry rejection")
	}
}

func TestWrongAudienceRejected(t *testing.T) {
	now := time.Now()
	claims := Claims{TenantID: 1, TrialID: "trial", Audience: "other", Scopes: []string{"model:test"}, Expires: now.Add(time.Minute).Unix(), IssuedAt: now.Unix(), JTI: "jti", MaxCalls: 2, MaxCost: 1}
	raw, _ := Sign(claims, []byte("12345678901234567890123456789012"))
	if _, err := Verify(raw, []byte("12345678901234567890123456789012"), now); err == nil {
		t.Fatal("expected audience rejection")
	}
}

func TestLongLivedTokenRejected(t *testing.T) {
	now := time.Now()
	claims := Claims{TenantID: 1, TrialID: "trial", Audience: Audience, Scopes: []string{"model:test"}, Expires: now.Add(16 * time.Minute).Unix(), IssuedAt: now.Unix(), JTI: "jti", MaxCalls: 2, MaxCost: 1}
	raw, _ := Sign(claims, []byte("12345678901234567890123456789012"))
	if _, err := Verify(raw, []byte("12345678901234567890123456789012"), now); err == nil {
		t.Fatal("expected long-lived token rejection")
	}
}
