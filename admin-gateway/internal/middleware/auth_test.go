package middleware

import (
	"admin-gateway/pkg/auth"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/spf13/viper"
)

// setupTestRouter creates a Gin test router with the Auth middleware applied.
func setupTestRouter() *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	return r
}

func setupTestViper() {
	viper.Reset()
	viper.Set("jwt.secret", "test-secret-key-for-unit-tests")
	viper.Set("jwt.expiration", 3600)
}

// generateTestToken is a helper that generates a valid JWT for tests.
func generateTestToken(adminID int64, username string, tenantID int64) string {
	token, err := auth.GenerateToken(adminID, username, tenantID)
	if err != nil {
		panic("failed to generate test token: " + err.Error())
	}
	return token
}

// ---------- Auth middleware: OPTIONS bypass ----------

func TestAuth_OptionsRequest_PassesThrough(t *testing.T) {
	setupTestViper()
	r := setupTestRouter()
	r.Use(Auth())
	r.OPTIONS("/api/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	w := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodOptions, "/api/test", nil)
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("OPTIONS status = %d, want %d", w.Code, http.StatusOK)
	}
}

// ---------- Auth middleware: missing Authorization header ----------

func TestAuth_MissingAuthorization_Returns401(t *testing.T) {
	setupTestViper()
	r := setupTestRouter()
	r.Use(Auth())
	r.GET("/api/protected", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	w := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodGet, "/api/protected", nil)
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want %d", w.Code, http.StatusUnauthorized)
	}
}

// ---------- Auth middleware: invalid format ----------

func TestAuth_InvalidBearerFormat_Returns401(t *testing.T) {
	setupTestViper()
	r := setupTestRouter()
	r.Use(Auth())
	r.GET("/api/protected", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	tests := []struct {
		name   string
		header string
	}{
		{"no Bearer prefix", "Token abc123"},
		{"bare token without Bearer", "abc123"},
		{"Basic auth instead", "Basic dXNlcjpwYXNz"},
		{"empty after Bearer", "Bearer "},
		{"just Bearer", "Bearer"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			w := httptest.NewRecorder()
			req, _ := http.NewRequest(http.MethodGet, "/api/protected", nil)
			req.Header.Set("Authorization", tt.header)
			r.ServeHTTP(w, req)

			if w.Code != http.StatusUnauthorized {
				t.Errorf("status = %d, want %d (header=%q)", w.Code, http.StatusUnauthorized, tt.header)
			}
		})
	}
}

// ---------- Auth middleware: invalid token ----------

func TestAuth_InvalidToken_Returns401(t *testing.T) {
	setupTestViper()
	r := setupTestRouter()
	r.Use(Auth())
	r.GET("/api/protected", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	w := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodGet, "/api/protected", nil)
	req.Header.Set("Authorization", "Bearer invalid.jwt.token")
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want %d", w.Code, http.StatusUnauthorized)
	}
}

// ---------- Auth middleware: valid token sets context ----------

