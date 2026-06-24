// Package middleware provides shared gin middleware reused across admin-*
// services. It lives in the admin-common module so every Go service can depend
// on a single, consistent JWT verification implementation instead of each
// service rolling its own.
package middleware

import (
	"fmt"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
)

// AuthMiddleware returns a gin middleware that verifies the HS256 JWT carried in
// the Authorization: Bearer header (or ?token= query param) against `secret`.
// On success it injects adminId / tenantId into the gin context for handlers.
// Empty secret => 503 (service misconfigured), so a missing JWT_SECRET fails loudly.
func AuthMiddleware(secret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		if secret == "" {
			c.AbortWithStatusJSON(http.StatusServiceUnavailable, gin.H{
				"code": 503, "message": "JWT secret not configured",
			})
			return
		}

		authHeader := c.GetHeader("Authorization")
		tokenString := strings.TrimPrefix(authHeader, "Bearer ")
		if tokenString == authHeader || tokenString == "" {
			// fall back to query param (e.g. WebSocket-style clients)
			tokenString = c.Query("token")
		}
		if tokenString == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
				"code": 401, "message": "authorization required",
			})
			return
		}

		token, err := jwt.ParseWithClaims(tokenString, jwt.MapClaims{}, func(t *jwt.Token) (interface{}, error) {
			// Reject alg=none / algorithm-confusion attacks: only HMAC is valid.
			if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
			}
			return []byte(secret), nil
		})

		if err != nil || !token.Valid {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
				"code": 401, "message": "invalid or expired token",
			})
			return
		}

		if claims, ok := token.Claims.(jwt.MapClaims); ok {
			c.Set("adminId", claims["adminId"])
			c.Set("tenantId", claims["tenantId"])
			c.Set("username", claims["username"])
		}
		c.Next()
	}
}

// AdminID extracts the admin id injected by AuthMiddleware (0 if absent).
func AdminID(c *gin.Context) int64 {
	v, _ := c.Get("adminId")
	switch n := v.(type) {
	case float64:
		return int64(n)
	case int64:
		return n
	case int:
		return int64(n)
	}
	return 0
}

// TenantID extracts the tenant id injected by AuthMiddleware (0 if absent).
func TenantID(c *gin.Context) int64 {
	v, _ := c.Get("tenantId")
	switch n := v.(type) {
	case float64:
		return int64(n)
	case int64:
		return n
	case int:
		return int64(n)
	}
	return 0
}
