package router

import (
	"admin-generator/internal/handler"

	"github.com/gin-gonic/gin"
)

// Setup 设置路由
func Setup(r *gin.Engine) {
	// 健康检查
	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "ok"})
	})

	// 生成器路由
	gen := r.Group("/generator")
	{
		// 对话生成
		gen.POST("/chat", handler.Chat)
		gen.GET("/chat/:sessionId", handler.GetChatHistory)

		// 功能配置
		gen.GET("/config", handler.ListConfig)
		gen.POST("/config", handler.CreateConfig)
		gen.GET("/config/:id", handler.GetConfig)
		gen.PUT("/config/:id", handler.UpdateConfig)
		gen.DELETE("/config/:id", handler.DeleteConfig)

		// 代码生成
		gen.POST("/generate", handler.GenerateCode)
		gen.GET("/preview/:id", handler.PreviewCode)
		gen.GET("/download/:id", handler.DownloadCode)
	}
}
