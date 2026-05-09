# AI协作可视化看板 - 测试方案

**项目**: 6智能体协作看板系统  
**测试负责人**: QA工程师  
**日期**: 2026-03-13  
**质量目标**: 状态更新延迟<500ms | 50+并发任务 | 断线重连无数据丢失

---

## 1. 测试用例清单

### 1.1 功能测试用例

| ID | 测试项 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|----|--------|----------|----------|----------|--------|
| **FT-001** | 智能体状态实时更新 | 看板已加载，WebSocket已连接 | 1. 触发智能体A状态变更<br>2. 观察看板更新时间 | 状态在500ms内更新，显示正确的状态图标和文本 | P0 |
| **FT-002** | 任务卡片拖拽到智能体列 | 至少有1个任务卡片和1个智能体 | 1. 拖拽任务卡片到目标智能体列<br>2. 释放鼠标 | 任务成功移动到目标列，任务assignee更新，其他客户端同步看到变化 | P0 |
| **FT-003** | 6个智能体并发工作 | 所有智能体处于idle状态 | 1. 同时触发6个任务分配给6个智能体<br>2. 观察看板状态 | 6个智能体同时显示"工作中"状态，任务卡片正确分配 | P0 |
| **FT-004** | 任务优先级排序 | 智能体列有多个任务 | 1. 修改任务优先级（高/中/低）<br>2. 观察任务排序 | 任务按优先级重新排序（高→中→低） | P1 |
| **FT-005** | 任务详情展示 | 任务卡片存在 | 1. 点击任务卡片<br>2. 查看详情面板 | 详情面板显示：任务描述、创建时间、执行日志、当前状态 | P1 |
| **FT-006** | 历史回放功能 | 系统运行超过1小时，有历史数据 | 1. 打开历史回放面板<br>2. 选择时间范围<br>3. 点击播放 | 回放显示指定时间段内的智能体活动和任务流转动画 | P1 |
| **FT-007** | 历史回放暂停/快进 | 历史回放正在播放 | 1. 点击暂停按钮<br>2. 拖动进度条快进 | 暂停成功，进度条跳转到指定时间点 | P2 |
| **FT-008** | 智能体筛选器 | 看板有多个智能体和任务 | 1. 选择只显示智能体A和C<br>2. 观察看板 | 只显示A和C两列，相关任务保留，其他列隐藏 | P2 |
| **FT-009** | 任务搜索 | 看板有多个任务 | 1. 在搜索框输入关键词<br>2. 观察结果 | 匹配的任务卡片高亮显示，不匹配的变暗 | P2 |
| **FT-010** | 多客户端同步 | 至少2个浏览器标签页打开看板 | 1. 在客户端A拖拽任务<br>2. 观察客户端B | 客户端B在500ms内同步显示相同变化 | P0 |

### 1.2 性能测试用例

| ID | 测试项 | 测试条件 | 测试步骤 | 验收标准 | 优先级 |
|----|--------|----------|----------|----------|--------|
| **PT-001** | 状态更新延迟 | WebSocket连接正常 | 1. 服务端触发状态变更<br>2. 客户端接收并渲染<br>3. 测量端到端延迟 | P95延迟 < 500ms | P0 |
| **PT-002** | 50并发任务加载 | 预置50个任务 | 1. 加载看板<br>2. 测量首屏渲染时间 | 首屏渲染 < 2秒 | P0 |
| **PT-003** | 100并发任务压力 | 预置100个任务 | 1. 加载看板<br>2. 触发20个并发操作 | 系统不崩溃，响应时间 < 3秒 | P1 |
| **PT-004** | WebSocket消息吞吐 | 模拟高频消息推送 | 1. 服务端每秒推送50条状态更新<br>2. 持续5分钟 | 客户端不丢消息，UI不卡顿 | P1 |
| **PT-005** | 历史回放加载速度 | 1小时历史数据 | 1. 请求1小时历史回放<br>2. 测量数据加载和渲染时间 | 加载时间 < 3秒，回放流畅（30fps+） | P2 |

### 1.3 边界测试用例

