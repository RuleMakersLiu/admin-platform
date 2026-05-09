package service

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"

	"admin-agent/internal/model"
)

// ========== 业务异常定义 ==========

// BusinessException 业务异常
type BusinessException struct {
	Message    string
	Code       int
	StatusCode int
}

func (e *BusinessException) Error() string {
	return e.Message
}

// NewBusinessException 创建业务异常
func NewBusinessException(message string, code int) *BusinessException {
	return &BusinessException{
		Message:    message,
		Code:       code,
		StatusCode: 400,
	}
}

// ========== 查询参数定义 ==========

// MarketQueryParams 市场查询参数
type MarketQueryParams struct {
	Page       int    `json:"page"`
	PageSize   int    `json:"page_size"`
	Keyword    string `json:"keyword"`
	CategoryID string `json:"category_id"`
	Status     string `json:"status"`
	AuthorID   int64  `json:"author_id"`
	SortBy     string `json:"sort_by"`     // downloads, rating, newest, views
	Featured   *bool  `json:"featured"`
	TenantID   int64  `json:"tenant_id"`
}

// MarketListResult 市场列表结果
type MarketListResult struct {
	Items      []MarketSkillItem `json:"items"`
	Total      int64             `json:"total"`
	Page       int               `json:"page"`
	PageSize   int               `json:"page_size"`
	TotalPages int               `json:"total_pages"`
}

// MarketSkillItem 市场技能项(列表显示用)
type MarketSkillItem struct {
	ID            uuid.UUID `json:"id"`
	Name          string    `json:"name"`
	DisplayName   string    `json:"display_name"`
	Description   string    `json:"description"`
	CategoryID    uuid.UUID `json:"category_id"`
	CategoryName  string    `json:"category_name"`
	Tags          []string  `json:"tags"`
	Icon          string    `json:"icon"`
	Version       string    `json:"version"`
	AuthorID      int64     `json:"author_id"`
	AuthorName    string    `json:"author_name"`
	DownloadCount int64     `json:"download_count"`
	ViewCount     int64     `json:"view_count"`
	RatingAvg     float64   `json:"rating_avg"`
	RatingCount   int64     `json:"rating_count"`
	Featured      bool      `json:"featured"`
	PublishedAt   *int64    `json:"published_at"`
	CreatedAt     int64     `json:"created_at"`
}

// ========== 服务定义 ==========

// SkillMarketService 技能市场服务
type SkillMarketService struct {
	db          *gorm.DB
	skillService *SkillService
}

// NewSkillMarketService 创建技能市场服务
func NewSkillMarketService(db *gorm.DB, skillService *SkillService) *SkillMarketService {
	return &SkillMarketService{
		db:           db,
		skillService: skillService,
	}
}

// ========== 市场技能 CRUD ==========

