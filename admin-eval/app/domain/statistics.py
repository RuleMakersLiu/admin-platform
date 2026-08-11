import math
import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ConfidenceInterval:
    estimate: float
    lower: float
    upper: float


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> ConfidenceInterval:
    if total <= 0 or successes < 0 or successes > total:
        raise ValueError("successes and total are invalid")
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return ConfidenceInterval(proportion, max(0.0, center - margin), min(1.0, center + margin))


@dataclass(frozen=True)
class McNemarResult:
    a_only_wins: int
    b_only_wins: int
    p_value: float


def paired_mcnemar(a_passed: Iterable[bool], b_passed: Iterable[bool]) -> McNemarResult:
    pairs = list(zip(a_passed, b_passed, strict=True))
    a_only = sum(a and not b for a, b in pairs)
    b_only = sum(b and not a for a, b in pairs)
    discordant = a_only + b_only
    if discordant == 0:
        return McNemarResult(a_only, b_only, 1.0)
    tail = sum(math.comb(discordant, k) for k in range(0, min(a_only, b_only) + 1)) / (2**discordant)
    return McNemarResult(a_only, b_only, min(1.0, 2 * tail))


def stratified_bootstrap_difference(
    a: dict[str, list[float]],
    b: dict[str, list[float]],
    samples: int = 2_000,
    seed: int = 0,
    statistic: Callable[[list[float]], float] | None = None,
) -> ConfidenceInterval:
    if set(a) != set(b) or not a:
        raise ValueError("A and B must contain the same non-empty strata")
    statistic = statistic or (lambda values: sum(values) / len(values))
    rng = random.Random(seed)
    observed_a = [value for values in a.values() for value in values]
    observed_b = [value for values in b.values() for value in values]
    if not observed_a or not observed_b or any(not values for values in a.values()) or any(not values for values in b.values()):
        raise ValueError("every stratum must contain observations")
    observed = statistic(observed_a) - statistic(observed_b)
    estimates: list[float] = []
    for _ in range(samples):
        sample_a: list[float] = []
        sample_b: list[float] = []
        for stratum in sorted(a):
            sample_a.extend(rng.choices(a[stratum], k=len(a[stratum])))
            sample_b.extend(rng.choices(b[stratum], k=len(b[stratum])))
        estimates.append(statistic(sample_a) - statistic(sample_b))
    estimates.sort()
    lower = estimates[int(0.025 * (samples - 1))]
    upper = estimates[int(0.975 * (samples - 1))]
    return ConfidenceInterval(observed, lower, upper)


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    if any(not 0 <= value <= 1 for value in p_values.values()):
        raise ValueError("p-values must be between 0 and 1")
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    adjusted: dict[str, float] = {}
    running_max = 0.0
    count = len(ordered)
    for index, (name, p_value) in enumerate(ordered):
        running_max = max(running_max, min(1.0, (count - index) * p_value))
        adjusted[name] = running_max
    return adjusted


def pareto_frontier(rows: list[dict[str, float]], maximize: tuple[str, ...], minimize: tuple[str, ...]) -> list[dict[str, float]]:
    def dominates(left: dict[str, float], right: dict[str, float]) -> bool:
        no_worse = all(left[key] >= right[key] for key in maximize) and all(left[key] <= right[key] for key in minimize)
        strictly_better = any(left[key] > right[key] for key in maximize) or any(left[key] < right[key] for key in minimize)
        return no_worse and strictly_better

    return [row for row in rows if not any(other is not row and dominates(other, row) for other in rows)]
