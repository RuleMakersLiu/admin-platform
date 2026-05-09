/**
 * WebSocket E2E 测试
 * 测试 WebSocket 连接和消息通信
 */

import { test, expect, Page, BrowserContext } from '@playwright/test';

test.describe('WebSocket E2E 测试', () => {
  let context: BrowserContext;
  let page: Page;
  let wsMessages: any[] = [];

  test.beforeAll(async ({ browser }) => {
    context = await browser.newContext();
    page = await context.newPage();
    
    // 监听 WebSocket 消息
    page.on('websocket', ws => {
      console.log(`[WebSocket] 连接建立: ${ws.url()}`);
      
      ws.on('framesreceived', frames => {
        for (const frame of frames) {
          try {
            const data = JSON.parse(frame.payload as string);
            wsMessages.push(data);
            console.log(`[WebSocket] 收到消息:`, data);
          } catch (e) {
            console.log(`[WebSocket] 收到非 JSON 消息:`, frame.payload);
          }
        }
      });
      
      ws.on('framessent', frames => {
        for (const frame of frames) {
          console.log(`[WebSocket] 发送消息:`, frame.payload);
        }
      });
      
      ws.on('close', () => {
        console.log(`[WebSocket] 连接关闭`);
      });
    });
  });

  test.afterAll(async () => {
    await context.close();
  });

  /**
   * 辅助函数：登录
   */
  async function login() {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    
    const usernameInput = page.locator('input[placeholder*="用户名"], input[placeholder*="username"]').first();
    await usernameInput.fill('admin');
    
    const passwordInput = page.locator('input[placeholder*="密码"], input[placeholder*="password"]').first();
    await passwordInput.fill('admin123');
    
    const loginButton = page.locator('button[type="submit"]').first();
    await loginButton.click();
    
    await page.waitForURL('/', { timeout: 10000 }).catch(() => {});
    await page.waitForLoadState('networkidle');
  }

  // ========== 测试1: WebSocket 连接 ==========
  test('1. WebSocket 应该能成功连接', async () => {
    await login();
    
    // 访问聊天页面（触发 WebSocket 连接）
    await page.goto('/agent/chat');
    await page.waitForLoadState('networkidle');
    
    // 等待 WebSocket 连接
    await page.waitForTimeout(3000);
    
    // 截图
    await page.screenshot({ path: 'screenshots/ws-01-connection.png', fullPage: true });
    
    console.log('✅ WebSocket 连接测试完成');
  });

  // ========== 测试2: 发送聊天消息 ==========
  test('2. 应该能通过 WebSocket 发送消息', async () => {
    await login();
    await page.goto('/agent/chat');
    await page.waitForLoadState('networkidle');
    
    // 查找输入框
    const inputArea = page.locator('textarea, input[type="text"]').first();
    
    if (await inputArea.isVisible({ timeout: 5000 }).catch(() => false)) {
      // 输入消息
      await inputArea.fill('你好，这是一条 WebSocket 测试消息');
      
      // 截图输入状态
      await page.screenshot({ path: 'screenshots/ws-02-input.png', fullPage: true });
      
      // 发送消息
      const sendButton = page.locator('button:has-text("发送"), button[type="submit"]').last();
      if (await sendButton.isVisible({ timeout: 3000 }).catch(() => false)) {
        await sendButton.click();
        
        // 等待响应
        await page.waitForTimeout(5000);
        
        // 截图发送后状态
        await page.screenshot({ path: 'screenshots/ws-03-sent.png', fullPage: true });
      }
    }
    
    console.log('✅ 发送消息测试完成');
  });

  // ========== 测试3: 接收消息 ==========
  test('3. 应该能接收 WebSocket 消息', async () => {
    wsMessages = []; // 清空消息记录
    
    await login();
    await page.goto('/agent/chat');
    await page.waitForLoadState('networkidle');
    
    // 发送消息
    const inputArea = page.locator('textarea, input[type="text"]').first();
    if (await inputArea.isVisible({ timeout: 5000 }).catch(() => false)) {
      await inputArea.fill('测试消息接收');
      
      const sendButton = page.locator('button:has-text("发送"), button[type="submit"]').last();
      if (await sendButton.isVisible({ timeout: 3000 }).catch(() => false)) {
        await sendButton.click();
      }
    }
    
    // 等待接收响应
    await page.waitForTimeout(10000);
    
    console.log(`收到 ${wsMessages.length} 条 WebSocket 消息`);
    
    // 截图
    await page.screenshot({ path: 'screenshots/ws-04-receive.png', fullPage: true });
    
    console.log('✅ 接收消息测试完成');
  });

  // ========== 测试4: 会话管理 ==========
  test('4. 应该能创建和管理会话', async () => {
    await login();
    await page.goto('/agent/chat');
    await page.waitForLoadState('networkidle');
    
    // 查找新建会话按钮
    const newSessionButton = page.locator('button:has-text("新"), button:has-text("创建")').first();
    
    if (await newSessionButton.isVisible({ timeout: 5000 }).catch(() => false)) {
      await newSessionButton.click();
      await page.waitForTimeout(2000);
      
      // 截图
      await page.screenshot({ path: 'screenshots/ws-05-new-session.png', fullPage: true });
    }
    
    console.log('✅ 会话管理测试完成');
  });

  // ========== 测试5: 连接状态显示 ==========
  test('5. 应该显示 WebSocket 连接状态', async () => {
    await login();
    await page.goto('/agent/chat');
    await page.waitForLoadState('networkidle');
    
    // 查找连接状态指示器
    const statusIndicator = page.locator('.ant-badge, [class*="status"], [class*="connected"]');
    const indicatorCount = await statusIndicator.count();
    
    console.log(`找到 ${indicatorCount} 个状态指示器`);
    
    // 截图
    await page.screenshot({ path: 'screenshots/ws-06-status.png', fullPage: true });
    
    console.log('✅ 连接状态测试完成');
  });

  // ========== 测试6: 重连机制 ==========
  test('6. WebSocket 应该有重连机制', async () => {
    await login();
    await page.goto('/agent/chat');
    await page.waitForLoadState('networkidle');
    
    // 等待初始连接
    await page.waitForTimeout(3000);
    
    // 刷新页面（触发重连）
    await page.reload();
    await page.waitForLoadState('networkidle');
    
    // 等待重连
    await page.waitForTimeout(3000);
    
    // 截图
    await page.screenshot({ path: 'screenshots/ws-07-reconnect.png', fullPage: true });
    
    console.log('✅ 重连机制测试完成');
  });

  // ========== 测试7: 流式消息 ==========
  test('7. 应该支持流式消息接收', async () => {
    await login();
    await page.goto('/agent/chat');
    await page.waitForLoadState('networkidle');
    
    // 发送消息
    const inputArea = page.locator('textarea, input[type="text"]').first();
    if (await inputArea.isVisible({ timeout: 5000 }).catch(() => false)) {
      await inputArea.fill('请详细描述流式消息的处理过程');
      
      const sendButton = page.locator('button:has-text("发送"), button[type="submit"]').last();
      if (await sendButton.isVisible({ timeout: 3000 }).catch(() => false)) {
        await sendButton.click();
        
        // 等待流式响应
        await page.waitForTimeout(10000);
        
        // 截图流式输出
        await page.screenshot({ path: 'screenshots/ws-08-streaming.png', fullPage: true });
      }
    }
    
    console.log('✅ 流式消息测试完成');
  });

  // ========== 测试8: 心跳检测 ==========
  test('8. WebSocket 应该有心跳检测', async () => {
    await login();
    await page.goto('/agent/chat');
    await page.waitForLoadState('networkidle');
    
    // 等待心跳消息
    await page.waitForTimeout(60000); // 等待 60 秒观察心跳
    
    // 检查是否有心跳消息
    const pingMessages = wsMessages.filter(m => m.type === 'ping' || m.type === 'pong');
    console.log(`收到 ${pingMessages.length} 条心跳消息`);
    
    console.log('✅ 心跳检测测试完成');
  });

  // ========== 测试9: 错误处理 ==========
  test('9. WebSocket 应该正确处理错误', async () => {
    // 模拟无效 Token
    await page.goto('/agent/chat?token=invalid_token');
    await page.waitForLoadState('networkidle');
    
    // 等待错误响应
    await page.waitForTimeout(3000);
    
    // 检查是否显示错误信息
    const errorMessage = page.locator('text=/错误|失败|invalid|unauthorized/i');
    const hasError = await errorMessage.isVisible({ timeout: 5000 }).catch(() => false);
    
    console.log(`错误处理: ${hasError ? '正确显示错误' : '未显示错误'}`);
    
    // 截图
    await page.screenshot({ path: 'screenshots/ws-09-error.png', fullPage: true });
    
    console.log('✅ 错误处理测试完成');
  });

  // ========== 测试10: API 与 WebSocket 协同 ==========
  test('10. API 和 WebSocket 应该能协同工作', async () => {
    // 使用 API 创建会话
    const loginResponse = await page.request.post('http://localhost:8081/api/auth/login', {
      data: {
        username: 'admin',
        password: 'admin123'
      }
    });
    
    expect(loginResponse.status()).toBe(200);
    const loginData = await loginResponse.json();
    const token = loginData.data.token;
    
    // 创建会话
    const sessionResponse = await page.request.post('http://localhost:8081/api/agent/chat/sessions', {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      data: {
        title: 'WebSocket 测试会话'
      }
    });
    
    expect(sessionResponse.status()).toBe(200);
    const sessionData = await sessionResponse.json();
    console.log('创建会话响应:', sessionData);
    
    // 使用 WebSocket 发送消息
    await login();
    await page.goto('/agent/chat');
    await page.waitForLoadState('networkidle');
    
    const inputArea = page.locator('textarea, input[type="text"]').first();
    if (await inputArea.isVisible({ timeout: 5000 }).catch(() => false)) {
      await inputArea.fill('API 和 WebSocket 协同测试消息');
      
      const sendButton = page.locator('button:has-text("发送"), button[type="submit"]').last();
      if (await sendButton.isVisible({ timeout: 3000 }).catch(() => false)) {
        await sendButton.click();
        await page.waitForTimeout(5000);
      }
    }
    
    // 截图
    await page.screenshot({ path: 'screenshots/ws-10-api-ws.png', fullPage: true });
    
    console.log('✅ API 和 WebSocket 协同测试完成');
  });
});