| ID | 测试项 | 测试条件 | 测试步骤 | 预期结果 | 优先级 |
|----|--------|----------|----------|----------|--------|
| **BT-001** | 断线重连数据恢复 | WebSocket连接中 | 1. 断开网络5秒<br>2. 恢复网络<br>3. 观察数据同步 | 重连后自动同步缺失数据，无数据丢失 | P0 |
| **BT-002** | 长时间断线重连 | 系统运行中 | 1. 断开网络2分钟<br>2. 恢复网络 | 重连后同步2分钟内所有变更，UI提示"已同步N条更新" | P0 |
| **BT-003** | 网络不稳定模拟 | WebSocket连接中 | 1. 模拟50%丢包率<br>2. 持续操作30秒 | 系统自动重连，消息队列保证最终一致性 | P1 |
| **BT-004** | 同时拖拽同一任务 | 2个客户端 | 1. 客户端A和B同时拖拽任务X<br>2. 释放到不同位置 | 后提交的操作覆盖先前的，最终状态一致，无冲突提示 | P1 |
| **BT-005** | 空看板状态 | 无任务数据 | 1. 加载空看板 | 显示空状态提示："暂无任务，请添加第一个任务" | P2 |
| **BT-006** | 超长任务名称 | 创建任务 | 1. 输入500字符任务名称 | 名称被截断显示（显示前50字符+...），详情页显示完整 | P2 |
| **BT-007** | 并发拖拽冲突 | 3个客户端 | 1. 3个客户端同时拖拽任务到不同智能体 | 最终状态一致，使用最后提交的位置，无数据损坏 | P1 |
| **BT-008** | 浏览器标签页切换 | 看板已打开 | 1. 切换到其他标签页5分钟<br>2. 切回看板标签页 | WebSocket重连（如断开），数据自动同步到最新状态 | P2 |

---

## 2. WebSocket测试方案

### 2.1 并发连接测试方案

#### 方案A：使用 k6 + WebSocket（推荐）

**测试脚本**: `tests/websocket-concurrent.js`

```javascript
import { check } from 'k6';
import { WebSocket } from 'k6/experimental/websockets';

export const options = {
  stages: [
    { duration: '30s', target: 20 },  // 逐步增加到20个连接
    { duration: '1m', target: 50 },   // 增加到50个连接
    { duration: '30s', target: 50 },  // 维持50个连接
    { duration: '30s', target: 0 },   // 逐步减少到0
  ],
};

export default function () {
  const url = 'ws://localhost:8080/ws/kanban';
  const ws = new WebSocket(url);
  
  let messageCount = 0;
  const startTime = Date.now();
  
  ws.onopen = () => {
    console.log(`VU ${__VU}: WebSocket connected`);
    
    // 模拟客户端订阅
    ws.send(JSON.stringify({ type: 'subscribe', channel: 'kanban-updates' }));
    
    // 定期发送心跳
    const heartbeat = setInterval(() => {
      ws.send(JSON.stringify({ type: 'ping' }));
    }, 30000);
    
    // 模拟用户操作（每5秒拖拽一次任务）
    const dragInterval = setInterval(() => {
      ws.send(JSON.stringify({
        type: 'task-move',
        taskId: `task-${Math.floor(Math.random() * 50)}`,
        targetAgent: `agent-${Math.floor(Math.random() * 6)}`,
        timestamp: Date.now()
      }));
    }, 5000);
    
    // 清理定时器
    ws.onclose = () => {
      clearInterval(heartbeat);
      clearInterval(dragInterval);
    };
  };
  
  ws.onmessage = (msg) => {
    messageCount++;
    const data = JSON.parse(msg.data);
    
    // 测量消息延迟
    if (data.timestamp) {
      const latency = Date.now() - data.timestamp;
      check(latency, {
        '消息延迟 < 500ms': (l) => l < 500,
      });
    }
    
    check(data, {
      '收到有效消息': (d) => d.type !== undefined,
    });
  };
  
  ws.onerror = (e) => {
    console.error(`VU ${__VU}: WebSocket error: ${e.error}`);
  };
  
  // 保持连接2分钟
  ws.setTimeout(() => {
    console.log(`VU ${__VU}: Received ${messageCount} messages in 2m`);
    ws.close();
  }, 120000);
}
```

**运行命令**:
```bash
k6 run tests/websocket-concurrent.js
```

#### 方案B：使用 Artillery（适合CI集成）

**配置文件**: `tests/artillery-websocket.yml`

```yaml
config:
  target: 'ws://localhost:8080'
  phases:
    - duration: 60
      arrivalRate: 5
      name: "Warm up"
    - duration: 120
      arrivalRate: 10
      name: "Sustained load"
scenarios:
  - name: "Kanban WebSocket Client"
    engine: "ws"
    flow:
      - connect:
          url: "/ws/kanban"
      - send:
          payload: '{"type":"subscribe","channel":"kanban-updates"}'
      - think: 5
      - loop:
          - send:
              payload: '{"type":"task-move","taskId":"task-{{ $randomNumber(1,50) }}","targetAgent":"agent-{{ $randomNumber(1,6) }}"}'
          - think: 5
        count: 20
```

