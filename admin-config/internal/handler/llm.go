package handler

import (
	"strconv"

	"admin-config/internal/model"
	"admin-config/internal/service"
	"admin-config/pkg/response"

	"github.com/gin-gonic/gin"
)

// LLMHandler LLM配置处理器
type LLMHandler struct {
	llmService *service.LLMService
}

// NewLLMHandler 创建LLM处理器
func NewLLMHandler(llmService *service.LLMService) *LLMHandler {
	return &LLMHandler{
		llmService: llmService,
	}
}

// Create 创建LLM配置
// @Summary 创建LLM配置
// @Tags LLM配置
// @Accept json
// @Produce json
// @Param body body model.LLMConfigCreate true "创建请求"
// @Success 200 {object} response.Response
// @Router /llm [post]
func (h *LLMHandler) Create(c *gin.Context) {
	var req model.LLMConfigCreate
	if err := c.ShouldBindJSON(&req); err != nil {
		response.BadRequest(c, "参数错误: "+err.Error())
		return
	}

	adminID := getAdminID(c)
	tenantID := getTenantID(c)

	llm, err := h.llmService.Create(adminID, tenantID, &req)
	if err != nil {
		response.InternalServerError(c, "创建失败: "+err.Error())
		return
	}

	response.Success(c, llm.ToResponse())
}

// Update 更新LLM配置
// @Summary 更新LLM配置
// @Tags LLM配置
// @Accept json
// @Produce json
// @Param id path int true "配置ID"
// @Param body body model.LLMConfigUpdate true "更新请求"
// @Success 200 {object} response.Response
// @Router /llm/{id} [put]
func (h *LLMHandler) Update(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		response.BadRequest(c, "无效的ID")
		return
	}

	var req model.LLMConfigUpdate
	if err := c.ShouldBindJSON(&req); err != nil {
		response.BadRequest(c, "参数错误: "+err.Error())
		return
	}

	tenantID := getTenantID(c)

	llm, err := h.llmService.Update(id, tenantID, &req)
	if err != nil {
		response.InternalServerError(c, "更新失败: "+err.Error())
		return
	}

	response.Success(c, llm.ToResponse())
}

// Delete 删除LLM配置
// @Summary 删除LLM配置
// @Tags LLM配置
// @Produce json
// @Param id path int true "配置ID"
// @Success 200 {object} response.Response
// @Router /llm/{id} [delete]
func (h *LLMHandler) Delete(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		response.BadRequest(c, "无效的ID")
		return
	}

	tenantID := getTenantID(c)

	if err := h.llmService.Delete(id, tenantID); err != nil {
		response.InternalServerError(c, "删除失败: "+err.Error())
		return
	}

	response.SuccessWithMsg(c, "删除成功", nil)
}

// GetByID 获取LLM配置详情
// @Summary 获取LLM配置详情
// @Tags LLM配置
// @Produce json
// @Param id path int true "配置ID"
// @Success 200 {object} response.Response
// @Router /llm/{id} [get]
func (h *LLMHandler) GetByID(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		response.BadRequest(c, "无效的ID")
		return
	}

	tenantID := getTenantID(c)

	llm, err := h.llmService.GetByID(id, tenantID)
	if err != nil {
		response.NotFound(c, err.Error())
		return
	}

	response.Success(c, llm.ToResponse())
}

// List 获取LLM配置列表
// @Summary 获取LLM配置列表
// @Tags LLM配置
// @Produce json
// @Param status query int false "状态"
// @Success 200 {object} response.Response
// @Router /llm [get]
func (h *LLMHandler) List(c *gin.Context) {
	tenantID := getTenantID(c)

	var status *int
	if s := c.Query("status"); s != "" {
		st, err := strconv.Atoi(s)
		if err == nil {
			status = &st
		}
	}

	list, total, err := h.llmService.List(tenantID, status)
	if err != nil {
		response.InternalServerError(c, "查询失败: "+err.Error())
		return
	}

	// 转换为响应结构
	result := make([]*model.LLMConfigResponse, len(list))
	for i, item := range list {
		result[i] = item.ToResponse()
	}

	response.SuccessWithPage(c, result, total)
}

// GetDefault 获取默认LLM配置
// @Summary 获取默认LLM配置
// @Tags LLM配置
// @Produce json
// @Success 200 {object} response.Response
// @Router /llm/default [get]
func (h *LLMHandler) GetDefault(c *gin.Context) {
	tenantID := getTenantID(c)

	llm, err := h.llmService.GetDefault(tenantID)
	if err != nil {
		response.NotFound(c, err.Error())
		return
	}

	response.Success(c, llm.ToResponse())
}

// TestConnection 测试LLM连接
// @Summary 测试LLM配置连接
// @Description 发送测试请求验证LLM配置是否正确可用
// @Tags LLM配置
// @Produce json
// @Param id path int true "配置ID"
// @Success 200 {object} response.Response{data=service.TestConnectionResult}
// @Router /llm/{id}/test [post]
func (h *LLMHandler) TestConnection(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		response.BadRequest(c, "无效的ID")
		return
	}

	tenantID := getTenantID(c)

	// 调用服务层测试连接
	result, err := h.llmService.TestConnection(id, tenantID)
	if err != nil {
		// 配置不存在等错误
		response.NotFound(c, err.Error())
		return
	}

	// 根据测试结果返回不同的状态码
	if result.Success {
		response.SuccessWithMsg(c, "连接测试成功", result)
	} else {
		// 连接失败返回200但标记success=false，让前端展示错误信息
		response.Success(c, result)
	}
}

// getAdminID 从上下文获取管理员ID
func getAdminID(c *gin.Context) int64 {
	adminIDStr := c.GetHeader("X-Admin-Id")
	if adminIDStr == "" {
		if v, exists := c.Get("adminId"); exists {
			switch id := v.(type) {
			case int64:
				return id
			case int:
				return int64(id)
			case string:
				if parsed, err := strconv.ParseInt(id, 10, 64); err == nil {
					return parsed
				}
			}
		}
		return 0
	}
	id, _ := strconv.ParseInt(adminIDStr, 10, 64)
	return id
}

// getTenantID 从上下文获取租户ID
func getTenantID(c *gin.Context) int64 {
	tenantIDStr := c.GetHeader("X-Tenant-Id")
	if tenantIDStr == "" {
		if v, exists := c.Get("tenantId"); exists {
			switch id := v.(type) {
			case int64:
				return id
			case int:
				return int64(id)
			case string:
				if parsed, err := strconv.ParseInt(id, 10, 64); err == nil {
					return parsed
				}
			}
		}
		return 1 // 默认租户
	}
	id, _ := strconv.ParseInt(tenantIDStr, 10, 64)
	return id
}
