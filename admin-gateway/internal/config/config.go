package config

import (
	"strings"

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
	viper.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	viper.AutomaticEnv()
	viper.SetEnvPrefix("ADMIN")
	viper.BindEnv("jwt.secret", "JWT_SECRET")
	viper.BindEnv("redis.host", "REDIS_HOST")
	viper.BindEnv("redis.password", "REDIS_PASSWORD")
	viper.BindEnv("server.mode", "GIN_MODE")
	viper.BindEnv("services.eval.internal_token", "EVAL_INTERNAL_SERVICE_TOKEN")
	viper.BindEnv("services.eval.host", "EVAL_SERVICE_HOST")
	viper.BindEnv("services.eval.port", "EVAL_SERVICE_PORT")

	return viper.ReadInConfig()
}
