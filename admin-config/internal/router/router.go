package router

import (
	"admin-config/internal/handler"
	"admin-config/internal/service"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

// Setup 设置路由
func Setup(r *gin.Engine, db *gorm.DB) error {
	// 初始化服务
	llmService, err := service.NewLLMService(db)
	if err != nil {
		return err
	}

	gitService, err := service.NewGitService(db)
	if err != nil {
		return err
	}

	// 初始化处理器
	llmHandler := handler.NewLLMHandler(llmService)
	gitHandler := handler.NewGitHandler(gitService)

	// 健康检查
	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"status":  "ok",
			"service": "admin-config",
			"version": "1.0.0",
		})
	})

	// API路由组
	api := r.Group("/config")
	{
		// LLM配置路由
		llm := api.Group("/llm")
		{
			llm.POST("", llmHandler.Create)
			llm.GET("", llmHandler.List)
			llm.GET("/default", llmHandler.GetDefault)
			llm.GET("/:id", llmHandler.GetByID)
			llm.PUT("/:id", llmHandler.Update)
			llm.DELETE("/:id", llmHandler.Delete)
			llm.POST("/:id/test", llmHandler.TestConnection) // 测试连接
		}

		// Git配置路由
		git := api.Group("/git")
		{
			git.POST("", gitHandler.Create)
			git.GET("", gitHandler.List)
			git.GET("/default", gitHandler.GetDefault)
			git.GET("/:id", gitHandler.GetByID)
			git.PUT("/:id", gitHandler.Update)
			git.DELETE("/:id", gitHandler.Delete)
		}
	}

	return nil
}

// CORS 跨域中间件
func CORS() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Header("Access-Control-Allow-Origin", "*")
		c.Header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		c.Header("Access-Control-Allow-Headers", "Origin, Content-Type, Authorization, X-Requested-With, X-Admin-Id, X-Tenant-Id")
		c.Header("Access-Control-Expose-Headers", "Content-Length, Access-Control-Allow-Origin, Access-Control-Allow-Headers, Content-Type")
		c.Header("Access-Control-Allow-Credentials", "true")

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}

		c.Next()
	}
}
