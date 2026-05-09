# 30秒激活体验 API 文档

## 概述

本模块实现了用户登录后的30秒激活体验功能，通过预加载和流式响应技术，确保用户能够在登录后快速完成首次AI对话。

## 技术栈

- **FastAPI**: 高性能异步Web框架
- **GLM-5**: 智谱AI提供的大语言模型
- **SSE (Server-Sent Events)**: 实现流式响应
- **Redis**: 缓存会话数据（可选）

## API端点

### 1. 预热AI连接

```http
POST /api/v1/activation/warmup
```

**说明**: 登录时调用，提前建立AI连接，减少首次对话延迟。

**响应示例**:
```json
{
  "code": 200,
  "message": "预热成功",
  "data": {
    "status": "warmed",
    "message": "AI连接已预热"
  }
}
```

---

### 2. 开始激活流程

```http
POST /api/v1/activation/start
```

**请求体**:
```json
{
  "userId": 123,
  "tenantId": 1,
  "userName": "张三"
}
```

**响应示例**:
```json
{
  "code": 200,
  "data": {
    "activationId": "act_abc123def456",
    "status": "ready",
    "welcomeMessage": "👋 你好，张三！\n\n欢迎来到智能管理系统！...",
    "suggestedPrompts": [
      "介绍一下系统的主要功能",
      "帮我创建第一个任务"
    ]
  }
}
```

---

### 3. 获取演示模板

```http
GET /api/v1/activation/templates
```

**响应示例**:
```json
{
  "code": 200,
  "data": {
    "templates": [
      {
        "id": "task-create",
        "title": "创建任务",
        "description": "帮我创建一个新的开发任务",
        "prompt": "帮我创建一个任务：实现用户登录功能",
        "category": "任务管理",
        "icon": "📋"
      }
    ],
    "categories": ["任务管理", "Bug管理", "项目管理"]
  }
}
```

---

### 4. 激活对话（SSE流式）

```http
POST /api/v1/activation/chat
```

**请求体**:
```json
{
  "activationId": "act_abc123def456",
  "message": "你好，介绍一下这个系统",
  "useStream": true
}
```

**响应（SSE流）**:
```
data: {"type":"chunk","content":"你","done":false}
data: {"type":"chunk","content":"好","done":false}
data: {"type":"chunk","content":"！","done":false}
...
data: {"type":"done","elapsed":1.23,"done":true}
```

**前端使用示例**:
```javascript
const eventSource = new EventSource('/api/v1/activation/chat', {
  method: 'POST',
  body: JSON.stringify({
    activationId: 'act_abc123def456',
    message: '你好',
    useStream: true
  })
});

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'chunk') {
    // 追加内容到UI
    appendToChat(data.content);
  } else if (data.type === 'done') {
    // 对话完成
    console.log(`耗时: ${data.elapsed}秒`);
    eventSource.close();
  }
};
```

---

### 5. 完成激活

```http
POST /api/v1/activation/complete
```

**请求体**:
```json
{
  "activationId": "act_abc123def456",
  "rating": 5,
  "feedback": "体验很好，很流畅！"
}
```

**响应示例**:
```json
{
  "code": 200,
  "data": {
    "status": "completed",
    "message": "激活完成，欢迎使用系统！",
    "nextSteps": [
      "查看项目概览",
      "创建第一个任务",
      "探索更多AI功能"
    ]
  }
}
```

---

### 6. 获取激活状态

```http
GET /api/v1/activation/status/{activation_id}
```

**响应示例**:
```json
{
  "code": 200,
  "data": {
    "activationId": "act_abc123def456",
    "status": "ready",
    "messageCount": 3,
    "startedAt": 1704067200000,
    "lastActivity": 1704067260000
  }
}
```

## 性能优化

### 1. 预加载机制

- **登录时预热**: 在用户登录成功后立即调用 `/activation/warmup`
- **并行准备**: 使用 `asyncio.create_task()` 并行执行预热任务
- **缓存常见问题**: 系统预设了6个常用演示模板

### 2. 流式响应优化

