package handler

import (
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"admin-agent/internal/model"
	"admin-agent/internal/service"
)

// SkillMarketHandler 技能市场处理器
type SkillMarketHandler struct {
	marketService *service.SkillMarketService
}

// NewSkillMarketHandler 创建技能市场处理器
func NewSkillMarketHandler(marketService *service.SkillMarketService) *SkillMarketHandler {
	return &SkillMarketHandler{
		marketService: marketService,
	}
}

// ========== 请求/响应 DTO ==========

// PublishSkillReq 发布技能请求
type PublishSkillReq struct {
	SkillID         string   `json:"skill_id" binding:"required"`
	DisplayName     string   `json:"display_name" binding:"required,max=100"`
	Description     string   `json:"description" binding:"required"`
	CategoryID      string   `json:"category_id" binding:"required"`
	Tags            []string `json:"tags"`
	Version         string   `json:"version" binding:"required,max=20"`
	Documentation   string   `json:"documentation"`
	SubmitForReview bool     `json:"submit_for_review"`
}

// UpdateSkillReq 更新技能请求
type UpdateSkillReq struct {
	DisplayName   string   `json:"display_name" binding:"max=100"`
	Description   string   `json:"description"`
	CategoryID    string   `json:"category_id"`
	Tags          []string `json:"tags"`
	Icon          string   `json:"icon" binding:"max=50"`
	Version       string   `json:"version" binding:"max=20"`
	Documentation string   `json:"documentation"`
	Changelog     string   `json:"changelog"`
}

// RateSkillReq 评分请求
type RateSkillReq struct {
	Rating  int    `json:"rating" binding:"required,min=1,max=5"`
	Comment string `json:"comment" binding:"max=1000"`
}

// CreateCategoryReq 创建分类请求
type CreateCategoryReq struct {
	Name        string `json:"name" binding:"required,max=50"`
	Code        string `json:"code" binding:"required,max=50"`
	Description string `json:"description"`
	Icon        string `json:"icon" binding:"max=50"`
	ParentID    string `json:"parent_id"`
	Sort        int    `json:"sort"`
}

// MarketQueryReq 市场查询请求
type MarketQueryReq struct {
	Page       int    `form:"page" binding:"min=1"`
	PageSize   int    `form:"page_size" binding:"min=1,max=100"`
	Keyword    string `form:"keyword"`
	CategoryID string `form:"category_id"`
	SortBy     string `form:"sort_by"` // downloads, rating, newest, views
	Featured   *bool  `form:"featured"`
}

// SkillDetailResponse 技能详情响应
type SkillDetailResponse struct {
	ID            uuid.UUID   `json:"id"`
	SkillID       uuid.UUID   `json:"skill_id"`
	Name          string      `json:"name"`
	DisplayName   string      `json:"display_name"`
	Description   string      `json:"description"`
	CategoryID    uuid.UUID   `json:"category_id"`
	CategoryName  string      `json:"category_name"`
	Tags          []string    `json:"tags"`
	Icon          string      `json:"icon"`
	Version       string      `json:"version"`
	InputSchema   interface{} `json:"input_schema"`
	OutputSchema  interface{} `json:"output_schema"`
	HandlerType   string      `json:"handler_type"`
	Timeout       int         `json:"timeout"`
	AuthorID      int64       `json:"author_id"`
	AuthorName    string      `json:"author_name"`
	Status        string      `json:"status"`
	DownloadCount int64       `json:"download_count"`
	ViewCount     int64       `json:"view_count"`
	RatingAvg     float64     `json:"rating_avg"`
	RatingCount   int64       `json:"rating_count"`
	Featured      bool        `json:"featured"`
	Documentation string      `json:"documentation"`
	Changelog     string      `json:"changelog"`
	PublishedAt   *int64      `json:"published_at"`
	CreatedAt     int64       `json:"created_at"`
	UpdatedAt     int64       `json:"updated_at"`
}

// RatingListResponse 评分列表响应
type RatingListResponse struct {
	Items    []RatingItem `json:"items"`
	Total    int64        `json:"total"`
	Page     int          `json:"page"`
	PageSize int          `json:"page_size"`
}

