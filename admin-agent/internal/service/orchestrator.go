package service

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"

	"admin-agent/internal/model"
	"admin-agent/pkg/claude"
	"admin-agent/pkg/prompt"
	"admin-agent/pkg/protocol"
	"gorm.io/gorm"
)

// Orchestrator 分身编排器
type Orchestrator struct {
	db            *gorm.DB
	claudeClient  *claude.Client
	promptManager *prompt.Manager
	workflow      *WorkflowService
	memoryService *MemoryService
	agents        map[model.AgentType]Agent
	mu            sync.RWMutex
}

// Agent 分身接口
type Agent interface {
	// Process 处理消息
	Process(ctx context.Context, msg *protocol.Message) (*protocol.Message, error)
	// GetType 获取分身类型
	GetType() model.AgentType
	// GetSystemPrompt 获取系统提示词
	GetSystemPrompt() string
}

// NewOrchestrator 创建编排器
func NewOrchestrator(agentService *AgentService) *Orchestrator {
	o := &Orchestrator{
		db:            agentService.db,
		claudeClient:  agentService.claudeClient,
		promptManager: agentService.promptManager,
		agents:        make(map[model.AgentType]Agent),
	}

	// 初始化工作流服务
	o.workflow = NewWorkflowService(o)

	// 初始化记忆服务
	o.memoryService = NewMemoryService(o.db)

	// 注册所有分身
	o.registerAgents()

	return o
}

// registerAgents 注册所有分身
func (o *Orchestrator) registerAgents() {
	// 注册PM分身
	o.agents[model.AgentPM] = NewBaseAgent(model.AgentPM, o.claudeClient, o.promptManager)

	// 注册PJM分身
	o.agents[model.AgentPJM] = NewBaseAgent(model.AgentPJM, o.claudeClient, o.promptManager)

	// 注册BE分身
	o.agents[model.AgentBE] = NewBaseAgent(model.AgentBE, o.claudeClient, o.promptManager)

	// 注册FE分身
	o.agents[model.AgentFE] = NewBaseAgent(model.AgentFE, o.claudeClient, o.promptManager)

	// 注册QA分身
	o.agents[model.AgentQA] = NewBaseAgent(model.AgentQA, o.claudeClient, o.promptManager)

	// 注册RPT分身
	o.agents[model.AgentRPT] = NewBaseAgent(model.AgentRPT, o.claudeClient, o.promptManager)
}

// RouteMessage 路由消息到对应分身
func (o *Orchestrator) RouteMessage(ctx context.Context, msg *protocol.Message) (*protocol.Message, error) {
	o.mu.RLock()
	agent, ok := o.agents[msg.To]
	o.mu.RUnlock()

	if !ok {
		return nil, fmt.Errorf("未找到目标分身: %s", msg.To)
	}

	// 处理消息
	response, err := agent.Process(ctx, msg)
	if err != nil {
		return nil, fmt.Errorf("分身处理失败: %w", err)
	}

	// 检查是否需要流转
	if nextAgent := o.workflow.GetNextAgent(msg, response); nextAgent != "" {
		// 创建转发消息
		forwardMsg, err := protocol.NewMessage(
			response.From,
			nextAgent,
			o.workflow.GetMessageType(nextAgent),
			map[string]interface{}{
				"forwarded_from": response.From,
				"original_msg":   response,
			},
		)
		if err != nil {
			return nil, err
		}
		forwardMsg.SessionID = msg.SessionID
		forwardMsg.ProjectID = msg.ProjectID

		// 异步转发
		go func() {
			_, _ = o.RouteMessage(context.Background(), forwardMsg)
		}()
	}

	return response, nil
}

