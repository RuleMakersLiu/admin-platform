package claude

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/spf13/viper"
)

// Client Claude API客户端
type Client struct {
	APIKey  string
	APIURL  string
	Model   string
	Timeout time.Duration
}

// Message 消息
type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// Request 请求
type Request struct {
	Model     string    `json:"model"`
	MaxTokens int       `json:"max_tokens"`
	Messages  []Message `json:"messages"`
}

// Response 响应
type Response struct {
	ID      string `json:"id"`
	Type    string `json:"type"`
	Role    string `json:"role"`
	Content []struct {
		Type string `json:"type"`
		Text string `json:"text"`
	} `json:"content"`
	Model      string `json:"model"`
	Usage      Usage  `json:"usage"`
	StopReason string `json:"stop_reason"`
}

// Usage Token使用量
type Usage struct {
	InputTokens  int `json:"input_tokens"`
	OutputTokens int `json:"output_tokens"`
}

// NewClient 创建客户端
func NewClient() *Client {
	return &Client{
		APIKey:  viper.GetString("claude.api_key"),
		APIURL:  viper.GetString("claude.api_url"),
		Model:   viper.GetString("claude.model"),
		Timeout: time.Duration(viper.GetInt("claude.timeout")) * time.Second,
	}
}

// Chat 发送消息
func (c *Client) Chat(messages []Message) (*Response, error) {
	req := Request{
		Model:     c.Model,
		MaxTokens: viper.GetInt("claude.max_tokens"),
		Messages:  messages,
	}

	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("序列化请求失败: %w", err)
	}

	httpReq, err := http.NewRequest("POST", c.APIURL, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("创建请求失败: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("x-api-key", c.APIKey)
	httpReq.Header.Set("anthropic-version", "2023-06-01")

	client := &http.Client{Timeout: c.Timeout}
	resp, err := client.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("请求失败: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("读取响应失败: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("API错误: %s", string(respBody))
	}

	var result Response
	if err := json.Unmarshal(respBody, &result); err != nil {
		return nil, fmt.Errorf("解析响应失败: %w", err)
	}

	return &result, nil
}

// GetContent 获取响应内容
func (r *Response) GetContent() string {
	if len(r.Content) > 0 {
		return r.Content[0].Text
	}
	return ""
}

// ParseNaturalLanguage 解析自然语言生成配置
func (c *Client) ParseNaturalLanguage(prompt string) (string, error) {
	systemPrompt := `你是一个代码生成助手。用户会描述需要创建的功能，你需要解析并返回结构化的JSON配置。

返回格式示例：
{
  "table": "product",
  "function_name": "商品管理",
  "function_desc": "商品信息管理功能",
  "fields": [
    {"name": "name", "type": "varchar(100)", "label": "商品名称", "required": true, "list": true, "form": true, "query": true, "query_type": "like"},
    {"name": "price", "type": "decimal(10,2)", "label": "价格", "required": true, "list": true, "form": true},
    {"name": "stock", "type": "int", "label": "库存", "required": false, "list": true, "form": true}
  ]
}

只返回JSON，不要包含其他说明文字。`

	messages := []Message{
		{Role: "user", Content: prompt},
	}

	// 添加系统提示（Claude API使用不同的方式传递系统提示）
	reqBody := map[string]interface{}{
		"model":      c.Model,
		"max_tokens": viper.GetInt("claude.max_tokens"),
		"system":     systemPrompt,
		"messages":   messages,
	}

	body, _ := json.Marshal(reqBody)

	httpReq, _ := http.NewRequest("POST", c.APIURL, bytes.NewReader(body))
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("x-api-key", c.APIKey)
	httpReq.Header.Set("anthropic-version", "2023-06-01")

	client := &http.Client{Timeout: c.Timeout}
	resp, err := client.Do(httpReq)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)

	var result Response
	json.Unmarshal(respBody, &result)

	return result.GetContent(), nil
}
