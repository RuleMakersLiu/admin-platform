package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"admin-agent/internal/service"
)

// SandboxHandler 沙箱执行处理器
type SandboxHandler struct {
	sandboxService *service.SandboxService
}

// NewSandboxHandler 创建沙箱处理器
func NewSandboxHandler(sandboxService *service.SandboxService) *SandboxHandler {
	return &SandboxHandler{
		sandboxService: sandboxService,
	}
}

// Execute 代码执行接口
// @Summary 执行代码
// @Description 在安全沙箱中执行代码
// @Tags sandbox
// @Accept json
// @Produce json
// @Param request body service.ExecuteRequest true "执行请求"
// @Success 200 {object} service.ExecuteResult
// @Failure 400 {object} map[string]interface{}
// @Failure 500 {object} map[string]interface{}
// @Router /api/v1/sandbox/execute [post]
func (h *SandboxHandler) Execute(c *gin.Context) {
	var req service.ExecuteRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": "参数错误: " + err.Error(),
		})
		return
	}

	// 验证代码长度(防止过大的代码)
	if len(req.Code) > 100*1024 { // 100KB限制
		c.JSON(http.StatusBadRequest, gin.H{
			"error": "代码长度超过限制(最大100KB)",
		})
		return
	}

	// 验证输入长度
	if len(req.Input) > 10*1024 { // 10KB限制
		c.JSON(http.StatusBadRequest, gin.H{
			"error": "输入长度超过限制(最大10KB)",
		})
		return
	}

	// 执行代码
	result, err := h.sandboxService.Execute(c.Request.Context(), &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "执行失败: " + err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, result)
}

// HealthCheck 沙箱健康检查
// @Summary 沙箱健康检查
// @Description 检查Docker沙箱服务是否正常
// @Tags sandbox
// @Produce json
// @Success 200 {object} map[string]interface{}
// @Failure 503 {object} map[string]interface{}
// @Router /api/v1/sandbox/health [get]
func (h *SandboxHandler) HealthCheck(c *gin.Context) {
	if err := h.sandboxService.HealthCheck(c.Request.Context()); err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"status": "unhealthy",
			"error":  err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"status":  "healthy",
		"message": "Docker沙箱服务正常运行",
	})
}

// GetConfig 获取沙箱配置
// @Summary 获取沙箱配置
// @Description 返回当前沙箱的资源配置
// @Tags sandbox
// @Produce json
// @Success 200 {object} map[string]interface{}
// @Router /api/v1/sandbox/config [get]
func (h *SandboxHandler) GetConfig(c *gin.Context) {
	cfg := h.sandboxService.GetConfig()
	c.JSON(http.StatusOK, gin.H{
		"memory_limit_mb":    cfg.MemoryLimit,
		"cpu_quota_percent":  cfg.CPUQuota / 1000, // 转为百分比
		"timeout_seconds":    cfg.Timeout,
		"network_disabled":   cfg.NetworkDisabled,
		"supported_languages": h.sandboxService.SupportedLanguages(),
	})
}

// SupportedLanguages 获取支持的语言列表
// @Summary 获取支持的语言
// @Description 返回沙箱支持的所有编程语言
// @Tags sandbox
// @Produce json
// @Success 200 {object} map[string]interface{}
// @Router /api/v1/sandbox/languages [get]
func (h *SandboxHandler) SupportedLanguages(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"languages": h.sandboxService.SupportedLanguages(),
	})
}
