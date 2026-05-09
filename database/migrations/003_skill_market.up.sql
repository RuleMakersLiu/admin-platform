-- 技能市场相关表
CREATE TABLE IF NOT EXISTS skill_market_item (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    author_id BIGINT NOT NULL,
    author_name VARCHAR(255),
    download_count INTEGER DEFAULT 0,
    rating DECIMAL(3,2) DEFAULT 0.0,
    rating_count INTEGER DEFAULT 0,
    skill_data JSONB NOT NULL,
    status INTEGER DEFAULT 1,
    create_time BIGINT NOT NULL,
    update_time BIGINT,
    CONSTRAINT fk_skill_author FOREIGN KEY (author_id) REFERENCES sys_admin(id)
);

CREATE INDEX idx_skill_market_category ON skill_market_item(category);
CREATE INDEX idx_skill_market_author ON skill_market_item(author_id);
CREATE INDEX idx_skill_market_status ON skill_market_item(status);

-- 技能评论表
CREATE TABLE IF NOT EXISTS skill_market_comment (
    id BIGSERIAL PRIMARY KEY,
    skill_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    user_name VARCHAR(255),
    rating INTEGER,
    comment TEXT,
    create_time BIGINT NOT NULL,
    CONSTRAINT fk_comment_skill FOREIGN KEY (skill_id) REFERENCES skill_market_item(id),
    CONSTRAINT fk_comment_user FOREIGN KEY (user_id) REFERENCES sys_admin(id)
);

CREATE INDEX idx_skill_comment_skill ON skill_market_comment(skill_id);
