# Redis缓存策略设计

## 1. 缓存架构

### 1.1 Redis部署方案
- **模式**: 单机 (开发) / 主从 + 哨兵 (生产)
- **内存**: 4GB+
- **持久化**: RDB + AOF混合
- **用途**: 
  - 缓存层 (热点数据)
  - 会话存储
  - WebSocket连接信息
  - 消息队列 (可选)

---

## 2. 数据结构设计

### 2.1 智能体状态缓存

#### Hash: 智能体详情
```
Key: agent:{agent_id}
Type: Hash
TTL: 5分钟
Fields:
  - id: 智能体ID
  - name: 名称
  - role: 角色
  - status: 状态
  - workload: 负载
  - current_task_id: 当前任务ID
  - last_heartbeat: 最后心跳时间
  - updated_at: 更新时间
```

#### Set: 各状态的智能体集合
```
Key: agents:status:{working|idle|offline}
Type: Set
TTL: 无 (通过定时任务维护)
用途: 快速查询某状态的所有智能体
```

#### ZSet: 智能体负载排行
```
Key: agents:workload:ranking
Type: Sorted Set
Score: workload
Member: agent_id
用途: 按负载排序,用于任务分配
```

### 2.2 任务状态缓存

#### Hash: 任务详情
```
Key: task:{task_id}
Type: Hash
TTL: 1小时
Fields:
  - id: 任务ID
  - title: 标题
  - status: 状态
  - priority: 优先级
  - progress: 进度
  - assigned_agents: JSON字符串
  - created_at: 创建时间
```

#### List: 待处理任务队列
```
Key: tasks:pending:queue
Type: List
用途: FIFO任务队列
```

#### Sorted Set: 优先级任务队列
```
Key: tasks:priority:queue
Type: Sorted Set
Score: 优先级权重 (urgent:100, high:75, medium:50, low:25)
Member: task_id
用途: 按优先级调度任务
```

### 2.3 协作记录缓存

#### List: 最近协作记录
```
Key: collaborations:recent:{agent_id}
Type: List
Length: 100
TTL: 24小时
用途: 存储智能体最近的协作记录
```

#### Hash: 任务协作时间线
```
Key: task:timeline:{task_id}
Type: Hash
Field: timestamp
Value: JSON字符串
TTL: 1天
```

### 2.4 看板数据缓存

#### String: 看板全景数据
```
Key: dashboard:data
Type: String (JSON)
TTL: 5秒
更新策略: 定时任务每5秒刷新
内容:
  - 所有智能体状态
  - 进行中的任务
  - 统计数据
```

### 2.5 WebSocket连接管理

#### Hash: 连接映射
```
Key: ws:connections
Type: Hash
Field: fd (连接描述符)
Value: JSON {user_id, connected_at, rooms}
```

#### Hash: 房间成员
```
Key: ws:rooms
Type: Hash
Field: room_name
Value: JSON [fd1, fd2, ...]
```

#### String: 房间消息计数
```
Key: ws:room:message:count:{room_name}
Type: String
用途: 监控房间活跃度
```

---

## 3. 缓存策略

### 3.1 缓存更新模式

#### Cache-Aside (旁路缓存)
```
读流程:
1. 查询Redis缓存
2. 缓存命中 -> 直接返回
3. 缓存未命中 -> 查询MySQL -> 写入Redis -> 返回

写流程:
1. 更新MySQL
2. 删除Redis缓存 (或更新)
```

#### Write-Through (写穿透)
```
用于高频更新的数据 (如智能体状态):
1. 更新Redis缓存
2. 异步写入MySQL (通过消息队列)
```

### 3.2 缓存过期策略

| 数据类型 | Key模式 | TTL | 更新触发 |
|---------|---------|-----|---------|
| 智能体详情 | agent:{id} | 5分钟 | 状态变更时 |
| 任务详情 | task:{id} | 1小时 | 任务更新时 |
| 看板数据 | dashboard:data | 5秒 | 定时任务 |
| WebSocket连接 | ws:* | 无 | 连接关闭时 |
| 协作记录 | collaborations:* | 24小时 | 新记录时 |

### 3.3 缓存预热

#### 启动时预热
```php
// 在服务启动时加载热点数据
php artisan cache:warmup

// 预热内容:
1. 所有智能体状态
2. 进行中的任务
3. 最近1小时的协作记录
4. 看板统计数据
```

### 3.4 缓存穿透防护

#### 空值缓存
```
如果查询不存在的数据,缓存null值,有效期5分钟
```

#### 布隆过滤器
```
使用RedisBloom模块,过滤不存在的智能体ID/任务ID
```

### 3.5 缓存雪崩防护

#### 随机过期时间
```
TTL = base_ttl + random(0, 300秒)
```

#### 互斥锁
```php
// 获取锁
$lock = Redis::set('lock:dashboard:data', 1, 'NX', 'EX', 10);

if ($lock) {
    // 重建缓存
    $data = $this->buildDashboardData();
    Redis::setex('dashboard:data', 5, json_encode($data));
}
```

### 3.6 缓存击穿防护

#### 热点数据永不过期
```
逻辑过期时间 + 异步刷新
```

---

## 4. 缓存更新流程

### 4.1 智能体状态更新

