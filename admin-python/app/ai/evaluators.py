"""统一评测（eval）的评分抽取 + 标准收口。

eval 阶段（_run_eval_stage）产 judge/hallucination/vision/e2e 四路结果写进一个 structured dict。
本模块提供：
  - extract_eval_scores(structured)：把四路结果**统一**抽成扁平分数字典，供
    _record_pipeline_eval 持久化 + _eval_quality_gate_reason 门控**同源**读分（取代散落的 ad-hoc 抽取）。
  - DEFAULT_EVAL_CRITERIA：eval 阶段无 golden case 时的默认评审标准（原居 flow_manager，收口到此）。

设计意图（部分待落地）：后续把 _run_eval_stage 的四路拼装（judge_output / judge_hallucination /
judge_output_vision / run_e2e_assertions）改为 Evaluator ABC + EvaluatorRegistry 可插拔驱动——
extract_eval_scores 是该抽象的第一个消费者；本期不重写 _run_eval_stage（其 judge/hallucination 在
acquire_live_preview 之外、vision/e2e 在内的编排有行为语义，重写需配套行为守卫测试，单独做）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# eval 阶段默认评审标准（无 golden case 时用）。
DEFAULT_EVAL_CRITERIA: List[str] = [
    "需求覆盖：产物实现了用户需求中的核心功能点，无重大遗漏",
    "契约完整：API 路径/方法/请求与响应字段清晰，前后端字段命名与类型对齐",
    "代码质量：结构清晰、无明显错误、具备可编译/可运行的意图",
    "可测试性：包含必要校验、边界处理与可验收的测试要点",
]


def extract_eval_scores(structured: Dict[str, Any]) -> Dict[str, Optional[int]]:
    """从 eval 阶段 structured dict 抽统一的 LLM 评测分。

    返回 {judge_score, hallucination_score, vision_score, e2e_passed}；缺失/出错 → None。
    judge.overall_score / vision.overall_score / hallucination.hallucination_score 为 int|None；
    e2e.passed 为 bool → 转 0/1（非 bool → None）。
    """
    judge = structured.get("judge") or {}
    hallu = structured.get("hallucination") or {}
    vision = structured.get("vision") or {}
    e2e = structured.get("e2e") or {}
    e2e_passed = e2e.get("passed")
    return {
        "judge_score": judge.get("overall_score"),
        "hallucination_score": hallu.get("hallucination_score"),
        "vision_score": vision.get("overall_score"),
        "e2e_passed": int(e2e_passed) if isinstance(e2e_passed, bool) else None,
    }
