"""Record snapshot provenance and bind approvals to content versions."""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "20260920_0003"
down_revision: str | None = "20260920_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text(
            """
            ALTER TABLE product_snapshots
                ADD COLUMN IF NOT EXISTS source product_source;
            UPDATE product_snapshots AS snapshot
            SET source = product.source
            FROM products AS product
            WHERE snapshot.product_id = product.id
              AND snapshot.source IS NULL;
            ALTER TABLE product_snapshots
                ALTER COLUMN source SET DEFAULT 'manual',
                ALTER COLUMN source SET NOT NULL;

            ALTER TABLE approval_requests
                ADD COLUMN IF NOT EXISTS content_version integer;
            UPDATE approval_requests AS approval
            SET content_version = content.version
            FROM content_items AS content
            WHERE approval.content_item_id = content.id
              AND approval.content_version IS NULL;
            ALTER TABLE approval_requests
                ALTER COLUMN content_version SET DEFAULT 1,
                ALTER COLUMN content_version SET NOT NULL;
            """
        )
    )
    bind.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION validate_publication_compliance()
            RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE approval_state approval_status;
            DECLARE approval_version integer;
            DECLARE content_version integer;
            DECLARE snapshot_available boolean;
            DECLARE snapshot_time timestamptz;
            DECLARE snapshot_source product_source;
            DECLARE product_source_value product_source;
            BEGIN
                SELECT ar.status, ar.content_version INTO approval_state, approval_version
                FROM approval_requests AS ar
                WHERE ar.id = NEW.approval_request_id AND ar.content_item_id = NEW.content_item_id;
                SELECT ci.version INTO content_version
                FROM content_items AS ci WHERE ci.id = NEW.content_item_id;
                SELECT ps.available, ps.collected_at, ps.source
                INTO snapshot_available, snapshot_time, snapshot_source
                FROM product_snapshots AS ps WHERE ps.id = NEW.product_snapshot_id;
                SELECT p.source INTO product_source_value
                FROM products AS p
                WHERE p.id = (SELECT ps2.product_id FROM product_snapshots AS ps2
                              WHERE ps2.id = NEW.product_snapshot_id);
                IF approval_state IS DISTINCT FROM 'approved' THEN
                    RAISE EXCEPTION 'approved human review is required';
                END IF;
                IF approval_version IS DISTINCT FROM content_version THEN
                    RAISE EXCEPTION 'approval does not match current content version';
                END IF;
                IF snapshot_available IS DISTINCT FROM true THEN
                    RAISE EXCEPTION 'available product snapshot is required';
                END IF;
                IF snapshot_source IS DISTINCT FROM product_source_value THEN
                    RAISE EXCEPTION 'snapshot provenance does not match product source';
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
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION validate_publication_compliance()
            RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE approval_state approval_status;
            DECLARE snapshot_available boolean;
            DECLARE snapshot_time timestamptz;
            BEGIN
                SELECT status INTO approval_state
                FROM approval_requests
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
            ALTER TABLE approval_requests DROP COLUMN IF EXISTS content_version;
            ALTER TABLE product_snapshots DROP COLUMN IF EXISTS source;
            """
        )
    )
