package hub

import (
	"context"
	"sync"
	"sync/atomic"
	"time"

	"admin-ws/internal/client"
	"admin-ws/internal/config"
	"admin-ws/internal/room"
	"admin-ws/pkg/protocol"

	"github.com/redis/go-redis/v9"
	"go.uber.org/zap"
)

// Hub WebSocket 连接中心
type Hub struct {
	clients       map[string]*client.Client    // 所有客户端
	channels      map[string]map[string]bool   // 频道订阅: channel -> clientIDs
	mu            sync.RWMutex
	roomManager   *room.Manager
	redis         *redis.Client
	logger        *zap.Logger
	config        *config.WebSocketConfig

	// 统计
	totalConnections atomic.Int64
	currentConnections atomic.Int64
	totalMessages    atomic.Int64

	// 消息通道
	broadcastChan   chan *broadcastMessage
	registerChan    chan *client.Client
	unregisterChan  chan *client.Client

	// 上下文
	ctx    context.Context
	cancel context.CancelFunc
}

type broadcastMessage struct {
	message  *protocol.Message
	exclude  []string
	channel  string
	room     string
	target   string
}

// NewHub 创建 Hub
func NewHub(cfg *config.WebSocketConfig, redisClient *redis.Client, logger *zap.Logger) *Hub {
	ctx, cancel := context.WithCancel(context.Background())

	return &Hub{
		clients:      make(map[string]*client.Client),
		channels:     make(map[string]map[string]bool),
		roomManager:  room.NewManager(logger),
		redis:        redisClient,
		logger:       logger,
		config:       cfg,
		broadcastChan: make(chan *broadcastMessage, 1000),
		registerChan:  make(chan *client.Client, 100),
		unregisterChan: make(chan *client.Client, 100),
		ctx:          ctx,
		cancel:       cancel,
	}
}

// Run 运行 Hub
func (h *Hub) Run() {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-h.ctx.Done():
			return

		case c := <-h.registerChan:
			h.register(c)

		case c := <-h.unregisterChan:
			h.unregister(c)

		case bm := <-h.broadcastChan:
			h.processBroadcast(bm)

		case <-ticker.C:
			h.cleanup()
		}
	}
}

// Register 注册客户端
func (h *Hub) Register(c *client.Client) {
	select {
	case h.registerChan <- c:
	default:
		h.logger.Warn("register channel full", zap.String("clientId", c.ID))
	}
}

// register 内部注册
func (h *Hub) register(c *client.Client) {
	h.mu.Lock()
	defer h.mu.Unlock()

	// 检查连接数限制
	if h.config.MaxConnections > 0 && len(h.clients) >= h.config.MaxConnections {
		h.logger.Warn("max connections reached", zap.Int("max", h.config.MaxConnections))
		c.SendError(protocol.CodeServiceUnavailable, "Service unavailable", "Max connections reached", "")
		c.Close()
		return
	}

	// 如果客户端已存在（重连），关闭旧连接
	if old, ok := h.clients[c.ID]; ok {
		old.Close()
	}

	h.clients[c.ID] = c
	h.totalConnections.Add(1)
	h.currentConnections.Add(1)

	h.logger.Info("client registered",
		zap.String("clientId", c.ID),
		zap.String("userId", c.UserID),
		zap.Int64("total", h.totalConnections.Load()),
		zap.Int64("current", h.currentConnections.Load()))

	// 发送连接成功事件
	c.SendEvent(protocol.SysEventConnected, map[string]interface{}{
		"clientId":    c.ID,
		"connectedAt": c.ConnectedAt(),
	})
}

// Unregister 注销客户端
func (h *Hub) Unregister(c *client.Client) {
	select {
	case h.unregisterChan <- c:
	default:
		h.logger.Warn("unregister channel full", zap.String("clientId", c.ID))
	}
}

