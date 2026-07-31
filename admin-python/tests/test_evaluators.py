"""evaluators.extract_eval_scores 统一评分抽取 + DEFAULT_EVAL_CRITERIA 收口测试。"""
from app.ai.evaluators import DEFAULT_EVAL_CRITERIA, extract_eval_scores


def test_extract_eval_scores_full():
    s = {
        "judge": {"overall_score": 80, "per_criterion": []},
        "hallucination": {"hallucination_score": 95},
        "vision": {"overall_score": 70},
        "e2e": {"passed": True, "issues": []},
    }
    assert extract_eval_scores(s) == {
        "judge_score": 80, "hallucination_score": 95, "vision_score": 70, "e2e_passed": 1,
    }


def test_extract_eval_scores_e2e_false_to_zero():
    assert extract_eval_scores({"e2e": {"passed": False}})["e2e_passed"] == 0


def test_extract_eval_scores_missing_errors_and_none():
    # 全缺 → 全 None
    assert extract_eval_scores({}) == {
        "judge_score": None, "hallucination_score": None, "vision_score": None, "e2e_passed": None,
    }
    # judge 出错 / e2e.passed 非 bool → None
    out = extract_eval_scores({"judge": {"error": "API 超时"}, "e2e": {"passed": None}})
    assert out["judge_score"] is None
    assert out["e2e_passed"] is None


def test_default_eval_criteria_moved_intact():
    # 从 flow_manager 收口到 evaluators，内容不变（4 条标准字符串）
    assert isinstance(DEFAULT_EVAL_CRITERIA, list)
    assert len(DEFAULT_EVAL_CRITERIA) == 4
    assert all(isinstance(c, str) for c in DEFAULT_EVAL_CRITERIA)
    # flow_manager 仍可访问（再导出，保 test_eval_stage 兼容）
    from app.ai import flow_manager
    assert flow_manager.DEFAULT_EVAL_CRITERIA is DEFAULT_EVAL_CRITERIA
