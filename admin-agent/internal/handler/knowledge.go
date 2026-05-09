package handler

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"

	"admin-agent/internal/model"
	"admin-agent/internal/service"
)

// KnowledgeHandler 知识库处理器
type KnowledgeHandler struct {
	knowledgeService *service.KnowledgeService
}

// NewKnowledgeHandler 创建知识库处理器
func NewKnowledgeHandler(knowledgeService *service.KnowledgeService) *KnowledgeHandler {
	return &KnowledgeHandler{
		knowledgeService: knowledgeService,
	}
}

// 统一响应格式
type Response struct {
	Code    int         `json:"code"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
}

// SuccessResponse 成功响应
func SuccessResponse(c *gin.Context, data interface{}) {
	c.JSON(http.StatusOK, Response{
		Code:    0,
		Message: "success",
		Data:    data,
	})
}

// ErrorResponse 错误响应
func ErrorResponse(c *gin.Context, code int, message string) {
	statusCode := http.StatusBadRequest
	if code >= 50000 {
		statusCode = http.StatusInternalServerError
	}
	c.JSON(statusCode, Response{
		Code:    code,
		Message: message,
	})
}

// ========== 请求/响应 DTO ==========

// CreateKnowledgeRequest 创建知识请求
type CreateKnowledgeRequest struct {
	Title      string   `json:"title" binding:"required,max=255"`
	Content    string   `json:"content" binding:"required"`
	Category   string   `json:"category" binding:"max=50"`
	Tags       []string `json:"tags"`
	AgentType  string   `json:"agent_type" binding:"max=20"`
	Source     string   `json:"source" binding:"max=255"`
	ProjectID  int64    `json:"project_id"`
}

// UpdateKnowledgeRequest 更新知识请求
type UpdateKnowledgeRequest struct {
	Title     string   `json:"title" binding:"max=255"`
	Content   string   `json:"content"`
	Category  string   `json:"category" binding:"max=50"`
	Tags      []string `json:"tags"`
	AgentType string   `json:"agent_type" binding:"max=20"`
	Source    string   `json:"source" binding:"max=255"`
	Status    int      `json:"status"`
}

// KnowledgeQueryRequest 查询知识请求参数
type KnowledgeQueryRequest struct {
	Page      int    `form:"page" binding:"min=1"`
	PageSize  int    `form:"page_size" binding:"min=1,max=100"`
	Keyword   string `form:"keyword"`
	Category  string `form:"category"`
	AgentType string `form:"agent_type"`
	ProjectID int64  `form:"project_id"`
	Status    int    `form:"status"`
	SortBy    string `form:"sort_by"`
	SortOrder string `form:"sort_order"`
}

// KnowledgeListResponse 知识列表响应
type KnowledgeListResponse struct {
	Items      []KnowledgeItem `json:"items"`
	Total      int64           `json:"total"`
	Page       int             `json:"page"`
	PageSize   int             `json:"page_size"`
	TotalPages int             `json:"total_pages"`
}

// KnowledgeItem 知识项
type KnowledgeItem struct {
	ID              int64    `json:"id"`
	KnowledgeID     string   `json:"knowledge_id"`
	ProjectID       int64    `json:"project_id"`
	Title           string   `json:"title"`
	Content         string   `json:"content"`
	Category        string   `json:"category"`
	Tags            []string `json:"tags"`
	Source          string   `json:"source"`
	AgentType       string   `json:"agent_type"`
	Version         int      `json:"version"`
	ViewCount       int      `json:"view_count"`
	EmbeddingStatus string   `json:"embedding_status"`
	CreateTime      int64    `json:"create_time"`
	UpdateTime      int64    `json:"update_time"`
}

// KnowledgeSearchRequest 搜索知识请求
type KnowledgeSearchRequest struct {
	Keyword   string `form:"keyword" binding:"required"`
	Page      int    `form:"page" binding:"min=1"`
	PageSize  int    `form:"page_size" binding:"min=1,max=100"`
	AgentType string `form:"agent_type"`
	Category  string `form:"category"`
}

// ========== API 处理函数 ==========

// CreateKnowledge 创建知识条目
// POST /api/v1/knowledge
func (h *KnowledgeHandler) CreateKnowledge(c *gin.Context) {
	var req CreateKnowledgeRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		ErrorResponse(c, 40001, "参数校验失败: "+err.Error())
		return
	}

	// 从上下文获取用户信息
	userID := c.GetUint64("user_id")
	tenantID := c.GetUint64("tenant_id")

	// 构建知识对象
	knowledge := &model.AgentKnowledge{
		Title:      strings.TrimSpace(req.Title),
		Content:    req.Content,
		Category:   req.Category,
		Tags:       strings.Join(req.Tags, ","),
		Source:     req.Source,
		ProjectID:  req.ProjectID,
	}

	// 调用服务层创建知识
	created, err := h.knowledgeService.CreateKnowledge(c.Request.Context(), knowledge, req.AgentType, userID, tenantID)
	if err != nil {
		ErrorResponse(c, 50001, "创建知识失败: "+err.Error())
		return
	}

	SuccessResponse(c, h.toKnowledgeItem(created))
}

// GetKnowledgeList 获取知识列表
// GET /api/v1/knowledge
// 支持分页、搜索、分类筛选
func (h *KnowledgeHandler) GetKnowledgeList(c *gin.Context) {
	var req KnowledgeQueryRequest
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
		req.SortBy = "create_time"
	}
	if req.SortOrder == "" {
		req.SortOrder = "desc"
	}

	// 从上下文获取租户信息
	tenantID := c.GetUint64("tenant_id")

	// 构建查询参数
	params := &service.KnowledgeQueryParams{
		Page:      req.Page,
		PageSize:  req.PageSize,
		Keyword:   req.Keyword,
		Category:  req.Category,
		AgentType: req.AgentType,
		ProjectID: req.ProjectID,
		Status:    req.Status,
		SortBy:    req.SortBy,
		SortOrder: req.SortOrder,
		TenantID:  tenantID,
	}

	// 调用服务层查询
	items, total, err := h.knowledgeService.ListKnowledge(c.Request.Context(), params)
	if err != nil {
		ErrorResponse(c, 50002, "查询知识列表失败: "+err.Error())
		return
	}

	// 计算总页数
	totalPages := int(total) / req.PageSize
	if int(total)%req.PageSize > 0 {
		totalPages++
	}

	// 转换响应
	response := KnowledgeListResponse{
		Items:      h.toKnowledgeItems(items),
		Total:      total,
		Page:       req.Page,
		PageSize:   req.PageSize,
		TotalPages: totalPages,
	}

	SuccessResponse(c, response)
}

// GetKnowledge 获取单个知识详情
// GET /api/v1/knowledge/:id
func (h *KnowledgeHandler) GetKnowledge(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		ErrorResponse(c, 40002, "无效的知识ID")
		return
	}

	// 从上下文获取租户信息
	tenantID := c.GetUint64("tenant_id")

	// 调用服务层获取详情
	knowledge, err := h.knowledgeService.GetKnowledge(c.Request.Context(), id, tenantID)
	if err != nil {
		ErrorResponse(c, 50003, "获取知识详情失败: "+err.Error())
		return
	}

	if knowledge == nil {
		ErrorResponse(c, 40004, "知识不存在")
		return
	}

	SuccessResponse(c, h.toKnowledgeItem(knowledge))
}

// UpdateKnowledge 更新知识
// PUT /api/v1/knowledge/:id
func (h *KnowledgeHandler) UpdateKnowledge(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		ErrorResponse(c, 40002, "无效的知识ID")
		return
	}

	var req UpdateKnowledgeRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		ErrorResponse(c, 40001, "参数校验失败: "+err.Error())
		return
	}

	// 从上下文获取用户和租户信息
	userID := c.GetUint64("user_id")
	tenantID := c.GetUint64("tenant_id")

	// 构建更新对象
	updates := make(map[string]interface{})
	if req.Title != "" {
		updates["title"] = strings.TrimSpace(req.Title)
	}
	if req.Content != "" {
		updates["content"] = req.Content
	}
	if req.Category != "" {
		updates["category"] = req.Category
	}
	if req.Tags != nil {
		updates["tags"] = strings.Join(req.Tags, ",")
	}
	if req.AgentType != "" {
		updates["agent_type"] = req.AgentType
	}
	if req.Source != "" {
		updates["source"] = req.Source
	}
	if req.Status != 0 {
		updates["status"] = req.Status
	}

	// 调用服务层更新
	updated, err := h.knowledgeService.UpdateKnowledge(c.Request.Context(), id, updates, userID, tenantID)
	if err != nil {
		ErrorResponse(c, 50004, "更新知识失败: "+err.Error())
		return
	}

	SuccessResponse(c, h.toKnowledgeItem(updated))
}

// DeleteKnowledge 删除知识（软删除）
// DELETE /api/v1/knowledge/:id
func (h *KnowledgeHandler) DeleteKnowledge(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		ErrorResponse(c, 40002, "无效的知识ID")
		return
	}

	// 从上下文获取租户信息
	tenantID := c.GetUint64("tenant_id")

	// 调用服务层删除
	err = h.knowledgeService.DeleteKnowledge(c.Request.Context(), id, tenantID)
	if err != nil {
		ErrorResponse(c, 50005, "删除知识失败: "+err.Error())
		return
	}

	SuccessResponse(c, gin.H{"message": "删除成功"})
}

// SearchKnowledge 搜索知识
// GET /api/v1/knowledge/search
// 按关键词搜索知识内容
func (h *KnowledgeHandler) SearchKnowledge(c *gin.Context) {
	var req KnowledgeSearchRequest
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

	// 从上下文获取租户信息
	tenantID := c.GetUint64("tenant_id")

	// 构建搜索参数
	params := &service.KnowledgeSearchParams{
		Keyword:   req.Keyword,
		Page:      req.Page,
		PageSize:  req.PageSize,
		AgentType: req.AgentType,
		Category:  req.Category,
		TenantID:  tenantID,
	}

	// 调用服务层搜索
	items, total, err := h.knowledgeService.SearchKnowledge(c.Request.Context(), params)
	if err != nil {
		ErrorResponse(c, 50006, "搜索知识失败: "+err.Error())
		return
	}

	// 计算总页数
	totalPages := int(total) / req.PageSize
	if int(total)%req.PageSize > 0 {
		totalPages++
	}

	response := KnowledgeListResponse{
		Items:      h.toKnowledgeItems(items),
		Total:      total,
		Page:       req.Page,
		PageSize:   req.PageSize,
		TotalPages: totalPages,
	}

	SuccessResponse(c, response)
}

// ========== 辅助方法 ==========

// toKnowledgeItem 转换单个知识模型到响应DTO
func (h *KnowledgeHandler) toKnowledgeItem(k *model.AgentKnowledge) KnowledgeItem {
	return KnowledgeItem{
		ID:              k.ID,
		KnowledgeID:     k.KnowledgeID,
		ProjectID:       k.ProjectID,
		Title:           k.Title,
		Content:         k.Content,
		Category:        k.Category,
		Tags:            h.parseTags(k.Tags),
		Source:          k.Source,
		AgentType:       h.extractAgentType(k),
		Version:         k.Version,
		ViewCount:       k.ViewCount,
		EmbeddingStatus: k.EmbeddingStatus,
		CreateTime:      k.CreateTime,
		UpdateTime:      k.UpdateTime,
	}
}

// toKnowledgeItems 批量转换知识模型
func (h *KnowledgeHandler) toKnowledgeItems(items []*model.AgentKnowledge) []KnowledgeItem {
	result := make([]KnowledgeItem, 0, len(items))
	for _, item := range items {
		result = append(result, h.toKnowledgeItem(item))
	}
	return result
}

// parseTags 解析标签字符串为数组
func (h *KnowledgeHandler) parseTags(tags string) []string {
	if tags == "" {
		return []string{}
	}
	return strings.Split(tags, ",")
}

// extractAgentType 从知识模型提取关联的分身类型
func (h *KnowledgeHandler) extractAgentType(k *model.AgentKnowledge) string {
	return k.AgentType
}