func TestAuth_ValidToken_SetsContextAndPasses(t *testing.T) {
	setupTestViper()
	r := setupTestRouter()

	var capturedAdminID interface{}
	var capturedUsername interface{}
	var capturedTenantID interface{}

	r.Use(Auth())
	r.GET("/api/protected", func(c *gin.Context) {
		capturedAdminID, _ = c.Get(ContextKeyAdminID)
		capturedUsername, _ = c.Get(ContextKeyUsername)
		capturedTenantID, _ = c.Get(ContextKeyTenantID)
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	token := generateTestToken(42, "testadmin", 7)

	w := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodGet, "/api/protected", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", w.Code, http.StatusOK)
	}

	if capturedAdminID == nil {
		t.Fatal("adminId not set in context")
	}
	if capturedAdminID.(int64) != 42 {
		t.Errorf("adminId = %v, want 42", capturedAdminID)
	}

	if capturedUsername == nil {
		t.Fatal("username not set in context")
	}
	if capturedUsername.(string) != "testadmin" {
		t.Errorf("username = %v, want %q", capturedUsername, "testadmin")
	}

	if capturedTenantID == nil {
		t.Fatal("tenantId not set in context")
	}
	if capturedTenantID.(int64) != 7 {
		t.Errorf("tenantId = %v, want 7", capturedTenantID)
	}
}

// ---------- Auth middleware: expired token ----------

func TestAuth_ExpiredToken_Returns401(t *testing.T) {
	setupTestViper()
	viper.Set("jwt.expiration", -1)

	r := setupTestRouter()
	r.Use(Auth())
	r.GET("/api/protected", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	token := generateTestToken(1, "admin", 1)

	w := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodGet, "/api/protected", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want %d", w.Code, http.StatusUnauthorized)
	}
}

// ---------- Auth middleware: response body structure ----------

func TestAuth_UnauthorizedResponse_HasCorrectStructure(t *testing.T) {
	setupTestViper()
	r := setupTestRouter()
	r.Use(Auth())
	r.GET("/api/protected", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	w := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodGet, "/api/protected", nil)
	r.ServeHTTP(w, req)

	var body map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil {
		t.Fatalf("failed to parse response body: %v", err)
	}

	code, ok := body["code"].(float64)
	if !ok || code != 401 {
		t.Errorf("response code = %v, want 401", body["code"])
	}

	msg, ok := body["message"].(string)
	if !ok || msg == "" {
		t.Error("response message is missing or not a string")
	}

	ts, ok := body["timestamp"].(float64)
	if !ok || ts <= 0 {
		t.Errorf("response timestamp = %v, want positive number", body["timestamp"])
	}
}

// ---------- skipPermissionCheck ----------

func TestSkipPermissionCheck(t *testing.T) {
	tests := []struct {
		name  string
		path  string
		skip  bool
	}{
		{"login path", "/api/auth/login", true},
		{"logout path", "/api/auth/logout", true},
		{"refresh path", "/api/auth/refresh", true},
		{"auth info", "/api/auth/info", true},
		{"auth menus", "/api/auth/menus", true},
		{"auth tenants", "/api/auth/tenants", true},
		{"config prefix", "/api/config/database", true},
		{"agent chat", "/api/agent/chat", true},
		{"doc.html", "/doc.html", true},
		{"swagger", "/swagger/index.html", true},
		{"health", "/health", true},
		{"user list (not skipped)", "/api/admin/user/list", false},
		{"role list (not skipped)", "/api/admin/role/list", false},
		{"random path (not skipped)", "/api/something/else", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := skipPermissionCheck(tt.path)
			if result != tt.skip {
				t.Errorf("skipPermissionCheck(%q) = %v, want %v", tt.path, result, tt.skip)
			}
		})
	}
}

// ---------- buildPermissionIdentifier ----------

func TestBuildPermissionIdentifier(t *testing.T) {
	tests := []struct {
		name       string
		path       string
		method     string
		wantPrefix string
	}{
		{
			name:       "user list",
			path:       "/api/admin/user/list",
			method:     "GET",
			wantPrefix: "admin_user_list",
		},
		{
			name:       "role create",
			path:       "/api/admin/role/create",
			method:     "POST",
			wantPrefix: "admin_role_create",
		},
		{
			name:       "user delete with path param",
			path:       "/api/admin/user/:id",
			method:     "DELETE",
			wantPrefix: "admin_user",
		},
		{
			name:       "nested resource",
			path:       "/api/system/menu/sub/list",
			method:     "GET",
			wantPrefix: "system_menu_sub_list",
		},
		{
			name:       "deeply nested with param",
			path:       "/api/admin/tenant/:tenantId/user/:userId",
			method:     "PUT",
			wantPrefix: "admin_tenant_user",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := buildPermissionIdentifier(tt.path, tt.method)
			if result != tt.wantPrefix {
				t.Errorf("buildPermissionIdentifier(%q, %q) = %q, want %q",
					tt.path, tt.method, result, tt.wantPrefix)
			}
		})
	}
}

// ---------- helper functions ----------

func TestInt64ToString(t *testing.T) {
	tests := []struct {
		input int64
		want  string
	}{
		{0, "0"},
		{1, "1"},
		{42, "42"},
		{-1, "-1"},
		{9999999999, "9999999999"},
	}

	for _, tt := range tests {
		t.Run(tt.want, func(t *testing.T) {
			result := int64ToString(tt.input)
			if result != tt.want {
				t.Errorf("int64ToString(%d) = %q, want %q", tt.input, result, tt.want)
			}
		})
	}
}

func TestContains(t *testing.T) {
	tests := []struct {
		name  string
		slice []string
		item  string
		want  bool
	}{
		{"found", []string{"a", "b", "c"}, "b", true},
		{"not found", []string{"a", "b", "c"}, "d", false},
		{"empty slice", []string{}, "a", false},
		{"nil slice", nil, "a", false},
		{"wildcard", []string{"read", "*", "write"}, "*", true},
		{"single match", []string{"only"}, "only", true},
		{"single no match", []string{"only"}, "other", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := contains(tt.slice, tt.item)
			if result != tt.want {
				t.Errorf("contains(%v, %q) = %v, want %v", tt.slice, tt.item, result, tt.want)
			}
		})
	}
}
