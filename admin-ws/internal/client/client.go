package client

import (
	"encoding/json"
	"sync"
	"sync/atomic"
	"time"

	"admin-ws/pkg/protocol"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

// Client WebSocket 客户端
type Client struct {
	ID           string            `json:"id"`           // 客户端唯一标识
	UserID       string            `json:"userId"`       // 用户ID
	TenantID     string            `json:"tenantId"`     // 租户ID
	Username     string            `json:"username"`     // 用户名
	Roles        []string          `json:"roles"`        // 角色列表
	Permissions  []string          `json:"permissions"`  // 权限列表
	Metadata     map[string]string `json:"metadata"`     // 元数据

	conn         *websocket.Conn   `json:"-"`            // WebSocket 连接
	hub          HubInterface      `json:"-"`            // Hub 引用
	send         chan []byte       `json:"-"`            // 发送队列
	logger       *zap.Logger       `json:"-"`            // 日志

	// 状态管理
	connectedAt  time.Time         `json:"connectedAt"`  // 连接时间
	lastPingAt   time.Time         `json:"lastPingAt"`   // 最后心跳时间
	sequence     int64             `json:"-"`            // 消息序列号
	closed       atomic.Bool       `json:"-"`            // 是否已关闭

	// 订阅管理
	channels     map[string]bool   `json:"-"`            // 订阅的频道
	rooms        map[string]bool   `json:"-"`            // 加入的房间
	mu           sync.RWMutex      `json:"-"`            // 读写锁
}

// HubInterface Hub 接口定义
type HubInterface interface {
	Register(client *Client)
	Unregister(client *Client)
	Broadcast(message *protocol.Message, exclude ...string)
	BroadcastToRoom(roomID string, message *protocol.Message, exclude ...string)
	BroadcastToChannel(channel string, message *protocol.Message, exclude ...string)
	SendToClient(clientID string, message *protocol.Message) bool
	GetClient(clientID string) (*Client, bool)
	GetRoomClients(roomID string) []*Client
}

// ConnectedAt 返回连接时间
func (c *Client) ConnectedAt() time.Time {
	return c.connectedAt
}

// NewClient 创建新客户端
func NewClient(id string, conn *websocket.Conn, hub HubInterface, logger *zap.Logger) *Client {
	return &Client{
		ID:          id,
		conn:        conn,
		hub:         hub,
		send:        make(chan []byte, 256),
		logger:      logger,
		connectedAt: time.Now(),
		lastPingAt:  time.Now(),
		channels:    make(map[string]bool),
		rooms:       make(map[string]bool),
		Metadata:    make(map[string]string),
	}
}

// ReadPump 读取消息泵
func (c *Client) ReadPump(maxMessageSize int64, pongWait, writeWait time.Duration, onMessage func(*protocol.Message)) {
	defer func() {
		c.Close()
	}()

	c.conn.SetReadLimit(maxMessageSize)
	c.conn.SetReadDeadline(time.Now().Add(pongWait))
	c.conn.SetPongHandler(func(string) error {
		c.conn.SetReadDeadline(time.Now().Add(pongWait))
		c.lastPingAt = time.Now()
		return nil
	})

	for {
		_, message, err := c.conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				c.logger.Error("read error", zap.Error(err), zap.String("clientId", c.ID))
			}
			break
		}

		msg, err := protocol.ParseMessage(message)
		if err != nil {
			c.logger.Error("parse message error", zap.Error(err), zap.String("clientId", c.ID))
			c.SendError(protocol.CodeBadRequest, "Invalid message format", err.Error(), "")
			continue
		}

		// 处理心跳
		if msg.Type == protocol.TypePing {
			c.lastPingAt = time.Now()
			c.SendMessage(protocol.NewPong())
			continue
		}

		// 调用消息处理函数
		if onMessage != nil {
			onMessage(msg)
		}
	}
}

