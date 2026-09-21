from uuid import UUID

from celery import Celery, Task
from celery.schedules import crontab
from sqlalchemy.exc import OperationalError

from shopee_affiliate_agent.core.config import get_settings

settings = get_settings()
celery_app = Celery("shopee_affiliate_agent", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    worker_concurrency=1,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=120,
    task_soft_time_limit=110,
    task_default_retry_delay=5,
    task_publish_retry=False,
    beat_schedule={
        "expire-opportunities-every-15-minutes": {
            "task": "phase2.expire_opportunities",
            "schedule": crontab(minute="*/15"),
        }
    },
)


class ImportTask(Task):  # type: ignore[misc]
    def on_failure(
        self,
        exc: BaseException,
        task_id: str,
        args: tuple[object, ...],
        kwargs: dict[str, object],
        einfo: object,
    ) -> None:
        from datetime import UTC, datetime

        from shopee_affiliate_agent.db.models import ImportBatch, OperationalAlert
        from shopee_affiliate_agent.db.session import SessionFactory
        from shopee_affiliate_agent.domain.enums import (
            AlertSeverity,
            AlertStatus,
            AlertType,
            ImportBatchStatus,
        )
        from shopee_affiliate_agent.services.commerce import audit

        if not args:
            return
        batch_id = UUID(str(args[0]))
        with SessionFactory.begin() as session:
            batch = session.get(ImportBatch, batch_id)
            if not batch or batch.status in {
                ImportBatchStatus.COMPLETED,
                ImportBatchStatus.PARTIALLY_COMPLETED,
                ImportBatchStatus.CANCELLED,
            }:
                return
            batch.status = ImportBatchStatus.FAILED
            batch.completed_at = datetime.now(UTC)
            alert = OperationalAlert(
                alert_type=AlertType.IMPORT_FAILED,
                severity=AlertSeverity.CRITICAL,
                entity_type="import_batch",
                entity_id=batch.id,
                message="Import processing failed after retry limit",
                status=AlertStatus.OPEN,
                detected_at=datetime.now(UTC),
                idempotency_key=f"import-worker-failed:{batch.id}",
            )
            session.add(alert)
            session.flush()
            audit(
                session,
                "import.failed",
                "import_batch",
                batch.id,
                f"audit:worker-failed:{batch.id}",
            )
            audit(
                session,
                "alert.opened",
                "operational_alert",
                alert.id,
                f"audit:alert:{alert.id}",
            )


@celery_app.task(  # type: ignore[misc]
    name="phase2.process_import",
    bind=True,
    base=ImportTask,
    autoretry_for=(ConnectionError, OperationalError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=4,
)
def process_import_task(self: object, batch_id: str) -> None:
    from shopee_affiliate_agent.db.session import SessionFactory
    from shopee_affiliate_agent.services.ingestion import process_batch

    with SessionFactory.begin() as session:
        process_batch(session, UUID(batch_id))


@celery_app.task(name="phase2.expire_opportunities")  # type: ignore[misc]
def expire_opportunities_task() -> int:
    from shopee_affiliate_agent.db.session import SessionFactory
    from shopee_affiliate_agent.services.commerce import expire_opportunities

    with SessionFactory.begin() as session:
        return expire_opportunities(session)
