import asyncio

import pytest
from fastapi import HTTPException
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.schemas import AdapterType, AgentCreate, RiskLevel
from app import security


def test_execution_requires_switch_and_gate_reference() -> None:
    assert not Settings(execution_enabled=False, approved_gate_reference="G1-123").execution_gate_open
    assert not Settings(execution_enabled=True, approved_gate_reference="").execution_gate_open
    assert Settings(execution_enabled=True, approved_gate_reference="G1-123").execution_gate_open


def test_short_internal_token_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(internal_service_token=SecretStr("too-short"))


def test_remote_agent_is_always_runner_only() -> None:
    payload = AgentCreate(name="remote", adapter_type=AdapterType.HTTP, risk_level=RiskLevel.LOW)
    assert payload.isolation_scope == "RUNNER_ONLY"


def test_container_agent_can_use_full_scope() -> None:
    payload = AgentCreate(name="container", adapter_type=AdapterType.CONTAINER, risk_level=RiskLevel.HIGH)
    assert payload.isolation_scope == "FULL"


def test_request_context_rejects_spoofed_headers_without_service_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security.settings, "internal_service_token", SecretStr("x" * 32))
    with pytest.raises(HTTPException) as error:
        asyncio.run(security.require_request_context("wrong", "1", "1", "attacker"))
    assert error.value.status_code == 401
