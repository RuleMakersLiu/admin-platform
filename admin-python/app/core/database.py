"""数据库配置"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.core.config import settings

# 创建异步引擎
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=settings.debug,
    pool_recycle=3600,
    pool_pre_ping=True,
)

# 创建会话工厂
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """模型基类"""
    pass


async def get_db() -> AsyncSession:
    """获取数据库会话"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def ensure_runtime_schema():
    """Ensure columns added during active development exist in local/runtime DB."""
    async with engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE agent_project ADD COLUMN IF NOT EXISTS pipeline_prompts TEXT")
        )
        await conn.execute(
            text("ALTER TABLE project_knowledge ADD COLUMN IF NOT EXISTS project_analysis_schema TEXT")
        )
        await conn.execute(
            text("ALTER TABLE project_knowledge ADD COLUMN IF NOT EXISTS generation_contract TEXT")
        )
        await conn.execute(
            text("ALTER TABLE project_knowledge ADD COLUMN IF NOT EXISTS verification_contract TEXT")
        )

        # RAG: pgvector 扩展 + agent_knowledge 向量列与索引（镜像需为 pgvector/pgvector:pg15）
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(
            text("ALTER TABLE agent_knowledge ADD COLUMN IF NOT EXISTS embedding vector(1024)")
        )
        await conn.execute(
            text("ALTER TABLE agent_knowledge ADD COLUMN IF NOT EXISTS content_hash CHAR(64)")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_knowledge_content_hash ON agent_knowledge(content_hash)")
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_knowledge_embedding_hnsw "
                "ON agent_knowledge USING hnsw (embedding vector_cosine_ops)"
            )
        )

        # 需求附件（图片/文档，JSON Text）——需求阶段多模态（设计稿当需求）
        await conn.execute(text(
            "ALTER TABLE dev_pipeline ADD COLUMN IF NOT EXISTS attachments TEXT"
        ))

        # Eval 增强：pipeline_eval_result 加 LLM-as-judge 评测列（eval 阶段产物）。现有库补列。
        await conn.execute(text(
            "ALTER TABLE pipeline_eval_result ADD COLUMN IF NOT EXISTS judge_score INTEGER"
        ))
        await conn.execute(text(
            "ALTER TABLE pipeline_eval_result ADD COLUMN IF NOT EXISTS hallucination_score INTEGER"
        ))
        await conn.execute(text(
            "ALTER TABLE pipeline_eval_result ADD COLUMN IF NOT EXISTS vision_score INTEGER"
        ))
        await conn.execute(text(
            "ALTER TABLE pipeline_eval_result ADD COLUMN IF NOT EXISTS e2e_passed SMALLINT"
        ))
        # 人工覆盖分（校准 LLM judge）。
        await conn.execute(text(
            "ALTER TABLE pipeline_eval_result ADD COLUMN IF NOT EXISTS human_score INTEGER"
        ))
        await conn.execute(text(
            "ALTER TABLE pipeline_eval_result ADD COLUMN IF NOT EXISTS human_comment VARCHAR(500)"
        ))
        await conn.execute(text(
            "ALTER TABLE pipeline_eval_result ADD COLUMN IF NOT EXISTS human_scored_by BIGINT"
        ))
        await conn.execute(text(
            "ALTER TABLE pipeline_eval_result ADD COLUMN IF NOT EXISTS human_scored_at BIGINT"
        ))

        # Eval 评测闭环：pipeline_eval_result（终端态聚合各 stage 评测信号）
        await conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS pipeline_eval_result (
                id BIGSERIAL PRIMARY KEY,
                eval_id VARCHAR(64) NOT NULL,
                pipeline_id VARCHAR(64) NOT NULL,
                tenant_id BIGINT NOT NULL,
                project_id VARCHAR(64),
                status VARCHAR(32) NOT NULL,
                overall_score INTEGER,
                pm_quality_score INTEGER,
                design_quality_score INTEGER,
                preview_quality_score INTEGER,
                judge_score INTEGER,
                hallucination_score INTEGER,
                vision_score INTEGER,
                e2e_passed SMALLINT,
                human_score INTEGER,
                human_comment VARCHAR(500),
                human_scored_by BIGINT,
                human_scored_at BIGINT,
                review_passed SMALLINT,
                tests_passed SMALLINT,
                tests_total INTEGER,
                tests_passed_count INTEGER,
                tests_failed_count INTEGER,
                retry_count INTEGER,
                auto_repair_iterations INTEGER,
                framework VARCHAR(32),
                test_duration_ms INTEGER,
                stage_scores TEXT,
                cost_input_tokens BIGINT,
                cost_output_tokens BIGINT,
                create_time BIGINT NOT NULL,
                update_time BIGINT NOT NULL,
                is_deleted SMALLINT NOT NULL DEFAULT 0
            )
            """
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uk_pipeline_eval_id ON pipeline_eval_result(eval_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_pipeline_eval_pipeline ON pipeline_eval_result(pipeline_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_pipeline_eval_tenant_time ON pipeline_eval_result(tenant_id, create_time)"
        ))
