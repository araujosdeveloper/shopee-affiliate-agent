from dataclasses import fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopee_affiliate_agent.db.models import (
    AuditEvent,
    OperationalAlert,
    Product,
    ProductAssessment,
    ProductOpportunity,
    ProductScore,
    ProductSnapshot,
)
from shopee_affiliate_agent.domain.enums import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    OpportunityStatus,
)
from shopee_affiliate_agent.services.scoring import DeterministicScoringService, ScoreInputs

OPPORTUNITY_POLICY_VERSION = "commercial-opportunity-v1"
OPPORTUNITY_THRESHOLD = Decimal("70.00")
SNAPSHOT_MAX_AGE = timedelta(minutes=60)


class DomainError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def audit(
    session: Session,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    key: str,
    actor_id: UUID | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEvent(
            occurred_at=datetime.now(UTC),
            actor_id=actor_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            event_data=data or {},
            idempotency_key=key,
        )
    )


def calculate_score(session: Session, assessment: ProductAssessment, key: str) -> ProductScore:
    existing = session.scalar(select(ProductScore).where(ProductScore.idempotency_key == key))
    if existing:
        if existing.product_assessment_id != assessment.id:
            raise DomainError("idempotency_conflict", "key belongs to another assessment")
        return existing
    names = [field.name for field in fields(ScoreInputs)]
    inputs = ScoreInputs(**{name: getattr(assessment, name) for name in names})
    service = DeterministicScoringService()
    total = service.calculate(inputs)
    weights = {name: str(getattr(service.weights, name)) for name in names}
    components = {
        name: str(
            (getattr(inputs, name) * getattr(service.weights, name) / Decimal("100")).quantize(
                Decimal("0.01")
            )
        )
        for name in names
    }
    score = ProductScore(
        product_id=assessment.product_id,
        product_snapshot_id=assessment.product_snapshot_id,
        product_assessment_id=assessment.id,
        rule_version=assessment.rule_version,
        weights=weights,
        components=components,
        total_score=total,
        calculated_at=datetime.now(UTC),
        idempotency_key=key,
    )
    session.add(score)
    session.flush()
    audit(
        session,
        "score.calculated",
        "product_score",
        score.id,
        f"audit:{key}",
        data={"total_score": str(total), "rule_version": assessment.rule_version},
    )
    return score


def generate_opportunity(session: Session, score: ProductScore, key: str) -> ProductOpportunity:
    existing = session.scalar(
        select(ProductOpportunity).where(ProductOpportunity.idempotency_key == key)
    )
    if existing:
        if existing.product_score_id != score.id:
            raise DomainError("idempotency_conflict", "key belongs to another score")
        return existing
    product = session.get(Product, score.product_id)
    snapshot = session.get(ProductSnapshot, score.product_snapshot_id)
    now = datetime.now(UTC)
    if not product or not snapshot or snapshot.product_id != product.id:
        raise DomainError("product_snapshot_mismatch", "product and snapshot do not match")
    if not product.is_active:
        raise DomainError("invalid_state_transition", "product is inactive")
    if not snapshot.available:
        raise DomainError("invalid_state_transition", "product is unavailable")
    if snapshot.source != product.source:
        raise DomainError("unsupported_source", "snapshot provenance does not match product")
    if snapshot.collected_at > now:
        raise DomainError("future_snapshot", "snapshot is in the future")
    if snapshot.collected_at < now - SNAPSHOT_MAX_AGE:
        raise DomainError("stale_snapshot", "snapshot is stale")
    if score.total_score < OPPORTUNITY_THRESHOLD:
        raise DomainError("score_below_threshold", "score must be at least 70.00")
    opportunity = ProductOpportunity(
        product_id=product.id,
        product_snapshot_id=snapshot.id,
        product_score_id=score.id,
        status=OpportunityStatus.CANDIDATE,
        score=score.total_score,
        reason_codes=[OPPORTUNITY_POLICY_VERSION, "score_at_or_above_70"],
        generated_at=now,
        expires_at=now + SNAPSHOT_MAX_AGE,
        idempotency_key=key,
    )
    session.add(opportunity)
    session.flush()
    audit(
        session,
        "opportunity.generated",
        "product_opportunity",
        opportunity.id,
        f"audit:{key}",
        data={"policy": OPPORTUNITY_POLICY_VERSION},
    )
    alert = OperationalAlert(
        alert_type=AlertType.HIGH_SCORE_OPPORTUNITY,
        severity=AlertSeverity.INFO,
        entity_type="product_opportunity",
        entity_id=opportunity.id,
        message="High score opportunity requires human review",
        status=AlertStatus.OPEN,
        detected_at=now,
        idempotency_key=f"high-score:{opportunity.id}",
    )
    session.add(alert)
    session.flush()
    audit(session, "alert.opened", "operational_alert", alert.id, f"audit:alert:{alert.id}")
    return opportunity


def expire_opportunities(session: Session) -> int:
    now = datetime.now(UTC)
    items = session.scalars(
        select(ProductOpportunity).where(
            ProductOpportunity.status == OpportunityStatus.CANDIDATE,
            ProductOpportunity.expires_at <= now,
        )
    ).all()
    for item in items:
        item.status = OpportunityStatus.EXPIRED
        audit(
            session,
            "opportunity.expired",
            "product_opportunity",
            item.id,
            f"audit:expired:{item.id}",
        )
    stale_candidates = session.scalars(
        select(ProductOpportunity.product_snapshot_id)
        .join(ProductSnapshot, ProductSnapshot.id == ProductOpportunity.product_snapshot_id)
        .where(
            ProductOpportunity.status == OpportunityStatus.CANDIDATE,
            ProductSnapshot.collected_at < now - SNAPSHOT_MAX_AGE,
        )
        .distinct()
    ).all()
    for snapshot_id in stale_candidates:
        key = f"stale:{snapshot_id}"
        existing = session.scalar(
            select(OperationalAlert).where(OperationalAlert.idempotency_key == key)
        )
        if not existing:
            alert = OperationalAlert(
                alert_type=AlertType.STALE_SNAPSHOT,
                severity=AlertSeverity.WARNING,
                entity_type="product_snapshot",
                entity_id=snapshot_id,
                message="Snapshot related to an active opportunity became stale",
                status=AlertStatus.OPEN,
                detected_at=now,
                idempotency_key=key,
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
    active_snapshot_ids = set(stale_candidates)
    stale_alerts = session.scalars(
        select(OperationalAlert).where(
            OperationalAlert.alert_type == AlertType.STALE_SNAPSHOT,
            OperationalAlert.status != AlertStatus.RESOLVED,
        )
    ).all()
    for alert in stale_alerts:
        if alert.entity_id not in active_snapshot_ids:
            alert.status = AlertStatus.RESOLVED
            alert.acknowledged_at = alert.acknowledged_at or now
            alert.resolved_at = now
            audit(
                session,
                "alert.resolved",
                "operational_alert",
                alert.id,
                f"audit:resolved:{alert.id}",
            )
    return len(items)
