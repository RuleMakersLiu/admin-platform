package service

import (
	"context"
	"fmt"
	"sync"
	"time"

	"admin-agent/internal/config"
	"admin-agent/internal/model"
	"admin-agent/pkg/claude"
	"admin-agent/pkg/prompt"

	"gorm.io/gorm"
)

// AgentService 分身服务 - 统一服务层
type AgentService struct {
	cfg           *config.Config
	db            *gorm.DB
	claudeClient  *claude.Client
	promptManager *prompt.Manager
	memoryService *MemoryService
	mu            sync.RWMutex
}

// NewAgentService 创建分身服务（无数据库版本，用于向后兼容）
// 注意：此版本使用 nil 数据库，记忆功能将无法正常工作
// 建议使用 NewAgentServiceWithDB 替代
func NewAgentService() *AgentService {
	return NewAgentServiceWithDB(nil)
}

// NewAgentServiceWithDB 创建分身服务（带数据库连接）
// 推荐使用此构造函数，支持记忆持久化
func NewAgentServiceWithDB(db *gorm.DB) *AgentService {
	// 如果配置未加载，使用默认配置
	cfg := config.GlobalConfig
	if cfg == nil {
		cfg = &config.Config{
			Claude: config.ClaudeConfig{
				APIKey:       "",
				BaseURL:      "https://api.anthropic.com",
				DefaultModel: "claude-sonnet-4-20250514",
				MaxTokens:    4096,
				Timeout:      120,
			},
		}
	}

	s := &AgentService{
		cfg:           cfg,
		db:            db,
		promptManager: prompt.NewManager(),
		memoryService: NewMemoryService(db),
	}

	if cfg.Claude.APIKey != "" {
		s.claudeClient = claude.NewClient(&cfg.Claude)
	}

	return s
}

// ProcessMessage 处理消息 (handler调用的主要接口)
func (s *AgentService) ProcessMessage(
	sessionID, projectID, message, agentType string,
	userID, tenantID uint64,
) (reply, msgID, agent string, err error) {
	// 确定目标分身
	targetAgent := model.AgentType(agentType)
	if targetAgent == "" {
		targetAgent = model.AgentPM // 默认PM
	}

	// 添加到记忆
	s.memoryService.AddMessage(sessionID, message)

	// 获取上下文
	context := s.buildContextForAgent(sessionID, targetAgent)

	// 调用Claude
	reply, err = s.callClaudeWithAgent(targetAgent, message, context)
	if err != nil {
		return "", "", "", err
	}

	// 保存回复到记忆
	s.memoryService.AddMessage(sessionID, reply)

	// 生成消息ID
	msgID = fmt.Sprintf("msg_%d", time.Now().UnixMilli())

	return reply, msgID, string(targetAgent), nil
}

// buildContextForAgent 为分身构建上下文
func (s *AgentService) buildContextForAgent(sessionID string, agentType model.AgentType) string {
	history := s.memoryService.GetRecentMessages(sessionID, 5)
	if len(history) == 0 {
		return ""
	}

	var ctx string
	ctx = "### 历史对话:\n"
	for i, h := range history {
		ctx += fmt.Sprintf("%d. %s\n", i+1, h)
	}
	return ctx
}

// callClaudeWithAgent 使用指定分身调用Claude
func (s *AgentService) callClaudeWithAgent(agentType model.AgentType, message, context string) (string, error) {
	if s.claudeClient == nil {
		return "Claude客户端未配置，请设置API Key", nil
	}

	// 获取分身Prompt
	promptCfg, err := s.promptManager.GetPrompt(prompt.AgentType(agentType))
	if err != nil {
		promptCfg = &prompt.PromptConfig{SystemPrompt: ""}
	}

	// 构建消息
	var messages []claude.Message
	if context != "" {
		messages = append(messages, claude.Message{
			Role:    "user",
			Content: context,
		})
		messages = append(messages, claude.Message{
			Role:    "assistant",
			Content: "好的，我已经了解了之前的对话内容。",
		})
	}
	messages = append(messages, claude.Message{
		Role:    "user",
		Content: message,
	})

	// 构建请求
	req := &claude.Request{
		Model:     "claude-sonnet-4-20250514",
		MaxTokens: 4096,
		Messages:  messages,
		System:    promptCfg.SystemPrompt,
		Stream:    false,
	}

	resp, err := s.claudeClient.Chat(req)
	if err != nil {
		return "", fmt.Errorf("调用Claude失败: %w", err)
	}

	if len(resp.Content) > 0 {
		return resp.Content[0].Text, nil
	}

	return "", nil
}