**运行命令**:
```bash
artillery run tests/artillery-websocket.yml
```

### 2.2 断线重连测试方案

#### 手动测试脚本: `tests/test-reconnect.sh`

```bash
#!/bin/bash
# 断线重连自动化测试

echo "=== 断线重连测试开始 ==="

# 1. 启动WebSocket监控
echo "启动WebSocket监控..."
node tests/ws-monitor.js &
MONITOR_PID=$!
sleep 2

# 2. 建立初始连接并记录状态
echo "记录初始状态..."
curl -s http://localhost:8080/api/kanban/state > /tmp/initial_state.json
echo "初始任务数: $(jq '.tasks | length' /tmp/initial_state.json)"

# 3. 模拟网络断开（使用iptables）
echo "模拟网络断开..."
sudo iptables -A INPUT -p tcp --dport 8080 -j DROP
sudo iptables -A OUTPUT -p tcp --dport 8080 -j DROP

# 4. 等待5秒
sleep 5

# 5. 触发服务端状态变更（通过其他客户端）
echo "在断线期间触发状态变更..."
sudo iptables -D INPUT -p tcp --dport 8080 -j DROP
sudo iptables -D OUTPUT -p tcp --dport 8080 -j DROP

# 等待重连
sleep 3

# 6. 检查重连后的数据一致性
echo "检查重连后状态..."
curl -s http://localhost:8080/api/kanban/state > /tmp/reconnected_state.json
echo "重连后任务数: $(jq '.tasks | length' /tmp/reconnected_state.json)"

# 7. 对比数据
if diff /tmp/initial_state.json /tmp/reconnected_state.json > /dev/null; then
    echo "❌ 测试失败：重连后数据未更新"
    exit 1
else
    echo "✅ 测试通过：重连后数据已同步"
fi

# 8. 清理
kill $MONITOR_PID
echo "=== 测试结束 ==="
```

#### 自动化重连测试脚本: `tests/ws-reconnect-test.js`

```javascript
const WebSocket = require('ws');
const axios = require('axios');

class ReconnectionTester {
  constructor(url) {
    this.url = url;
    this.ws = null;
    this.messageQueue = [];
    this.reconnectCount = 0;
    this.testResults = [];
  }

  async connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);
      
      this.ws.on('open', () => {
        console.log('✅ WebSocket已连接');
        this.ws.send(JSON.stringify({ type: 'subscribe', channel: 'kanban-updates' }));
        resolve();
      });
      
      this.ws.on('message', (data) => {
        const msg = JSON.parse(data);
        this.messageQueue.push({
          ...msg,
          receivedAt: Date.now()
        });
        console.log(`📨 收到消息: ${msg.type}`);
      });
      
      this.ws.on('close', () => {
        console.log('🔌 WebSocket连接关闭');
        this.reconnectCount++;
      });
      
      this.ws.on('error', (err) => {
        console.error('❌ WebSocket错误:', err.message);
        reject(err);
      });
    });
  }

  async simulateDisconnect(duration = 5000) {
    console.log(`🚫 模拟断线 ${duration}ms...`);
    this.ws.close();
    
    await new Promise(resolve => setTimeout(resolve, duration));
    
    console.log('🔄 尝试重连...');
    await this.connect();
  }

  async verifyDataConsistency() {
    // 获取服务端当前状态
    const serverState = await axios.get('http://localhost:8080/api/kanban/state');
    const serverTasks = serverState.data.tasks;
    
    // 对比客户端接收到的更新
    const clientTasks = this.messageQueue
      .filter(msg => msg.type === 'task-update')
      .map(msg => msg.task);
    
    console.log(`服务端任务数: ${serverTasks.length}`);
    console.log(`客户端接收更新数: ${clientTasks.length}`);
    
    // 验证一致性
    const missingUpdates = serverTasks.filter(st => 
      !clientTasks.find(ct => ct.id === st.id && ct.version >= st.version)
    );
    
    if (missingUpdates.length === 0) {
      console.log('✅ 数据一致性验证通过');
      return true;
    } else {
      console.log(`❌ 缺失更新: ${missingUpdates.length}条`);
      return false;
    }
  }

  async runTest() {
    console.log('=== 开始断线重连测试 ===');
    
    // 1. 建立初始连接
    await this.connect();
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    // 2. 记录初始消息数
    const initialMessageCount = this.messageQueue.length;
    console.log(`初始消息数: ${initialMessageCount}`);
    
    // 3. 模拟短时间断线
    await this.simulateDisconnect(5000);
    await new Promise(resolve => setTimeout(resolve, 3000));
    
    // 4. 验证数据一致性
    const shortDisconnectPass = await this.verifyDataConsistency();
    this.testResults.push({ test: '短时间断线重连', pass: shortDisconnectPass });
    
    // 5. 模拟长时间断线
    await this.simulateDisconnect(120000); // 2分钟
    await new Promise(resolve => setTimeout(resolve, 5000));
    
    // 6. 验证长时间断线后数据一致性
    const longDisconnectPass = await this.verifyDataConsistency();
    this.testResults.push({ test: '长时间断线重连', pass: longDisconnectPass });
    
    // 7. 输出测试报告
    console.log('\n=== 测试报告 ===');
    this.testResults.forEach(result => {
      console.log(`${result.pass ? '✅' : '❌'} ${result.test}`);
    });
    
    this.ws.close();
  }
}

// 运行测试
const tester = new ReconnectionTester('ws://localhost:8080/ws/kanban');
tester.runTest().catch(console.error);
```

