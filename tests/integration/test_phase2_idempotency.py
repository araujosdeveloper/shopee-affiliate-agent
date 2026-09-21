from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from starlette.datastructures import Headers, UploadFile

from shopee_affiliate_agent.api.routes.phase2 import (
    acknowledge_alert,
    cancel_import,
    create_assessment,
    create_opportunity,
    create_product,
    create_snapshot,
    dismiss,
    manual_import,
    official_import,
    resolve_alert,
    score_assessment,
    shortlist,
    update_product,
)
from shopee_affiliate_agent.api.schemas import (
    AssessmentCreate,
    DismissAction,
    ManualImportCreate,
    ProductCreate,
    ProductUpdate,
    SnapshotCreate,
    VersionAction,
)
from shopee_affiliate_agent.db.models import (
    AuditEvent,
    ImportBatch,
    OperationalAlert,
    Product,
    ProductAssessment,
    ProductOpportunity,
    ProductScore,
    ProductSnapshot,
)
from shopee_affiliate_agent.db.session import SessionFactory
from shopee_affiliate_agent.services.commerce import DomainError
from shopee_affiliate_agent.worker import process_import_task

pytestmark = pytest.mark.integration


def create_operator() -> UUID:
    operator_id = uuid4()
    with SessionFactory.begin() as session:
        session.execute(
            text("""
                INSERT INTO operators
                    (id,email,display_name,role,is_active,version,created_at,updated_at)
                VALUES (:id,:email,'Idempotency','admin',true,1,now(),now())
            """),
            {"id": operator_id, "email": f"{operator_id}@example.test"},
        )
    return operator_id


def count(session: object, model: object) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_product_and_update_replays_preserve_resource_version_and_audit() -> None:
    operator = create_operator()
    other_operator = create_operator()
    create_key = f"create-{uuid4()}"
    body = ProductCreate(external_id=str(uuid4()), title="Replay product")
    with SessionFactory() as session:
        product = create_product(body, session, operator, create_key)
        product_count = count(session, Product)
        audit_count = count(session, AuditEvent)
        replayed = create_product(body, session, operator, create_key)
        assert replayed.id == product.id
        assert count(session, Product) == product_count
        assert count(session, AuditEvent) == audit_count
        with pytest.raises(DomainError, match="conflicts"):
            create_product(
                ProductCreate(external_id=body.external_id, title="Different"),
                session,
                operator,
                create_key,
            )
        with pytest.raises(DomainError, match="conflicts"):
            create_product(body, session, other_operator, create_key)

        update_key = f"update-{uuid4()}"
        action = ProductUpdate(title="Updated once", version=product.version)
        updated = update_product(product.id, action, session, operator, update_key)
        version = updated.version
        audit_count = count(session, AuditEvent)
        replayed_update = update_product(product.id, action, session, operator, update_key)
        assert replayed_update.version == version
        assert count(session, AuditEvent) == audit_count
        with pytest.raises(DomainError, match="conflicts"):
            update_product(
                product.id,
                ProductUpdate(title="Different update", version=action.version),
                session,
                operator,
                update_key,
            )
        other = create_product(
            ProductCreate(external_id=str(uuid4()), title="Other product"),
            session,
            operator,
            f"other-{uuid4()}",
        )
        with pytest.raises(DomainError, match="conflicts"):
            update_product(other.id, action, session, operator, update_key)
        with pytest.raises(DomainError, match="conflicts"):
            update_product(product.id, action, session, other_operator, update_key)


def test_snapshot_parent_scope_canonical_dedup_and_source_hash_conflict() -> None:
    operator = create_operator()
    other_operator = create_operator()
    with SessionFactory() as session:
        first_product = create_product(
            ProductCreate(external_id=str(uuid4()), title="Snapshot parent one"),
            session,
            operator,
            f"product-{uuid4()}",
        )
        second_product = create_product(
            ProductCreate(external_id=str(uuid4()), title="Snapshot parent two"),
            session,
            operator,
            f"product-{uuid4()}",
        )
        body = SnapshotCreate(
            price=Decimal("10.00"),
            currency="BRL",
            available=True,
            collected_at=datetime.now(UTC),
            source_payload_hash="a" * 64,
        )
        key = f"snapshot-{uuid4()}"
        snapshot = create_snapshot(first_product.id, body, session, operator, key)
        assert snapshot.idempotency_key.startswith("canonical:")
        snapshot_count = count(session, ProductSnapshot)
        audit_count = count(session, AuditEvent)
        replayed = create_snapshot(first_product.id, body, session, operator, key)
        assert replayed.id == snapshot.id
        assert count(session, ProductSnapshot) == snapshot_count
        assert count(session, AuditEvent) == audit_count
        with pytest.raises(DomainError, match="conflicts"):
            create_snapshot(second_product.id, body, session, operator, key)
        with pytest.raises(DomainError, match="conflicts"):
            create_snapshot(first_product.id, body, session, other_operator, key)
        with pytest.raises(DomainError, match="conflicts"):
            create_snapshot(
                first_product.id,
                body.model_copy(update={"price": Decimal("11.00")}),
                session,
                operator,
                key,
            )

        deduped = create_snapshot(
            first_product.id, body, session, operator, f"snapshot-dedupe-{uuid4()}"
        )
        assert deduped.id == snapshot.id
        assert count(session, ProductSnapshot) == snapshot_count
        with pytest.raises(HTTPException) as conflict:
            create_snapshot(
                first_product.id,
                body.model_copy(update={"price": Decimal("11.00")}),
                session,
                operator,
                f"snapshot-conflict-{uuid4()}",
            )
        assert conflict.value.status_code == 409
        assert conflict.value.detail == "source_payload_hash_conflict"


