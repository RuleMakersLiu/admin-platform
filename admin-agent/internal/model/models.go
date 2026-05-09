package model

import (
	"time"
)

// AgentType 分身类型
type AgentType string

const (
	AgentPM  AgentType = "PM"  // 产品经理
	AgentPJM AgentType = "PJM" // 项目经理
	AgentBE  AgentType = "BE"  // 后端开发
	AgentFE  AgentType = "FE"  // 前端开发
	AgentQA  AgentType = "QA"  // 测试分身
	AgentRPT AgentType = "RPT" // 汇报分身
	AgentUSER AgentType = "USER" // 用户
)

// MsgType 消息类型
type MsgType string

const (
	MsgTypeChat          MsgType = "chat"           // 普通对话
	MsgTypeRequirementDoc MsgType = "requirement_doc" // 需求文档
	MsgTypeTaskList      MsgType = "task_list"      // 任务列表
	MsgTypeAPIContract   MsgType = "api_contract"   // API契约
	MsgTypeCodeReview    MsgType = "code_review"    // 代码审查
	MsgTypeBugReport     MsgType = "bug_report"     // BUG报告
	MsgTypeTestReport    MsgType = "test_report"    // 测试报告
	MsgTypeDailyReport   MsgType = "daily_report"   // 日报
)

// ProjectStatus 项目状态
type ProjectStatus string

const (
	ProjectPending   ProjectStatus = "pending"
	ProjectActive    ProjectStatus = "active"
	ProjectCompleted ProjectStatus = "completed"
	ProjectCancelled ProjectStatus = "cancelled"
)

// TaskStatus 任务状态
type TaskStatus string

const (
	TaskPending    TaskStatus = "pending"
	TaskInProgress TaskStatus = "in_progress"
	TaskCompleted  TaskStatus = "completed"
	TaskBlocked    TaskStatus = "blocked"
	TaskCancelled  TaskStatus = "cancelled"
)

// BugStatus BUG状态
type BugStatus string

const (
	BugOpen       BugStatus = "open"
	BugInProgress BugStatus = "in_progress"
	BugFixed      BugStatus = "fixed"
	BugVerified   BugStatus = "verified"
	BugClosed     BugStatus = "closed"
	BugWontFix    BugStatus = "wontfix"
)

// BugSeverity BUG严重程度
type BugSeverity string

const (
	BugCritical BugSeverity = "critical"
	BugMajor    BugSeverity = "major"
	BugMinor    BugSeverity = "minor"
	BugTrivial  BugSeverity = "trivial"
)

// WorkflowStage 工作流阶段
type WorkflowStage string

const (
	StageRequirement WorkflowStage = "requirement" // 需求阶段
	StagePlanning    WorkflowStage = "planning"    // 规划阶段
	StageDevelopment WorkflowStage = "development" // 开发阶段
	StageTesting     WorkflowStage = "testing"     // 测试阶段
	StageReport      WorkflowStage = "report"      // 汇报阶段
)

// ========== 数据模型 ==========

// AgentProject 项目模型
type AgentProject struct {
	ID          int64         `json:"id" gorm:"primaryKey"`
	ProjectCode string        `json:"project_code" gorm:"uniqueIndex;size:64;not null"`
	ProjectName string        `json:"project_name" gorm:"size:255;not null"`
	Description string        `json:"description" gorm:"type:text"`
	Status      ProjectStatus `json:"status" gorm:"size:32;not null;default:pending"`
	Priority    string        `json:"priority" gorm:"size:16;not null;default:P2"`
	TenantID    int64         `json:"tenant_id" gorm:"not null;index"`
	CreatorID   int64         `json:"creator_id" gorm:"not null"`
	StartTime   int64         `json:"start_time"`
	EndTime     int64         `json:"end_time"`
	CreateTime  int64         `json:"create_time" gorm:"not null"`
	UpdateTime  int64         `json:"update_time" gorm:"not null"`
	IsDeleted   int           `json:"is_deleted" gorm:"not null;default:0"`
}

// TableName 指定表名
func (AgentProject) TableName() string {
	return "agent_project"
}

// AgentSession 会话模型
type AgentSession struct {
	ID              int64         `json:"id" gorm:"primaryKey"`
	SessionID       string        `json:"session_id" gorm:"uniqueIndex;size:64;not null"`
	ProjectID       int64         `json:"project_id" gorm:"index"`
	UserID          int64         `json:"user_id" gorm:"not null;index"`
	TenantID        int64         `json:"tenant_id" gorm:"not null;index"`
	Title           string        `json:"title" gorm:"size:255"`
	CurrentAgent    AgentType     `json:"current_agent" gorm:"size:32"`
	WorkflowStage   WorkflowStage `json:"workflow_stage" gorm:"size:32"`
	Status          string        `json:"status" gorm:"size:32;not null;default:active;index"`
	MessageCount    int           `json:"message_count" gorm:"not null;default:0"`
	LastMessageTime int64         `json:"last_message_time"`
	CreateTime      int64         `json:"create_time" gorm:"not null"`
	UpdateTime      int64         `json:"update_time" gorm:"not null"`
	IsDeleted       int           `json:"is_deleted" gorm:"not null;default:0"`
}

