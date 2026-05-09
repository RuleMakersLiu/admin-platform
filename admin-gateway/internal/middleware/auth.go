package middleware

import (
	"admin-gateway/pkg/auth"
	"admin-gateway/pkg/cache"
	"admin-gateway/pkg/response"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/spf13/viper"
)

const (
	// 上下文键
	ContextKeyAdminID  = "adminId"
	ContextKeyUsername = "username"
	ContextKeyTenantID = "tenantId"
)

// Auth JWT认证中间件
func Auth() gin.HandlerFunc {
	return func(c *gin.Context) {
		// 放行OPTIONS请求
		if c.Request.Method == "OPTIONS" {
			c.Next()
			return
		}

		// 获取Token
		authorization := c.GetHeader("Authorization")
		if authorization == "" {
			response.Unauthorized(c, "未提供认证令牌")
			c.Abort()
			return
		}

		// 解析Bearer Token
		parts := strings.SplitN(authorization, " ", 2)
		if len(parts) != 2 || parts[0] != "Bearer" {
			response.Unauthorized(c, "认证令牌格式错误")
			c.Abort()
			return
		}

		tokenString := parts[1]

		// 验证Token
		claims, err := auth.ParseToken(tokenString)
		if err != nil {
			response.Unauthorized(c, err.Error())
			c.Abort()
			return
		}

		// 设置上下文
		c.Set(ContextKeyAdminID, claims.AdminID)
		c.Set(ContextKeyUsername, claims.Username)
		c.Set(ContextKeyTenantID, claims.TenantID)

		c.Next()
	}
}

// Permission 权限校验中间件
func Permission() gin.HandlerFunc {
	return func(c *gin.Context) {
		// 获取用户信息
		adminID, exists := c.Get(ContextKeyAdminID)
		if !exists {
			response.Unauthorized(c, "未登录")
			c.Abort()
			return
		}

		_, _ = c.Get(ContextKeyTenantID)

		// 生成权限标识
		// 参考PHP项目: app/Http/Middleware/ApiAuthAdmin.php:45-80
		// 路由: /api/admin/user/list -> 权限标识: admin_admin_user_list
		path := c.Request.URL.Path
		method := c.Request.Method

		// 跳过不需要权限校验的路径
		if skipPermissionCheck(path) {
			c.Next()
			return
		}

		permission := buildPermissionIdentifier(path, method)

		// 从Redis缓存检查权限
		ctx := c.Request.Context()
		cacheKey := "admin:permission:" + int64ToString(adminID.(int64))

		hasPermission, err := cache.SIsMember(ctx, cacheKey, permission)
		if err != nil {
			// SECURITY: Redis异常时拒绝访问（安全优先于可用性）
			response.Forbidden(c, "权限服务暂不可用，请稍后重试")
			c.Abort()
			return
		}

		// 检查是否是超级管理员（拥有所有权限）
		permissions, _ := cache.SMembers(ctx, cacheKey)
		if contains(permissions, "*") {
			c.Next()
			return
		}

		if !hasPermission {
			response.Forbidden(c, "无权访问")
			c.Abort()
			return
		}

		c.Next()
	}
}

// skipPermissionCheck 跳过权限校验的路径
func skipPermissionCheck(path string) bool {
	skipPaths := []string{
		"/api/auth/login",
		"/api/auth/logout",
		"/api/auth/refresh",
		"/api/auth/info",
		"/api/auth/menus",
		"/api/auth/tenants",
		"/api/config/",      // 配置管理（已通过 Auth 认证）
		"/api/agent/chat",   // 智能对话
		"/api/flow/",        // 智能体流程（流水线）
		"/doc.html",
		"/swagger",
		"/health",
	}

	for _, p := range skipPaths {
		if strings.HasPrefix(path, p) {
			return true
		}
	}
	return false
}

// buildPermissionIdentifier 构建权限标识
// 参考PHP项目实现
func buildPermissionIdentifier(path, method string) string {
	// 移除前缀 /api/
	path = strings.TrimPrefix(path, "/api/")
	// 替换 / 为 _
	path = strings.ReplaceAll(path, "/", "_")
	// 移除路径参数（如 :id）
	parts := strings.Split(path, "_")
	var result []string
	for _, part := range parts {
		if !strings.HasPrefix(part, ":") {
			result = append(result, part)
		}
	}
	return strings.Join(result, "_")
}

// RateLimit 限流中间件（线程安全）
func RateLimit() gin.HandlerFunc {
	var mu sync.RWMutex
	limiter := make(map[string][]time.Time)

	return func(c *gin.Context) {
		if !viper.GetBool("rate_limit.enabled") {
			c.Next()
			return
		}

		ip := c.ClientIP()
		now := time.Now()
		rps := viper.GetInt("rate_limit.requests_per_second")

		mu.Lock()

		// 清理过期记录
		if requests, exists := limiter[ip]; exists {
			var valid []time.Time
			for _, t := range requests {
				if now.Sub(t) < time.Second {
					valid = append(valid, t)
				}
			}
			limiter[ip] = valid
		}

		// 检查限流
		if len(limiter[ip]) >= rps {
			mu.Unlock()
			response.TooManyRequests(c, "请求过于频繁")
			c.Abort()
			return
		}

		limiter[ip] = append(limiter[ip], now)
		mu.Unlock()

		c.Next()
	}
}

// 辅助函数
func int64ToString(n int64) string {
	return fmt.Sprintf("%d", n)
}

func contains(slice []string, item string) bool {
	for _, s := range slice {
		if s == item {
			return true
		}
	}
	return false
}