// RatingItem 评分项
type RatingItem struct {
	ID        uuid.UUID `json:"id"`
	UserID    int64     `json:"user_id"`
	UserName  string    `json:"user_name"`
	Rating    int       `json:"rating"`
	Comment   string    `json:"comment"`
	Helpful   int       `json:"helpful"`
	CreatedAt int64     `json:"created_at"`
}

// CategoryResponse 分类响应
type CategoryResponse struct {
	ID          uuid.UUID           `json:"id"`
	Name        string              `json:"name"`
	Code        string              `json:"code"`
	Description string              `json:"description"`
	Icon        string              `json:"icon"`
	ParentID    *uuid.UUID          `json:"parent_id"`
	Sort        int                 `json:"sort"`
	SkillCount  int64               `json:"skill_count"`
	Children    []CategoryResponse  `json:"children,omitempty"`
}

// ========== API 处理函数 ==========

// ListMarketSkills 获取市场技能列表
// GET /api/v1/skills/market
// 支持分页、搜索、分类筛选、排序
func (h *SkillMarketHandler) ListMarketSkills(c *gin.Context) {
	// 处理空服务的情况
	if h.marketService == nil {
		ErrorResponse(c, 50001, "技能市场服务未初始化")
		return
	}

	var req MarketQueryReq
	if err := c.ShouldBindQuery(&req); err != nil {
		ErrorResponse(c, 40001, "参数校验失败: "+err.Error())
		return
	}

	// 设置默认值
	if req.Page == 0 {
		req.Page = 1
	}
	if req.PageSize == 0 {
		req.PageSize = 20
	}
	if req.SortBy == "" {
		req.SortBy = "newest"
	}

	// 从上下文获取租户信息
	tenantID := c.GetUint64("tenant_id")

	// 构建查询参数
	params := &service.MarketQueryParams{
		Page:     req.Page,
		PageSize: req.PageSize,
		Keyword:  req.Keyword,
		SortBy:   req.SortBy,
		Featured: req.Featured,
		TenantID: int64(tenantID),
	}

	if req.CategoryID != "" {
		params.CategoryID = req.CategoryID
	}

	// 调用服务层
	result, err := h.marketService.ListMarketSkills(c.Request.Context(), params)
	if err != nil {
		h.handleError(c, err)
		return
	}

	SuccessResponse(c, result)
}

// GetMarketSkill 获取市场技能详情
// GET /api/v1/skills/market/:id
func (h *SkillMarketHandler) GetMarketSkill(c *gin.Context) {
	if h.marketService == nil {
		ErrorResponse(c, 50001, "技能市场服务未初始化")
		return
	}

	idStr := c.Param("id")
	id, err := uuid.Parse(idStr)
	if err != nil {
		ErrorResponse(c, 40002, "无效的技能ID")
		return
	}

	// 从上下文获取租户信息
	tenantID := c.GetUint64("tenant_id")

	// 调用服务层
	skill, err := h.marketService.GetMarketSkill(c.Request.Context(), id, int64(tenantID))
	if err != nil {
		h.handleError(c, err)
		return
	}

	SuccessResponse(c, h.toSkillDetailResponse(skill))
}

// PublishSkill 发布技能到市场
// POST /api/v1/skills/market/publish
func (h *SkillMarketHandler) PublishSkill(c *gin.Context) {
	if h.marketService == nil {
		ErrorResponse(c, 50001, "技能市场服务未初始化")
		return
	}

	var req PublishSkillReq
	if err := c.ShouldBindJSON(&req); err != nil {
		ErrorResponse(c, 40001, "参数校验失败: "+err.Error())
		return
	}

	// 解析 UUID
	skillID, err := uuid.Parse(req.SkillID)
	if err != nil {
		ErrorResponse(c, 40002, "无效的技能ID")
		return
	}

	categoryID, err := uuid.Parse(req.CategoryID)
	if err != nil {
		ErrorResponse(c, 40003, "无效的分类ID")
		return
	}

	// 从上下文获取用户信息
	userID := c.GetUint64("user_id")
	tenantID := c.GetUint64("tenant_id")
	userName := c.GetString("user_name")
	if userName == "" {
		userName = "User"
	}

	// 构建请求
	publishReq := &service.PublishSkillRequest{
		SkillID:         skillID,
		DisplayName:     strings.TrimSpace(req.DisplayName),
		Description:     req.Description,
		CategoryID:      categoryID,
		Tags:            req.Tags,
		Version:         req.Version,
		Documentation:   req.Documentation,
		SubmitForReview: req.SubmitForReview,
		AuthorID:        int64(userID),
		AuthorName:      userName,
		TenantID:        int64(tenantID),
	}

	// 调用服务层
	skill, err := h.marketService.PublishSkill(c.Request.Context(), publishReq)
	if err != nil {
		h.handleError(c, err)
		return
	}

	SuccessResponse(c, gin.H{
		"id":      skill.ID,
		"message": "技能发布成功",
	})
}

