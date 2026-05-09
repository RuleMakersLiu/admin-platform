package config

import (
	"fmt"
	"os"

	"github.com/spf13/viper"
)

// Config 全局配置结构
type Config struct {
	Server   ServerConfig   `mapstructure:"server"`
	Database DatabaseConfig `mapstructure:"database"`
	Redis    RedisConfig    `mapstructure:"redis"`
	Claude   ClaudeConfig   `mapstructure:"claude"`
	JWT      JWTConfig      `mapstructure:"jwt"`
	Log      LogConfig      `mapstructure:"log"`
	Services ServicesConfig `mapstructure:"services"`
	Voice    VoiceConfig    `mapstructure:"voice"`
}

// VoiceConfig 语音服务配置
type VoiceConfig struct {
	// TTS 配置
	TTSEnabled     bool   `mapstructure:"tts_enabled"`
	TTSProvider    string `mapstructure:"tts_provider"`
	TTSCacheDir    string `mapstructure:"tts_cache_dir"`
	TTSDefaultLang string `mapstructure:"tts_default_lang"`

	// STT 配置
	STTEnabled     bool   `mapstructure:"stt_enabled"`
	STTProvider    string `mapstructure:"stt_provider"`
	WhisperAPIKey  string `mapstructure:"whisper_api_key"`
	WhisperModel   string `mapstructure:"whisper_model"`
	WhisperAPIURL  string `mapstructure:"whisper_api_url"`

	// 通用配置
	MaxTextLength  int `mapstructure:"max_text_length"`
	MaxAudioSize   int `mapstructure:"max_audio_size"`
	RequestTimeout int `mapstructure:"request_timeout"`
}

// ServerConfig 服务器配置
type ServerConfig struct {
	Port int    `mapstructure:"port"`
	Mode string `mapstructure:"mode"`
}

// DatabaseConfig 数据库配置
type DatabaseConfig struct {
	Host            string `mapstructure:"host"`
	Port            int    `mapstructure:"port"`
	Username        string `mapstructure:"username"`
	Password        string `mapstructure:"password"`
	Database        string `mapstructure:"database"`
	SSLMode         string `mapstructure:"sslmode"`
	MaxIdleConns    int    `mapstructure:"max_idle_conns"`
	MaxOpenConns    int    `mapstructure:"max_open_conns"`
	ConnMaxLifetime int    `mapstructure:"conn_max_lifetime"`
}

// RedisConfig Redis配置
type RedisConfig struct {
	Host     string `mapstructure:"host"`
	Port     int    `mapstructure:"port"`
	Password string `mapstructure:"password"`
	DB       int    `mapstructure:"db"`
	PoolSize int    `mapstructure:"pool_size"`
}

// ClaudeConfig Claude API配置
type ClaudeConfig struct {
	APIKey       string `mapstructure:"api_key"`
	BaseURL      string `mapstructure:"base_url"`
	DefaultModel string `mapstructure:"default_model"`
	MaxTokens    int    `mapstructure:"max_tokens"`
	Timeout      int    `mapstructure:"timeout"`
}

// JWTConfig JWT配置
type JWTConfig struct {
	Secret string `mapstructure:"secret"`
	Expire int    `mapstructure:"expire"`
}

// LogConfig 日志配置
type LogConfig struct {
	Level  string `mapstructure:"level"`
	Format string `mapstructure:"format"`
	Output string `mapstructure:"output"`
}

// ServicesConfig 服务地址配置
type ServicesConfig struct {
	BackendURL   string `mapstructure:"backend_url"`
	GeneratorURL string `mapstructure:"generator_url"`
	DeployURL    string `mapstructure:"deploy_url"`
}

var GlobalConfig *Config

// Load 加载配置
func Load(configPath string) (*Config, error) {
	v := viper.New()

	// 设置配置文件
	v.SetConfigFile(configPath)

	// 允许环境变量覆盖
	v.AutomaticEnv()

	// 读取配置
	if err := v.ReadInConfig(); err != nil {
		return nil, fmt.Errorf("读取配置文件失败: %w", err)
	}

	// 展开环境变量
	for _, key := range v.AllKeys() {
		val := v.GetString(key)
		if len(val) > 0 && val[0] == '$' {
			envKey := val[1:]
			if envVal := os.Getenv(envKey); envVal != "" {
				v.Set(key, envVal)
			}
		}
	}

	var cfg Config
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("解析配置失败: %w", err)
	}

	GlobalConfig = &cfg
	return &cfg, nil
}

// GetDSN 获取数据库连接字符串 (PostgreSQL格式)
func (c *DatabaseConfig) GetDSN() string {
	sslMode := c.SSLMode
	if sslMode == "" {
		sslMode = "disable"
	}
	return fmt.Sprintf("host=%s port=%d user=%s password=%s dbname=%s sslmode=%s",
		c.Host, c.Port, c.Username, c.Password, c.Database, sslMode)
}

// GetRedisAddr 获取Redis地址
func (c *RedisConfig) GetRedisAddr() string {
	return fmt.Sprintf("%s:%d", c.Host, c.Port)
}
