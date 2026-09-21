import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from shopee_affiliate_agent.db.models import IdempotencyRecord
from shopee_affiliate_agent.services.commerce import DomainError


def _json_default(value: object) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID | Enum):
        return str(value)
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def fingerprint(payload: Any) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def replay(
    session: Session,
    *,
    key: str,
    operation: str,
    entity_type: str,
    entity_id: UUID | None,
    actor_id: UUID | None,
    payload: Any,
) -> IdempotencyRecord | None:
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})
    record = session.scalar(
        select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == key)
    )
    if record is None:
        return None
    if (
        record.operation != operation
        or record.entity_type != entity_type
        or (entity_id is not None and record.entity_id != entity_id)
        or record.actor_id != actor_id
        or record.payload_fingerprint != fingerprint(payload)
    ):
        raise DomainError("idempotency_conflict", "idempotency key conflicts with prior request")
    return record


def record(
    session: Session,
    *,
    key: str,
    operation: str,
    entity_type: str,
    entity_id: UUID,
    actor_id: UUID | None,
    payload: Any,
) -> None:
    session.add(
        IdempotencyRecord(
            idempotency_key=key,
            operation=operation,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            payload_fingerprint=fingerprint(payload),
        )
    )
