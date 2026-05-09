package handler

import (
	"strconv"

	"admin-config/internal/model"
	"admin-config/internal/service"
	"admin-config/pkg/response"

	"github.com/gin-gonic/gin"
)

// GitHandler Git配置处理器
type GitHandler struct {
	gitService *service.GitService
}

// NewGitHandler 创建Git处理器
func NewGitHandler(gitService *service.GitService) *GitHandler {
	return &GitHandler{
		gitService: gitService,
	}
}

// Create 创建Git配置
// @Summary 创建Git配置
// @Tags Git配置
// @Accept json
// @Produce json
// @Param body body model.GitConfigCreate true "创建请求"
// @Success 200 {object} response.Response
// @Router /git [post]
func (h *GitHandler) Create(c *gin.Context) {
	var req model.GitConfigCreate
	if err := c.ShouldBindJSON(&req); err != nil {
		response.BadRequest(c, "参数错误: "+err.Error())
		return
	}

	adminID := getAdminID(c)
	tenantID := getTenantID(c)

	git, err := h.gitService.Create(adminID, tenantID, &req)
	if err != nil {
		response.InternalServerError(c, "创建失败: "+err.Error())
		return
	}

	response.Success(c, git.ToResponse())
}

// Update 更新Git配置
// @Summary 更新Git配置
// @Tags Git配置
// @Accept json
// @Produce json
// @Param id path int true "配置ID"
// @Param body body model.GitConfigUpdate true "更新请求"
// @Success 200 {object} response.Response
// @Router /git/{id} [put]
func (h *GitHandler) Update(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		response.BadRequest(c, "无效的ID")
		return
	}

	var req model.GitConfigUpdate
	if err := c.ShouldBindJSON(&req); err != nil {
		response.BadRequest(c, "参数错误: "+err.Error())
		return
	}

	tenantID := getTenantID(c)

	git, err := h.gitService.Update(id, tenantID, &req)
	if err != nil {
		response.InternalServerError(c, "更新失败: "+err.Error())
		return
	}

	response.Success(c, git.ToResponse())
}

// Delete 删除Git配置
// @Summary 删除Git配置
// @Tags Git配置
// @Produce json
// @Param id path int true "配置ID"
// @Success 200 {object} response.Response
// @Router /git/{id} [delete]
func (h *GitHandler) Delete(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		response.BadRequest(c, "无效的ID")
		return
	}

	tenantID := getTenantID(c)

	if err := h.gitService.Delete(id, tenantID); err != nil {
		response.InternalServerError(c, "删除失败: "+err.Error())
		return
	}

	response.SuccessWithMsg(c, "删除成功", nil)
}

// GetByID 获取Git配置详情
// @Summary 获取Git配置详情
// @Tags Git配置
// @Produce json
// @Param id path int true "配置ID"
// @Success 200 {object} response.Response
// @Router /git/{id} [get]
func (h *GitHandler) GetByID(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		response.BadRequest(c, "无效的ID")
		return
	}

	tenantID := getTenantID(c)

	git, err := h.gitService.GetByID(id, tenantID)
	if err != nil {
		response.NotFound(c, err.Error())
		return
	}

	response.Success(c, git.ToResponse())
}

// List 获取Git配置列表
// @Summary 获取Git配置列表
// @Tags Git配置
// @Produce json
// @Param platform query string false "平台"
// @Param status query int false "状态"
// @Success 200 {object} response.Response
// @Router /git [get]
func (h *GitHandler) List(c *gin.Context) {
	tenantID := getTenantID(c)
	platform := c.Query("platform")

	var status *int
	if s := c.Query("status"); s != "" {
		st, err := strconv.Atoi(s)
		if err == nil {
			status = &st
		}
	}

	list, total, err := h.gitService.List(tenantID, platform, status)
	if err != nil {
		response.InternalServerError(c, "查询失败: "+err.Error())
		return
	}

	// 转换为响应结构
	result := make([]*model.GitConfigResponse, len(list))
	for i, item := range list {
		result[i] = item.ToResponse()
	}

	response.SuccessWithPage(c, result, total)
}

// GetDefault 获取默认Git配置
// @Summary 获取默认Git配置
// @Tags Git配置
// @Produce json
// @Success 200 {object} response.Response
// @Router /git/default [get]
func (h *GitHandler) GetDefault(c *gin.Context) {
	tenantID := getTenantID(c)

	git, err := h.gitService.GetDefault(tenantID)
	if err != nil {
		response.NotFound(c, err.Error())
		return
	}

	response.Success(c, git.ToResponse())
}
