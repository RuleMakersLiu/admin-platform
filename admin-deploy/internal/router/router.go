package router

import (
	"admin-common/middleware"
	"admin-deploy/internal/handler"

	"github.com/gin-gonic/gin"
	"github.com/spf13/viper"
)

// Setup 设置路由
func Setup(r *gin.Engine) {
	// 健康检查
	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "ok"})
	})

	// 部署路由（所有操作需 JWT 鉴权，防止匿名直连触发 RCE / 容器越权操作）
	deploy := r.Group("/deploy")
	deploy.Use(middleware.AuthMiddleware(viper.GetString("jwt.secret")))
	{
		// 项目管理
		deploy.GET("/projects", handler.ListProjects)
		deploy.GET("/projects/:id", handler.GetProject)
		deploy.POST("/projects", handler.CreateProject)
		deploy.PUT("/projects/:id", handler.UpdateProject)
		deploy.DELETE("/projects/:id", handler.DeleteProject)

		// 任务管理
		deploy.GET("/tasks", handler.ListTasks)
		deploy.GET("/tasks/:id", handler.GetTask)
		deploy.POST("/tasks", handler.CreateTask)
		deploy.POST("/tasks/:id/execute", handler.ExecuteTask)
		deploy.POST("/tasks/:id/cancel", handler.CancelTask)
		deploy.GET("/tasks/:id/logs", handler.GetTaskLogs)

		// Docker管理
		deploy.GET("/containers", handler.ListContainers)
		deploy.GET("/containers/:id/logs", handler.GetContainerLogs)
		deploy.POST("/containers/:id/start", handler.StartContainer)
		deploy.POST("/containers/:id/stop", handler.StopContainer)
		deploy.DELETE("/containers/:id", handler.RemoveContainer)

		deploy.GET("/images", handler.ListImages)
		deploy.DELETE("/images/:id", handler.RemoveImage)

		// ========== 测试管理 ==========
		deploy.GET("/tests", handler.ListTestTasks)
		deploy.GET("/tests/:id", handler.GetTestTask)
		deploy.POST("/tests", handler.CreateTestTask)
		deploy.POST("/tests/:id/execute", handler.ExecuteTestTask)
		deploy.POST("/tests/:id/cancel", handler.CancelTestTask)
		deploy.GET("/tests/:id/logs", handler.GetTestTaskLogs)
	}
}
