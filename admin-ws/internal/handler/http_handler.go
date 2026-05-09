package handler

import (
	"net/http"

	"admin-ws/internal/hub"
	"admin-ws/pkg/protocol"

	"github.com/gin-gonic/gin"
)

// HTTPHandler HTTP 处理器（用于管理接口）
type HTTPHandler struct {
	hub *hub.Hub
}

// NewHTTPHandler 创建 HTTP 处理器
func NewHTTPHandler(h *hub.Hub) *HTTPHandler {
	return &HTTPHandler{hub: h}
}

// GetStats 获取统计信息
func (h *HTTPHandler) GetStats(c *gin.Context) {
	stats := h.hub.GetStats()
	c.JSON(http.StatusOK, gin.H{
		"code":    0,
		"message": "success",
		"data":    stats,
	})
}

// GetClients 获取客户端列表
func (h *HTTPHandler) GetClients(c *gin.Context) {
	clients := h.hub.GetClientInfos()
	c.JSON(http.StatusOK, gin.H{
		"code":    0,
		"message": "success",
		"data": gin.H{
			"clients": clients,
			"total":   len(clients),
		},
	})
}

// GetRooms 获取房间列表
func (h *HTTPHandler) GetRooms(c *gin.Context) {
	rooms := h.hub.GetRoomManager().GetAllRooms()
	c.JSON(http.StatusOK, gin.H{
		"code":    0,
		"message": "success",
		"data": gin.H{
			"rooms": rooms,
		},
	})
}

// GetRoomInfo 获取房间信息
func (h *HTTPHandler) GetRoomInfo(c *gin.Context) {
	roomID := c.Param("id")
	info, ok := h.hub.GetRoomManager().GetRoomInfo(roomID, true)
	if !ok {
		c.JSON(http.StatusNotFound, gin.H{
			"code":    40400,
			"message": "Room not found",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    0,
		"message": "success",
		"data":    info,
	})
}

// BroadcastRequest 广播请求
type BroadcastRequest struct {
	Channel string                 `json:"channel"`
	Room    string                 `json:"room"`
	Event   string                 `json:"event"`
	Data    map[string]interface{} `json:"data"`
}

// Broadcast 广播消息
func (h *HTTPHandler) Broadcast(c *gin.Context) {
	var req BroadcastRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    40000,
			"message": "Invalid request",
		})
		return
	}

	msg := protocol.NewEvent(req.Event, req.Data)

	switch {
	case req.Room != "":
		h.hub.BroadcastToRoom(req.Room, msg)
	case req.Channel != "":
		h.hub.BroadcastToChannel(req.Channel, msg)
	default:
		h.hub.Broadcast(msg)
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    0,
		"message": "success",
	})
}

// AgentCallbackRequest Agent回调请求
type AgentCallbackRequest struct {
	SessionID string                 `json:"session_id"`
	UserID    string                 `json:"user_id"`
	Event     string                 `json:"event"`
	Data      map[string]interface{} `json:"data"`
}

// HandleAgentCallback 处理Agent回调
func (h *HTTPHandler) HandleAgentCallback(c *gin.Context) {
	var req AgentCallbackRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    40000,
			"message": "Invalid request",
		})
		return
	}

	msg := protocol.NewEvent(req.Event, req.Data)

	if req.UserID != "" {
		h.hub.BroadcastToChannel("user:"+req.UserID, msg)
	}
	if req.SessionID != "" {
		h.hub.BroadcastToChannel("session:"+req.SessionID, msg)
	}

	h.hub.BroadcastToChannel("agent", msg)

	c.JSON(http.StatusOK, gin.H{
		"code":    0,
		"message": "success",
	})
}