// PublishSkill 发布技能到市场
// 将私有技能发布到市场供其他用户下载使用
func (s *SkillMarketService) PublishSkill(ctx context.Context, req *PublishSkillRequest) (*model.SkillMarket, error) {
	// 1. 验证原始技能是否存在
	skill, err := s.skillService.Get(req.SkillID)
	if err != nil {
		return nil, NewBusinessException("技能不存在", 40401)
	}

	// 2. 检查是否已发布
	var existingCount int64
	s.db.Model(&model.SkillMarket{}).Where("skill_id = ?", req.SkillID).Count(&existingCount)
	if existingCount > 0 {
		return nil, NewBusinessException("该技能已发布到市场", 40402)
	}

	// 3. 验证分类是否存在
	var category model.SkillCategory
	if err := s.db.First(&category, "id = ?", req.CategoryID).Error; err != nil {
		return nil, NewBusinessException("分类不存在", 40403)
	}

	// 4. 创建市场技能记录
	marketSkill := &model.SkillMarket{
		ID:           uuid.New(),
		SkillID:      skill.ID,
		Name:         skill.Name,
		DisplayName:  req.DisplayName,
		Description:  req.Description,
		CategoryID:   req.CategoryID,
		CategoryName: category.Name,
		Tags:         strings.Join(req.Tags, ","),
		Icon:         skill.Icon,
		Version:      req.Version,
		SkillConfig:  skill.Config,
		InputSchema:  skill.InputSchema,
		OutputSchema: skill.OutputSchema,
		HandlerType:  skill.HandlerType,
		HandlerURL:   skill.HandlerURL,
		ScriptPath:   skill.ScriptPath,
		BuiltinFunc:  skill.BuiltinFunc,
		Timeout:      skill.Timeout,
		AuthorID:     req.AuthorID,
		AuthorName:   req.AuthorName,
		TenantID:     req.TenantID,
		Status:       model.MarketSkillDraft,
	}

	// 5. 如果直接提交审核
	if req.SubmitForReview {
		marketSkill.Status = model.MarketSkillPending
	}

	// 6. 保存到数据库
	if err := s.db.Create(marketSkill).Error; err != nil {
		return nil, fmt.Errorf("保存市场技能失败: %w", err)
	}

	// 7. 更新分类技能数量
	s.db.Model(&category).UpdateColumn("skill_count", gorm.Expr("skill_count + 1"))

	return marketSkill, nil
}

// GetMarketSkill 获取市场技能详情
func (s *SkillMarketService) GetMarketSkill(ctx context.Context, id uuid.UUID, tenantID int64) (*model.SkillMarket, error) {
	var skill model.SkillMarket
	err := s.db.Where("id = ? AND (tenant_id = ? OR status = ?)", id, tenantID, model.MarketSkillPublished).
		First(&skill).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, NewBusinessException("技能不存在", 40404)
		}
		return nil, fmt.Errorf("查询技能失败: %w", err)
	}

	// 增加浏览次数
	go s.db.Model(&skill).UpdateColumn("view_count", gorm.Expr("view_count + 1"))

	return &skill, nil
}

// ListMarketSkills 列出市场技能
// 支持分页、搜索、分类筛选、排序
func (s *SkillMarketService) ListMarketSkills(ctx context.Context, params *MarketQueryParams) (*MarketListResult, error) {
	// 设置默认值
	if params.Page <= 0 {
		params.Page = 1
	}
	if params.PageSize <= 0 {
		params.PageSize = 20
	}
	if params.PageSize > 100 {
		params.PageSize = 100
	}

	query := s.db.Model(&model.SkillMarket{})

	// 只显示已发布的技能(非作者本人)
	if params.AuthorID == 0 {
		query = query.Where("status = ?", model.MarketSkillPublished)
	} else {
		// 作者查看自己的技能时可以看到所有状态
		query = query.Where("author_id = ?", params.AuthorID)
	}

	// 关键词搜索
	if params.Keyword != "" {
		keyword := "%" + params.Keyword + "%"
		query = query.Where("name LIKE ? OR display_name LIKE ? OR description LIKE ?",
			keyword, keyword, keyword)
	}

	// 分类筛选
	if params.CategoryID != "" {
		categoryID, err := uuid.Parse(params.CategoryID)
		if err == nil {
			query = query.Where("category_id = ?", categoryID)
		}
	}

	// 精选筛选
	if params.Featured != nil {
		query = query.Where("featured = ?", *params.Featured)
	}

	// 排序
	orderBy := "created_at DESC"
	switch params.SortBy {
	case "downloads":
		orderBy = "download_count DESC"
	case "rating":
		orderBy = "rating_avg DESC, rating_count DESC"
	case "views":
		orderBy = "view_count DESC"
	case "newest":
		orderBy = "created_at DESC"
	}
	query = query.Order(orderBy)

	// 计算总数
	var total int64
	if err := query.Count(&total).Error; err != nil {
		return nil, fmt.Errorf("统计技能数量失败: %w", err)
	}

	// 分页查询
	var skills []model.SkillMarket
	offset := (params.Page - 1) * params.PageSize
	if err := query.Offset(offset).Limit(params.PageSize).Find(&skills).Error; err != nil {
		return nil, fmt.Errorf("查询技能列表失败: %w", err)
	}

	// 计算总页数
	totalPages := int(total) / params.PageSize
	if int(total)%params.PageSize > 0 {
		totalPages++
	}

	// 转换响应
	items := make([]MarketSkillItem, 0, len(skills))
	for _, skill := range skills {
		items = append(items, s.toMarketSkillItem(&skill))
	}

	return &MarketListResult{
		Items:      items,
		Total:      total,
		Page:       params.Page,
		PageSize:   params.PageSize,
		TotalPages: totalPages,
	}, nil
}

