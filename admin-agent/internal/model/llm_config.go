package model

import (
	"database/sql/driver"
	"encoding/json"
	"time"
)

// LLMProvider LLM提供商类型
type LLMProvider string

const (
	ProviderAnthropic LLMProvider = "anthropic"
	ProviderOpenAI    LLMProvider = "openai"
	ProviderAzure     LLMProvider = "azure"
	ProviderCustom    LLMProvider = "custom"
)

// ProviderStatus 提供商状态
type ProviderStatus string

const (
	ProviderStatusHealthy   ProviderStatus = "healthy"
	ProviderStatusDegraded  ProviderStatus = "degraded"
	ProviderStatusUnhealthy ProviderStatus = "unhealthy"
)

// SysLLMConfig 大模型配置 (对应sys_llm_config表)
type SysLLMConfig struct {
	ID           int64          `json:"id" gorm:"primaryKey"`
	Name         string         `json:"name" gorm:"size:100;not null"`
	Provider     LLMProvider    `json:"provider" gorm:"size:50;not null"`
	BaseURL      string         `json:"base_url" gorm:"size:255;not null"`
	APIKey       string         `json:"api_key" gorm:"size:255;not null"` // AES加密存储
	ModelName    string         `json:"model_name" gorm:"size:100;not null"`
	MaxTokens    int            `json:"max_tokens" gorm:"default:4096"`
	Temperature  float64        `json:"temperature" gorm:"type:decimal(3,2);default:0.7"`
	ExtraConfig  JSONB          `json:"extra_config" gorm:"type:json"`
	Priority     int            `json:"priority" gorm:"default:0"`     // 优先级，数字越小优先级越高
	Weight       int            `json:"weight" gorm:"default:100"`     // 权重，用于负载均衡
	IsDefault    int            `json:"is_default" gorm:"default:0"`
	Status       int            `json:"status" gorm:"default:1"`       // 0禁用 1启用
	TenantID     int64          `json:"tenant_id" gorm:"default:0;index"`
	AdminID      int64          `json:"admin_id" gorm:"not null"`
	CreateTime   int64          `json:"create_time" gorm:"not null"`
	UpdateTime   int64          `json:"update_time" gorm:"not null"`
}

// TableName 指定表名
func (SysLLMConfig) TableName() string {
	return "sys_llm_config"
}

// BeforeCreate GORM钩子
func (c *SysLLMConfig) BeforeCreate() error {
	if c.CreateTime == 0 {
		c.CreateTime = time.Now().UnixMilli()
	}
	if c.UpdateTime == 0 {
		c.UpdateTime = time.Now().UnixMilli()
	}
	return nil
}

// BeforeUpdate GORM钩子
func (c *SysLLMConfig) BeforeUpdate() error {
	c.UpdateTime = time.Now().UnixMilli()
	return nil
}

// JSONB 自定义JSON类型
type JSONB map[string]interface{}
// JSON 是 JSONB 的别名，用于 gorm type:jsonb 标签
type JSON = JSONB

// Value 实现driver.Valuer接口
func (j JSONB) Value() (driver.Value, error) {
	if j == nil {
		return nil, nil
	}
	return json.Marshal(j)
}

// Scan 实现sql.Scanner接口
func (j *JSONB) Scan(value interface{}) error {
	if value == nil {
		*j = nil
		return nil
	}
	bytes, ok := value.([]byte)
	if !ok {
		return nil
	}
	return json.Unmarshal(bytes, j)
}

// ProviderHealthMetric 提供商健康指标 (内存中跟踪)
type ProviderHealthMetric struct {
	ConfigID          int64         `json:"config_id"`
	Provider          LLMProvider   `json:"provider"`
	Status            ProviderStatus `json:"status"`
	TotalRequests     int64         `json:"total_requests"`
	SuccessRequests   int64         `json:"success_requests"`
	FailedRequests    int64         `json:"failed_requests"`
	TotalLatency      int64         `json:"total_latency_ms"` // 累计延迟(毫秒)
	AvgLatency        int64         `json:"avg_latency_ms"`   // 平均延迟
	LastSuccessTime   int64         `json:"last_success_time"`
	LastFailTime      int64         `json:"last_fail_time"`
	LastFailReason    string        `json:"last_fail_reason"`
	ConsecutiveFails  int           `json:"consecutive_fails"` // 连续失败次数
	CircuitOpenTime   int64         `json:"circuit_open_time"` // 熔断器打开时间
	CircuitState      CircuitState  `json:"circuit_state"`
}

// CircuitState 熔断器状态
type CircuitState string

const (
	CircuitClosed   CircuitState = "closed"   // 正常状态
	CircuitOpen     CircuitState = "open"     // 熔断状态
	CircuitHalfOpen CircuitState = "half_open" // 半开状态
)

// LLMRequest LLM请求参数
type LLMRequest struct {
	Model       string        `json:"model"`
	MaxTokens   int           `json:"max_tokens"`
	Temperature float64       `json:"temperature,omitempty"`
	Messages    []LLMMessage  `json:"messages"`
	System      string        `json:"system,omitempty"`
	Stream      bool          `json:"stream"`
}

// LLMMessage LLM消息
type LLMMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// LLMResponse LLM响应
type LLMResponse struct {
	ID           string           `json:"id"`
	Provider     LLMProvider      `json:"provider"`
	Model        string           `json:"model"`
	Content      string           `json:"content"`
	Usage        LLMUsage         `json:"usage"`
	ProviderID   int64            `json:"provider_id"` // 实际响应的提供商ID
}

// LLMUsage Token使用统计
type LLMUsage struct {
	InputTokens  int `json:"input_tokens"`
	OutputTokens int `json:"output_tokens"`
}

// FailoverLog 故障转移日志 (用于调试和审计)
type FailoverLog struct {
	ID              int64        `json:"id"`
	SessionID       string       `json:"session_id" gorm:"size:64;index"`
	OriginalConfigID int64       `json:"original_config_id"`
	FailoverConfigID int64       `json:"failover_config_id"`
	Reason          string       `json:"reason" gorm:"size:255"`
	OriginalError   string       `json:"original_error" gorm:"type:text"`
	RetryCount      int          `json:"retry_count"`
	TenantID        int64        `json:"tenant_id" gorm:"index"`
	CreateTime      int64        `json:"create_time" gorm:"not null;index"`
}

// TableName 指定表名
func (FailoverLog) TableName() string {
	return "agent_failover_log"
}