// DownloadSkill 从市场下载技能
// POST /api/v1/skills/market/download/:id
func (h *SkillMarketHandler) DownloadSkill(c *gin.Context) {
	if h.marketService == nil {
		ErrorResponse(c, 50001, "技能市场服务未初始化")
		return
	}

	idStr := c.Param("id")
	id, err := uuid.Parse(idStr)
	if err != nil {
		ErrorResponse(c, 40002, "无效的技能ID")
		return
	}

	// 从上下文获取用户信息
	userID := c.GetUint64("user_id")
	tenantID := c.GetUint64("tenant_id")

	// 调用服务层
	skill, err := h.marketService.DownloadSkill(c.Request.Context(), id, int64(userID), int64(tenantID))
	if err != nil {
		h.handleError(c, err)
		return
	}

	SuccessResponse(c, gin.H{
		"skill_id": skill.ID,
		"message":  "技能下载成功",
	})
}

// RateSkill 评分技能
// POST /api/v1/skills/market/rate/:id
func (h *SkillMarketHandler) RateSkill(c *gin.Context) {
	if h.marketService == nil {
		ErrorResponse(c, 50001, "技能市场服务未初始化")
		return
	}

	idStr := c.Param("id")
	id, err := uuid.Parse(idStr)
	if err != nil {
		ErrorResponse(c, 40002, "无效的技能ID")
		return
	}

	var req RateSkillReq
	if err := c.ShouldBindJSON(&req); err != nil {
		ErrorResponse(c, 40001, "参数校验失败: "+err.Error())
		return
	}

	// 从上下文获取用户信息
	userID := c.GetUint64("user_id")
	tenantID := c.GetUint64("tenant_id")
	userName := c.GetString("user_name")
	if userName == "" {
		userName = "User"
	}

	// 构建请求
	rateReq := &service.RateSkillRequest{
		MarketSkillID: id,
		UserID:        int64(userID),
		UserName:      userName,
		TenantID:      int64(tenantID),
		Rating:        req.Rating,
		Comment:       req.Comment,
	}

	// 调用服务层
	rating, err := h.marketService.RateSkill(c.Request.Context(), rateReq)
	if err != nil {
		h.handleError(c, err)
		return
	}

	SuccessResponse(c, gin.H{
		"id":      rating.ID,
		"message": "评分成功",
	})
}

// GetRatings 获取技能评分列表
// GET /api/v1/skills/market/:id/ratings
func (h *SkillMarketHandler) GetRatings(c *gin.Context) {
	if h.marketService == nil {
		ErrorResponse(c, 50001, "技能市场服务未初始化")
		return
	}

	idStr := c.Param("id")
	id, err := uuid.Parse(idStr)
	if err != nil {
		ErrorResponse(c, 40002, "无效的技能ID")
		return
	}

	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "10"))

	// 调用服务层
	ratings, total, err := h.marketService.ListRatings(c.Request.Context(), id, page, pageSize)
	if err != nil {
		h.handleError(c, err)
		return
	}

	// 转换响应
	items := make([]RatingItem, 0, len(ratings))
	for _, r := range ratings {
		items = append(items, RatingItem{
			ID:        r.ID,
			UserID:    r.UserID,
			UserName:  r.UserName,
			Rating:    r.Rating,
			Comment:   r.Comment,
			Helpful:   r.Helpful,
			CreatedAt: r.CreatedAt.UnixMilli(),
		})
	}

	SuccessResponse(c, RatingListResponse{
		Items:    items,
		Total:    total,
		Page:     page,
		PageSize: pageSize,
	})
}

// GetCategories 获取技能分类列表
// GET /api/v1/skills/market/categories
func (h *SkillMarketHandler) GetCategories(c *gin.Context) {
	if h.marketService == nil {
		ErrorResponse(c, 50001, "技能市场服务未初始化")
		return
	}

	categories, err := h.marketService.GetCategories(c.Request.Context())
	if err != nil {
		h.handleError(c, err)
		return
	}

	// 转换为响应格式并构建树形结构
	response := h.buildCategoryTree(categories)

	SuccessResponse(c, response)
}

