package router

import (
	"admin-common/middleware"
	"admin-generator/internal/handler"

	"github.com/gin-gonic/gin"
	"github.com/spf13/viper"
)

// Setup 设置路由
func Setup(r *gin.Engine) {
	// 健康检查
	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "ok"})
	})

	// 生成器路由（需 JWT 鉴权）
	gen := r.Group("/generator")
	gen.Use(middleware.AuthMiddleware(viper.GetString("jwt.secret")))
	{
		// 对话生成（保留原有）
		gen.POST("/chat", handler.Chat)
		gen.GET("/chat/:sessionId", handler.GetChatHistory)

		// 功能配置（保留原有）
		gen.GET("/config", handler.ListConfig)
		gen.POST("/config", handler.CreateConfig)
		gen.GET("/config/:id", handler.GetConfig)
		gen.PUT("/config/:id", handler.UpdateConfig)
		gen.DELETE("/config/:id", handler.DeleteConfig)

		// 代码生成（保留原有）
		gen.POST("/generate", handler.GenerateCode)
		gen.GET("/preview/:id", handler.PreviewCode)
		gen.GET("/download/:id", handler.DownloadCode)

		// ========== 新增：项目模板 ==========
		gen.GET("/templates", handler.ListTemplates)
		gen.GET("/templates/:id", handler.GetTemplate)
		gen.POST("/templates", handler.CreateTemplate)
		gen.PUT("/templates/:id", handler.UpdateTemplate)
		gen.DELETE("/templates/:id", handler.DeleteTemplate)
		gen.GET("/languages", handler.ListLanguages)

		// ========== 新增：项目生成 ==========
		gen.GET("/projects", handler.ListProjects)
		gen.POST("/projects", handler.CreateProject)
		gen.POST("/projects/import", handler.ImportProject)
		gen.GET("/projects/:id", handler.GetProject)
		gen.PUT("/projects/:id", handler.UpdateProject)
		gen.DELETE("/projects/:id", handler.DeleteProject)
		gen.GET("/projects/:id/preview", handler.PreviewProject)
		gen.GET("/projects/:id/download", handler.DownloadProject)
		gen.POST("/projects/:id/regenerate", handler.RegenerateProject)
		gen.GET("/projects/:id/test-config", handler.GetProjectTestConfig)
	}
}
