import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID


class Split(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"
    REGRESSION = "REGRESSION"
    HIDDEN = "HIDDEN"


class SourceType(StrEnum):
    DEIDENTIFIED = "DEIDENTIFIED"
    EXPERT = "EXPERT"
    AI_VARIANT = "AI_VARIANT"
    SYNTHETIC = "SYNTHETIC"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class OracleType(StrEnum):
    STATE = "STATE"
    EXACT = "EXACT"
    REFERENCE = "REFERENCE"
    TOOL_TRACE = "TOOL_TRACE"
    HYBRID = "HYBRID"


@dataclass(frozen=True)
class CaseDraft:
    external_id: UUID
    category: str
    risk_level: RiskLevel
    split: Split
    source_type: SourceType
    input_payload: dict[str, Any]
    expected_state: dict[str, Any]
    rubric: dict[str, Any]
    budget: dict[str, Any]
    deterministic_checks: list[dict[str, Any]]
    tool_policy: list[dict[str, Any]]
    oracle_type: OracleType = OracleType.HYBRID
    initial_state_ref: str | None = None
    prohibited_behaviors: tuple[str, ...] = ()
    source_group_id: str | None = None
    source_parent_hash: str | None = None


@dataclass(frozen=True)
class ScanFinding:
    path: str
    category: str


_VALUE_PATTERNS = {
    "EMAIL": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "CN_MOBILE": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "CN_ID": re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)"),
    "PRIVATE_KEY": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "CLOUD_ACCESS_KEY": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "BEARER_TOKEN": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}", re.IGNORECASE),
}
_SENSITIVE_KEYS = re.compile(r"(?:password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key|cookie)", re.IGNORECASE)


def scan_sensitive_data(value: Any, path: str = "$") -> list[ScanFinding]:
    findings: list[ScanFinding] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if _SENSITIVE_KEYS.search(str(key)) and child not in (None, "", "REDACTED", "SYNTHETIC"):
                findings.append(ScanFinding(child_path, "SENSITIVE_KEY"))
            findings.extend(scan_sensitive_data(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(scan_sensitive_data(child, f"{path}[{index}]"))
    elif isinstance(value, str):
        for category, pattern in _VALUE_PATTERNS.items():
            if pattern.search(value):
                findings.append(ScanFinding(path, category))
    return findings


def canonical_case_hash(case: CaseDraft) -> str:
    content = {
        "category": case.category,
        "risk_level": case.risk_level,
        "input_payload": case.input_payload,
        "expected_state": case.expected_state,
        "rubric": case.rubric,
        "budget": case.budget,
        "deterministic_checks": case.deterministic_checks,
        "tool_policy": case.tool_policy,
        "oracle_type": case.oracle_type,
        "initial_state_ref": case.initial_state_ref,
        "prohibited_behaviors": case.prohibited_behaviors,
    }
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_case(case: CaseDraft) -> list[str]:
    errors: list[str] = []
    if not case.category.strip():
        errors.append("category is required")
    if not case.input_payload or not case.expected_state:
        errors.append("input and expected state are required")
    if not case.deterministic_checks:
        errors.append("at least one deterministic check is required")
    if not case.rubric:
        errors.append("rubric is required")
    if case.risk_level == RiskLevel.HIGH and not case.prohibited_behaviors:
        errors.append("high-risk case requires prohibited behaviors")
    if case.source_type == SourceType.AI_VARIANT and not case.source_parent_hash:
        errors.append("AI variant requires immutable parent provenance")
    if scan_sensitive_data({
        "input": case.input_payload,
        "initial_state_ref": case.initial_state_ref,
        "expected": case.expected_state,
        "rubric": case.rubric,
        "checks": case.deterministic_checks,
        "tools": case.tool_policy,
        "budget": case.budget,
    }):
        errors.append("case contains possible personal data or credentials")
    for tool in case.tool_policy:
        if not isinstance(tool.get("tool_id"), str) or not tool["tool_id"].strip():
            errors.append("tool policy requires a non-empty tool_id")
        if not isinstance(tool.get("allowed_actions"), list):
            errors.append("tool policy requires allowed_actions")
        mode = tool.get("side_effect_mode")
        if mode not in {"READ_ONLY", "MOCK_WRITE", "SANDBOX_WRITE"}:
            errors.append("tool policy contains a prohibited side-effect mode")
    timeout = case.budget.get("timeout_seconds")
    tool_calls = case.budget.get("max_tool_calls")
    model_cost = case.budget.get("max_model_cost")
    if not isinstance(timeout, int) or not 1 <= timeout <= 600:
        errors.append("budget.timeout_seconds must be between 1 and 600")
    if not isinstance(tool_calls, int) or not 0 <= tool_calls <= 50:
        errors.append("budget.max_tool_calls must be between 0 and 50")
    if not isinstance(model_cost, (int, float)) or not 0 <= model_cost <= 5:
        errors.append("budget.max_model_cost must be between 0 and 5")
    return errors


def validate_release(cases: list[CaseDraft]) -> list[str]:
    errors: list[str] = []
    hashes: set[str] = set()
    external_ids: set[UUID] = set()
    source_group_splits: dict[str, set[Split]] = {}
    missing_source_groups = 0
    for index, case in enumerate(cases):
        errors.extend(f"case[{index}]: {error}" for error in validate_case(case))
        content_hash = canonical_case_hash(case)
        if content_hash in hashes:
            errors.append(f"case[{index}]: exact duplicate")
        if case.external_id in external_ids:
            errors.append(f"case[{index}]: duplicate external ID")
        hashes.add(content_hash)
        external_ids.add(case.external_id)
        if case.source_group_id:
            source_group_splits.setdefault(case.source_group_id, set()).add(case.split)
        else:
            missing_source_groups += 1
    for group_id, splits in source_group_splits.items():
        if len(splits) > 1:
            errors.append(f"source group {group_id!r} crosses dataset splits")
    if missing_source_groups:
        errors.append(f"{missing_source_groups} case(s) are missing source_group_id")
    if cases:
        split_counts = {split: sum(case.split == split for case in cases) for split in Split}
        if split_counts[Split.HIDDEN] == 0:
            errors.append("release must contain a hidden acceptance split")
        if split_counts[Split.REGRESSION] == 0:
            errors.append("release must contain a fixed regression split")
    return errors


def build_agent_case_payload(case: CaseDraft) -> dict[str, Any]:
    """Return the only Case fields permitted inside an Agent sandbox."""
    return {
        "case_id": str(case.external_id),
        "input": case.input_payload,
        "budget": case.budget,
        "tools": [
            {key: tool[key] for key in ("tool_id", "allowed_actions", "input_schema") if key in tool}
            for tool in case.tool_policy
        ],
    }
