"""应用配置"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


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
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Redis配置
    redis_url: str = "redis://localhost:6379/1"

    # JWT配置
    # SECURITY: 生产环境必须设置 JWT_SECRET 环境变量
    jwt_secret: str = "CHANGE-ME-IN-PRODUCTION-USE-openssl-rand-hex-32"
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
    deploy_service_url: str = "http://admin-deploy:8083"

    # ==================== 埋点数据配置 ====================

    # Kafka 配置
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_tracking_topic: str = "tracking-events"
    kafka_tracking_group: str = "tracking-consumer"

    # ClickHouse 配置
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 9000
    clickhouse_database: str = "analytics"
    clickhouse_user: str = "default"
    clickhouse_password: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
