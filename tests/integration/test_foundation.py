from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from shopee_affiliate_agent.core.config import get_settings
from shopee_affiliate_agent.db.session import SessionFactory
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
