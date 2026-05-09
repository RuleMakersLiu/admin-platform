package main

import (
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"

	"admin-config/internal/config"
	"admin-config/internal/router"

	"github.com/gin-gonic/gin"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

func main() {
	// 加载配置
	configPath := os.Getenv("CONFIG_PATH")
	cfg, err := config.Load(configPath)
	if err != nil {
		log.Printf("警告: 加载配置失败(%v)，使用默认配置", err)
	}

	// 初始化数据库
	var db *gorm.DB
	if cfg != nil {
		db, err = initDB(cfg)
		if err != nil {
			log.Fatalf("数据库连接失败: %v", err)
		}
		log.Println("数据库连接成功")
	}

	// 设置Gin模式
	if cfg != nil && cfg.Server.Mode != "" {
		gin.SetMode(cfg.Server.Mode)
	} else {
		gin.SetMode(gin.DebugMode)
	}

	// 创建Gin引擎
	engine := gin.New()
	engine.Use(gin.Recovery())
	engine.Use(gin.Logger())
	engine.Use(router.CORS())

	// 设置路由
	if err := router.Setup(engine, db); err != nil {
		log.Fatalf("路由设置失败: %v", err)
	}

	// 获取端口
	port := 8085
	if cfg != nil && cfg.Server.Port != 0 {
		port = cfg.Server.Port
	}

	// 启动服务
	addr := fmt.Sprintf(":%d", port)
	go func() {
		log.Printf("Admin Config 服务启动，监听端口 %d", port)
		if err := engine.Run(addr); err != nil {
			log.Fatalf("服务启动失败: %v", err)
		}
	}()

	// 优雅关闭
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("服务正在关闭...")
	log.Println("服务已关闭")
}

// initDB 初始化数据库连接
func initDB(cfg *config.Config) (*gorm.DB, error) {
	dsn := cfg.Database.GetDSN()
	db, err := gorm.Open(postgres.Open(dsn), &gorm.Config{})
	if err != nil {
		return nil, err
	}

	// 获取底层SQL DB
	sqlDB, err := db.DB()
	if err != nil {
		return nil, err
	}

	// 设置连接池
	sqlDB.SetMaxIdleConns(cfg.Database.MaxIdleConns)
	sqlDB.SetMaxOpenConns(cfg.Database.MaxOpenConns)
	// sqlDB.SetConnMaxLifetime(time.Duration(cfg.Database.ConnMaxLifetime) * time.Second)

	return db, nil
}
