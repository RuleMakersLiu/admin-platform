package auth

import (
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/spf13/viper"
)

// setupTestViper initializes viper with test values.
// Each test calls this to avoid relying on config files.
func setupTestViper() {
	viper.Reset()
	viper.Set("jwt.secret", "test-secret-key-for-unit-tests")
	viper.Set("jwt.expiration", 3600) // 1 hour
}

// ---------- GenerateToken ----------

func TestGenerateToken_Success(t *testing.T) {
	setupTestViper()

	token, err := GenerateToken(1, "admin", 100)
	if err != nil {
		t.Fatalf("GenerateToken returned unexpected error: %v", err)
	}
	if token == "" {
		t.Fatal("GenerateToken returned empty token")
	}
}

func TestGenerateToken_DifferentUsers(t *testing.T) {
	setupTestViper()

	token1, err := GenerateToken(1, "alice", 10)
	if err != nil {
		t.Fatalf("GenerateToken alice: %v", err)
	}
	token2, err := GenerateToken(2, "bob", 20)
	if err != nil {
		t.Fatalf("GenerateToken bob: %v", err)
	}
	if token1 == token2 {
		t.Fatal("tokens for different users should not be equal")
	}
}

// ---------- ParseToken (round-trip) ----------

func TestParseToken_ValidToken(t *testing.T) {
	setupTestViper()

	token, err := GenerateToken(42, "admin", 1)
	if err != nil {
		t.Fatalf("GenerateToken: %v", err)
	}

	claims, err := ParseToken(token)
	if err != nil {
		t.Fatalf("ParseToken returned unexpected error: %v", err)
	}

	if claims.AdminID != 42 {
		t.Errorf("AdminID = %d, want 42", claims.AdminID)
	}
	if claims.Username != "admin" {
		t.Errorf("Username = %q, want %q", claims.Username, "admin")
	}
	if claims.TenantID != 1 {
		t.Errorf("TenantID = %d, want 1", claims.TenantID)
	}
}

func TestParseToken_AllFieldsPreserved(t *testing.T) {
	setupTestViper()

	token, err := GenerateToken(999, "testuser", 55)
	if err != nil {
		t.Fatalf("GenerateToken: %v", err)
	}

	claims, err := ParseToken(token)
	if err != nil {
		t.Fatalf("ParseToken: %v", err)
	}

	if claims.AdminID != 999 {
		t.Errorf("AdminID = %d, want 999", claims.AdminID)
	}
	if claims.Username != "testuser" {
		t.Errorf("Username = %q, want %q", claims.Username, "testuser")
	}
	if claims.TenantID != 55 {
		t.Errorf("TenantID = %d, want 55", claims.TenantID)
	}
}

// ---------- ParseToken error cases ----------

func TestParseToken_ExpiredToken(t *testing.T) {
	setupTestViper()
	// Override expiration to a negative value so the token is immediately expired.
	viper.Set("jwt.expiration", -1)

	token, err := GenerateToken(1, "admin", 1)
	if err != nil {
		t.Fatalf("GenerateToken: %v", err)
	}

	_, err = ParseToken(token)
	if err == nil {
		t.Fatal("expected error for expired token, got nil")
	}
	if err != ErrTokenExpired {
		t.Errorf("error = %v, want ErrTokenExpired", err)
	}
}

func TestParseToken_MalformedToken(t *testing.T) {
	setupTestViper()

	_, err := ParseToken("this.is.not.a.jwt")
	if err == nil {
		t.Fatal("expected error for malformed token, got nil")
	}
	if err != ErrTokenMalformed {
		t.Errorf("error = %v, want ErrTokenMalformed", err)
	}
}

func TestParseToken_EmptyToken(t *testing.T) {
	setupTestViper()

	_, err := ParseToken("")
	if err == nil {
		t.Fatal("expected error for empty token, got nil")
	}
}

func TestParseToken_RandomString(t *testing.T) {
	setupTestViper()

	_, err := ParseToken("random-garbage-not-a-jwt")
	if err == nil {
		t.Fatal("expected error for random string token, got nil")
	}
}