// CreateCategory 创建技能分类(管理员)
// POST /api/v1/skills/market/categories
func (h *SkillMarketHandler) CreateCategory(c *gin.Context) {
	if h.marketService == nil {
		ErrorResponse(c, 50001, "技能市场服务未初始化")
		return
	}

	var req CreateCategoryReq
	if err := c.ShouldBindJSON(&req); err != nil {
		ErrorResponse(c, 40001, "参数校验失败: "+err.Error())
		return
	}

	// 构建请求
	var parentID *uuid.UUID
	if req.ParentID != "" {
		pid, err := uuid.Parse(req.ParentID)
		if err != nil {
			ErrorResponse(c, 40003, "无效的父分类ID")
			return
		}
		parentID = &pid
	}

	createReq := &service.CreateCategoryRequest{
		Name:        strings.TrimSpace(req.Name),
		Code:        strings.TrimSpace(req.Code),
		Description: req.Description,
		Icon:        req.Icon,
		ParentID:    parentID,
		Sort:        req.Sort,
	}

	// 调用服务层
	category, err := h.marketService.CreateCategory(c.Request.Context(), createReq)
	if err != nil {
		h.handleError(c, err)
		return
	}

	SuccessResponse(c, h.toCategoryResponse(category))
}

// UpdateSkill 更新市场技能
// PUT /api/v1/skills/market/:id
func (h *SkillMarketHandler) UpdateSkill(c *gin.Context) {
	if h.marketService == nil {
		ErrorResponse(c, 50001, "技能市场服务未初始化")
		return
	}

	idStr := c.Param("id")
	id, err := uuid.Parse(idStr)
	if err != nil {
		ErrorResponse(c, 40002, "无效的技能ID")
		return
	}

	var req UpdateSkillReq
	if err := c.ShouldBindJSON(&req); err != nil {
		ErrorResponse(c, 40001, "参数校验失败: "+err.Error())
		return
	}

	// 从上下文获取用户信息
	userID := c.GetUint64("user_id")

	// 构建更新请求
	updateReq := &service.UpdateMarketSkillRequest{
		DisplayName:   req.DisplayName,
		Description:   req.Description,
		Tags:          req.Tags,
		Icon:          req.Icon,
		Version:       req.Version,
		Documentation: req.Documentation,
		Changelog:     req.Changelog,
	}

	if req.CategoryID != "" {
		categoryID, err := uuid.Parse(req.CategoryID)
		if err != nil {
			ErrorResponse(c, 40003, "无效的分类ID")
			return
		}
		updateReq.CategoryID = categoryID
	}

	// 调用服务层
	skill, err := h.marketService.UpdateMarketSkill(c.Request.Context(), id, updateReq, int64(userID))
	if err != nil {
		h.handleError(c, err)
		return
	}

	SuccessResponse(c, h.toSkillDetailResponse(skill))
}

// DeleteSkill 删除/下架市场技能
// DELETE /api/v1/skills/market/:id
func (h *SkillMarketHandler) DeleteSkill(c *gin.Context) {
	if h.marketService == nil {
		ErrorResponse(c, 50001, "技能市场服务未初始化")
		return
	}

	idStr := c.Param("id")
	id, err := uuid.Parse(idStr)
	if err != nil {
		ErrorResponse(c, 40002, "无效的技能ID")
		return
	}

	// 从上下文获取用户信息
	userID := c.GetUint64("user_id")

	// 调用服务层
	err = h.marketService.DeleteMarketSkill(c.Request.Context(), id, int64(userID))
	if err != nil {
		h.handleError(c, err)
		return
	}

	SuccessResponse(c, gin.H{"message": "技能已下架"})
}

