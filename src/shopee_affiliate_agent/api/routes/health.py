from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from shopee_affiliate_agent.core.config import Settings, get_settings
from shopee_affiliate_agent.db.session import get_db_session

router = APIRouter(tags=["health"])


class LiveResponse(BaseModel):
    status: Literal["ok"] = "ok"


class DependencyStatus(BaseModel):
    postgres: Literal["ok", "unavailable"]
    redis: Literal["ok", "unavailable"]


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: DependencyStatus


@router.get("/health/live", response_model=LiveResponse)
def live() -> LiveResponse:
    return LiveResponse()


@router.get("/health/ready", response_model=ReadyResponse)
def ready(
    response: Response,
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadyResponse:
    postgres_status: Literal["ok", "unavailable"] = "unavailable"
    redis_status: Literal["ok", "unavailable"] = "unavailable"
    try:
        session.execute(text("SELECT 1"))
        postgres_status = "ok"
    except SQLAlchemyError:
        session.rollback()
    try:
        client: Redis[Any] = Redis.from_url(
            settings.redis_url, socket_connect_timeout=1, socket_timeout=1
        )
        if client.ping():
            redis_status = "ok"
    except (RedisConnectionError, RedisTimeoutError):
        pass
    is_ready = postgres_status == "ok" and redis_status == "ok"
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(
        status="ready" if is_ready else "not_ready",
        dependencies=DependencyStatus(postgres=postgres_status, redis=redis_status),
    )
