package service

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"admin-agent/internal/model"

	"gorm.io/gorm"
)

// KnowledgeService 知识库服务
// 负责知识条目的 CRUD 操作、搜索、分类管理等核心业务逻辑
type KnowledgeService struct {
	db *gorm.DB
}

// NewKnowledgeService 创建知识库服务
func NewKnowledgeService(db *gorm.DB) *KnowledgeService {
	return &KnowledgeService{db: db}
}

// ========== 查询参数定义 ==========

// KnowledgeQueryParams 知识查询参数
type KnowledgeQueryParams struct {
	Page      int
	PageSize  int
	Keyword   string
	Category  string
	AgentType string
	ProjectID int64
	Status    int
	SortBy    string
	SortOrder string
	TenantID  uint64
}

// KnowledgeSearchParams 知识搜索参数
type KnowledgeSearchParams struct {
	Keyword   string
	Page      int
	PageSize  int
	AgentType string
	Category  string
	TenantID  uint64
}

// ========== 业务方法 ==========

// CreateKnowledge 创建知识条目
func (s *KnowledgeService) CreateKnowledge(
	ctx context.Context,
	knowledge *model.AgentKnowledge,
	agentType string,
	userID, tenantID uint64,
) (*model.AgentKnowledge, error) {
	now := time.Now().UnixMilli()

	knowledgeID := fmt.Sprintf("KN%s%d", time.Now().Format("20060102150405"), now%10000)

	knowledge.KnowledgeID = knowledgeID
	knowledge.TenantID = int64(tenantID)
	knowledge.AdminID = int64(userID)
	knowledge.AgentType = agentType
	knowledge.Status = 1
	knowledge.Version = 1
	knowledge.ViewCount = 0
	knowledge.EmbeddingStatus = "pending"
	knowledge.CreateTime = now
	knowledge.UpdateTime = now
	knowledge.IsDeleted = 0

	if err := s.db.WithContext(ctx).Create(knowledge).Error; err != nil {
		return nil, fmt.Errorf("数据库插入失败: %w", err)
	}

	return knowledge, nil
}

// ListKnowledge 获取知识列表
func (s *KnowledgeService) ListKnowledge(
	ctx context.Context,
	params *KnowledgeQueryParams,
) ([]*model.AgentKnowledge, int64, error) {
	if params.Page < 1 {
		params.Page = 1
	}
	if params.PageSize < 1 || params.PageSize > 100 {
		params.PageSize = 20
	}

	query := s.db.WithContext(ctx).Model(&model.AgentKnowledge{}).
		Where("tenant_id = ? AND is_deleted = 0", params.TenantID)

	if params.Keyword != "" {
		keyword := "%" + params.Keyword + "%"
		query = query.Where("title LIKE ? OR content LIKE ?", keyword, keyword)
	}

	if params.Category != "" {
		query = query.Where("category = ?", params.Category)
	}

	if params.ProjectID > 0 {
		query = query.Where("project_id = ?", params.ProjectID)
	}

	if params.Status > 0 {
		query = query.Where("status = ?", params.Status)
	}

	var total int64
	if err := query.Count(&total).Error; err != nil {
		return nil, 0, fmt.Errorf("统计失败: %w", err)
	}

	sortBy := "create_time"
	if params.SortBy != "" {
		sortBy = params.SortBy
	}
	sortOrder := "DESC"
	if params.SortOrder == "asc" {
		sortOrder = "ASC"
	}
	query = query.Order(sortBy + " " + sortOrder)

	offset := (params.Page - 1) * params.PageSize
	var items []*model.AgentKnowledge
	if err := query.Offset(offset).Limit(params.PageSize).Find(&items).Error; err != nil {
		return nil, 0, fmt.Errorf("查询失败: %w", err)
	}

	return items, total, nil
}

// GetKnowledge 获取单个知识详情
func (s *KnowledgeService) GetKnowledge(
	ctx context.Context,
	id int64,
	tenantID uint64,
) (*model.AgentKnowledge, error) {
	var knowledge model.AgentKnowledge
	err := s.db.WithContext(ctx).
		Where("id = ? AND tenant_id = ? AND is_deleted = 0", id, tenantID).
		First(&knowledge).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, fmt.Errorf("查询失败: %w", err)
	}

	go func() {
		s.db.Model(&model.AgentKnowledge{}).
			Where("id = ?", id).
			UpdateColumn("view_count", gorm.Expr("view_count + 1"))
	}()

	return &knowledge, nil
}

// UpdateKnowledge 更新知识
func (s *KnowledgeService) UpdateKnowledge(
	ctx context.Context,
	id int64,
	updates map[string]interface{},
	userID, tenantID uint64,
) (*model.AgentKnowledge, error) {
	var knowledge model.AgentKnowledge
	err := s.db.WithContext(ctx).
		Where("id = ? AND tenant_id = ? AND is_deleted = 0", id, tenantID).
		First(&knowledge).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, fmt.Errorf("知识不存在")
		}
		return nil, fmt.Errorf("查询失败: %w", err)
	}

	updates["update_time"] = time.Now().UnixMilli()
	updates["version"] = gorm.Expr("version + 1")

	err = s.db.WithContext(ctx).
		Model(&model.AgentKnowledge{}).
		Where("id = ? AND tenant_id = ?", id, tenantID).
		Updates(updates).Error
	if err != nil {
		return nil, fmt.Errorf("更新失败: %w", err)
	}

	return s.GetKnowledge(ctx, id, tenantID)
}

