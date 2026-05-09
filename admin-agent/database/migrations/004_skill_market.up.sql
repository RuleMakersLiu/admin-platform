-- =============================================
-- 技能市场数据库迁移
-- 版本: 1.0.0
-- 日期: 2026-03-01
-- =============================================

-- 技能分类表
CREATE TABLE IF NOT EXISTS skill_categories (
    id UUID PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    code VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    icon VARCHAR(50),
    parent_id UUID,
    sort INT NOT NULL DEFAULT 0,
    skill_count BIGINT NOT NULL DEFAULT 0,
    status INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 技能市场表
CREATE TABLE IF NOT EXISTS skill_market (
    id UUID PRIMARY KEY,
    skill_id UUID NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    category_id UUID NOT NULL,
    category_name VARCHAR(50) NOT NULL,
    tags TEXT,
    icon VARCHAR(50),
    version VARCHAR(20) NOT NULL,
    skill_config JSONB,
    input_schema JSONB,
    output_schema JSONB,
    handler_type VARCHAR(20) NOT NULL DEFAULT 'http',
    handler_url VARCHAR(255),
    script_path VARCHAR(255),
    builtin_func VARCHAR(100),
    timeout INT DEFAULT 30,
    author_id BIGINT NOT NULL,
    author_name VARCHAR(100) NOT NULL,
    tenant_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    review_comment TEXT,
    download_count BIGINT NOT NULL DEFAULT 0,
    view_count BIGINT NOT NULL DEFAULT 0,
    rating_avg DECIMAL(3,2) NOT NULL DEFAULT 0.00,
    rating_count BIGINT NOT NULL DEFAULT 0,
    featured BOOLEAN NOT NULL DEFAULT FALSE,
    documentation TEXT,
    changelog TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP WITH TIME ZONE
);

-- 技能评分表
CREATE TABLE IF NOT EXISTS skill_ratings (
    id UUID PRIMARY KEY,
    market_skill_id UUID NOT NULL,
    user_id BIGINT NOT NULL,
    user_name VARCHAR(100) NOT NULL,
    tenant_id BIGINT NOT NULL,
    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    helpful INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (market_skill_id, user_id)
);

-- 技能下载记录表
CREATE TABLE IF NOT EXISTS skill_downloads (
    id UUID PRIMARY KEY,
    market_skill_id UUID NOT NULL,
    user_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    skill_version VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_skill_market_skill_id ON skill_market(skill_id);
CREATE INDEX IF NOT EXISTS idx_skill_market_category_id ON skill_market(category_id);
CREATE INDEX IF NOT EXISTS idx_skill_market_author_id ON skill_market(author_id);
CREATE INDEX IF NOT EXISTS idx_skill_market_tenant_id ON skill_market(tenant_id);
CREATE INDEX IF NOT EXISTS idx_skill_market_status ON skill_market(status);
CREATE INDEX IF NOT EXISTS idx_skill_market_featured ON skill_market(featured);

CREATE INDEX IF NOT EXISTS idx_skill_ratings_market_skill_id ON skill_ratings(market_skill_id);
CREATE INDEX IF NOT EXISTS idx_skill_ratings_user_id ON skill_ratings(user_id);
CREATE INDEX IF NOT EXISTS idx_skill_ratings_tenant_id ON skill_ratings(tenant_id);

CREATE INDEX IF NOT EXISTS idx_skill_downloads_market_skill_id ON skill_downloads(market_skill_id);
CREATE INDEX IF NOT EXISTS idx_skill_downloads_user_id ON skill_downloads(user_id);
CREATE INDEX IF NOT EXISTS idx_skill_downloads_tenant_id ON skill_downloads(tenant_id);

CREATE INDEX IF NOT EXISTS idx_skill_categories_parent_id ON skill_categories(parent_id);

-- 插入默认分类数据
INSERT INTO skill_categories (id, name, code, description, icon, sort, status) VALUES
    ('11111111-1111-1111-1111-111111111111', '开发工具', 'development', '代码开发相关工具', 'code', 1, 1),
    ('22222222-2222-2222-2222-222222222222', '数据处理', 'data', '数据处理和分析工具', 'database', 2, 1),
    ('33333333-3333-3333-3333-333333333333', '生产力', 'productivity', '提升工作效率的工具', 'tool', 3, 1),
    ('44444444-4444-4444-4444-444444444444', '网络服务', 'network', '网络请求和API调用', 'global', 4, 1),
    ('55555555-5555-5555-5555-555555555555', '实用工具', 'utility', '常用实用工具集合', 'appstore', 5, 1),
    ('66666666-6666-6666-6666-666666666666', 'AI助手', 'ai', 'AI和机器学习相关工具', 'robot', 6, 1)
ON CONFLICT DO NOTHING;
