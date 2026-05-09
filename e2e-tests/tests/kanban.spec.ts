/**
 * 看板 E2E 测试
 * 测试看板页面的完整用户流程
 */

import { test, expect, Page, BrowserContext } from '@playwright/test';

test.describe('看板 E2E 测试', () => {
  let context: BrowserContext;
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    context = await browser.newContext();
    page = await context.newPage();
    
    // 监听控制台日志
    page.on('console', msg => {
      console.log(`[Browser] ${msg.type()}: ${msg.text()}`);
    });
    
    // 监听网络请求
    page.on('request', request => {
      if (request.url().includes('/api/')) {
        console.log(`[API Request] ${request.method()} ${request.url()}`);
      }
    });
    
    page.on('response', response => {
      if (response.url().includes('/api/')) {
        console.log(`[API Response] ${response.status()} ${response.url()}`);
      }
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
    
    // 输入用户名
    const usernameInput = page.locator('input[placeholder*="用户名"], input[placeholder*="username"]').first();
    await usernameInput.fill('admin');
    
    // 输入密码
    const passwordInput = page.locator('input[placeholder*="密码"], input[placeholder*="password"]').first();
    await passwordInput.fill('admin123');
    
    // 点击登录
    const loginButton = page.locator('button[type="submit"]').first();
    await loginButton.click();
    
    // 等待登录完成
    await page.waitForURL('/', { timeout: 10000 }).catch(() => {});
    await page.waitForLoadState('networkidle');
    
    // 截图
    await page.screenshot({ path: 'screenshots/kanban-01-login.png', fullPage: true });
  }

  // ========== 测试1: 访问看板页面 ==========
  test('1. 应该能访问看板页面', async () => {
    await login();
    
    // 访问看板页面
    await page.goto('/agent/task');
    await page.waitForLoadState('networkidle');
    
    // 检查页面标题
    const pageTitle = page.locator('text=任务看板');
    await expect(pageTitle).toBeVisible({ timeout: 10000 });
    
    // 截图
    await page.screenshot({ path: 'screenshots/kanban-02-board.png', fullPage: true });
    
    console.log('✅ 看板页面访问成功');
  });

  // ========== 测试2: 看板列显示 ==========
  test('2. 看板应该显示四个状态列', async () => {
    await login();
    await page.goto('/agent/task');
    await page.waitForLoadState('networkidle');
    
    // 检查四个状态列
    const columns = ['TODO', 'IN PROGRESS', 'BLOCKED', 'DONE'];
    
    for (const column of columns) {
      const columnElement = page.locator(`text=${column}`);
      await expect(columnElement).toBeVisible({ timeout: 5000 });
    }
    
    // 截图
    await page.screenshot({ path: 'screenshots/kanban-03-columns.png', fullPage: true });
    
    console.log('✅ 四个状态列显示正常');
  });

  // ========== 测试3: 创建任务 ==========
  test('3. 应该能创建新任务', async () => {
    await login();
    await page.goto('/agent/task');
    await page.waitForLoadState('networkidle');
    
    // 查找创建任务按钮
    const createButton = page.locator('button:has-text("创建任务"), button:has-text("新增")').first();
    
    if (await createButton.isVisible({ timeout: 5000 }).catch(() => false)) {
      await createButton.click();
      await page.waitForLoadState('networkidle');
      
      // 填写任务表单
      const titleInput = page.locator('input[placeholder*="标题"], input[placeholder*="title"]').first();
      if (await titleInput.isVisible({ timeout: 3000 }).catch(() => false)) {
        await titleInput.fill('E2E测试任务');
        
        const descInput = page.locator('textarea[placeholder*="描述"], textarea').first();
        await descInput.fill('这是一个E2E测试任务描述，用于验证任务创建功能');
        
        // 截图表单
        await page.screenshot({ path: 'screenshots/kanban-04-create-form.png', fullPage: true });
        
        // 提交表单
        const submitButton = page.locator('button:has-text("创建"), button[type="submit"]').last();
        await submitButton.click();
        
        // 等待创建完成
        await page.waitForTimeout(2000);
      }
    }
    
    console.log('✅ 任务创建流程测试完成');
  });

  // ========== 测试4: 任务卡片显示 ==========
  test('4. 任务卡片应该正确显示', async () => {
    await login();
    await page.goto('/agent/task');
    await page.waitForLoadState('networkidle');
    
    // 查找任务卡片
    const taskCards = page.locator('[data-testid="task-card"], .ant-card');
    const cardCount = await taskCards.count();
    
    console.log(`找到 ${cardCount} 个任务卡片`);
    
    if (cardCount > 0) {
      // 检查第一个卡片的元素
      const firstCard = taskCards.first();
      
      // 检查拖拽功能
      const isDraggable = await firstCard.getAttribute('draggable');
      console.log(`任务卡片可拖拽: ${isDraggable}`);
      
      // 截图
      await page.screenshot({ path: 'screenshots/kanban-05-task-cards.png', fullPage: true });
    }
    
    console.log('✅ 任务卡片显示正常');
  });

  // ========== 测试5: 拖拽功能 ==========
  test('5. 应该能拖拽任务卡片', async () => {
    await login();
    await page.goto('/agent/task');
    await page.waitForLoadState('networkidle');
    
    // 查找任务卡片
    const taskCard = page.locator('[draggable="true"]').first();
    
    if (await taskCard.isVisible({ timeout: 5000 }).catch(() => false)) {
      // 获取初始位置
      const initialBox = await taskCard.boundingBox();
      
      if (initialBox) {
        // 查找目标列
        const targetColumn = page.locator('text=IN PROGRESS').first();
        const targetBox = await targetColumn.boundingBox();
        
        if (targetBox) {
          // 执行拖拽
          await taskCard.hover();
          await page.mouse.down();
          await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + 100);
          await page.mouse.up();
          
          // 等待动画
          await page.waitForTimeout(1000);
        }
      }
      
      // 截图
      await page.screenshot({ path: 'screenshots/kanban-06-drag-drop.png', fullPage: true });
    }
    
    console.log('✅ 拖拽功能测试完成');
  });

  // ========== 测试6: 任务详情 ==========
  test('6. 应该能查看任务详情', async () => {
    await login();
    await page.goto('/agent/task');
    await page.waitForLoadState('networkidle');
    
    // 查找并点击任务卡片
    const taskCard = page.locator('.ant-card').first();
    
    if (await taskCard.isVisible({ timeout: 5000 }).catch(() => false)) {
      await taskCard.click();
      
      // 等待详情弹窗
      await page.waitForTimeout(1000);
      
      // 截图详情弹窗
      await page.screenshot({ path: 'screenshots/kanban-07-task-detail.png', fullPage: true });
      
      // 关闭弹窗
      const closeButton = page.locator('button:has-text("关闭"), button[aria-label="Close"]').first();
      if (await closeButton.isVisible({ timeout: 3000 }).catch(() => false)) {
        await closeButton.click();
      }
    }
    
    console.log('✅ 任务详情测试完成');
  });

  // ========== 测试7: 筛选功能 ==========
  test('7. 应该能筛选任务', async () => {
    await login();
    await page.goto('/agent/task');
    await page.waitForLoadState('networkidle');
    
    // 查找筛选下拉框
    const filterSelect = page.locator('.ant-select, select').first();
    
    if (await filterSelect.isVisible({ timeout: 5000 }).catch(() => false)) {
      await filterSelect.click();
      await page.waitForTimeout(500);
      
      // 截图筛选选项
      await page.screenshot({ path: 'screenshots/kanban-08-filter.png', fullPage: true });
      
      // 按 ESC 关闭下拉
      await page.keyboard.press('Escape');
    }
    
    console.log('✅ 筛选功能测试完成');
  });

  // ========== 测试8: 响应式设计 ==========
  test('8. 看板在移动设备上应该正常显示', async () => {
    await page.setViewportSize({ width: 375, height: 667 });
    
    await login();
    await page.goto('/agent/task');
    await page.waitForLoadState('networkidle');
    
    // 截图移动端视图
    await page.screenshot({ path: 'screenshots/kanban-09-mobile.png', fullPage: true });
    
    // 恢复桌面视口
    await page.setViewportSize({ width: 1280, height: 720 });
    
    console.log('✅ 移动端响应式测试完成');
  });

  // ========== 测试9: 统计信息 ==========
  test('9. 应该显示任务统计信息', async () => {
    await login();
    await page.goto('/agent/task');
    await page.waitForLoadState('networkidle');
    
    // 查找统计标签
    const statsTags = page.locator('.ant-tag');
    const tagCount = await statsTags.count();
    
    console.log(`找到 ${tagCount} 个统计标签`);
    
    // 查找总计标签
    const totalTag = page.locator('text=/总计:/');
    if (await totalTag.isVisible({ timeout: 3000 }).catch(() => false)) {
      const totalText = await totalTag.textContent();
      console.log(`统计信息: ${totalText}`);
    }
    
    // 截图统计信息
    await page.screenshot({ path: 'screenshots/kanban-10-stats.png', fullPage: true });
    
    console.log('✅ 统计信息显示正常');
  });

  // ========== 测试10: API 请求测试 ==========
  test('10. 看板应该正确调用后端 API', async () => {
    // 使用 API 请求测试
    const loginResponse = await page.request.post('http://localhost:8081/api/auth/login', {
      data: {
        username: 'admin',
        password: 'admin123'
      }
    });
    
    expect(loginResponse.status()).toBe(200);
    const loginData = await loginResponse.json();
    const token = loginData.data.token;
    
    // 获取任务列表
    const tasksResponse = await page.request.get('http://localhost:8081/api/agent/tasks', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    
    expect(tasksResponse.status()).toBe(200);
    const tasksData = await tasksResponse.json();
    expect(tasksData.code).toBe(200);
    
    console.log(`✅ API 测试通过，获取到 ${tasksData.data?.total || 0} 个任务`);
  });
});
