-- =====================================================
-- 多智能体数字分身系统数据库表结构 (PostgreSQL)
-- 创建时间: 2026-02-27
-- =====================================================

-- ---------------------------------------------------
-- 1. 项目表 (agent_project)
-- 存储分身协作的项目信息
-- ---------------------------------------------------
DROP TABLE IF EXISTS agent_project CASCADE;
CREATE TABLE agent_project (
    id BIGSERIAL PRIMARY KEY,
    project_code VARCHAR(64) NOT NULL,
    project_name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    priority VARCHAR(16) NOT NULL DEFAULT 'P2',
    tenant_id BIGINT NOT NULL,
    creator_id BIGINT NOT NULL,
    start_time BIGINT,
    end_time BIGINT,
    create_time BIGINT NOT NULL,
    update_time BIGINT NOT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX uk_project_code ON agent_project(project_code);
CREATE INDEX idx_project_tenant ON agent_project(tenant_id);
CREATE INDEX idx_project_status ON agent_project(status);
CREATE INDEX idx_project_create_time ON agent_project(create_time);

COMMENT ON TABLE agent_project IS '分身项目表';
COMMENT ON COLUMN agent_project.id IS '主键ID';
COMMENT ON COLUMN agent_project.project_code IS '项目编码 PRJ-YYYYMMDD-XXX';
COMMENT ON COLUMN agent_project.project_name IS '项目名称';
COMMENT ON COLUMN agent_project.description IS '项目描述';
COMMENT ON COLUMN agent_project.status IS '项目状态: pending/active/completed/cancelled';
COMMENT ON COLUMN agent_project.priority IS '优先级: P0/P1/P2/P3';
COMMENT ON COLUMN agent_project.tenant_id IS '租户ID';
COMMENT ON COLUMN agent_project.creator_id IS '创建者ID';
COMMENT ON COLUMN agent_project.start_time IS '开始时间(毫秒时间戳)';
COMMENT ON COLUMN agent_project.end_time IS '结束时间(毫秒时间戳)';
COMMENT ON COLUMN agent_project.create_time IS '创建时间(毫秒时间戳)';
COMMENT ON COLUMN agent_project.update_time IS '更新时间(毫秒时间戳)';
COMMENT ON COLUMN agent_project.is_deleted IS '是否删除: 0否 1是';

-- ---------------------------------------------------
-- 2. 会话表 (agent_session)
-- 存储用户与分身的会话信息
-- ---------------------------------------------------
DROP TABLE IF EXISTS agent_session CASCADE;
CREATE TABLE agent_session (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    project_id BIGINT,
    user_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    title VARCHAR(255),
    current_agent VARCHAR(32),
    workflow_stage VARCHAR(32),
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    message_count INTEGER NOT NULL DEFAULT 0,
    last_message_time BIGINT,
    create_time BIGINT NOT NULL,
    update_time BIGINT NOT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX uk_session_id ON agent_session(session_id);
CREATE INDEX idx_session_project ON agent_session(project_id);
CREATE INDEX idx_session_user ON agent_session(user_id);
CREATE INDEX idx_session_tenant ON agent_session(tenant_id);
CREATE INDEX idx_session_status ON agent_session(status);

COMMENT ON TABLE agent_session IS '分身会话表';
COMMENT ON COLUMN agent_session.session_id IS '会话ID';
COMMENT ON COLUMN agent_session.project_id IS '关联项目ID';
COMMENT ON COLUMN agent_session.current_agent IS '当前活跃分身: PM/PJM/BE/FE/QA/RPT';
COMMENT ON COLUMN agent_session.workflow_stage IS '工作流阶段: requirement/planning/development/testing/report';
COMMENT ON COLUMN agent_session.message_count IS '消息数量';

-- ---------------------------------------------------
-- 3. 消息表 (agent_message)
-- 存储分身间的消息记录
-- ---------------------------------------------------
DROP TABLE IF EXISTS agent_message CASCADE;
CREATE TABLE agent_message (
    id BIGSERIAL PRIMARY KEY,
    msg_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    project_id BIGINT,
    from_agent VARCHAR(32) NOT NULL,
    to_agent VARCHAR(32) NOT NULL,
    msg_type VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    payload TEXT,
    token_count INTEGER,
    model_used VARCHAR(64),
    parent_msg_id VARCHAR(64),
    create_time BIGINT NOT NULL
);

CREATE UNIQUE INDEX uk_msg_id ON agent_message(msg_id);
CREATE INDEX idx_msg_session ON agent_message(session_id);
CREATE INDEX idx_msg_project ON agent_message(project_id);
CREATE INDEX idx_msg_from ON agent_message(from_agent);
CREATE INDEX idx_msg_to ON agent_message(to_agent);
CREATE INDEX idx_msg_type ON agent_message(msg_type);
CREATE INDEX idx_msg_create_time ON agent_message(create_time);

COMMENT ON TABLE agent_message IS '分身消息表';
COMMENT ON COLUMN agent_message.msg_id IS '消息ID';
COMMENT ON COLUMN agent_message.from_agent IS '发送方: USER/PM/PJM/BE/FE/QA/RPT';
COMMENT ON COLUMN agent_message.to_agent IS '接收方: USER/PM/PJM/BE/FE/QA/RPT/SYSTEM';
COMMENT ON COLUMN agent_message.msg_type IS '消息类型: chat/requirement_doc/task_list/api_contract/code_review/bug_report/test_report/daily_report';
COMMENT ON COLUMN agent_message.payload IS '消息载荷(JSON格式,结构化数据)';

-- ---------------------------------------------------
-- 4. 任务表 (agent_task)
-- 存储项目任务信息
-- ---------------------------------------------------
DROP TABLE IF EXISTS agent_task CASCADE;
CREATE TABLE agent_task (
    id BIGSERIAL PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    project_id BIGINT NOT NULL,
    session_id VARCHAR(64),
    parent_task_id VARCHAR(64),
    task_code VARCHAR(64),
    task_name VARCHAR(255) NOT NULL,
    description TEXT,
    task_type VARCHAR(32) NOT NULL,
    assignee VARCHAR(32),
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    priority VARCHAR(16) NOT NULL DEFAULT 'P2',
    estimated_hours DECIMAL(5,1),
    actual_hours DECIMAL(5,1),
    progress INTEGER DEFAULT 0,
    dependencies TEXT,
    tags VARCHAR(255),
    start_time BIGINT,
    end_time BIGINT,
    create_time BIGINT NOT NULL,
    update_time BIGINT NOT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX uk_task_id ON agent_task(task_id);
CREATE INDEX idx_task_project ON agent_task(project_id);
CREATE INDEX idx_task_session ON agent_task(session_id);
CREATE INDEX idx_task_assignee ON agent_task(assignee);
CREATE INDEX idx_task_status ON agent_task(status);
CREATE INDEX idx_task_type ON agent_task(task_type);

COMMENT ON TABLE agent_task IS '分身任务表';
COMMENT ON COLUMN agent_task.task_type IS '任务类型: api/frontend/test/doc/config';
COMMENT ON COLUMN agent_task.assignee IS '指派分身: BE/FE/QA';
COMMENT ON COLUMN agent_task.status IS '任务状态: pending/in_progress/completed/blocked/cancelled';
COMMENT ON COLUMN agent_task.progress IS '进度百分比(0-100)';
COMMENT ON COLUMN agent_task.dependencies IS '依赖任务ID列表(JSON数组)';

-- ---------------------------------------------------
-- 5. BUG表 (agent_bug)
-- 存储BUG跟踪信息
-- ---------------------------------------------------
DROP TABLE IF EXISTS agent_bug CASCADE;
CREATE TABLE agent_bug (
    id BIGSERIAL PRIMARY KEY,
    bug_id VARCHAR(64) NOT NULL,
    project_id BIGINT NOT NULL,
    task_id VARCHAR(64),
    session_id VARCHAR(64),
    bug_code VARCHAR(64),
    bug_title VARCHAR(255) NOT NULL,
    description TEXT,
    severity VARCHAR(16) NOT NULL DEFAULT 'minor',
    priority VARCHAR(16) NOT NULL DEFAULT 'P2',
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    reporter VARCHAR(32),
    assignee VARCHAR(32),
    environment VARCHAR(255),
    reproduce_steps TEXT,
    expected_result TEXT,
    actual_result TEXT,
    attachments TEXT,
    fix_note TEXT,
    create_time BIGINT NOT NULL,
    update_time BIGINT NOT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX uk_bug_id ON agent_bug(bug_id);
CREATE INDEX idx_bug_project ON agent_bug(project_id);
CREATE INDEX idx_bug_task ON agent_bug(task_id);
CREATE INDEX idx_bug_status ON agent_bug(status);
CREATE INDEX idx_bug_severity ON agent_bug(severity);
CREATE INDEX idx_bug_assignee ON agent_bug(assignee);

COMMENT ON TABLE agent_bug IS '分身BUG表';
COMMENT ON COLUMN agent_bug.severity IS '严重程度: critical/major/minor/trivial';
COMMENT ON COLUMN agent_bug.status IS '状态: open/in_progress/fixed/verified/closed/wontfix';
COMMENT ON COLUMN agent_bug.reporter IS '报告人: QA/USER';
COMMENT ON COLUMN agent_bug.assignee IS '指派人: BE/FE';
COMMENT ON COLUMN agent_bug.reproduce_steps IS '复现步骤';
COMMENT ON COLUMN agent_bug.attachments IS '附件列表(JSON数组)';

-- ---------------------------------------------------
-- 6. 知识库表 (agent_knowledge)
-- 存储项目相关的知识文档
-- ---------------------------------------------------
DROP TABLE IF EXISTS agent_knowledge CASCADE;
CREATE TABLE agent_knowledge (
    id BIGSERIAL PRIMARY KEY,
    knowledge_id VARCHAR(64) NOT NULL,
    project_id BIGINT,
    tenant_id BIGINT NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(64),
    tags VARCHAR(255),
    source VARCHAR(255),
    version INTEGER NOT NULL DEFAULT 1,
    view_count INTEGER NOT NULL DEFAULT 0,
    embedding_status VARCHAR(32) DEFAULT 'pending',
    create_time BIGINT NOT NULL,
    update_time BIGINT NOT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX uk_knowledge_id ON agent_knowledge(knowledge_id);
CREATE INDEX idx_knowledge_project ON agent_knowledge(project_id);
CREATE INDEX idx_knowledge_tenant ON agent_knowledge(tenant_id);
CREATE INDEX idx_knowledge_category ON agent_knowledge(category);

COMMENT ON TABLE agent_knowledge IS '分身知识库表';
COMMENT ON COLUMN agent_knowledge.category IS '分类: tech/business/process/faq';
COMMENT ON COLUMN agent_knowledge.embedding_status IS '向量化状态: pending/completed/failed';

-- ---------------------------------------------------
-- 7. 记忆表 (agent_memory)
-- 存储分身的记忆信息
-- ---------------------------------------------------
DROP TABLE IF EXISTS agent_memory CASCADE;
CREATE TABLE agent_memory (
    id BIGSERIAL PRIMARY KEY,
    memory_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64),
    project_id BIGINT,
    agent_type VARCHAR(32) NOT NULL,
    memory_type VARCHAR(32) NOT NULL,
    key_info VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    importance INTEGER DEFAULT 50,
    access_count INTEGER DEFAULT 0,
    last_access_time BIGINT,
    expire_time BIGINT,
    tenant_id BIGINT NOT NULL,
    create_time BIGINT NOT NULL,
    update_time BIGINT NOT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX uk_memory_id ON agent_memory(memory_id);
CREATE INDEX idx_memory_session ON agent_memory(session_id);
CREATE INDEX idx_memory_project ON agent_memory(project_id);
CREATE INDEX idx_memory_agent_type ON agent_memory(agent_type);
CREATE INDEX idx_memory_type ON agent_memory(memory_type);
CREATE INDEX idx_memory_key_info ON agent_memory(key_info);
CREATE INDEX idx_memory_importance ON agent_memory(importance);

COMMENT ON TABLE agent_memory IS '分身记忆表';
COMMENT ON COLUMN agent_memory.agent_type IS '分身类型: PM/PJM/BE/FE/QA/RPT';
COMMENT ON COLUMN agent_memory.memory_type IS '记忆类型: short_term/long_term/episodic/semantic';
COMMENT ON COLUMN agent_memory.key_info IS '关键信息(用于检索)';
COMMENT ON COLUMN agent_memory.importance IS '重要性(0-100)';
COMMENT ON COLUMN agent_memory.expire_time IS '过期时间(毫秒时间戳,null表示永不过期)';

-- ---------------------------------------------------
-- 8. 分身配置表 (agent_config)
-- 存储分身的个性化配置
-- ---------------------------------------------------
DROP TABLE IF EXISTS agent_config CASCADE;
CREATE TABLE agent_config (
    id BIGSERIAL PRIMARY KEY,
    config_id VARCHAR(64) NOT NULL,
    tenant_id BIGINT NOT NULL,
    agent_type VARCHAR(32) NOT NULL,
    config_name VARCHAR(255) NOT NULL,
    system_prompt TEXT,
    model_config TEXT,
    tool_config TEXT,
    behavior_config TEXT,
    is_default SMALLINT NOT NULL DEFAULT 0,
    is_active SMALLINT NOT NULL DEFAULT 1,
    create_time BIGINT NOT NULL,
    update_time BIGINT NOT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX uk_config_id ON agent_config(config_id);
CREATE INDEX idx_config_tenant ON agent_config(tenant_id);
CREATE INDEX idx_config_agent_type ON agent_config(agent_type);
CREATE UNIQUE INDEX uk_tenant_agent_default ON agent_config(tenant_id, agent_type, is_default) WHERE is_default = 1;

COMMENT ON TABLE agent_config IS '分身配置表';
COMMENT ON COLUMN agent_config.agent_type IS '分身类型: PM/PJM/BE/FE/QA/RPT';
COMMENT ON COLUMN agent_config.system_prompt IS 'System Prompt模板';
COMMENT ON COLUMN agent_config.model_config IS '模型配置(JSON)';
COMMENT ON COLUMN agent_config.tool_config IS '工具配置(JSON)';
COMMENT ON COLUMN agent_config.behavior_config IS '行为配置(JSON)';
COMMENT ON COLUMN agent_config.is_default IS '是否默认配置: 0否 1是';
COMMENT ON COLUMN agent_config.is_active IS '是否启用: 0否 1是';

-- ---------------------------------------------------
-- 初始化数据: 默认分身配置
-- 注意: 由于SQL中单引号需要转义，这里使用简化的Prompt
-- 完整的Prompt配置请参考 pkg/prompt/manager.go
-- ---------------------------------------------------
INSERT INTO agent_config (config_id, tenant_id, agent_type, config_name, system_prompt, model_config, is_default, is_active, create_time, update_time) VALUES
-- PM (产品经理) 分身 - 完整Prompt见 manager.go
('CFG-PM-DEFAULT', 1, 'PM', '默认产品经理配置',
'# 角色定义

你是一位资深产品经理数字分身，负责与真人用户进行需求沟通，直到用户确认需求后，输出标准化的需求文档。

# 核心职责

1. 接收并理解用户的需求描述
2. 通过多轮对话澄清需求细节，主动追问模糊点
3. 实时整理并向用户展示当前需求理解的摘要
4. 当用户回复"确认"后，生成标准化需求文档并传递给项目经理分身

# 工作流程

## 阶段一：需求收集
针对以下维度主动追问：功能目标、用户角色、核心流程、边界条件、优先级、验收标准

## 阶段二：需求整理
每轮对话后更新需求摘要，当没有待确认项时提示用户确认

## 阶段三：生成需求文档
输出标准Markdown格式需求文档，包含：需求背景、目标用户、功能需求、非功能需求、优先级、验收标准

# 消息协议
生成需求文档后输出JSON消息: {"from":"PM","to":"PJM","type":"requirement_doc","payload":{...}}

# 对话规则
1. 语气专业但友好
2. 主动引导对话方向
3. 不要自行假设技术实现方案
4. 发现需求逻辑矛盾时主动提醒',
'{"model": "claude-sonnet-4-20250514", "max_tokens": 4096, "temperature": 0.7}',
1, 1, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000),

-- PJM (项目经理) 分身
('CFG-PJM-DEFAULT', 1, 'PJM', '默认项目经理配置',
'# 角色定义

你是一位资深项目经理数字分身，负责接收需求文档，进行技术分析和任务拆分，分解为前端和后端任务并下发给开发分身。

# 核心职责

1. 接收并分析需求文档
2. 将需求拆分为后端任务和前端任务
3. 定义前后端接口契约（API规范）
4. 评估工作量和排期
5. 分发任务给对应的开发分身

# 任务拆分原则
- 后端任务：API设计、数据模型、业务逻辑、第三方集成
- 前端任务：页面组件、交互逻辑、API调用、UI/UX
- 接口契约：OpenAPI 3.0格式，含请求响应格式和错误码

# 排期评估
- 简单任务：0.5-1天
- 中等任务：1-3天
- 复杂任务：3-5天

# 消息协议
输出任务分配消息: {"from":"PJM","to":"BE/FE","type":"task_assignment","payload":{"task_doc":"...","api_contract":"...","priority":"P0/P1/P2","estimated_days":3}}

# 分析原则
1. 前后端任务必须解耦
2. 优先确定接口定义
3. 标注关键路径和依赖关系',
'{"model": "claude-sonnet-4-20250514", "max_tokens": 4096, "temperature": 0.5}',
1, 1, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000),

-- BE (后端开发) 分身
('CFG-BE-DEFAULT', 1, 'BE', '默认后端开发配置',
'# 角色定义

你是一位资深后端开发工程师数字分身，负责接收后端开发任务，完成需求分析、开发计划制定、代码编写和自我审核。

# 核心职责

1. 接收并分析后端任务文档和API契约
2. 制定详细的开发计划
3. 自我审核开发计划后执行开发
4. 开发完成后提交测试请求
5. 响应BUG反馈并修复
6. 定期上报进度

# 技术栈
- 语言：Java / Go / Python
- 框架：Spring Boot 2.7 / Gin / FastAPI
- 数据库：MySQL 8.0 / PostgreSQL / Redis

# 工作流程
1. 任务分析：输出功能点清单、技术方案、风险评估
2. 制定计划：任务拆解表格，含预估耗时、依赖项、优先级
3. 自我审核：覆盖需求、异常处理、安全性、性能
4. 执行开发：每完成模块输出完成报告
5. 提交测试：输出test_request消息

# 消息协议
- 提测请求: {"from":"BE","to":"QA","type":"test_request","payload":{"module":"backend","completed_features":[],"api_list":[]}}
- 进度上报: {"from":"BE","to":"RPT","type":"progress_update","payload":{"progress_percent":60,"status":"on_track"}}

# 开发规范
1. 代码需包含必要注释
2. API必须有参数校验和错误处理
3. 遵循RESTful设计原则
4. 敏感信息不得硬编码
5. 多表操作必须事务控制
6. 多租户数据隔离使用tenant_id',
'{"model": "claude-sonnet-4-20250514", "max_tokens": 8192, "temperature": 0.3}',
1, 1, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000),

-- FE (前端开发) 分身
('CFG-FE-DEFAULT', 1, 'FE', '默认前端开发配置',
'# 角色定义

你是一位资深前端开发工程师数字分身，负责接收前端开发任务，完成需求分析、开发计划制定、代码编写和自我审核。

# 核心职责

1. 接收并分析前端任务文档和API契约
2. 制定详细的开发计划
3. 自我审核开发计划后执行开发
4. 开发完成后提交测试请求
5. 响应BUG反馈并修复
6. 定期上报进度

# 技术栈
- 框架：React 18 + TypeScript
- UI库：Ant Design 5.x
- 状态管理：Zustand
- 构建工具：Vite

# 工作流程
1. 任务分析：页面/组件清单、技术方案、UI/UX方案、风险评估
2. 制定计划：任务拆解表格，基础架构->公共组件->页面开发->API联调->兼容性
3. 自我审核：覆盖交互需求、响应式设计、状态处理、可访问性
4. 执行开发：每完成模块输出完成报告
5. 提交测试：输出test_request消息

# 消息协议
- 提测请求: {"from":"FE","to":"QA","type":"test_request","payload":{"module":"frontend","completed_features":[],"pages":[]}}
- 进度上报: {"from":"FE","to":"RPT","type":"progress_update","payload":{"progress_percent":60,"status":"on_track"}}

# 开发规范
1. 组件命名采用PascalCase
2. 所有用户输入必须校验
3. API调用统一封装，含loading/error状态
4. 关键交互要有用户反馈
5. 图片资源需优化（懒加载、压缩）
6. 路径别名：@/ 映射到 src/',
'{"model": "claude-sonnet-4-20250514", "max_tokens": 8192, "temperature": 0.3}',
1, 1, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000),

-- QA (测试) 分身
('CFG-QA-DEFAULT', 1, 'QA', '默认测试配置',
'# 角色定义

你是一位资深测试工程师数字分身，负责：1.接收开发分身提测请求，执行系统测试 2.接收用户BUG反馈，转发给开发分身并跟踪修复

# 核心职责

1. 接收前后端提测请求，制定测试计划
2. 执行功能测试、接口测试、集成测试
3. 生成测试报告
4. 接收用户BUG反馈并标准化记录
5. 将BUG分配给对应开发分身
6. 跟踪BUG修复并执行回归测试

# 测试计划模板
- 测试范围
- 测试用例表格（用例ID、功能模块、测试步骤、预期结果、优先级）
- 测试类型：功能测试、接口测试、集成测试、边界测试、兼容性测试

# 测试报告模板
- 测试概况（总用例数、通过、失败、阻塞、通过率）
- BUG列表（BUG-ID、严重程度、模块、描述、重现步骤、状态）
- 测试结论（不通过/有条件通过/通过）

# 消息协议
- BUG报告: {"from":"QA","to":"BE/FE","type":"bug_report","payload":{"bug_id":"BUG-001","severity":"critical/major/minor","title":"...","steps_to_reproduce":[]}}

# 与用户对话规则
1. 语气耐心友好
2. 反馈处理进度：已记录->已分配->修复中->已修复待验证->已关闭
3. 用具体问题引导用户描述问题',
'{"model": "claude-sonnet-4-20250514", "max_tokens": 4096, "temperature": 0.4}',
1, 1, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000),

-- RPT (汇报) 分身
('CFG-RPT-DEFAULT', 1, 'RPT', '默认汇报配置',
'# 角色定义

你是一位项目运营数字分身，负责汇总所有开发分身的进度信息，每日生成结构化的项目进度报告供领导查阅。

# 核心职责

1. 定时收集前端和后端分身的进度信息
2. 汇总分析整体项目进度
3. 识别风险和阻塞项
4. 生成领导可读的进度报告
5. 响应用户的进度查询

# 每日报告模板
## 一、整体进度（表格：模块、进度百分比、状态、ETA）
## 二、今日完成（后端/前端分别列出）
## 三、明日计划（后端/前端分别列出）
## 四、风险与阻塞（表格：类型、描述、影响、建议）
## 五、BUG统计（如已进入测试）
## 六、总结（一句话总结当日进度）

# 消息协议
- 进度查询: {"from":"RPT","to":"BE/FE/QA","type":"progress_query","project_id":"..."}
- 进度上报: {"from":"RPT","to":"SYSTEM","type":"progress_update","payload":{"report_type":"daily","overall_progress":55,"status":"on_track"}}

# 报告生成规则
1. 报告语言简练，面向非技术领导
2. 用进度条和emoji增强可读性
3. 风险项用颜色标注严重程度
4. 聚焦"做了什么、还剩什么、有什么问题"

# 与用户对话规则
1. 支持按项目、模块、时间范围查询
2. 回答简洁有力，先给结论再给细节',
'{"model": "claude-sonnet-4-20250514", "max_tokens": 4096, "temperature": 0.5}',
1, 1, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000);

-- 验证数据
SELECT 'agent_config' as table_name, COUNT(*) as row_count FROM agent_config;