def test_assessment_parent_is_part_of_idempotency_context() -> None:
    operator = create_operator()
    other_operator = create_operator()
    with SessionFactory() as session:
        product = create_product(
            ProductCreate(external_id=str(uuid4()), title="Assessment parent"),
            session,
            operator,
            f"product-{uuid4()}",
        )
        other = create_product(
            ProductCreate(external_id=str(uuid4()), title="Other assessment parent"),
            session,
            operator,
            f"product-{uuid4()}",
        )
        snapshot = create_snapshot(
            product.id,
            SnapshotCreate(
                price=Decimal("20.00"),
                currency="BRL",
                available=True,
                collected_at=datetime.now(UTC),
            ),
            session,
            operator,
            f"snapshot-{uuid4()}",
        )
        body = AssessmentCreate(
            product_snapshot_id=snapshot.id,
            conversion_potential=Decimal("80"),
            net_commission=Decimal("80"),
            product_quality=Decimal("80"),
            price_stock_stability=Decimal("80"),
            niche_fit=Decimal("80"),
            video_demonstration_potential=Decimal("80"),
            cancellation_quality=Decimal("80"),
        )
        key = f"assessment-{uuid4()}"
        assessment = create_assessment(product.id, body, session, operator, key)
        resource_count = count(session, ProductAssessment)
        audit_count = count(session, AuditEvent)
        replayed = create_assessment(product.id, body, session, operator, key)
        assert replayed.id == assessment.id
        assert count(session, ProductAssessment) == resource_count
        assert count(session, AuditEvent) == audit_count
        with pytest.raises(DomainError, match="conflicts"):
            create_assessment(other.id, body, session, operator, key)
        with pytest.raises(DomainError, match="conflicts"):
            create_assessment(product.id, body, session, other_operator, key)
        with pytest.raises(DomainError, match="conflicts"):
            create_assessment(
                product.id,
                body.model_copy(update={"rule_version": "different"}),
                session,
                operator,
                key,
            )


def assessment_body(snapshot_id: UUID, value: str = "90") -> AssessmentCreate:
    score = Decimal(value)
    return AssessmentCreate(
        product_snapshot_id=snapshot_id,
        conversion_potential=score,
        net_commission=score,
        product_quality=score,
        price_stock_stability=score,
        niche_fit=score,
        video_demonstration_potential=score,
        cancellation_quality=score,
    )


