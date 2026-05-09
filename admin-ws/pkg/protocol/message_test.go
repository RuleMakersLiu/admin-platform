package protocol

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
	"time"
)

// --- NewMessage tests ---

func TestNewMessage(t *testing.T) {
	msg := NewMessage(TypeRequest, ActionSubscribe)

	if msg.Type != TypeRequest {
		t.Errorf("expected type %q, got %q", TypeRequest, msg.Type)
	}
	if msg.Action != ActionSubscribe {
		t.Errorf("expected action %q, got %q", ActionSubscribe, msg.Action)
	}
	if msg.Timestamp <= 0 {
		t.Error("expected positive timestamp")
	}
	// Timestamp should be recent (within last 5 seconds)
	now := time.Now().UnixMilli()
	if msg.Timestamp > now || msg.Timestamp < now-5000 {
		t.Errorf("timestamp %d is not recent (now=%d)", msg.Timestamp, now)
	}
}

// --- NewEvent tests ---

func TestNewEvent_WithData(t *testing.T) {
	data := map[string]string{"status": "ok"}
	msg := NewEvent(EventConnected, data)

	if msg.Type != TypeEvent {
		t.Errorf("expected type %q, got %q", TypeEvent, msg.Type)
	}
	if msg.Event != EventConnected {
		t.Errorf("expected event %q, got %q", EventConnected, msg.Event)
	}
	if msg.Data == nil {
		t.Error("expected non-nil data")
	}

	// Verify data marshaled correctly
	var parsed map[string]string
	if err := json.Unmarshal(msg.Data, &parsed); err != nil {
		t.Fatalf("failed to unmarshal data: %v", err)
	}
	if parsed["status"] != "ok" {
		t.Errorf("expected status 'ok', got %q", parsed["status"])
	}
}

func TestNewEvent_WithNilData(t *testing.T) {
	msg := NewEvent("test.event", nil)

	if msg.Data != nil {
		t.Error("expected nil data when nil is passed")
	}
}

func TestNewEvent_TimestampSet(t *testing.T) {
	before := time.Now().UnixMilli()
	msg := NewEvent("test", nil)
	after := time.Now().UnixMilli()

	if msg.Timestamp < before || msg.Timestamp > after {
		t.Errorf("timestamp %d not between %d and %d", msg.Timestamp, before, after)
	}
}

// --- NewResponse tests ---

func TestNewResponse(t *testing.T) {
	msg := NewResponse(CodeSuccess, "ok", map[string]int{"count": 5}, "req-123")

	if msg.Type != TypeResponse {
		t.Errorf("expected type %q, got %q", TypeResponse, msg.Type)
	}
	if msg.RequestID != "req-123" {
		t.Errorf("expected requestId 'req-123', got %q", msg.RequestID)
	}

	// Parse the inner response data
	var resp Response
	if err := json.Unmarshal(msg.Data, &resp); err != nil {
		t.Fatalf("failed to unmarshal response data: %v", err)
	}
	if resp.Code != CodeSuccess {
		t.Errorf("expected code %d, got %d", CodeSuccess, resp.Code)
	}
	if resp.Message != "ok" {
		t.Errorf("expected message 'ok', got %q", resp.Message)
	}
	if resp.RequestID != "req-123" {
		t.Errorf("expected requestId 'req-123', got %q", resp.RequestID)
	}
}

func TestNewResponse_WithNilData(t *testing.T) {
	msg := NewResponse(CodeSuccess, "done", nil, "req-456")

	var resp Response
	if err := json.Unmarshal(msg.Data, &resp); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}
	if resp.Code != CodeSuccess {
		t.Errorf("expected code %d, got %d", CodeSuccess, resp.Code)
	}
}

// --- NewError tests ---

func TestNewError(t *testing.T) {
	msg := NewError(CodeBadRequest, "bad request", "missing field 'name'", "req-err-1")

	if msg.Type != TypeError {
		t.Errorf("expected type %q, got %q", TypeError, msg.Type)
	}
	if msg.RequestID != "req-err-1" {
		t.Errorf("expected requestId 'req-err-1', got %q", msg.RequestID)
	}

	var errResp ErrorResponse
	if err := json.Unmarshal(msg.Data, &errResp); err != nil {
		t.Fatalf("failed to unmarshal error data: %v", err)
	}
	if errResp.Code != CodeBadRequest {
		t.Errorf("expected code %d, got %d", CodeBadRequest, errResp.Code)
	}
	if errResp.Message != "bad request" {
		t.Errorf("expected message 'bad request', got %q", errResp.Message)
	}
	if errResp.Detail != "missing field 'name'" {
		t.Errorf("expected detail, got %q", errResp.Detail)
	}
}

