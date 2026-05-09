package protocol

import (
	"encoding/json"
	"time"
)

// 消息类型
const (
	TypeEvent   = "event"   // 事件消息（服务端推送）
	TypeRequest = "request" // 请求消息（需要响应）
	TypeResponse = "response" // 响应消息
	TypePing    = "ping"    // 心跳请求
	TypePong    = "pong"    // 心跳响应
	TypeError   = "error"   // 错误消息
)

// 操作类型
const (
	ActionSubscribe   = "subscribe"   // 订阅频道/房间
	ActionUnsubscribe = "unsubscribe" // 取消订阅
	ActionPublish     = "publish"     // 发布消息到频道
	ActionBroadcast   = "broadcast"   // 广播消息
	ActionJoin        = "join"        // 加入房间
	ActionLeave       = "leave"       // 离开房间
	ActionDirect      = "direct"      // 点对点消息
)

// 预定义事件
const (
	EventConnected    = "connected"
	EventDisconnected = "disconnected"
	EventJoined       = "joined"
	EventLeft         = "left"
	EventError        = "error"
)

// 预定义错误码
const (
	CodeSuccess         = 0
	CodeBadRequest      = 40000
	CodeUnauthorized    = 40100
	CodeForbidden       = 40300
	CodeNotFound        = 40400
	CodeRateLimit       = 42900
	CodeInternalError   = 50000
	CodeServiceUnavailable = 50300
)

// Message WebSocket 消息结构
type Message struct {
	Type      string          `json:"type"`                // 消息类型
	Action    string          `json:"action,omitempty"`    // 操作类型
	Channel   string          `json:"channel,omitempty"`   // 频道名称
	Room      string          `json:"room,omitempty"`      // 房间ID
	Target    string          `json:"target,omitempty"`    // 目标客户端ID（点对点）
	Event     string          `json:"event,omitempty"`     // 事件名称
	Data      json.RawMessage `json:"data,omitempty"`      // 消息数据
	Timestamp int64           `json:"timestamp"`           // 时间戳（毫秒）
	Sequence  int64           `json:"sequence,omitempty"`  // 序列号
	RequestID string          `json:"requestId,omitempty"` // 请求ID（用于请求-响应模式）
}

// Response 响应消息
type Response struct {
	Code      int             `json:"code"`
	Message   string          `json:"message"`
	Data      json.RawMessage `json:"data,omitempty"`
	Timestamp int64           `json:"timestamp"`
	RequestID string          `json:"requestId,omitempty"`
}

// ErrorResponse 错误响应
type ErrorResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Detail  string `json:"detail,omitempty"`
}

// NewMessage 创建新消息
func NewMessage(msgType, action string) *Message {
	return &Message{
		Type:      msgType,
		Action:    action,
		Timestamp: time.Now().UnixMilli(),
	}
}

// NewEvent 创建事件消息
func NewEvent(event string, data interface{}) *Message {
	m := &Message{
		Type:      TypeEvent,
		Event:     event,
		Timestamp: time.Now().UnixMilli(),
	}
	if data != nil {
		m.Data, _ = json.Marshal(data)
	}
	return m
}

// NewResponse 创建响应消息
func NewResponse(code int, message string, data interface{}, requestID string) *Message {
	m := &Message{
		Type:      TypeResponse,
		Timestamp: time.Now().UnixMilli(),
		RequestID: requestID,
	}
	m.Data, _ = json.Marshal(Response{
		Code:      code,
		Message:   message,
		Data:      marshalData(data),
		Timestamp: m.Timestamp,
		RequestID: requestID,
	})
	return m
}

// NewError 创建错误消息
func NewError(code int, message, detail, requestID string) *Message {
	m := &Message{
		Type:      TypeError,
		Timestamp: time.Now().UnixMilli(),
		RequestID: requestID,
	}
	m.Data, _ = json.Marshal(ErrorResponse{
		Code:    code,
		Message: message,
		Detail:  detail,
	})
	return m
}

// NewPong 创建心跳响应
func NewPong() *Message {
	return &Message{
		Type:      TypePong,
		Timestamp: time.Now().UnixMilli(),
	}
}

// ParseMessage 解析消息
func ParseMessage(data []byte) (*Message, error) {
	var msg Message
	if err := json.Unmarshal(data, &msg); err != nil {
		return nil, err
	}
	if msg.Timestamp == 0 {
		msg.Timestamp = time.Now().UnixMilli()
	}
	return &msg, nil
}

// ToJSON 序列化为JSON
func (m *Message) ToJSON() ([]byte, error) {
	return json.Marshal(m)
}

func marshalData(data interface{}) json.RawMessage {
	if data == nil {
		return nil
	}
	b, _ := json.Marshal(data)
	return b
}
