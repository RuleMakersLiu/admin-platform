package main

import (
	"admin-gateway/internal/config"
	"admin-gateway/internal/kafka"
	"admin-gateway/internal/router"
	"admin-gateway/pkg/cache"
	"log"

	"github.com/gin-gonic/gin"
	"github.com/spf13/viper"
)

func main() {
	// 加载配置
	if err := config.Load(); err != nil {
		log.Fatalf("加载配置失败: %v", err)
	}

	// 初始化Redis
	if err := cache.Init(); err != nil {
		log.Fatalf("初始化Redis失败: %v", err)
	}
	defer cache.Close()

	// 初始化Kafka生产者
	producer := kafka.GetProducer()
	if err := producer.Connect(); err != nil {
		log.Printf("⚠️  Kafka连接失败（埋点功能不可用）: %v", err)
	} else {
		defer producer.Close()
		log.Println("✅ Kafka连接成功")
	}

	// 设置运行模式
	gin.SetMode(viper.GetString("server.mode"))

	// 创建路由
	r := gin.New()

	// 注册路由
	router.Setup(r)

	// 启动服务
	port := viper.GetString("server.port")
	log.Printf("网关服务启动，监听端口: %s", port)
	if err := r.Run(":" + port); err != nil {
		log.Fatalf("启动服务失败: %v", err)
	}
}
