"""Test configuration and fixtures for integration tests"""
import pytest
import httpx

# Base URL for the running server
BASE_URL = "http://localhost:8080"


@pytest.fixture
def client() -> httpx.Client:
    """Create a sync HTTP client for testing."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
        yield c


@pytest.fixture
def auth_token(client: httpx.Client) -> str:
    """Get authentication token for testing."""
    response = client.post(
        "/api/auth/login",
        json={
            "username": "admin",
            "password": "admin123",
            "tenantId": 1
        }
    )
    assert response.status_code == 200
    data = response.json()
    return data["data"]["token"]


@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    """Get authorization headers for testing."""
    return {"Authorization": f"Bearer {auth_token}"}
