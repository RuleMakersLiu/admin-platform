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


@dataclass(frozen=True)
class CaseDraft:
    external_id: UUID
    category: str
    split: Split
    source_type: SourceType
    input_payload: dict[str, Any]
    expected_state: dict[str, Any]
    rubric: dict[str, Any]
    budget: dict[str, Any]
    deterministic_checks: list[dict[str, Any]]
    tool_policy: list[dict[str, Any]]
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
        "input_payload": case.input_payload,
        "expected_state": case.expected_state,
        "rubric": case.rubric,
        "budget": case.budget,
        "deterministic_checks": case.deterministic_checks,
        "tool_policy": case.tool_policy,
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
    if case.source_type == SourceType.AI_VARIANT and not case.source_parent_hash:
        errors.append("AI variant requires immutable parent provenance")
    if scan_sensitive_data({
        "input": case.input_payload,
        "expected": case.expected_state,
        "rubric": case.rubric,
    }):
        errors.append("case contains possible personal data or credentials")
    for tool in case.tool_policy:
        mode = tool.get("side_effect_mode")
        if mode not in {"READ_ONLY", "MOCK_WRITE", "SANDBOX_WRITE"}:
            errors.append("tool policy contains a prohibited side-effect mode")
    return errors


def validate_release(cases: list[CaseDraft]) -> list[str]:
    errors: list[str] = []
    hashes: set[str] = set()
    external_ids: set[UUID] = set()
    for index, case in enumerate(cases):
        errors.extend(f"case[{index}]: {error}" for error in validate_case(case))
        content_hash = canonical_case_hash(case)
        if content_hash in hashes:
            errors.append(f"case[{index}]: exact duplicate")
        if case.external_id in external_ids:
            errors.append(f"case[{index}]: duplicate external ID")
        hashes.add(content_hash)
        external_ids.add(case.external_id)
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
