package service

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"time"

	"admin-config/internal/config"
	"admin-config/internal/model"
	"admin-config/pkg/crypto"

	"gorm.io/gorm"
)

// LLM 提供商常量
const (
	ProviderOpenAI    = "openai"
	ProviderDeepSeek  = "deepseek"
	ProviderAnthropic = "anthropic"
	ProviderQwen      = "qwen"
	ProviderZhipu     = "zhipu"
	ProviderCustom    = "custom"
)

// TestConnectionResult 测试连接结果
type TestConnectionResult struct {
	Success   bool   `json:"success"`
	Message   string `json:"message"`
	Model     string `json:"model,omitempty"`
	Latency   int64  `json:"latency"` // 响应耗时(毫秒)
	Provider  string `json:"provider"`
	Response  string `json:"response,omitempty"` // 模型返回的测试内容
}

// LLMService LLM配置服务
type LLMService struct {
	db     *gorm.DB
	crypto *crypto.AESCrypto
}

// NewLLMService 创建LLM服务
func NewLLMService(db *gorm.DB) (*LLMService, error) {
	aesCrypto, err := crypto.NewAESCrypto(config.GlobalConfig.Crypto.AESKey)
	if err != nil {
		return nil, err
	}
	return &LLMService{
		db:     db,
		crypto: aesCrypto,
	}, nil
}

// Create 创建LLM配置
func (s *LLMService) Create(adminID, tenantID int64, req *model.LLMConfigCreate) (*model.LLMConfig, error) {
	// 加密API Key
	encryptedKey, err := s.crypto.Encrypt(req.APIKey)
	if err != nil {
		return nil, err
	}

	now := time.Now().UnixMilli()
	llm := &model.LLMConfig{
		Name:        req.Name,
		Provider:    req.Provider,
		BaseURL:     req.BaseURL,
		APIKey:      encryptedKey,
		ModelName:   req.ModelName,
		MaxTokens:   req.MaxTokens,
		Temperature: req.Temperature,
		ExtraConfig: req.ExtraConfig,
		IsDefault:   req.IsDefault,
		Status:      1,
		TenantID:    tenantID,
		AdminID:     adminID,
		CreateTime:  now,
		UpdateTime:  now,
	}

	// 如果设置为默认，先取消其他默认配置
	if llm.IsDefault == 1 {
		s.db.Model(&model.LLMConfig{}).
			Where("tenant_id = ? AND is_default = 1", tenantID).
			Update("is_default", 0)
	}

	if err := s.db.Create(llm).Error; err != nil {
		return nil, err
	}

	return llm, nil
}

// Update 更新LLM配置
func (s *LLMService) Update(id int64, tenantID int64, req *model.LLMConfigUpdate) (*model.LLMConfig, error) {
	var llm model.LLMConfig
	if err := s.db.Where("id = ? AND tenant_id = ?", id, tenantID).First(&llm).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, errors.New("配置不存在")
		}
		return nil, err
	}

	updates := make(map[string]interface{})

	if req.Name != "" {
		updates["name"] = req.Name
	}
	if req.BaseURL != "" {
		updates["base_url"] = req.BaseURL
	}
	if req.APIKey != "" {
		encryptedKey, err := s.crypto.Encrypt(req.APIKey)
		if err != nil {
			return nil, err
		}
		updates["api_key"] = encryptedKey
	}
	if req.ModelName != "" {
		updates["model_name"] = req.ModelName
	}
	if req.MaxTokens != nil {
		updates["max_tokens"] = *req.MaxTokens
	}
	if req.Temperature != nil {
		updates["temperature"] = *req.Temperature
	}
	if req.ExtraConfig != nil {
		updates["extra_config"] = req.ExtraConfig
	}
	if req.IsDefault != nil {
		// 如果设置为默认，先取消其他默认配置
		if *req.IsDefault == 1 {
			s.db.Model(&model.LLMConfig{}).
				Where("tenant_id = ? AND is_default = 1 AND id != ?", tenantID, id).
				Update("is_default", 0)
		}
		updates["is_default"] = *req.IsDefault
	}
	if req.Status != nil {
		updates["status"] = *req.Status
	}

	updates["update_time"] = time.Now().UnixMilli()

	if err := s.db.Model(&llm).Updates(updates).Error; err != nil {
		return nil, err
	}

	// 重新查询
	if err := s.db.Where("id = ?", id).First(&llm).Error; err != nil {
		return nil, err
	}

	return &llm, nil
}

