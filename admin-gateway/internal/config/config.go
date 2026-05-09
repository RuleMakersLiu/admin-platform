package config

import (
	"github.com/spf13/viper"
)

// Load 加载配置文件
func Load() error {
	viper.SetConfigName("config")
	viper.SetConfigType("yaml")
	viper.AddConfigPath(".")
	viper.AddConfigPath("./config")
	viper.AddConfigPath("/etc/admin-gateway")

	// 设置默认值
	viper.SetDefault("server.port", "8080")
	viper.SetDefault("server.mode", "debug")
	viper.SetDefault("redis.host", "localhost")
	viper.SetDefault("redis.port", 6379)
	viper.SetDefault("redis.db", 0)

	// 支持环境变量覆盖配置（优先级: 环境变量 > 配置文件）
	viper.AutomaticEnv()
	viper.SetEnvPrefix("ADMIN")
	viper.BindEnv("jwt.secret", "JWT_SECRET")
	viper.BindEnv("redis.password", "REDIS_PASSWORD")
	viper.BindEnv("server.mode", "GIN_MODE")

	return viper.ReadInConfig()
}
