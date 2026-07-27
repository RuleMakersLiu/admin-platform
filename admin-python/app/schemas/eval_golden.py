"""评测 Golden Case 请求/响应 Schema + JSON 存储 helpers。"""
import json
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class GoldenCaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    category: str = Field("general", max_length=64)
    project_type: Optional[str] = Field(None, max_length=64)
    input_spec: Any = Field(..., description="需求文本或结构化 JSON")
    expected_criteria: Any = Field(..., description="评判标准：文本或 JSON 列表")
    tags: Optional[str] = Field(None, max_length=256)
    enabled: int = 1


class GoldenCaseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    category: Optional[str] = None
    project_type: Optional[str] = None
    input_spec: Optional[Any] = None
    expected_criteria: Optional[Any] = None
    tags: Optional[str] = None
    enabled: Optional[int] = None


class GoldenCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tenant_id: int
    name: str
    category: str
    project_type: Optional[str] = None
    input_spec: Any
    expected_criteria: Any
    tags: Optional[str] = None
    enabled: int
    created_by: Optional[int] = None
    create_time: int


def to_storage(value: Any) -> str:
    """把任意 JSON 可序列化值序列化为存储文本；字符串原样保留。"""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def from_storage(raw: Optional[str]) -> Any:
    """从存储文本还原；非 JSON 字符串原样返回（兼容纯文本需求）。"""
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw
