# AI协作可视化看板 - 后端设计文档

## 📋 文档索引

本目录包含完整的后端设计文档，涵盖API设计、数据库设计、WebSocket服务、缓存策略和状态同步机制。

---

## 📚 文档列表

### 1. [API文档.md](./API文档.md)
**RESTful API接口设计**

- ✅ 6个任务管理接口
- ✅ 3个智能体状态接口
- ✅ 3个协作记录接口
- ✅ 2个统计分析接口
- ✅ WebSocket消息协议
- ✅ 错误码和限流规则

**核心内容:**
- 基础信息配置
- 完整的请求/响应示例
- WebSocket连接规范
- 数据字段说明

---

### 2. [database-schema.sql](./database-schema.sql)
**数据库表结构设计**

- ✅ 7张核心数据表
- ✅ 索引和约束
- ✅ 视图和存储过程
- ✅ 触发器
- ✅ 6个智能体初始数据

**表结构:**
1. `agents` - 智能体表
2. `tasks` - 任务表
3. `task_dependencies` - 任务依赖关系表
4. `task_agents` - 任务智能体关联表
5. `collaboration_records` - 协作记录表
6. `agent_statistics` - 智能体统计表
7. `websocket_connections` - WebSocket连接表
8. `system_logs` - 系统日志表

---

### 3. [WebSocket-Service.php](./WebSocket-Service.php)
**Swoole WebSocket服务代码骨架**

- ✅ 完整的服务架构
- ✅ 连接管理
- ✅ 房间管理
- ✅ 心跳检测
- ✅ 消息路由
- ✅ Redis Pub/Sub集成
- ✅ 异步任务处理

**核心功能:**
- 基于 Swoole 4.8+
- 协程支持
- 内存表管理连接
- 5秒定时看板更新
- 房间订阅/退订机制

---

### 4. [Redis缓存策略.md](./Redis缓存策略.md)
**Redis缓存层设计**

- ✅ 数据结构设计
- ✅ 缓存更新策略
- ✅ 缓存失效处理
- ✅ 性能优化方案
- ✅ 监控和容灾

**缓存类型:**
- 智能体状态缓存 (Hash)
- 任务状态缓存 (Hash + Sorted Set)
- 协作记录缓存 (List)
- 看板数据缓存 (String)
- WebSocket连接管理

---

### 5. [智能体状态同步机制.md](./智能体状态同步机制.md)
**实时状态同步设计**

- ✅ 6个智能体角色定义
- ✅ 状态变更流程
- ✅ 推送机制设计
- ✅ 一致性保证
- ✅ 断线重连处理
- ✅ 协作示例流程

**核心机制:**
- 心跳保活 (30秒间隔)
- 事件驱动推送
- Redis Pub/Sub
- 定时全量更新
- 版本号控制

---

### 6. [工作量评估.md](./工作量评估.md)
**项目实施评估**

- ✅ 详细工作量分解
- ✅ 技术难点评估
- ✅ 风险评估
- ✅ 团队配置建议
- ✅ 里程碑计划

**工作量汇总:**
- 基础工作量: 18人日
- 总工作量: ~22人日 (含难度系数)
- 建议团队: 2-3人
- 预计工期: 2-3周

---

## 🏗️ 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                        客户端层                               │
│         (Vue前端 / WebSocket Client / HTTP Client)          │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┴──────────────┐
         │                              │
    ┌────▼─────┐                  ┌────▼─────┐
    │ REST API │                  │WebSocket │
    │  :80     │                  │  :9501   │
    └────┬─────┘                  └────┬─────┘
         │                              │
    ┌────▼──────────────────────────────▼────┐
    │          Laravel Application            │
    │  (Controllers / Models / Services)      │
    └────┬──────────────────────────────┬────┘
         │                              │
    ┌────▼─────┐                  ┌────▼─────┐
    │  MySQL   │                  │  Redis   │
    │  :3306   │                  │  :6379   │
    └──────────┘                  └──────────┘
```

---

## 🚀 快速开始

### 1. 数据库初始化
```bash
mysql -u root -p < database-schema.sql
```

### 2. 配置Laravel
```bash
composer install
cp .env.example .env
php artisan key:generate
```

### 3. 启动WebSocket服务
```php
// 在 app/Console/Commands/StartWebSocketServer.php
php artisan ws:start
```

### 4. 测试API
```bash
# 获取所有智能体
curl http://localhost/api/v1/agents

# 创建任务
curl -X POST http://localhost/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"测试任务","priority":"high"}'
```

---

## 📊 核心功能流程

### 任务协作完整流程

```
1. 项目经理创建任务
   └─> POST /api/v1/tasks

2. 分配给需求分析师
   └─> POST /api/v1/tasks/{id}/assign

3. 需求分析师开始工作
   └─> WebSocket: agent_status_update

4. 需求分析完成,转交UI设计师
   └─> 创建协作记录 (transferred)

5. UI设计师完成设计,转交前端+后端
   └─> 并行开发

6. 开发完成,转交测试工程师
   └─> 测试验证

7. 测试通过,任务完成
   └─> WebSocket: task_status_update (completed)
```

---

## 🔧 技术要点

### WebSocket消息流
```
智能体 → HTTP API → MySQL → Observer → Redis → WebSocket → 客户端
```

### 缓存更新策略
```
1. 智能体状态: Write-Through (实时更新Redis)
2. 任务详情: Cache-Aside (查询时缓存)
3. 看板数据: 定时刷新 (5秒一次)
```

### 状态一致性保证
```
1. 数据库事务
2. Redis分布式锁
3. 版本号控制
4. Observer监听
```

---

## 📈 性能指标

| 指标 | 目标值 |
|------|--------|
| WebSocket连接数 | ≥ 1000 |
| 消息推送延迟 | ≤ 500ms |
| API响应时间 | ≤ 200ms |
| 并发请求 | ≥ 500 QPS |

---

## 🛡️ 安全措施

1. **认证**: JWT Token验证
2. **授权**: 角色权限控制
3. **限流**: 60次/分钟/IP
4. **加密**: WSS (WebSocket over SSL)
5. **日志**: 操作审计日志

---

## 📦 依赖要求

```
PHP >= 8.0
Laravel 8.x
Swoole >= 4.8
Redis >= 6.0
MySQL >= 8.0
```

---

## 📝 TODO

### Phase 1 (核心功能)
- [ ] 实现所有API接口
- [ ] 完成WebSocket服务
- [ ] 集成Redis缓存
- [ ] 状态同步机制

### Phase 2 (优化增强)
- [ ] 性能压测
- [ ] 监控告警
- [ ] 文档完善
- [ ] 单元测试

### Phase 3 (生产部署)
- [ ] Docker容器化
- [ ] 负载均衡
- [ ] 数据库读写分离
- [ ] Redis集群

---

## 👥 团队分工建议

### 后端工程师A
- WebSocket服务开发
- Redis缓存层
- 状态同步机制

### 后端工程师B
- RESTful API开发
- 业务逻辑层
- 数据库设计

### 后端工程师C
- 测试与优化
- 监控部署
- 文档编写

---

## 📞 联系方式

如有疑问,请联系项目负责人。

---

**文档版本**: v1.0  
**创建日期**: 2026-03-13  
**最后更新**: 2026-03-13  
**作者**: AI协作看板后端团队