// UpdateMarketSkill 更新市场技能
func (s *SkillMarketService) UpdateMarketSkill(ctx context.Context, id uuid.UUID, req *UpdateMarketSkillRequest, userID int64) (*model.SkillMarket, error) {
	// 1. 获取技能
	var skill model.SkillMarket
	if err := s.db.First(&skill, "id = ?", id).Error; err != nil {
		return nil, NewBusinessException("技能不存在", 40404)
	}

	// 2. 权限检查
	if !skill.CanUserModify(userID) {
		return nil, NewBusinessException("无权限修改此技能", 40301)
	}

	// 3. 构建更新字段
	updates := make(map[string]interface{})

	if req.DisplayName != "" {
		updates["display_name"] = req.DisplayName
	}
	if req.Description != "" {
		updates["description"] = req.Description
	}
	if req.CategoryID != uuid.Nil {
		// 验证新分类
		var category model.SkillCategory
		if err := s.db.First(&category, "id = ?", req.CategoryID).Error; err != nil {
			return nil, NewBusinessException("分类不存在", 40403)
		}
		updates["category_id"] = req.CategoryID
		updates["category_name"] = category.Name
	}
	if req.Tags != nil {
		updates["tags"] = strings.Join(req.Tags, ",")
	}
	if req.Icon != "" {
		updates["icon"] = req.Icon
	}
	if req.Version != "" {
		updates["version"] = req.Version
	}
	if req.Documentation != "" {
		updates["documentation"] = req.Documentation
	}
	if req.Changelog != "" {
		updates["changelog"] = req.Changelog
	}

	// 4. 执行更新
	if len(updates) > 0 {
		if err := s.db.Model(&skill).Updates(updates).Error; err != nil {
			return nil, fmt.Errorf("更新技能失败: %w", err)
		}
	}

	// 5. 重新查询
	s.db.First(&skill, "id = ?", id)
	return &skill, nil
}

// DeleteMarketSkill 删除/下架市场技能
func (s *SkillMarketService) DeleteMarketSkill(ctx context.Context, id uuid.UUID, userID int64) error {
	// 1. 获取技能
	var skill model.SkillMarket
	if err := s.db.First(&skill, "id = ?", id).Error; err != nil {
		return NewBusinessException("技能不存在", 40404)
	}

	// 2. 权限检查
	if !skill.CanUserModify(userID) {
		return NewBusinessException("无权限删除此技能", 40301)
	}

	// 3. 状态流转检查
	if !model.IsValidStatusTransition(skill.Status, model.MarketSkillRemoved) {
		return NewBusinessException("当前状态不允许下架", 40405)
	}

	// 4. 更新状态为已下架
	if err := s.db.Model(&skill).Update("status", model.MarketSkillRemoved).Error; err != nil {
		return fmt.Errorf("下架技能失败: %w", err)
	}

	// 5. 更新分类技能数量
	s.db.Model(&model.SkillCategory{}).
		Where("id = ?", skill.CategoryID).
		UpdateColumn("skill_count", gorm.Expr("GREATEST(skill_count - 1, 0)"))

	return nil
}