func TestNewError_WithEmptyDetail(t *testing.T) {
	msg := NewError(CodeInternalError, "internal error", "", "req-err-2")

	var errResp ErrorResponse
	if err := json.Unmarshal(msg.Data, &errResp); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}
	if errResp.Detail != "" {
		t.Errorf("expected empty detail, got %q", errResp.Detail)
	}
}

// --- NewPong tests ---

func TestNewPong(t *testing.T) {
	msg := NewPong()

	if msg.Type != TypePong {
		t.Errorf("expected type %q, got %q", TypePong, msg.Type)
	}
	if msg.Timestamp <= 0 {
		t.Error("expected positive timestamp")
	}
}

// --- ParseMessage tests ---

func TestParseMessage_ValidJSON(t *testing.T) {
	raw := []byte(`{
		"type": "request",
		"action": "subscribe",
		"channel": "system",
		"timestamp": 1700000000000,
		"requestId": "req-001"
	}`)

	msg, err := ParseMessage(raw)
	if err != nil {
		t.Fatalf("ParseMessage failed: %v", err)
	}
	if msg.Type != "request" {
		t.Errorf("expected type 'request', got %q", msg.Type)
	}
	if msg.Action != "subscribe" {
		t.Errorf("expected action 'subscribe', got %q", msg.Action)
	}
	if msg.Channel != "system" {
		t.Errorf("expected channel 'system', got %q", msg.Channel)
	}
	if msg.RequestID != "req-001" {
		t.Errorf("expected requestId 'req-001', got %q", msg.RequestID)
	}
	if msg.Timestamp != 1700000000000 {
		t.Errorf("expected timestamp 1700000000000, got %d", msg.Timestamp)
	}
}

func TestParseMessage_MissingTimestamp(t *testing.T) {
	raw := []byte(`{
		"type": "event",
		"event": "connected"
	}`)

	msg, err := ParseMessage(raw)
	if err != nil {
		t.Fatalf("ParseMessage failed: %v", err)
	}
	// When timestamp is 0, it should be set to current time
	if msg.Timestamp <= 0 {
		t.Error("expected timestamp to be auto-filled when missing")
	}
	now := time.Now().UnixMilli()
	if msg.Timestamp > now+1000 {
		t.Errorf("timestamp %d is in the future", msg.Timestamp)
	}
}

func TestParseMessage_InvalidJSON(t *testing.T) {
	raw := []byte(`{invalid json`)

	_, err := ParseMessage(raw)
	if err == nil {
		t.Error("expected error for invalid JSON, got nil")
	}
}

func TestParseMessage_WithData(t *testing.T) {
	raw := []byte(`{
		"type": "event",
		"event": "agent:message",
		"data": {"content": "hello"},
		"timestamp": 1700000000000
	}`)

	msg, err := ParseMessage(raw)
	if err != nil {
		t.Fatalf("ParseMessage failed: %v", err)
	}

	var data map[string]string
	if err := json.Unmarshal(msg.Data, &data); err != nil {
		t.Fatalf("failed to unmarshal data: %v", err)
	}
	if data["content"] != "hello" {
		t.Errorf("expected content 'hello', got %q", data["content"])
	}
}

// --- ToJSON tests ---

func TestMessage_ToJSON(t *testing.T) {
	msg := &Message{
		Type:      TypeEvent,
		Event:     EventConnected,
		Timestamp: 1700000000000,
	}

	bytes, err := msg.ToJSON()
	if err != nil {
		t.Fatalf("ToJSON failed: %v", err)
	}

	// Should be valid JSON
	var parsed map[string]interface{}
	if err := json.Unmarshal(bytes, &parsed); err != nil {
		t.Fatalf("ToJSON produced invalid JSON: %v", err)
	}

	if parsed["type"] != "event" {
		t.Errorf("expected type 'event', got %v", parsed["type"])
	}
	if parsed["event"] != "connected" {
		t.Errorf("expected event 'connected', got %v", parsed["event"])
	}
}

// --- Roundtrip: ToJSON -> ParseMessage ---

