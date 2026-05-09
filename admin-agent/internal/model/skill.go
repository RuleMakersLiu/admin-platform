package model

import (
	"time"

	"github.com/google/uuid"
)

// Skill 技能定义
type Skill struct {
    ID          uuid.UUID `gorm:"type:uuid;primaryKey" json:"id"`
    Name        string    `gorm:"size:100;uniqueIndex" json:"name"`
    DisplayName string    `gorm:"size:100" json:"display_name"`
    Description string    `gorm:"type:text" json:"description"`
    Category    string    `gorm:"size:50;index" json:"category"`       // weather, productivity, development, utility
    Icon        string    `gorm:"size:50" json:"icon"`
    Version     string    `gorm:"size:20" json:"version"`
    Enabled     bool      `gorm:"default:true" json:"enabled"`
    Config      JSON     `gorm:"type:jsonb" json:"config"`              // 技能特定配置
    InputSchema JSON     `gorm:"type:jsonb" json:"input_schema"`  // JSON Schema 输入定义
    OutputSchema JSON    `gorm:"type:jsonb" json:"output_schema"` // JSON Schema 输出定义
    HandlerType string    `gorm:"size:20;default:'http'" json:"handler_type"` // http, script, builtin
    HandlerURL  string    `gorm:"size:255" json:"handler_url"`   // HTTP handler URL
    ScriptPath   string    `gorm:"size:255" json:"script_path"`   // 脚本路径
    BuiltinFunc string    `gorm:"size:100" json:"builtin_func"`  // 内置函数名
    Timeout     int       `gorm:"default:30" json:"timeout"`        // 执行超时(秒)
    CreatedAt  time.Time `gorm:"autoCreateTime" json:"created_at"`
    UpdatedAt  time.Time `gorm:"autoCreateTime" json:"updated_at"`
}

// SkillExecution 技能执行记录
type SkillExecution struct {
    ID           uuid.UUID `gorm:"type:uuid;primaryKey" json:"id"`
    SkillID      uuid.UUID `gorm:"type:uuid;index" json:"skill_id"`
    SessionID   *uuid.UUID `gorm:"type:uuid;index" json:"session_id"`
    Input        JSON     `gorm:"type:jsonb" json:"input"`
    Output       JSON     `gorm:"type:jsonb" json:"output"`
    Status       string    `gorm:"size:20;default:'pending'" json:"status"` // pending, running, success, failed
    Error       string    `gorm:"type:text" json:"error"`
    Duration    int       `gorm:"default:0" json:"duration"`        // 执行时长(ms)
    CreatedAt   time.Time `gorm:"autoCreateTime" json:"created_at"`
}

// SkillConfig 技能配置
type WeatherSkillConfig struct {
    APIKey   string `json:"api_key"`
    Location string `json:"location"`
}

type TodoSkillConfig struct {
    ListID    string `json:"list_id"`
    ReminderTime string `json:"reminder_time"`
}

type CodeExecConfig struct {
    Language    string `json:"language"`
    MaxTimeout  int    `json:"max_timeout"`
    MemoryLimit int    `json:"memory_limit"`
}