// ========== 技能下载 ==========

// DownloadSkill 下载技能
// 将市场技能复制到用户的私有技能库
func (s *SkillMarketService) DownloadSkill(ctx context.Context, marketSkillID uuid.UUID, userID, tenantID int64) (*model.Skill, error) {
	// 1. 获取市场技能
	var marketSkill model.SkillMarket
	if err := s.db.First(&marketSkill, "id = ? AND status = ?", marketSkillID, model.MarketSkillPublished).Error; err != nil {
		return nil, NewBusinessException("技能不存在或未发布", 40404)
	}

	// 2. 检查用户是否已下载
	var existingCount int64
	s.db.Model(&model.SkillDownload{}).
		Where("market_skill_id = ? AND user_id = ?", marketSkillID, userID).
		Count(&existingCount)

	// 3. 创建下载记录
	download := &model.SkillDownload{
		ID:            uuid.New(),
		MarketSkillID: marketSkillID,
		UserID:        userID,
		TenantID:      tenantID,
		SkillVersion:  marketSkill.Version,
	}
	if err := s.db.Create(download).Error; err != nil {
		// 忽略重复下载错误，继续执行
	}

	// 4. 增加下载计数
	s.db.Model(&marketSkill).UpdateColumn("download_count", gorm.Expr("download_count + 1"))

	// 5. 创建用户私有技能副本
	newSkill := &model.Skill{
		ID:           uuid.New(),
		Name:         fmt.Sprintf("%s_%s", marketSkill.Name, userID),
		DisplayName:  marketSkill.DisplayName,
		Description:  marketSkill.Description,
		Category:     marketSkill.CategoryName,
		Icon:         marketSkill.Icon,
		Version:      marketSkill.Version,
		Enabled:      true,
		Config:       marketSkill.SkillConfig,
		InputSchema:  marketSkill.InputSchema,
		OutputSchema: marketSkill.OutputSchema,
		HandlerType:  marketSkill.HandlerType,
		HandlerURL:   marketSkill.HandlerURL,
		ScriptPath:   marketSkill.ScriptPath,
		BuiltinFunc:  marketSkill.BuiltinFunc,
		Timeout:      marketSkill.Timeout,
	}

	// 6. 保存到用户技能库
	if err := s.skillService.Register(newSkill); err != nil {
		return nil, fmt.Errorf("保存技能失败: %w", err)
	}

	return newSkill, nil
}

// ========== 技能评分 ==========

// RateSkill 评分技能
func (s *SkillMarketService) RateSkill(ctx context.Context, req *RateSkillRequest) (*model.SkillRating, error) {
	// 1. 验证技能存在且已发布
	var marketSkill model.SkillMarket
	if err := s.db.First(&marketSkill, "id = ? AND status = ?", req.MarketSkillID, model.MarketSkillPublished).Error; err != nil {
		return nil, NewBusinessException("技能不存在或未发布", 40404)
	}

	// 2. 检查是否已评分
	canRate, err := model.CanUserRate(s.db, req.MarketSkillID, req.UserID)
	if err != nil {
		return nil, fmt.Errorf("检查评分状态失败: %w", err)
	}
	if !canRate {
		return nil, NewBusinessException("您已评价过此技能", 40406)
	}

	// 3. 验证评分范围
	if req.Rating < 1 || req.Rating > 5 {
		return nil, NewBusinessException("评分必须在1-5之间", 40407)
	}

	// 4. 创建评分记录
	rating := &model.SkillRating{
		ID:            uuid.New(),
		MarketSkillID: req.MarketSkillID,
		UserID:        req.UserID,
		UserName:      req.UserName,
		TenantID:      req.TenantID,
		Rating:        req.Rating,
		Comment:       req.Comment,
	}

	if err := s.db.Create(rating).Error; err != nil {
		return nil, fmt.Errorf("保存评分失败: %w", err)
	}

	// 5. 更新技能平均评分(使用事务保证一致性)
	s.updateSkillRatingStats(req.MarketSkillID)

	return rating, nil
}

