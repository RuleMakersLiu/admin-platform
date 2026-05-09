package service

import (
	"context"
	"encoding/json"
	"fmt"

	"admin-agent/internal/model"
	"admin-agent/pkg/claude"
	"admin-agent/pkg/prompt"
	"admin-agent/pkg/protocol"
)

// BaseAgent 基础分身实现
type BaseAgent struct {
	agentType     model.AgentType
	claudeClient  *claude.Client
	promptManager *prompt.Manager
}

// NewBaseAgent 创建基础分身
func NewBaseAgent(agentType model.AgentType, client *claude.Client, pm *prompt.Manager) *BaseAgent {
	return &BaseAgent{
		agentType:     agentType,
		claudeClient:  client,
		promptManager: pm,
	}
}

// GetType 获取分身类型
func (a *BaseAgent) GetType() model.AgentType {
	return a.agentType
}

// GetSystemPrompt 获取系统提示词
func (a *BaseAgent) GetSystemPrompt() string {
	cfg, err := a.promptManager.GetPrompt(prompt.AgentType(a.agentType))
	if err != nil {
		return ""
	}
	return cfg.SystemPrompt
}

// Process 处理消息
func (a *BaseAgent) Process(ctx context.Context, msg *protocol.Message) (*protocol.Message, error) {
	// 解析消息内容
	var content string
	switch msg.Type {
	case model.MsgTypeChat:
		var payload protocol.ChatPayload
		if err := json.Unmarshal(msg.Payload, &payload); err != nil {
			return nil, fmt.Errorf("解析消息失败: %w", err)
		}
		content = payload.Content

	case model.MsgTypeRequirementDoc:
		var payload protocol.RequirementDocPayload
		if err := json.Unmarshal(msg.Payload, &payload); err != nil {
			return nil, fmt.Errorf("解析需求文档失败: %w", err)
		}
		content = fmt.Sprintf("请分析以下需求文档:\n\n# %s\n\n%s", payload.DocTitle, payload.DocContent)

	case model.MsgTypeTaskList:
		var payload protocol.TaskListPayload
		if err := json.Unmarshal(msg.Payload, &payload); err != nil {
			return nil, fmt.Errorf("解析任务列表失败: %w", err)
		}
		content = a.formatTaskListForAgent(payload.Tasks)

	case model.MsgTypeAPIContract:
		var payload protocol.APIContractPayload
		if err := json.Unmarshal(msg.Payload, &payload); err != nil {
			return nil, fmt.Errorf("解析API契约失败: %w", err)
		}
		content = a.formatAPIContractForAgent(payload)

	default:
		content = string(msg.Payload)
	}

	// 调用Claude API
	response, err := a.callClaude(ctx, content)
	if err != nil {
		return nil, fmt.Errorf("调用Claude失败: %w", err)
	}

	// 创建响应消息
	responseMsg, err := protocol.NewMessage(
		a.agentType,
		msg.From,
		msg.Type,
		map[string]interface{}{
			"content": response,
		},
	)
	if err != nil {
		return nil, err
	}

	responseMsg.SessionID = msg.SessionID
	responseMsg.ProjectID = msg.ProjectID

	return responseMsg, nil
}

// callClaude 调用Claude API
func (a *BaseAgent) callClaude(ctx context.Context, content string) (string, error) {
	req := &claude.Request{
		Model:     "claude-sonnet-4-20250514",
		MaxTokens: 4096,
		Messages: []claude.Message{
			{
				Role:    "user",
				Content: content,
			},
		},
		System: a.GetSystemPrompt(),
		Stream: false,
	}

	resp, err := a.claudeClient.Chat(req)
	if err != nil {
		return "", err
	}

	if len(resp.Content) > 0 {
		return resp.Content[0].Text, nil
	}

	return "", nil
}

