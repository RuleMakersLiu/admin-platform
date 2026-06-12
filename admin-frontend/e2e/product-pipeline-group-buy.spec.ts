import { expect, test, type Page } from '@playwright/test';

const pipelineId = 'pipe_groupbuy_e2e';
const completedPipelineId = 'pipe_groupbuy_completed_e2e';

const groupBuyRequirement = [
  '做一个拼团团购活动管理功能。',
  '运营可以创建拼团活动、选择商品 SKU、设置团购价、成团人数、活动时间、限购和库存。',
  '需要活动列表、创建编辑、详情、团单处理、上线下线、导出、权限和验收标准。',
].join('\n');

const authState = {
  state: {
    token: 'e2e-token',
    user: {
      adminId: 1,
      username: 'pm-e2e',
      realName: '产品经理 E2E',
      tenantId: 1,
      isSuper: true,
      permissions: ['*'],
    },
  },
  version: 0,
};

async function seedAuth(page: Page) {
  await page.addInitScript((state) => {
    window.localStorage.setItem('auth-storage', JSON.stringify(state));
    window.localStorage.removeItem('lastProductPipelineId');
  }, authState);
}

async function mockProductPipelineApis(page: Page) {
  const statusPayload = {
    pipeline_id: pipelineId,
    status: 'waiting_confirm',
    current_stage: 'requirement',
    pipeline_mode: 'frontend_contract_review',
    stages: {
      requirement: {
        status: 'completed',
        output: '# 拼团活动管理 PRD\n\n## 需求分析执行步骤\n输入盘点、功能点拆分、流程建模、验收标准落地已完成。\n\n## 验收标准\n- 创建活动后列表可查询。\n- 无权限 API 返回 403。',
      },
      page_design: { status: 'pending', output: '' },
      prototype: { status: 'pending', output: '' },
      delivery: { status: 'pending', output: '' },
      code_review: { status: 'pending', output: '' },
      report: { status: 'pending', output: '' },
    },
    project_skill: {
      project_id: 101,
      project_name: 'web-product-agent',
      skill_version: 3,
    },
    backend_project_skills: [
      {
        project_id: 202,
        project_name: 'wealth-marketing-service',
        skill_version: 2,
      },
    ],
  };

  const artifactPayload = {
    preview_html: '',
    api_contract: '# API 契约\nGET /api/marketing/group-buy/page',
    frontend_files: {
      'src/views/marketing/groupBuy/GroupBuyList.vue': '<template><div>拼团活动列表</div></template>',
    },
    review: {},
    review_status: 'pending',
    review_output: '',
    report: '',
  };

  await page.route('**/api/auth/info', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 200,
        data: {
          adminId: 1,
          username: 'pm-e2e',
          realName: '产品经理 E2E',
          tenantId: 1,
          isSuper: true,
          permissions: ['*'],
        },
      }),
    });
  });

  await page.route('**/api/auth/menus', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: [] }),
    });
  });

  await page.route('**/api/flow/pipeline/list', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: [] }),
    });
  });

  await page.route('**/api/flow/pipeline/match', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 200,
        data: {
          skill: {
            project_id: 101,
            project_name: 'web-product-agent',
            language: 'javascript',
            framework: 'vue2',
            skill_version: 3,
            confirmed_at: 1760000000000,
          },
          confidence: 0.96,
          match_source: 'project_skill',
          match_reason: '团购活动属于营销活动后台管理能力，匹配商品和营销后台前端项目。',
          frontend_page_candidates: {
            requires_selection: false,
            uncertain: false,
            candidates: [],
          },
          backend_matches: [
            {
              skill: {
                project_id: 202,
                project_name: 'wealth-marketing-service',
                language: 'java',
                framework: 'spring-boot',
                skill_version: 2,
                confirmed_at: 1760000000000,
              },
              confidence: 0.94,
              match_source: 'project_skill',
              match_reason: '拼团活动 API 归属营销活动服务。',
            },
          ],
        },
      }),
    });
  });

  await page.route('**/api/flow/pipeline/create', async (route) => {
    const request = route.request().postDataJSON();
    expect(request.user_request).toContain('拼团团购活动管理');
    expect(request.pipeline_mode).toBe('frontend_contract_review');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { pipeline_id: pipelineId, status: 'pending' } }),
    });
  });

  await page.route(`**/api/flow/pipeline/${pipelineId}/execute-stream`, async (route) => {
    const frames = [
      { type: 'stage_started', stage: 'requirement', pipeline_id: pipelineId },
      { type: 'chunk', stage: 'requirement', content: '# 拼团活动管理 PRD\n' },
      { type: 'chunk', stage: 'requirement', content: '需求分析执行步骤、验收标准和权限矩阵已生成。\n' },
      { type: 'stage_completed', stage: 'requirement', pipeline_id: pipelineId },
      { type: 'waiting_confirm', stage: 'requirement', pipeline_id: pipelineId },
      { type: 'done', pipeline_id: pipelineId },
    ].map((event) => `data: ${JSON.stringify(event)}\n\n`).join('');

    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: frames,
    });
  });

  await page.route(`**/api/flow/pipeline/${pipelineId}/status`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: statusPayload }),
    });
  });

  await page.route(`**/api/flow/pipeline/${pipelineId}/artifact`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: artifactPayload }),
    });
  });

}

