package middleware

import (
	"net/http"
	"strings"
	"time"

	"admin-ws/internal/config"
	"admin-ws/pkg/protocol"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"go.uber.org/zap"
)

// JWTClaims JWT 声明
type JWTClaims struct {
	UserID      string   `json:"userId"`
	TenantID    string   `json:"tenantId"`
	Username    string   `json:"username"`
	Roles       []string `json:"roles"`
	Permissions []string `json:"permissions"`
	jwt.RegisteredClaims
}

// AuthMiddleware JWT 认证中间件
func AuthMiddleware(cfg *config.JWTConfig, logger *zap.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		// 从 Header 获取 token
		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			// 尝试从查询参数获取
			authHeader = c.Query("token")
			if authHeader == "" {
				c.JSON(http.StatusUnauthorized, gin.H{
					"code":    protocol.CodeUnauthorized,
					"message": "Authorization header required",
				})
				c.Abort()
				return
			}
		}

		// 解析 Bearer token
		var tokenString string
		if strings.HasPrefix(authHeader, "Bearer ") {
			tokenString = strings.TrimPrefix(authHeader, "Bearer ")
		} else {
			tokenString = authHeader
		}

		// 解析 token
		token, err := jwt.ParseWithClaims(tokenString, &JWTClaims{}, func(token *jwt.Token) (interface{}, error) {
			return []byte(cfg.Secret), nil
		})

		if err != nil {
			logger.Debug("jwt parse error", zap.Error(err))
			c.JSON(http.StatusUnauthorized, gin.H{
				"code":    protocol.CodeUnauthorized,
				"message": "Invalid token",
			})
			c.Abort()
			return
		}

		if !token.Valid {
			c.JSON(http.StatusUnauthorized, gin.H{
				"code":    protocol.CodeUnauthorized,
				"message": "Token expired or invalid",
			})
			c.Abort()
			return
		}

		claims, ok := token.Claims.(*JWTClaims)
		if !ok {
			c.JSON(http.StatusUnauthorized, gin.H{
				"code":    protocol.CodeUnauthorized,
				"message": "Invalid token claims",
			})
			c.Abort()
			return
		}

		// 将用户信息存入上下文
		c.Set("userId", claims.UserID)
		c.Set("tenantId", claims.TenantID)
		c.Set("username", claims.Username)
		c.Set("roles", claims.Roles)
		c.Set("permissions", claims.Permissions)

		c.Next()
	}
}

// CORSMiddleware CORS 中间件
func CORSMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Header("Access-Control-Allow-Origin", "*")
		c.Header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		c.Header("Access-Control-Allow-Headers", "Origin, Content-Type, Authorization")
		c.Header("Access-Control-Expose-Headers", "Content-Length, Access-Control-Allow-Origin")
		c.Header("Access-Control-Allow-Credentials", "true")

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}

		c.Next()
	}
}

// LoggerMiddleware 日志中间件
func LoggerMiddleware(logger *zap.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		path := c.Request.URL.Path
		query := c.Request.URL.RawQuery

		c.Next()

		latency := time.Since(start)
		status := c.Writer.Status()

		logger.Info("HTTP request",
			zap.Int("status", status),
			zap.String("method", c.Request.Method),
			zap.String("path", path),
			zap.String("query", query),
			zap.Duration("latency", latency),
			zap.String("ip", c.ClientIP()),
		)
	}
}

// RecoveryMiddleware 恢复中间件
func RecoveryMiddleware(logger *zap.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		defer func() {
			if err := recover(); err != nil {
				logger.Error("panic recovered",
					zap.Any("error", err),
					zap.String("path", c.Request.URL.Path))

				c.JSON(http.StatusInternalServerError, gin.H{
					"code":    protocol.CodeInternalError,
					"message": "Internal server error",
				})
				c.Abort()
			}
		}()
		c.Next()
	}
}