// TableName 指定表名
func (AgentSession) TableName() string {
	return "agent_session"
}

// AgentMessage 消息模型
type AgentMessage struct {
	ID          int64     `json:"id" gorm:"primaryKey"`
	MsgID       string    `json:"msg_id" gorm:"uniqueIndex;size:64;not null"`
	SessionID   string    `json:"session_id" gorm:"index;size:64;not null"`
	ProjectID   int64     `json:"project_id" gorm:"index"`
	FromAgent   AgentType `json:"from_agent" gorm:"size:32;not null;index"`
	ToAgent     AgentType `json:"to_agent" gorm:"size:32;not null;index"`
	MsgType     MsgType   `json:"msg_type" gorm:"size:32;not null;index"`
	Content     string    `json:"content" gorm:"type:longtext;not null"`
	Payload     string    `json:"payload" gorm:"type:longtext"`
	TokenCount  int       `json:"token_count"`
	ModelUsed   string    `json:"model_used" gorm:"size:64"`
	ParentMsgID string    `json:"parent_msg_id" gorm:"size:64"`
	CreateTime  int64     `json:"create_time" gorm:"not null;index"`
}

// TableName 指定表名
func (AgentMessage) TableName() string {
	return "agent_message"
}

// AgentTask 任务模型
type AgentTask struct {
	ID             int64      `json:"id" gorm:"primaryKey"`
	TaskID         string     `json:"task_id" gorm:"uniqueIndex;size:64;not null"`
	ProjectID      int64      `json:"project_id" gorm:"not null;index"`
	SessionID      string     `json:"session_id" gorm:"index;size:64"`
	ParentTaskID   string     `json:"parent_task_id" gorm:"size:64"`
	TaskCode       string     `json:"task_code" gorm:"size:64"`
	TaskName       string     `json:"task_name" gorm:"size:255;not null"`
	Description    string     `json:"description" gorm:"type:text"`
	TaskType       string     `json:"task_type" gorm:"size:32;not null;index"`
	Assignee       AgentType  `json:"assignee" gorm:"size:32;index"`
	Status         TaskStatus `json:"status" gorm:"size:32;not null;default:pending;index"`
	Priority       string     `json:"priority" gorm:"size:16;not null;default:P2"`
	EstimatedHours float64    `json:"estimated_hours" gorm:"type:decimal(5,1)"`
	ActualHours    float64    `json:"actual_hours" gorm:"type:decimal(5,1)"`
	Progress       int        `json:"progress" gorm:"default:0"`
	Dependencies   string     `json:"dependencies" gorm:"type:text"`
	Tags           string     `json:"tags" gorm:"size:255"`
	StartTime      int64      `json:"start_time"`
	EndTime        int64      `json:"end_time"`
	CreateTime     int64      `json:"create_time" gorm:"not null"`
	UpdateTime     int64      `json:"update_time" gorm:"not null"`
	IsDeleted      int        `json:"is_deleted" gorm:"not null;default:0"`
}

// TableName 指定表名
func (AgentTask) TableName() string {
	return "agent_task"
}

// AgentBug BUG模型
type AgentBug struct {
	ID             int64       `json:"id" gorm:"primaryKey"`
	BugID          string      `json:"bug_id" gorm:"uniqueIndex;size:64;not null"`
	ProjectID      int64       `json:"project_id" gorm:"not null;index"`
	TaskID         string      `json:"task_id" gorm:"index;size:64"`
	SessionID      string      `json:"session_id" gorm:"index;size:64"`
	BugCode        string      `json:"bug_code" gorm:"size:64"`
	BugTitle       string      `json:"bug_title" gorm:"size:255;not null"`
	Description    string      `json:"description" gorm:"type:text"`
	Severity       BugSeverity `json:"severity" gorm:"size:16;not null;default:minor;index"`
	Priority       string      `json:"priority" gorm:"size:16;not null;default:P2"`
	Status         BugStatus   `json:"status" gorm:"size:32;not null;default:open;index"`
	Reporter       AgentType   `json:"reporter" gorm:"size:32"`
	Assignee       AgentType   `json:"assignee" gorm:"size:32;index"`
	Environment    string      `json:"environment" gorm:"size:255"`
	ReproduceSteps string      `json:"reproduce_steps" gorm:"type:text"`
	ExpectedResult string      `json:"expected_result" gorm:"type:text"`
	ActualResult   string      `json:"actual_result" gorm:"type:text"`
	Attachments    string      `json:"attachments" gorm:"type:text"`
	FixNote        string      `json:"fix_note" gorm:"type:text"`
	CreateTime     int64       `json:"create_time" gorm:"not null"`
	UpdateTime     int64       `json:"update_time" gorm:"not null"`
	IsDeleted      int         `json:"is_deleted" gorm:"not null;default:0"`
}

