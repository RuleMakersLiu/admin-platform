from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AdapterType(StrEnum):
    HTTP = "HTTP"
    SSE = "SSE"
    OPENAI_COMPATIBLE = "OPENAI_COMPATIBLE"
    CONTAINER = "CONTAINER"
    CLI = "CLI"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    adapter_type: AdapterType
    risk_level: RiskLevel

    @property
    def isolation_scope(self) -> str:
        return "RUNNER_ONLY" if self.adapter_type in {
            AdapterType.HTTP,
            AdapterType.SSE,
            AdapterType.OPENAI_COMPATIBLE,
        } else "FULL"


class DatasetCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=4000)


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    dataset_version_id: UUID
    price_book_id: UUID
    agent_version_ids: list[UUID] = Field(min_length=2, max_length=10)
    repetitions: int = Field(default=3, ge=1, le=5)
    sandbox_policy_version: str = Field(min_length=1, max_length=80)
    experiment_type: str = Field(default="PAIRED_OFFLINE", pattern="^(PAIRED_OFFLINE|SHADOW_REPLAY)$")
    execution_order_seed: int

    @model_validator(mode="after")
    def unique_agent_versions(self) -> "ExperimentCreate":
        if len(set(self.agent_version_ids)) != len(self.agent_version_ids):
            raise ValueError("agent versions must be unique")
        return self


class ApiResponse(BaseModel):
    code: int = 0
    data: object | None = None
    message: str = "ok"
