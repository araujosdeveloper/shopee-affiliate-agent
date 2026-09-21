from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from shopee_affiliate_agent.db.session import SessionFactory
from shopee_affiliate_agent.main import app

pytestmark = pytest.mark.integration


def test_phase2_tables_exist() -> None:
    expected = {
        "import_batches",
        "import_rows",
        "product_assessments",
        "product_scores",
        "product_opportunities",
        "operational_alerts",
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