- **SSE技术**: 使用 Server-Sent Events 实现真正的流式传输
- **禁用缓冲**: 设置 `X-Accel-Buffering: no` 禁用Nginx缓冲
- **减少延迟**: 首字延迟控制在2秒以内

### 3. 会话管理

- **内存缓存**: 使用内存存储会话数据，避免数据库IO
- **自动过期**: 会话30分钟后自动清理
- **历史消息**: 保留最近5轮对话上下文

## 前端集成示例

### React + TypeScript

```typescript
// 开始激活
const startActivation = async (userId: number, tenantId: number) => {
  const response = await fetch('/api/v1/activation/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId, tenantId, userName: '用户' })
  });
  const { data } = await response.json();
  return data;
};

// 流式对话
const streamChat = (activationId: string, message: string) => {
  return new Promise((resolve) => {
    let fullResponse = '';
    
    const eventSource = new EventSource('/api/v1/activation/chat', {
      // Note: EventSource doesn't support POST by default
      // Use fetch with ReadableStream instead
    });
    
    // 使用 fetch + ReadableStream
    fetch('/api/v1/activation/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ activationId, message, useStream: true })
    }).then(response => {
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
      const readStream = () => {
        reader?.read().then(({ done, value }) => {
          if (done) {
            resolve(fullResponse);
            return;
          }
          
          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');
          
          lines.forEach(line => {
            if (line.startsWith('data: ')) {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'chunk') {
                fullResponse += data.content;
                onChunkReceived?.(data.content); // 实时更新UI
              } else if (data.type === 'done') {
                resolve(fullResponse);
              }
            }
          });
          
          readStream();
        });
      };
      
      readStream();
    });
  });
};
```

## 测试

### 单元测试

```bash
# 运行测试
pytest tests/test_activation.py -v
```

### 手动测试

```bash
# 1. 预热AI
curl -X POST http://localhost:8081/api/v1/activation/warmup

# 2. 开始激活
curl -X POST http://localhost:8081/api/v1/activation/start \
  -H "Content-Type: application/json" \
  -d '{"userId": 1, "tenantId": 1, "userName": "测试用户"}'

# 3. 获取模板
curl http://localhost:8081/api/v1/activation/templates

# 4. 发送对话（流式）
curl -X POST http://localhost:8081/api/v1/activation/chat \
  -H "Content-Type: application/json" \
  -d '{"activationId": "act_xxx", "message": "你好", "useStream": true}'

# 5. 完成激活
curl -X POST http://localhost:8081/api/v1/activation/complete \
  -H "Content-Type: application/json" \
  -d '{"activationId": "act_xxx", "rating": 5}'
```

## 监控指标

建议监控以下指标：

- **首字延迟**: AI首次响应时间（目标 <2秒）
- **激活完成率**: 完成激活的用户比例
- **平均对话数**: 每次激活的平均消息数量
- **用户评分**: 完成激活后的用户评分

## 故障排查

### 常见问题

1. **AI响应慢**
   - 检查网络连接
   - 确认预热接口是否被调用
   - 查看GLM-5 API状态

2. **SSE连接断开**
   - 检查Nginx配置（禁用缓冲）
   - 确认超时设置
   - 检查客户端EventSource实现

3. **会话丢失**
   - 确认会话未过期（30分钟TTL）
   - 检查内存使用情况
   - 考虑使用Redis持久化

## 部署注意事项

1. **环境变量**
   - 确保 `ZAI_API_KEY` 已配置
   - 设置合适的 `CORS_ORIGINS`

2. **Nginx配置**
```nginx
location /api/v1/activation/chat {
    proxy_pass http://localhost:8081;
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header X-Accel-Buffering no;
}
```

3. **性能调优**
   - 增加数据库连接池大小
   - 配置合适的worker数量
   - 启用响应压缩

## 更新日志

### v1.0.0 (2026-03-13)
- ✅ 实现完整的激活流程API
- ✅ 支持SSE流式响应
- ✅ 添加预热机制
- ✅ 提供6个演示模板
- ✅ 实现会话管理
