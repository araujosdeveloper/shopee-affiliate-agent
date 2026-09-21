import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from shopee_affiliate_agent.db.models import (
    ImportBatch,
    ImportOutbox,
    ImportRow,
    OperationalAlert,
    Product,
    ProductSnapshot,
)
from shopee_affiliate_agent.domain.enums import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    ImportBatchStatus,
    ImportRowStatus,
    OutboxStatus,
    ProductSource,
)
from shopee_affiliate_agent.services.commerce import DomainError, audit
from shopee_affiliate_agent.services.imports import ParsedRow
from shopee_affiliate_agent.services.normalization import (
    NormalizationError,
    canonical_sha256,
    normalize_product,
)


def create_batch(
    session: Session,
    *,
    source: ProductSource,
    filename: str | None,
    content_type: str,
    payload_hash: str,
    operator_id: UUID,
    key: str,
) -> ImportBatch:
    existing = session.scalar(select(ImportBatch).where(ImportBatch.idempotency_key == key))
    if existing:
        if existing.payload_sha256 != payload_hash:
            raise DomainError("idempotency_conflict", "idempotency key has a different payload")
        return existing
    batch = ImportBatch(
        source=source,
        filename=filename,
        content_type=content_type,
        payload_sha256=payload_hash,
        status=ImportBatchStatus.RECEIVED,
        requested_by_id=operator_id,
        idempotency_key=key,
    )
    session.add(batch)
    session.flush()
    audit(session, "import.received", "import_batch", batch.id, f"audit:{key}", operator_id)
    return batch


