# Admin WebSocket Gateway

WebSocket 网关服务，提供实时双向通信能力。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                  WebSocket Gateway (8086)                │
├─────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │
│  │  Auth   │  │   Hub   │  │  Room   │  │ Client  │    │
│  │Middleware│  │ Manager │  │ Manager │  │ Manager │    │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘    │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────┐    │
│  │              Message Protocol                    │    │
│  │  {type, action, data, timestamp, sequence}      │    │
│  └─────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────┤
│  ┌───────────────┐         ┌───────────────┐            │
│  │ admin-gateway │         │ admin-agent   │            │
│  │   (JWT验证)    │         │   (8087)      │            │
│  └───────────────┘         └───────────────┘            │
└─────────────────────────────────────────────────────────┘
```

## 快速开始

### 安装依赖

```bash
go mod tidy
```

### 启动服务

```bash
go run cmd/server/main.go
```

### 配置

编辑 `config.yaml`:

```yaml
server:
  port: 8086
  mode: debug

websocket:
  ping_period: 30s
  pong_wait: 60s
  max_connections: 10000

redis:
  host: localhost
  port: 6379

jwt:
  secret: your-jwt-secret-key
```

## 消息协议

### 消息格式

```json
{
  "type": "event|request|response|ping|pong|error",
  "action": "subscribe|unsubscribe|publish|broadcast|join|leave|direct",
  "channel": "channel-name",
  "room": "room-id",
  "target": "target-client-id",
  "event": "event-name",
  "data": {},
  "timestamp": 1709251200000,
  "sequence": 1,
  "requestId": "request-id"
}
```

### 消息类型

| 类型 | 说明 |
|------|------|
| `event` | 事件消息（服务端推送） |
| `request` | 请求消息（需要响应） |
| `response` | 响应消息 |
| `ping` | 心跳请求 |
| `pong` | 心跳响应 |
| `error` | 错误消息 |

### 操作类型

| 操作 | 说明 |
|------|------|
| `subscribe` | 订阅频道 |
| `unsubscribe` | 取消订阅 |
| `publish` | 发布消息到频道 |
| `broadcast` | 广播消息 |
| `join` | 加入房间 |
| `leave` | 离开房间 |
| `direct` | 点对点消息 |

## API

### WebSocket 连接

```
ws://localhost:8086/ws/connect?token=<jwt-token>
```

或使用 Header:

```
Authorization: Bearer <jwt-token>
```

### HTTP API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/stats` | GET | 获取统计信息 |
| `/api/rooms` | GET | 获取房间列表 |
| `/api/rooms/:id` | GET | 获取房间详情 |
| `/api/broadcast` | POST | 广播消息 |

## 使用示例

### 客户端连接

```javascript
const ws = new WebSocket('ws://localhost:8086/ws/connect?token=xxx');

ws.onopen = () => {
  console.log('Connected');

  // 订阅频道
  ws.send(JSON.stringify({
    type: 'request',
    action: 'subscribe',
    channel: 'system'
  }));

  // 加入房间
  ws.send(JSON.stringify({
    type: 'request',
    action: 'join',
    room: 'project:1'
  }));
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log('Received:', msg);
};

// 心跳
setInterval(() => {
  ws.send(JSON.stringify({ type: 'ping' }));
}, 25000);
```

### 发布消息

```javascript
ws.send(JSON.stringify({
  type: 'request',
  action: 'publish',
  channel: 'system',
  event: 'notice:info',
  data: { message: 'Hello World' }
}));
```

### 广播到房间

```javascript
ws.send(JSON.stringify({
  type: 'request',
  action: 'broadcast',
  room: 'project:1',
  event: 'deploy:progress',
  data: { progress: 50, status: 'building' }
}));
```

## 预定义频道

| 频道 | 说明 |
|------|------|
| `system` | 系统频道 |
| `notice` | 通知频道 |
| `log` | 日志频道 |
| `agent` | Agent 通信频道 |
| `deploy` | 部署频道 |
| `monitor` | 监控频道 |

## 预定义事件

### 系统事件

| 事件 | 说明 |
|------|------|
| `sys:connected` | 连接成功 |
| `sys:disconnected` | 断开连接 |
| `sys:room:joined` | 加入房间 |
| `sys:room:left` | 离开房间 |
| `sys:channel:subscribed` | 订阅成功 |

### 业务事件

| 事件 | 说明 |
|------|------|
| `agent:message` | Agent 消息 |
| `agent:status` | Agent 状态 |
| `deploy:start` | 部署开始 |
| `deploy:progress` | 部署进度 |
| `deploy:success` | 部署成功 |
| `deploy:failed` | 部署失败 |

## 目录结构

```
admin-ws/
├── cmd/
│   └── server/
│       └── main.go          # 入口文件
├── internal/
│   ├── config/              # 配置管理
│   ├── hub/                 # WebSocket Hub
│   ├── handler/             # 消息处理
│   ├── client/              # 客户端管理
│   ├── room/                # 房间管理
│   ├── middleware/          # 中间件
│   ├── router/              # 路由
│   └── service/             # 业务服务
├── pkg/
│   ├── protocol/            # 消息协议
│   └── utils/               # 工具函数
├── config.yaml              # 配置文件
├── go.mod
└── README.md
```

## Docker

```dockerfile
FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY . .
RUN go mod tidy && go build -o ws-server ./cmd/server

FROM alpine:latest
WORKDIR /app
COPY --from=builder /app/ws-server .
COPY config.yaml .
EXPOSE 8086
CMD ["./ws-server"]
```

## 错误码

| 错误码 | 说明 |
|--------|------|
| 0 | 成功 |
| 40000 | 请求参数错误 |
| 40100 | 未授权 |
| 40300 | 无权限 |
| 40400 | 资源不存在 |
| 42900 | 请求频率限制 |
| 50000 | 内部错误 |
| 50300 | 服务不可用 |
