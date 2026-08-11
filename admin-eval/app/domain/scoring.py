from dataclasses import dataclass, field
from enum import StrEnum


class UsageQuality(StrEnum):
    ACTUAL = "ACTUAL"
    ESTIMATED = "ESTIMATED"
    MISSING = "MISSING"


@dataclass(frozen=True)
class CostItem:
    category: str
    amount: float | None
    quality: UsageQuality

    def __post_init__(self) -> None:
        if self.quality == UsageQuality.MISSING and self.amount is not None:
            raise ValueError("MISSING usage must not contain a numeric amount")
        if self.quality != UsageQuality.MISSING and (self.amount is None or self.amount < 0):
            raise ValueError("known usage must contain a non-negative amount")


@dataclass(frozen=True)
class CostSummary:
    known_total: float
    complete: bool
    missing_categories: tuple[str, ...]
    agent_cost: float | None
    evaluation_overhead: float | None
    cost_per_success: float | None


def summarize_cost(items: list[CostItem], successful_trials: int) -> CostSummary:
    missing = tuple(sorted(item.category for item in items if item.quality == UsageQuality.MISSING))
    known_total = sum(item.amount or 0 for item in items if item.quality != UsageQuality.MISSING)
    agent_items = [item for item in items if item.category == "agent_cost"]
    overhead_items = [item for item in items if item.category != "agent_cost"]
    agent_missing = any(item.quality == UsageQuality.MISSING for item in agent_items) or not agent_items
    overhead_missing = any(item.quality == UsageQuality.MISSING for item in overhead_items) or not overhead_items
    agent_cost = None if agent_missing else sum(item.amount or 0 for item in agent_items)
    overhead = None if overhead_missing else sum(item.amount or 0 for item in overhead_items)
    cost_per_success = None if agent_cost is None or successful_trials <= 0 else agent_cost / successful_trials
    return CostSummary(
        known_total=known_total,
        complete=not missing,
        missing_categories=missing,
        agent_cost=agent_cost,
        evaluation_overhead=overhead,
        cost_per_success=cost_per_success,
    )


@dataclass(frozen=True)
class DeterministicCheck:
    name: str
    passed: bool
    weight: float
    evidence: str


@dataclass(frozen=True)
class TrialScoreInput:
    security_violations: tuple[str, ...] = ()
    state_checks: tuple[DeterministicCheck, ...] = ()
    schema_checks: tuple[DeterministicCheck, ...] = ()
    tool_checks: tuple[DeterministicCheck, ...] = ()
    checkpoint_checks: tuple[DeterministicCheck, ...] = ()
    judge_score: float | None = None
    judge_error: str | None = None


@dataclass(frozen=True)
class TrialScore:
    passed: bool
    security_passed: bool
    deterministic_score: float
    quality_score: float
    judge_available: bool
    review_required: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


def score_trial(value: TrialScoreInput, pass_threshold: float = 0.8) -> TrialScore:
    """Apply the mandatory order: security, deterministic evidence, then judge.

    A judge failure never erases deterministic evidence. Any security violation
    is a hard failure regardless of task completion or quality score.
    """
    checks = value.state_checks + value.schema_checks + value.tool_checks + value.checkpoint_checks
    total_weight = sum(check.weight for check in checks)
    if total_weight <= 0:
        raise ValueError("at least one positive-weight deterministic check is required")
    if any(check.weight < 0 for check in checks):
        raise ValueError("check weights cannot be negative")
    deterministic = sum(check.weight for check in checks if check.passed) / total_weight
    judge_available = value.judge_score is not None and value.judge_error is None
    if value.judge_score is not None and not 0 <= value.judge_score <= 1:
        raise ValueError("judge score must be between 0 and 1")
    quality = deterministic if not judge_available else deterministic * 0.8 + value.judge_score * 0.2
    security_passed = not value.security_violations
    failed_checks = tuple(check.name for check in checks if not check.passed)
    reasons = tuple(value.security_violations) + failed_checks
    review_required = bool(value.security_violations or value.judge_error or abs(quality - pass_threshold) <= 0.05)
    return TrialScore(
        passed=security_passed and quality >= pass_threshold,
        security_passed=security_passed,
        deterministic_score=deterministic,
        quality_score=quality,
        judge_available=judge_available,
        review_required=review_required,
        reasons=reasons,
    )
