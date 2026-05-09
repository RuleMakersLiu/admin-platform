package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"admin-agent/internal/model"
	"admin-agent/internal/service"
)

// LLMHandler LLM配置处理器
type LLMHandler struct {
	providerService *service.LLMProviderService
}

// NewLLMHandler 创建LLM处理器
func NewLLMHandler(providerService *service.LLMProviderService) *LLMHandler {
	return &LLMHandler{
		providerService: providerService,
	}
}

// HealthResponse 健康检查响应
type HealthResponse struct {
	Code      int                    `json:"code"`
	Message   string                 `json:"message"`
	Data      []ProviderHealthData   `json:"data"`
	Timestamp int64                  `json:"timestamp"`
}

// ProviderHealthData 提供商健康数据
type ProviderHealthData struct {
	ConfigID         int64                    `json:"config_id"`
	Provider         string                   `json:"provider"`
	Name             string                   `json:"name"`
	Status           string                   `json:"status"`
	CircuitState     string                   `json:"circuit_state"`
	TotalRequests    int64                    `json:"total_requests"`
	SuccessRequests  int64                    `json:"success_requests"`
	FailedRequests   int64                    `json:"failed_requests"`
	SuccessRate      float64                  `json:"success_rate"`
	AvgLatencyMs     int64                    `json:"avg_latency_ms"`
	LastSuccessTime  int64                    `json:"last_success_time"`
	LastFailTime     int64                    `json:"last_fail_time"`
	LastFailReason   string                   `json:"last_fail_reason"`
	ConsecutiveFails int                      `json:"consecutive_fails"`
}

// GetHealth 获取LLM提供商健康状态
// @Summary 获取LLM提供商健康状态
// @Description 获取所有LLM提供商的健康状态和指标
// @Tags LLM
// @Accept json
// @Produce json
// @Success 200 {object} HealthResponse
// @Router /api/llm/health [get]
func (h *LLMHandler) GetHealth(c *gin.Context) {
	if h.providerService == nil {
		c.JSON(http.StatusOK, gin.H{
			"code":      50001,
			"message":   "LLM服务未初始化",
			"data":      nil,
			"timestamp": model.NowMillis(),
		})
		return
	}

	metrics := h.providerService.GetProviderHealth()
	providers := h.providerService.GetProviders()

	// 构建提供商名称映射
	nameMap := make(map[int64]string)
	for _, p := range providers {
		nameMap[p.ID] = p.Name
	}

	// 构建响应数据
	data := make([]ProviderHealthData, 0, len(metrics))
	for _, m := range metrics {
		successRate := float64(0)
		if m.TotalRequests > 0 {
			successRate = float64(m.SuccessRequests) / float64(m.TotalRequests) * 100
		}

		data = append(data, ProviderHealthData{
			ConfigID:         m.ConfigID,
			Provider:         string(m.Provider),
			Name:             nameMap[m.ConfigID],
			Status:           string(m.Status),
			CircuitState:     string(m.CircuitState),
			TotalRequests:    m.TotalRequests,
			SuccessRequests:  m.SuccessRequests,
			FailedRequests:   m.FailedRequests,
			SuccessRate:      successRate,
			AvgLatencyMs:     m.AvgLatency,
			LastSuccessTime:  m.LastSuccessTime,
			LastFailTime:     m.LastFailTime,
			LastFailReason:   m.LastFailReason,
			ConsecutiveFails: m.ConsecutiveFails,
		})
	}

	c.JSON(http.StatusOK, HealthResponse{
		Code:      0,
		Message:   "success",
		Data:      data,
		Timestamp: model.NowMillis(),
	})
}

