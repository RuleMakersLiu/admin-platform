package handler

import (
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/spf13/viper"
)

func TestProxyToEvalRebuildsIdentityHeaders(t *testing.T) {
	gin.SetMode(gin.TestMode)
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Admin-Id") != "42" || r.Header.Get("X-Tenant-Id") != "7" || r.Header.Get("X-Username") != "trusted" {
			t.Errorf("identity headers were not rebuilt: %#v", r.Header)
		}
		if r.Header.Get("X-Internal-Service-Token") != strings.Repeat("s", 32) {
			t.Error("internal service token missing")
		}
		if r.URL.Path != "/api/eval/agent/list" {
			t.Errorf("path = %q", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"code":0}`))
	}))
	defer backend.Close()
	parsed, _ := url.Parse(backend.URL)
	_, port, _ := strings.Cut(parsed.Host, ":")
	viper.Reset()
	viper.Set("services.eval.host", parsed.Hostname())
	viper.Set("services.eval.port", port)
	viper.Set("services.eval.prefix", "/api/eval")
	viper.Set("services.eval.internal_token", strings.Repeat("s", 32))

	router := gin.New()
	router.Any("/api/eval/*action", func(c *gin.Context) {
		c.Set("adminId", int64(42))
		c.Set("tenantId", int64(7))
		c.Set("username", "trusted")
		ProxyToEval(c)
	})
	frontend := httptest.NewServer(router)
	defer frontend.Close()
	request, _ := http.NewRequest(http.MethodGet, frontend.URL+"/api/eval/agent/list", nil)
	request.Header.Set("X-Admin-Id", "999")
	request.Header.Set("X-Tenant-Id", "999")
	request.Header.Set("X-Username", "attacker")
	request.Header.Set("X-Internal-Service-Token", "attacker-token")
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("status=%d", response.StatusCode)
	}
}
