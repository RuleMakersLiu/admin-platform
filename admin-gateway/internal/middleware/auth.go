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

		// 生成权限标识。优先使用 module:resource:action，同时兼容旧版下划线 key。
		path := c.Request.URL.Path
		method := c.Request.Method

		// 跳过不需要权限校验的路径
		if skipPermissionCheck(path) {
			c.Next()
			return
		}

		ctx := c.Request.Context()
		cacheKey := "admin:permission:" + int64ToString(adminID.(int64))

		permissions, err := cache.SMembers(ctx, cacheKey)
		if err != nil {
			// SECURITY: Redis异常时拒绝访问（安全优先于可用性）
			response.Forbidden(c, "权限服务暂不可用，请稍后重试")
			c.Abort()
			return
		}

		// 检查是否是超级管理员（拥有所有权限）
		if contains(permissions, "*") {
			c.Next()
			return
		}

		if !hasAnyPermission(permissions, buildPermissionCandidates(path, method)) {
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
		"/api/tracking/",
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
func buildPermissionIdentifier(path, method string) string {
	candidates := buildPermissionCandidates(path, method)
	if len(candidates) == 0 {
		return ""
	}
	return candidates[0]
}

// buildPermissionCandidates returns canonical and legacy permission keys.
func buildPermissionCandidates(path, method string) []string {
	// 移除前缀 /api/
	path = strings.TrimPrefix(path, "/api/")
	parts := strings.Split(path, "/")
	var clean []string
	hadParam := false
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		if isPathParamSegment(part) {
			hadParam = true
			continue
		}
		clean = append(clean, part)
	}
	if len(clean) == 0 {
		return nil
	}

	module := clean[0]
	resource := "index"
	action := actionFromMethod(method)

	if len(clean) >= 2 {
		resource = clean[1]
	}
	if module == "system" && resource == "permission" {
		resource = "group"
		action = "list"
	}

	if module == "flow" {
		resource = "pipeline"
		if len(clean) >= 2 {
			action = clean[len(clean)-1]
		} else if method == "GET" {
			action = "list"
		}
	} else if len(clean) >= 3 {
		last := clean[len(clean)-1]
		switch last {
		case "list", "all", "tree", "options":
			action = "list"
		case "detail", "info":
			action = "view"
		case "create", "update", "edit", "delete", "remove", "save", "test", "execute", "confirm", "rollback", "default", "regenerate", "cancel":
			action = last
		default:
			if method == "GET" {
				action = "view"
			}
		}
	} else if method == "GET" && len(clean) == 2 {
		if hadParam {
			action = "view"
		} else {
			action = "list"
		}
	}

	canonical := strings.ToLower(module + ":" + resource + ":" + action)
	legacy := strings.ReplaceAll(canonical, ":", "_")
	oldPathStyle := strings.ToLower(strings.Join(clean, "_"))
	return uniqueStrings([]string{canonical, legacy, oldPathStyle})
}

func actionFromMethod(method string) string {
	switch method {
	case "GET":
		return "view"
	case "POST":
		return "create"
	case "PUT", "PATCH":
		return "edit"
	case "DELETE":
		return "delete"
	default:
		return strings.ToLower(method)
	}
}

func isPathParamSegment(part string) bool {
	if strings.HasPrefix(part, ":") {
		return true
	}
	if len(part) >= 24 && strings.Count(part, "-") >= 4 {
		return true
	}
	for _, r := range part {
		if r < '0' || r > '9' {
			return false
		}
	}
	return part != ""
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

func hasAnyPermission(granted []string, required []string) bool {
	for _, permission := range required {
		if contains(granted, permission) {
			return true
		}
	}
	return false
}

func uniqueStrings(values []string) []string {
	seen := make(map[string]bool, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		if value == "" || seen[value] {
			continue
		}
		seen[value] = true
		result = append(result, value)
	}
	return result
}
