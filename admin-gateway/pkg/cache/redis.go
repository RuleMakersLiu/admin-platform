package cache

import (
	"context"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/spf13/viper"
)

var client *redis.Client

// Init 初始化Redis客户端
func Init() error {
	client = redis.NewClient(&redis.Options{
		Addr:     viper.GetString("redis.host") + ":" + viper.GetString("redis.port"),
		Password: viper.GetString("redis.password"),
		DB:       viper.GetInt("redis.db"),
		PoolSize: viper.GetInt("redis.pool_size"),
	})

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	return client.Ping(ctx).Err()
}

// Close 关闭连接
func Close() error {
	if client != nil {
		return client.Close()
	}
	return nil
}

// GetClient 获取Redis客户端
func GetClient() *redis.Client {
	return client
}

// Get 获取值
func Get(ctx context.Context, key string) (string, error) {
	return client.Get(ctx, key).Result()
}

// Set 设置值
func Set(ctx context.Context, key string, value interface{}, expiration time.Duration) error {
	return client.Set(ctx, key, value, expiration).Err()
}

// Del 删除键
func Del(ctx context.Context, keys ...string) error {
	return client.Del(ctx, keys...).Err()
}

// SIsMember 检查集合成员
func SIsMember(ctx context.Context, key string, member interface{}) (bool, error) {
	return client.SIsMember(ctx, key, member).Result()
}

// SMembers 获取集合所有成员
func SMembers(ctx context.Context, key string) ([]string, error) {
	return client.SMembers(ctx, key).Result()
}
