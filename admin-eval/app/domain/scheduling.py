import hashlib
import hmac
import random
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class TrialPlan:
    case_id: UUID
    agent_version_id: UUID
    repetition: int
    execution_order: int
    idempotency_key: str


def paired_trial_plan(case_ids: list[UUID], agent_version_ids: list[UUID], repetitions: int, seed: int) -> list[TrialPlan]:
    if not case_ids or len(agent_version_ids) < 2 or repetitions < 1:
        raise ValueError("paired experiments require cases, two agents, and repetitions")
    if len(set(case_ids)) != len(case_ids) or len(set(agent_version_ids)) != len(agent_version_ids):
        raise ValueError("case and Agent version IDs must be unique")
    candidates = [(case_id, agent_id, repetition) for case_id in case_ids for repetition in range(1, repetitions + 1) for agent_id in agent_version_ids]
    random.Random(seed).shuffle(candidates)
    return [
        TrialPlan(
            case_id=case_id,
            agent_version_id=agent_id,
            repetition=repetition,
            execution_order=index,
            idempotency_key=hashlib.sha256(f"{case_id}:{agent_id}:{repetition}".encode()).hexdigest(),
        )
        for index, (case_id, agent_id, repetition) in enumerate(candidates)
    ]


def blind_ab_order(trial_a: UUID, trial_b: UUID, review_id: UUID, secret: bytes) -> tuple[UUID, UUID, str]:
    if len(secret) < 32:
        raise ValueError("blind-order secret must contain at least 32 bytes")
    digest = hmac.new(secret, f"{review_id}:{trial_a}:{trial_b}".encode(), hashlib.sha256).digest()
    ordered = (trial_a, trial_b) if digest[0] % 2 == 0 else (trial_b, trial_a)
    proof = hmac.new(secret, f"{review_id}:{ordered[0]}:{ordered[1]}".encode(), hashlib.sha256).hexdigest()
    return ordered[0], ordered[1], proof
