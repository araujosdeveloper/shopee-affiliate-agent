from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from shopee_affiliate_agent.db.models import ImportRow
from shopee_affiliate_agent.db.session import SessionFactory
from shopee_affiliate_agent.domain.enums import ImportBatchStatus, ImportRowStatus, ProductSource
from shopee_affiliate_agent.main import app
from shopee_affiliate_agent.services.imports import ParsedRow
from shopee_affiliate_agent.services.ingestion import add_rows, create_batch, process_batch

pytestmark = pytest.mark.integration


def test_phase2_tables_exist() -> None:
    expected = {
        "import_batches",
        "import_rows",
        "product_assessments",
        "product_scores",
        "product_opportunities",
        "operational_alerts",
        "idempotency_records",
        "import_outbox",
    }
    with SessionFactory() as session:
        actual = set(
            session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name = ANY(:names)"
                ),
                {"names": list(expected)},
            ).scalars()
        )
    assert actual == expected


def test_phase2_api_routes_require_authentication() -> None:
    routes = ["/api/v1/products", "/api/v1/imports", "/api/v1/opportunities", "/api/v1/alerts"]
    with TestClient(app) as client:
        for route in routes:
            assert client.get(route).status_code == 401


def test_product_snapshots_are_immutable() -> None:
    product_id, snapshot_id = uuid4(), uuid4()
    with SessionFactory() as session:
        session.execute(
            text(
                """
                INSERT INTO products
                    (id, source, external_id, title, is_active, version, created_at, updated_at)
                VALUES (:id, 'manual', :external_id, 'Immutable', true, 1, now(), now())
                """
            ),
            {"id": product_id, "external_id": str(product_id)},
        )
        session.execute(
            text(
                """
                INSERT INTO product_snapshots
                    (id, product_id, source, price, currency, available, collected_at,
                     idempotency_key, created_at, updated_at)
                VALUES (:id, :product_id, 'manual', 10.00, 'BRL', true, :collected_at,
                        :key, now(), now())
                """
            ),
            {
                "id": snapshot_id,
                "product_id": product_id,
                "collected_at": datetime.now(UTC),
                "key": f"immutable-{snapshot_id}",
            },
        )
        session.commit()
        with pytest.raises(DBAPIError, match="immutable"):
            session.execute(
                text("UPDATE product_snapshots SET price=11.00 WHERE id=:id"), {"id": snapshot_id}
            )
            session.commit()


def test_opportunity_expiry_is_bound_to_snapshot_evidence() -> None:
    operator_id = uuid4()
    product_id = uuid4()
    snapshot_id = uuid4()
    assessment_id = uuid4()
    score_id = uuid4()
    opportunity_id = uuid4()
    collected_at = datetime.now(UTC)
    with SessionFactory.begin() as session:
        statements = """
                INSERT INTO operators
                    (id,email,display_name,role,is_active,version,created_at,updated_at)
                VALUES (:operator_id,:email,'Integrity','admin',true,1,now(),now());
                INSERT INTO products
                    (id,source,external_id,title,is_active,version,created_at,updated_at)
                VALUES (:product_id,'manual',:external_id,'Evidence',true,1,now(),now());
                INSERT INTO product_snapshots
                    (id,product_id,source,price,currency,available,collected_at,
                     idempotency_key,created_at,updated_at)
                VALUES (:snapshot_id,:product_id,'manual',10,'BRL',true,:collected_at,
                        :snapshot_key,now(),now());
                INSERT INTO product_assessments
                    (id,product_id,product_snapshot_id,conversion_potential,net_commission,
                     product_quality,price_stock_stability,niche_fit,
                     video_demonstration_potential,cancellation_quality,evidence,
                     assessed_by_id,rule_version,idempotency_key,created_at)
                VALUES (:assessment_id,:product_id,:snapshot_id,80,80,80,80,80,80,80,'{}',
                        :operator_id,'v1',:assessment_key,now());
                INSERT INTO product_scores
                    (id,product_id,product_snapshot_id,product_assessment_id,rule_version,
                     weights,components,total_score,calculated_at,idempotency_key)
                VALUES (:score_id,:product_id,:snapshot_id,:assessment_id,'v1','{}','{}',
                        80,now(),:score_key);
                INSERT INTO product_opportunities
                    (id,product_id,product_snapshot_id,product_score_id,status,score,
                     reason_codes,generated_at,expires_at,idempotency_key,version,
                     created_at,updated_at)
                VALUES (:opportunity_id,:product_id,:snapshot_id,:score_id,'candidate',80,'[]',
                        now(),:expires_at,:opportunity_key,1,now(),now());
            """
        parameters = {
            "operator_id": operator_id,
            "email": f"{operator_id}@example.test",
            "product_id": product_id,
            "external_id": str(product_id),
            "snapshot_id": snapshot_id,
            "collected_at": collected_at,
            "snapshot_key": f"snapshot-{snapshot_id}",
            "assessment_id": assessment_id,
            "assessment_key": f"assessment-{assessment_id}",
            "score_id": score_id,
            "score_key": f"score-{score_id}",
            "opportunity_id": opportunity_id,
            "opportunity_key": f"opportunity-{opportunity_id}",
            "expires_at": collected_at + timedelta(minutes=60),
        }
        for statement in statements.split(";"):
            if statement.strip():
                session.execute(text(statement), parameters)
        expires_at = session.scalar(
            text("SELECT expires_at FROM product_opportunities WHERE id=:id"),
            {"id": opportunity_id},
        )
        assert expires_at == collected_at + timedelta(minutes=60)
        with pytest.raises(DBAPIError, match="expiry must match evidence validity"):
            with session.begin_nested():
                session.execute(
                    text(
                        "UPDATE product_opportunities "
                        "SET expires_at=expires_at + interval '1 minute' WHERE id=:id"
                    ),
                    {"id": opportunity_id},
                )


def test_database_error_is_isolated_to_one_import_row() -> None:
    operator_id = uuid4()
    now = datetime.now(UTC).isoformat()
    with SessionFactory.begin() as session:
        session.execute(
            text("""
                INSERT INTO operators
                    (id,email,display_name,role,is_active,version,created_at,updated_at)
                VALUES (:id,:email,'Row isolation','admin',true,1,now(),now())
            """),
            {"id": operator_id, "email": f"{operator_id}@example.test"},
        )
        batch = create_batch(
            session,
            source=ProductSource.MANUAL,
            filename=None,
            content_type="application/json",
            payload_hash="b" * 64,
            operator_id=operator_id,
            key=f"batch-{operator_id}",
        )
        bad = {
            "external_id": "bad",
            "title": "x" * 501,
            "price": "10.00",
            "currency": "BRL",
            "available": "true",
            "collected_at": now,
        }
        good = {**bad, "external_id": "good", "title": "Valid product"}
        add_rows(
            session,
            batch,
            [ParsedRow(1, bad, bad), ParsedRow(2, good, good)],
        )
        process_batch(session, batch.id)
        rows = (
            session.query(ImportRow)
            .filter_by(import_batch_id=batch.id)
            .order_by(ImportRow.row_number)
            .all()
        )
        assert [row.status for row in rows] == [ImportRowStatus.REJECTED, ImportRowStatus.ACCEPTED]
        assert rows[0].error_code == "row_processing_error"
        assert rows[0].error_message == "Row could not be processed"
        assert batch.status == ImportBatchStatus.PARTIALLY_COMPLETED
