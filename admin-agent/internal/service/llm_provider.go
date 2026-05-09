package service

import (
	"bytes"
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"sync"
	"time"

	"admin-agent/internal/config"
	"admin-agent/internal/model"

	"gorm.io/gorm"
)

// CircuitBreakerConfig 熔断器配置
type CircuitBreakerConfig struct {
	// FailureThreshold 失败阈值，连续失败多少次后熔断
	FailureThreshold int
	// SuccessThreshold 成功阈值，半开状态下连续成功多少次后恢复
	SuccessThreshold int
	// Timeout 熔断超时时间，熔断后多久尝试恢复
	Timeout time.Duration
	// HalfOpenRequests 半开状态下允许的请求数
	HalfOpenRequests int
}

// DefaultCircuitBreakerConfig 默认熔断器配置
var DefaultCircuitBreakerConfig = CircuitBreakerConfig{
	FailureThreshold: 5,
	SuccessThreshold: 3,
	Timeout:          30 * time.Second,
	HalfOpenRequests: 1,
}

// RetryConfig 重试配置
type RetryConfig struct {
	// MaxRetries 最大重试次数
	MaxRetries int
	// InitialDelay 初始延迟
	InitialDelay time.Duration
	// MaxDelay 最大延迟
	MaxDelay time.Duration
	// Multiplier 延迟倍数
	Multiplier float64
}

// DefaultRetryConfig 默认重试配置
var DefaultRetryConfig = RetryConfig{
	MaxRetries:   3,
	InitialDelay: 500 * time.Millisecond,
	MaxDelay:     10 * time.Second,
	Multiplier:   2.0,
}

// LLMProviderService LLM提供商服务 - 支持故障转移和负载均衡
type LLMProviderService struct {
	db             *gorm.DB
	cfg            *config.Config
	providers      []*model.SysLLMConfig      // 按优先级排序的提供商列表
	healthMetrics  map[int64]*model.ProviderHealthMetric // 健康指标
	cbConfig       CircuitBreakerConfig       // 熔断器配置
	retryConfig    RetryConfig                // 重试配置
	encryptionKey  []byte                     // AES加密密钥
	mu             sync.RWMutex
	httpClient     *http.Client
}

// NewLLMProviderService 创建LLM提供商服务
func NewLLMProviderService(db *gorm.DB, cfg *config.Config) *LLMProviderService {
	// 从配置获取加密密钥
	encKey := []byte("32-byte-encryption-key!!") // 32字节密钥
	if cfg != nil && len(cfg.JWT.Secret) >= 32 {
		encKey = []byte(cfg.JWT.Secret[:32])
	}

	s := &LLMProviderService{
		db:            db,
		cfg:           cfg,
		providers:     make([]*model.SysLLMConfig, 0),
		healthMetrics: make(map[int64]*model.ProviderHealthMetric),
		cbConfig:      DefaultCircuitBreakerConfig,
		retryConfig:   DefaultRetryConfig,
		encryptionKey: encKey,
		httpClient: &http.Client{
			Timeout: 120 * time.Second,
		},
	}

	// 加载提供商配置
	if db != nil {
		s.loadProviders()
	}

	// 启动健康检查
	go s.startHealthCheck()

	return s
}