// TableName 指定表名
func (AgentBug) TableName() string {
	return "agent_bug"
}

// AgentKnowledge 知识库模型
type AgentKnowledge struct {
	ID              int64    `json:"id" gorm:"primaryKey"`
	KnowledgeID     string   `json:"knowledge_id" gorm:"uniqueIndex;size:64;not null"`
	ProjectID       int64    `json:"project_id" gorm:"index"`
	TenantID        int64    `json:"tenant_id" gorm:"not null;index"`
	AdminID         int64    `json:"admin_id" gorm:"not null"` // 创建者ID
	Title           string   `json:"title" gorm:"size:255;not null"`
	Content         string   `json:"content" gorm:"type:longtext;not null"`
	Category        string   `json:"category" gorm:"size:50;index"` // 分类
	Tags            string   `json:"tags" gorm:"type:jsonb"`        // JSONB存储标签数组
	AgentType       string   `json:"agent_type" gorm:"size:20;index"` // 关联的分身类型
	Source          string   `json:"source" gorm:"size:255"`
	Status          int      `json:"status" gorm:"not null;default:1"` // 1-正常, 0-禁用
	Version         int      `json:"version" gorm:"not null;default:1"`
	ViewCount       int      `json:"view_count" gorm:"not null;default:0"`
	EmbeddingStatus string   `json:"embedding_status" gorm:"size:32;default:pending"` // pending, processing, completed, failed
	CreateTime      int64    `json:"create_time" gorm:"not null"`
	UpdateTime      int64    `json:"update_time" gorm:"not null"`
	IsDeleted       int      `json:"is_deleted" gorm:"not null;default:0"`
}

// TableName 指定表名
func (AgentKnowledge) TableName() string {
	return "agent_knowledge"
}

// AgentMemory 记忆模型
type AgentMemory struct {
	ID             int64     `json:"id" gorm:"primaryKey"`
	MemoryID       string    `json:"memory_id" gorm:"uniqueIndex;size:64;not null"`
	SessionID      string    `json:"session_id" gorm:"index;size:64"`
	ProjectID      int64     `json:"project_id" gorm:"index"`
	AgentType      AgentType `json:"agent_type" gorm:"size:32;not null;index"`
	MemoryType     string    `json:"memory_type" gorm:"size:32;not null;index"`
	KeyInfo        string    `json:"key_info" gorm:"size:255;not null;index"`
	Content        string    `json:"content" gorm:"type:longtext;not null"`
	Importance     int       `json:"importance" gorm:"default:50;index"`
	AccessCount    int       `json:"access_count" gorm:"default:0"`
	LastAccessTime int64     `json:"last_access_time"`
	ExpireTime     int64     `json:"expire_time"`
	TenantID       int64     `json:"tenant_id" gorm:"not null"`
	CreateTime     int64     `json:"create_time" gorm:"not null"`
	UpdateTime     int64     `json:"update_time" gorm:"not null"`
	IsDeleted      int       `json:"is_deleted" gorm:"not null;default:0"`
}

// TableName 指定表名
func (AgentMemory) TableName() string {
	return "agent_memory"
}

// AgentConfig 分身配置模型
type AgentConfig struct {
	ID            int64     `json:"id" gorm:"primaryKey"`
	ConfigID      string    `json:"config_id" gorm:"uniqueIndex;size:64;not null"`
	TenantID      int64     `json:"tenant_id" gorm:"not null;index"`
	AgentType     AgentType `json:"agent_type" gorm:"size:32;not null;index"`
	ConfigName    string    `json:"config_name" gorm:"size:255;not null"`
	SystemPrompt  string    `json:"system_prompt" gorm:"type:text"`
	ModelConfig   string    `json:"model_config" gorm:"type:text"`
	ToolConfig    string    `json:"tool_config" gorm:"type:text"`
	BehaviorConfig string   `json:"behavior_config" gorm:"type:text"`
	IsDefault     int       `json:"is_default" gorm:"not null;default:0"`
	IsActive      int       `json:"is_active" gorm:"not null;default:1"`
	CreateTime    int64     `json:"create_time" gorm:"not null"`
	UpdateTime    int64     `json:"update_time" gorm:"not null"`
	IsDeleted     int       `json:"is_deleted" gorm:"not null;default:0"`
}

// TableName 指定表名
func (AgentConfig) TableName() string {
	return "agent_config"
}

// ========== 辅助函数 ==========

// NowMillis 获取当前毫秒时间戳
func NowMillis() int64 {
	return time.Now().UnixMilli()
}
