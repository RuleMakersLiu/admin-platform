import json
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class DatasetCaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: UUID = Field(default_factory=uuid4)
    category: str = Field(min_length=1, max_length=80)
    risk_level: RiskLevel = RiskLevel.LOW
    split: str = Field(pattern="^(DEVELOPMENT|REGRESSION|HIDDEN)$")
    source_type: str = Field(pattern="^(DEIDENTIFIED|EXPERT|AI_VARIANT|SYNTHETIC)$")
    input_payload: dict[str, Any]
    initial_state_ref: str | None = Field(default=None, max_length=255)
    expected_state: dict[str, Any]
    rubric: dict[str, Any]
    tool_policy: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    budget: dict[str, Any]
    deterministic_checks: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    oracle_type: str = Field(default="HYBRID", pattern="^(STATE|EXACT|REFERENCE|TOOL_TRACE|HYBRID)$")
    prohibited_behaviors: list[str] = Field(default_factory=list, max_length=50)
    source_group_id: str | None = Field(default=None, max_length=160)
    source_parent_hash: str | None = Field(default=None, min_length=64, max_length=64)

    @model_validator(mode="after")
    def bounded_case_payload(self) -> "DatasetCaseInput":
        encoded = json.dumps(self.model_dump(mode="json"), ensure_ascii=False).encode()
        if len(encoded) > 512 * 1024:
            raise ValueError("one dataset case cannot exceed 512 KiB")
        return self


class DatasetCaseUpdate(DatasetCaseInput):
    pass


class DatasetCaseImport(BaseModel):
    cases: list[DatasetCaseInput] = Field(min_length=1, max_length=500)
    dry_run: bool = False


class GoldenImportRequest(BaseModel):
    golden_case_ids: list[int] | None = Field(default=None, max_length=500)
    split: str = Field(default="DEVELOPMENT", pattern="^(DEVELOPMENT|REGRESSION)$")


class DatasetReviewRequest(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    comment: str | None = Field(default=None, max_length=2000)


class DatasetPublishRequest(BaseModel):
    expected_review_round: int = Field(ge=1)


class DatasetVersionCreate(BaseModel):
    clone_latest: bool = True


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