// loadProviders 从数据库加载提供商配置
func (s *LLMProviderService) loadProviders() error {
	var configs []model.SysLLMConfig
	err := s.db.Where("status = ?", 1).
		Order("priority ASC, weight DESC").
		Find(&configs).Error
	if err != nil {
		log.Printf("[LLMProvider] 加载提供商配置失败: %v", err)
		return err
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	s.providers = make([]*model.SysLLMConfig, 0, len(configs))
	for i := range configs {
		// 解密API Key
		decryptedKey, err := s.decryptAPIKey(configs[i].APIKey)
		if err != nil {
			log.Printf("[LLMProvider] 解密API Key失败[config_id=%d]: %v", configs[i].ID, err)
			continue
		}
		configs[i].APIKey = decryptedKey

		s.providers = append(s.providers, &configs[i])

		// 初始化健康指标
		if _, exists := s.healthMetrics[configs[i].ID]; !exists {
			s.healthMetrics[configs[i].ID] = &model.ProviderHealthMetric{
				ConfigID:     configs[i].ID,
				Provider:     configs[i].Provider,
				Status:       model.ProviderStatusHealthy,
				CircuitState: model.CircuitClosed,
			}
		}
	}

	log.Printf("[LLMProvider] 加载了 %d 个提供商配置", len(s.providers))
	return nil
}

// ReloadProviders 重新加载提供商配置
func (s *LLMProviderService) ReloadProviders() error {
	return s.loadProviders()
}

// Chat 执行对话请求 (带故障转移)
func (s *LLMProviderService) Chat(ctx context.Context, req *model.LLMRequest) (*model.LLMResponse, error) {
	return s.ChatWithFailover(ctx, req, "")
}

// ChatWithFailover 执行对话请求 (带故障转移和会话ID用于日志)
func (s *LLMProviderService) ChatWithFailover(ctx context.Context, req *model.LLMRequest, sessionID string) (*model.LLMResponse, error) {
	providers := s.getAvailableProviders()
	if len(providers) == 0 {
		return nil, fmt.Errorf("没有可用的LLM提供商")
	}

	var lastErr error
	var attemptedProviders []int64

	for _, provider := range providers {
		// 检查熔断器状态
		if !s.canRequest(provider.ID) {
			log.Printf("[LLMProvider] 提供商 %s (ID:%d) 被熔断，跳过", provider.Name, provider.ID)
			continue
		}

		attemptedProviders = append(attemptedProviders, provider.ID)

		// 使用重试机制调用
		resp, err := s.callWithRetry(ctx, provider, req)
		if err != nil {
			lastErr = err
			s.recordFailure(provider.ID, err.Error())
			log.Printf("[LLMProvider] 提供商 %s (ID:%d) 调用失败: %v", provider.Name, provider.ID, err)
			continue
		}

		// 成功
		s.recordSuccess(provider.ID)
		return resp, nil
	}

	// 所有提供商都失败，记录故障转移日志
	if sessionID != "" && s.db != nil {
		s.logFailover(sessionID, attemptedProviders, lastErr)
	}

	return nil, fmt.Errorf("所有LLM提供商都失败: %w", lastErr)
}

// getAvailableProviders 获取可用的提供商列表 (按优先级排序)
func (s *LLMProviderService) getAvailableProviders() []*model.SysLLMConfig {
	s.mu.RLock()
	defer s.mu.RUnlock()

	result := make([]*model.SysLLMConfig, 0, len(s.providers))
	for _, p := range s.providers {
		// 跳过被熔断的提供商
		metric, exists := s.healthMetrics[p.ID]
		if exists && metric.CircuitState == model.CircuitOpen {
			// 检查是否可以尝试半开
			if time.Now().UnixMilli()-metric.CircuitOpenTime < int64(s.cbConfig.Timeout/time.Millisecond) {
				continue
			}
		}
		result = append(result, p)
	}

	return result
}

// canRequest 检查提供商是否可以接受请求
func (s *LLMProviderService) canRequest(providerID int64) bool {
	s.mu.RLock()
	defer s.mu.RUnlock()

	metric, exists := s.healthMetrics[providerID]
	if !exists {
		return true
	}

	switch metric.CircuitState {
	case model.CircuitOpen:
		// 检查是否超时，可以尝试半开
		elapsed := time.Now().UnixMilli() - metric.CircuitOpenTime
		if elapsed >= int64(s.cbConfig.Timeout/time.Millisecond) {
			return true
		}
		return false
	case model.CircuitHalfOpen:
		// 半开状态限制请求数
		return metric.TotalRequests < int64(s.cbConfig.HalfOpenRequests)
	default:
		return true
	}
}

// callWithRetry 带重试的调用
func (s *LLMProviderService) callWithRetry(ctx context.Context, provider *model.SysLLMConfig, req *model.LLMRequest) (*model.LLMResponse, error) {
	var lastErr error
	delay := s.retryConfig.InitialDelay

	for attempt := 0; attempt <= s.retryConfig.MaxRetries; attempt++ {
		if attempt > 0 {
			// 指数退避
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(delay):
			}
			delay = time.Duration(float64(delay) * s.retryConfig.Multiplier)
			if delay > s.retryConfig.MaxDelay {
				delay = s.retryConfig.MaxDelay
			}
		}

		startTime := time.Now()
		resp, err := s.callProvider(ctx, provider, req)
		latency := time.Since(startTime).Milliseconds()

		if err != nil {
			lastErr = err
			// 判断是否可重试的错误
			if !s.isRetryableError(err) {
				return nil, err
			}
			log.Printf("[LLMProvider] 重试 %d/%d, 提供商: %s, 错误: %v", attempt, s.retryConfig.MaxRetries, provider.Name, err)
			continue
		}

		// 更新延迟指标
		s.updateLatencyMetric(provider.ID, latency)

		return resp, nil
	}

	return nil, fmt.Errorf("重试 %d 次后仍然失败: %w", s.retryConfig.MaxRetries, lastErr)
}

