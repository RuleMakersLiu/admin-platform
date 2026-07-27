"""应用配置"""
from functools import lru_cache
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Dev-only default; production MUST override via JWT_SECRET (enforced by the validator below).
DEFAULT_JWT_SECRET = "admin-platform-jwt-secret-key-2026-dev-only"


class Settings(BaseSettings):
    """应用配置"""

    # 服务配置
    app_name: str = "Admin Platform"
    app_version: str = "1.0.0"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8081

    # 数据库配置
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/admin_platform"
    # 连接池需容纳并发流水线最坏占用：每条流水线顺序阶段持 1 连接，并行 FE/BE 阶段
    # 额外开 2 条 branch_session（共 3）。pipeline_execution_concurrency=8 时最坏 24 连接，
    # 需为其它请求留余量，故默认池上限 15+30=45。
    database_pool_size: int = 15
    database_max_overflow: int = 30

    # Redis配置
    redis_url: str = "redis://localhost:6379/1"

    # JWT配置
    # SECURITY: production must set JWT_SECRET. The dev default is shared with admin-gateway.
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24小时

    # Claude API配置
    claude_api_key: Optional[str] = None
    claude_base_url: str = "https://api.anthropic.com"
    claude_default_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 4096

    # GLM-5 API配置（用户偏好）
    zai_api_key: Optional[str] = None
    zai_base_url: str = "https://open.bigmodel.cn"
    zai_default_model: str = "glm-4-flash"
    zai_max_tokens: int = 4096

    # GLM Embedding（RAG 向量检索）配置 — 复用 zai_api_key
    zai_embedding_model: str = "embedding-3"
    zai_embedding_dimensions: int = 1024
    zai_embedding_batch_size: int = 32

    # GLM 视觉模型（多模态：图像理解/视觉评测）配置 — 复用 zai_api_key
    zai_vision_model: str = "glm-4v-plus"

    # ASR 语音转写（OpenAI 兼容 Whisper 端点；可指向 OpenAI / Groq / 本地 whisper-server）
    asr_base_url: str = ""
    asr_api_key: str = ""
    asr_model: str = "whisper-1"

    # RAG 检索参数
    rag_top_k: int = 5
    rag_min_similarity: float = 0.75

    # CORS配置
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # ==================== 多渠道消息配置 ====================

    # Telegram Bot 配置
    telegram_bot_token: Optional[str] = None
    telegram_secret_token: Optional[str] = None  # Webhook 验证 token

    # Discord Bot 配置
    discord_bot_token: Optional[str] = None
    discord_application_id: Optional[str] = None
    discord_public_key: Optional[str] = None  # 用于验证 Interaction 签名

    # Slack Bot 配置
    slack_bot_token: Optional[str] = None  # xoxb-xxx
    slack_app_token: Optional[str] = None  # xapp-xxx (可选)
    slack_signing_secret: Optional[str] = None  # Webhook 签名密钥

    # 飞书 Bot 配置
    feishu_app_id: Optional[str] = None
    feishu_app_secret: Optional[str] = None
    feishu_encrypt_key: Optional[str] = None  # 消息加密密钥
    feishu_verification_token: Optional[str] = None  # Webhook 验证 token

    # ==================== Pipeline v2 配置 ====================
    pipeline_workspace_root: str = "/data/pipelines"
    pipeline_test_timeout: int = 120
    pipeline_preview_host: str = "127.0.0.1"
    pipeline_preview_port_start: int = 43000
    pipeline_preview_port_end: int = 43100
    pipeline_preview_api_proxy: str = ""
    pipeline_execution_concurrency: int = 8
    pipeline_execution_queue_limit: int = 50
    deploy_service_url: str = "http://admin-deploy:8083"

    @model_validator(mode="after")
    def _enforce_production_secret(self) -> "Settings":
        """Fail fast if the JWT secret is missing or is the insecure dev default, outside debug mode."""
        if not self.debug and (not self.jwt_secret or self.jwt_secret == DEFAULT_JWT_SECRET):
            raise ValueError(
                "Refusing to start: jwt_secret is empty or the insecure dev default. "
                "Set the JWT_SECRET environment variable (or DEBUG=true for local dev)."
            )
        return self

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