**运行命令**:
```bash
node tests/ws-reconnect-test.js
```

---

## 3. 性能测试方案

### 3.1 延迟测试方案（验证500ms要求）

#### 测试脚本: `tests/latency-test.js`

```javascript
const WebSocket = require('ws');
const axios = require('axios');

class LatencyTester {
  constructor(wsUrl, apiUrl) {
    this.wsUrl = wsUrl;
    this.apiUrl = apiUrl;
    this.ws = null;
    this.latencyRecords = [];
  }

  async connect() {
    return new Promise((resolve) => {
      this.ws = new WebSocket(this.wsUrl);
      this.ws.on('open', resolve);
    });
  }

  async measureLatency(iterations = 100) {
    for (let i = 0; i < iterations; i++) {
      // 1. 记录发送时间
      const sendTime = Date.now();
      const timestamp = sendTime;
      
      // 2. 服务端触发状态变更
      await axios.post(`${this.apiUrl}/api/test/trigger-update`, {
        agentId: `agent-${i % 6}`,
        status: 'working',
        timestamp
      });
      
      // 3. 等待WebSocket消息
      const latency = await new Promise((resolve) => {
        const handler = (data) => {
          const msg = JSON.parse(data);
          if (msg.timestamp === timestamp) {
            const receiveTime = Date.now();
            resolve(receiveTime - sendTime);
            this.ws.off('message', handler);
          }
        };
        this.ws.on('message', handler);
        
        // 超时处理
        setTimeout(() => resolve(9999), 5000);
      });
      
      this.latencyRecords.push(latency);
      console.log(`测试 ${i + 1}/${iterations}: ${latency}ms`);
      
      // 间隔100ms
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }

  generateReport() {
    const sorted = [...this.latencyRecords].sort((a, b) => a - b);
    const p50 = sorted[Math.floor(sorted.length * 0.5)];
    const p95 = sorted[Math.floor(sorted.length * 0.95)];
    const p99 = sorted[Math.floor(sorted.length * 0.99)];
    const avg = sorted.reduce((a, b) => a + b, 0) / sorted.length;
    const max = sorted[sorted.length - 1];
    const min = sorted[0];
    
    console.log('\n=== 延迟测试报告 ===');
    console.log(`测试次数: ${sorted.length}`);
    console.log(`最小延迟: ${min}ms`);
    console.log(`最大延迟: ${max}ms`);
    console.log(`平均延迟: ${avg.toFixed(2)}ms`);
    console.log(`P50延迟: ${p50}ms`);
    console.log(`P95延迟: ${p95}ms`);
    console.log(`P99延迟: ${p99}ms`);
    console.log(`\n验收标准: P95 < 500ms`);
    console.log(`测试结果: ${p95 < 500 ? '✅ 通过' : '❌ 失败'}`);
    
    return {
      iterations: sorted.length,
      min,
      max,
      avg,
      p50,
      p95,
      p99,
      pass: p95 < 500
    };
  }

  async run() {
    await this.connect();
    await this.measureLatency(100);
    const report = this.generateReport();
    this.ws.close();
    return report;
  }
}

// 运行测试
const tester = new LatencyTester(
  'ws://localhost:8080/ws/kanban',
  'http://localhost:8080'
);
tester.run().then(report => {
  process.exit(report.pass ? 0 : 1);
});
```

**运行命令**:
```bash
node tests/latency-test.js
```

### 3.2 并发任务压力测试方案

#### 测试脚本: `tests/concurrent-tasks-test.js`

