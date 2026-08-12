from uuid import UUID

import pytest
from pydantic import ValidationError

from app.domain.scheduling import blind_ab_order, paired_trial_plan
from app.domain.review import Preference, ReviewCandidate, requires_arbitration, stratified_review_sample, weighted_kappa
from app.domain.dataset_factory import CaseDraft, RiskLevel, SourceType, Split, build_agent_case_payload, validate_case, validate_release
from app.domain.scoring import CostItem, DeterministicCheck, TrialScoreInput, UsageQuality, score_trial, summarize_cost
from app.domain.statistics import holm_adjust, paired_mcnemar, pareto_frontier, wilson_interval
from app.schemas import DatasetCaseInput


def test_security_violation_overrides_completed_task() -> None:
    result = score_trial(TrialScoreInput(
        security_violations=("CROSS_TENANT_ACCESS",),
        state_checks=(DeterministicCheck("state", True, 1, "ok"),),
        judge_score=1.0,
    ))
    assert result.quality_score == 1.0
    assert not result.passed
    assert not result.security_passed
    assert result.review_required


def test_judge_failure_preserves_deterministic_score() -> None:
    result = score_trial(TrialScoreInput(
        state_checks=(DeterministicCheck("state", True, 3, "ok"),),
        schema_checks=(DeterministicCheck("schema", False, 1, "bad"),),
        judge_error="timeout",
    ))
    assert result.deterministic_score == 0.75
    assert result.quality_score == 0.75
    assert not result.judge_available


def test_missing_cost_is_not_silently_zero() -> None:
    summary = summarize_cost([
        CostItem("agent_cost", 4.0, UsageQuality.ACTUAL),
        CostItem("judge_cost", None, UsageQuality.MISSING),
    ], successful_trials=2)
    assert summary.known_total == 4
    assert not summary.complete
    assert summary.evaluation_overhead is None
    assert summary.cost_per_success == 2
    with pytest.raises(ValueError):
        CostItem("storage_cost", 0, UsageQuality.MISSING)


def test_wilson_and_exact_mcnemar() -> None:
    interval = wilson_interval(80, 100)
    assert 0.70 < interval.lower < interval.estimate < interval.upper < 0.90
    result = paired_mcnemar([True] * 8 + [False], [False] * 8 + [True])
    assert result.a_only_wins == 8 and result.b_only_wins == 1
    assert result.p_value < 0.05


def test_holm_is_monotonic_and_pareto_has_no_dominated_rows() -> None:
    adjusted = holm_adjust({"a": 0.01, "b": 0.03, "c": 0.2})
    assert adjusted["a"] <= adjusted["b"] <= adjusted["c"]
    rows = [
        {"id": 1, "success": 0.9, "cost": 2.0},
        {"id": 2, "success": 0.8, "cost": 3.0},
        {"id": 3, "success": 0.85, "cost": 1.0},
    ]
    frontier = pareto_frontier(rows, maximize=("success",), minimize=("cost",))
    assert {row["id"] for row in frontier} == {1, 3}


def test_pairing_is_reproducible_and_each_run_is_independent() -> None:
    cases = [UUID(int=1), UUID(int=2)]
    agents = [UUID(int=10), UUID(int=11)]
    first = paired_trial_plan(cases, agents, repetitions=3, seed=42)
    second = paired_trial_plan(cases, agents, repetitions=3, seed=42)
    assert first == second
    assert len(first) == 12
    assert len({item.idempotency_key for item in first}) == 12


def test_blind_order_has_verifiable_proof_without_identity_in_ui() -> None:
    first, second, proof = blind_ab_order(UUID(int=10), UUID(int=11), UUID(int=99), b"x" * 32)
    assert {first, second} == {UUID(int=10), UUID(int=11)}
    assert len(proof) == 64


def make_case(identifier: int, split: Split = Split.HIDDEN) -> CaseDraft:
    return CaseDraft(
        external_id=UUID(int=identifier), category="order_query", split=split,
        risk_level=RiskLevel.LOW,
        source_type=SourceType.SYNTHETIC, input_payload={"order_id": f"mock-{identifier}"},
        expected_state={"status": "FOUND"}, rubric={"correct": 1},
        budget={"timeout_seconds": 60, "max_tool_calls": 3, "max_model_cost": 1},
        deterministic_checks=[{"path": "$.status", "equals": "FOUND"}],
        tool_policy=[{"tool_id": "mock-order", "side_effect_mode": "READ_ONLY", "allowed_actions": ["get"], "input_schema": {}}],
    )


def test_agent_payload_excludes_answers_and_rubric() -> None:
    payload = build_agent_case_payload(make_case(1))
    assert "expected_state" not in payload
    assert "rubric" not in payload
    assert "deterministic_checks" not in payload


def test_dataset_release_rejects_pii_duplicates_and_missing_splits() -> None:
    unsafe = make_case(1)
    unsafe = CaseDraft(**{**unsafe.__dict__, "input_payload": {"email": "real.person@example.com"}})
    assert validate_case(unsafe)
    duplicate = make_case(2)
    duplicate = CaseDraft(**{**duplicate.__dict__, "external_id": UUID(int=3)})
    errors = validate_release([unsafe, duplicate, duplicate])
    assert any("personal data" in error for error in errors)
    assert any("duplicate" in error for error in errors)
    assert any("regression" in error for error in errors)


def test_dataset_release_keeps_source_family_in_one_split() -> None:
    hidden = make_case(10, Split.HIDDEN)
    regression = make_case(11, Split.REGRESSION)
    hidden = CaseDraft(**{**hidden.__dict__, "source_group_id": "same-seed"})
    regression = CaseDraft(**{**regression.__dict__, "source_group_id": "same-seed"})
    assert any("crosses dataset splits" in error for error in validate_release([hidden, regression]))


def test_dataset_case_schema_rejects_oversized_payload() -> None:
    with pytest.raises(ValidationError):
        DatasetCaseInput(
            category="oversized", split="DEVELOPMENT", source_type="SYNTHETIC",
            input_payload={"request": "x" * (513 * 1024)}, expected_state={"ok": True},
            rubric={"correct": 1}, deterministic_checks=[{"operator": "eq"}],
            budget={"timeout_seconds": 60, "max_tool_calls": 0, "max_model_cost": 0},
        )


def test_review_sampling_always_includes_risk_and_stratifies_remainder() -> None:
    candidates = [
        ReviewCandidate("security", "security", security_alert=True),
        ReviewCandidate("a1", "normal"), ReviewCandidate("a2", "normal"),
        ReviewCandidate("b1", "edge"), ReviewCandidate("b2", "edge"),
    ]
    selected = stratified_review_sample(candidates, rate=0.05, seed=7)
    assert "security" in selected
    assert any(value.startswith("a") for value in selected)
    assert any(value.startswith("b") for value in selected)


def test_kappa_threshold_and_arbitration_rules() -> None:
    agreement = weighted_kappa(
        [Preference.A_STRONG, Preference.TIE, Preference.B_STRONG],
        [Preference.A_STRONG, Preference.TIE, Preference.B_STRONG],
    )
    assert agreement == 1
    disagreement = weighted_kappa(
        [Preference.A_STRONG, Preference.A_STRONG, Preference.A_SLIGHT],
        [Preference.B_STRONG, Preference.B_STRONG, Preference.B_SLIGHT],
    )
    assert disagreement < 0.65
    assert requires_arbitration(Preference.A_SLIGHT, Preference.B_SLIGHT, {"correctness": 4}, {"correctness": 4})
    assert requires_arbitration(Preference.TIE, Preference.TIE, {"clarity": 5}, {"clarity": 3})
