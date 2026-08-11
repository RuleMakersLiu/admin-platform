package budget

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

var ErrExceeded = errors.New("trial budget exceeded")

type usage struct {
	Calls int
	Cost  float64
}

type Store interface {
	Charge(ctx context.Context, jti string, cost float64, maxCalls int, maxCost float64, ttl time.Duration) (int, float64, error)
	Revoke(ctx context.Context, jti string, ttl time.Duration) error
}

// MemoryStore is safe only for a single local instance. Production deployment
// must use the Redis-backed atomic ledger before execution can be enabled.
type MemoryStore struct {
	mu      sync.Mutex
	usage   map[string]usage
	revoked map[string]bool
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{usage: map[string]usage{}, revoked: map[string]bool{}}
}

func (s *MemoryStore) Charge(_ context.Context, jti string, cost float64, maxCalls int, maxCost float64, _ time.Duration) (int, float64, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.revoked[jti] {
		return 0, 0, errors.New("trial token revoked")
	}
	current := s.usage[jti]
	if current.Calls+1 > maxCalls || current.Cost+cost > maxCost {
		return current.Calls, current.Cost, ErrExceeded
	}
	current.Calls++
	current.Cost += cost
	s.usage[jti] = current
	return current.Calls, current.Cost, nil
}

func (s *MemoryStore) Revoke(_ context.Context, jti string, _ time.Duration) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.revoked[jti] = true
	return nil
}

type RedisStore struct{ client *redis.Client }

func NewRedisStore(address, password string, database int) *RedisStore {
	return &RedisStore{client: redis.NewClient(&redis.Options{Addr: address, Password: password, DB: database})}
}

func (s *RedisStore) Ping(ctx context.Context) error { return s.client.Ping(ctx).Err() }

var chargeScript = redis.NewScript(`
local key = KEYS[1]
if redis.call('HGET', key, 'revoked') == '1' then return {-1, 0, 0} end
local calls = tonumber(redis.call('HGET', key, 'calls') or '0')
local cost = tonumber(redis.call('HGET', key, 'cost') or '0')
local next_calls = calls + 1
local next_cost = cost + tonumber(ARGV[1])
if next_calls > tonumber(ARGV[2]) or next_cost > tonumber(ARGV[3]) then
  redis.call('HSET', key, 'revoked', '1')
  redis.call('EXPIRE', key, tonumber(ARGV[4]))
  return {0, calls, tostring(cost)}
end
redis.call('HSET', key, 'calls', next_calls, 'cost', tostring(next_cost))
redis.call('EXPIRE', key, tonumber(ARGV[4]))
return {1, next_calls, tostring(next_cost)}
`)

func (s *RedisStore) Charge(ctx context.Context, jti string, cost float64, maxCalls int, maxCost float64, ttl time.Duration) (int, float64, error) {
	seconds := int64(ttl.Seconds())
	if seconds < 1 {
		seconds = 1
	}
	value, err := chargeScript.Run(ctx, s.client, []string{"eval:budget:" + jti}, cost, maxCalls, maxCost, seconds).Slice()
	if err != nil {
		return 0, 0, fmt.Errorf("atomic budget ledger unavailable: %w", err)
	}
	if len(value) != 3 {
		return 0, 0, errors.New("invalid budget ledger response")
	}
	status, _ := strconv.ParseInt(fmt.Sprint(value[0]), 10, 64)
	calls, _ := strconv.Atoi(fmt.Sprint(value[1]))
	totalCost, _ := strconv.ParseFloat(fmt.Sprint(value[2]), 64)
	if status <= 0 {
		return calls, totalCost, ErrExceeded
	}
	return calls, totalCost, nil
}

func (s *RedisStore) Revoke(ctx context.Context, jti string, ttl time.Duration) error {
	pipe := s.client.TxPipeline()
	key := "eval:budget:" + jti
	pipe.HSet(ctx, key, "revoked", "1")
	pipe.Expire(ctx, key, ttl)
	_, err := pipe.Exec(ctx)
	return err
}