```javascript
const axios = require('axios');
const WebSocket = require('ws');

class ConcurrentTasksTester {
  constructor(baseUrl, wsUrl) {
    this.baseUrl = baseUrl;
    this.wsUrl = wsUrl;
  }

  async createTasks(count) {
    console.log(`创建 ${count} 个任务...`);
    const promises = [];
    
    for (let i = 0; i < count; i++) {
      promises.push(
        axios.post(`${this.baseUrl}/api/tasks`, {
          title: `测试任务-${i}`,
          priority: ['high', 'medium', 'low'][i % 3],
          assignee: `agent-${i % 6}`
        })
      );
    }
    
    const start = Date.now();
    await Promise.all(promises);
    const duration = Date.now() - start;
    
    console.log(`创建完成，耗时: ${duration}ms`);
    return duration;
  }

  async loadKanban() {
    const start = Date.now();
    const response = await axios.get(`${this.baseUrl}/api/kanban`);
    const duration = Date.now() - start;
    
    console.log(`看板加载时间: ${duration}ms`);
    console.log(`任务数量: ${response.data.tasks.length}`);
    
    return { duration, taskCount: response.data.tasks.length };
  }

  async measureRenderTime() {
    // 使用Puppeteer测量首屏渲染时间
    const puppeteer = require('puppeteer');
    const browser = await puppeteer.launch();
    const page = await browser.newPage();
    
    const start = Date.now();
    await page.goto(`${this.baseUrl}/kanban`, { waitUntil: 'networkidle0' });
    
    // 等待看板渲染完成
    await page.waitForSelector('.task-card', { timeout: 10000 });
    const renderTime = Date.now() - start;
    
    console.log(`首屏渲染时间: ${renderTime}ms`);
    
    await browser.close();
    return renderTime;
  }

  async testConcurrentOperations(clients = 10) {
    console.log(`\n测试 ${clients} 个客户端并发操作...`);
    
    const wsClients = [];
    const results = [];
    
    // 建立多个WebSocket连接
    for (let i = 0; i < clients; i++) {
      const ws = new WebSocket(this.wsUrl);
      await new Promise(resolve => ws.on('open', resolve));
      wsClients.push(ws);
    }
    
    // 并发执行拖拽操作
    const start = Date.now();
    const operations = wsClients.map((ws, index) => {
      return new Promise(resolve => {
        const sendTime = Date.now();
        ws.send(JSON.stringify({
          type: 'task-move',
          taskId: `task-${index % 50}`,
          targetAgent: `agent-${(index + 1) % 6}`,
          timestamp: sendTime
        }));
        
        ws.once('message', (data) => {
          const msg = JSON.parse(data);
          resolve(Date.now() - sendTime);
        });
      });
    });
    
    const latencies = await Promise.all(operations);
    const totalDuration = Date.now() - start;
    
    console.log(`并发操作完成，总耗时: ${totalDuration}ms`);
    console.log(`平均响应时间: ${(latencies.reduce((a, b) => a + b) / latencies.length).toFixed(2)}ms`);
    console.log(`最大响应时间: ${Math.max(...latencies)}ms`);
    
    // 清理
    wsClients.forEach(ws => ws.close());
    
    return { totalDuration, latencies };
  }

  async runTest() {
    console.log('=== 并发任务压力测试 ===\n');
    
    // 1. 测试50任务加载
    await this.createTasks(50);
    await this.loadKanban();
    await this.measureRenderTime();
    
    // 2. 测试100任务压力
    await this.createTasks(50); // 再加50个
    await this.loadKanban();
    
    // 3. 测试并发操作
    await this.testConcurrentOperations(20);
    
    console.log('\n=== 测试完成 ===');
  }
}

// 运行
const tester = new ConcurrentTasksTester(
  'http://localhost:8080',
  'ws://localhost:8080/ws/kanban'
);
tester.runTest().catch(console.error);
```

**运行命令**:
```bash
node tests/concurrent-tasks-test.js
```

---

## 4. 自动化测试方案

### 4.1 可自动化测试范围

| 测试类型 | 自动化比例 | 实现方式 | CI集成 |
|---------|-----------|---------|--------|
| 功能测试 | 70% | Playwright E2E测试 | ✅ 每次PR |
| 性能测试 | 90% | k6 + 自定义Node脚本 | ✅ 每日构建 |
| WebSocket测试 | 80% | k6 + Artillery | ✅ 每日构建 |
| 边界测试 | 60% | Playwright + 手动验证 | ⚠️ 发布前 |
| 视觉回归 | 50% | Percy / Playwright截图对比 | ✅ 每次PR |

### 4.2 E2E自动化测试套件（Playwright）

#### 测试配置: `playwright.config.js`

