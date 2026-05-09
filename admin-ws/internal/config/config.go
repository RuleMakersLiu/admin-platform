package config

import (
	"time"

	"github.com/spf13/viper"
)

type Config struct {
	Server    ServerConfig    `mapstructure:"server"`
	WebSocket WebSocketConfig `mapstructure:"websocket"`
	Redis     RedisConfig     `mapstructure:"redis"`
	JWT       JWTConfig       `mapstructure:"jwt"`
	Log       LogConfig       `mapstructure:"log"`
	Agent     AgentConfig     `mapstructure:"agent"`
	Gateway   GatewayConfig   `mapstructure:"gateway"`
}

type ServerConfig struct {
	Port int    `mapstructure:"port"`
	Mode string `mapstructure:"mode"`
}

type WebSocketConfig struct {
	ReadBufferSize  int           `mapstructure:"read_buffer_size"`
	WriteBufferSize int           `mapstructure:"write_buffer_size"`
	MaxMessageSize  int64         `mapstructure:"max_message_size"`
	PingPeriod      time.Duration `mapstructure:"ping_period"`
	PongWait        time.Duration `mapstructure:"pong_wait"`
	WriteWait       time.Duration `mapstructure:"write_wait"`
	MaxConnections  int           `mapstructure:"max_connections"`
	MessageQueueSize int          `mapstructure:"message_queue_size"`
}

type RedisConfig struct {
	Host     string `mapstructure:"host"`
	Port     int    `mapstructure:"port"`
	Password string `mapstructure:"password"`
	DB       int    `mapstructure:"db"`
	PoolSize int    `mapstructure:"pool_size"`
}

type JWTConfig struct {
	Secret string `mapstructure:"secret"`
	Issuer string `mapstructure:"issuer"`
}

type LogConfig struct {
	Level  string `mapstructure:"level"`
	Format string `mapstructure:"format"`
}

type AgentConfig struct {
	Enabled bool          `mapstructure:"enabled"`
	Address string        `mapstructure:"address"`
	Timeout time.Duration `mapstructure:"timeout"`
}

type GatewayConfig struct {
	Enabled bool          `mapstructure:"enabled"`
	Address string        `mapstructure:"address"`
	Timeout time.Duration `mapstructure:"timeout"`
}

var GlobalConfig *Config

// Load 加载配置
func Load(configPath string) (*Config, error) {
	v := viper.New()
	v.SetConfigFile(configPath)
	v.SetConfigType("yaml")

	// 设置默认值
	setDefaults(v)

	if err := v.ReadInConfig(); err != nil {
		return nil, err
	}

	var cfg Config
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, err
	}

	GlobalConfig = &cfg
	return &cfg, nil
}

func setDefaults(v *viper.Viper) {
	// Server
	v.SetDefault("server.port", 8086)
	v.SetDefault("server.mode", "debug")

	// WebSocket
	v.SetDefault("websocket.read_buffer_size", 1024)
	v.SetDefault("websocket.write_buffer_size", 1024)
	v.SetDefault("websocket.max_message_size", 65536)
	v.SetDefault("websocket.ping_period", "30s")
	v.SetDefault("websocket.pong_wait", "60s")
	v.SetDefault("websocket.write_wait", "10s")
	v.SetDefault("websocket.max_connections", 10000)
	v.SetDefault("websocket.message_queue_size", 256)

	// Redis
	v.SetDefault("redis.host", "localhost")
	v.SetDefault("redis.port", 6379)
	v.SetDefault("redis.password", "")
	v.SetDefault("redis.db", 0)
	v.SetDefault("redis.pool_size", 100)

	// Log
	v.SetDefault("log.level", "debug")
	v.SetDefault("log.format", "console")
}
