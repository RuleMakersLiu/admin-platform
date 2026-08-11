from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EVAL_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/admin_platform"
    kafka_bootstrap_servers: str = "127.0.0.1:9092"
    internal_service_token: SecretStr = SecretStr("")
    execution_enabled: bool = False
    approved_gate_reference: str = ""
    max_experiment_trials: int = Field(default=10_000, ge=1, le=100_000)

    @field_validator("internal_service_token")
    @classmethod
    def validate_internal_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if token and len(token) < 32:
            raise ValueError("internal service token must contain at least 32 characters")
        return value

    @property
    def execution_gate_open(self) -> bool:
        return self.execution_enabled and bool(self.approved_gate_reference.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
