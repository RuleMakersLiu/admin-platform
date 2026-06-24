"""Security regression tests for the batch-3/4 hardening.

These are pure-logic tests with no DB or live-server dependency, so they run
fast and deterministically. They lock in:
  - SSRF host validation (flow_manager._is_safe_git_url)
  - JWT secret startup enforcement (config.Settings validator)
  - Identity derived from JWT, not the spoofable X-Tenant-Id header (flow._jwt_claim)
"""
import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_JWT_SECRET, Settings


# ---------- SSRF ----------

def test_is_safe_git_url_allows_known_hosts():
    from app.ai.flow_manager import _is_safe_git_url

    for url in [
        "https://github.com/x/y.git",
        "http://gitlab.com/x/y.git",
        "https://gitee.com/x/y.git",
    ]:
        ok, reason = _is_safe_git_url(url)
        assert ok, f"{url} should be allowed ({reason})"


def test_is_safe_git_url_blocks_ssrf_targets():
    from app.ai.flow_manager import _is_safe_git_url

    bad = [
        "http://127.0.0.1:6379/x",          # loopback
        "http://169.254.169.254/latest",    # cloud metadata
        "http://10.0.0.1/x",                # private
        "http://192.168.1.1/x",             # private
        "file:///etc/passwd",               # bad scheme
        "http://localhost/x",               # localhost
        "http://metadata.google.internal/x",
    ]
    for url in bad:
        ok, _ = _is_safe_git_url(url)
        assert not ok, f"{url} should be blocked"


# ---------- JWT secret startup enforcement ----------

def test_jwt_secret_validator_rejects_insecure_in_production():
    with pytest.raises((ValidationError, ValueError)):
        Settings(debug=False, jwt_secret=DEFAULT_JWT_SECRET)
    with pytest.raises((ValidationError, ValueError)):
        Settings(debug=False, jwt_secret="")


def test_jwt_secret_validator_allows_real_secret_and_dev():
    # real secret in prod
    Settings(debug=False, jwt_secret="a-real-random-secret")
    # dev keeps working with the default
    Settings(debug=True)


# ---------- Identity from JWT (anti privilege escalation) ----------

def test_identity_derived_from_jwt_not_spoofable_header():
    import jwt as _jwt
    from app.api.flow import _jwt_claim
    from app.core.config import settings

    class H:
        def __init__(self, d):
            self.d = d

        def get(self, k, default=None):
            return self.d.get(k, default)

    class R:
        def __init__(self, h):
            self.headers = h

    token = _jwt.encode({"adminId": 42, "tenantId": 7}, settings.jwt_secret, algorithm="HS256")

    # spoofed X-Tenant-Id:999 must be ignored — value comes from the JWT
    r = R(H({"authorization": f"Bearer {token}", "X-Tenant-Id": "999"}))
    assert _jwt_claim(r, "tenantId") == 7
    assert _jwt_claim(r, "adminId") == 42

    # missing token -> default
    assert _jwt_claim(R(H({})), "tenantId") == 0
    assert _jwt_claim(R(H({})), "adminId") == 0
