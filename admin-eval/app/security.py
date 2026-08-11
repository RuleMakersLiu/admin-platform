import hmac
from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from app.config import settings


@dataclass(frozen=True)
class RequestContext:
    admin_id: int
    tenant_id: int
    username: str


async def require_request_context(
    x_internal_service_token: str = Header(default=""),
    x_admin_id: str = Header(default=""),
    x_tenant_id: str = Header(default=""),
    x_username: str = Header(default=""),
) -> RequestContext:
    expected = settings.internal_service_token.get_secret_value()
    if not expected or not hmac.compare_digest(x_internal_service_token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid service identity")
    try:
        admin_id = int(x_admin_id)
        tenant_id = int(x_tenant_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid identity context") from exc
    if admin_id <= 0 or tenant_id <= 0 or not x_username.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="incomplete identity context")
    return RequestContext(admin_id=admin_id, tenant_id=tenant_id, username=x_username.strip())
