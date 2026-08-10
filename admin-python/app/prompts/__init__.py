"""流水线 prompt 统一包。

  contracts/  — 边界强制规则（全局契约、质量审查契约、评审关卡）
  stages/     — 各阶段 prompt（requirement ~ report，每阶段一个文件）
"""
from app.prompts.contracts import (
    PIPELINE_GLOBAL_PROMPT_CONTRACT,
    PM_REQUIREMENT_REVIEW_CONTRACT,
    PM_PAGE_DESIGN_REVIEW_CONTRACT,
    REVIEW_GATE_CRITERIA,
    REVIEW_GATE_PASS_SCORE,
)
from app.prompts.stages import DEFAULT_STAGE_PROMPTS

__all__ = [
    "PIPELINE_GLOBAL_PROMPT_CONTRACT",
    "DEFAULT_STAGE_PROMPTS",
    "PM_REQUIREMENT_REVIEW_CONTRACT",
    "PM_PAGE_DESIGN_REVIEW_CONTRACT",
    "REVIEW_GATE_CRITERIA",
    "REVIEW_GATE_PASS_SCORE",
]
