-- =============================================
-- 看板系统数据库表结构 (PostgreSQL)
-- 版本: 1.0.0
-- 日期: 2026-03-13
-- 说明: 智能体协作看板相关表
-- =============================================

-- ---------------------------------------------
-- 1. 智能体表 (agents)
-- ---------------------------------------------
DROP TABLE IF EXISTS agents CASCADE;
CREATE TABLE agents (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE COMMENT '智能体编码(唯一标识)',
    name VARCHAR(100) NOT NULL COMMENT '智能体名称',
    avatar VARCHAR(255) COMMENT '头像URL',
    description TEXT COMMENT '智能体描述',
    capabilities TEXT[] COMMENT '能力标签数组',
    personality TEXT COMMENT '性格描述',
    system_prompt TEXT COMMENT '系统提示词',
    model_config JSONB COMMENT '模型配置JSON',
    tools JSONB COMMENT '工具配置JSON',
    memory_config JSONB COMMENT '记忆配置JSON',
    max_concurrent_tasks INTEGER DEFAULT 3 COMMENT '最大并发任务数',
    status SMALLINT NOT NULL DEFAULT 1 COMMENT '状态: 0禁用 1启用',
    tenant_id BIGINT NOT NULL DEFAULT 0 COMMENT '租户ID',
    admin_id BIGINT COMMENT '创建者ID',
    create_time BIGINT NOT NULL COMMENT '创建时间(毫秒时间戳)',
    update_time BIGINT NOT NULL COMMENT '更新时间(毫秒时间戳)',
    
    CONSTRAINT fk_agents_admin FOREIGN KEY (admin_id) REFERENCES sys_admin(id) ON DELETE SET NULL
);

-- 索引
CREATE INDEX idx_agents_code ON agents(code);
CREATE INDEX idx_agents_status ON agents(status);
CREATE INDEX idx_agents_tenant_id ON agents(tenant_id);
CREATE INDEX idx_agents_admin_id ON agents(admin_id);

COMMENT ON TABLE agents IS '智能体表';
COMMENT ON COLUMN agents.id IS '主键ID';
COMMENT ON COLUMN agents.code IS '智能体编码(唯一标识)';
COMMENT ON COLUMN agents.name IS '智能体名称';
COMMENT ON COLUMN agents.avatar IS '头像URL';
COMMENT ON COLUMN agents.description IS '智能体描述';
COMMENT ON COLUMN agents.capabilities IS '能力标签数组';
COMMENT ON COLUMN agents.personality IS '性格描述';
COMMENT ON COLUMN agents.system_prompt IS '系统提示词';
COMMENT ON COLUMN agents.model_config IS '模型配置JSON';
COMMENT ON COLUMN agents.tools IS '工具配置JSON';
COMMENT ON COLUMN agents.memory_config IS '记忆配置JSON';
COMMENT ON COLUMN agents.max_concurrent_tasks IS '最大并发任务数';
COMMENT ON COLUMN agents.status IS '状态: 0禁用 1启用';
COMMENT ON COLUMN agents.tenant_id IS '租户ID';
COMMENT ON COLUMN agents.admin_id IS '创建者ID';
COMMENT ON COLUMN agents.create_time IS '创建时间(毫秒时间戳)';
COMMENT ON COLUMN agents.update_time IS '更新时间(毫秒时间戳)';

