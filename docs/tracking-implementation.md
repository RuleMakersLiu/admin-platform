# 埋点系统实现文档

## 概述

本埋点系统采用**Go网关 + Kafka + Python消费者 + ClickHouse**的架构，支持高性能、可扩展的用户行为数据采集和分析。

## 架构设计

```
前端/客户端
    ↓ (HTTP POST)
Go网关 (admin-gateway)
    ↓ (Kafka Producer)
Kafka Topic: tracking-events
    ↓ (Kafka Consumer)
Python消费服务 (admin-python)
    ↓ (批量写入)
ClickHouse (analytics.tracking_events)
```

## 技术栈

- **Go网关**: Gin + Sarama (Kafka客户端)
- **Kafka**: 消息队列，解耦和缓冲
- **Python服务**: aiokafka + asynch (ClickHouse客户端)
- **ClickHouse**: 列式数据库，高性能分析查询

## 部署步骤

### 1. 安装依赖

#### Go网关依赖
```bash
cd /home/pastorlol/admin-platform/admin-gateway
go mod tidy
```

#### Python服务依赖
```bash
cd /home/pastorlol/admin-platform/admin-python
pip install aiokafka asynch
```

### 2. 配置环境变量

#### Go网关配置 (config.yaml)
```yaml
kafka:
  brokers:
    - localhost:9092
  topic: tracking-events
  queue_size: 10000
  batch_size: 100
  flush_period_ms: 100
```

#### Python服务配置 (.env)
```bash
# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TRACKING_TOPIC=tracking-events
KAFKA_TRACKING_GROUP=tracking-consumer

# ClickHouse
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=9000
CLICKHOUSE_DATABASE=analytics
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=
```

### 3. 启动基础设施

#### 启动Kafka (使用Docker)
```bash
# Zookeeper
docker run -d --name zookeeper \
  -p 2181:2181 \
  confluentinc/cp-zookeeper:latest

# Kafka
docker run -d --name kafka \
  -p 9092:9092 \
  -e KAFKA_ZOOKEEPER_CONNECT=zookeeper:2181 \
  -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092 \
  -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
  confluentinc/cp-kafka:latest
```

#### 启动ClickHouse
```bash
docker run -d --name clickhouse \
  -p 9000:9000 \
  -p 8123:8123 \
  clickhouse/clickhouse-server
```

### 4. 创建Kafka Topic
```bash
# 进入Kafka容器
docker exec -it kafka bash

# 创建Topic
kafka-topics --create \
  --bootstrap-server localhost:9092 \
  --topic tracking-events \
  --partitions 3 \
  --replication-factor 1
```

### 5. 启动服务

#### 启动Go网关
```bash
cd /home/pastorlol/admin-platform/admin-gateway
go run cmd/main.go
```

#### 启动Python消费服务
```bash
cd /home/pastorlol/admin-platform/admin-python

# 方式1: 作为独立进程运行
python -m app.services.tracking_worker

# 方式2: 集成到FastAPI应用中（在main.py中启动）
# 参见下方的"集成到FastAPI"章节
```

## API使用说明

### 1. 批量上报事件

**请求**
```http
POST /api/tracking/events
Content-Type: application/json

{
  "events": [
    {
      "event_type": "page_view",
      "event_name": "home_page",
      "timestamp": 1710000000000,
      "user_id": "user123",
      "session_id": "session456",
      "page_url": "https://example.com/home",
      "page_title": "首页",
      "properties": {
        "button_color": "blue",
        "ab_test_group": "A"
      }
    },
    {
      "event_type": "click",
      "event_name": "submit_button",
      "timestamp": 1710000001000,
      "user_id": "user123",
      "session_id": "session456",
      "page_url": "https://example.com/home",
      "properties": {
        "button_text": "提交"
      }
    }
  ]
}
```

**响应**
```json
{
  "code": 200,
  "message": "Success",
  "data": {
    "success": 2,
    "failed": 0,
    "errors": []
  }
}
```

### 2. 单个事件上报

**请求**
```http
POST /api/tracking/event
Content-Type: application/json

{
  "event_type": "api_call",
  "event_name": "get_user_info",
  "timestamp": 1710000000000,
  "user_id": "user123"
}
```