// Delete 删除LLM配置
func (s *LLMService) Delete(id int64, tenantID int64) error {
	result := s.db.Where("id = ? AND tenant_id = ?", id, tenantID).Delete(&model.LLMConfig{})
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return errors.New("配置不存在")
	}
	return nil
}

// GetByID 根据ID获取LLM配置
func (s *LLMService) GetByID(id int64, tenantID int64) (*model.LLMConfig, error) {
	var llm model.LLMConfig
	if err := s.db.Where("id = ? AND tenant_id = ?", id, tenantID).First(&llm).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, errors.New("配置不存在")
		}
		return nil, err
	}
	return &llm, nil
}

// List 获取LLM配置列表
func (s *LLMService) List(tenantID int64, status *int) ([]*model.LLMConfig, int64, error) {
	var list []*model.LLMConfig
	var total int64

	query := s.db.Model(&model.LLMConfig{}).Where("tenant_id = ?", tenantID)

	if status != nil {
		query = query.Where("status = ?", *status)
	}

	if err := query.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	if err := query.Order("is_default desc, create_time desc").Find(&list).Error; err != nil {
		return nil, 0, err
	}

	return list, total, nil
}

// GetDefault 获取默认LLM配置
func (s *LLMService) GetDefault(tenantID int64) (*model.LLMConfig, error) {
	var llm model.LLMConfig
	if err := s.db.Where("tenant_id = ? AND is_default = 1 AND status = 1", tenantID).First(&llm).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, errors.New("未配置默认LLM")
		}
		return nil, err
	}
	return &llm, nil
}

// DecryptAPIKey 解密API Key（供内部调用使用）
func (s *LLMService) DecryptAPIKey(encryptedKey string) (string, error) {
	return s.crypto.Decrypt(encryptedKey)
}

// TestConnection 测试LLM连接
// 通过发送一个简单的 chat completion 请求来验证配置是否正确
func (s *LLMService) TestConnection(id int64, tenantID int64) (*TestConnectionResult, error) {
	// 1. 获取配置
	llm, err := s.GetByID(id, tenantID)
	if err != nil {
		return nil, err
	}

	// 2. 检查配置状态
	if llm.Status != 1 {
		return &TestConnectionResult{
			Success:  false,
			Message:  "配置已禁用，请先启用配置",
			Provider: llm.Provider,
		}, nil
	}

	// 3. 解密API Key
	apiKey, err := s.DecryptAPIKey(llm.APIKey)
	if err != nil {
		return &TestConnectionResult{
			Success:  false,
			Message:  "API Key 解密失败: " + err.Error(),
			Provider: llm.Provider,
		}, nil
	}

	// 4. 根据提供商构建测试请求
	return s.testLLMConnection(llm, apiKey)
}

// testLLMConnection 执行实际的LLM连接测试
func (s *LLMService) testLLMConnection(llm *model.LLMConfig, apiKey string) (*TestConnectionResult, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	startTime := time.Now()

	// 根据 provider 选择测试方式
	switch llm.Provider {
	case ProviderAnthropic:
		return s.testAnthropicConnection(ctx, llm, apiKey, startTime)
	default:
		// OpenAI 兼容 API (OpenAI, DeepSeek, Qwen, Zhipu, Custom 等)
		return s.testOpenAICompatibleConnection(ctx, llm, apiKey, startTime)
	}
}