-- ---------------------------------------------
-- 2. 任务表 (tasks)
-- ---------------------------------------------
DROP TABLE IF EXISTS tasks CASCADE;
CREATE TABLE tasks (
    id BIGSERIAL PRIMARY KEY,
    task_no VARCHAR(50) NOT NULL UNIQUE COMMENT '任务编号',
    title VARCHAR(255) NOT NULL COMMENT '任务标题',
    description TEXT COMMENT '任务描述',
    type VARCHAR(20) NOT NULL COMMENT '任务类型: feature/bug/optimize/test/docs',
    priority VARCHAR(20) NOT NULL DEFAULT 'medium' COMMENT '优先级: critical/high/medium/low',
    status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '状态: pending/assigned/running/completed/failed/cancelled',
    progress SMALLINT DEFAULT 0 COMMENT '进度(0-100)',
    
    -- 关联关系
    assignee_id BIGINT COMMENT '主负责人(智能体ID)',
    creator_id BIGINT NOT NULL COMMENT '创建者(管理员ID)',
    parent_task_id BIGINT COMMENT '父任务ID',
    project_id BIGINT COMMENT '项目ID',
    
    -- 执行信息
    execution_log TEXT COMMENT '执行日志',
    error_msg TEXT COMMENT '错误信息',
    result TEXT COMMENT '执行结果',
    
    -- 时间信息
    estimated_hours DECIMAL(5,2) COMMENT '预估工时(小时)',
    actual_hours DECIMAL(5,2) COMMENT '实际工时(小时)',
    start_time BIGINT COMMENT '开始时间(毫秒时间戳)',
    end_time BIGINT COMMENT '结束时间(毫秒时间戳)',
    deadline BIGINT COMMENT '截止时间(毫秒时间戳)',
    
    -- 元数据
    tags TEXT[] COMMENT '标签数组',
    attachments JSONB COMMENT '附件信息JSON',
    extra_config JSONB COMMENT '额外配置JSON',
    
    tenant_id BIGINT NOT NULL DEFAULT 0 COMMENT '租户ID',
    create_time BIGINT NOT NULL COMMENT '创建时间(毫秒时间戳)',
    update_time BIGINT NOT NULL COMMENT '更新时间(毫秒时间戳)',
    
    CONSTRAINT fk_tasks_assignee FOREIGN KEY (assignee_id) REFERENCES agents(id) ON DELETE SET NULL,
    CONSTRAINT fk_tasks_creator FOREIGN KEY (creator_id) REFERENCES sys_admin(id) ON DELETE CASCADE,
    CONSTRAINT fk_tasks_parent FOREIGN KEY (parent_task_id) REFERENCES tasks(id) ON DELETE SET NULL
);

-- 索引
CREATE INDEX idx_tasks_task_no ON tasks(task_no);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_priority ON tasks(priority);
CREATE INDEX idx_tasks_type ON tasks(type);
CREATE INDEX idx_tasks_assignee_id ON tasks(assignee_id);
CREATE INDEX idx_tasks_creator_id ON tasks(creator_id);
CREATE INDEX idx_tasks_parent_task_id ON tasks(parent_task_id);
CREATE INDEX idx_tasks_project_id ON tasks(project_id);
CREATE INDEX idx_tasks_tenant_id ON tasks(tenant_id);
CREATE INDEX idx_tasks_create_time ON tasks(create_time);
CREATE INDEX idx_tasks_deadline ON tasks(deadline);

COMMENT ON TABLE tasks IS '任务表';
COMMENT ON COLUMN tasks.id IS '主键ID';
COMMENT ON COLUMN tasks.task_no IS '任务编号';
COMMENT ON COLUMN tasks.title IS '任务标题';
COMMENT ON COLUMN tasks.description IS '任务描述';
COMMENT ON COLUMN tasks.type IS '任务类型: feature/bug/optimize/test/docs';
COMMENT ON COLUMN tasks.priority IS '优先级: critical/high/medium/low';
COMMENT ON COLUMN tasks.status IS '状态: pending/assigned/running/completed/failed/cancelled';
COMMENT ON COLUMN tasks.progress IS '进度(0-100)';
COMMENT ON COLUMN tasks.assignee_id IS '主负责人(智能体ID)';
COMMENT ON COLUMN tasks.creator_id IS '创建者(管理员ID)';
COMMENT ON COLUMN tasks.parent_task_id IS '父任务ID';
COMMENT ON COLUMN tasks.project_id IS '项目ID';
COMMENT ON COLUMN tasks.execution_log IS '执行日志';
COMMENT ON COLUMN tasks.error_msg IS '错误信息';
COMMENT ON COLUMN tasks.result IS '执行结果';
COMMENT ON COLUMN tasks.estimated_hours IS '预估工时(小时)';
COMMENT ON COLUMN tasks.actual_hours IS '实际工时(小时)';
COMMENT ON COLUMN tasks.start_time IS '开始时间(毫秒时间戳)';
COMMENT ON COLUMN tasks.end_time IS '结束时间(毫秒时间戳)';
COMMENT ON COLUMN tasks.deadline IS '截止时间(毫秒时间戳)';
COMMENT ON COLUMN tasks.tags IS '标签数组';
COMMENT ON COLUMN tasks.attachments IS '附件信息JSON';
COMMENT ON COLUMN tasks.extra_config IS '额外配置JSON';
COMMENT ON COLUMN tasks.tenant_id IS '租户ID';
COMMENT ON COLUMN tasks.create_time IS '创建时间(毫秒时间戳)';
COMMENT ON COLUMN tasks.update_time IS '更新时间(毫秒时间戳)';