func TestRoundtrip_ToJSON_ParseMessage(t *testing.T) {
	original := NewMessage(TypeRequest, ActionPublish)
	original.Channel = "agent"
	original.RequestID = "round-trip-1"
	original.Data = json.RawMessage(`{"text": "hello"}`)

	jsonBytes, err := original.ToJSON()
	if err != nil {
		t.Fatalf("ToJSON failed: %v", err)
	}

	parsed, err := ParseMessage(jsonBytes)
	if err != nil {
		t.Fatalf("ParseMessage failed: %v", err)
	}

	if parsed.Type != original.Type {
		t.Errorf("type mismatch: %q vs %q", original.Type, parsed.Type)
	}
	if parsed.Action != original.Action {
		t.Errorf("action mismatch: %q vs %q", original.Action, parsed.Action)
	}
	if parsed.Channel != original.Channel {
		t.Errorf("channel mismatch: %q vs %q", original.Channel, parsed.Channel)
	}
	if parsed.RequestID != original.RequestID {
		t.Errorf("requestId mismatch: %q vs %q", original.RequestID, parsed.RequestID)
	}
	if string(parsed.Data) != string(original.Data) {
		var oc, pc bytes.Buffer
		json.Compact(&oc, original.Data)
		json.Compact(&pc, parsed.Data)
		if oc.String() != pc.String() {
			t.Errorf("data mismatch: %q vs %q", oc.String(), pc.String())
		}
	}
}

// --- Constants validation ---

func TestMessageTypeConstants(t *testing.T) {
	types := []string{TypeEvent, TypeRequest, TypeResponse, TypePing, TypePong, TypeError}
	for _, typ := range types {
		if typ == "" {
			t.Error("message type constant should not be empty")
		}
	}

	// Ensure uniqueness
	seen := make(map[string]bool)
	for _, typ := range types {
		if seen[typ] {
			t.Errorf("duplicate message type constant: %q", typ)
		}
		seen[typ] = true
	}
}

func TestActionConstants(t *testing.T) {
	actions := []string{
		ActionSubscribe, ActionUnsubscribe, ActionPublish,
		ActionBroadcast, ActionJoin, ActionLeave, ActionDirect,
	}
	for _, a := range actions {
		if a == "" {
			t.Error("action constant should not be empty")
		}
	}
}

func TestErrorCodeConstants(t *testing.T) {
	codes := []int{
		CodeSuccess, CodeBadRequest, CodeUnauthorized,
		CodeForbidden, CodeNotFound, CodeRateLimit,
		CodeInternalError, CodeServiceUnavailable,
	}

	// All codes should be unique
	seen := make(map[int]bool)
	for _, code := range codes {
		if seen[code] {
			t.Errorf("duplicate error code: %d", code)
		}
		seen[code] = true
	}
}

// --- marshalData tests (indirect via NewEvent) ---

func TestMarshalData_ComplexStructure(t *testing.T) {
	complexData := map[string]interface{}{
		"string":  "value",
		"int":     42,
		"float":   3.14,
		"bool":    true,
		"null":    nil,
		"array":   []int{1, 2, 3},
		"nested":  map[string]string{"key": "val"},
	}
	msg := NewEvent("complex", complexData)

	var parsed map[string]interface{}
	if err := json.Unmarshal(msg.Data, &parsed); err != nil {
		t.Fatalf("failed to unmarshal complex data: %v", err)
	}
}

// --- JSON serialization omits empty optional fields ---

func TestMessage_OmitEmptyFields(t *testing.T) {
	msg := NewMessage(TypePing, "")
	msg.Timestamp = 1700000000000

	jsonBytes, _ := msg.ToJSON()
	jsonStr := string(jsonBytes)

	// Optional fields should be omitted when empty
	if strings.Contains(jsonStr, `"action"`) {
		t.Error("expected 'action' to be omitted when empty")
	}
	if strings.Contains(jsonStr, `"channel"`) {
		t.Error("expected 'channel' to be omitted when empty")
	}
	if strings.Contains(jsonStr, `"requestId"`) {
		t.Error("expected 'requestId' to be omitted when empty")
	}
	if strings.Contains(jsonStr, `"data"`) {
		t.Error("expected 'data' to be omitted when empty")
	}
	// Required fields should be present
	if !strings.Contains(jsonStr, `"type"`) {
		t.Error("expected 'type' to be present")
	}
	if !strings.Contains(jsonStr, `"timestamp"`) {
		t.Error("expected 'timestamp' to be present")
	}
}
