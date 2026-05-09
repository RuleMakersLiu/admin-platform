package router

import (
	"admin-gateway/internal/handler"
	"admin-gateway/internal/middleware"

	"github.com/gin-gonic/gin"
)

// Setup 设置路由
func Setup(r *gin.Engine) {
	// 中间件
	r.Use(gin.Recovery())
	r.Use(gin.Logger())
	r.Use(middleware.RateLimit())
	r.Use(CORS())

	// 健康检查
	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "ok"})
	})

	// WebSocket连接（需要认证）
	wsGroup := r.Group("/ws")
	wsGroup.Use(middleware.Auth())
	{
		wsGroup.GET("/connect", handler.ProxyWebSocket)
	}

	// API路由组
	api := r.Group("/api")
	{
		// 埋点服务（不需要认证，可选认证）
		trackingGroup := api.Group("/tracking")
		{
			trackingGroup.POST("/events", handler.TrackEvents)          // 批量事件
			trackingGroup.POST("/event", handler.TrackSingleEvent)      // 单个事件
			trackingGroup.GET("/health", handler.TrackingHealth)        // 健康检查
			trackingGroup.GET("/device-id", handler.GetDeviceID)        // 获取设备ID
		}

		// 认证相关（不需要权限校验）
		api.POST("/auth/login", handler.ProxyToPython)
		api.POST("/auth/logout", handler.ProxyToPython)
		api.GET("/auth/tenants", handler.ProxyToPython) // 获取租户列表（公开）

		// 需要认证的路由
		authGroup := api.Group("")
		authGroup.Use(middleware.Auth())
		{
			// 用户信息（不需要权限校验）
			authGroup.GET("/auth/info", handler.ProxyToPython)
			authGroup.GET("/auth/menus", handler.ProxyToPython)

			// 需要权限校验的路由
			protected := authGroup.Group("")
			protected.Use(middleware.Permission())
			{
				// 系统管理 -> Python后端
				protected.Any("/system/*action", handler.ProxyToPython)

				// 智能分身 -> Python后端
				protected.Any("/agent/*action", handler.ProxyToPython)

				// 智能体流程（流水线） -> Python后端
				protected.Any("/flow/*action", handler.ProxyToPython)

				// 代码生成
				protected.Any("/generator/*action", handler.ProxyToGenerator)

				// 部署管理
				protected.Any("/deploy/*action", handler.ProxyToDeploy)

				// 配置管理
				protected.Any("/config/*action", handler.ProxyToConfig)

				// WebSocket服务HTTP API
				protected.Any("/ws/*action", handler.ProxyToWS)
			}
		}
	}
}

// CORS 跨域中间件
func CORS() gin.HandlerFunc {
	return func(c *gin.Context) {
		// SECURITY: 使用白名单替代通配符
		origin := c.GetHeader("Origin")
		allowedOrigins := []string{"http://localhost:3000", "http://localhost:3001"}
		for _, o := range allowedOrigins {
			if origin == o {
				c.Header("Access-Control-Allow-Origin", origin)
				break
			}
		}
		c.Header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		c.Header("Access-Control-Allow-Headers", "Origin, Content-Type, Authorization, X-Requested-With")
		c.Header("Access-Control-Expose-Headers", "Content-Length, Access-Control-Allow-Origin, Access-Control-Allow-Headers, Content-Type")
		c.Header("Access-Control-Allow-Credentials", "true")

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}

		c.Next()
	}
}