// ReviewSkill 审核技能(管理员)
// POST /api/v1/skills/market/:id/review
func (h *SkillMarketHandler) ReviewSkill(c *gin.Context) {
	if h.marketService == nil {
		ErrorResponse(c, 50001, "技能市场服务未初始化")
		return
	}

	idStr := c.Param("id")
	id, err := uuid.Parse(idStr)
	if err != nil {
		ErrorResponse(c, 40002, "无效的技能ID")
		return
	}

	var req struct {
		Approved bool   `json:"approved"`
		Comment  string `json:"comment"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		ErrorResponse(c, 40001, "参数校验失败: "+err.Error())
		return
	}

	// 从上下文获取审核人ID
	reviewerID := c.GetUint64("user_id")

	// 调用服务层
	err = h.marketService.ReviewSkill(c.Request.Context(), id, req.Approved, req.Comment, int64(reviewerID))
	if err != nil {
		h.handleError(c, err)
		return
	}

	message := "审核通过"
	if !req.Approved {
		message = "审核拒绝"
	}
	SuccessResponse(c, gin.H{"message": message})
}

// ========== 辅助方法 ==========

// handleError 统一错误处理
func (h *SkillMarketHandler) handleError(c *gin.Context, err error) {
	if bizErr, ok := err.(*service.BusinessException); ok {
		ErrorResponse(c, bizErr.Code, bizErr.Message)
		return
	}
	ErrorResponse(c, 50000, "服务内部错误: "+err.Error())
}

// toSkillDetailResponse 转换为详情响应
func (h *SkillMarketHandler) toSkillDetailResponse(skill *model.SkillMarket) SkillDetailResponse {
	var publishedAt *int64
	if skill.PublishedAt != nil {
		ts := skill.PublishedAt.UnixMilli()
		publishedAt = &ts
	}

	return SkillDetailResponse{
		ID:            skill.ID,
		SkillID:       skill.SkillID,
		Name:          skill.Name,
		DisplayName:   skill.DisplayName,
		Description:   skill.Description,
		CategoryID:    skill.CategoryID,
		CategoryName:  skill.CategoryName,
		Tags:          h.parseTags(skill.Tags),
		Icon:          skill.Icon,
		Version:       skill.Version,
		InputSchema:   skill.InputSchema,
		OutputSchema:  skill.OutputSchema,
		HandlerType:   skill.HandlerType,
		Timeout:       skill.Timeout,
		AuthorID:      skill.AuthorID,
		AuthorName:    skill.AuthorName,
		Status:        string(skill.Status),
		DownloadCount: skill.DownloadCount,
		ViewCount:     skill.ViewCount,
		RatingAvg:     skill.RatingAvg,
		RatingCount:   skill.RatingCount,
		Featured:      skill.Featured,
		Documentation: skill.Documentation,
		Changelog:     skill.Changelog,
		PublishedAt:   publishedAt,
		CreatedAt:     skill.CreatedAt.UnixMilli(),
		UpdatedAt:     skill.UpdatedAt.UnixMilli(),
	}
}

// parseTags 解析标签
func (h *SkillMarketHandler) parseTags(tags string) []string {
	if tags == "" {
		return []string{}
	}
	return strings.Split(tags, ",")
}

// buildCategoryTree 构建分类树形结构
func (h *SkillMarketHandler) buildCategoryTree(categories []model.SkillCategory) []CategoryResponse {
	// 构建映射
	categoryMap := make(map[uuid.UUID]*CategoryResponse)
	for _, cat := range categories {
		categoryMap[cat.ID] = &CategoryResponse{
			ID:          cat.ID,
			Name:        cat.Name,
			Code:        cat.Code,
			Description: cat.Description,
			Icon:        cat.Icon,
			ParentID:    cat.ParentID,
			Sort:        cat.Sort,
			SkillCount:  cat.SkillCount,
			Children:    []CategoryResponse{},
		}
	}

	// 构建树形结构
	var roots []CategoryResponse
	for _, cat := range categoryMap {
		if cat.ParentID == nil {
			roots = append(roots, *cat)
		} else {
			if parent, ok := categoryMap[*cat.ParentID]; ok {
				parent.Children = append(parent.Children, *cat)
			}
		}
	}

	return roots
}

// toCategoryResponse 转换为分类响应
func (h *SkillMarketHandler) toCategoryResponse(cat *model.SkillCategory) CategoryResponse {
	return CategoryResponse{
		ID:          cat.ID,
		Name:        cat.Name,
		Code:        cat.Code,
		Description: cat.Description,
		Icon:        cat.Icon,
		ParentID:    cat.ParentID,
		Sort:        cat.Sort,
		SkillCount:  cat.SkillCount,
	}
}
