-- Add missing operation/API permissions to the role permission tree.

DO $$
DECLARE
    now_ms BIGINT := (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT;
    system_parent_id BIGINT;
    admin_parent_id BIGINT;
    group_parent_id BIGINT;
    menu_parent_id BIGINT;
    tenant_parent_id BIGINT;
    llm_parent_id BIGINT;
    git_parent_id BIGINT;
    knowledge_parent_id BIGINT;
    pipeline_parent_id BIGINT;
    project_parent_id BIGINT;
    project_access_parent_id BIGINT;
    skills_parent_id BIGINT;
    agent_parent_id BIGINT;
BEGIN
    SELECT id INTO system_parent_id FROM sys_menu WHERE path = '/system' ORDER BY id LIMIT 1;
    SELECT id INTO admin_parent_id FROM sys_menu WHERE permission = 'system:admin:list' ORDER BY id LIMIT 1;
    SELECT id INTO group_parent_id FROM sys_menu WHERE permission = 'system:group:list' ORDER BY id LIMIT 1;
    SELECT id INTO menu_parent_id FROM sys_menu WHERE permission = 'system:menu:list' ORDER BY id LIMIT 1;
    SELECT id INTO tenant_parent_id FROM sys_menu WHERE permission = 'system:tenant:list' ORDER BY id LIMIT 1;
    SELECT id INTO llm_parent_id FROM sys_menu WHERE permission = 'system:llm:list' ORDER BY id LIMIT 1;
    SELECT id INTO git_parent_id FROM sys_menu WHERE permission = 'system:git:list' ORDER BY id LIMIT 1;
    SELECT id INTO knowledge_parent_id FROM sys_menu WHERE permission = 'system:knowledge:list' ORDER BY id LIMIT 1;
    SELECT id INTO pipeline_parent_id FROM sys_menu WHERE path = '/pipeline' ORDER BY id LIMIT 1;
    SELECT id INTO project_parent_id FROM sys_menu WHERE path = '/project' ORDER BY id LIMIT 1;
    SELECT id INTO project_access_parent_id FROM sys_menu WHERE permission = 'portal:developer' ORDER BY id LIMIT 1;
    SELECT id INTO skills_parent_id FROM sys_menu WHERE path = '/skills/market' ORDER BY id LIMIT 1;
    SELECT id INTO agent_parent_id FROM sys_menu WHERE path = '/agent' ORDER BY id LIMIT 1;

    IF skills_parent_id IS NOT NULL THEN
        UPDATE sys_menu
        SET permission = 'skills:market:list',
            update_time = now_ms
        WHERE id = skills_parent_id
          AND COALESCE(permission, '') = '';
    END IF;

    SELECT id INTO skills_parent_id FROM sys_menu WHERE permission = 'skills:market:list' ORDER BY id LIMIT 1;

    IF agent_parent_id IS NULL THEN
        INSERT INTO sys_menu (
            parent_id, name, path, component, permission, icon, menu_type, visible, sort,
            status, tenant_id, create_time, update_time
        )
        VALUES (0, '智能体', '/agent', 'Layout', NULL, 'RobotOutlined', 1, 0, 90, 1, 1, now_ms, now_ms)
        RETURNING id INTO agent_parent_id;
    END IF;

    INSERT INTO sys_menu (
        parent_id, name, path, component, permission, icon, menu_type, visible, sort,
        status, tenant_id, create_time, update_time
    )
    SELECT item.parent_id, item.name, NULL, NULL, item.permission, NULL, 3, 0, item.sort, 1, 1, now_ms, now_ms
    FROM (
        VALUES
            (admin_parent_id, '新增用户', 'system:admin:create', 11),
            (admin_parent_id, '查看用户', 'system:admin:view', 12),
            (admin_parent_id, '编辑用户', 'system:admin:edit', 13),
            (admin_parent_id, '删除用户', 'system:admin:delete', 14),
            (group_parent_id, '新增角色', 'system:group:create', 21),
            (group_parent_id, '查看角色', 'system:group:view', 22),
            (group_parent_id, '编辑角色', 'system:group:edit', 23),
            (group_parent_id, '删除角色', 'system:group:delete', 24),
            (menu_parent_id, '新增菜单', 'system:menu:create', 31),
            (menu_parent_id, '查看菜单', 'system:menu:view', 32),
            (menu_parent_id, '编辑菜单', 'system:menu:edit', 33),
            (menu_parent_id, '删除菜单', 'system:menu:delete', 34),
            (tenant_parent_id, '新增租户', 'system:tenant:create', 41),
            (tenant_parent_id, '查看租户', 'system:tenant:view', 42),
            (tenant_parent_id, '编辑租户', 'system:tenant:edit', 43),
            (tenant_parent_id, '删除租户', 'system:tenant:delete', 44),
            (llm_parent_id, '新增 LLM 配置', 'system:llm:create', 51),
            (llm_parent_id, '查看 LLM 配置', 'system:llm:view', 52),
            (llm_parent_id, '编辑 LLM 配置', 'system:llm:edit', 53),
            (llm_parent_id, '删除 LLM 配置', 'system:llm:delete', 54),
            (llm_parent_id, '测试 LLM 配置', 'system:llm:test', 55),
            (llm_parent_id, '设为默认 LLM', 'system:llm:default', 56),
            (git_parent_id, '新增 Git 配置', 'system:git:create', 61),
            (git_parent_id, '查看 Git 配置', 'system:git:view', 62),
            (git_parent_id, '编辑 Git 配置', 'system:git:edit', 63),
            (git_parent_id, '删除 Git 配置', 'system:git:delete', 64),
            (git_parent_id, '测试 Git 配置', 'system:git:test', 65),
            (git_parent_id, '设为默认 Git', 'system:git:default', 66),
            (knowledge_parent_id, '搜索知识', 'knowledge:search:list', 71),
            (knowledge_parent_id, '新增知识', 'knowledge:create:create', 72),
            (knowledge_parent_id, '查看知识', 'knowledge:index:view', 73),
            (knowledge_parent_id, '编辑知识', 'knowledge:index:edit', 74),
            (knowledge_parent_id, '删除知识', 'knowledge:index:delete', 75),
            (knowledge_parent_id, '知识图谱查看', 'knowledge:graph:view', 76),
            (knowledge_parent_id, '知识图谱维护', 'knowledge:graph:create', 77),
            (knowledge_parent_id, '知识图谱删除', 'knowledge:graph:delete', 78),
            (pipeline_parent_id, '删除流水线', 'flow:pipeline:delete', 37),
            (pipeline_parent_id, '查看流水线模板', 'flow:pipeline:templates', 38),
            (pipeline_parent_id, '查看 Pipeline Skills', 'flow:pipeline:skills', 39),
            (pipeline_parent_id, '查看默认提示词', 'flow:pipeline:defaults', 40),
            (pipeline_parent_id, '查看项目提示词', 'flow:pipeline:prompts', 41),
            (pipeline_parent_id, '更新 Skill 配置', 'flow:pipeline:skill-config', 42),
            (pipeline_parent_id, '查看流水线文件', 'flow:pipeline:files', 43),
            (pipeline_parent_id, '查看 Git 状态', 'flow:pipeline:git-status', 44),
            (pipeline_parent_id, '查看部署状态', 'flow:pipeline:deploy-status', 45),
            (pipeline_parent_id, '分析项目', 'flow:pipeline:analyze', 46),
            (pipeline_parent_id, '查看项目知识', 'flow:pipeline:knowledge', 47),
            (pipeline_parent_id, '查看/编辑项目 Skill', 'flow:pipeline:skill', 48),
            (project_access_parent_id, '创建项目', 'project:create', 80),
            (project_parent_id, '项目列表', 'generator:projects:list', 90),
            (project_parent_id, '创建项目', 'generator:projects:create', 91),
            (project_parent_id, '查看项目', 'generator:projects:view', 92),
            (project_parent_id, '编辑项目', 'generator:projects:edit', 93),
            (project_parent_id, '删除项目', 'generator:projects:delete', 94),
            (project_parent_id, '重新生成项目', 'generator:projects:regenerate', 95),
            (project_parent_id, '模板列表', 'generator:templates:list', 100),
            (project_parent_id, '查看模板', 'generator:templates:view', 101),
            (project_parent_id, '创建模板', 'generator:templates:create', 102),
            (project_parent_id, '编辑模板', 'generator:templates:edit', 103),
            (project_parent_id, '删除模板', 'generator:templates:delete', 104),
            (project_parent_id, '语言列表', 'generator:languages:list', 105),
            (project_parent_id, '测试任务列表', 'deploy:tests:list', 110),
            (project_parent_id, '创建测试任务', 'deploy:tests:create', 111),
            (project_parent_id, '查看测试任务', 'deploy:tests:view', 112),
            (project_parent_id, '执行测试任务', 'deploy:tests:execute', 113),
            (project_parent_id, '取消测试任务', 'deploy:tests:cancel', 114),
            (skills_parent_id, '查看技能市场', 'skills:market:list', 120),
            (skills_parent_id, '查看技能详情', 'skills:market:view', 121),
            (skills_parent_id, '发布/下载/评分技能', 'skills:market:create', 122),
            (skills_parent_id, '删除我的技能', 'skills:market:delete', 123),
            (skills_parent_id, '管理本地技能', 'skills:manage:create', 124),
            (agent_parent_id, '聊天会话查看', 'agent:chat:view', 130),
            (agent_parent_id, '聊天会话创建', 'agent:chat:create', 131),
            (agent_parent_id, '聊天会话删除', 'agent:chat:delete', 132),
            (agent_parent_id, '智能体项目列表', 'agent:projects:list', 140),
            (agent_parent_id, '智能体项目创建', 'agent:projects:create', 141),
            (agent_parent_id, '智能体项目查看', 'agent:projects:view', 142),
            (agent_parent_id, '智能体项目编辑', 'agent:projects:edit', 143),
            (agent_parent_id, '智能体项目删除', 'agent:projects:delete', 144),
            (agent_parent_id, '智能体任务列表', 'agent:tasks:list', 150),
            (agent_parent_id, '智能体任务创建', 'agent:tasks:create', 151),
            (agent_parent_id, '智能体任务查看', 'agent:tasks:view', 152),
            (agent_parent_id, '智能体任务编辑', 'agent:tasks:edit', 153),
            (agent_parent_id, '智能体任务删除', 'agent:tasks:delete', 154),
            (agent_parent_id, '缺陷列表', 'agent:bugs:list', 160),
            (agent_parent_id, '缺陷创建', 'agent:bugs:create', 161),
            (agent_parent_id, '缺陷查看', 'agent:bugs:view', 162),
            (agent_parent_id, '缺陷编辑', 'agent:bugs:edit', 163),
            (agent_parent_id, '缺陷删除', 'agent:bugs:delete', 164)
    ) AS item(parent_id, name, permission, sort)
    WHERE item.parent_id IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM sys_menu WHERE sys_menu.permission = item.permission
      );
END $$;