// unregister 内部注销
func (h *Hub) unregister(c *client.Client) {
	h.mu.Lock()
	defer h.mu.Unlock()

	if _, ok := h.clients[c.ID]; ok {
		delete(h.clients, c.ID)
		h.currentConnections.Add(-1)

		// 从所有频道取消订阅
		for _, channel := range c.GetChannels() {
			if clients, ok := h.channels[channel]; ok {
				delete(clients, c.ID)
				if len(clients) == 0 {
					delete(h.channels, channel)
				}
			}
		}

		// 从所有房间离开
		h.roomManager.LeaveAllRooms(c)

		h.logger.Info("client unregistered",
			zap.String("clientId", c.ID),
			zap.Int64("current", h.currentConnections.Load()))
	}
}

// processBroadcast 处理广播消息
func (h *Hub) processBroadcast(bm *broadcastMessage) {
	h.totalMessages.Add(1)

	switch {
	case bm.target != "":
		// 点对点消息
		h.sendToClientDirect(bm.target, bm.message)

	case bm.room != "":
		// 房间广播
		h.roomManager.BroadcastToRoom(bm.room, bm.message, bm.exclude...)

	case bm.channel != "":
		// 频道广播
		h.broadcastToChannelDirect(bm.channel, bm.message, bm.exclude...)

	default:
		// 全局广播
		h.broadcastDirect(bm.message, bm.exclude...)
	}
}

// Broadcast 全局广播
func (h *Hub) Broadcast(message *protocol.Message, exclude ...string) {
	bm := &broadcastMessage{
		message: message,
		exclude: exclude,
	}
	select {
	case h.broadcastChan <- bm:
	default:
		h.logger.Warn("broadcast channel full")
	}
}

// BroadcastToChannel 广播到频道
func (h *Hub) BroadcastToChannel(channel string, message *protocol.Message, exclude ...string) {
	bm := &broadcastMessage{
		message: message,
		channel: channel,
		exclude: exclude,
	}
	select {
	case h.broadcastChan <- bm:
	default:
		h.logger.Warn("broadcast channel full", zap.String("channel", channel))
	}
}

// BroadcastToRoom 广播到房间
func (h *Hub) BroadcastToRoom(roomID string, message *protocol.Message, exclude ...string) {
	bm := &broadcastMessage{
		message: message,
		room:    roomID,
		exclude: exclude,
	}
	select {
	case h.broadcastChan <- bm:
	default:
		h.logger.Warn("broadcast channel full", zap.String("room", roomID))
	}
}

// SendToClient 发送消息给指定客户端
func (h *Hub) SendToClient(clientID string, message *protocol.Message) bool {
	bm := &broadcastMessage{
		message: message,
		target:  clientID,
	}
	select {
	case h.broadcastChan <- bm:
		return true
	default:
		return false
	}
}

// broadcastDirect 直接广播
func (h *Hub) broadcastDirect(message *protocol.Message, exclude ...string) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	excludeMap := make(map[string]bool)
	for _, id := range exclude {
		excludeMap[id] = true
	}

	for _, c := range h.clients {
		if !excludeMap[c.ID] {
			c.SendMessage(message)
		}
	}
}

// broadcastToChannelDirect 直接广播到频道
func (h *Hub) broadcastToChannelDirect(channel string, message *protocol.Message, exclude ...string) {
	h.mu.RLock()
	clientIDs, ok := h.channels[channel]
	if !ok {
		h.mu.RUnlock()
		return
	}

	excludeMap := make(map[string]bool)
	for _, id := range exclude {
		excludeMap[id] = true
	}

	for clientID := range clientIDs {
		if !excludeMap[clientID] {
			if c, ok := h.clients[clientID]; ok {
				c.SendMessage(message)
			}
		}
	}
	h.mu.RUnlock()
}

// sendToClientDirect 直接发送给客户端
func (h *Hub) sendToClientDirect(clientID string, message *protocol.Message) bool {
	h.mu.RLock()
	c, ok := h.clients[clientID]
	h.mu.RUnlock()

	if !ok {
		return false
	}

	return c.SendMessage(message)
}

