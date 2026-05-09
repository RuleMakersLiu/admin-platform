package model

import "time"

// LLMConfig 大模型配置
type LLMConfig struct {
	ID          int64   `json:"id" gorm:"primaryKey;autoIncrement"`
	Name        string  `json:"name" gorm:"size:100;not null;comment:配置名称"`
	Provider    string  `json:"provider" gorm:"size:50;not null;comment:提供商"`
	BaseURL     string  `json:"base_url" gorm:"column:base_url;size:255;not null;comment:API Base URL"`
	APIKey      string  `json:"-" gorm:"column:api_key;size:255;not null;comment:API Key(AES加密)"`
	ModelName   string  `json:"model_name" gorm:"column:model_name;size:100;not null;comment:模型名称"`
	MaxTokens   int     `json:"max_tokens" gorm:"default:4096;comment:最大Token"`
	Temperature float64 `json:"temperature" gorm:"type:decimal(3,2);default:0.7;comment:温度参数"`
	ExtraConfig *string `json:"extra_config,omitempty" gorm:"type:json;comment:额外配置"`
	IsDefault   int     `json:"is_default" gorm:"column:is_default;default:0;comment:是否默认"`
	Status      int     `json:"status" gorm:"default:1;comment:状态:0禁用1启用"`
	TenantID    int64   `json:"tenant_id" gorm:"column:tenant_id;default:0;comment:租户ID"`
	AdminID     int64   `json:"admin_id" gorm:"column:admin_id;not null;comment:创建者ID"`
	CreateTime  int64   `json:"create_time" gorm:"column:create_time;not null;comment:创建时间"`
	UpdateTime  int64   `json:"update_time" gorm:"column:update_time;not null;comment:更新时间"`
}

// TableName 设置表名
func (LLMConfig) TableName() string {
	return "sys_llm_config"
}

// BeforeCreate 创建前钩子
func (l *LLMConfig) BeforeCreate() error {
	now := time.Now().UnixMilli()
	if l.CreateTime == 0 {
		l.CreateTime = now
	}
	if l.UpdateTime == 0 {
		l.UpdateTime = now
	}
	if l.MaxTokens == 0 {
		l.MaxTokens = 4096
	}
	if l.Temperature == 0 {
		l.Temperature = 0.7
	}
	return nil
}

// BeforeUpdate 更新前钩子
func (l *LLMConfig) BeforeUpdate() error {
	l.UpdateTime = time.Now().UnixMilli()
	return nil
}

// LLMConfigCreate 创建请求
type LLMConfigCreate struct {
	Name        string  `json:"name" binding:"required"`
	Provider    string  `json:"provider" binding:"required"`
	BaseURL     string  `json:"base_url" binding:"required"`
	APIKey      string  `json:"api_key" binding:"required"`
	ModelName   string  `json:"model_name" binding:"required"`
	MaxTokens   int     `json:"max_tokens"`
	Temperature float64 `json:"temperature"`
	ExtraConfig *string `json:"extra_config"`
	IsDefault   int     `json:"is_default"`
}

// LLMConfigUpdate 更新请求
type LLMConfigUpdate struct {
	Name        string   `json:"name"`
	BaseURL     string   `json:"base_url"`
	APIKey      string   `json:"api_key"`
	ModelName   string   `json:"model_name"`
	MaxTokens   *int     `json:"max_tokens"`
	Temperature *float64 `json:"temperature"`
	ExtraConfig *string  `json:"extra_config"`
	IsDefault   *int     `json:"is_default"`
	Status      *int     `json:"status"`
}

// LLMConfigResponse 响应结构
type LLMConfigResponse struct {
	ID          int64   `json:"id"`
	Name        string  `json:"name"`
	Provider    string  `json:"provider"`
	BaseURL     string  `json:"base_url"`
	ModelName   string  `json:"model_name"`
	MaxTokens   int     `json:"max_tokens"`
	Temperature float64 `json:"temperature"`
	ExtraConfig *string `json:"extra_config,omitempty"`
	IsDefault   int     `json:"is_default"`
	Status      int     `json:"status"`
	TenantID    int64   `json:"tenant_id"`
	CreateTime  int64   `json:"create_time"`
	UpdateTime  int64   `json:"update_time"`
}

// ToResponse 转换为响应结构
func (l *LLMConfig) ToResponse() *LLMConfigResponse {
	return &LLMConfigResponse{
		ID:          l.ID,
		Name:        l.Name,
		Provider:    l.Provider,
		BaseURL:     l.BaseURL,
		ModelName:   l.ModelName,
		MaxTokens:   l.MaxTokens,
		Temperature: l.Temperature,
		ExtraConfig: l.ExtraConfig,
		IsDefault:   l.IsDefault,
		Status:      l.Status,
		TenantID:    l.TenantID,
		CreateTime:  l.CreateTime,
		UpdateTime:  l.UpdateTime,
	}
}