// ========== 会话管理 ==========

// SessionItem 会话列表项
type SessionItem struct {
	SessionID       string `json:"session_id"`
	Title           string `json:"title"`
	CurrentAgent    string `json:"current_agent"`
	WorkflowStage   string `json:"workflow_stage"`
	Status          string `json:"status"`
	MessageCount    int    `json:"message_count"`
	LastMessageTime int64  `json:"last_message_time"`
	CreateTime      int64  `json:"create_time"`
}

// ListSessions 获取会话列表
func (s *AgentService) ListSessions(userID, tenantID uint64) ([]SessionItem, error) {
	// 简化实现：返回空列表
	// 实际应从数据库获取
	return []SessionItem{}, nil
}

// GetSessionMessages 获取会话消息
func (s *AgentService) GetSessionMessages(sessionID string) ([]map[string]interface{}, error) {
	messages := s.memoryService.GetRecentMessages(sessionID, 50)
	var result []map[string]interface{}
	for i, msg := range messages {
		role := "user"
		if i%2 == 1 {
			role = "assistant"
		}
		result = append(result, map[string]interface{}{
			"role":    role,
			"content": msg,
		})
	}
	return result, nil
}

// CreateSession 创建会话
func (s *AgentService) CreateSession(userID, tenantID uint64, projectID, title string) (*SessionItem, error) {
	sessionID := fmt.Sprintf("sess_%d", time.Now().UnixMilli())
	return &SessionItem{
		SessionID:     sessionID,
		Title:         title,
		CurrentAgent:  "PM",
		WorkflowStage: "requirement",
		Status:        "active",
		CreateTime:    time.Now().UnixMilli(),
	}, nil
}

// DeleteSession 删除会话
func (s *AgentService) DeleteSession(sessionID string) error {
	s.memoryService.ClearSession(sessionID)
	return nil
}

// ========== 项目管理 ==========

// ProjectItem 项目项
type ProjectItem struct {
	ID          int64  `json:"id"`
	ProjectCode string `json:"project_code"`
	ProjectName string `json:"project_name"`
	Description string `json:"description"`
	Status      string `json:"status"`
	Priority    string `json:"priority"`
	CreateTime  int64  `json:"create_time"`
}

// CreateProject 创建项目
func (s *AgentService) CreateProject(userID, tenantID uint64, name, description, priority string) (*ProjectItem, error) {
	now := time.Now().UnixMilli()
	projectCode := fmt.Sprintf("PRJ-%s-%03d", time.Now().Format("20060102"), 1)
	return &ProjectItem{
		ProjectCode: projectCode,
		ProjectName: name,
		Description: description,
		Status:      "pending",
		Priority:    priority,
		CreateTime:  now,
	}, nil
}

// GetProject 获取项目
func (s *AgentService) GetProject(projectID string) (*ProjectItem, error) {
	return &ProjectItem{
		ProjectCode: projectID,
		ProjectName: "示例项目",
		Status:      "active",
	}, nil
}

// ListProjects 获取项目列表
func (s *AgentService) ListProjects(tenantID uint64, status string) ([]ProjectItem, error) {
	return []ProjectItem{}, nil
}

// ========== 任务管理 ==========

// TaskItem 任务项
type TaskItem struct {
	TaskID      string `json:"task_id"`
	TaskName    string `json:"task_name"`
	TaskType    string `json:"task_type"`
	Assignee    string `json:"assignee"`
	Status      string `json:"status"`
	Priority    string `json:"priority"`
	Progress    int    `json:"progress"`
	Description string `json:"description"`
}