// testOpenAICompatibleConnection 测试 OpenAI 兼容 API 连接
// 适用于 OpenAI, DeepSeek, Qwen, Zhipu 等兼容 OpenAI 格式的提供商
func (s *LLMService) testOpenAICompatibleConnection(ctx context.Context, llm *model.LLMConfig, apiKey string, startTime time.Time) (*TestConnectionResult, error) {
	// 构建请求体 - 发送一个简单的测试消息
	requestBody := map[string]interface{}{
		"model": llm.ModelName,
		"messages": []map[string]string{
			{
				"role":    "user",
				"content": "Hello, please respond with 'OK' to confirm the connection.",
			},
		},
		"max_tokens":  50, // 测试只需要少量 token
		"temperature": 0.1,
		"stream":      false,
	}

	jsonBody, err := json.Marshal(requestBody)
	if err != nil {
		return &TestConnectionResult{
			Success:  false,
			Message:  "构建请求失败: " + err.Error(),
			Provider: llm.Provider,
			Model:    llm.ModelName,
		}, nil
	}

	// 构建完整的 API URL
	apiURL := llm.BaseURL
	// 确保 URL 以 /chat/completions 结尾
	if apiURL[len(apiURL)-1] == '/' {
		apiURL = apiURL[:len(apiURL)-1]
	}
	if !endsWith(apiURL, "/chat/completions") {
		apiURL = apiURL + "/v1/chat/completions"
	}

	// 创建 HTTP 请求
	req, err := http.NewRequestWithContext(ctx, "POST", apiURL, bytes.NewReader(jsonBody))
	if err != nil {
		return &TestConnectionResult{
			Success:  false,
			Message:  "创建请求失败: " + err.Error(),
			Provider: llm.Provider,
			Model:    llm.ModelName,
		}, nil
	}

	// 设置请求头
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+apiKey)

	// 某些提供商可能需要额外的 header
	if llm.Provider == ProviderDeepSeek {
		// DeepSeek 使用标准 Bearer token
	} else if llm.Provider == ProviderQwen {
		// 通义千问使用 Authorization: Bearer
	}

	// 发送请求
	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		latency := time.Since(startTime).Milliseconds()
		return &TestConnectionResult{
			Success:  false,
			Message:  "连接失败: " + err.Error(),
			Provider: llm.Provider,
			Model:    llm.ModelName,
			Latency:  latency,
		}, nil
	}
	defer resp.Body.Close()

	latency := time.Since(startTime).Milliseconds()

	// 读取响应
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return &TestConnectionResult{
			Success:  false,
			Message:  "读取响应失败: " + err.Error(),
			Provider: llm.Provider,
			Model:    llm.ModelName,
			Latency:  latency,
		}, nil
	}

	// 检查 HTTP 状态码
	if resp.StatusCode != http.StatusOK {
		// 尝试解析错误信息
		var errResp OpenAIErrorResponse
		if json.Unmarshal(body, &errResp) == nil && errResp.Error.Message != "" {
			return &TestConnectionResult{
				Success:  false,
				Message:  fmt.Sprintf("API 错误 (HTTP %d): %s", resp.StatusCode, errResp.Error.Message),
				Provider: llm.Provider,
				Model:    llm.ModelName,
				Latency:  latency,
			}, nil
		}
		return &TestConnectionResult{
			Success:  false,
			Message:  fmt.Sprintf("HTTP 错误: %d, 响应: %s", resp.StatusCode, string(body)),
			Provider: llm.Provider,
			Model:    llm.ModelName,
			Latency:  latency,
		}, nil
	}

	// 解析成功响应
	var successResp OpenAIChatResponse
	if err := json.Unmarshal(body, &successResp); err != nil {
		return &TestConnectionResult{
			Success:  false,
			Message:  "解析响应失败: " + err.Error(),
			Provider: llm.Provider,
			Model:    llm.ModelName,
			Latency:  latency,
		}, nil
	}

	// 提取响应内容
	var responseContent string
	if len(successResp.Choices) > 0 {
		responseContent = successResp.Choices[0].Message.Content
	}

	return &TestConnectionResult{
		Success:  true,
		Message:  "连接成功",
		Provider: llm.Provider,
		Model:    successResp.Model,
		Latency:  latency,
		Response: responseContent,
	}, nil
}