func TestParseToken_WrongSecret(t *testing.T) {
	setupTestViper()

	token, err := GenerateToken(1, "admin", 1)
	if err != nil {
		t.Fatalf("GenerateToken: %v", err)
	}

	// Change the secret so ParseToken uses a different key.
	viper.Set("jwt.secret", "wrong-secret-key")

	_, err = ParseToken(token)
	if err == nil {
		t.Fatal("expected error when parsing token with wrong secret, got nil")
	}
}

// ---------- Table-driven: various invalid tokens ----------

func TestParseToken_InvalidTokens_TableDriven(t *testing.T) {
	setupTestViper()

	tests := []struct {
		name  string
		token string
	}{
		{"empty string", ""},
		{"single dot", "."},
		{"two dots", ".."},
		{"random chars", "abc.def.ghi"},
		{"partial JWT", "eyJhbGciOiJIUzI1NiJ9.bogus"},
		{"numeric payload", "eyJhbGciOiJIUzI1NiJ9.12345.signature"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := ParseToken(tt.token)
			if err == nil {
				t.Errorf("ParseToken(%q) expected error, got nil", tt.token)
			}
		})
	}
}

// ---------- Token NotValidYet ----------

func TestParseToken_NotValidYet(t *testing.T) {
	setupTestViper()

	// Build a token whose NotBefore is in the future by constructing claims manually.
	claims := Claims{
		AdminID:  1,
		Username: "admin",
		TenantID: 1,
		RegisteredClaims: jwt.RegisteredClaims{
			NotBefore: jwt.NewNumericDate(time.Now().Add(1 * time.Hour)),
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(2 * time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			Issuer:    "admin-gateway",
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenString, err := token.SignedString([]byte(viper.GetString("jwt.secret")))
	if err != nil {
		t.Fatalf("failed to sign token: %v", err)
	}

	_, err = ParseToken(tokenString)
	if err == nil {
		t.Fatal("expected error for not-valid-yet token, got nil")
	}
	if err != ErrTokenNotValidYet {
		t.Errorf("error = %v, want ErrTokenNotValidYet", err)
	}
}

// ---------- RefreshToken ----------

func TestRefreshToken_ValidToken(t *testing.T) {
	setupTestViper()

	token, err := GenerateToken(10, "refresh-user", 5)
	if err != nil {
		t.Fatalf("GenerateToken: %v", err)
	}

	newToken, err := RefreshToken(token)
	if err != nil {
		t.Fatalf("RefreshToken returned unexpected error: %v", err)
	}
	if newToken == "" {
		t.Fatal("RefreshToken returned empty token")
	}
	claims, err := ParseToken(newToken)
	if err != nil {
		t.Fatalf("ParseToken on refreshed token: %v", err)
	}
	if claims.AdminID != 10 {
		t.Errorf("AdminID = %d, want 10", claims.AdminID)
	}
	if claims.Username != "refresh-user" {
		t.Errorf("Username = %q, want %q", claims.Username, "refresh-user")
	}
	if claims.TenantID != 5 {
		t.Errorf("TenantID = %d, want 5", claims.TenantID)
	}
}

func TestRefreshToken_ExpiredToken(t *testing.T) {
	setupTestViper()
	viper.Set("jwt.expiration", -1)

	token, err := GenerateToken(1, "admin", 1)
	if err != nil {
		t.Fatalf("GenerateToken: %v", err)
	}

	_, err = RefreshToken(token)
	if err == nil {
		t.Fatal("RefreshToken with expired token should return error")
	}
}

func TestRefreshToken_InvalidToken(t *testing.T) {
	setupTestViper()

	_, err := RefreshToken("invalid.token.string")
	if err == nil {
		t.Fatal("RefreshToken with invalid token should return error")
	}
}

// ---------- Issuer ----------

func TestTokenIssuer(t *testing.T) {
	setupTestViper()

	token, err := GenerateToken(1, "admin", 1)
	if err != nil {
		t.Fatalf("GenerateToken: %v", err)
	}

	claims, err := ParseToken(token)
	if err != nil {
		t.Fatalf("ParseToken: %v", err)
	}

	if claims.Issuer != "admin-gateway" {
		t.Errorf("Issuer = %q, want %q", claims.Issuer, "admin-gateway")
	}
}
