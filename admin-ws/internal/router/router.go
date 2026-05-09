package router

import (
	"admin-ws/internal/config"
	"admin-ws/internal/handler"
	"admin-ws/internal/hub"
	"admin-ws/internal/middleware"
	"admin-ws/internal/service"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

// Setup 设置路由
func Setup(
	cfg *config.Config,
	h *hub.Hub,
	agentService *service.AgentService,
	healthService *service.HealthService,
	logger *zap.Logger,
) *gin.Engine {
	gin.SetMode(cfg.Server.Mode)

	r := gin.New()

	r.Use(middleware.CORSMiddleware())
	r.Use(middleware.LoggerMiddleware(logger))
	r.Use(middleware.RecoveryMiddleware(logger))

	wsHandler := handler.NewWebSocketHandler(h, &cfg.WebSocket, logger)
	httpHandler := handler.NewHTTPHandler(h)

	// 健康检查（无需认证）
	r.GET("/health", func(c *gin.Context) {
		status := healthService.Check(c.Request.Context())
		c.JSON(200, gin.H{
			"code":    0,
			"message": "success",
			"data":    status,
		})
	})

	// WebSocket 端点（需要认证）
	wsGroup := r.Group("/ws")
	wsGroup.Use(middleware.AuthMiddleware(&cfg.JWT, logger))
	{
		wsGroup.GET("/connect", wsHandler.HandleWebSocket)
	}

	// API 端点
	apiGroup := r.Group("/api")
	apiGroup.Use(middleware.AuthMiddleware(&cfg.JWT, logger))
	{
		apiGroup.GET("/stats", httpHandler.GetStats)
		apiGroup.GET("/clients", httpHandler.GetClients)
		apiGroup.GET("/rooms", httpHandler.GetRooms)
		apiGroup.GET("/rooms/:id", httpHandler.GetRoomInfo)
		apiGroup.POST("/broadcast", httpHandler.Broadcast)
	}

	// 内部 API（供其他服务调用）
	internalGroup := r.Group("/internal")
	{
		internalGroup.POST("/broadcast", httpHandler.Broadcast)
		internalGroup.POST("/agent/callback", httpHandler.HandleAgentCallback)
	}

	return r
}
