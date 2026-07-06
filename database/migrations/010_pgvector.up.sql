-- 010_pgvector.up.sql
-- RAG 向量检索支持：启用 pgvector 扩展 + agent_knowledge 向量列与索引
-- 前置: PostgreSQL 镜像需为 pgvector/pgvector:pg15 (docker-compose 已切换)
-- 幂等: 所有语句均 IF NOT EXISTS，可重复执行 (与 ensure_runtime_schema 保持一致)

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE agent_knowledge ADD COLUMN IF NOT EXISTS embedding vector(1024);
ALTER TABLE agent_knowledge ADD COLUMN IF NOT EXISTS content_hash CHAR(64);

CREATE INDEX IF NOT EXISTS idx_knowledge_content_hash ON agent_knowledge(content_hash);
CREATE INDEX IF NOT EXISTS idx_knowledge_embedding_hnsw
    ON agent_knowledge USING hnsw (embedding vector_cosine_ops);