// DeleteKnowledge 删除知识（软删除）
func (s *KnowledgeService) DeleteKnowledge(
	ctx context.Context,
	id int64,
	tenantID uint64,
) error {
	result := s.db.WithContext(ctx).
		Model(&model.AgentKnowledge{}).
		Where("id = ? AND tenant_id = ? AND is_deleted = 0", id, tenantID).
		Update("is_deleted", 1)
	if result.Error != nil {
		return fmt.Errorf("删除失败: %w", result.Error)
	}
	if result.RowsAffected == 0 {
		return fmt.Errorf("知识不存在或已删除")
	}
	return nil
}

// SearchKnowledge 搜索知识
func (s *KnowledgeService) SearchKnowledge(
	ctx context.Context,
	params *KnowledgeSearchParams,
) ([]*model.AgentKnowledge, int64, error) {
	if params.Keyword == "" {
		return []*model.AgentKnowledge{}, 0, nil
	}
	if params.Page < 1 {
		params.Page = 1
	}
	if params.PageSize < 1 || params.PageSize > 100 {
		params.PageSize = 20
	}

	keyword := "%" + params.Keyword + "%"
	query := s.db.WithContext(ctx).Model(&model.AgentKnowledge{}).
		Where("tenant_id = ? AND is_deleted = 0", params.TenantID).
		Where("title LIKE ? OR content LIKE ?", keyword, keyword)

	if params.Category != "" {
		query = query.Where("category = ?", params.Category)
	}

	var total int64
	if err := query.Count(&total).Error; err != nil {
		return nil, 0, fmt.Errorf("统计失败: %w", err)
	}

	offset := (params.Page - 1) * params.PageSize
	var items []*model.AgentKnowledge
	if err := query.Order("create_time DESC").
		Offset(offset).Limit(params.PageSize).
		Find(&items).Error; err != nil {
		return nil, 0, fmt.Errorf("搜索失败: %w", err)
	}

	return items, total, nil
}

// GetCategories 获取所有知识分类
func (s *KnowledgeService) GetCategories(
	ctx context.Context,
	tenantID uint64,
) ([]string, error) {
	var categories []string
	err := s.db.WithContext(ctx).
		Model(&model.AgentKnowledge{}).
		Where("tenant_id = ? AND is_deleted = 0", tenantID).
		Distinct("category").
		Pluck("category", &categories).Error
	if err != nil {
		return nil, fmt.Errorf("查询分类失败: %w", err)
	}
	return categories, nil
}

// GetTags 获取所有知识标签
func (s *KnowledgeService) GetTags(
	ctx context.Context,
	tenantID uint64,
) ([]string, error) {
	var tagStrings []string
	s.db.WithContext(ctx).
		Model(&model.AgentKnowledge{}).
		Where("tenant_id = ? AND is_deleted = 0", tenantID).
		Where("tags IS NOT NULL AND tags != ''").
		Pluck("tags", &tagStrings)

	tagSet := make(map[string]bool)
	for _, ts := range tagStrings {
		for _, tag := range strings.Split(ts, ",") {
			tag = strings.TrimSpace(tag)
			if tag != "" {
				tagSet[tag] = true
			}
		}
	}

	tags := make([]string, 0, len(tagSet))
	for tag := range tagSet {
		tags = append(tags, tag)
	}
	return tags, nil
}

// BatchDeleteKnowledge 批量删除知识
func (s *KnowledgeService) BatchDeleteKnowledge(
	ctx context.Context,
	ids []int64,
	tenantID uint64,
) error {
	if len(ids) == 0 {
		return nil
	}
	result := s.db.WithContext(ctx).
		Model(&model.AgentKnowledge{}).
		Where("id IN ? AND tenant_id = ? AND is_deleted = 0", ids, tenantID).
		Update("is_deleted", 1)
	if result.Error != nil {
		return fmt.Errorf("批量删除失败: %w", result.Error)
	}
	return nil
}

// IncrementViewCount 增加浏览计数
func (s *KnowledgeService) IncrementViewCount(ctx context.Context, id int64) {
	go func() {
		s.db.Model(&model.AgentKnowledge{}).
			Where("id = ?", id).
			UpdateColumn("view_count", gorm.Expr("view_count + 1"))
	}()
}

// ParseTags 解析标签字符串为数组
func ParseTags(tags string) []string {
	if tags == "" {
		return []string{}
	}
	return strings.Split(tags, ",")
}

// JoinTags 将标签数组合并为字符串
func JoinTags(tags []string) string {
	return strings.Join(tags, ",")
}
