package service

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"admin-ws/internal/config"
	"admin-ws/pkg/protocol"

	"go.uber.org/zap"
)

// AgentService Agent 服务集成
type AgentService struct {
	cfg    *config.AgentConfig
	logger *zap.Logger
	client *http.Client
}

// NewAgentService 创建 Agent 服务
func NewAgentService(cfg *config.AgentConfig, logger *zap.Logger) *AgentService {
	return &AgentService{
		cfg:    cfg,
		logger: logger,
		client: &http.Client{
			Timeout: cfg.Timeout,
		},
	}
}

// AgentRequest Agent 请求
type AgentRequest struct {
	SessionID string                 `json:"sessionId"`
	Message   string                 `json:"message"`
	Context   map[string]interface{} `json:"context,omitempty"`
	Stream    bool                   `json:"stream"`
}

// AgentResponse Agent 响应
type AgentResponse struct {
	SessionID string `json:"sessionId"`
	Message   string `json:"message"`
	Success   bool   `json:"success"`
	Error     string `json:"error,omitempty"`
}

// SendMessage 发送消息到 Agent
func (s *AgentService) SendMessage(ctx context.Context, req *AgentRequest) (*AgentResponse, error) {
	if !s.cfg.Enabled {
		return nil, fmt.Errorf("agent service is disabled")
	}

	url := fmt.Sprintf("http://%s/api/agent/message", s.cfg.Address)

	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := s.client.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("do request: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("agent returned status %d: %s", resp.StatusCode, string(respBody))
	}

	var agentResp AgentResponse
	if err := json.Unmarshal(respBody, &agentResp); err != nil {
		return nil, fmt.Errorf("unmarshal response: %w", err)
	}

	return &agentResp, nil
}

// BroadcastAgentMessage 广播 Agent 消息到 WebSocket
func (s *AgentService) BroadcastAgentMessage(broadcaster func(*protocol.Message), sessionID string, message string) {
	msg := protocol.NewEvent(protocol.EventAgentMessage, map[string]interface{}{
		"sessionId": sessionID,
		"message":   message,
		"timestamp": time.Now().UnixMilli(),
	})
	broadcaster(msg)
}

// NotifyAgentStatus 通知 Agent 状态变化
func (s *AgentService) NotifyAgentStatus(broadcaster func(*protocol.Message), status string) {
	msg := protocol.NewEvent(protocol.EventAgentStatus, map[string]interface{}{
		"status":    status,
		"timestamp": time.Now().UnixMilli(),
	})
	broadcaster(msg)
}