// ListTasks 获取任务列表
func (s *AgentService) ListTasks(projectID, status, assignee string) ([]TaskItem, error) {
	return []TaskItem{}, nil
}

// UpdateTaskStatus 更新任务状态
func (s *AgentService) UpdateTaskStatus(taskID, status string, progress int) error {
	return nil
}

// ========== BUG管理 ==========

// BugItem BUG项
type BugItem struct {
	BugID      string `json:"bug_id"`
	BugTitle   string `json:"bug_title"`
	Severity   string `json:"severity"`
	Status     string `json:"status"`
	Assignee   string `json:"assignee"`
	CreateTime int64  `json:"create_time"`
}

// ListBugs 获取BUG列表
func (s *AgentService) ListBugs(projectID, status, severity string) ([]BugItem, error) {
	return []BugItem{}, nil
}

// UpdateBugStatus 更新BUG状态
func (s *AgentService) UpdateBugStatus(bugID, status, fixNote string) error {
	return nil
}

// ========== 流式对话 ==========

// StreamChat 流式对话
// 返回一个channel，通过channel持续推送AI生成的内容
// 支持客户端实时接收响应，提升用户体验
func (s *AgentService) StreamChat(
	ctx context.Context,
	sessionID, projectID, message, agentType string,
	userID, tenantID uint64,
) (<-chan map[string]interface{}, error) {
	streamChan := make(chan map[string]interface{}, 100)

	// 确定目标分身类型
	targetAgent := model.AgentType(agentType)
	if targetAgent == "" {
		targetAgent = model.AgentPM // 默认使用PM分身
	}

	// 启动goroutine处理流式响应
	go func() {
		defer close(streamChan)

		// 检查Claude客户端是否配置
		if s.claudeClient == nil {
			streamChan <- map[string]interface{}{
				"type":    "error",
				"message": "Claude客户端未配置，请设置API Key",
			}
			return
		}

		// 添加用户消息到记忆
		s.memoryService.AddMessage(sessionID, message)

		// 获取对话上下文
		context := s.buildContextForAgent(sessionID, targetAgent)

		// 获取分身Prompt配置
		promptCfg, err := s.promptManager.GetPrompt(prompt.AgentType(targetAgent))
		if err != nil {
			promptCfg = &prompt.PromptConfig{SystemPrompt: ""}
		}

		// 构建消息列表
		var messages []claude.Message
		if context != "" {
			messages = append(messages, claude.Message{
				Role:    "user",
				Content: context,
			})
			messages = append(messages, claude.Message{
				Role:    "assistant",
				Content: "好的，我已经了解了之前的对话内容。",
			})
		}
		messages = append(messages, claude.Message{
			Role:    "user",
			Content: message,
		})

		// 构建Claude请求
		req := &claude.Request{
			Model:     "claude-sonnet-4-20250514",
			MaxTokens: 4096,
			Messages:  messages,
			System:    promptCfg.SystemPrompt,
			Stream:    true,
		}

		// 发送开始事件
		streamChan <- map[string]interface{}{
			"type":       "start",
			"session_id": sessionID,
			"agent_type": string(targetAgent),
		}

		// 调用Claude流式API
		var fullReply string
		_, err = s.claudeClient.ChatStream(req, func(text string) error {
			// 检查上下文是否已取消
			select {
			case <-ctx.Done():
				return ctx.Err()
			default:
			}

			// 累积完整回复
			fullReply += text

			// 发送内容块到channel
			streamChan <- map[string]interface{}{
				"type":    "content",
				"content": text,
			}
			return nil
		})

		if err != nil {
			streamChan <- map[string]interface{}{
				"type":    "error",
				"message": fmt.Sprintf("调用Claude失败: %v", err),
			}
			return
		}

		// 保存完整回复到记忆
		s.memoryService.AddMessage(sessionID, fullReply)

		// 发送完成事件
		msgID := fmt.Sprintf("msg_%d", time.Now().UnixMilli())
		streamChan <- map[string]interface{}{
			"type":       "complete",
			"msg_id":     msgID,
			"session_id": sessionID,
			"agent_type": string(targetAgent),
		}
	}()

	return streamChan, nil
}