// updateSkillRatingStats 更新技能评分统计
func (s *SkillMarketService) updateSkillRatingStats(marketSkillID uuid.UUID) {
	var stats struct {
		AvgRating float64
		Count     int64
	}

	s.db.Model(&model.SkillRating{}).
		Select("AVG(rating) as avg_rating, COUNT(*) as count").
		Where("market_skill_id = ?", marketSkillID).
		Scan(&stats)

	s.db.Model(&model.SkillMarket{}).
		Where("id = ?", marketSkillID).
		Updates(map[string]interface{}{
			"rating_avg":   stats.AvgRating,
			"rating_count": stats.Count,
		})
}

// ListRatings 获取技能评分列表
func (s *SkillMarketService) ListRatings(ctx context.Context, marketSkillID uuid.UUID, page, pageSize int) ([]model.SkillRating, int64, error) {
	if page <= 0 {
		page = 1
	}
	if pageSize <= 0 {
		pageSize = 10
	}

	var total int64
	s.db.Model(&model.SkillRating{}).Where("market_skill_id = ?", marketSkillID).Count(&total)

	var ratings []model.SkillRating
	offset := (page - 1) * pageSize
	err := s.db.Where("market_skill_id = ?", marketSkillID).
		Order("created_at DESC").
		Offset(offset).
		Limit(pageSize).
		Find(&ratings).Error

	if err != nil {
		return nil, 0, fmt.Errorf("查询评分列表失败: %w", err)
	}

	return ratings, total, nil
}

// ========== 技能分类 ==========

// GetCategories 获取所有技能分类
func (s *SkillMarketService) GetCategories(ctx context.Context) ([]model.SkillCategory, error) {
	var categories []model.SkillCategory
	err := s.db.Where("status = ?", 1).
		Order("sort ASC, created_at ASC").
		Find(&categories).Error
	if err != nil {
		return nil, fmt.Errorf("查询分类列表失败: %w", err)
	}
	return categories, nil
}

// CreateCategory 创建技能分类
func (s *SkillMarketService) CreateCategory(ctx context.Context, req *CreateCategoryRequest) (*model.SkillCategory, error) {
	// 检查名称和编码是否重复
	var count int64
	s.db.Model(&model.SkillCategory{}).
		Where("name = ? OR code = ?", req.Name, req.Code).
		Count(&count)
	if count > 0 {
		return nil, NewBusinessException("分类名称或编码已存在", 40408)
	}

	category := &model.SkillCategory{
		ID:          uuid.New(),
		Name:        req.Name,
		Code:        req.Code,
		Description: req.Description,
		Icon:        req.Icon,
		ParentID:    req.ParentID,
		Sort:        req.Sort,
		Status:      1,
	}

	if err := s.db.Create(category).Error; err != nil {
		return nil, fmt.Errorf("创建分类失败: %w", err)
	}

	return category, nil
}

// ========== 审核相关 ==========

// ReviewSkill 审核技能(管理员使用)
func (s *SkillMarketService) ReviewSkill(ctx context.Context, id uuid.UUID, approved bool, comment string, reviewerID int64) error {
	var skill model.SkillMarket
	if err := s.db.First(&skill, "id = ?", id).Error; err != nil {
		return NewBusinessException("技能不存在", 40404)
	}

	// 状态检查
	if skill.Status != model.MarketSkillPending {
		return NewBusinessException("只有待审核状态的技能才能审核", 40409)
	}

	newStatus := model.MarketSkillRejected
	if approved {
		newStatus = model.MarketSkillPublished
	}

	// 状态流转检查
	if !model.IsValidStatusTransition(skill.Status, newStatus) {
		return NewBusinessException("非法的状态流转", 40410)
	}

	updates := map[string]interface{}{
		"status":         newStatus,
		"review_comment": comment,
	}

	if approved {
		now := time.Now()
		updates["published_at"] = &now
	}

	if err := s.db.Model(&skill).Updates(updates).Error; err != nil {
		return fmt.Errorf("审核技能失败: %w", err)
	}

	return nil
}