```javascript
module.exports = {
  testDir: './tests/e2e',
  timeout: 30000,
  retries: 2,
  use: {
    baseURL: 'http://localhost:8080',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
    {
      name: 'firefox',
      use: { browserName: 'firefox' },
    },
  ],
};
```

#### 核心测试文件: `tests/e2e/kanban.spec.js`

```javascript
const { test, expect } = require('@playwright/test');

test.describe('AI协作看板 - 功能测试', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.goto('/kanban');
    await page.waitForSelector('.kanban-board');
  });
  
  test('FT-001: 智能体状态实时更新', async ({ page }) => {
    // 1. 定位智能体A的状态图标
    const agentA = page.locator('[data-testid="agent-A"]');
    const statusIcon = agentA.locator('.status-icon');
    
    // 2. 触发状态变更（通过API或UI）
    await page.evaluate(() => {
      window.websocket.send(JSON.stringify({
        type: 'agent-status-change',
        agentId: 'A',
        status: 'working'
      }));
    });
    
    // 3. 验证状态在500ms内更新
    await expect(statusIcon).toHaveClass(/working/, { timeout: 500 });
    await expect(agentA.locator('.status-text')).toContainText('工作中');
  });
  
  test('FT-002: 任务卡片拖拽', async ({ page }) => {
    // 1. 定位任务卡片和目标智能体列
    const taskCard = page.locator('[data-testid="task-1"]');
    const targetColumn = page.locator('[data-testid="agent-B-column"]');
    
    // 2. 执行拖拽
    await taskCard.dragTo(targetColumn);
    
    // 3. 验证任务移动到目标列
    await expect(targetColumn.locator('[data-testid="task-1"]')).toBeVisible();
    
    // 4. 验证assignee更新
    const taskInNewColumn = targetColumn.locator('[data-testid="task-1"]');
    await expect(taskInNewColumn.locator('.assignee')).toContainText('Agent B');
  });
  
  test('FT-010: 多客户端同步', async ({ browser }) => {
    // 1. 打开两个浏览器上下文
    const context1 = await browser.newContext();
    const context2 = await browser.newContext();
    const page1 = await context1.newPage();
    const page2 = await context2.newPage();
    
    // 2. 两个页面都加载看板
    await page1.goto('/kanban');
    await page2.goto('/kanban');
    await page1.waitForSelector('.kanban-board');
    await page2.waitForSelector('.kanban-board');
    
    // 3. 在page1执行拖拽
    const taskCard = page1.locator('[data-testid="task-1"]');
    const targetColumn = page1.locator('[data-testid="agent-C-column"]');
    await taskCard.dragTo(targetColumn);
    
    // 4. 验证page2在500ms内同步
    const taskInPage2 = page2.locator('[data-testid="agent-C-column"] [data-testid="task-1"]');
    await expect(taskInPage2).toBeVisible({ timeout: 500 });
    
    // 清理
    await context1.close();
    await context2.close();
  });
  
  test('BT-001: 断线重连数据恢复', async ({ page, context }) => {
    // 1. 加载看板并记录初始任务数
    await page.goto('/kanban');
    const initialTaskCount = await page.locator('.task-card').count();
    
    // 2. 模拟断网
    await context.setOffline(true);
    await page.waitForTimeout(5000);
    
    // 3. 恢复网络
    await context.setOffline(false);
    
    // 4. 等待重连提示
    await expect(page.locator('.reconnect-toast')).toContainText('已重新连接');
    
    // 5. 验证任务数量一致
    const reconnectedTaskCount = await page.locator('.task-card').count();
    expect(reconnectedTaskCount).toBe(initialTaskCount);
  });
  
  test('FT-006: 历史回放功能', async ({ page }) => {
    // 1. 打开历史回放面板
    await page.click('[data-testid="history-button"]');
    await expect(page.locator('.history-panel')).toBeVisible();
    
    // 2. 选择时间范围（最近1小时）
    await page.fill('[data-testid="history-start"]', '1 hour ago');
    await page.fill('[data-testid="history-end"]', 'now');
    
    // 3. 点击播放
    await page.click('[data-testid="play-button"]');
    
    // 4. 验证回放动画开始
    await expect(page.locator('.replay-progress')).toBeVisible();
    await expect(page.locator('.kanban-board')).toHaveClass(/replay-mode/);
  });
});

test.describe('AI协作看板 - 性能测试', () => {
  
  test('PT-001: 状态更新延迟 < 500ms', async ({ page }) => {
    await page.goto('/kanban');
    
    const latencies = [];
    
    // 测量10次状态更新延迟
    for (let i = 0; i < 10; i++) {
      const startTime = Date.now();
      
      await page.evaluate(() => {
        window.websocket.send(JSON.stringify({
          type: 'ping',
          timestamp: Date.now()
        }));
      });
      
      // 等待pong响应
      await page.waitForFunction(() => {
        return window.lastPongTime && (Date.now() - window.lastPongTime) < 100;
      });
      
      const latency = Date.now() - startTime;
      latencies.push(latency);
    }
    
    const avgLatency = latencies.reduce((a, b) => a + b) / latencies.length;
    console.log(`平均延迟: ${avgLatency}ms`);
    
    expect(avgLatency).toBeLessThan(500);
  });
  
  test('PT-002: 50任务首屏渲染 < 2秒', async ({ page }) => {
    // 预置50个任务
    await page.goto('/kanban?test-mode=50-tasks');
    
    const startTime = Date.now();
    await page.waitForSelector('.task-card:nth-child(50)');
    const renderTime = Date.now() - startTime;
    
    console.log(`50任务渲染时间: ${renderTime}ms`);
    expect(renderTime).toBeLessThan(2000);
  });
});
```