// formatTaskListForAgent 格式化任务列表给分身
func (a *BaseAgent) formatTaskListForAgent(tasks []protocol.TaskItem) string {
	var result string
	result = "以下是待处理的任务列表:\n\n"
	for i, task := range tasks {
		result += fmt.Sprintf("%d. **%s** (ID: %s)\n", i+1, task.TaskName, task.TaskID)
		result += fmt.Sprintf("   - 类型: %s\n", task.TaskType)
		result += fmt.Sprintf("   - 优先级: %s\n", task.Priority)
		if task.Assignee != "" {
			result += fmt.Sprintf("   - 指派: %s\n", task.Assignee)
		}
		if task.Description != "" {
			result += fmt.Sprintf("   - 描述: %s\n", task.Description)
		}
		result += "\n"
	}
	return result
}

// formatAPIContractForAgent 格式化API契约给分身
func (a *BaseAgent) formatAPIContractForAgent(contract protocol.APIContractPayload) string {
	var result string
	result = fmt.Sprintf("# API契约: %s (v%s)\n\n", contract.ContractName, contract.Version)

	for _, ep := range contract.Endpoints {
		result += fmt.Sprintf("## %s %s\n", ep.Method, ep.Path)
		result += fmt.Sprintf("描述: %s\n\n", ep.Description)

		if ep.Request != nil {
			result += "### 请求体\n```json\n"
			reqJSON, _ := json.MarshalIndent(ep.Request, "", "  ")
			result += string(reqJSON) + "\n```\n\n"
		}

		if ep.Response != nil {
			result += "### 响应体\n```json\n"
			respJSON, _ := json.MarshalIndent(ep.Response, "", "  ")
			result += string(respJSON) + "\n```\n\n"
		}
	}

	return result
}

// ========== 专用分身实现 ==========

// PMAgent 产品经理分身
type PMAgent struct {
	*BaseAgent
}

// NewPMAgent 创建PM分身
func NewPMAgent(client *claude.Client, pm *prompt.Manager) *PMAgent {
	return &PMAgent{
		BaseAgent: NewBaseAgent(model.AgentPM, client, pm),
	}
}

// Process 处理消息 (PM特化逻辑)
func (a *PMAgent) Process(ctx context.Context, msg *protocol.Message) (*protocol.Message, error) {
	// PM分身特化: 自动识别是否需要输出PRD
	response, err := a.BaseAgent.Process(ctx, msg)
	if err != nil {
		return nil, err
	}

	// 检查是否包含需求文档标记
	// 如果需要，可以在这里添加PRD格式化逻辑

	return response, nil
}

// PJMAgent 项目经理分身
type PJMAgent struct {
	*BaseAgent
}

// NewPJMAgent 创建PJM分身
func NewPJMAgent(client *claude.Client, pm *prompt.Manager) *PJMAgent {
	return &PJMAgent{
		BaseAgent: NewBaseAgent(model.AgentPJM, client, pm),
	}
}

// BEAgent 后端开发分身
type BEAgent struct {
	*BaseAgent
}

// NewBEAgent 创建BE分身
func NewBEAgent(client *claude.Client, pm *prompt.Manager) *BEAgent {
	return &BEAgent{
		BaseAgent: NewBaseAgent(model.AgentBE, client, pm),
	}
}

// FEAgent 前端开发分身
type FEAgent struct {
	*BaseAgent
}

// NewFEAgent 创建FE分身
func NewFEAgent(client *claude.Client, pm *prompt.Manager) *FEAgent {
	return &FEAgent{
		BaseAgent: NewBaseAgent(model.AgentFE, client, pm),
	}
}

// QAAgent 测试分身
type QAAgent struct {
	*BaseAgent
}

// NewQAAgent 创建QA分身
func NewQAAgent(client *claude.Client, pm *prompt.Manager) *QAAgent {
	return &QAAgent{
		BaseAgent: NewBaseAgent(model.AgentQA, client, pm),
	}
}

// RPTAgent 汇报分身
type RPTAgent struct {
	*BaseAgent
}

// NewRPTAgent 创建RPT分身
func NewRPTAgent(client *claude.Client, pm *prompt.Manager) *RPTAgent {
	return &RPTAgent{
		BaseAgent: NewBaseAgent(model.AgentRPT, client, pm),
	}
}