// GetProviders 获取LLM提供商列表
// @Summary 获取LLM提供商列表
// @Description 获取所有配置的LLM提供商
// @Tags LLM
// @Accept json
// @Produce json
// @Success 200 {object} map[string]interface{}
// @Router /api/llm/providers [get]
func (h *LLMHandler) GetProviders(c *gin.Context) {
	if h.providerService == nil {
		c.JSON(http.StatusOK, gin.H{
			"code":      50001,
			"message":   "LLM服务未初始化",
			"data":      nil,
			"timestamp": model.NowMillis(),
		})
		return
	}

	providers := h.providerService.GetProviders()

	// 隐藏敏感信息
	result := make([]map[string]interface{}, 0, len(providers))
	for _, p := range providers {
		result = append(result, map[string]interface{}{
			"id":          p.ID,
			"name":        p.Name,
			"provider":    p.Provider,
			"model_name":  p.ModelName,
			"max_tokens":  p.MaxTokens,
			"temperature": p.Temperature,
			"priority":    p.Priority,
			"weight":      p.Weight,
			"is_default":  p.IsDefault,
			"status":      p.Status,
		})
	}

	c.JSON(http.StatusOK, gin.H{
		"code":      0,
		"message":   "success",
		"data":      result,
		"timestamp": model.NowMillis(),
	})
}

// ReloadProviders 重新加载提供商配置
// @Summary 重新加载提供商配置
// @Description 从数据库重新加载LLM提供商配置
// @Tags LLM
// @Accept json
// @Produce json
// @Success 200 {object} map[string]interface{}
// @Router /api/llm/reload [post]
func (h *LLMHandler) ReloadProviders(c *gin.Context) {
	if h.providerService == nil {
		c.JSON(http.StatusOK, gin.H{
			"code":      50001,
			"message":   "LLM服务未初始化",
			"data":      nil,
			"timestamp": model.NowMillis(),
		})
		return
	}

	if err := h.providerService.ReloadProviders(); err != nil {
		c.JSON(http.StatusOK, gin.H{
			"code":      50000,
			"message":   "重新加载配置失败: " + err.Error(),
			"data":      nil,
			"timestamp": model.NowMillis(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":      0,
		"message":   "success",
		"data":      nil,
		"timestamp": model.NowMillis(),
	})
}

// TestRequest 测试请求
type TestRequest struct {
	Message   string  `json:"message" binding:"required"`
	Model     string  `json:"model"`
	MaxTokens int     `json:"max_tokens"`
	Temperature float64 `json:"temperature"`
}

// TestProvider 测试提供商
// @Summary 测试LLM提供商
// @Description 测试指定的LLM提供商是否能正常工作
// @Tags LLM
// @Accept json
// @Produce json
// @Param request body TestRequest true "测试请求"
// @Success 200 {object} map[string]interface{}
// @Router /api/llm/test [post]
func (h *LLMHandler) TestProvider(c *gin.Context) {
	if h.providerService == nil {
		c.JSON(http.StatusOK, gin.H{
			"code":      50001,
			"message":   "LLM服务未初始化",
			"data":      nil,
			"timestamp": model.NowMillis(),
		})
		return
	}

	var req TestRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusOK, gin.H{
			"code":      40000,
			"message":   "参数错误: " + err.Error(),
			"data":      nil,
			"timestamp": model.NowMillis(),
		})
		return
	}

	// 设置默认值
	if req.MaxTokens == 0 {
		req.MaxTokens = 100
	}
	if req.Temperature == 0 {
		req.Temperature = 0.7
	}

	// 构建LLM请求
	llmReq := &model.LLMRequest{
		Model:       req.Model,
		MaxTokens:   req.MaxTokens,
		Temperature: req.Temperature,
		Messages: []model.LLMMessage{
			{
				Role:    "user",
				Content: req.Message,
			},
		},
		Stream: false,
	}

	// 调用LLM
	resp, err := h.providerService.Chat(c.Request.Context(), llmReq)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"code":      50000,
			"message":   "调用LLM失败: " + err.Error(),
			"data":      nil,
			"timestamp": model.NowMillis(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    0,
		"message": "success",
		"data": map[string]interface{}{
			"provider_id":   resp.ProviderID,
			"provider":      resp.Provider,
			"model":         resp.Model,
			"content":       resp.Content,
			"input_tokens":  resp.Usage.InputTokens,
			"output_tokens": resp.Usage.OutputTokens,
		},
		"timestamp": model.NowMillis(),
	})
}