#### 运行E2E测试:
```bash
# 安装依赖
npm install -D @playwright/test

# 运行所有测试
npx playwright test

# 运行特定测试
npx playwright test tests/e2e/kanban.spec.js

# 生成HTML报告
npx playwright show-report
```

### 4.3 CI/CD集成配置

#### GitHub Actions: `.github/workflows/test.yml`

```yaml
name: Kanban Test Suite

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]
  schedule:
    - cron: '0 2 * * *'  # 每日凌晨2点运行

jobs:
  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'
      
      - name: Install dependencies
        run: npm ci
      
      - name: Install Playwright
        run: npx playwright install --with-deps
      
      - name: Run E2E tests
        run: npx playwright test
        env:
          BASE_URL: http://localhost:8080
      
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: playwright-report
          path: playwright-report/
  
  performance-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup k6
        uses: grafana/setup-k6@v1
      
      - name: Run WebSocket concurrent test
        run: k6 run tests/websocket-concurrent.js
      
      - name: Run latency test
        run: node tests/latency-test.js
      
      - name: Upload performance report
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: performance-report
          path: reports/
  
  websocket-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'
      
      - name: Install dependencies
        run: npm ci
      
      - name: Run WebSocket reconnection test
        run: node tests/ws-reconnect-test.js
      
      - name: Run concurrent tasks test
        run: node tests/concurrent-tasks-test.js
```

---

## 5. 质量验收标准（GO/NO-GO检查项）

### 5.1 上线前验收清单

#### 🔴 必须通过（阻塞性）- GO/NO-GO

| # | 检查项 | 验收标准 | 验证方法 | 负责人 | 状态 |
|---|--------|----------|----------|--------|------|
| 1 | 状态更新延迟 | P95延迟 < 500ms | `node tests/latency-test.js` | QA | ⬜ |
| 2 | 断线重连数据完整性 | 重连后无数据丢失 | `node tests/ws-reconnect-test.js` | QA | ⬜ |
| 3 | 50并发任务支持 | 系统稳定运行，无崩溃 | `node tests/concurrent-tasks-test.js` | QA | ⬜ |
| 4 | 核心功能E2E测试 | 100%通过 | `npx playwright test` | QA | ⬜ |
| 5 | WebSocket连接稳定性 | 50并发连接无掉线 | `k6 run tests/websocket-concurrent.js` | QA | ⬜ |
| 6 | 拖拽功能多客户端同步 | 延迟 < 500ms | Playwright FT-010测试 | QA | ⬜ |
| 7 | 无阻塞性Bug | P0/P1级别Bug数 = 0 | Bug管理系统 | 开发 | ⬜ |
| 8 | 生产环境部署验证 | 看板可访问，功能正常 | 手动冒烟测试 | QA | ⬜ |

#### 🟡 强烈建议（非阻塞）

| # | 检查项 | 验收标准 | 验证方法 | 负责人 | 状态 |
|---|--------|----------|----------|--------|------|
| 9 | 历史回放流畅度 | ≥ 30fps | Chrome DevTools Performance | 前端 | ⬜ |
| 10 | 100任务压力测试 | 响应时间 < 3秒 | `node tests/concurrent-tasks-test.js` (100任务) | QA | ⬜ |
| 11 | 代码覆盖率 | ≥ 70% | Jest / Istanbul | 开发 | ⬜ |
| 12 | 视觉回归测试 | 无意外UI变化 | Percy / Playwright截图对比 | QA | ⬜ |
| 13 | P2级别Bug数 | < 5个 | Bug管理系统 | 开发 | ⬜ |
| 14 | 浏览器兼容性 | Chrome/Firefox/Safari通过 | Playwright多浏览器测试 | QA | ⬜ |

