from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from shopee_affiliate_agent.core.config import get_settings
from shopee_affiliate_agent.db.session import SessionFactory
from shopee_affiliate_agent.domain.compliance import PRICE_VALIDATION_MAX_AGE
from shopee_affiliate_agent.main import app

pytestmark = pytest.mark.integration


def test_health_readiness_and_authentication() -> None:
    token = get_settings().INTERNAL_API_TOKEN.get_secret_value()
    with TestClient(app) as client:
        live = client.get("/health/live")
        assert live.status_code == 200
        assert live.json() == {"status": "ok"}
        assert live.headers["X-Request-ID"]

        ready = client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json()["dependencies"] == {"postgres": "ok", "redis": "ok"}

        assert client.get("/api/v1/system/status").status_code == 401
        authorized = client.get(
            "/api/v1/system/status", headers={"Authorization": f"Bearer {token}"}
        )
        assert authorized.status_code == 200
        assert authorized.json()["automatic_publication"] == "disabled"


def test_audit_events_are_append_only_for_application_user() -> None:
    event_id = uuid4()
    with SessionFactory() as session:
        session.execute(
            text(
                """INSERT INTO audit_events
                (id, occurred_at, event_type, entity_type, event_data, idempotency_key)
                VALUES (:id, :occurred_at, 'test.created', 'test', '{}', :key)"""
            ),
            {"id": event_id, "occurred_at": datetime.now(UTC), "key": f"test-{event_id}"},
        )
        session.commit()
        with pytest.raises(DBAPIError):
            session.execute(
                text("UPDATE audit_events SET event_type = 'tampered' WHERE id = :id"),
                {"id": event_id},
            )
            session.commit()
        session.rollback()
        with pytest.raises(DBAPIError):
            session.execute(text("DELETE FROM audit_events WHERE id = :id"), {"id": event_id})
            session.commit()
        session.rollback()
        session.execute(
            text(
                """INSERT INTO audit_events
                (id, occurred_at, event_type, entity_type, event_data, idempotency_key)
                VALUES (:id, :occurred_at, 'test.truncate', 'test', '{}', :key)"""
            ),
            {"id": uuid4(), "occurred_at": datetime.now(UTC), "key": f"truncate-{event_id}"},
        )
        session.commit()
        with pytest.raises(DBAPIError):
            session.execute(text("TRUNCATE audit_events"))
            session.commit()


def test_application_and_database_use_the_same_price_policy() -> None:
    assert PRICE_VALIDATION_MAX_AGE.total_seconds() == 60 * 60
    with SessionFactory() as session:
        definition = session.execute(
            text("SELECT pg_get_functiondef('validate_publication_compliance()'::regprocedure)")
        ).scalar_one()
    assert "interval '60 minutes'" in definition
    assert "publication snapshot does not belong to content product" in definition
    assert "product snapshot timestamp is in the future" in definition