test.describe('Product pipeline PM workflow', () => {
  test('runs a group-buying requirement through the PM confirmation checkpoint', async ({ page }) => {
    test.setTimeout(90000);

    await seedAuth(page);
    await mockProductPipelineApis(page);

    await page.goto('/pipeline/development', { waitUntil: 'domcontentloaded', timeout: 60000 });

    await expect(page.getByRole('heading', { name: '需求开发' })).toBeVisible();
    await page.getByPlaceholder('描述产品需求、页面目标、核心字段、权限点和验收标准').fill(groupBuyRequirement);
    await page.getByRole('button', { name: /分析需求并匹配页面功能/ }).click();

    await expect(page.getByText('已匹配项目')).toBeVisible();
    await expect(page.getByText(/前端：web-product-agent/).first()).toBeVisible();
    await expect(page.getByText(/后端：wealth-marketing-service/).first()).toBeVisible();
    await expect(page.getByText(`流水线已创建：${pipelineId}`)).toBeVisible();
    await expect(page.getByText('确认需求，进入页面设计')).toBeVisible();
    await expect(page.getByText('拼团活动管理 PRD')).toBeVisible();
    await expect(page.getByText('src/views/marketing/groupBuy/GroupBuyList.vue')).toBeVisible();
    await expect(page.getByRole('button', { name: /确认需求，进入页面设计/ })).toBeVisible();
  });

  test('allows PM feedback adjustment after a pipeline is completed', async ({ page }) => {
    test.setTimeout(90000);

    await seedAuth(page);

    let rollbackRequest: any = null;
    let executeRequest: any = null;

    const completedStatus = {
      pipeline_id: completedPipelineId,
      status: 'completed',
      current_stage: 'report',
      pipeline_mode: 'frontend_contract_review',
      user_request: groupBuyRequirement,
      stages: {
        requirement: { status: 'completed', output: '# 需求分析' },
        page_design: { status: 'completed', output: '# 页面设计' },
        prototype: { status: 'completed', output: '# 前端预览' },
        delivery: { status: 'completed', output: '# API 契约' },
        code_review: { status: 'completed', output: '# 审查通过' },
        report: { status: 'completed', output: '# 交付报告' },
      },
      project_skill: {
        project_id: 101,
        project_name: 'web-product-agent',
        skill_version: 3,
      },
      backend_project_skills: [],
    };

    const runningStatus = {
      ...completedStatus,
      status: 'waiting_confirm',
      current_stage: 'prototype',
      stages: {
        ...completedStatus.stages,
        prototype: { status: 'completed', output: '# 已按反馈修复前端预览' },
        delivery: { status: 'pending', output: '' },
        code_review: { status: 'pending', output: '' },
        report: { status: 'pending', output: '' },
      },
    };

    await page.route('**/api/auth/info', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 200, data: authState.state.user }),
      });
    });

    await page.route('**/api/auth/menus', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 200, data: [] }),
      });
    });

    await page.route('**/api/flow/pipeline/list', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 200,
          data: [
            {
              pipeline_id: completedPipelineId,
              status: 'completed',
              current_stage: 'report',
              user_request: groupBuyRequirement,
            },
          ],
        }),
      });
    });

    await page.route(`**/api/flow/pipeline/${completedPipelineId}/status`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 200, data: rollbackRequest ? runningStatus : completedStatus }),
      });
    });

    await page.route(`**/api/flow/pipeline/${completedPipelineId}/artifact`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 200,
          data: {
            preview_html: '',
            api_contract: '# API 契约',
            frontend_files: {
              'src/views/activityManage/ActivityGroupList.vue': '<template><div>拼团活动列表</div></template>',
            },
            review: {},
            review_status: 'completed',
            review_output: '',
            report: '# 交付报告',
          },
        }),
      });
    });

    await page.route(`**/api/flow/pipeline/${completedPipelineId}/rollback`, async (route) => {
      rollbackRequest = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 200, data: { pipeline_id: completedPipelineId, status: 'pending' } }),
      });
    });

    await page.route(`**/api/flow/pipeline/${completedPipelineId}/execute-stream`, async (route) => {
      executeRequest = route.request().postDataJSON();
      const frames = [
        { type: 'stage_started', stage: 'prototype', pipeline_id: completedPipelineId },
        { type: 'chunk', stage: 'prototype', content: '# 已按反馈修复前端预览\n' },
        { type: 'stage_completed', stage: 'prototype', pipeline_id: completedPipelineId },
        { type: 'waiting_confirm', stage: 'prototype', pipeline_id: completedPipelineId },
        { type: 'done', pipeline_id: completedPipelineId },
      ].map((event) => `data: ${JSON.stringify(event)}\n\n`).join('');

      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: frames,
      });
    });

    await page.goto('/pipeline/development', { waitUntil: 'domcontentloaded', timeout: 60000 });

    await page.getByRole('button', { name: '查看/调整' }).click();
    await expect(page.getByText('验收后需要调整')).toBeVisible();
    await page.getByPlaceholder(/真实预览里新增和编辑都不能打开/).fill(
      '真实预览里新增和编辑都不能打开/保存，请修复创建页路由、编辑回填和保存成功态。',
    );
    await page.getByRole('button', { name: '提交反馈并重新调整' }).click();

    await expect(page.getByText('等待人工确认：前端预览代码')).toBeVisible();
    await page.getByRole('button', { name: /collapsed 前端预览代码/ }).click();
    await expect(page.getByText('已按反馈修复前端预览')).toBeVisible();
    expect(rollbackRequest).toMatchObject({ stage: 'prototype' });
    expect(rollbackRequest.feedback).toContain('新增和编辑都不能打开/保存');
    expect(executeRequest.user_input).toContain('新增和编辑都不能打开/保存');
  });
});