// ========== 辅助方法 ==========

// toMarketSkillItem 转换为列表项
func (s *SkillMarketService) toMarketSkillItem(skill *model.SkillMarket) MarketSkillItem {
	var publishedAt *int64
	if skill.PublishedAt != nil {
		ts := skill.PublishedAt.UnixMilli()
		publishedAt = &ts
	}

	return MarketSkillItem{
		ID:            skill.ID,
		Name:          skill.Name,
		DisplayName:   skill.DisplayName,
		Description:   skill.Description,
		CategoryID:    skill.CategoryID,
		CategoryName:  skill.CategoryName,
		Tags:          s.parseTags(skill.Tags),
		Icon:          skill.Icon,
		Version:       skill.Version,
		AuthorID:      skill.AuthorID,
		AuthorName:    skill.AuthorName,
		DownloadCount: skill.DownloadCount,
		ViewCount:     skill.ViewCount,
		RatingAvg:     skill.RatingAvg,
		RatingCount:   skill.RatingCount,
		Featured:      skill.Featured,
		PublishedAt:   publishedAt,
		CreatedAt:     skill.CreatedAt.UnixMilli(),
	}
}

// parseTags 解析标签字符串
func (s *SkillMarketService) parseTags(tags string) []string {
	if tags == "" {
		return []string{}
	}
	return strings.Split(tags, ",")
}

// ========== 请求 DTO ==========

// PublishSkillRequest 发布技能请求
type PublishSkillRequest struct {
	SkillID         uuid.UUID `json:"skill_id" binding:"required"`
	DisplayName     string    `json:"display_name" binding:"required,max=100"`
	Description     string    `json:"description" binding:"required"`
	CategoryID      uuid.UUID `json:"category_id" binding:"required"`
	Tags            []string  `json:"tags"`
	Version         string    `json:"version" binding:"required,max=20"`
	Documentation   string    `json:"documentation"`
	SubmitForReview bool      `json:"submit_for_review"`
	AuthorID        int64     `json:"author_id"`
	AuthorName      string    `json:"author_name"`
	TenantID        int64     `json:"tenant_id"`
}

// UpdateMarketSkillRequest 更新技能请求
type UpdateMarketSkillRequest struct {
	DisplayName   string    `json:"display_name" binding:"max=100"`
	Description   string    `json:"description"`
	CategoryID    uuid.UUID `json:"category_id"`
	Tags          []string  `json:"tags"`
	Icon          string    `json:"icon" binding:"max=50"`
	Version       string    `json:"version" binding:"max=20"`
	Documentation string    `json:"documentation"`
	Changelog     string    `json:"changelog"`
}

// RateSkillRequest 评分请求
type RateSkillRequest struct {
	MarketSkillID uuid.UUID `json:"market_skill_id" binding:"required"`
	UserID        int64     `json:"user_id" binding:"required"`
	UserName      string    `json:"user_name" binding:"required"`
	TenantID      int64     `json:"tenant_id" binding:"required"`
	Rating        int       `json:"rating" binding:"required,min=1,max=5"`
	Comment       string    `json:"comment" binding:"max=1000"`
}

// CreateCategoryRequest 创建分类请求
type CreateCategoryRequest struct {
	Name        string     `json:"name" binding:"required,max=50"`
	Code        string     `json:"code" binding:"required,max=50"`
	Description string     `json:"description"`
	Icon        string     `json:"icon" binding:"max=50"`
	ParentID    *uuid.UUID `json:"parent_id"`
	Sort        int        `json:"sort"`
}