-- ---------------------------------------------
-- 3. 智能体会话表 (agent_sessions)
-- ---------------------------------------------
DROP TABLE IF EXISTS agent_sessions CASCADE;
CREATE TABLE agent_sessions (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(50) NOT NULL UNIQUE COMMENT '会话ID',
    agent_id BIGINT NOT NULL COMMENT '智能体ID',
    admin_id BIGINT COMMENT '管理员ID(人工监督会话)',
    
    -- 会话信息
    session_type VARCHAR(20) NOT NULL COMMENT '会话类型: autonomous/supervised/collaboration',
    title VARCHAR(255) COMMENT '会话标题',
    description TEXT COMMENT '会话描述',
    context TEXT COMMENT '会话上下文',
    
    -- 关联任务
    task_id BIGINT COMMENT '关联任务ID',
    
    -- 会话状态
    status VARCHAR(20) NOT NULL DEFAULT 'active' COMMENT '状态: active/paused/completed/failed',
    message_count INTEGER DEFAULT 0 COMMENT '消息数量',
    token_count INTEGER DEFAULT 0 COMMENT 'Token消耗',
    
    -- 配置信息
    config JSONB COMMENT '会话配置JSON',
    metadata JSONB COMMENT '元数据JSON',
    
    -- 时间信息
    start_time BIGINT NOT NULL COMMENT '开始时间(毫秒时间戳)',
    end_time BIGINT COMMENT '结束时间(毫秒时间戳)',
    duration INTEGER COMMENT '持续时间(毫秒)',
    
    tenant_id BIGINT NOT NULL DEFAULT 0 COMMENT '租户ID',
    create_time BIGINT NOT NULL COMMENT '创建时间(毫秒时间戳)',
    update_time BIGINT NOT NULL COMMENT '更新时间(毫秒时间戳)',
    
    CONSTRAINT fk_sessions_agent FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
    CONSTRAINT fk_sessions_admin FOREIGN KEY (admin_id) REFERENCES sys_admin(id) ON DELETE SET NULL,
    CONSTRAINT fk_sessions_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
);

-- 索引
CREATE INDEX idx_agent_sessions_session_id ON agent_sessions(session_id);
CREATE INDEX idx_agent_sessions_agent_id ON agent_sessions(agent_id);
CREATE INDEX idx_agent_sessions_admin_id ON agent_sessions(admin_id);
CREATE INDEX idx_agent_sessions_task_id ON agent_sessions(task_id);
CREATE INDEX idx_agent_sessions_status ON agent_sessions(status);
CREATE INDEX idx_agent_sessions_session_type ON agent_sessions(session_type);
CREATE INDEX idx_agent_sessions_tenant_id ON agent_sessions(tenant_id);
CREATE INDEX idx_agent_sessions_start_time ON agent_sessions(start_time);

COMMENT ON TABLE agent_sessions IS '智能体会话表';
COMMENT ON COLUMN agent_sessions.id IS '主键ID';
COMMENT ON COLUMN agent_sessions.session_id IS '会话ID';
COMMENT ON COLUMN agent_sessions.agent_id IS '智能体ID';
COMMENT ON COLUMN agent_sessions.admin_id IS '管理员ID(人工监督会话)';
COMMENT ON COLUMN agent_sessions.session_type IS '会话类型: autonomous/supervised/collaboration';
COMMENT ON COLUMN agent_sessions.title IS '会话标题';
COMMENT ON COLUMN agent_sessions.description IS '会话描述';
COMMENT ON COLUMN agent_sessions.context IS '会话上下文';
COMMENT ON COLUMN agent_sessions.task_id IS '关联任务ID';
COMMENT ON COLUMN agent_sessions.status IS '状态: active/paused/completed/failed';
COMMENT ON COLUMN agent_sessions.message_count IS '消息数量';
COMMENT ON COLUMN agent_sessions.token_count IS 'Token消耗';
COMMENT ON COLUMN agent_sessions.config IS '会话配置JSON';
COMMENT ON COLUMN agent_sessions.metadata IS '元数据JSON';
COMMENT ON COLUMN agent_sessions.start_time IS '开始时间(毫秒时间戳)';
COMMENT ON COLUMN agent_sessions.end_time IS '结束时间(毫秒时间戳)';
COMMENT ON COLUMN agent_sessions.duration IS '持续时间(毫秒)';
COMMENT ON COLUMN agent_sessions.tenant_id IS '租户ID';
COMMENT ON COLUMN agent_sessions.create_time IS '创建时间(毫秒时间戳)';
COMMENT ON COLUMN agent_sessions.update_time IS '更新时间(毫秒时间戳)';

