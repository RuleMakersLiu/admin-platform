package handler

import (
	"net/http"
	"time"

	"admin-ws/internal/client"
	"admin-ws/internal/config"
	"admin-ws/internal/hub"
	"admin-ws/pkg/protocol"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

// WebSocketHandler WebSocket 处理器
type WebSocketHandler struct {
	hub        *hub.Hub
	upgrader   websocket.Upgrader
	config     *config.WebSocketConfig
	logger     *zap.Logger
}

// NewWebSocketHandler 创建 WebSocket 处理器
func NewWebSocketHandler(h *hub.Hub, cfg *config.WebSocketConfig, logger *zap.Logger) *WebSocketHandler {
	return &WebSocketHandler{
		hub:    h,
		config: cfg,
		logger: logger,
		upgrader: websocket.Upgrader{
			ReadBufferSize:  cfg.ReadBufferSize,
			WriteBufferSize: cfg.WriteBufferSize,
			CheckOrigin: func(r *http.Request) bool {
				return true // 生产环境应根据域名限制
			},
		},
	}
}

// HandleWebSocket 处理 WebSocket 连接
func (h *WebSocketHandler) HandleWebSocket(c *gin.Context) {
	// 从上下文获取用户信息（由中间件设置）
	userID, _ := c.Get("userId")
	tenantID, _ := c.Get("tenantId")
	username, _ := c.Get("username")
	roles, _ := c.Get("roles")
	permissions, _ := c.Get("permissions")

	// 升级 HTTP 连接到 WebSocket
	conn, err := h.upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		h.logger.Error("upgrade websocket failed", zap.Error(err))
		return
	}

	// 生成客户端 ID
	clientID := generateClientID(userID.(string), tenantID.(string))

	// 创建客户端
	cli := client.NewClient(clientID, conn, h.hub, h.logger)
	cli.UserID = userID.(string)
	cli.TenantID = tenantID.(string)
	cli.Username = username.(string)
	if r, ok := roles.([]string); ok {
		cli.Roles = r
	}
	if p, ok := permissions.([]string); ok {
		cli.Permissions = p
	}

	// 注册客户端
	h.hub.Register(cli)

	// 启动读写协程
	go cli.WritePump(h.config.PingPeriod, h.config.WriteWait)
	go cli.ReadPump(h.config.MaxMessageSize, h.config.PongWait, h.config.WriteWait, func(msg *protocol.Message) {
		h.handleMessage(cli, msg)
	})
}

// handleMessage 处理客户端消息
func (h *WebSocketHandler) handleMessage(c *client.Client, msg *protocol.Message) {
	h.logger.Debug("received message",
		zap.String("clientId", c.ID),
		zap.String("type", msg.Type),
		zap.String("action", msg.Action))

	switch msg.Action {
	case protocol.ActionSubscribe:
		h.handleSubscribe(c, msg)

	case protocol.ActionUnsubscribe:
		h.handleUnsubscribe(c, msg)

	case protocol.ActionJoin:
		h.handleJoin(c, msg)

	case protocol.ActionLeave:
		h.handleLeave(c, msg)

	case protocol.ActionPublish:
		h.handlePublish(c, msg)

	case protocol.ActionBroadcast:
		h.handleBroadcast(c, msg)

	case protocol.ActionDirect:
		h.handleDirect(c, msg)

	default:
		c.SendError(protocol.CodeBadRequest, "Unknown action", "", msg.RequestID)
	}
}

// handleSubscribe 处理订阅
func (h *WebSocketHandler) handleSubscribe(c *client.Client, msg *protocol.Message) {
	channel := msg.Channel
	if channel == "" {
		c.SendError(protocol.CodeBadRequest, "Channel is required", "", msg.RequestID)
		return
	}

	// 检查权限（可选）
	// if !h.hasPermission(c, channel) {
	// 	c.SendError(protocol.CodeForbidden, "No permission to subscribe", "", msg.RequestID)
	// 	return
	// }

	h.hub.SubscribeChannel(c, channel)

	c.SendMessage(protocol.NewResponse(protocol.CodeSuccess, "Subscribed", map[string]string{
		"channel": channel,
	}, msg.RequestID))

	c.SendEvent(protocol.SysEventSubscribed, map[string]string{
		"channel": channel,
	})
}

