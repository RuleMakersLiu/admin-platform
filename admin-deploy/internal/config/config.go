package config

import (
	"context"
	"fmt"
	"time"

	"github.com/docker/docker/api"
	"github.com/docker/docker/client"
	"github.com/spf13/viper"
	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

var (
	DB    *gorm.DB
	Docker *client.Client
)

// Load 加载配置
func Load() error {
	viper.SetConfigName("config")
	viper.SetConfigType("yaml")
	viper.AddConfigPath(".")
	viper.AddConfigPath("./config")

	viper.SetDefault("server.port", "8083")
	viper.SetDefault("database.port", 3306)

	return viper.ReadInConfig()
}

// InitDB 初始化数据库
func InitDB() error {
	dsn := fmt.Sprintf("%s:%s@tcp(%s:%d)/%s?charset=utf8mb4&parseTime=True&loc=Local",
		viper.GetString("database.user"),
		viper.GetString("database.password"),
		viper.GetString("database.host"),
		viper.GetInt("database.port"),
		viper.GetString("database.dbname"),
	)

	var err error
	DB, err = gorm.Open(mysql.Open(dsn), &gorm.Config{
		Logger: logger.Default.LogMode(logger.Info),
	})
	if err != nil {
		return err
	}

	sqlDB, err := DB.DB()
	if err != nil {
		return err
	}

	sqlDB.SetMaxIdleConns(viper.GetInt("database.max_idle_conns"))
	sqlDB.SetMaxOpenConns(viper.GetInt("database.max_open_conns"))
	sqlDB.SetConnMaxLifetime(time.Hour)

	return nil
}

// InitDocker 初始化Docker客户端
func InitDocker() error {
	var err error
	Docker, err = client.NewClientWithOpts(
		client.WithHost(viper.GetString("docker.host")),
		client.WithAPIVersionNegotiation(),
	)
	if err != nil {
		return err
	}

	// 测试连接
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	_, err = Docker.Ping(ctx)
	return err
}

// GetDB 获取数据库连接
func GetDB() *gorm.DB {
	return DB
}

// GetDocker 获取Docker客户端
func GetDocker() *client.Client {
	return Docker
}

// APIVersion 获取Docker API版本
func APIVersion() string {
	return api.DefaultVersion
}