// SubscribeChannel 订阅频道
func (h *Hub) SubscribeChannel(c *client.Client, channel string) {
	h.mu.Lock()
	defer h.mu.Unlock()

	if _, ok := h.channels[channel]; !ok {
		h.channels[channel] = make(map[string]bool)
	}
	h.channels[channel][c.ID] = true
	c.SubscribeChannel(channel)

	h.logger.Debug("client subscribed to channel",
		zap.String("clientId", c.ID),
		zap.String("channel", channel))
}

// UnsubscribeChannel 取消订阅频道
func (h *Hub) UnsubscribeChannel(c *client.Client, channel string) {
	h.mu.Lock()
	defer h.mu.Unlock()

	if clients, ok := h.channels[channel]; ok {
		delete(clients, c.ID)
		if len(clients) == 0 {
			delete(h.channels, channel)
		}
	}
	c.UnsubscribeChannel(channel)
}

// GetClient 获取客户端
func (h *Hub) GetClient(clientID string) (*client.Client, bool) {
	h.mu.RLock()
	defer h.mu.RUnlock()
	c, ok := h.clients[clientID]
	return c, ok
}

// GetRoomClients 获取房间内客户端
func (h *Hub) GetRoomClients(roomID string) []*client.Client {
	return h.roomManager.GetRoomClients(roomID)
}

// GetChannelClients 获取频道订阅者
func (h *Hub) GetChannelClients(channel string) []*client.Client {
	h.mu.RLock()
	defer h.mu.RUnlock()

	var clients []*client.Client
	if clientIDs, ok := h.channels[channel]; ok {
		for clientID := range clientIDs {
			if c, ok := h.clients[clientID]; ok {
				clients = append(clients, c)
			}
		}
	}
	return clients
}

// GetStats 获取统计信息
func (h *Hub) GetStats() map[string]interface{} {
	h.mu.RLock()
	defer h.mu.RUnlock()

	return map[string]interface{}{
		"totalConnections":    h.totalConnections.Load(),
		"currentConnections":  h.currentConnections.Load(),
		"totalMessages":       h.totalMessages.Load(),
		"totalClients":        len(h.clients),
		"totalChannels":       len(h.channels),
		"totalRooms":          h.roomManager.GetRoomCount(),
	}
}

// cleanup 定期清理
func (h *Hub) cleanup() {
	h.roomManager.Cleanup()
	h.logger.Debug("hub cleanup completed",
		zap.Int64("currentConnections", h.currentConnections.Load()),
		zap.Int("rooms", h.roomManager.GetRoomCount()))
}

// Shutdown 关闭 Hub
func (h *Hub) Shutdown() {
	h.cancel()

	h.mu.Lock()
	defer h.mu.Unlock()

	// 关闭所有客户端连接
	for _, c := range h.clients {
		c.Close()
	}

	h.clients = make(map[string]*client.Client)
	h.channels = make(map[string]map[string]bool)

	h.logger.Info("hub shutdown completed")
}

// GetRoomManager 获取房间管理器
func (h *Hub) GetRoomManager() *room.Manager {
	return h.roomManager
}

// ClientInfo 客户端信息摘要
type ClientInfo struct {
	ID          string   `json:"id"`
	UserID      string   `json:"userId"`
	TenantID    string   `json:"tenantId"`
	Username    string   `json:"username"`
	ConnectedAt time.Time `json:"connectedAt"`
	Channels    []string `json:"channels"`
	Rooms       []string `json:"rooms"`
}

// GetClientInfos 获取所有客户端信息
func (h *Hub) GetClientInfos() []ClientInfo {
	h.mu.RLock()
	defer h.mu.RUnlock()

	infos := make([]ClientInfo, 0, len(h.clients))
	for _, c := range h.clients {
		info := ClientInfo{
			ID:          c.ID,
			UserID:      c.UserID,
			TenantID:    c.TenantID,
			Username:    c.Username,
			ConnectedAt: c.ConnectedAt(),
			Channels:    c.GetChannels(),
			Rooms:       c.GetRooms(),
		}
		infos = append(infos, info)
	}
	return infos
}