def test_snapshot_provenance_and_approval_version_columns_exist() -> None:
    with SessionFactory() as session:
        columns = session.execute(
            text(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE (table_name, column_name) IN (
                    ('product_snapshots', 'source'),
                    ('approval_requests', 'content_version')
                )
                """
            )
        ).all()
    assert set(columns) == {
        ("product_snapshots", "source"),
        ("approval_requests", "content_version"),
    }


def test_database_blocks_publication_without_current_compliant_evidence() -> None:
    product_id = uuid4()
    snapshot_id = uuid4()
    other_product_id = uuid4()
    other_snapshot_id = uuid4()
    operator_id = uuid4()
    channel_id = uuid4()
    content_id = uuid4()
    approval_id = uuid4()

    with SessionFactory() as session:
        session.execute(
            text(
                """
                INSERT INTO operators
                    (id, email, display_name, role, is_active, version, created_at, updated_at)
                VALUES (:id, :email, 'Integration Operator', 'admin', true, 1, now(), now())
                """
            ),
            {"id": operator_id, "email": f"{operator_id}@example.test"},
        )
        session.execute(
            text(
                """
                INSERT INTO products
                    (id, source, external_id, title, is_active, version, created_at, updated_at)
                VALUES (:id, 'manual', :external_id, 'Integration Product', true, 1, now(), now())
                """
            ),
            {"id": product_id, "external_id": str(product_id)},
        )
        session.execute(
            text(
                """
                INSERT INTO product_snapshots
                    (id, product_id, source, price, available, collected_at, idempotency_key,
                     currency, created_at, updated_at)
                VALUES (:id, :product_id, 'manual', 10.00, true, :collected_at, :key,
                        'BRL', now(), now())
                """
            ),
            {
                "id": snapshot_id,
                "product_id": product_id,
                "collected_at": datetime.now(UTC),
                "key": f"snapshot-{snapshot_id}",
            },
        )
        session.execute(
            text(
                """
                INSERT INTO products
                    (id, source, external_id, title, is_active, version, created_at, updated_at)
                VALUES (:id, 'manual', :external_id, 'Other Integration Product', true, 1,
                        now(), now())
                """
            ),
            {"id": other_product_id, "external_id": str(other_product_id)},
        )
        session.execute(
            text(
                """
                INSERT INTO product_snapshots
                    (id, product_id, source, price, currency, available, collected_at,
                     idempotency_key, created_at, updated_at)
                VALUES (:id, :product_id, 'manual', 20.00, 'BRL', true, now(), :key,
                        now(), now())
                """
            ),
            {
                "id": other_snapshot_id,
                "product_id": other_product_id,
                "key": f"snapshot-{other_snapshot_id}",
            },
        )
        session.execute(
            text(
                """
                INSERT INTO media_channels
                    (id, channel_type, external_reference, display_name, is_active,
                     version, created_at, updated_at)
                VALUES (:id, 'social', :external_reference, 'Integration Channel', true,
                        1, now(), now())
                """
            ),
            {"id": channel_id, "external_reference": str(channel_id)},
        )
        session.execute(
            text(
                """
                INSERT INTO content_items
                    (id, product_id, title, body, status, claim_types, idempotency_key,
                     version, created_at, updated_at)
                VALUES (:id, :product_id, 'Title', 'Body', 'approved', '[]', :key, 1, now(), now())
                """
            ),
            {"id": content_id, "product_id": product_id, "key": f"content-{content_id}"},
        )
        session.execute(
            text(
                """
                INSERT INTO approval_requests
                    (id, content_item_id, content_version, requested_by_id, reviewer_id, status,
                     reviewed_at, idempotency_key, version, created_at, updated_at)
                VALUES (:id, :content_id, 1, :operator_id, :operator_id, 'pending', now(), :key,
                        1, now(), now())
                """
            ),
            {
                "id": approval_id,
                "content_id": content_id,
                "operator_id": operator_id,
                "key": f"approval-{approval_id}",
            },
        )
        session.commit()

        def insert_publication(
            *, is_automatic: bool, key: str, publication_snapshot_id: object = snapshot_id
        ) -> None:
            session.execute(
                text(
                    """
                    INSERT INTO publications
                        (id, content_item_id, media_channel_id, approval_request_id,
                         product_snapshot_id, status, is_automatic, idempotency_key,
                         version, created_at, updated_at)
                    VALUES (:id, :content_id, :channel_id, :approval_id, :snapshot_id,
                            'pending', :is_automatic, :key, 1, now(), now())
                    """
                ),
                {
                    "id": uuid4(),
                    "content_id": content_id,
                    "channel_id": channel_id,
                    "approval_id": approval_id,
                    "snapshot_id": publication_snapshot_id,
                    "is_automatic": is_automatic,
                    "key": key,
                },
            )
            session.commit()

        def insert_snapshot(collected_at: datetime) -> object:
            new_snapshot_id = uuid4()
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
                    "id": new_snapshot_id,
                    "product_id": product_id,
                    "collected_at": collected_at,
                    "key": f"snapshot-{new_snapshot_id}",
                },
            )
            session.commit()
            return new_snapshot_id

        with pytest.raises(DBAPIError):
            insert_publication(is_automatic=False, key=f"pending-{uuid4()}")
        session.rollback()
        session.execute(
            text("UPDATE approval_requests SET status = 'approved' WHERE id = :id"),
            {"id": approval_id},
        )
        session.commit()
        with pytest.raises(DBAPIError):
            insert_publication(is_automatic=True, key=f"automatic-{uuid4()}")
        session.rollback()
        with pytest.raises(
            DBAPIError, match="publication snapshot does not belong to content product"
        ):
            insert_publication(
                is_automatic=False,
                key=f"wrong-product-{uuid4()}",
                publication_snapshot_id=other_snapshot_id,
            )
        session.rollback()
        future_snapshot_id = insert_snapshot(datetime.now(UTC) + timedelta(seconds=30))
        with pytest.raises(DBAPIError, match="product snapshot timestamp is in the future"):
            insert_publication(
                is_automatic=False,
                key=f"future-{uuid4()}",
                publication_snapshot_id=future_snapshot_id,
            )
        session.rollback()
        stale_snapshot_id = insert_snapshot(datetime.now(UTC) - PRICE_VALIDATION_MAX_AGE)
        with pytest.raises(DBAPIError):
            insert_publication(
                is_automatic=False,
                key=f"expired-{uuid4()}",
                publication_snapshot_id=stale_snapshot_id,
            )
        session.rollback()
        session.execute(
            text("UPDATE content_items SET version = 2 WHERE id = :id"), {"id": content_id}
        )
        session.commit()
        with pytest.raises(DBAPIError):
            insert_publication(is_automatic=False, key=f"version-{uuid4()}")
        session.rollback()
        session.execute(
            text("UPDATE approval_requests SET content_version = 2 WHERE id = :id"),
            {"id": approval_id},
        )
        session.commit()
        insert_publication(is_automatic=False, key=f"valid-{uuid4()}")
