package model

import "time"

// GitConfig Git配置
type GitConfig struct {
	ID            int64  `json:"id" gorm:"primaryKey;autoIncrement"`
	Name          string `json:"name" gorm:"size:100;not null;comment:配置名称"`
	Platform      string `json:"platform" gorm:"size:20;not null;comment:平台"`
	BaseURL       string `json:"base_url" gorm:"column:base_url;size:255;not null;comment:Git服务URL"`
	AccessToken   string `json:"-" gorm:"column:access_token;size:255;not null;comment:Access Token(AES加密)"`
	WebhookSecret string `json:"webhook_secret,omitempty" gorm:"column:webhook_secret;size:255;comment:Webhook密钥"`
	SSHKey        string `json:"-" gorm:"column:ssh_key;type:text;comment:SSH私钥"`
	ExtraConfig   *string `json:"extra_config,omitempty" gorm:"type:json;comment:额外配置"`
	IsDefault     int    `json:"is_default" gorm:"column:is_default;default:0;comment:是否默认"`
	Status        int    `json:"status" gorm:"default:1;comment:状态:0禁用1启用"`
	TenantID      int64  `json:"tenant_id" gorm:"column:tenant_id;default:0;comment:租户ID"`
	AdminID       int64  `json:"admin_id" gorm:"column:admin_id;not null;comment:创建者ID"`
	CreateTime    int64  `json:"create_time" gorm:"column:create_time;not null;comment:创建时间"`
	UpdateTime    int64  `json:"update_time" gorm:"column:update_time;not null;comment:更新时间"`
}

// TableName 设置表名
func (GitConfig) TableName() string {
	return "sys_git_config"
}

// BeforeCreate 创建前钩子
func (g *GitConfig) BeforeCreate() error {
	now := time.Now().UnixMilli()
	if g.CreateTime == 0 {
		g.CreateTime = now
	}
	if g.UpdateTime == 0 {
		g.UpdateTime = now
	}
	return nil
}

// BeforeUpdate 更新前钩子
func (g *GitConfig) BeforeUpdate() error {
	g.UpdateTime = time.Now().UnixMilli()
	return nil
}

// GitConfigCreate 创建请求
type GitConfigCreate struct {
	Name          string  `json:"name" binding:"required"`
	Platform      string  `json:"platform" binding:"required"`
	BaseURL       string  `json:"base_url" binding:"required"`
	AccessToken   string  `json:"access_token" binding:"required"`
	WebhookSecret string  `json:"webhook_secret"`
	SSHKey        string  `json:"ssh_key"`
	ExtraConfig   *string `json:"extra_config"`
	IsDefault     int     `json:"is_default"`
}

// GitConfigUpdate 更新请求
type GitConfigUpdate struct {
	Name          string  `json:"name"`
	BaseURL       string  `json:"base_url"`
	AccessToken   string  `json:"access_token"`
	WebhookSecret string  `json:"webhook_secret"`
	SSHKey        string  `json:"ssh_key"`
	ExtraConfig   *string `json:"extra_config"`
	IsDefault     *int    `json:"is_default"`
	Status        *int    `json:"status"`
}

// GitConfigResponse 响应结构
type GitConfigResponse struct {
	ID            int64   `json:"id"`
	Name          string  `json:"name"`
	Platform      string  `json:"platform"`
	BaseURL       string  `json:"base_url"`
	WebhookSecret string  `json:"webhook_secret,omitempty"`
	ExtraConfig   *string `json:"extra_config,omitempty"`
	IsDefault     int     `json:"is_default"`
	Status        int     `json:"status"`
	TenantID      int64   `json:"tenant_id"`
	CreateTime    int64   `json:"create_time"`
	UpdateTime    int64   `json:"update_time"`
}

// ToResponse 转换为响应结构
func (g *GitConfig) ToResponse() *GitConfigResponse {
	return &GitConfigResponse{
		ID:            g.ID,
		Name:          g.Name,
		Platform:      g.Platform,
		BaseURL:       g.BaseURL,
		WebhookSecret: g.WebhookSecret,
		ExtraConfig:   g.ExtraConfig,
		IsDefault:     g.IsDefault,
		Status:        g.Status,
		TenantID:      g.TenantID,
		CreateTime:    g.CreateTime,
		UpdateTime:    g.UpdateTime,
	}
}
