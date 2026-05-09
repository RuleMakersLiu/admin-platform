package service

import (
	"fmt"
	"sync"
	"time"

	"admin-agent/internal/model"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

// MemoryType 记忆类型常量
const (
	MemoryTypeShortTerm = "short_term" // 短期记忆
	MemoryTypeLongTerm  = "long_term"  // 长期记忆
)

// MemoryService 记忆服务 - 数据库持久化实现
// 短期记忆用于存储会话对话上下文，长期记忆用于存储需要持久化的关键信息
// 当数据库不可用时，自动降级到内存存储模式
type MemoryService struct {
	db *gorm.DB
	// 内存降级存储（当 db 为 nil 时使用）
	inMemoryShortTerm map[string][]string
	inMemoryLongTerm  map[string]map[string]string
	mu                sync.RWMutex
}

// NewMemoryService 创建记忆服务
// 数据库连接由外部注入，实现依赖倒置原则
// 如果 db 为 nil，自动降级到内存存储模式
func NewMemoryService(db *gorm.DB) *MemoryService {
	return &MemoryService{
		db:                db,
		inMemoryShortTerm: make(map[string][]string),
		inMemoryLongTerm:  make(map[string]map[string]string),
	}
}

// isDBAvailable 检查数据库是否可用
func (m *MemoryService) isDBAvailable() bool {
	return m.db != nil
}

// ========== 短期记忆接口 ==========

// AddMessage 添加消息到短期记忆
// 自动生成 memory_id，使用当前时间戳作为创建时间
// 短期记忆不设置过期时间，由 CleanupExpired 统一清理
func (m *MemoryService) AddMessage(sessionID, content string) {
	if m.isDBAvailable() {
		m.addMessageDB(sessionID, content)
	} else {
		m.addMessageMemory(sessionID, content)
	}
}

// addMessageDB 数据库存储实现
func (m *MemoryService) addMessageDB(sessionID, content string) {
	now := model.NowMillis()
	memoryID := fmt.Sprintf("mem_%s", uuid.New().String()[:8])

	memory := &model.AgentMemory{
		MemoryID:   memoryID,
		SessionID:  sessionID,
		MemoryType: MemoryTypeShortTerm,
		Content:    content,
		KeyInfo:    "", // 短期记忆不需要 key_info
		Importance: 50, // 默认重要性
		TenantID:   0,  // 短期记忆不区分租户
		CreateTime: now,
		UpdateTime: now,
	}

	// 插入新记录
	if err := m.db.Create(memory).Error; err != nil {
		// 数据库操作失败时静默处理，不影响主流程
		return
	}

	// 自动清理超出限制的旧消息，保留最近 20 条
	m.cleanupOldMessagesDB(sessionID, 20)
}

// addMessageMemory 内存存储实现（降级模式）
func (m *MemoryService) addMessageMemory(sessionID, content string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	messages := m.inMemoryShortTerm[sessionID]
	messages = append(messages, content)

	// 保留最近20条消息
	if len(messages) > 20 {
		messages = messages[len(messages)-20:]
	}

	m.inMemoryShortTerm[sessionID] = messages
}

// GetRecentMessages 获取最近的消息
// 按创建时间倒序获取最近 limit 条消息，然后按时间正序返回
// 保证消息顺序与对话顺序一致
func (m *MemoryService) GetRecentMessages(sessionID string, limit int) []string {
	if limit <= 0 {
		limit = 20
	}

	if m.isDBAvailable() {
		return m.getRecentMessagesDB(sessionID, limit)
	}
	return m.getRecentMessagesMemory(sessionID, limit)
}

// getRecentMessagesDB 数据库查询实现
func (m *MemoryService) getRecentMessagesDB(sessionID string, limit int) []string {
	var memories []model.AgentMemory
	// 先按时间倒序获取最近的记录
	err := m.db.Where("session_id = ? AND memory_type = ? AND is_deleted = 0",
		sessionID, MemoryTypeShortTerm).
		Order("create_time DESC").
		Limit(limit).
		Find(&memories).Error

	if err != nil || len(memories) == 0 {
		return nil
	}

	// 反转顺序，使消息按时间正序排列
	result := make([]string, len(memories))
	for i, j := 0, len(memories)-1; i < len(memories); i, j = i+1, j-1 {
		result[i] = memories[j].Content
	}

	return result
}

// getRecentMessagesMemory 内存查询实现（降级模式）
func (m *MemoryService) getRecentMessagesMemory(sessionID string, limit int) []string {
	m.mu.RLock()
	defer m.mu.RUnlock()

	messages := m.inMemoryShortTerm[sessionID]
	if len(messages) == 0 {
		return nil
	}

	if limit > len(messages) {
		limit = len(messages)
	}

	return messages[len(messages)-limit:]
}

// ========== 长期记忆接口 ==========

// StoreLongTerm 存储长期记忆
// 长期记忆通过 keyInfo 作为键进行索引，支持快速检索
// 如果已存在相同 session_id + key_info 的记录，则更新内容
func (m *MemoryService) StoreLongTerm(sessionID, keyInfo, content string) {
	if m.isDBAvailable() {
		m.storeLongTermDB(sessionID, keyInfo, content)
	} else {
		m.storeLongTermMemory(sessionID, keyInfo, content)
	}
}

// storeLongTermDB 数据库存储实现
func (m *MemoryService) storeLongTermDB(sessionID, keyInfo, content string) {
	now := model.NowMillis()

	// 查找是否已存在相同的长期记忆
	var existing model.AgentMemory
	err := m.db.Where("session_id = ? AND key_info = ? AND memory_type = ? AND is_deleted = 0",
		sessionID, keyInfo, MemoryTypeLongTerm).
		First(&existing).Error

	if err == gorm.ErrRecordNotFound {
		// 不存在，创建新记录
		memoryID := fmt.Sprintf("mem_%s", uuid.New().String()[:8])
		memory := &model.AgentMemory{
			MemoryID:   memoryID,
			SessionID:  sessionID,
			MemoryType: MemoryTypeLongTerm,
			KeyInfo:    keyInfo,
			Content:    content,
			Importance: 80, // 长期记忆默认重要性较高
			TenantID:   0,
			CreateTime: now,
			UpdateTime: now,
		}
		m.db.Create(memory)
	} else if err == nil {
		// 已存在，更新内容和时间
		m.db.Model(&existing).Updates(map[string]interface{}{
			"content":     content,
			"update_time": now,
		})
	}
	// 其他错误静默处理
}

// storeLongTermMemory 内存存储实现（降级模式）
func (m *MemoryService) storeLongTermMemory(sessionID, keyInfo, content string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.inMemoryLongTerm[sessionID] == nil {
		m.inMemoryLongTerm[sessionID] = make(map[string]string)
	}

	m.inMemoryLongTerm[sessionID][keyInfo] = content
}

// RetrieveLongTerm 检索长期记忆
// 根据 session_id 和 key_info 精确查找长期记忆
func (m *MemoryService) RetrieveLongTerm(sessionID, keyInfo string) string {
	if m.isDBAvailable() {
		return m.retrieveLongTermDB(sessionID, keyInfo)
	}
	return m.retrieveLongTermMemory(sessionID, keyInfo)
}

// retrieveLongTermDB 数据库查询实现
func (m *MemoryService) retrieveLongTermDB(sessionID, keyInfo string) string {
	var memory model.AgentMemory
	err := m.db.Where("session_id = ? AND key_info = ? AND memory_type = ? AND is_deleted = 0",
		sessionID, keyInfo, MemoryTypeLongTerm).
		First(&memory).Error

	if err != nil {
		return ""
	}

	// 更新访问计数和最后访问时间
	now := model.NowMillis()
	m.db.Model(&memory).Updates(map[string]interface{}{
		"access_count":     gorm.Expr("access_count + 1"),
		"last_access_time": now,
	})

	return memory.Content
}

// retrieveLongTermMemory 内存查询实现（降级模式）
func (m *MemoryService) retrieveLongTermMemory(sessionID, keyInfo string) string {
	m.mu.RLock()
	defer m.mu.RUnlock()

	if memories, ok := m.inMemoryLongTerm[sessionID]; ok {
		return memories[keyInfo]
	}
	return ""
}

// GetAllLongTerm 获取所有长期记忆
// 返回指定会话的所有长期记忆，以 key_info 为键的 map 形式
func (m *MemoryService) GetAllLongTerm(sessionID string) map[string]string {
	if m.isDBAvailable() {
		return m.getAllLongTermDB(sessionID)
	}
	return m.getAllLongTermMemory(sessionID)
}

// getAllLongTermDB 数据库查询实现
func (m *MemoryService) getAllLongTermDB(sessionID string) map[string]string {
	var memories []model.AgentMemory
	err := m.db.Where("session_id = ? AND memory_type = ? AND is_deleted = 0",
		sessionID, MemoryTypeLongTerm).
		Order("importance DESC, create_time DESC").
		Find(&memories).Error

	result := make(map[string]string)
	if err != nil || len(memories) == 0 {
		return result
	}

	for _, mem := range memories {
		result[mem.KeyInfo] = mem.Content
	}

	return result
}

// getAllLongTermMemory 内存查询实现（降级模式）
func (m *MemoryService) getAllLongTermMemory(sessionID string) map[string]string {
	m.mu.RLock()
	defer m.mu.RUnlock()

	result := make(map[string]string)
	if memories, ok := m.inMemoryLongTerm[sessionID]; ok {
		for k, v := range memories {
			result[k] = v
		}
	}
	return result
}

// ========== 会话管理接口 ==========

// ClearSession 清除会话记忆
// 软删除方式，将 is_deleted 标记为 1
// 同时清除短期和长期记忆
func (m *MemoryService) ClearSession(sessionID string) {
	if m.isDBAvailable() {
		m.clearSessionDB(sessionID)
	} else {
		m.clearSessionMemory(sessionID)
	}
}

// clearSessionDB 数据库清除实现
func (m *MemoryService) clearSessionDB(sessionID string) {
	now := model.NowMillis()
	m.db.Model(&model.AgentMemory{}).
		Where("session_id = ? AND is_deleted = 0", sessionID).
		Updates(map[string]interface{}{
			"is_deleted":  1,
			"update_time": now,
		})
}

// clearSessionMemory 内存清除实现（降级模式）
func (m *MemoryService) clearSessionMemory(sessionID string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	delete(m.inMemoryShortTerm, sessionID)
	delete(m.inMemoryLongTerm, sessionID)
}

// ========== 维护接口 ==========

// CleanupExpired 清理过期记忆
// 清理满足以下条件的记忆：
// 1. 短期记忆超过 maxAge 时间的
// 2. 显式设置了 expire_time 且已过期的
// 注意：内存模式下不支持过期清理
func (m *MemoryService) CleanupExpired(maxAge time.Duration) {
	if !m.isDBAvailable() {
		// 内存模式不支持过期清理
		return
	}

	now := model.NowMillis()
	expireThreshold := now - maxAge.Milliseconds()

	// 删除过期的短期记忆（按时间阈值）
	m.db.Model(&model.AgentMemory{}).
		Where("memory_type = ? AND create_time < ? AND is_deleted = 0",
			MemoryTypeShortTerm, expireThreshold).
		Updates(map[string]interface{}{
			"is_deleted":  1,
			"update_time": now,
		})

	// 删除显式设置过期时间且已过期的记忆
	m.db.Model(&model.AgentMemory{}).
		Where("expire_time > 0 AND expire_time < ? AND is_deleted = 0", now).
		Updates(map[string]interface{}{
			"is_deleted":  1,
			"update_time": now,
		})
}

// GetMemoryStats 获取记忆统计
// 返回指定会话的记忆使用情况统计信息
func (m *MemoryService) GetMemoryStats(sessionID string) map[string]interface{} {
	if m.isDBAvailable() {
		return m.getMemoryStatsDB(sessionID)
	}
	return m.getMemoryStatsMemory(sessionID)
}

// getMemoryStatsDB 数据库统计实现
func (m *MemoryService) getMemoryStatsDB(sessionID string) map[string]interface{} {
	// 统计短期记忆数量
	var shortTermCount int64
	m.db.Model(&model.AgentMemory{}).
		Where("session_id = ? AND memory_type = ? AND is_deleted = 0",
			sessionID, MemoryTypeShortTerm).
		Count(&shortTermCount)

	// 统计长期记忆数量
	var longTermCount int64
	m.db.Model(&model.AgentMemory{}).
		Where("session_id = ? AND memory_type = ? AND is_deleted = 0",
			sessionID, MemoryTypeLongTerm).
		Count(&longTermCount)

	return map[string]interface{}{
		"session_id":       sessionID,
		"short_term_count": shortTermCount,
		"long_term_count":  longTermCount,
		"short_term_limit": 20,
	}
}

// getMemoryStatsMemory 内存统计实现（降级模式）
func (m *MemoryService) getMemoryStatsMemory(sessionID string) map[string]interface{} {
	m.mu.RLock()
	defer m.mu.RUnlock()

	shortTermCount := len(m.inMemoryShortTerm[sessionID])
	longTermCount := 0
	if memories, ok := m.inMemoryLongTerm[sessionID]; ok {
		longTermCount = len(memories)
	}

	return map[string]interface{}{
		"session_id":       sessionID,
		"short_term_count": shortTermCount,
		"long_term_count":  longTermCount,
		"short_term_limit": 20,
	}
}

// ========== 内部方法 ==========

// cleanupOldMessagesDB 清理超出限制的旧消息（数据库版）
// 内部方法，保留最近 limit 条消息，删除其余的
func (m *MemoryService) cleanupOldMessagesDB(sessionID string, limit int) {
	// 获取第 limit 条记录的时间作为阈值
	var threshold model.AgentMemory
	err := m.db.Where("session_id = ? AND memory_type = ? AND is_deleted = 0",
		sessionID, MemoryTypeShortTerm).
		Order("create_time DESC").
		Offset(limit).
		First(&threshold).Error

	if err != nil {
		// 记录不足 limit 条，无需清理
		return
	}

	// 删除早于阈值时间的记录
	m.db.Model(&model.AgentMemory{}).
		Where("session_id = ? AND memory_type = ? AND create_time < ? AND is_deleted = 0",
			sessionID, MemoryTypeShortTerm, threshold.CreateTime).
		Updates(map[string]interface{}{
			"is_deleted":  1,
			"update_time": model.NowMillis(),
		})
}
