import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from shopee_affiliate_agent.api.dependencies import require_internal_token
from shopee_affiliate_agent.api.routes import health, phase2, system
from shopee_affiliate_agent.core.config import get_settings
from shopee_affiliate_agent.core.logging import configure_logging
from shopee_affiliate_agent.services.commerce import DomainError

settings = get_settings()
configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))[:64]
        request.state.request_id = request_id
        started = time.monotonic()
        content_length = request.headers.get("content-length")
        if (
            content_length
            and content_length.isdigit()
            and int(content_length) > 5 * 1024 * 1024 + 64 * 1024
        ):
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "import_limit_exceeded",
                        "message": "Request payload is too large",
                    },
                    "request_id": request_id,
                },
                headers={"X-Request-ID": request_id},
            )
        has_body = (
            content_length is not None and content_length.isdigit() and int(content_length) > 0
        )
        if (
            has_body
            and request.method in {"POST", "PATCH", "PUT"}
            and request.url.path.startswith("/api/v1")
        ):
            content_type = request.headers.get("content-type", "").split(";", 1)[0]
            if content_type not in {
                "application/json",
                "text/csv",
                "application/csv",
                "application/vnd.ms-excel",
                "multipart/form-data",
            }:
                return JSONResponse(
                    status_code=415,
                    content={
                        "error": {
                            "code": "validation_error",
                            "message": "Unsupported Content-Type",
                        },
                        "request_id": request_id,
                    },
                    headers={"X-Request-ID": request_id},
                )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            },
        )
        return response


@asynccontextmanager
async def lifespan(_: FastAPI) -> Any:
    logger.info("application_started", extra={"request_id": None})
    yield
    logger.info("application_stopped", extra={"request_id": None})


app = FastAPI(
    title="Shopee Affiliate Agent API",
    description="Deterministic and compliance-first internal API.",
    version="0.2.0",
    lifespan=lifespan,
)
app.add_middleware(RequestContextMiddleware)
app.include_router(health.router)
app.include_router(system.router, dependencies=[Depends(require_internal_token)])
app.include_router(phase2.router, dependencies=[Depends(require_internal_token)])


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    known_codes = {
        "authentication_required",
        "not_found",
        "conflict",
        "stale_version",
        "idempotency_conflict",
        "source_payload_hash_conflict",
        "unsupported_source",
        "invalid_import_file",
        "import_limit_exceeded",
        "product_snapshot_mismatch",
        "stale_snapshot",
        "future_snapshot",
        "score_below_threshold",
        "invalid_state_transition",
    }
    detail = str(exc.detail)
    normalized = detail.lower().replace(" ", "_")
    code = (
        normalized
        if normalized in known_codes
        else "authentication_required"
        if exc.status_code == 401
        else "not_found"
        if exc.status_code == 404
        else "conflict"
        if exc.status_code == 409
        else "validation_error"
        if exc.status_code in {400, 413, 415, 422}
        else "http_error"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {"code": code, "message": detail},
            "request_id": getattr(request.state, "request_id", None),
        },
        headers=exc.headers,
    )


@app.exception_handler(DomainError)
async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": {"code": exc.code, "message": str(exc)},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {"code": "validation_error", "message": "Request validation failed"},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled_error", exc_info=exc, extra={"request_id": request.state.request_id}
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {"code": "internal_error", "message": "Internal server error"},
            "request_id": request.state.request_id,
        },
    )