-- ---------------------------------------------
-- 4. 协作记录表 (collaboration_records)
-- ---------------------------------------------
DROP TABLE IF EXISTS collaboration_records CASCADE;
CREATE TABLE collaboration_records (
    id BIGSERIAL PRIMARY KEY,
    record_id VARCHAR(50) NOT NULL UNIQUE COMMENT '记录ID',
    
    -- 关联信息
    task_id BIGINT COMMENT '任务ID',
    session_id BIGINT COMMENT '会话ID',
    
    -- 协作参与者
    primary_agent_id BIGINT NOT NULL COMMENT '主要智能体ID',
    collaborator_agent_id BIGINT COMMENT '协作智能体ID',
    admin_id BIGINT COMMENT '参与的管理员ID',
    
    -- 协作信息
    collaboration_type VARCHAR(20) NOT NULL COMMENT '协作类型: delegation/assistance/review/handoff',
    action VARCHAR(50) NOT NULL COMMENT '动作: assign/transfer/request_help/review/approve/reject',
    
    -- 内容信息
    title VARCHAR(255) COMMENT '记录标题',
    content TEXT COMMENT '协作内容',
    context TEXT COMMENT '上下文信息',
    attachments JSONB COMMENT '附件信息JSON',
    
    -- 执行结果
    status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '状态: pending/accepted/rejected/completed',
    result TEXT COMMENT '执行结果',
    feedback TEXT COMMENT '反馈信息',
    
    -- 时间信息
    start_time BIGINT COMMENT '开始时间(毫秒时间戳)',
    end_time BIGINT COMMENT '结束时间(毫秒时间戳)',
    duration INTEGER COMMENT '持续时间(毫秒)',
    
    -- 评分和指标
    quality_score DECIMAL(3,2) COMMENT '质量评分(0-5)',
    efficiency_score DECIMAL(3,2) COMMENT '效率评分(0-5)',
    
    tenant_id BIGINT NOT NULL DEFAULT 0 COMMENT '租户ID',
    create_time BIGINT NOT NULL COMMENT '创建时间(毫秒时间戳)',
    update_time BIGINT NOT NULL COMMENT '更新时间(毫秒时间戳)',
    
    CONSTRAINT fk_collab_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL,
    CONSTRAINT fk_collab_session FOREIGN KEY (session_id) REFERENCES agent_sessions(id) ON DELETE SET NULL,
    CONSTRAINT fk_collab_primary_agent FOREIGN KEY (primary_agent_id) REFERENCES agents(id) ON DELETE CASCADE,
    CONSTRAINT fk_collab_collaborator_agent FOREIGN KEY (collaborator_agent_id) REFERENCES agents(id) ON DELETE SET NULL,
    CONSTRAINT fk_collab_admin FOREIGN KEY (admin_id) REFERENCES sys_admin(id) ON DELETE SET NULL
);

-- 索引
CREATE INDEX idx_collaboration_records_record_id ON collaboration_records(record_id);
CREATE INDEX idx_collaboration_records_task_id ON collaboration_records(task_id);
CREATE INDEX idx_collaboration_records_session_id ON collaboration_records(session_id);
CREATE INDEX idx_collaboration_records_primary_agent_id ON collaboration_records(primary_agent_id);
CREATE INDEX idx_collaboration_records_collaborator_agent_id ON collaboration_records(collaborator_agent_id);
CREATE INDEX idx_collaboration_records_admin_id ON collaboration_records(admin_id);
CREATE INDEX idx_collaboration_records_collaboration_type ON collaboration_records(collaboration_type);
CREATE INDEX idx_collaboration_records_action ON collaboration_records(action);
CREATE INDEX idx_collaboration_records_status ON collaboration_records(status);
CREATE INDEX idx_collaboration_records_tenant_id ON collaboration_records(tenant_id);
CREATE INDEX idx_collaboration_records_create_time ON collaboration_records(create_time);