// Chat 对话接口
func (o *Orchestrator) Chat(ctx context.Context, req *ChatRequest) (*ChatResponse, error) {
	// 确定目标分身
	targetAgent := req.AgentType
	if targetAgent == "" {
		targetAgent = model.AgentPM // 默认使用PM分身
	}

	// 创建消息
	msg, err := protocol.NewMessage(
		model.AgentUSER,
		targetAgent,
		model.MsgTypeChat,
		&protocol.ChatPayload{
			Content:   req.Content,
			UserInput: req.Content,
		},
	)
	if err != nil {
		return nil, fmt.Errorf("创建消息失败: %w", err)
	}

	msg.SessionID = req.SessionID
	msg.ProjectID = req.ProjectID

	// 获取分身
	o.mu.RLock()
	agent, ok := o.agents[targetAgent]
	o.mu.RUnlock()

	if !ok {
		return nil, fmt.Errorf("未找到分身: %s", targetAgent)
	}

	// 构建上下文
	contextMsgs, err := o.buildContext(ctx, req.SessionID, agent)
	if err != nil {
		return nil, fmt.Errorf("构建上下文失败: %w", err)
	}

	// 调用Claude API
	response, err := o.callClaude(ctx, agent, contextMsgs, req.Content, req.Stream)
	if err != nil {
		return nil, fmt.Errorf("调用Claude失败: %w", err)
	}

	// 更新工作流状态
	if req.ProjectID != "" {
		o.workflow.UpdateStage(req.ProjectID, targetAgent)
	}

	return &ChatResponse{
		MsgID:     msg.MsgID,
		AgentType: targetAgent,
		Content:   response,
		SessionID: req.SessionID,
	}, nil
}

// ChatRequest 对话请求
type ChatRequest struct {
	SessionID string          `json:"session_id"`
	ProjectID string          `json:"project_id"`
	AgentType model.AgentType `json:"agent_type"`
	Content   string          `json:"content"`
	Stream    bool            `json:"stream"`
}

// ChatResponse 对话响应
type ChatResponse struct {
	MsgID     string          `json:"msg_id"`
	AgentType model.AgentType `json:"agent_type"`
	Content   string          `json:"content"`
	SessionID string          `json:"session_id"`
}

// buildContext 构建上下文
func (o *Orchestrator) buildContext(ctx context.Context, sessionID string, agent Agent) ([]claude.Message, error) {
	var messages []claude.Message

	// 获取历史消息
	if o.memoryService != nil {
		history := o.memoryService.GetRecentMessages(sessionID, 10)
		for _, h := range history {
			messages = append(messages, claude.Message{
				Role:    "user",
				Content: h,
			})
		}
	}

	return messages, nil
}

// callClaude 调用Claude API
func (o *Orchestrator) callClaude(ctx context.Context, agent Agent, history []claude.Message, content string, stream bool) (string, error) {
	// 构建消息
	messages := append(history, claude.Message{
		Role:    "user",
		Content: content,
	})

	// 构建请求
	req := &claude.Request{
		Model:     "claude-sonnet-4-20250514",
		MaxTokens: 4096,
		Messages:  messages,
		System:    agent.GetSystemPrompt(),
		Stream:    stream,
	}

	if stream {
		var result strings.Builder
		_, err := o.claudeClient.ChatStream(req, func(text string) error {
			result.WriteString(text)
			return nil
		})
		if err != nil {
			return "", err
		}
		return result.String(), nil
	}

	resp, err := o.claudeClient.Chat(req)
	if err != nil {
		return "", err
	}

	if len(resp.Content) > 0 {
		return resp.Content[0].Text, nil
	}

	return "", nil
}

// GetAgent 获取指定分身
func (o *Orchestrator) GetAgent(agentType model.AgentType) (Agent, bool) {
	o.mu.RLock()
	defer o.mu.RUnlock()
	agent, ok := o.agents[agentType]
	return agent, ok
}

// GetWorkflow 获取工作流服务
func (o *Orchestrator) GetWorkflow() *WorkflowService {
	return o.workflow
}

// ParseMessagePayload 解析消息载荷
func ParseMessagePayload(payload json.RawMessage, target interface{}) error {
	return json.Unmarshal(payload, target)
}
