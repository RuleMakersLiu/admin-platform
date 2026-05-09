package claude

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"admin-agent/internal/config"
)

// Message Claude API消息
type Message struct {
	Role    string `json:"role"`    // user/assistant
	Content string `json:"content"` // 消息内容
}

// Request Claude API请求
type Request struct {
	Model     string    `json:"model"`           // 模型名称
	MaxTokens int       `json:"max_tokens"`      // 最大token数
	Messages  []Message `json:"messages"`        // 消息列表
	System    string    `json:"system,omitempty"` // System Prompt
	Stream    bool      `json:"stream"`          // 是否流式
}

// Response Claude API响应
type Response struct {
	ID      string `json:"id"`
	Type    string `json:"type"`
	Role    string `json:"role"`
	Content []struct {
		Type string `json:"type"`
		Text string `json:"text"`
	} `json:"content"`
	Model       string `json:"model"`
	StopReason  string `json:"stop_reason"`
	Usage       Usage  `json:"usage"`
}

// Usage Token使用统计
type Usage struct {
	InputTokens  int `json:"input_tokens"`
	OutputTokens int `json:"output_tokens"`
}

// StreamResponse 流式响应
type StreamResponse struct {
	Type         string `json:"type"`
	Index        int    `json:"index"`
	Delta        Delta  `json:"delta"`
	ContentBlock *struct {
		Type string `json:"type"`
		Text string `json:"text"`
	} `json:"content_block,omitempty"`
	Message *Response `json:"message,omitempty"`
}

// Delta 增量内容
type Delta struct {
	Type string `json:"type"`
	Text string `json:"text"`
	StopReason string `json:"stop_reason,omitempty"`
}

// Client Claude API客户端
type Client struct {
	apiKey   string
	baseURL  string
	timeout  time.Duration
	httpClient *http.Client
}

// NewClient 创建新客户端
func NewClient(cfg *config.ClaudeConfig) *Client {
	return &Client{
		apiKey:  cfg.APIKey,
		baseURL: cfg.BaseURL,
		timeout: time.Duration(cfg.Timeout) * time.Second,
		httpClient: &http.Client{
			Timeout: time.Duration(cfg.Timeout) * time.Second,
		},
	}
}

// Chat 发送对话请求
func (c *Client) Chat(req *Request) (*Response, error) {
	req.Stream = false

	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("序列化请求失败: %w", err)
	}

	httpReq, err := http.NewRequest("POST", c.baseURL+"/v1/messages", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("创建请求失败: %w", err)
	}

	c.setHeaders(httpReq)

	resp, err := c.httpClient.Do(httpReq)
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

	var result Response
	if err := json.Unmarshal(respBody, &result); err != nil {
		return nil, fmt.Errorf("解析响应失败: %w", err)
	}

	return &result, nil
}

// ChatStream 发送流式对话请求
func (c *Client) ChatStream(req *Request, onChunk func(text string) error) (*Response, error) {
	req.Stream = true

	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("序列化请求失败: %w", err)
	}

	httpReq, err := http.NewRequest("POST", c.baseURL+"/v1/messages", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("创建请求失败: %w", err)
	}

	c.setHeaders(httpReq)
	httpReq.Header.Set("Accept", "text/event-stream")

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("发送请求失败: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("API错误[%d]: %s", resp.StatusCode, string(respBody))
	}

	var finalResponse Response
	var fullText string

	decoder := NewSSEDecoder(resp.Body)
	for {
		event, err := decoder.Decode()
		if err != nil {
			if err == io.EOF {
				break
			}
			return nil, fmt.Errorf("解码SSE失败: %w", err)
		}

		if event == nil || event.Data == "" {
			continue
		}

		if event.Data == "[DONE]" {
			break
		}

		var streamResp StreamResponse
		if err := json.Unmarshal([]byte(event.Data), &streamResp); err != nil {
			continue
		}

		switch streamResp.Type {
		case "content_block_delta":
			if streamResp.Delta.Type == "text_delta" && streamResp.Delta.Text != "" {
				fullText += streamResp.Delta.Text
				if onChunk != nil {
					if err := onChunk(streamResp.Delta.Text); err != nil {
						return nil, err
					}
				}
			}
		case "message_delta":
			if streamResp.Message != nil {
				finalResponse = *streamResp.Message
			}
		case "message_start":
			if streamResp.Message != nil {
				finalResponse.ID = streamResp.Message.ID
				finalResponse.Model = streamResp.Message.Model
				finalResponse.Role = streamResp.Message.Role
			}
		}
	}

	// 构建完整响应
	finalResponse.Content = []struct {
		Type string `json:"type"`
		Text string `json:"text"`
	}{
		{Type: "text", Text: fullText},
	}

	return &finalResponse, nil
}

// setHeaders 设置请求头
func (c *Client) setHeaders(req *http.Request) {
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-api-key", c.apiKey)
	req.Header.Set("anthropic-version", "2023-06-01")
}

// SSEEvent SSE事件
type SSEEvent struct {
	Event string
	Data  string
}

// SSEDecoder SSE解码器
type SSEDecoder struct {
	reader io.Reader
}

// NewSSEDecoder 创建SSE解码器
func NewSSEDecoder(reader io.Reader) *SSEDecoder {
	return &SSEDecoder{reader: reader}
}

// Decode 解码下一个事件
func (d *SSEDecoder) Decode() (*SSEEvent, error) {
	var event SSEEvent
	var data string

	buf := make([]byte, 1)
	for {
		_, err := d.reader.Read(buf)
		if err != nil {
			return nil, err
		}

		if buf[0] == '\n' {
			if data == "" {
				continue
			}
			if len(data) > 6 && data[:6] == "data: " {
				event.Data = data[6:]
				return &event, nil
			}
			data = ""
			continue
		}

		data += string(buf[0])
	}
}