**响应**
```json
{
  "code": 200,
  "message": "Success",
  "data": {
    "event_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

### 3. 健康检查

**请求**
```http
GET /api/tracking/health
```

**响应**
```json
{
  "code": 200,
  "message": "Success",
  "data": {
    "status": "healthy",
    "kafka_connected": true,
    "queue_size": 0,
    "processed_count": 1234,
    "failed_count": 0,
    "last_process_time": "2024-03-14T00:00:00Z",
    "version": "1.0.0"
  }
}
```

## 事件模型

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| event_id | string | 否 | 事件ID（自动生成UUID） |
| event_type | string | 是 | 事件类型（page_view, click, api_call等） |
| event_name | string | 是 | 事件名称 |
| timestamp | int64 | 是 | 事件时间戳（毫秒） |
| platform | string | 否 | 平台（web, app, mini_program） |
| version | string | 否 | 应用版本 |
| user_id | string | 否 | 用户ID（已登录） |
| device_id | string | 否 | 设备ID（未登录用户） |
| session_id | string | 否 | 会话ID |
| tenant_id | string | 否 | 租户ID |
| admin_id | string | 否 | 管理员ID |
| username | string | 否 | 用户名 |
| user_type | string | 否 | 用户类型（admin, user, guest） |
| device_type | string | 否 | 设备类型（mobile, desktop, tablet） |
| os | string | 否 | 操作系统 |
| os_version | string | 否 | 操作系统版本 |
| browser | string | 否 | 浏览器 |
| browser_version | string | 否 | 浏览器版本 |
| screen_width | int | 否 | 屏幕宽度 |
| screen_height | int | 否 | 屏幕高度 |
| language | string | 否 | 语言 |
| ip | string | 否 | IP地址 |
| country | string | 否 | 国家 |
| province | string | 否 | 省份 |
| city | string | 否 | 城市 |
| page_url | string | 否 | 页面URL |
| page_title | string | 否 | 页面标题 |
| referrer | string | 否 | 来源页面 |
| page_duration | int64 | 否 | 页面停留时长（毫秒） |
| properties | object | 否 | 自定义属性 |
| source | string | 否 | 来源（sdk, api, batch） |
| user_agent | string | 否 | User-Agent |

### 自动填充字段

以下字段会由网关自动填充：
- **event_id**: 如果未提供，自动生成UUID
- **timestamp**: 如果未提供，使用当前时间
- **ip**: 从请求中提取
- **user_agent**: 从请求头中提取
- **os/browser/device_type**: 解析User-Agent
- **admin_id/username/tenant_id**: 从认证信息中提取（如果有）

## 数据分析查询

### 1. 按事件类型统计

```python
from app.services.tracking_analyzer import get_tracking_analyzer
from datetime import datetime, timedelta

analyzer = await get_tracking_analyzer()

# 统计最近7天的事件数量
end_time = datetime.now()
start_time = end_time - timedelta(days=7)

event_counts = await analyzer.get_event_count_by_type(
    tenant_id="tenant123",
    start_time=start_time,
    end_time=end_time
)

# 返回: {"page_view": 10000, "click": 5000, "api_call": 3000}
```

### 2. 获取DAU

```python
dau_data = await analyzer.get_daily_active_users(
    tenant_id="tenant123",
    start_date=start_time,
    end_date=end_time
)

# 返回: [{"date": "2024-03-01", "dau": 1234}, ...]
```

### 3. 页面浏览量统计

```python
page_views = await analyzer.get_page_views_by_url(
    tenant_id="tenant123",
    start_time=start_time,
    end_time=end_time,
    limit=100
)

# 返回: [{"page_url": "/home", "page_views": 5000, "unique_visitors": 3000}, ...]
```

### 4. 用户留存率

```python
retention = await analyzer.get_user_retention(
    tenant_id="tenant123",
    cohort_date=datetime(2024, 3, 1)
)

# 返回: {"day_1": 45.5, "day_3": 30.2, "day_7": 20.1}
```

### 5. 设备分布

```python
device_dist = await analyzer.get_device_distribution(
    tenant_id="tenant123",
    start_time=start_time,
    end_time=end_time
)