def add_rows(session: Session, batch: ImportBatch, rows: list[ParsedRow]) -> None:
    if session.scalar(select(ImportRow.id).where(ImportRow.import_batch_id == batch.id).limit(1)):
        return
    for row in rows:
        raw_json = json.dumps(
            row.raw_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        session.add(
            ImportRow(
                import_batch_id=batch.id,
                row_number=row.row_number,
                external_id=(row.raw_data.get("external_id") or "")[:255],
                raw_data=row.raw_data,
                normalized_data=row.normalized,
                status=ImportRowStatus.REJECTED if row.error_code else ImportRowStatus.PENDING,
                error_code=row.error_code,
                error_message=row.error_message,
                row_sha256=hashlib.sha256(raw_json.encode()).hexdigest(),
            )
        )
    batch.total_rows = len(rows)


def enqueue_import(session: Session, batch: ImportBatch) -> ImportOutbox:
    existing = session.scalar(
        select(ImportOutbox).where(
            ImportOutbox.import_batch_id == batch.id,
            ImportOutbox.task_name == "phase2.process_import",
        )
    )
    if existing:
        return existing
    item = ImportOutbox(
        import_batch_id=batch.id,
        task_name="phase2.process_import",
        status=OutboxStatus.PENDING,
        attempts=0,
        next_attempt_at=datetime.now(UTC),
    )
    session.add(item)
    session.flush()
    audit(
        session,
        "import.outbox_pending",
        "import_outbox",
        item.id,
        f"audit:outbox:pending:{batch.id}",
        batch.requested_by_id,
    )
    return item


def process_batch(session: Session, batch_id: UUID) -> ImportBatch:
    locked = session.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"), {"key": str(batch_id)}
    )
    if not locked:
        raise DomainError("batch_locked", "import batch is already being processed")
    batch = session.get(ImportBatch, batch_id)
    if not batch:
        raise ValueError("batch not found")
    if batch.status in {
        ImportBatchStatus.COMPLETED,
        ImportBatchStatus.PARTIALLY_COMPLETED,
        ImportBatchStatus.FAILED,
        ImportBatchStatus.CANCELLED,
    }:
        outbox = session.scalar(
            select(ImportOutbox).where(ImportOutbox.import_batch_id == batch.id)
        )
        if outbox and outbox.status != OutboxStatus.COMPLETED:
            outbox.status = OutboxStatus.COMPLETED
            outbox.completed_at = datetime.now(UTC)
        return batch
    now = datetime.now(UTC)
    batch.status = ImportBatchStatus.PROCESSING
    batch.started_at = batch.started_at or now
    audit(
        session,
        "import.started",
        "import_batch",
        batch.id,
        f"audit:started:{batch.id}",
        batch.requested_by_id,
    )
    rows = session.scalars(
        select(ImportRow)
        .where(ImportRow.import_batch_id == batch.id)
        .order_by(ImportRow.row_number)
    ).all()
    for row in rows:
        if row.status != ImportRowStatus.PENDING:
            continue
        try:
            with session.begin_nested():
                product_data: dict[str, Any] = row.normalized_data or {}
                normalized = normalize_product(product_data, batch.source)
                product = session.scalar(
                    select(Product).where(
                        Product.source == batch.source,
                        Product.external_id == normalized.external_id,
                    )
                )
                if not product:
                    product = Product(
                        source=batch.source,
                        external_id=normalized.external_id,
                        title=normalized.title,
                        canonical_url=normalized.canonical_url,
                        category=normalized.category,
                        is_active=True,
                    )
                    session.add(product)
                    session.flush()
                    audit(
                        session,
                        "product.created",
                        "product",
                        product.id,
                        f"audit:product:{batch.id}:{row.row_number}",
                        batch.requested_by_id,
                    )
                digest = canonical_sha256(normalized)
                snapshot_key = f"canonical:{digest}"
                snapshot = session.scalar(
                    select(ProductSnapshot).where(ProductSnapshot.idempotency_key == snapshot_key)
                )
                if snapshot:
                    row.status = ImportRowStatus.DUPLICATE
                else:
                    if normalized.source_payload_hash:
                        source_hash_conflict = session.scalar(
                            select(ProductSnapshot).where(
                                ProductSnapshot.source == batch.source,
                                ProductSnapshot.source_payload_hash
                                == normalized.source_payload_hash,
                                ProductSnapshot.idempotency_key != snapshot_key,
                            )
                        )
                        if source_hash_conflict:
                            raise DomainError(
                                "source_payload_hash_conflict",
                                "source payload hash belongs to different evidence",
                            )
                    snapshot = ProductSnapshot(
                        product_id=product.id,
                        source=batch.source,
                        price=normalized.price,
                        currency=normalized.currency,
                        available=normalized.available,
                        collected_at=normalized.collected_at,
                        source_payload_hash=normalized.source_payload_hash or digest,
                        idempotency_key=snapshot_key,
                    )
                    session.add(snapshot)
                    session.flush()
                    row.status = ImportRowStatus.ACCEPTED
                    audit(
                        session,
                        "snapshot.created",
                        "product_snapshot",
                        snapshot.id,
                        f"audit:snapshot:{snapshot.id}",
                        batch.requested_by_id,
                    )
                row.product_id = product.id
                row.product_snapshot_id = snapshot.id
        except DomainError as exc:
            row.status = ImportRowStatus.REJECTED
            row.error_code = exc.code
            row.error_message = "Row conflicts with existing source evidence"
            audit(
                session,
                "import.row_rejected",
                "import_row",
                row.id,
                f"audit:rejected:{row.id}",
                batch.requested_by_id,
            )
        except (NormalizationError, IntegrityError, SQLAlchemyError):
            row.status = ImportRowStatus.REJECTED
            row.error_code = "row_processing_error"
            row.error_message = "Row could not be processed"
            audit(
                session,
                "import.row_rejected",
                "import_row",
                row.id,
                f"audit:rejected:{row.id}",
                batch.requested_by_id,
            )
    batch.accepted_rows = sum(row.status == ImportRowStatus.ACCEPTED for row in rows)
    batch.rejected_rows = sum(row.status == ImportRowStatus.REJECTED for row in rows)
    batch.duplicate_rows = sum(row.status == ImportRowStatus.DUPLICATE for row in rows)
    batch.completed_at = datetime.now(UTC)
    batch.status = (
        ImportBatchStatus.PARTIALLY_COMPLETED
        if batch.rejected_rows and (batch.accepted_rows or batch.duplicate_rows)
        else ImportBatchStatus.FAILED
        if batch.rejected_rows and not (batch.accepted_rows or batch.duplicate_rows)
        else ImportBatchStatus.COMPLETED
    )
    event = {
        ImportBatchStatus.COMPLETED: "import.completed",
        ImportBatchStatus.PARTIALLY_COMPLETED: "import.partially_completed",
        ImportBatchStatus.FAILED: "import.failed",
    }[batch.status]
    audit(
        session,
        event,
        "import_batch",
        batch.id,
        f"audit:finished:{batch.id}",
        batch.requested_by_id,
    )
    if batch.status in {ImportBatchStatus.PARTIALLY_COMPLETED, ImportBatchStatus.FAILED}:
        partial = batch.status == ImportBatchStatus.PARTIALLY_COMPLETED
        alert = OperationalAlert(
            alert_type=(
                AlertType.IMPORT_PARTIALLY_COMPLETED if partial else AlertType.IMPORT_FAILED
            ),
            severity=AlertSeverity.WARNING if partial else AlertSeverity.CRITICAL,
            entity_type="import_batch",
            entity_id=batch.id,
            message=f"Import batch ended with status {batch.status.value}",
            status=AlertStatus.OPEN,
            detected_at=datetime.now(UTC),
            idempotency_key=f"import-status:{batch.id}",
        )
        session.add(alert)
        session.flush()
        audit(
            session,
            "alert.opened",
            "operational_alert",
            alert.id,
            f"audit:alert:{alert.id}",
        )
    outbox = session.scalar(select(ImportOutbox).where(ImportOutbox.import_batch_id == batch.id))
    if outbox:
        if outbox.status != OutboxStatus.COMPLETED:
            outbox.status = OutboxStatus.COMPLETED
            outbox.completed_at = datetime.now(UTC)
            audit(
                session,
                "import.outbox_completed",
                "import_outbox",
                outbox.id,
                f"audit:outbox:completed:{batch.id}",
                batch.requested_by_id,
            )
    return batch