// callProvider 调用单个提供商
func (s *LLMProviderService) callProvider(ctx context.Context, provider *model.SysLLMConfig, req *model.LLMRequest) (*model.LLMResponse, error) {
	switch provider.Provider {
	case model.ProviderAnthropic:
		return s.callAnthropic(ctx, provider, req)
	case model.ProviderOpenAI:
		return s.callOpenAI(ctx, provider, req)
	case model.ProviderAzure:
		return s.callAzure(ctx, provider, req)
	case model.ProviderCustom:
		return s.callCustom(ctx, provider, req)
	default:
		return s.callAnthropic(ctx, provider, req)
	}
}

// callAnthropic 调用Anthropic API
func (s *LLMProviderService) callAnthropic(ctx context.Context, provider *model.SysLLMConfig, req *model.LLMRequest) (*model.LLMResponse, error) {
	// 构建请求
	anthropicReq := map[string]interface{}{
		"model":      provider.ModelName,
		"max_tokens": req.MaxTokens,
		"messages":   req.Messages,
	}
	if req.System != "" {
		anthropicReq["system"] = req.System
	}
	if req.Temperature > 0 {
		anthropicReq["temperature"] = req.Temperature
	}

	body, err := json.Marshal(anthropicReq)
	if err != nil {
		return nil, fmt.Errorf("序列化请求失败: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", provider.BaseURL+"/v1/messages", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("创建请求失败: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("x-api-key", provider.APIKey)
	httpReq.Header.Set("anthropic-version", "2023-06-01")

	resp, err := s.httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("发送请求失败: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("读取响应失败: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("API错误[%d]: %s", resp.StatusCode, string(respBody))
	}

	var result struct {
		ID      string `json:"id"`
		Model   string `json:"model"`
		Content []struct {
			Type string `json:"type"`
			Text string `json:"text"`
		} `json:"content"`
		Usage struct {
			InputTokens  int `json:"input_tokens"`
			OutputTokens int `json:"output_tokens"`
		} `json:"usage"`
	}

	if err := json.Unmarshal(respBody, &result); err != nil {
		return nil, fmt.Errorf("解析响应失败: %w", err)
	}

	content := ""
	if len(result.Content) > 0 {
		content = result.Content[0].Text
	}

	return &model.LLMResponse{
		ID:         result.ID,
		Provider:   provider.Provider,
		Model:      result.Model,
		Content:    content,
		ProviderID: provider.ID,
		Usage: model.LLMUsage{
			InputTokens:  result.Usage.InputTokens,
			OutputTokens: result.Usage.OutputTokens,
		},
	}, nil
}

// callOpenAI 调用OpenAI API
func (s *LLMProviderService) callOpenAI(ctx context.Context, provider *model.SysLLMConfig, req *model.LLMRequest) (*model.LLMResponse, error) {
	// 构建OpenAI格式请求
	messages := make([]map[string]string, 0)
	if req.System != "" {
		messages = append(messages, map[string]string{
			"role":    "system",
			"content": req.System,
		})
	}
	for _, m := range req.Messages {
		messages = append(messages, map[string]string{
			"role":    m.Role,
			"content": m.Content,
		})
	}

	openaiReq := map[string]interface{}{
		"model":      provider.ModelName,
		"max_tokens": req.MaxTokens,
		"messages":   messages,
	}
	if req.Temperature > 0 {
		openaiReq["temperature"] = req.Temperature
	}

	body, err := json.Marshal(openaiReq)
	if err != nil {
		return nil, fmt.Errorf("序列化请求失败: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", provider.BaseURL+"/v1/chat/completions", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("创建请求失败: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+provider.APIKey)

	resp, err := s.httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("发送请求失败: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("读取响应失败: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("API错误[%d]: %s", resp.StatusCode, string(respBody))
	}

	var result struct {
		ID      string `json:"id"`
		Model   string `json:"model"`
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
		Usage struct {
			PromptTokens     int `json:"prompt_tokens"`
			CompletionTokens int `json:"completion_tokens"`
		} `json:"usage"`
	}

	if err := json.Unmarshal(respBody, &result); err != nil {
		return nil, fmt.Errorf("解析响应失败: %w", err)
	}

	content := ""
	if len(result.Choices) > 0 {
		content = result.Choices[0].Message.Content
	}

	return &model.LLMResponse{
		ID:         result.ID,
		Provider:   provider.Provider,
		Model:      result.Model,
		Content:    content,
		ProviderID: provider.ID,
		Usage: model.LLMUsage{
			InputTokens:  result.Usage.PromptTokens,
			OutputTokens: result.Usage.CompletionTokens,
		},
	}, nil
}

// callAzure 调用Azure OpenAI API
func (s *LLMProviderService) callAzure(ctx context.Context, provider *model.SysLLMConfig, req *model.LLMRequest) (*model.LLMResponse, error) {
	// Azure OpenAI 格式与 OpenAI 类似，但认证方式不同
	messages := make([]map[string]string, 0)
	if req.System != "" {
		messages = append(messages, map[string]string{
			"role":    "system",
			"content": req.System,
		})
	}
	for _, m := range req.Messages {
		messages = append(messages, map[string]string{
			"role":    m.Role,
			"content": m.Content,
		})
	}

	azureReq := map[string]interface{}{
		"max_tokens": req.MaxTokens,
		"messages":   messages,
	}
	if req.Temperature > 0 {
		azureReq["temperature"] = req.Temperature
	}

	body, err := json.Marshal(azureReq)
	if err != nil {
		return nil, fmt.Errorf("序列化请求失败: %w", err)
	}

	// Azure OpenAI URL格式: {endpoint}/openai/deployments/{deployment-id}/chat/completions?api-version=xxx
	httpReq, err := http.NewRequestWithContext(ctx, "POST", provider.BaseURL, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("创建请求失败: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("api-key", provider.APIKey)

	resp, err := s.httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("发送请求失败: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("读取响应失败: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("API错误[%d]: %s", resp.StatusCode, string(respBody))
	}

	var result struct {
		ID      string `json:"id"`
		Model   string `json:"model"`
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
		Usage struct {
			PromptTokens     int `json:"prompt_tokens"`
			CompletionTokens int `json:"completion_tokens"`
		} `json:"usage"`
	}

	if err := json.Unmarshal(respBody, &result); err != nil {
		return nil, fmt.Errorf("解析响应失败: %w", err)
	}

	content := ""
	if len(result.Choices) > 0 {
		content = result.Choices[0].Message.Content
	}

	return &model.LLMResponse{
		ID:         result.ID,
		Provider:   provider.Provider,
		Model:      result.Model,
		Content:    content,
		ProviderID: provider.ID,
		Usage: model.LLMUsage{
			InputTokens:  result.Usage.PromptTokens,
			OutputTokens: result.Usage.CompletionTokens,
		},
	}, nil
}

// callCustom 调用自定义API
func (s *LLMProviderService) callCustom(ctx context.Context, provider *model.SysLLMConfig, req *model.LLMRequest) (*model.LLMResponse, error) {
	// 自定义API，尝试兼容OpenAI格式
	return s.callOpenAI(ctx, provider, req)
}

// isRetryableError 判断错误是否可重试
func (s *LLMProviderService) isRetryableError(err error) bool {
	if err == nil {
		return false
	}
	errStr := err.Error()
	// 网络错误、超时、5xx错误可重试
	return contains(errStr, "timeout") ||
		contains(errStr, "connection refused") ||
		contains(errStr, "EOF") ||
		contains(errStr, "500") ||
		contains(errStr, "502") ||
		contains(errStr, "503") ||
		contains(errStr, "504") ||
		contains(errStr, "429") // Rate limit
}

// recordSuccess 记录成功
func (s *LLMProviderService) recordSuccess(providerID int64) {
	s.mu.Lock()
	defer s.mu.Unlock()

	metric, exists := s.healthMetrics[providerID]
	if !exists {
		metric = &model.ProviderHealthMetric{
			ConfigID:     providerID,
			CircuitState: model.CircuitClosed,
		}
		s.healthMetrics[providerID] = metric
	}

	metric.TotalRequests++
	metric.SuccessRequests++
	metric.LastSuccessTime = time.Now().UnixMilli()
	metric.ConsecutiveFails = 0

	// 熔断器状态转换
	if metric.CircuitState == model.CircuitHalfOpen {
		// 半开状态下成功，检查是否可以关闭
		if metric.SuccessRequests-metric.FailedRequests >= int64(s.cbConfig.SuccessThreshold) {
			metric.CircuitState = model.CircuitClosed
			metric.Status = model.ProviderStatusHealthy
			log.Printf("[LLMProvider] 提供商 (ID:%d) 熔断器关闭，恢复正常", providerID)
		}
	}
}

// recordFailure 记录失败
func (s *LLMProviderService) recordFailure(providerID int64, reason string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	metric, exists := s.healthMetrics[providerID]
	if !exists {
		metric = &model.ProviderHealthMetric{
			ConfigID:     providerID,
			CircuitState: model.CircuitClosed,
		}
		s.healthMetrics[providerID] = metric
	}

	metric.TotalRequests++
	metric.FailedRequests++
	metric.LastFailTime = time.Now().UnixMilli()
	metric.LastFailReason = reason
	metric.ConsecutiveFails++

	// 更新健康状态
	failRate := float64(metric.FailedRequests) / float64(metric.TotalRequests)
	if failRate > 0.5 {
		metric.Status = model.ProviderStatusUnhealthy
	} else if failRate > 0.2 {
		metric.Status = model.ProviderStatusDegraded
	}

	// 熔断器状态转换
	if metric.CircuitState == model.CircuitClosed {
		if metric.ConsecutiveFails >= s.cbConfig.FailureThreshold {
			metric.CircuitState = model.CircuitOpen
			metric.CircuitOpenTime = time.Now().UnixMilli()
			log.Printf("[LLMProvider] 提供商 (ID:%d) 熔断器打开，开始熔断", providerID)
		}
	} else if metric.CircuitState == model.CircuitHalfOpen {
		// 半开状态下失败，重新打开熔断器
		metric.CircuitState = model.CircuitOpen
		metric.CircuitOpenTime = time.Now().UnixMilli()
		log.Printf("[LLMProvider] 提供商 (ID:%d) 半开状态下失败，重新熔断", providerID)
	}
}

// updateLatencyMetric 更新延迟指标
func (s *LLMProviderService) updateLatencyMetric(providerID int64, latencyMs int64) {
	s.mu.Lock()
	defer s.mu.Unlock()

	metric, exists := s.healthMetrics[providerID]
	if !exists {
		return
	}

	metric.TotalLatency += latencyMs
	if metric.TotalRequests > 0 {
		metric.AvgLatency = metric.TotalLatency / metric.TotalRequests
	}
}

// startHealthCheck 启动健康检查
func (s *LLMProviderService) startHealthCheck() {
	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		s.checkProvidersHealth()
	}
}

// checkProvidersHealth 检查提供商健康状态
func (s *LLMProviderService) checkProvidersHealth() {
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now().UnixMilli()
	for id, metric := range s.healthMetrics {
		// 检查熔断器是否可以转为半开
		if metric.CircuitState == model.CircuitOpen {
			elapsed := now - metric.CircuitOpenTime
			if elapsed >= int64(s.cbConfig.Timeout/time.Millisecond) {
				metric.CircuitState = model.CircuitHalfOpen
				log.Printf("[LLMProvider] 提供商 (ID:%d) 熔断器进入半开状态", id)
			}
		}

		// 更新健康状态
		if metric.TotalRequests > 10 {
			failRate := float64(metric.FailedRequests) / float64(metric.TotalRequests)
			if failRate > 0.5 {
				metric.Status = model.ProviderStatusUnhealthy
			} else if failRate > 0.2 {
				metric.Status = model.ProviderStatusDegraded
			} else {
				metric.Status = model.ProviderStatusHealthy
			}
		}
	}
}

// logFailover 记录故障转移日志
func (s *LLMProviderService) logFailover(sessionID string, attemptedProviders []int64, lastErr error) {
	if len(attemptedProviders) < 2 {
		return // 没有实际的故障转移
	}

	failoverLog := &model.FailoverLog{
		SessionID:        sessionID,
		OriginalConfigID: attemptedProviders[0],
		FailoverConfigID: attemptedProviders[len(attemptedProviders)-1],
		Reason:           "primary_provider_failed",
		OriginalError:    lastErr.Error(),
		RetryCount:       len(attemptedProviders) - 1,
		CreateTime:       time.Now().UnixMilli(),
	}

	if err := s.db.Create(failoverLog).Error; err != nil {
		log.Printf("[LLMProvider] 记录故障转移日志失败: %v", err)
	}
}

// GetProviderHealth 获取提供商健康状态
func (s *LLMProviderService) GetProviderHealth() []model.ProviderHealthMetric {
	s.mu.RLock()
	defer s.mu.RUnlock()

	result := make([]model.ProviderHealthMetric, 0, len(s.healthMetrics))
	for _, metric := range s.healthMetrics {
		result = append(result, *metric)
	}
	return result
}

// GetProviders 获取所有提供商配置
func (s *LLMProviderService) GetProviders() []*model.SysLLMConfig {
	s.mu.RLock()
	defer s.mu.RUnlock()

	result := make([]*model.SysLLMConfig, len(s.providers))
	copy(result, s.providers)
	return result
}

// encryptAPIKey 加密API Key
func (s *LLMProviderService) encryptAPIKey(plainText string) (string, error) {
	block, err := aes.NewCipher(s.encryptionKey)
	if err != nil {
		return "", err
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}

	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return "", err
	}

	cipherText := gcm.Seal(nonce, nonce, []byte(plainText), nil)
	return base64.StdEncoding.EncodeToString(cipherText), nil
}

// decryptAPIKey 解密API Key
func (s *LLMProviderService) decryptAPIKey(cipherText string) (string, error) {
	// 如果不是加密的，直接返回 (兼容未加密的历史数据)
	if len(cipherText) < 24 {
		return cipherText, nil
	}

	data, err := base64.StdEncoding.DecodeString(cipherText)
	if err != nil {
		// 解码失败，可能是未加密的明文
		return cipherText, nil
	}

	block, err := aes.NewCipher(s.encryptionKey)
	if err != nil {
		return "", err
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}

	nonceSize := gcm.NonceSize()
	if len(data) < nonceSize {
		return cipherText, nil
	}

	nonce, cipherData := data[:nonceSize], data[nonceSize:]
	plainText, err := gcm.Open(nil, nonce, cipherData, nil)
	if err != nil {
		// 解密失败，可能是未加密的明文
		return cipherText, nil
	}

	return string(plainText), nil
}

// contains 检查字符串是否包含子串
func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > len(substr) && (s[:len(substr)] == substr || s[len(s)-len(substr):] == substr || containsMiddle(s, substr)))
}

func containsMiddle(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
