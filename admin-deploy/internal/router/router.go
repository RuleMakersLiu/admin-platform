package router

import (
	"admin-deploy/internal/handler"

	"github.com/gin-gonic/gin"
)

// Setup 设置路由
func Setup(r *gin.Engine) {
	// 健康检查
	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "ok"})
	})

	// 部署路由
	deploy := r.Group("/deploy")
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
	}
}