// testAnthropicConnection 测试 Anthropic Claude API 连接
// Anthropic 使用不同的 API 格式
func (s *LLMService) testAnthropicConnection(ctx context.Context, llm *model.LLMConfig, apiKey string, startTime time.Time) (*TestConnectionResult, error) {
	// 构建请求体 - Anthropic 格式
	requestBody := map[string]interface{}{
		"model":      llm.ModelName,
		"max_tokens": 50,
		"messages": []map[string]string{
			{
				"role":    "user",
				"content": "Hello, please respond with 'OK' to confirm the connection.",
			},
		},
	}

	jsonBody, err := json.Marshal(requestBody)
	if err != nil {
		return &TestConnectionResult{
			Success:  false,
			Message:  "构建请求失败: " + err.Error(),
			Provider: llm.Provider,
			Model:    llm.ModelName,
		}, nil
	}

	// 构建完整的 API URL
	apiURL := llm.BaseURL
	if apiURL[len(apiURL)-1] == '/' {
		apiURL = apiURL[:len(apiURL)-1]
	}
	if !endsWith(apiURL, "/messages") {
		apiURL = apiURL + "/v1/messages"
	}

	// 创建 HTTP 请求
	req, err := http.NewRequestWithContext(ctx, "POST", apiURL, bytes.NewReader(jsonBody))
	if err != nil {
		return &TestConnectionResult{
			Success:  false,
			Message:  "创建请求失败: " + err.Error(),
			Provider: llm.Provider,
			Model:    llm.ModelName,
		}, nil
	}

	// 设置请求头 - Anthropic 特定格式
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-api-key", apiKey)
	req.Header.Set("anthropic-version", "2023-06-01")

	// 发送请求
	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		latency := time.Since(startTime).Milliseconds()
		return &TestConnectionResult{
			Success:  false,
			Message:  "连接失败: " + err.Error(),
			Provider: llm.Provider,
			Model:    llm.ModelName,
			Latency:  latency,
		}, nil
	}
	defer resp.Body.Close()

	latency := time.Since(startTime).Milliseconds()

	// 读取响应
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return &TestConnectionResult{
			Success:  false,
			Message:  "读取响应失败: " + err.Error(),
			Provider: llm.Provider,
			Model:    llm.ModelName,
			Latency:  latency,
		}, nil
	}

	// 检查 HTTP 状态码
	if resp.StatusCode != http.StatusOK {
		return &TestConnectionResult{
			Success:  false,
			Message:  fmt.Sprintf("HTTP 错误: %d, 响应: %s", resp.StatusCode, string(body)),
			Provider: llm.Provider,
			Model:    llm.ModelName,
			Latency:  latency,
		}, nil
	}

	// 解析成功响应
	var successResp AnthropicResponse
	if err := json.Unmarshal(body, &successResp); err != nil {
		return &TestConnectionResult{
			Success:  false,
			Message:  "解析响应失败: " + err.Error(),
			Provider: llm.Provider,
			Model:    llm.ModelName,
			Latency:  latency,
		}, nil
	}

	// 提取响应内容
	var responseContent string
	if len(successResp.Content) > 0 {
		responseContent = successResp.Content[0].Text
	}

	return &TestConnectionResult{
		Success:  true,
		Message:  "连接成功",
		Provider: llm.Provider,
		Model:    successResp.Model,
		Latency:  latency,
		Response: responseContent,
	}, nil
}

// endsWith 检查字符串是否以指定后缀结尾
func endsWith(s, suffix string) bool {
	if len(suffix) > len(s) {
		return false
	}
	return s[len(s)-len(suffix):] == suffix
}

// OpenAI API 响应结构定义

// OpenAIErrorResponse OpenAI 错误响应
type OpenAIErrorResponse struct {
	Error struct {
		Message string `json:"message"`
		Type    string `json:"type"`
		Code    string `json:"code"`
	} `json:"error"`
}

// OpenAIChatResponse OpenAI Chat 响应
type OpenAIChatResponse struct {
	ID      string `json:"id"`
	Object  string `json:"object"`
	Created int64  `json:"created"`
	Model   string `json:"model"`
	Choices []struct {
		Index   int `json:"index"`
		Message struct {
			Role    string `json:"role"`
			Content string `json:"content"`
		} `json:"message"`
		FinishReason string `json:"finish_reason"`
	} `json:"choices"`
	Usage struct {
		PromptTokens     int `json:"prompt_tokens"`
		CompletionTokens int `json:"completion_tokens"`
		TotalTokens      int `json:"total_tokens"`
	} `json:"usage"`
}

// AnthropicResponse Anthropic Claude 响应
type AnthropicResponse struct {
	ID      string `json:"id"`
	Type    string `json:"type"`
	Role    string `json:"role"`
	Model   string `json:"model"`
	Content []struct {
		Type string `json:"type"`
		Text string `json:"text"`
	} `json:"content"`
	StopReason string `json:"stop_reason"`
	Usage      struct {
		InputTokens  int `json:"input_tokens"`
		OutputTokens int `json:"output_tokens"`
	} `json:"usage"`
}