def test_score_opportunity_and_human_action_replays_are_context_scoped() -> None:
    operator = create_operator()
    other_operator = create_operator()
    with SessionFactory() as session:
        product = create_product(
            ProductCreate(external_id=str(uuid4()), title="Commerce replay"),
            session,
            operator,
            f"product-{uuid4()}",
        )
        snapshot = create_snapshot(
            product.id,
            SnapshotCreate(
                price=Decimal("30.00"),
                currency="BRL",
                available=True,
                collected_at=datetime.now(UTC),
            ),
            session,
            operator,
            f"snapshot-{uuid4()}",
        )
        first_assessment = create_assessment(
            product.id,
            assessment_body(snapshot.id),
            session,
            operator,
            f"assessment-{uuid4()}",
        )
        second_assessment = create_assessment(
            product.id,
            assessment_body(snapshot.id, "95"),
            session,
            operator,
            f"assessment-{uuid4()}",
        )
        score_key = f"score-{uuid4()}"
        score = score_assessment(first_assessment.id, session, score_key)
        score_count = count(session, ProductScore)
        audit_count = count(session, AuditEvent)
        replayed_score = score_assessment(first_assessment.id, session, score_key)
        assert replayed_score.id == score.id
        assert count(session, ProductScore) == score_count
        assert count(session, AuditEvent) == audit_count
        with pytest.raises(DomainError, match="conflicts"):
            score_assessment(second_assessment.id, session, score_key)

        second_score = score_assessment(second_assessment.id, session, f"score-{uuid4()}")
        opportunity_key = f"opportunity-{uuid4()}"
        opportunity = create_opportunity(score.id, session, opportunity_key)
        opportunity_count = count(session, ProductOpportunity)
        audit_count = count(session, AuditEvent)
        replayed_opportunity = create_opportunity(score.id, session, opportunity_key)
        assert replayed_opportunity.id == opportunity.id
        assert count(session, ProductOpportunity) == opportunity_count
        assert count(session, AuditEvent) == audit_count
        with pytest.raises(DomainError, match="conflicts"):
            create_opportunity(second_score.id, session, opportunity_key)

        shortlist_key = f"shortlist-{uuid4()}"
        shortlist_action = VersionAction(version=opportunity.version)
        shortlisted = shortlist(opportunity.id, shortlist_action, session, operator, shortlist_key)
        shortlisted_version = shortlisted.version
        audit_count = count(session, AuditEvent)
        replayed_shortlist = shortlist(
            opportunity.id, shortlist_action, session, operator, shortlist_key
        )
        assert replayed_shortlist.version == shortlisted_version
        assert count(session, AuditEvent) == audit_count
        with pytest.raises(DomainError, match="conflicts"):
            shortlist(
                opportunity.id,
                VersionAction(version=shortlist_action.version + 1),
                session,
                operator,
                shortlist_key,
            )
        with pytest.raises(DomainError, match="conflicts"):
            shortlist(opportunity.id, shortlist_action, session, other_operator, shortlist_key)
        other_candidate = create_opportunity(score.id, session, f"opportunity-{uuid4()}")
        with pytest.raises(DomainError, match="conflicts"):
            shortlist(
                other_candidate.id,
                VersionAction(version=other_candidate.version),
                session,
                operator,
                shortlist_key,
            )

        dismissible = create_opportunity(score.id, session, f"opportunity-{uuid4()}")
        dismiss_key = f"dismiss-{uuid4()}"
        dismiss_action = DismissAction(version=dismissible.version, reason="not selected")
        dismissed = dismiss(dismissible.id, dismiss_action, session, operator, dismiss_key)
        dismissed_version = dismissed.version
        audit_count = count(session, AuditEvent)
        replayed_dismiss = dismiss(dismissible.id, dismiss_action, session, operator, dismiss_key)
        assert replayed_dismiss.version == dismissed_version
        assert count(session, AuditEvent) == audit_count
        with pytest.raises(DomainError, match="conflicts"):
            dismiss(
                dismissible.id,
                dismiss_action.model_copy(update={"reason": "different"}),
                session,
                operator,
                dismiss_key,
            )
        with pytest.raises(DomainError, match="conflicts"):
            dismiss(dismissible.id, dismiss_action, session, other_operator, dismiss_key)
        other_dismissible = create_opportunity(score.id, session, f"opportunity-{uuid4()}")
        with pytest.raises(DomainError, match="conflicts"):
            dismiss(
                other_dismissible.id,
                DismissAction(version=other_dismissible.version, reason="not selected"),
                session,
                operator,
                dismiss_key,
            )

        alert = session.scalar(
            select(OperationalAlert).where(OperationalAlert.entity_id == opportunity.id)
        )
        assert alert is not None
        acknowledge_key = f"acknowledge-{uuid4()}"
        acknowledge_action = VersionAction(version=alert.version)
        acknowledged = acknowledge_alert(
            alert.id, acknowledge_action, session, operator, acknowledge_key
        )
        acknowledged_version = acknowledged.version
        audit_count = count(session, AuditEvent)
        replayed_acknowledge = acknowledge_alert(
            alert.id, acknowledge_action, session, operator, acknowledge_key
        )
        assert replayed_acknowledge.version == acknowledged_version
        assert count(session, AuditEvent) == audit_count
        with pytest.raises(DomainError, match="conflicts"):
            acknowledge_alert(
                alert.id, acknowledge_action, session, other_operator, acknowledge_key
            )
        other_alert = session.scalar(
            select(OperationalAlert).where(OperationalAlert.entity_id == other_candidate.id)
        )
        assert other_alert is not None
        with pytest.raises(DomainError, match="conflicts"):
            acknowledge_alert(
                other_alert.id,
                VersionAction(version=other_alert.version),
                session,
                operator,
                acknowledge_key,
            )

        resolve_key = f"resolve-{uuid4()}"
        resolve_action = VersionAction(version=acknowledged.version)
        resolved = resolve_alert(alert.id, resolve_action, session, operator, resolve_key)
        resolved_version = resolved.version
        audit_count = count(session, AuditEvent)
        replayed_resolve = resolve_alert(alert.id, resolve_action, session, operator, resolve_key)
        assert replayed_resolve.version == resolved_version
        assert count(session, AuditEvent) == audit_count
        with pytest.raises(DomainError, match="conflicts"):
            resolve_alert(
                alert.id,
                VersionAction(version=resolve_action.version + 1),
                session,
                operator,
                resolve_key,
            )
        with pytest.raises(DomainError, match="conflicts"):
            resolve_alert(
                other_alert.id,
                VersionAction(version=other_alert.version),
                session,
                operator,
                resolve_key,
            )


