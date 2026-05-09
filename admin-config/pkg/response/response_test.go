package response

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func init() {
	gin.SetMode(gin.TestMode)
}

// helper to create a gin context with recorder
func newTestContext() (*gin.Context, *httptest.ResponseRecorder) {
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	return c, w
}

func parseResponseBody(t *testing.T, w *httptest.ResponseRecorder) Response {
	t.Helper()
	var resp Response
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to parse response body: %v", err)
	}
	return resp
}

func parsePageData(t *testing.T, raw interface{}) PageData {
	t.Helper()
	bytes, err := json.Marshal(raw)
	if err != nil {
		t.Fatalf("failed to marshal raw data: %v", err)
	}
	var pd PageData
	if err := json.Unmarshal(bytes, &pd); err != nil {
		t.Fatalf("failed to unmarshal page data: %v", err)
	}
	return pd
}

// --- Success tests ---

func TestSuccess_WithData(t *testing.T) {
	c, w := newTestContext()

	Success(c, map[string]string{"name": "test"})

	if w.Code != http.StatusOK {
		t.Errorf("expected status %d, got %d", http.StatusOK, w.Code)
	}

	resp := parseResponseBody(t, w)
	if resp.Code != 0 {
		t.Errorf("expected code 0, got %d", resp.Code)
	}
	if resp.Message != "操作成功" {
		t.Errorf("expected message '操作成功', got %q", resp.Message)
	}
	if resp.Timestamp <= 0 {
		t.Error("expected positive timestamp")
	}
	if resp.Data == nil {
		t.Error("expected non-nil data")
	}
}

func TestSuccess_WithNilData(t *testing.T) {
	c, w := newTestContext()

	Success(c, nil)

	resp := parseResponseBody(t, w)
	if resp.Code != 0 {
		t.Errorf("expected code 0, got %d", resp.Code)
	}
}

// --- SuccessWithMsg tests ---

func TestSuccessWithMsg(t *testing.T) {
	c, w := newTestContext()

	SuccessWithMsg(c, "自定义成功", map[string]int{"count": 42})

	resp := parseResponseBody(t, w)
	if resp.Code != 0 {
		t.Errorf("expected code 0, got %d", resp.Code)
	}
	if resp.Message != "自定义成功" {
		t.Errorf("expected message '自定义成功', got %q", resp.Message)
	}
}

// --- Error tests ---

func TestError(t *testing.T) {
	c, w := newTestContext()

	Error(c, 50000, "服务器内部错误")

	// Error() uses http.StatusOK
	if w.Code != http.StatusOK {
		t.Errorf("expected status %d, got %d", http.StatusOK, w.Code)
	}

	resp := parseResponseBody(t, w)
	if resp.Code != 50000 {
		t.Errorf("expected code 50000, got %d", resp.Code)
	}
	if resp.Message != "服务器内部错误" {
		t.Errorf("expected message '服务器内部错误', got %q", resp.Message)
	}
	if resp.Data != nil {
		t.Error("expected nil data for error response")
	}
}

// --- BadRequest tests ---

func TestBadRequest(t *testing.T) {
	c, w := newTestContext()

	BadRequest(c, "参数错误")

	resp := parseResponseBody(t, w)
	if resp.Code != 40000 {
		t.Errorf("expected code 40000, got %d", resp.Code)
	}
	if resp.Message != "参数错误" {
		t.Errorf("expected message '参数错误', got %q", resp.Message)
	}
}

// --- Unauthorized tests ---

func TestUnauthorized(t *testing.T) {
	c, w := newTestContext()

	Unauthorized(c, "未授权")

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected status %d, got %d", http.StatusUnauthorized, w.Code)
	}

	resp := parseResponseBody(t, w)
	if resp.Code != 40100 {
		t.Errorf("expected code 40100, got %d", resp.Code)
	}
	if resp.Message != "未授权" {
		t.Errorf("expected message '未授权', got %q", resp.Message)
	}
}

// --- Forbidden tests ---

func TestForbidden(t *testing.T) {
	c, w := newTestContext()

	Forbidden(c, "禁止访问")

	if w.Code != http.StatusForbidden {
		t.Errorf("expected status %d, got %d", http.StatusForbidden, w.Code)
	}

	resp := parseResponseBody(t, w)
	if resp.Code != 40300 {
		t.Errorf("expected code 40300, got %d", resp.Code)
	}
	if resp.Message != "禁止访问" {
		t.Errorf("expected message '禁止访问', got %q", resp.Message)
	}
}

// --- NotFound tests ---

func TestNotFound(t *testing.T) {
	c, w := newTestContext()

	NotFound(c, "资源不存在")

	resp := parseResponseBody(t, w)
	if resp.Code != 40001 {
		t.Errorf("expected code 40001, got %d", resp.Code)
	}
	if resp.Message != "资源不存在" {
		t.Errorf("expected message '资源不存在', got %q", resp.Message)
	}
}

// --- InternalServerError tests ---

func TestInternalServerError(t *testing.T) {
	c, w := newTestContext()

	InternalServerError(c, "内部错误")

	resp := parseResponseBody(t, w)
	if resp.Code != 50000 {
		t.Errorf("expected code 50000, got %d", resp.Code)
	}
	if resp.Message != "内部错误" {
		t.Errorf("expected message '内部错误', got %q", resp.Message)
	}
}

// --- SuccessWithPage tests ---

func TestSuccessWithPage(t *testing.T) {
	c, w := newTestContext()

	items := []map[string]string{
		{"id": "1", "name": "item1"},
		{"id": "2", "name": "item2"},
	}

	SuccessWithPage(c, items, 100)

	resp := parseResponseBody(t, w)
	if resp.Code != 0 {
		t.Errorf("expected code 0, got %d", resp.Code)
	}

	pd := parsePageData(t, resp.Data)
	if pd.Total != 100 {
		t.Errorf("expected total 100, got %d", pd.Total)
	}
}

// --- JSON structure verification ---

func TestResponse_JSONFieldNames(t *testing.T) {
	c, w := newTestContext()

	Success(c, "data")

	// Verify JSON field names are correct
	var raw map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &raw); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}

	expectedFields := []string{"code", "message", "data", "timestamp"}
	for _, field := range expectedFields {
		if _, ok := raw[field]; !ok {
			t.Errorf("expected JSON field %q in response", field)
		}
	}
}

func TestPageData_JSONFieldNames(t *testing.T) {
	c, w := newTestContext()

	SuccessWithPage(c, []string{"a", "b"}, 2)

	var raw map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &raw); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}

	data := raw["data"].(map[string]interface{})
	if _, ok := data["list"]; !ok {
		t.Error("expected 'list' field in page data")
	}
	if _, ok := data["total"]; !ok {
		t.Error("expected 'total' field in page data")
	}
}
