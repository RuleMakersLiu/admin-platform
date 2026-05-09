package room

import (
	"sync"
	"time"

	"admin-ws/internal/client"
	"admin-ws/pkg/protocol"

	"go.uber.org/zap"
)

// Room 房间管理
type Room struct {
	ID          string            `json:"id"`
	Name        string            `json:"name"`
	Owner       string            `json:"owner"`        // 房间所有者
	Config      protocol.RoomConfig `json:"config"`
	CreatedAt   time.Time         `json:"createdAt"`
	members     map[string]*client.Client
	mu          sync.RWMutex
	logger      *zap.Logger
	messageChan chan *protocol.Message // 消息通道
	closed      bool
}

// NewRoom 创建新房间
func NewRoom(id, name, owner string, config protocol.RoomConfig, logger *zap.Logger) *Room {
	return &Room{
		ID:        id,
		Name:      name,
		Owner:     owner,
		Config:    config,
		CreatedAt: time.Now(),
		members:   make(map[string]*client.Client),
		logger:    logger,
	}
}

// Join 加入房间
func (r *Room) Join(c *client.Client) bool {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.closed {
		return false
	}

	// 检查房间人数限制
	if r.Config.MaxMembers > 0 && len(r.members) >= r.Config.MaxMembers {
		r.logger.Warn("room is full",
			zap.String("roomId", r.ID),
			zap.Int("maxMembers", r.Config.MaxMembers))
		return false
	}

	r.members[c.ID] = c
	c.JoinRoom(r.ID)

	r.logger.Debug("client joined room",
		zap.String("roomId", r.ID),
		zap.String("clientId", c.ID),
		zap.Int("memberCount", len(r.members)))

	return true
}

// Leave 离开房间
func (r *Room) Leave(c *client.Client) {
	r.mu.Lock()
	defer r.mu.Unlock()

	delete(r.members, c.ID)
	c.LeaveRoom(r.ID)

	r.logger.Debug("client left room",
		zap.String("roomId", r.ID),
		zap.String("clientId", c.ID),
		zap.Int("memberCount", len(r.members)))
}

// Broadcast 广播消息到房间
func (r *Room) Broadcast(message *protocol.Message, exclude ...string) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	if r.closed {
		return
	}

	excludeMap := make(map[string]bool)
	for _, id := range exclude {
		excludeMap[id] = true
	}

	for _, c := range r.members {
		if !excludeMap[c.ID] {
			c.SendMessage(message)
		}
	}
}

// GetMembers 获取房间成员
func (r *Room) GetMembers() []*client.Client {
	r.mu.RLock()
	defer r.mu.RUnlock()

	members := make([]*client.Client, 0, len(r.members))
	for _, c := range r.members {
		members = append(members, c)
	}
	return members
}

// GetMemberCount 获取成员数量
func (r *Room) GetMemberCount() int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return len(r.members)
}

// HasMember 检查成员是否在房间
func (r *Room) HasMember(clientID string) bool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	_, ok := r.members[clientID]
	return ok
}

// Close 关闭房间
func (r *Room) Close() {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.closed {
		return
	}

	r.closed = true

	// 通知所有成员房间已关闭
	closeMsg := protocol.NewEvent(protocol.EventLeft, map[string]interface{}{
		"roomId": r.ID,
		"reason": "room_closed",
	})

	for _, c := range r.members {
		c.SendMessage(closeMsg)
		c.LeaveRoom(r.ID)
	}

	r.members = make(map[string]*client.Client)
}

// IsClosed 检查房间是否已关闭
func (r *Room) IsClosed() bool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.closed
}

// RoomInfo 房间信息
type RoomInfo struct {
	ID          string   `json:"id"`
	Name        string   `json:"name"`
	Owner       string   `json:"owner"`
	MemberCount int      `json:"memberCount"`
	CreatedAt   int64    `json:"createdAt"`
	Members     []string `json:"members,omitempty"`
}

// GetInfo 获取房间信息
func (r *Room) GetInfo(includeMembers bool) *RoomInfo {
	r.mu.RLock()
	defer r.mu.RUnlock()

	info := &RoomInfo{
		ID:          r.ID,
		Name:        r.Name,
		Owner:       r.Owner,
		MemberCount: len(r.members),
		CreatedAt:   r.CreatedAt.UnixMilli(),
	}

	if includeMembers {
		info.Members = make([]string, 0, len(r.members))
		for id := range r.members {
			info.Members = append(info.Members, id)
		}
	}

	return info
}
