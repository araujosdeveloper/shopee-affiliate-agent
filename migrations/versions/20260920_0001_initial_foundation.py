"""Initial deterministic foundation schema."""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

from shopee_affiliate_agent.core.config import get_settings
from shopee_affiliate_agent.db import models  # noqa: F401
from shopee_affiliate_agent.db.base import Base

revision: str = "20260920_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    bind.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION prevent_audit_event_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'audit_events are append-only';
            END;
            $$;
            CREATE TRIGGER audit_events_append_only
            BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation();

            CREATE OR REPLACE FUNCTION validate_content_status_transition()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.status = OLD.status THEN RETURN NEW; END IF;
                IF NOT (
                    (OLD.status = 'draft' AND NEW.status IN ('pending_review', 'retired')) OR
                    (OLD.status = 'pending_review' AND NEW.status IN ('approved', 'rejected')) OR
                    (OLD.status = 'rejected' AND NEW.status IN ('draft', 'retired')) OR
                    (OLD.status = 'approved' AND NEW.status IN ('scheduled', 'retired')) OR
                    (OLD.status = 'scheduled' AND NEW.status IN ('published', 'retired')) OR
                    (OLD.status = 'published' AND NEW.status = 'retired')
                ) THEN
                    RAISE EXCEPTION 'invalid content status transition';
                END IF;
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER content_status_transition
            BEFORE UPDATE OF status ON content_items
            FOR EACH ROW EXECUTE FUNCTION validate_content_status_transition();

            CREATE OR REPLACE FUNCTION validate_publication_compliance()
            RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE approval_state approval_status;
            DECLARE snapshot_available boolean;
            DECLARE snapshot_time timestamptz;
            BEGIN
                SELECT status INTO approval_state FROM approval_requests
                WHERE id = NEW.approval_request_id AND content_item_id = NEW.content_item_id;
                SELECT available, collected_at INTO snapshot_available, snapshot_time
                FROM product_snapshots WHERE id = NEW.product_snapshot_id;
                IF approval_state IS DISTINCT FROM 'approved' THEN
                    RAISE EXCEPTION 'approved human review is required';
                END IF;
                IF snapshot_available IS DISTINCT FROM true THEN
                    RAISE EXCEPTION 'available product snapshot is required';
                END IF;
                IF snapshot_time < now() - interval '60 minutes' THEN
                    RAISE EXCEPTION 'product snapshot is stale';
                END IF;
                IF NEW.is_automatic THEN
                    RAISE EXCEPTION 'automatic publication is disabled';
                END IF;
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER publication_compliance
            BEFORE INSERT OR UPDATE ON publications
            FOR EACH ROW EXECUTE FUNCTION validate_publication_compliance();
            """
        )
    )

    settings = get_settings()
    app_user = bind.dialect.identifier_preparer.quote(settings.POSTGRES_APP_USER)
    bind.execute(text(f"GRANT USAGE ON SCHEMA public TO {app_user}"))
    bind.execute(
        text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {app_user}")
    )
    bind.execute(text(f"REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM {app_user}"))


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
    bind.execute(text("DROP FUNCTION IF EXISTS prevent_audit_event_mutation() CASCADE"))
    bind.execute(text("DROP FUNCTION IF EXISTS validate_content_status_transition() CASCADE"))
    bind.execute(text("DROP FUNCTION IF EXISTS validate_publication_compliance() CASCADE"))