// handleUnsubscribe 处理取消订阅
func (h *WebSocketHandler) handleUnsubscribe(c *client.Client, msg *protocol.Message) {
	channel := msg.Channel
	if channel == "" {
		c.SendError(protocol.CodeBadRequest, "Channel is required", "", msg.RequestID)
		return
	}

	h.hub.UnsubscribeChannel(c, channel)

	c.SendMessage(protocol.NewResponse(protocol.CodeSuccess, "Unsubscribed", map[string]string{
		"channel": channel,
	}, msg.RequestID))
}

// handleJoin 处理加入房间
func (h *WebSocketHandler) handleJoin(c *client.Client, msg *protocol.Message) {
	roomID := msg.Room
	if roomID == "" {
		c.SendError(protocol.CodeBadRequest, "Room ID is required", "", msg.RequestID)
		return
	}

	if !h.hub.GetRoomManager().JoinRoom(roomID, c) {
		c.SendError(protocol.CodeInternalError, "Failed to join room", "", msg.RequestID)
		return
	}

	// 通知客户端加入成功
	c.SendMessage(protocol.NewResponse(protocol.CodeSuccess, "Joined room", map[string]string{
		"roomId": roomID,
	}, msg.RequestID))

	// 广播房间加入事件
	h.hub.BroadcastToRoom(roomID, protocol.NewEvent(protocol.EventJoined, map[string]interface{}{
		"roomId":   roomID,
		"clientId": c.ID,
		"username": c.Username,
	}), c.ID)
}

// handleLeave 处理离开房间
func (h *WebSocketHandler) handleLeave(c *client.Client, msg *protocol.Message) {
	roomID := msg.Room
	if roomID == "" {
		c.SendError(protocol.CodeBadRequest, "Room ID is required", "", msg.RequestID)
		return
	}

	h.hub.GetRoomManager().LeaveRoom(roomID, c)

	c.SendMessage(protocol.NewResponse(protocol.CodeSuccess, "Left room", map[string]string{
		"roomId": roomID,
	}, msg.RequestID))

	// 广播房间离开事件
	h.hub.BroadcastToRoom(roomID, protocol.NewEvent(protocol.EventLeft, map[string]interface{}{
		"roomId":   roomID,
		"clientId": c.ID,
		"username": c.Username,
	}))
}

// handlePublish 处理发布消息
func (h *WebSocketHandler) handlePublish(c *client.Client, msg *protocol.Message) {
	channel := msg.Channel
	if channel == "" {
		c.SendError(protocol.CodeBadRequest, "Channel is required", "", msg.RequestID)
		return
	}

	// 检查是否订阅了该频道
	if !c.IsSubscribed(channel) {
		c.SendError(protocol.CodeForbidden, "Not subscribed to channel", "", msg.RequestID)
		return
	}

	// 广播到频道
	h.hub.BroadcastToChannel(channel, msg, c.ID)

	c.SendMessage(protocol.NewResponse(protocol.CodeSuccess, "Message published", nil, msg.RequestID))
}

// handleBroadcast 处理广播消息
func (h *WebSocketHandler) handleBroadcast(c *client.Client, msg *protocol.Message) {
	roomID := msg.Room
	if roomID == "" {
		c.SendError(protocol.CodeBadRequest, "Room ID is required", "", msg.RequestID)
		return
	}

	// 检查是否在房间中
	if !c.IsInRoom(roomID) {
		c.SendError(protocol.CodeForbidden, "Not in room", "", msg.RequestID)
		return
	}

	// 广播到房间
	h.hub.BroadcastToRoom(roomID, msg, c.ID)
}

// handleDirect 处理点对点消息
func (h *WebSocketHandler) handleDirect(c *client.Client, msg *protocol.Message) {
	targetID := msg.Target
	if targetID == "" {
		c.SendError(protocol.CodeBadRequest, "Target client ID is required", "", msg.RequestID)
		return
	}

	// 发送给目标客户端
	if !h.hub.SendToClient(targetID, msg) {
		c.SendError(protocol.CodeNotFound, "Target client not found", "", msg.RequestID)
		return
	}

	c.SendMessage(protocol.NewResponse(protocol.CodeSuccess, "Message sent", nil, msg.RequestID))
}

// generateClientID 生成客户端 ID
func generateClientID(userID, tenantID string) string {
	return tenantID + ":" + userID + ":" + time.Now().Format("20060102150405")
}
