package service

import (
	"context"

	"github.com/redis/go-redis/v9"
)

// HealthService 健康检查服务
type HealthService struct {
	redis *redis.Client
}

// NewHealthService 创建健康检查服务
func NewHealthService(redis *redis.Client) *HealthService {
	return &HealthService{redis: redis}
}

// HealthStatus 健康状态
type HealthStatus struct {
	Status    string            `json:"status"`
	Components map[string]ComponentHealth `json:"components"`
}

// ComponentHealth 组件健康状态
type ComponentHealth struct {
	Status string `json:"status"`
	Error  string `json:"error,omitempty"`
}

// Check 执行健康检查
func (s *HealthService) Check(ctx context.Context) *HealthStatus {
	status := &HealthStatus{
		Status:     "healthy",
		Components: make(map[string]ComponentHealth),
	}

	// 检查 Redis
	if s.redis != nil {
		if err := s.redis.Ping(ctx).Err(); err != nil {
			status.Components["redis"] = ComponentHealth{
				Status: "unhealthy",
				Error:  err.Error(),
			}
			status.Status = "degraded"
		} else {
			status.Components["redis"] = ComponentHealth{
				Status: "healthy",
			}
		}
	}

	return status
}