COMMENT ON TABLE collaboration_records IS '协作记录表';
COMMENT ON COLUMN collaboration_records.id IS '主键ID';
COMMENT ON COLUMN collaboration_records.record_id IS '记录ID';
COMMENT ON COLUMN collaboration_records.task_id IS '任务ID';
COMMENT ON COLUMN collaboration_records.session_id IS '会话ID';
COMMENT ON COLUMN collaboration_records.primary_agent_id IS '主要智能体ID';
COMMENT ON COLUMN collaboration_records.collaborator_agent_id IS '协作智能体ID';
COMMENT ON COLUMN collaboration_records.admin_id IS '参与的管理员ID';
COMMENT ON COLUMN collaboration_records.collaboration_type IS '协作类型: delegation/assistance/review/handoff';
COMMENT ON COLUMN collaboration_records.action IS '动作: assign/transfer/requestHelp/review/approve/reject';
COMMENT ON COLUMN collaboration_records.title IS '记录标题';
COMMENT ON COLUMN collaboration_records.content IS '协作内容';
COMMENT ON COLUMN collaboration_records.context IS '上下文信息';
COMMENT ON COLUMN collaboration_records.attachments IS '附件信息JSON';
COMMENT ON COLUMN collaboration_records.status IS '状态: pending/accepted/rejected/completed';
COMMENT ON COLUMN collaboration_records.result IS '执行结果';
COMMENT ON COLUMN collaboration_records.feedback IS '反馈信息';
COMMENT ON COLUMN collaboration_records.start_time IS '开始时间(毫秒时间戳)';
COMMENT ON COLUMN collaboration_records.end_time IS '结束时间(毫秒时间戳)';
COMMENT ON COLUMN collaboration_records.duration IS '持续时间(毫秒)';
COMMENT ON COLUMN collaboration_records.quality_score IS '质量评分(0-5)';
COMMENT ON COLUMN collaboration_records.efficiency_score IS '效率评分(0-5)';
COMMENT ON COLUMN collaboration_records.tenant_id IS '租户ID';
COMMENT ON COLUMN collaboration_records.create_time IS '创建时间(毫秒时间戳)';
COMMENT ON COLUMN collaboration_records.update_time IS '更新时间(毫秒时间戳)';

