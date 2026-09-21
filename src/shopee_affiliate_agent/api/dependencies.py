import secrets
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from shopee_affiliate_agent.core.config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


def require_internal_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    expected = settings.INTERNAL_API_TOKEN.get_secret_value()
    received = credentials.credentials if credentials else ""
    if not expected or not secrets.compare_digest(received, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_operator_id(x_operator_id: Annotated[str | None, Header()] = None) -> UUID:
    if not x_operator_id:
        raise HTTPException(status_code=400, detail="X-Operator-ID is required")
    try:
        return UUID(x_operator_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="X-Operator-ID must be a UUID") from exc


def require_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if not idempotency_key or len(idempotency_key) > 255:
        raise HTTPException(status_code=400, detail="A valid Idempotency-Key is required")
    return idempotency_key