```
1. 智能体调用API更新状态
2. Controller更新MySQL
3. 触发Observer事件
4. Observer执行:
   a. 更新Redis Hash (agent:{id})
   b. 更新状态集合 (agents:status:{status})
   c. 发布到Redis频道 (agent_updates)
5. WebSocket订阅频道,收到消息后广播
```

### 4.2 任务状态更新

```
1. 任务状态变更
2. 更新MySQL
3. 更新Redis缓存:
   a. task:{id} (任务详情)
   b. 从旧状态集合移除
   c. 加入新状态集合
4. 发布到task_updates频道
5. WebSocket广播
```

### 4.3 协作记录创建

```
1. 创建协作记录
2. 写入MySQL
3. 更新Redis:
   a. LPUSH collaborations:recent:{agent_id}
   b. LTRIM保留最近100条
   c. HSET task:timeline:{task_id}
4. 发布协作事件
```

---

## 5. 数据同步策略

### 5.1 MySQL -> Redis 同步

#### 实时同步 (Observer模式)
```php
// AgentObserver.php
public function updated(Agent $agent)
{
    // 更新Redis
    Redis::hmset("agent:{$agent->id}", $agent->toArray());
    
    // 发布事件
    Redis::publish('agent_updates', json_encode([
        'agent_id' => $agent->id,
        'status' => $agent->status,
        'workload' => $agent->workload,
    ]));
}
```

#### 定时同步 (Cron)
```php
// 每小时全量同步
Schedule::call(function () {
    // 同步所有智能体状态
    Agent::chunk(100, function ($agents) {
        foreach ($agents as $agent) {
            Redis::hmset("agent:{$agent->id}", $agent->toArray());
        }
    });
})->hourly();
```

### 5.2 Redis -> MySQL 回填

#### 异步持久化
```
高频率变更的数据(如workload)先写Redis,
定时任务批量回写到MySQL
```

---

## 6. 缓存监控

### 6.1 监控指标

```bash
# 内存使用率
redis-cli info memory | grep used_memory_percent

# 缓存命中率
redis-cli info stats | grep keyspace_hits_rate

# 连接数
redis-cli info clients | grep connected_clients

# 慢查询
redis-cli slowlog get 10
```

### 6.2 监控命令

```php
// Laravel中监控
Cache::store('redis')->getRedis()->info();
```

---

## 7. Redis发布订阅

### 7.1 频道定义

| 频道名 | 用途 | 消息格式 |
|-------|------|---------|
| agent_updates | 智能体状态更新 | {agent_id, status, ...} |
| task_updates | 任务状态更新 | {task_id, status, ...} |
| collaboration_events | 协作事件 | {record_id, action, ...} |
| broadcast | 全局广播 | {message, ...} |

### 7.2 订阅示例

```php
// 在Swoole Worker中订阅
$redis = new Swoole\Coroutine\Redis();
$redis->connect('127.0.0.1', 6379);
$redis->subscribe(['agent_updates', 'task_updates'], function ($redis, $channel, $message) {
    $data = json_decode($message, true);
    // 处理并广播到WebSocket
});
```

---

## 8. 性能优化建议

### 8.1 Pipeline优化

```php
// 批量操作使用Pipeline
Redis::pipeline(function ($pipe) {
    foreach ($agents as $agent) {
        $pipe->hmset("agent:{$agent->id}", $agent->toArray());
    }
});
```

### 8.2 Lua脚本

```lua
-- 原子更新智能体状态
local agentKey = KEYS[1]
local statusSet = KEYS[2]
local oldStatus = ARGV[1]
local newStatus = ARGV[2]

redis.call('HSET', agentKey, 'status', newStatus)
redis.call('SREM', statusSet .. oldStatus, agentKey)
redis.call('SADD', statusSet .. newStatus, agentKey)

return 1
```

### 8.3 连接池

```php
// Swoole协程连接池
$pool = new Swoole\Database\RedisPool(
    (new Swoole\Database\RedisConfig)
        ->withHost('127.0.0.1')
        ->withPort(6379)
);
```

---

## 9. 容灾方案

### 9.1 主从切换

```
1. 使用Redis Sentinel监控
2. 主节点故障自动切换
3. 应用层通过Sentinel获取新主节点地址
```

### 9.2 数据备份

```bash
# RDB备份 (每小时)
redis-cli BGSAVE

# AOF备份 (实时)
appendonly yes
```

### 9.3 缓存降级

```php
// Redis不可用时降级到直接查MySQL
try {
    $data = Redis::get('dashboard:data');
} catch (\Exception $e) {
    Log::error('Redis connection failed', ['error' => $e->getMessage()]);
    $data = $this->getFromDatabase();
}
```

---

## 10. Redis配置建议

```conf
# redis.conf

# 内存设置
maxmemory 4gb
maxmemory-policy allkeys-lru

# 持久化
save 900 1
save 300 10
save 60 10000
appendonly yes
appendfsync everysec

# 网络
tcp-keepalive 300
timeout 0

# 性能
tcp-backlog 511
```

---

## 11. 常用命令速查

```bash
# 清空所有缓存
redis-cli FLUSHDB

# 查看所有智能体状态
redis-cli KEYS "agent:*"

# 查看房间成员
redis-cli HGET ws:rooms dashboard

# 监控实时命令
redis-cli MONITOR

# 查看内存使用
redis-cli MEMORY USAGE agent:uuid
```