-- ---------------------------------------------
-- 5. 会话消息表 (session_messages) - 可选扩展
-- ---------------------------------------------
DROP TABLE IF EXISTS session_messages CASCADE;
CREATE TABLE session_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL COMMENT '会话ID',
    message_id VARCHAR(50) NOT NULL UNIQUE COMMENT '消息ID',
    
    -- 发送者信息
    sender_type VARCHAR(20) NOT NULL COMMENT '发送者类型: agent/admin/system',
    sender_id BIGINT NOT NULL COMMENT '发送者ID',
    
    -- 消息内容
    message_type VARCHAR(20) NOT NULL COMMENT '消息类型: text/code/file/action',
    content TEXT NOT NULL COMMENT '消息内容',
    
    -- 元数据
    metadata JSONB COMMENT '元数据JSON',
    attachments JSONB COMMENT '附件信息JSON',
    
    -- Token统计
    tokens_used INTEGER DEFAULT 0 COMMENT 'Token消耗',
    
    tenant_id BIGINT NOT NULL DEFAULT 0 COMMENT '租户ID',
    create_time BIGINT NOT NULL COMMENT '创建时间(毫秒时间戳)',
    
    CONSTRAINT fk_messages_session FOREIGN KEY (session_id) REFERENCES agent_sessions(id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX idx_session_messages_session_id ON session_messages(session_id);
CREATE INDEX idx_session_messages_message_id ON session_messages(message_id);
CREATE INDEX idx_session_messages_sender_type ON session_messages(sender_type);
CREATE INDEX idx_session_messages_sender_id ON session_messages(sender_id);
CREATE INDEX idx_session_messages_tenant_id ON session_messages(tenant_id);
CREATE INDEX idx_session_messages_create_time ON session_messages(create_time);

COMMENT ON TABLE session_messages IS '会话消息表';
COMMENT ON COLUMN session_messages.id IS '主键ID';
COMMENT ON COLUMN session_messages.session_id IS '会话ID';
COMMENT ON COLUMN session_messages.message_id IS '消息ID';
COMMENT ON COLUMN session_messages.sender_type IS '发送者类型: agent/admin/system';
COMMENT ON COLUMN session_messages.sender_id IS '发送者ID';
COMMENT ON COLUMN session_messages.message_type IS '消息类型: text/code/file/action';
COMMENT ON COLUMN session_messages.content IS '消息内容';
COMMENT ON COLUMN session_messages.metadata IS '元数据JSON';
COMMENT ON COLUMN session_messages.attachments IS '附件信息JSON';
COMMENT ON COLUMN session_messages.tokens_used IS 'Token消耗';
COMMENT ON COLUMN session_messages.tenant_id IS '租户ID';
COMMENT ON COLUMN session_messages.create_time IS '创建时间(毫秒时间戳)';

-- ---------------------------------------------
-- 初始数据 - 6个智能体
-- ---------------------------------------------

-- 插入6个智能体 (使用 EXTRACT(EPOCH FROM NOW()) * 1000 获取毫秒时间戳)
INSERT INTO agents (code, name, avatar, description, capabilities, personality, system_prompt, model_config, max_concurrent_tasks, status, tenant_id, admin_id, create_time, update_time) VALUES
-- 1. 产品经理智能体 (PM)
(
    'PM',
    '产品经理',
    'https://download-cyagent.hctest.tech/group1/M00/00/63/CgABhGmo6YaAfdIVABN459NE988239.png',
    '负责需求收集、需求分析、PRD文档撰写。通过多轮对话澄清需求细节，输出标准化需求文档。',
    ARRAY['需求分析', 'PRD撰写', '用户研究', '竞品分析', '需求优先级', '验收标准', '沟通协调'],
    '专业、友好、善于引导对话',
    '你是产品经理智能体，负责与用户进行需求沟通。通过多轮对话澄清需求细节，当用户确认后输出标准化的PRD文档。关注功能目标、用户角色、核心流程、边界条件和验收标准。',
    '{"model": "claude-sonnet-4-20250514", "temperature": 0.7, "max_tokens": 4096}',
    5,
    1,
    1,
    1,
    EXTRACT(EPOCH FROM NOW()) * 1000,
    EXTRACT(EPOCH FROM NOW()) * 1000
),

-- 2. 项目经理智能体 (PJM)
(
    'PJM',
    '项目经理',
    'https://download-cyagent.hctest.tech/group1/M00/00/63/CgABhGmo6YaAfdIVABN459NE988239.png',
    '负责项目规划、任务拆分、API契约定义、资源协调、风险控制。确保项目按时高质量交付。',
    ARRAY['项目规划', '任务拆分', 'API契约', '资源协调', '风险控制', '排期评估', '团队协作'],
    '稳重、高效、善于沟通和协调',
    '你是项目经理智能体，负责接收需求文档进行技术分析和任务拆分。将需求拆分为前端和后端任务，定义接口契约（OpenAPI 3.0），评估工作量并分发任务。',
    '{"model": "claude-sonnet-4-20250514", "temperature": 0.5, "max_tokens": 4096}',
    10,
    1,
    1,
    1,
    EXTRACT(EPOCH FROM NOW()) * 1000,
    EXTRACT(EPOCH FROM NOW()) * 1000
),

-- 3. 后端开发智能体 (BE)
(
    'BE',
    '后端开发',
    'https://download-cyagent.hctest.tech/group1/M00/00/63/CgABhGmo6YaAfdIVABN459NE988239.png',
    '精通后端技术栈：Go、Python、FastAPI。负责后端API开发、数据库设计、业务逻辑实现。',
    ARRAY['Go开发', 'Python开发', 'FastAPI', '数据库设计', 'API设计', '微服务', '性能优化'],
    '专业、严谨、注重代码质量和系统性能',
    '你是后端开发智能体，精通Go和Python后端技术栈。遵循最佳实践编写高质量、高性能、可维护的代码。关注API设计、数据一致性、异常处理和性能优化。',
    '{"model": "claude-sonnet-4-20250514", "temperature": 0.3, "max_tokens": 8192}',
    5,
    1,
    1,
    1,
    EXTRACT(EPOCH FROM NOW()) * 1000,
    EXTRACT(EPOCH FROM NOW()) * 1000
),

-- 4. 前端开发智能体 (FE)
(
    'FE',
    '前端开发',
    'https://download-cyagent.hctest.tech/group1/M00/00/63/CgABhGmo6YaAfdIVABN459NE988239.png',
    '精通前端技术栈：React、TypeScript、Ant Design。负责UI组件开发、前端架构、用户体验优化。',
    ARRAY['React开发', 'TypeScript', 'Ant Design', '前端架构', 'UI组件', '状态管理', '性能优化'],
    '细致、创新、注重用户体验和界面美观',
    '你是前端开发智能体，精通React和TypeScript前端技术栈。构建美观、易用、高性能的用户界面。关注组件化开发、状态管理（Zustand）、响应式设计和交互体验。',
    '{"model": "claude-sonnet-4-20250514", "temperature": 0.3, "max_tokens": 8192}',
    5,
    1,
    1,
    1,
    EXTRACT(EPOCH FROM NOW()) * 1000,
    EXTRACT(EPOCH FROM NOW()) * 1000
),

-- 5. QA测试智能体 (QA)
(
    'QA',
    '测试工程师',
    'https://download-cyagent.hctest.tech/group1/M00/00/63/CgABhGmo6YaAfdIVABN459NE988239.png',
    '负责测试策略制定、测试用例设计、自动化测试开发、缺陷跟踪。确保产品质量。',
    ARRAY['测试策略', '测试用例', '自动化测试', '性能测试', '缺陷管理', '质量保证', '回归测试'],
    '细致、严谨、追求高质量',
    '你是QA测试智能体，负责产品的质量保证工作。制定全面的测试策略，设计高质量的测试用例，执行功能测试、性能测试和自动化测试。关注产品质量、测试覆盖率和缺陷追踪。',
    '{"model": "claude-sonnet-4-20250514", "temperature": 0.4, "max_tokens": 4096}',
    5,
    1,
    1,
    1,
    EXTRACT(EPOCH FROM NOW()) * 1000,
    EXTRACT(EPOCH FROM NOW()) * 1000
),

-- 6. 汇报智能体 (RPT)
(
    'RPT',
    '项目汇报',
    'https://download-cyagent.hctest.tech/group1/M00/00/63/CgABhGmo6YaAfdIVABN459NE988239.png',
    '负责汇总项目进度信息，生成结构化的项目进度报告。识别风险和阻塞项，支持进度查询。',
    ARRAY['进度汇总', '报告生成', '风险识别', '数据分析', '可视化', '进度跟踪', '沟通汇报'],
    '简洁、清晰、面向非技术领导',
    '你是项目汇报智能体，负责汇总所有开发分身的进度信息，生成结构化的项目进度报告供领导查阅。报告简练有力，聚焦做了什么、还剩什么、有什么问题。',
    '{"model": "claude-sonnet-4-20250514", "temperature": 0.5, "max_tokens": 4096}',
    10,
    1,
    1,
    1,
    EXTRACT(EPOCH FROM NOW()) * 1000,
    EXTRACT(EPOCH FROM NOW()) * 1000
);

-- 验证插入结果
SELECT id, code, name, status, max_concurrent_tasks FROM agents;

-- =============================================
-- 完成提示
-- =============================================
-- 看板系统数据表创建完成！
-- 
-- 已创建表:
-- 1. agents - 智能体表
-- 2. tasks - 任务表
-- 3. agent_sessions - 智能体会话表
-- 4. collaboration_records - 协作记录表
-- 5. session_messages - 会话消息表(扩展)
--
-- 已插入数据:
-- - 6个智能体: PM(产品经理)、PJM(项目经理)、BE(后端开发)、FE(前端开发)、QA(测试)、RPT(汇报)
-- =============================================
