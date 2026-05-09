package room

import (
	"sync"

	"admin-ws/internal/client"
	"admin-ws/pkg/protocol"

	"go.uber.org/zap"
)

// Manager 房间管理器
type Manager struct {
	rooms    map[string]*Room
	mu       sync.RWMutex
	logger   *zap.Logger
}

// NewManager 创建房间管理器
func NewManager(logger *zap.Logger) *Manager {
	return &Manager{
		rooms:  make(map[string]*Room),
		logger: logger,
	}
}

// CreateRoom 创建房间
func (m *Manager) CreateRoom(id, name, owner string, config *protocol.RoomConfig) *Room {
	m.mu.Lock()
	defer m.mu.Unlock()

	// 如果房间已存在，返回现有房间
	if room, ok := m.rooms[id]; ok {
		return room
	}

	// 使用默认配置
	if config == nil {
		defaultConfig := protocol.DefaultRoomConfig
		config = &defaultConfig
	}

	room := NewRoom(id, name, owner, *config, m.logger)
	m.rooms[id] = room

	m.logger.Info("room created",
		zap.String("roomId", id),
		zap.String("owner", owner))

	return room
}

// GetRoom 获取房间
func (m *Manager) GetRoom(id string) (*Room, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	room, ok := m.rooms[id]
	return room, ok
}

// DeleteRoom 删除房间
func (m *Manager) DeleteRoom(id string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if room, ok := m.rooms[id]; ok {
		room.Close()
		delete(m.rooms, id)
		m.logger.Info("room deleted", zap.String("roomId", id))
	}
}

// JoinRoom 加入房间
func (m *Manager) JoinRoom(roomID string, c *client.Client) bool {
	m.mu.RLock()
	room, ok := m.rooms[roomID]
	m.mu.RUnlock()

	if !ok {
		// 自动创建房间
		room = m.CreateRoom(roomID, roomID, c.ID, nil)
	}

	return room.Join(c)
}

// LeaveRoom 离开房间
func (m *Manager) LeaveRoom(roomID string, c *client.Client) {
	m.mu.RLock()
	room, ok := m.rooms[roomID]
	m.mu.RUnlock()

	if ok {
		room.Leave(c)

		// 如果房间为空且非持久化，则删除
		if room.GetMemberCount() == 0 && !room.Config.IsPersistent {
			m.DeleteRoom(roomID)
		}
	}
}

// LeaveAllRooms 离开所有房间
func (m *Manager) LeaveAllRooms(c *client.Client) {
	m.mu.RLock()
	rooms := make([]*Room, 0)
	for _, room := range m.rooms {
		if room.HasMember(c.ID) {
			rooms = append(rooms, room)
		}
	}
	m.mu.RUnlock()

	for _, room := range rooms {
		room.Leave(c)
		if room.GetMemberCount() == 0 && !room.Config.IsPersistent {
			m.DeleteRoom(room.ID)
		}
	}
}

// BroadcastToRoom 广播消息到房间
func (m *Manager) BroadcastToRoom(roomID string, message *protocol.Message, exclude ...string) bool {
	m.mu.RLock()
	room, ok := m.rooms[roomID]
	m.mu.RUnlock()

	if !ok {
		return false
	}

	room.Broadcast(message, exclude...)
	return true
}

// GetRoomClients 获取房间内所有客户端
func (m *Manager) GetRoomClients(roomID string) []*client.Client {
	m.mu.RLock()
	room, ok := m.rooms[roomID]
	m.mu.RUnlock()

	if !ok {
		return nil
	}

	return room.GetMembers()
}

// GetRoomInfo 获取房间信息
func (m *Manager) GetRoomInfo(roomID string, includeMembers bool) (*RoomInfo, bool) {
	m.mu.RLock()
	room, ok := m.rooms[roomID]
	m.mu.RUnlock()

	if !ok {
		return nil, false
	}

	return room.GetInfo(includeMembers), true
}

// GetAllRooms 获取所有房间
func (m *Manager) GetAllRooms() []*RoomInfo {
	m.mu.RLock()
	defer m.mu.RUnlock()

	rooms := make([]*RoomInfo, 0, len(m.rooms))
	for _, room := range m.rooms {
		rooms = append(rooms, room.GetInfo(false))
	}
	return rooms
}

// GetRoomCount 获取房间数量
func (m *Manager) GetRoomCount() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.rooms)
}

// GetClientRooms 获取客户端所在的房间
func (m *Manager) GetClientRooms(clientID string) []string {
	m.mu.RLock()
	defer m.mu.RUnlock()

	rooms := make([]string, 0)
	for _, room := range m.rooms {
		if room.HasMember(clientID) {
			rooms = append(rooms, room.ID)
		}
	}
	return rooms
}

// Cleanup 清理空房间
func (m *Manager) Cleanup() {
	m.mu.Lock()
	defer m.mu.Unlock()

	for id, room := range m.rooms {
		if room.GetMemberCount() == 0 && !room.Config.IsPersistent {
			room.Close()
			delete(m.rooms, id)
			m.logger.Debug("cleaned up empty room", zap.String("roomId", id))
		}
	}
}