#### 🟢 优化建议（可延后）

| # | 检查项 | 验收标准 | 验证方法 | 负责人 | 状态 |
|---|--------|----------|----------|--------|------|
| 15 | 移动端适配 | 平板可正常操作 | 手动测试iPad | QA | ⬜ |
| 16 | 无障碍性 | WCAG AA级 | axe-core工具 | 前端 | ⬜ |
| 17 | 国际化支持 | 中英文切换正常 | 手动测试 | 前端 | ⬜ |

### 5.2 验收流程

```
┌─────────────────────────────────────────────┐
│         上线验收流程 (Release Gate)          │
└─────────────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  1. 自动化测试通过     │
         │  (E2E + 性能 + WS)    │
         └───────────────────────┘
                     │ ✅
                     ▼
         ┌───────────────────────┐
         │  2. P0/P1 Bug清零     │
         └───────────────────────┘
                     │ ✅
                     ▼
         ┌───────────────────────┐
         │  3. 性能指标达标       │
         │  (延迟 < 500ms)       │
         └───────────────────────┘
                     │ ✅
                     ▼
         ┌───────────────────────┐
         │  4. 生产环境冒烟测试   │
         └───────────────────────┘
                     │ ✅
                     ▼
         ┌───────────────────────┐
         │     ✅ GO - 上线       │
         └───────────────────────┘

任一步骤失败 → ❌ NO-GO → 修复后重新验收
```

### 5.3 验收报告模板

```markdown
# AI协作看板 - 上线验收报告

**版本**: v1.0.0
**验收日期**: 2026-03-13
**验收人**: [姓名]
**决策**: ✅ GO / ❌ NO-GO

## 1. 测试执行情况

### 1.1 功能测试
- 总用例数: 10
- 通过: X
- 失败: X
- 阻塞: X

### 1.2 性能测试
- 延迟测试: P95 = XXXms (目标 < 500ms) → ✅/❌
- 并发测试: XX任务稳定运行 → ✅/❌
- WebSocket稳定性: XX连接无掉线 → ✅/❌

### 1.3 自动化测试
- E2E测试通过率: XX%
- 代码覆盖率: XX%

## 2. Bug统计

| 级别 | 总数 | 已修复 | 待修复 |
|------|------|--------|--------|
| P0   | X    | X      | X      |
| P1   | X    | X      | X      |
| P2   | X    | X      | X      |

## 3. 风险评估

- [列出已知风险和应对措施]

## 4. 决策依据

[说明GO/NO-GO的理由]

## 5. 附件

- [测试报告链接]
- [性能报告链接]
- [Bug列表链接]
```

---

## 6. 测试环境准备

### 6.1 测试数据准备脚本

```javascript
// tests/seed-test-data.js
const axios = require('axios');

async function seedTestData() {
  const baseUrl = 'http://localhost:8080/api';
  
  // 创建6个智能体
  for (let i = 1; i <= 6; i++) {
    await axios.post(`${baseUrl}/agents`, {
      id: `agent-${i}`,
      name: `Agent ${String.fromCharCode(64 + i)}`,
      status: 'idle'
    });
  }
  
  // 创建50个测试任务
  for (let i = 1; i <= 50; i++) {
    await axios.post(`${baseUrl}/tasks`, {
      id: `task-${i}`,
      title: `测试任务 ${i}`,
      priority: ['high', 'medium', 'low'][i % 3],
      assignee: `agent-${(i % 6) + 1}`
    });
  }
  
  console.log('✅ 测试数据准备完成');
}

seedTestData();
```

### 6.2 测试环境要求

- **Node.js**: v18+
- **浏览器**: Chrome latest, Firefox latest
- **测试工具**: k6, Playwright, Artillery
- **服务端**: 本地运行在 localhost:8080

---

## 7. 测试执行计划

| 阶段 | 测试类型 | 频率 | 执行时间 |
|------|----------|------|----------|
| 开发阶段 | 单元测试 | 每次提交 | 2分钟 |
| PR阶段 | E2E测试 | 每个PR | 10分钟 |
| 每日构建 | 性能+WS测试 | 每日1次 | 30分钟 |
| 发布前 | 全量验收 | 每次发布 | 2小时 |

---

**文档版本**: v1.0  
**最后更新**: 2026-03-13  
**维护人**: QA工程师
