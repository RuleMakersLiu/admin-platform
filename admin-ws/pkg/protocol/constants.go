package protocol

// 系统事件定义
const (
	// 连接事件
	SysEventConnected    = "sys:connected"
	SysEventDisconnected = "sys:disconnected"
	SysEventReconnected  = "sys:reconnected"

	// 房间事件
	SysEventRoomJoined  = "sys:room:joined"
	SysEventRoomLeft    = "sys:room:left"
	SysEventRoomMembers = "sys:room:members"

	// 订阅事件
	SysEventSubscribed   = "sys:channel:subscribed"
	SysEventUnsubscribed = "sys:channel:unsubscribed"

	// 广播事件
	SysEventBroadcast = "sys:broadcast"
)

// 预定义频道
const (
	ChannelSystem  = "system"       // 系统频道
	ChannelNotice  = "notice"       // 通知频道
	ChannelLog     = "log"          // 日志频道
	ChannelAgent   = "agent"        // Agent 通信频道
	ChannelDeploy  = "deploy"       // 部署频道
	ChannelMonitor = "monitor"      // 监控频道
)

// 预定义房间
const (
	RoomAdmin    = "admin"         // 管理员房间
	RoomTenant   = "tenant:%d"     // 租户房间
	RoomProject  = "project:%d"    // 项目房间
	RoomTask     = "task:%d"       // 任务房间
	RoomDeploy   = "deploy:%d"     // 部署房间
)

// 预定义事件（业务）
const (
	// Agent 相关
	EventAgentMessage   = "agent:message"
	EventAgentStatus    = "agent:status"
	EventAgentTaskStart = "agent:task:start"
	EventAgentTaskEnd   = "agent:task:end"

	// 部署相关
	EventDeployStart    = "deploy:start"
	EventDeployProgress = "deploy:progress"
	EventDeploySuccess  = "deploy:success"
	EventDeployFailed   = "deploy:failed"

	// 系统通知
	EventNoticeInfo     = "notice:info"
	EventNoticeWarning  = "notice:warning"
	EventNoticeError    = "notice:error"

	// 监控相关
	EventMonitorMetric  = "monitor:metric"
	EventMonitorAlert   = "monitor:alert"
)

// 房间配置
type RoomConfig struct {
	MaxMembers    int  `json:"maxMembers"`    // 最大成员数
	IsPersistent  bool `json:"isPersistent"`  // 是否持久化
	IsPrivate     bool `json:"isPrivate"`     // 是否私有房间
	EnableHistory bool `json:"enableHistory"` // 是否启用历史消息
	TTL           int  `json:"ttl"`           // 过期时间（秒），0表示不过期
}

// 频道配置
type ChannelConfig struct {
	IsPublic      bool `json:"isPublic"`      // 是否公开
	EnableBuffer  bool `json:"enableBuffer"`  // 是否启用缓冲
	BufferSize    int  `json:"bufferSize"`    // 缓冲大小
	RateLimit     int  `json:"rateLimit"`     // 速率限制（消息/秒）
}

// 默认配置
var DefaultRoomConfig = RoomConfig{
	MaxMembers:    1000,
	IsPersistent:  false,
	IsPrivate:     false,
	EnableHistory: false,
	TTL:           0,
}

var DefaultChannelConfig = ChannelConfig{
	IsPublic:      true,
	EnableBuffer:  true,
	BufferSize:    100,
	RateLimit:     100,
}
