package token

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"
)

const Audience = "admin-eval-egress"

type Claims struct {
	TenantID int64    `json:"tenant_id"`
	TrialID  string   `json:"trial_id"`
	Audience string   `json:"aud"`
	Scopes   []string `json:"scopes"`
	Expires  int64    `json:"exp"`
	IssuedAt int64    `json:"iat"`
	JTI      string   `json:"jti"`
	MaxCalls int      `json:"max_calls"`
	MaxCost  float64  `json:"max_cost"`
}

func Sign(claims Claims, key []byte) (string, error) {
	if len(key) < 32 {
		return "", errors.New("signing key must contain at least 32 bytes")
	}
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"HS256","typ":"JWT"}`))
	payload, err := json.Marshal(claims)
	if err != nil {
		return "", err
	}
	body := header + "." + base64.RawURLEncoding.EncodeToString(payload)
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write([]byte(body))
	return body + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil)), nil
}

func Verify(raw string, key []byte, now time.Time) (Claims, error) {
	var claims Claims
	parts := strings.Split(raw, ".")
	if len(parts) != 3 || len(key) < 32 {
		return claims, errors.New("invalid token")
	}
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write([]byte(parts[0] + "." + parts[1]))
	provided, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil || !hmac.Equal(provided, mac.Sum(nil)) {
		return claims, errors.New("invalid token signature")
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil || json.Unmarshal(payload, &claims) != nil {
		return claims, errors.New("invalid token claims")
	}
	if claims.Audience != Audience {
		return claims, errors.New("invalid token audience")
	}
	if claims.Expires <= now.Unix() || claims.IssuedAt > now.Add(time.Minute).Unix() {
		return claims, errors.New("expired or not-yet-valid token")
	}
	if claims.Expires <= claims.IssuedAt || claims.Expires-claims.IssuedAt > int64((15*time.Minute).Seconds()) {
		return claims, errors.New("trial token lifetime exceeds policy")
	}
	if claims.TenantID <= 0 || claims.TrialID == "" || claims.JTI == "" || claims.MaxCalls <= 0 || claims.MaxCost <= 0 {
		return claims, errors.New("incomplete token claims")
	}
	return claims, nil
}

func (c Claims) Allows(scope string) bool {
	for _, candidate := range c.Scopes {
		if candidate == scope {
			return true
		}
	}
	return false
}

func NewJTI(trialID string, attempt int, issuedAt time.Time) string {
	sum := sha256.Sum256([]byte(trialID + ":" + strconv.Itoa(attempt) + ":" + strconv.FormatInt(issuedAt.UnixNano(), 10)))
	return fmt.Sprintf("%x", sum[:16])
}
