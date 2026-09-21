from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import kombu.exceptions  # type: ignore[import-untyped]
import pytest
from sqlalchemy import func, select, text, update

from shopee_affiliate_agent.api.routes.phase2 import cancel_import
from shopee_affiliate_agent.api.schemas import VersionAction
from shopee_affiliate_agent.db.models import (
    AuditEvent,
    ImportBatch,
    ImportOutbox,
    ImportRow,
    OperationalAlert,
)
from shopee_affiliate_agent.db.session import SessionFactory
from shopee_affiliate_agent.domain.enums import ImportBatchStatus, OutboxStatus, ProductSource
from shopee_affiliate_agent.services.commerce import DomainError
from shopee_affiliate_agent.services.imports import ParsedRow
from shopee_affiliate_agent.services.ingestion import (
    add_rows,
    create_batch,
    enqueue_import,
    process_batch,
)
from shopee_affiliate_agent.worker import dispatch_import_outbox_task, process_import_task

pytestmark = pytest.mark.integration


def create_operator() -> UUID:
    operator_id = uuid4()
    with SessionFactory.begin() as session:
        session.execute(
            text("""
                INSERT INTO operators
                    (id,email,display_name,role,is_active,version,created_at,updated_at)
                VALUES (:id,:email,'Outbox','admin',true,1,now(),now())
            """),
            {"id": operator_id, "email": f"{operator_id}@example.test"},
        )
    return operator_id


def create_durable_batch(operator_id: UUID) -> tuple[UUID, UUID]:
    suffix = str(uuid4())
    row = {
        "external_id": f"outbox-{suffix}",
        "title": "Outbox product",
        "price": "10.00",
        "currency": "BRL",
        "available": "true",
        "collected_at": datetime.now(UTC).isoformat(),
    }
    with SessionFactory.begin() as session:
        session.execute(
            update(ImportOutbox)
            .where(ImportOutbox.status != OutboxStatus.COMPLETED)
            .values(status=OutboxStatus.COMPLETED, completed_at=datetime.now(UTC))
        )
        batch = create_batch(
            session,
            source=ProductSource.OFFICIAL_IMPORT,
            filename="official.csv",
            content_type="text/csv",
            payload_hash=uuid4().hex.ljust(64, "0"),
            operator_id=operator_id,
            key=f"outbox-batch-{suffix}",
        )
        add_rows(session, batch, [ParsedRow(1, row, row)])
        outbox = enqueue_import(session, batch)
        return batch.id, outbox.id


def test_batch_rows_and_outbox_share_the_same_transaction() -> None:
    operator = create_operator()
    batch_id, outbox_id = create_durable_batch(operator)
    with SessionFactory() as session:
        assert session.get(ImportBatch, batch_id) is not None
        assert session.get(ImportOutbox, outbox_id) is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(ImportRow)
                .where(ImportRow.import_batch_id == batch_id)
            )
            == 1
        )

    rolled_back_batch = uuid4()
    with pytest.raises(RuntimeError, match="rollback"):
        with SessionFactory.begin() as session:
            batch = create_batch(
                session,
                source=ProductSource.OFFICIAL_IMPORT,
                filename="rollback.csv",
                content_type="text/csv",
                payload_hash="d" * 64,
                operator_id=operator,
                key=f"rollback-{rolled_back_batch}",
            )
            rolled_back_batch = batch.id
            add_rows(
                session,
                batch,
                [
                    ParsedRow(
                        1,
                        {"external_id": "rollback"},
                        {"external_id": "rollback"},
                    )
                ],
            )
            enqueue_import(session, batch)
            raise RuntimeError("rollback")
    with SessionFactory() as session:
        assert session.get(ImportBatch, rolled_back_batch) is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(ImportRow)
                .where(ImportRow.import_batch_id == rolled_back_batch)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ImportOutbox)
                .where(ImportOutbox.import_batch_id == rolled_back_batch)
            )
            == 0
        )


