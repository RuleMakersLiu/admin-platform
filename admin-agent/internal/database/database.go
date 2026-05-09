package database

import (
	"fmt"
	"log"
	"time"

	"admin-agent/internal/config"
	"admin-agent/internal/model"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

// InitDB 初始化数据库连接
// 使用 GORM 连接 PostgreSQL 数据库
func InitDB(cfg *config.DatabaseConfig) (*gorm.DB, error) {
	if cfg == nil {
		return nil, fmt.Errorf("数据库配置为空")
	}

	dsn := cfg.GetDSN()

	// 配置 GORM 日志级别
	var gormLogger logger.Interface
	gormLogger = logger.Default.LogMode(logger.Silent) // 生产环境静默

	// 打开数据库连接
	db, err := gorm.Open(postgres.Open(dsn), &gorm.Config{
		Logger: gormLogger,
	})
	if err != nil {
		return nil, fmt.Errorf("连接数据库失败: %w", err)
	}

	// 获取底层 SQL DB 以配置连接池
	sqlDB, err := db.DB()
	if err != nil {
		return nil, fmt.Errorf("获取数据库连接失败: %w", err)
	}

	// 配置连接池
	if cfg.MaxIdleConns > 0 {
		sqlDB.SetMaxIdleConns(cfg.MaxIdleConns)
	} else {
		sqlDB.SetMaxIdleConns(10)
	}

	if cfg.MaxOpenConns > 0 {
		sqlDB.SetMaxOpenConns(cfg.MaxOpenConns)
	} else {
		sqlDB.SetMaxOpenConns(100)
	}

	if cfg.ConnMaxLifetime > 0 {
		sqlDB.SetConnMaxLifetime(time.Duration(cfg.ConnMaxLifetime) * time.Second)
	} else {
		sqlDB.SetConnMaxLifetime(time.Hour)
	}

	// 测试连接
	if err := sqlDB.Ping(); err != nil {
		return nil, fmt.Errorf("数据库连接测试失败: %w", err)
	}

	log.Println("数据库连接成功")

	// 自动迁移表结构（仅开发环境使用）
	// 生产环境应使用独立的迁移脚本
	// AutoMigrate(db)

	return db, nil
}

// AutoMigrate 自动迁移表结构
// 仅在开发环境使用，生产环境应使用版本化的 SQL 迁移脚本
func AutoMigrate(db *gorm.DB) error {
	return db.AutoMigrate(
		&model.AgentProject{},
		&model.AgentSession{},
		&model.AgentMessage{},
		&model.AgentTask{},
		&model.AgentBug{},
		&model.AgentKnowledge{},
		&model.AgentMemory{},
		&model.AgentConfig{},
		&model.SysLLMConfig{},
		&model.FailoverLog{},
		// 技能市场相关表
		&model.Skill{},
		&model.SkillExecution{},
		&model.SkillMarket{},
		&model.SkillRating{},
		&model.SkillCategory{},
		&model.SkillDownload{},
	)
}
