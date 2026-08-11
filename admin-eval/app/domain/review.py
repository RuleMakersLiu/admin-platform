import random
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum


class Preference(StrEnum):
    A_STRONG = "A_STRONG"
    A_SLIGHT = "A_SLIGHT"
    TIE = "TIE"
    B_SLIGHT = "B_SLIGHT"
    B_STRONG = "B_STRONG"
    BOTH_FAILED = "BOTH_FAILED"


_ORDINAL = {
    Preference.A_STRONG: 0,
    Preference.A_SLIGHT: 1,
    Preference.TIE: 2,
    Preference.B_SLIGHT: 3,
    Preference.B_STRONG: 4,
    Preference.BOTH_FAILED: 5,
}


@dataclass(frozen=True)
class ReviewCandidate:
    trial_id: str
    category: str
    security_alert: bool = False
    judge_conflict: bool = False
    near_threshold: bool = False
    novel_configuration: bool = False
    anomalous_cost_or_latency: bool = False

    @property
    def requires_double_review(self) -> bool:
        return any((
            self.security_alert,
            self.judge_conflict,
            self.near_threshold,
            self.novel_configuration,
            self.anomalous_cost_or_latency,
        ))


def stratified_review_sample(candidates: list[ReviewCandidate], rate: float = 0.05, seed: int = 0) -> set[str]:
    if not 0 <= rate <= 1:
        raise ValueError("sampling rate must be between zero and one")
    selected = {candidate.trial_id for candidate in candidates if candidate.requires_double_review}
    rng = random.Random(seed)
    strata: dict[str, list[ReviewCandidate]] = {}
    for candidate in candidates:
        if not candidate.requires_double_review:
            strata.setdefault(candidate.category, []).append(candidate)
    for category in sorted(strata):
        population = sorted(strata[category], key=lambda candidate: candidate.trial_id)
        sample_size = round(len(population) * rate)
        if rate > 0 and population:
            sample_size = max(1, sample_size)
        selected.update(item.trial_id for item in rng.sample(population, min(sample_size, len(population))))
    return selected


def weighted_kappa(left: list[Preference], right: list[Preference]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("review lists must have the same non-zero length")
    categories = list(Preference)
    size = len(categories)
    observed = Counter(zip(left, right, strict=True))
    left_counts = Counter(left)
    right_counts = Counter(right)
    count = len(left)

    def disagreement(a: Preference, b: Preference) -> float:
        return ((_ORDINAL[a] - _ORDINAL[b]) / (size - 1)) ** 2

    observed_disagreement = sum(disagreement(a, b) * observed[(a, b)] / count for a in categories for b in categories)
    expected_disagreement = sum(
        disagreement(a, b) * left_counts[a] * right_counts[b] / (count * count)
        for a in categories for b in categories
    )
    if expected_disagreement == 0:
        return 1.0 if observed_disagreement == 0 else 0.0
    return 1 - observed_disagreement / expected_disagreement


def requires_arbitration(
    first_preference: Preference,
    second_preference: Preference,
    first_absolute_scores: dict[str, float],
    second_absolute_scores: dict[str, float],
) -> bool:
    opposite = (
        first_preference.value.startswith("A") and second_preference.value.startswith("B")
    ) or (
        first_preference.value.startswith("B") and second_preference.value.startswith("A")
    )
    score_gap = any(
        abs(first_absolute_scores.get(key, 0) - second_absolute_scores.get(key, 0)) >= 2
        for key in set(first_absolute_scores) | set(second_absolute_scores)
    )
    return opposite or score_gap
