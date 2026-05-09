package model

import (
	"time"
)

// Event 埋点事件
type Event struct {
	// 基础信息
	EventID   string                 `json:"event_id" binding:"required"`   // 事件ID（UUID）
	EventType string                 `json:"event_type" binding:"required"` // 事件类型（page_view, click, api_call等）
	EventName string                 `json:"event_name" binding:"required"` // 事件名称
	Timestamp int64                  `json:"timestamp" binding:"required"`  // 事件时间戳（毫秒）
	Platform  string                 `json:"platform"`                      // 平台（web, app, mini_program）
	Version   string                 `json:"version"`                       // 应用版本

	// 用户信息
	UserID     string `json:"user_id"`      // 用户ID（已登录）
	DeviceID   string `json:"device_id"`    // 设备ID（未登录用户）
	SessionID  string `json:"session_id"`   // 会话ID
	TenantID   string `json:"tenant_id"`    // 租户ID
	AdminID    string `json:"admin_id"`     // 管理员ID
	Username   string `json:"username"`     // 用户名
	UserType   string `json:"user_type"`    // 用户类型（admin, user, guest）

	// 设备信息
	DeviceType    string `json:"device_type"`    // 设备类型（mobile, desktop, tablet）
	OS            string `json:"os"`             // 操作系统
	OSVersion     string `json:"os_version"`     // 操作系统版本
	Browser       string `json:"browser"`        // 浏览器
	BrowserVersion string `json:"browser_version"` // 浏览器版本
	ScreenWidth   int    `json:"screen_width"`   // 屏幕宽度
	ScreenHeight  int    `json:"screen_height"`  // 屏幕高度
	Language      string `json:"language"`       // 语言

	// 地理信息
	IP        string `json:"ip"`         // IP地址
	Country   string `json:"country"`    // 国家
	Province  string `json:"province"`   // 省份
	City      string `json:"city"`       // 城市

	// 页面信息
	PageURL       string `json:"page_url"`       // 页面URL
	PageTitle     string `json:"page_title"`     // 页面标题
	Referrer      string `json:"referrer"`       // 来源页面
	PageDuration  int64  `json:"page_duration"`  // 页面停留时长（毫秒）

	// 事件属性
	Properties map[string]interface{} `json:"properties"` // 自定义属性

	// 元数据
	Source    string `json:"source"`     // 来源（sdk, api, batch）
	UserAgent string `json:"user_agent"` // User-Agent
}

// BatchEventsRequest 批量事件请求
type BatchEventsRequest struct {
	Events []Event `json:"events" binding:"required,min=1,max=100"`
}

// BatchEventsResponse 批量事件响应
type BatchEventsResponse struct {
	Success int      `json:"success"`       // 成功数量
	Failed  int      `json:"failed"`        // 失败数量
	Errors  []string `json:"errors"`        // 错误信息
}

// TrackingHealthResponse 健康检查响应
type TrackingHealthResponse struct {
	Status          string            `json:"status"`
	KafkaConnected  bool              `json:"kafka_connected"`
	QueueSize       int               `json:"queue_size"`
	ProcessedCount  int64             `json:"processed_count"`
	FailedCount     int64             `json:"failed_count"`
	LastProcessTime time.Time         `json:"last_process_time"`
	Version         string            `json:"version"`
}

// ClickHouse Event Schema (for reference)
// CREATE TABLE tracking_events (
//     event_id String,
//     event_type String,
//     event_name String,
//     timestamp DateTime64(3),
//     platform String,
//     version String,
//     user_id String,
//     device_id String,
//     session_id String,
//     tenant_id String,
//     admin_id String,
//     username String,
//     user_type String,
//     device_type String,
//     os String,
//     os_version String,
//     browser String,
//     browser_version String,
//     screen_width UInt32,
//     screen_height UInt32,
//     language String,
//     ip String,
//     country String,
//     province String,
//     city String,
//     page_url String,
//     page_title String,
//     referrer String,
//     page_duration UInt64,
//     properties String,  // JSON string
//     source String,
//     user_agent String,
//     created_at DateTime DEFAULT now()
// ) ENGINE = MergeTree()
// PARTITION BY toYYYYMM(timestamp)
// ORDER BY (tenant_id, event_type, timestamp)
// SETTINGS index_granularity = 8192;