// WritePump 写入消息泵
func (c *Client) WritePump(pingPeriod, writeWait time.Duration) {
	ticker := time.NewTicker(pingPeriod)
	defer func() {
		ticker.Stop()
		c.Close()
	}()

	for {
		select {
		case message, ok := <-c.send:
			c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if !ok {
				c.conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}

			w, err := c.conn.NextWriter(websocket.TextMessage)
			if err != nil {
				return
			}
			w.Write(message)

			// 批量发送队列中的消息
			n := len(c.send)
			for i := 0; i < n; i++ {
				w.Write([]byte{'\n'})
				w.Write(<-c.send)
			}

			if err := w.Close(); err != nil {
				return
			}

		case <-ticker.C:
			c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}

// SendMessage 发送消息
func (c *Client) SendMessage(msg *protocol.Message) bool {
	if c.closed.Load() {
		return false
	}

	msg.Sequence = atomic.AddInt64(&c.sequence, 1)

	data, err := msg.ToJSON()
	if err != nil {
		c.logger.Error("marshal message error", zap.Error(err), zap.String("clientId", c.ID))
		return false
	}

	select {
	case c.send <- data:
		return true
	default:
		c.logger.Warn("client send buffer full", zap.String("clientId", c.ID))
		return false
	}
}

// SendError 发送错误消息
func (c *Client) SendError(code int, message, detail, requestID string) {
	c.SendMessage(protocol.NewError(code, message, detail, requestID))
}

// SendEvent 发送事件消息
func (c *Client) SendEvent(event string, data interface{}) {
	c.SendMessage(protocol.NewEvent(event, data))
}

// Close 关闭客户端连接
func (c *Client) Close() {
	if !c.closed.CompareAndSwap(false, true) {
		return
	}

	close(c.send)
	c.conn.Close()

	if c.hub != nil {
		c.hub.Unregister(c)
	}
}

// SubscribeChannel 订阅频道
func (c *Client) SubscribeChannel(channel string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.channels[channel] = true
}

// UnsubscribeChannel 取消订阅频道
func (c *Client) UnsubscribeChannel(channel string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	delete(c.channels, channel)
}

// GetChannels 获取订阅的频道列表
func (c *Client) GetChannels() []string {
	c.mu.RLock()
	defer c.mu.RUnlock()

	channels := make([]string, 0, len(c.channels))
	for ch := range c.channels {
		channels = append(channels, ch)
	}
	return channels
}

// IsSubscribed 检查是否订阅了频道
func (c *Client) IsSubscribed(channel string) bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.channels[channel]
}

// JoinRoom 加入房间
func (c *Client) JoinRoom(roomID string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.rooms[roomID] = true
}

// LeaveRoom 离开房间
func (c *Client) LeaveRoom(roomID string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	delete(c.rooms, roomID)
}

// GetRooms 获取加入的房间列表
func (c *Client) GetRooms() []string {
	c.mu.RLock()
	defer c.mu.RUnlock()

	rooms := make([]string, 0, len(c.rooms))
	for room := range c.rooms {
		rooms = append(rooms, room)
	}
	return rooms
}

// IsInRoom 检查是否在房间中
func (c *Client) IsInRoom(roomID string) bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.rooms[roomID]
}

// GetInfo 获取客户端信息
func (c *Client) GetInfo() *ClientInfo {
	c.mu.RLock()
	defer c.mu.RUnlock()

	return &ClientInfo{
		ID:           c.ID,
		UserID:       c.UserID,
		TenantID:     c.TenantID,
		Username:     c.Username,
		Roles:        c.Roles,
		ConnectedAt:  c.connectedAt.UnixMilli(),
		LastPingAt:   c.lastPingAt.UnixMilli(),
		Channels:     c.GetChannels(),
		Rooms:        c.GetRooms(),
		Metadata:     c.Metadata,
	}
}

// SetMetadata 设置元数据
func (c *Client) SetMetadata(key, value string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.Metadata[key] = value
}

// GetMetadata 获取元数据
func (c *Client) GetMetadata(key string) (string, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	val, ok := c.Metadata[key]
	return val, ok
}

// ClientInfo 客户端信息（用于序列化）
type ClientInfo struct {
	ID           string            `json:"id"`
	UserID       string            `json:"userId"`
	TenantID     string            `json:"tenantId"`
	Username     string            `json:"username"`
	Roles        []string          `json:"roles"`
	ConnectedAt  int64             `json:"connectedAt"`
	LastPingAt   int64             `json:"lastPingAt"`
	Channels     []string          `json:"channels"`
	Rooms        []string          `json:"rooms"`
	Metadata     map[string]string `json:"metadata"`
}

// MarshalJSON 自定义 JSON 序列化
func (c *Client) MarshalJSON() ([]byte, error) {
	return json.Marshal(c.GetInfo())
}