def test_outbox_failure_recovery_completion_and_repeated_task_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = create_operator()
    batch_id, outbox_id = create_durable_batch(operator)

    def unavailable(*args: object, **kwargs: object) -> None:
        raise kombu.exceptions.OperationalError("broker unavailable")

    monkeypatch.setattr(process_import_task, "apply_async", unavailable)
    assert dispatch_import_outbox_task.run() == 0
    with SessionFactory() as session:
        outbox = session.get(ImportOutbox, outbox_id)
        assert outbox is not None
        assert outbox.status == OutboxStatus.FAILED
        assert outbox.attempts == 1
        assert outbox.next_attempt_at > datetime.now(UTC)
        assert outbox.last_error_code == "broker_unavailable"

    with SessionFactory.begin() as session:
        outbox = session.get(ImportOutbox, outbox_id)
        assert outbox is not None
        outbox.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    monkeypatch.setattr(process_import_task, "apply_async", lambda *args, **kwargs: None)
    assert dispatch_import_outbox_task.run() == 1
    with SessionFactory() as session:
        outbox = session.get(ImportOutbox, outbox_id)
        assert outbox is not None and outbox.status == OutboxStatus.PUBLISHED

    with SessionFactory.begin() as session:
        process_batch(session, batch_id)
    with SessionFactory() as session:
        outbox = session.get(ImportOutbox, outbox_id)
        batch = session.get(ImportBatch, batch_id)
        assert outbox is not None and outbox.status == OutboxStatus.COMPLETED
        assert batch is not None and batch.status == ImportBatchStatus.COMPLETED
        row_count = session.scalar(
            select(func.count()).select_from(ImportRow).where(ImportRow.import_batch_id == batch_id)
        )
        audit_count = session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == batch_id)
        )
    with SessionFactory.begin() as session:
        process_batch(session, batch_id)
    with SessionFactory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ImportRow)
                .where(ImportRow.import_batch_id == batch_id)
            )
            == row_count
        )
        assert (
            session.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == batch_id)
            )
            == audit_count
        )


def test_fifth_dispatch_failure_creates_one_alert_and_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = create_operator()
    batch_id, outbox_id = create_durable_batch(operator)

    def unavailable(*args: object, **kwargs: object) -> None:
        raise kombu.exceptions.OperationalError("sensitive broker detail")

    monkeypatch.setattr(process_import_task, "apply_async", unavailable)
    for _ in range(5):
        with SessionFactory.begin() as session:
            outbox = session.get(ImportOutbox, outbox_id)
            assert outbox is not None
            outbox.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        dispatch_import_outbox_task.run()
    dispatch_import_outbox_task.run()
    with SessionFactory() as session:
        outbox = session.get(ImportOutbox, outbox_id)
        assert outbox is not None
        assert outbox.status == OutboxStatus.FAILED
        assert outbox.attempts == 5
        assert outbox.last_error_code == "broker_unavailable"
        alerts = session.scalar(
            select(func.count())
            .select_from(OperationalAlert)
            .where(
                OperationalAlert.entity_id == batch_id,
                OperationalAlert.idempotency_key == f"outbox-exhausted:{batch_id}",
            )
        )
        assert alerts == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.event_type == "import.outbox_failed",
                    AuditEvent.entity_id == outbox_id,
                )
            )
            == 5
        )


def test_cancelled_batch_completes_outbox_and_later_processing_is_noop() -> None:
    operator = create_operator()
    batch_id, outbox_id = create_durable_batch(operator)
    with SessionFactory() as session:
        batch = session.get(ImportBatch, batch_id)
        assert batch is not None
        cancelled = cancel_import(
            batch_id,
            VersionAction(version=batch.version),
            session,
            operator,
            f"cancel-{uuid4()}",
        )
        cancelled_version = cancelled.version
    with SessionFactory.begin() as session:
        process_batch(session, batch_id)
    with SessionFactory() as session:
        batch = session.get(ImportBatch, batch_id)
        outbox = session.get(ImportOutbox, outbox_id)
        assert batch is not None and batch.status == ImportBatchStatus.CANCELLED
        assert batch.version == cancelled_version
        assert outbox is not None and outbox.status == OutboxStatus.COMPLETED


def test_skip_locked_and_batch_advisory_lock_prevent_concurrent_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = create_operator()
    batch_id, outbox_id = create_durable_batch(operator)
    published: list[str] = []
    monkeypatch.setattr(
        process_import_task,
        "apply_async",
        lambda args: published.append(str(args[0])),
    )
    with SessionFactory.begin() as locking_session:
        locked = locking_session.scalar(
            select(ImportOutbox).where(ImportOutbox.id == outbox_id).with_for_update()
        )
        assert locked is not None
        assert dispatch_import_outbox_task.run() == 0
        assert published == []

    with SessionFactory.begin() as locking_session:
        assert locking_session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
            {"key": str(batch_id)},
        )
        with SessionFactory.begin() as competing_session:
            with pytest.raises(DomainError) as locked_error:
                process_batch(competing_session, batch_id)
            assert locked_error.value.code == "batch_locked"

    process_import_task.run(str(batch_id))
    with SessionFactory() as session:
        batch = session.get(ImportBatch, batch_id)
        assert batch is not None and batch.status == ImportBatchStatus.COMPLETED
        assert (
            session.scalar(
                select(func.count())
                .select_from(OperationalAlert)
                .where(
                    OperationalAlert.entity_id == batch_id,
                    OperationalAlert.idempotency_key == f"import-worker-failed:{batch_id}",
                )
            )
            == 0
        )