# 返回: {"desktop": 5000, "mobile": 3000, "tablet": 1000}
```

## 集成到FastAPI

### 方式1: 作为后台任务启动

编辑 `app/main.py`:

```python
from contextlib import asynccontextmanager
from app.services.tracking_worker import start_tracking_worker, stop_tracking_worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info(f"🚀 {settings.app_name} v{settings.app_version} 启动中...")
    
    # 启动埋点消费服务（作为后台任务）
    asyncio.create_task(start_tracking_worker())
    logger.info("✅ 埋点消费服务启动中...")
    
    yield
    
    # 关闭时
    await stop_tracking_worker()
    logger.info(f"👋 {settings.app_name} 关闭中...")

app = FastAPI(lifespan=lifespan)
```

### 方式2: 独立进程运行

```bash
# 使用systemd管理
sudo systemctl start tracking-worker

# 或使用supervisor
supervisorctl start tracking-worker
```

## 性能优化

### 1. Kafka配置优化

- **批量大小**: 100-1000条
- **刷新间隔**: 100-500ms
- **压缩**: Snappy压缩
- **分区数**: 根据并发量调整（建议3-10）

### 2. ClickHouse优化

- **批量写入**: 1000-10000条/批
- **分区策略**: 按月分区
- **索引设计**: (tenant_id, event_type, timestamp)
- **物化视图**: 预聚合常用查询

### 3. 连接池

- Kafka: 保持长连接
- ClickHouse: 使用连接池

## 监控指标

### 1. Go网关指标

- `kafka_queue_size`: 队列大小
- `kafka_processed_count`: 已处理事件数
- `kafka_failed_count`: 失败事件数
- `kafka_last_process_time`: 最后处理时间

### 2. Python消费者指标

- `consumer_processed_count`: 已消费事件数
- `consumer_failed_count`: 失败事件数
- `clickhouse_insert_count`: ClickHouse插入数

### 3. ClickHouse指标

- 表大小
- 行数
- 查询性能

## 故障排查

### Kafka连接失败
```bash
# 检查Kafka状态
docker logs kafka

# 测试连接
kafka-topics --bootstrap-server localhost:9092 --list
```

### ClickHouse连接失败
```bash
# 检查ClickHouse状态
docker logs clickhouse

# 测试连接
clickhouse-client --host localhost --port 9000
```

### 查看消费延迟
```bash
# 查看消费者组状态
kafka-consumer-groups --bootstrap-server localhost:9092 \
  --describe --group tracking-consumer
```

## 扩展功能

### 1. 实时看板
可以基于ClickHouse创建实时数据看板：
- 实时UV/PV
- 热门页面TOP10
- 地域分布
- 设备分布

### 2. 告警规则
基于埋点数据设置告警：
- 异常流量告警
- 接口错误率告警
- 用户流失告警

### 3. A/B测试
利用properties字段记录实验分组：
```json
{
  "properties": {
    "ab_test_id": "homepage_redesign",
    "ab_test_group": "B",
    "variant": "new_layout"
  }
}
```

## 安全考虑

1. **数据脱敏**: 网关自动脱敏敏感参数（token, password等）
2. **权限控制**: 分析查询需要租户隔离
3. **数据保留**: 设置合理的数据保留期（如90天）
4. **访问日志**: 记录所有分析查询

## 下一步

1. ✅ 实现基础埋点采集
2. ✅ 实现Kafka集成
3. ✅ 实现ClickHouse写入
4. ✅ 实现基础分析查询
5. ⏳ 添加实时看板
6. ⏳ 添加告警系统
7. ⏳ 优化查询性能
8. ⏳ 添加数据导出功能

## 常见问题

**Q: 为什么要用Kafka而不是直接写ClickHouse？**
A: Kafka提供缓冲和削峰填谷，避免高并发时压垮数据库，同时支持多消费者扩展。

**Q: ClickHouse vs Elasticsearch？**
A: ClickHouse更适合OLAP分析查询，性能更高；ES更适合全文搜索。埋点场景推荐ClickHouse。

**Q: 如何保证数据不丢失？**
A: Kafka配置`acks=all`，Python消费者手动提交offset，ClickHouse批量写入。

**Q: 如何处理突发流量？**
A: Kafka队列缓冲 + ClickHouse批量写入 + 自动扩容消费者。
