import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from shopee_affiliate_agent.db.models import (
    AuditEvent,
    ImportBatch,
    ImportRow,
    OperationalAlert,
    Product,
    ProductAssessment,
    ProductOpportunity,
    ProductScore,
    ProductSnapshot,
)
from shopee_affiliate_agent.db.session import SessionFactory
from shopee_affiliate_agent.domain.enums import OpportunityStatus, ProductSource
from shopee_affiliate_agent.services.commerce import (
    audit,
    calculate_score,
    expire_opportunities,
    generate_opportunity,
)
from shopee_affiliate_agent.services.imports import ParsedRow
from shopee_affiliate_agent.services.ingestion import add_rows, create_batch, process_batch

pytestmark = pytest.mark.integration


def test_phase2_end_to_end_persists_and_constrains_the_complete_flow() -> None:
    operator_id = uuid4()
    suffix = str(uuid4())
    collected_at = datetime.now(UTC) - timedelta(minutes=59, seconds=57)
    row_data = {
        "external_id": f"e2e-{suffix}",
        "title": "Phase two E2E product",
        "price": "100.00",
        "currency": "BRL",
        "available": "true",
        "collected_at": collected_at.isoformat(),
    }
    with SessionFactory.begin() as session:
        session.execute(
            text("""
                INSERT INTO operators
                    (id,email,display_name,role,is_active,version,created_at,updated_at)
                VALUES (:id,:email,'E2E operator','admin',true,1,now(),now())
            """),
            {"id": operator_id, "email": f"e2e-{suffix}@example.test"},
        )
        batch = create_batch(
            session,
            source=ProductSource.MANUAL,
            filename=None,
            content_type="application/json",
            payload_hash="c" * 64,
            operator_id=operator_id,
            key=f"e2e-batch-{suffix}",
        )
        add_rows(session, batch, [ParsedRow(1, row_data, row_data)])
        process_batch(session, batch.id)
        row = session.scalar(select(ImportRow).where(ImportRow.import_batch_id == batch.id))
        assert row is not None and row.product_id and row.product_snapshot_id
        assessment = ProductAssessment(
            product_id=row.product_id,
            product_snapshot_id=row.product_snapshot_id,
            conversion_potential=Decimal("100"),
            net_commission=Decimal("100"),
            product_quality=Decimal("100"),
            price_stock_stability=Decimal("100"),
            niche_fit=Decimal("100"),
            video_demonstration_potential=Decimal("100"),
            cancellation_quality=Decimal("100"),
            evidence={"operator_provided": True},
            assessed_by_id=operator_id,
            rule_version="e2e-v1",
            idempotency_key=f"e2e-assessment-{suffix}",
        )
        session.add(assessment)
        session.flush()
        audit(
            session,
            "assessment.created",
            "product_assessment",
            assessment.id,
            f"audit:e2e-assessment-{suffix}",
            operator_id,
        )
        score = calculate_score(session, assessment, f"e2e-score-{suffix}")
        opportunities = [
            generate_opportunity(session, score, f"e2e-opportunity-{index}-{suffix}")
            for index in range(3)
        ]
        now = datetime.now(UTC)
        opportunities[0].status = OpportunityStatus.SHORTLISTED
        opportunities[0].shortlisted_at = now
        audit(
            session,
            "opportunity.shortlisted",
            "product_opportunity",
            opportunities[0].id,
            f"audit:e2e-shortlist-{suffix}",
            operator_id,
        )
        opportunities[1].status = OpportunityStatus.DISMISSED
        opportunities[1].dismissed_at = now
        opportunities[1].dismissed_reason = "not selected"
        audit(
            session,
            "opportunity.dismissed",
            "product_opportunity",
            opportunities[1].id,
            f"audit:e2e-dismiss-{suffix}",
            operator_id,
        )
        batch_id = batch.id
        expiring_id = opportunities[2].id
        product_id = row.product_id
        snapshot_id = row.product_snapshot_id
        assessment_id = assessment.id
        score_id = score.id

    time.sleep(3.2)
    with SessionFactory.begin() as session:
        assert expire_opportunities(session) == 1

    with SessionFactory() as session:
        assert session.get(ImportBatch, batch_id) is not None
        assert session.get(Product, product_id) is not None
        assert session.get(ProductSnapshot, snapshot_id) is not None
        assert session.get(ProductAssessment, assessment_id) is not None
        assert session.get(ProductScore, score_id) is not None
        assert session.get(ProductOpportunity, expiring_id).status == OpportunityStatus.EXPIRED
        assert session.scalar(select(func.count()).select_from(OperationalAlert)) >= 3
        assert session.scalar(select(func.count()).select_from(AuditEvent)) >= 1
