from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import main, security


def test_health_discloses_closed_gate_without_secrets() -> None:
    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["execution_enabled"] is False
    assert "token" not in response.text.lower()


def test_control_api_rejects_caller_identity_without_gateway_service_token(monkeypatch) -> None:
    monkeypatch.setattr(security.settings, "internal_service_token", SecretStr("s" * 32))
    with TestClient(main.app) as client:
        rejected = client.get("/api/eval/security/approve", headers={
            "X-Admin-Id": "1", "X-Tenant-Id": "1", "X-Username": "spoofed",
        })
        accepted = client.get("/api/eval/security/approve", headers={
            "X-Internal-Service-Token": "s" * 32,
            "X-Admin-Id": "1", "X-Tenant-Id": "1", "X-Username": "trusted",
        })
    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json()["data"]["production_write_tools"] is False
    assert accepted.json()["data"]["remote_agent_isolation"] == "RUNNER_ONLY"


def test_dataset_workflow_routes_are_registered() -> None:
    paths = {route.path for route in main.app.routes}
    assert "/api/eval/dataset/{dataset_id}/cases/import" in paths
    assert "/api/eval/dataset/{dataset_id}/import-golden" in paths
    assert "/api/eval/dataset/version/{version_id}/submit-review" in paths
    assert "/api/eval/dataset/version/{version_id}/review" in paths
    assert "/api/eval/dataset/version/{version_id}/publish" in paths
    assert "/api/eval/dataset/{dataset_id}/version/create" in paths