def csv_upload(
    external_id: str,
    title: str = "Official product",
    collected_at: str | None = None,
) -> UploadFile:
    collected_at = collected_at or datetime.now(UTC).isoformat()
    payload = (
        "external_id,title,price,currency,available,collected_at\n"
        f"{external_id},{title},10.00,BRL,true,{collected_at}\n"
    ).encode()
    return UploadFile(
        BytesIO(payload),
        filename="official.csv",
        headers=Headers({"content-type": "text/csv"}),
    )


def test_manual_official_and_cancel_import_replays_are_context_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = create_operator()
    other_operator = create_operator()
    monkeypatch.setattr(process_import_task, "delay", lambda *args: None)
    with SessionFactory() as session:
        manual_body = ManualImportCreate(
            external_id=str(uuid4()),
            title="Manual import",
            price=Decimal("10.00"),
            currency="BRL",
            available=True,
            collected_at=datetime.now(UTC),
        )
        manual_key = f"manual-{uuid4()}"
        manual_batch = manual_import(manual_body, session, operator, manual_key)
        batch_count = count(session, ImportBatch)
        audit_count = count(session, AuditEvent)
        replayed_manual = manual_import(manual_body, session, operator, manual_key)
        assert replayed_manual.id == manual_batch.id
        assert count(session, ImportBatch) == batch_count
        assert count(session, AuditEvent) == audit_count
        with pytest.raises(DomainError, match="conflicts"):
            manual_import(
                manual_body.model_copy(update={"title": "Different"}),
                session,
                operator,
                manual_key,
            )
        with pytest.raises(DomainError, match="conflicts"):
            manual_import(manual_body, session, other_operator, manual_key)

        official_external_id = str(uuid4())
        official_collected_at = datetime.now(UTC).isoformat()
        official_key = f"official-{uuid4()}"
        official_batch = official_import(
            session,
            operator,
            official_key,
            csv_upload(official_external_id, collected_at=official_collected_at),
        )
        batch_count = count(session, ImportBatch)
        audit_count = count(session, AuditEvent)
        replayed_official = official_import(
            session,
            operator,
            official_key,
            csv_upload(official_external_id, collected_at=official_collected_at),
        )
        assert replayed_official.id == official_batch.id
        assert count(session, ImportBatch) == batch_count
        assert count(session, AuditEvent) == audit_count
        with pytest.raises(DomainError, match="conflicts"):
            official_import(
                session,
                operator,
                official_key,
                csv_upload(str(uuid4()), "Different official product"),
            )
        with pytest.raises(DomainError, match="conflicts"):
            official_import(
                session,
                other_operator,
                official_key,
                csv_upload(official_external_id, collected_at=official_collected_at),
            )

        cancel_key = f"cancel-{uuid4()}"
        cancel_action = VersionAction(version=official_batch.version)
        cancelled = cancel_import(official_batch.id, cancel_action, session, operator, cancel_key)
        cancelled_version = cancelled.version
        audit_count = count(session, AuditEvent)
        replayed_cancel = cancel_import(
            official_batch.id, cancel_action, session, operator, cancel_key
        )
        assert replayed_cancel.version == cancelled_version
        assert count(session, AuditEvent) == audit_count
        with pytest.raises(DomainError, match="conflicts"):
            cancel_import(
                official_batch.id,
                VersionAction(version=cancel_action.version + 1),
                session,
                operator,
                cancel_key,
            )
        with pytest.raises(DomainError, match="conflicts"):
            cancel_import(
                official_batch.id,
                cancel_action,
                session,
                other_operator,
                cancel_key,
            )
        other_batch = official_import(
            session, operator, f"official-{uuid4()}", csv_upload(str(uuid4()))
        )
        with pytest.raises(DomainError, match="conflicts"):
            cancel_import(
                other_batch.id,
                VersionAction(version=other_batch.version),
                session,
                operator,
                cancel_key,
            )
