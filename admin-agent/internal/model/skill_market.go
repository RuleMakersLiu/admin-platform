package model

import (
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

// ========== 枚举定义 ==========

// MarketSkillStatus 市场技能状态
type MarketSkillStatus string

const (
	MarketSkillDraft     MarketSkillStatus = "draft"     // 草稿
	MarketSkillPending   MarketSkillStatus = "pending"   // 待审核
	MarketSkillPublished MarketSkillStatus = "published" // 已发布
	MarketSkillRejected  MarketSkillStatus = "rejected"  // 已拒绝
	MarketSkillRemoved   MarketSkillStatus = "removed"   // 已下架
)

// ========== 数据模型 ==========

// SkillMarket 技能市场 - 发布到市场的技能
type SkillMarket struct {
	ID             uuid.UUID         `gorm:"type:uuid;primaryKey" json:"id"`
	SkillID        uuid.UUID         `gorm:"type:uuid;not null;uniqueIndex" json:"skill_id"`        // 原始技能ID
	Name           string            `gorm:"size:100;not null;index" json:"name"`                   // 技能名称
	DisplayName    string            `gorm:"size:100;not null" json:"display_name"`                 // 显示名称
	Description    string            `gorm:"type:text;not null" json:"description"`                 // 技能描述
	CategoryID     uuid.UUID         `gorm:"type:uuid;not null;index" json:"category_id"`           // 分类ID
	CategoryName   string            `gorm:"size:50;not null" json:"category_name"`                 // 分类名称(冗余)
	Tags           string            `gorm:"type:text" json:"tags"`                                 // 标签,逗号分隔
	Icon           string            `gorm:"size:50" json:"icon"`                                   // 图标
	Version        string            `gorm:"size:20;not null" json:"version"`                       // 版本号
	SkillConfig    JSON              `gorm:"type:jsonb" json:"skill_config"`                        // 技能配置快照
	InputSchema    JSON              `gorm:"type:jsonb" json:"input_schema"`                        // 输入Schema
	OutputSchema   JSON              `gorm:"type:jsonb" json:"output_schema"`                       // 输出Schema
	HandlerType    string            `gorm:"size:20;not null" json:"handler_type"`                  // 处理类型
	HandlerURL     string            `gorm:"size:255" json:"handler_url"`                           // HTTP处理URL
	ScriptPath     string            `gorm:"size:255" json:"script_path"`                           // 脚本路径
	BuiltinFunc    string            `gorm:"size:100" json:"builtin_func"`                          // 内置函数
	Timeout        int               `gorm:"default:30" json:"timeout"`                             // 超时时间(秒)
	AuthorID       int64             `gorm:"not null;index" json:"author_id"`                       // 作者ID
	AuthorName     string            `gorm:"size:100;not null" json:"author_name"`                  // 作者名称
	TenantID       int64             `gorm:"not null;index" json:"tenant_id"`                       // 租户ID
	Status         MarketSkillStatus `gorm:"size:20;not null;default:draft;index" json:"status"`    // 状态
	ReviewComment  string            `gorm:"type:text" json:"review_comment"`                       // 审核意见
	DownloadCount  int64             `gorm:"not null;default:0" json:"download_count"`              // 下载次数
	ViewCount      int64             `gorm:"not null;default:0" json:"view_count"`                  // 浏览次数
	RatingAvg      float64           `gorm:"type:decimal(3,2);not null;default:0" json:"rating_avg"` // 平均评分
	RatingCount    int64             `gorm:"not null;default:0" json:"rating_count"`                // 评分数量
	Featured       bool              `gorm:"not null;default:false;index" json:"featured"`          // 是否精选
	Documentation  string            `gorm:"type:text" json:"documentation"`                        // 使用文档
	Changelog      string            `gorm:"type:text" json:"changelog"`                            // 更新日志
	CreatedAt      time.Time         `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt      time.Time         `gorm:"autoUpdateTime" json:"updated_at"`
	PublishedAt    *time.Time        `json:"published_at"` // 发布时间
}

// TableName 指定表名
func (SkillMarket) TableName() string {
	return "skill_market"
}

// SkillRating 技能评分 - 用户对技能的评分和评论
type SkillRating struct {
	ID          uuid.UUID `gorm:"type:uuid;primaryKey" json:"id"`
	MarketSkillID uuid.UUID `gorm:"type:uuid;not null;index" json:"market_skill_id"` // 市场技能ID
	UserID      int64     `gorm:"not null;index" json:"user_id"`                    // 用户ID
	UserName    string    `gorm:"size:100;not null" json:"user_name"`               // 用户名称
	TenantID    int64     `gorm:"not null;index" json:"tenant_id"`                  // 租户ID
	Rating      int       `gorm:"not null;check:rating >= 1 AND rating <= 5" json:"rating"` // 评分 1-5
	Comment     string    `gorm:"type:text" json:"comment"`                         // 评论内容
	Helpful     int       `gorm:"not null;default:0" json:"helpful"`                // 有用数
	CreatedAt   time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt   time.Time `gorm:"autoUpdateTime" json:"updated_at"`
}

// TableName 指定表名
func (SkillRating) TableName() string {
	return "skill_ratings"
}

// SkillCategory 技能分类 - 技能分类管理
type SkillCategory struct {
	ID          uuid.UUID `gorm:"type:uuid;primaryKey" json:"id"`
	Name        string    `gorm:"size:50;not null;uniqueIndex" json:"name"`        // 分类名称
	Code        string    `gorm:"size:50;not null;uniqueIndex" json:"code"`        // 分类编码
	Description string    `gorm:"type:text" json:"description"`                    // 分类描述
	Icon        string    `gorm:"size:50" json:"icon"`                             // 图标
	ParentID    *uuid.UUID `gorm:"type:uuid;index" json:"parent_id"`               // 父分类ID
	Sort        int       `gorm:"not null;default:0" json:"sort"`                  // 排序
	SkillCount  int64     `gorm:"not null;default:0" json:"skill_count"`           // 技能数量(冗余)
	Status      int       `gorm:"not null;default:1" json:"status"`                // 状态: 1启用 0禁用
	CreatedAt   time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt   time.Time `gorm:"autoUpdateTime" json:"updated_at"`
}

// TableName 指定表名
func (SkillCategory) TableName() string {
	return "skill_categories"
}

// SkillDownload 技能下载记录 - 记录用户下载技能的历史
type SkillDownload struct {
	ID           uuid.UUID `gorm:"type:uuid;primaryKey" json:"id"`
	MarketSkillID uuid.UUID `gorm:"type:uuid;not null;index" json:"market_skill_id"` // 市场技能ID
	UserID       int64     `gorm:"not null;index" json:"user_id"`                    // 下载用户ID
	TenantID     int64     `gorm:"not null;index" json:"tenant_id"`                  // 租户ID
	SkillVersion string    `gorm:"size:20;not null" json:"skill_version"`            // 下载时的版本
	CreatedAt    time.Time `gorm:"autoCreateTime" json:"created_at"`
}

// TableName 指定表名
func (SkillDownload) TableName() string {
	return "skill_downloads"
}

// ========== 辅助函数 ==========

// IsValidStatusTransition 验证状态流转是否合法
// 状态机: draft -> pending -> published/rejected -> removed
func IsValidStatusTransition(from, to MarketSkillStatus) bool {
	validTransitions := map[MarketSkillStatus][]MarketSkillStatus{
		MarketSkillDraft:     {MarketSkillPending, MarketSkillRemoved},
		MarketSkillPending:   {MarketSkillPublished, MarketSkillRejected, MarketSkillDraft},
		MarketSkillPublished: {MarketSkillRemoved},
		MarketSkillRejected:  {MarketSkillDraft, MarketSkillPending, MarketSkillRemoved},
		MarketSkillRemoved:   {MarketSkillDraft},
	}

	allowed, exists := validTransitions[from]
	if !exists {
		return false
	}

	for _, status := range allowed {
		if status == to {
			return true
		}
	}
	return false
}

// CanUserModify 检查用户是否可以修改技能
// 只有作者可以修改自己的技能
func (s *SkillMarket) CanUserModify(userID int64) bool {
	return s.AuthorID == userID
}

// CanUserRate 检查用户是否可以评分
// 已评分过的用户不能重复评分
func CanUserRate(db *gorm.DB, marketSkillID uuid.UUID, userID int64) (bool, error) {
	var count int64
	err := db.Model(&SkillRating{}).
		Where("market_skill_id = ? AND user_id = ?", marketSkillID, userID).
		Count(&count).Error
	if err != nil {
		return false, err
	}
	return count == 0, nil
}
