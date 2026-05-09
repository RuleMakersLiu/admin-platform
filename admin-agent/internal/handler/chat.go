package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"admin-agent/internal/service"
)

// ChatHandler 对话处理器
type ChatHandler struct {
	orchestrator *service.Orchestrator
	agentService *service.AgentService
}

// NewChatHandler 创建对话处理器
func NewChatHandler(orchestrator *service.Orchestrator, agentService *service.AgentService) *ChatHandler {
	return &ChatHandler{
		orchestrator: orchestrator,
		agentService: agentService,
	}
}

// ChatRequest 对话请求
type ChatRequest struct {
	SessionID string `json:"session_id" binding:"required"`
	ProjectID string `json:"project_id"`
	Message   string `json:"message" binding:"required"`
	AgentType string `json:"agent_type"` // 指定分身类型，不指定则自动路由
}

// ChatResponse 对话响应
type ChatResponse struct {
	SessionID string `json:"session_id"`
	MsgID     string `json:"msg_id"`
	AgentType string `json:"agent_type"`
	Reply     string `json:"reply"`
	MsgType   string `json:"msg_type"`
}

// Chat 处理对话请求
func (h *ChatHandler) Chat(c *gin.Context) {
	var req ChatRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// 获取用户信息
	userID := c.GetUint64("user_id")
	tenantID := c.GetUint64("tenant_id")

	// 处理对话
	reply, msgID, agentType, err := h.agentService.ProcessMessage(
		req.SessionID,
		req.ProjectID,
		req.Message,
		req.AgentType,
		userID,
		tenantID,
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, ChatResponse{
		SessionID: req.SessionID,
		MsgID:     msgID,
		AgentType: agentType,
		Reply:     reply,
		MsgType:   "chat",
	})
}

// SessionListResponse 会话列表响应
type SessionListResponse struct {
	Total int                    `json:"total"`
	List  []service.SessionItem `json:"list"`
}

// ListSessions 获取会话列表
func (h *ChatHandler) ListSessions(c *gin.Context) {
	userID := c.GetUint64("user_id")
	tenantID := c.GetUint64("tenant_id")

	sessions, err := h.agentService.ListSessions(userID, tenantID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, SessionListResponse{
		Total: len(sessions),
		List:  sessions,
	})
}

// GetSessionHistory 获取会话历史
func (h *ChatHandler) GetSessionHistory(c *gin.Context) {
	sessionID := c.Param("session_id")

	messages, err := h.agentService.GetSessionMessages(sessionID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"session_id": sessionID,
		"messages":   messages,
	})
}

// CreateSessionRequest 创建会话请求
type CreateSessionRequest struct {
	ProjectID string `json:"project_id"`
	Title     string `json:"title"`
}

// CreateSession 创建新会话
func (h *ChatHandler) CreateSession(c *gin.Context) {
	var req CreateSessionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	userID := c.GetUint64("user_id")
	tenantID := c.GetUint64("tenant_id")

	session, err := h.agentService.CreateSession(userID, tenantID, req.ProjectID, req.Title)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, session)
}

// DeleteSession 删除会话
func (h *ChatHandler) DeleteSession(c *gin.Context) {
	sessionID := c.Param("session_id")

	if err := h.agentService.DeleteSession(sessionID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "删除成功"})
}

// StreamChatRequest 流式对话请求
type StreamChatRequest struct {
	SessionID string `json:"session_id" binding:"required"`
	ProjectID string `json:"project_id"`
	Message   string `json:"message" binding:"required"`
	AgentType string `json:"agent_type"` // 指定分身类型，不指定则自动路由
}

// StreamChat HTTP流式对话
// 支持Server-Sent Events (SSE)协议，实现实时流式输出
func (h *ChatHandler) StreamChat(c *gin.Context) {
	// 设置SSE响应头，保持长连接
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("Connection", "keep-alive")
	c.Header("Access-Control-Allow-Origin", "*")

	var req StreamChatRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.SSEvent("error", gin.H{"message": "参数错误: " + err.Error()})
		c.Writer.Flush()
		return
	}

	// 获取用户信息（从中间件注入）
	userID := c.GetUint64("user_id")
	tenantID := c.GetUint64("tenant_id")

	// 调用流式对话服务
	streamChan, err := h.agentService.StreamChat(
		c.Request.Context(),
		req.SessionID,
		req.ProjectID,
		req.Message,
		req.AgentType,
		userID,
		tenantID,
	)
	if err != nil {
		c.SSEvent("error", gin.H{"message": err.Error()})
		c.Writer.Flush()
		return
	}

	// 持续读取流式数据并发送给客户端
	for {
		select {
		case chunk, ok := <-streamChan:
			if !ok {
				// channel已关闭，发送完成事件
				c.SSEvent("done", gin.H{})
				c.Writer.Flush()
				return
			}
			// 发送消息事件
			c.SSEvent("message", chunk)
			c.Writer.Flush()
		case <-c.Request.Context().Done():
			// 客户端断开连接
			return
		}
	}
}
