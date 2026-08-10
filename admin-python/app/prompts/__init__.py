"""流水线 prompt 统一导出。

所有阶段的 prompt 模板、全局契约、质量审查契约集中在本包，改 prompt 不用翻代码。
flow_manager.py 只需 from app.prompts import DEFAULT_STAGE_PROMPTS, PIPELINE_GLOBAL_PROMPT_CONTRACT 等。
"""
from app.prompts.global_contract import PIPELINE_GLOBAL_PROMPT_CONTRACT
from app.prompts.stage_prompts import DEFAULT_STAGE_PROMPTS
from app.prompts.review_contracts import (
    PM_REQUIREMENT_REVIEW_CONTRACT,
    PM_PAGE_DESIGN_REVIEW_CONTRACT,
    REVIEW_GATE_PASS_SCORE,
    REVIEW_GATE_CRITERIA,
)

__all__ = [
    "PIPELINE_GLOBAL_PROMPT_CONTRACT",
    "DEFAULT_STAGE_PROMPTS",
    "PM_REQUIREMENT_REVIEW_CONTRACT",
    "PM_PAGE_DESIGN_REVIEW_CONTRACT",
    "REVIEW_GATE_PASS_SCORE",
    "REVIEW_GATE_CRITERIA",
]
