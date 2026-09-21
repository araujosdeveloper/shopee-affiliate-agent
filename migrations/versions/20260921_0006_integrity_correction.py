"""Correct phase two integrity, idempotency, and durable import delivery."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from shopee_affiliate_agent.core.config import get_settings

revision: str = "20260921_0006"
down_revision: str | None = "20260921_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM("pending", "published", "completed", "failed", name="outbox_status").create(
        bind
    )
    op.create_table(
        "idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("operation", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operators.id", ondelete="RESTRICT"),
        ),
        sa.Column("payload_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_table(
        "import_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "import_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_batches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("task_name", sa.String(120), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "published",
                "completed",
                "failed",
                name="outbox_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("import_batch_id", "task_name"),
        sa.CheckConstraint("attempts >= 0", name="attempts_non_negative"),
    )
    bind.execute(
        text("""
    CREATE OR REPLACE FUNCTION validate_phase2_links() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE snapshot_product uuid; assessment_product uuid; assessment_snapshot uuid; score_product uuid; score_snapshot uuid;
    DECLARE snapshot_source product_source; DECLARE product_source_value product_source;
    DECLARE snapshot_available boolean; DECLARE snapshot_time timestamptz; DECLARE product_active boolean; DECLARE score_value numeric;
    BEGIN
      IF TG_TABLE_NAME = 'product_assessments' THEN
        SELECT product_id INTO snapshot_product FROM product_snapshots WHERE id=NEW.product_snapshot_id;
        IF snapshot_product IS DISTINCT FROM NEW.product_id THEN RAISE EXCEPTION 'assessment snapshot/product mismatch'; END IF;
      ELSIF TG_TABLE_NAME = 'product_scores' THEN
        SELECT product_id, product_snapshot_id INTO assessment_product, assessment_snapshot FROM product_assessments WHERE id=NEW.product_assessment_id;
        IF (assessment_product, assessment_snapshot) IS DISTINCT FROM (NEW.product_id, NEW.product_snapshot_id) THEN RAISE EXCEPTION 'score assessment/snapshot/product mismatch'; END IF;
      ELSIF TG_TABLE_NAME = 'product_opportunities' THEN
        SELECT product_id, product_snapshot_id, total_score INTO score_product, score_snapshot, score_value FROM product_scores WHERE id=NEW.product_score_id;
        SELECT product_id, source, available, collected_at INTO snapshot_product, snapshot_source, snapshot_available, snapshot_time FROM product_snapshots WHERE id=NEW.product_snapshot_id;
        SELECT source, is_active INTO product_source_value, product_active FROM products WHERE id=NEW.product_id;
        IF (score_product, score_snapshot) IS DISTINCT FROM (NEW.product_id, NEW.product_snapshot_id) THEN RAISE EXCEPTION 'opportunity score/snapshot/product mismatch'; END IF;
        IF snapshot_product IS DISTINCT FROM NEW.product_id THEN RAISE EXCEPTION 'opportunity snapshot/product mismatch'; END IF;
        IF snapshot_source IS DISTINCT FROM product_source_value THEN RAISE EXCEPTION 'snapshot provenance mismatch'; END IF;
        IF score_value < 70.00 OR NEW.score IS DISTINCT FROM score_value THEN RAISE EXCEPTION 'score below threshold or inconsistent'; END IF;
        IF TG_OP = 'INSERT' OR (OLD.status = 'candidate' AND NEW.status = 'shortlisted') THEN
          IF product_active IS DISTINCT FROM true THEN RAISE EXCEPTION 'active product is required'; END IF;
          IF snapshot_available IS DISTINCT FROM true THEN RAISE EXCEPTION 'available snapshot is required'; END IF;
          IF snapshot_time > now() THEN RAISE EXCEPTION 'future snapshot'; END IF;
          IF snapshot_time + interval '60 minutes' <= now() THEN RAISE EXCEPTION 'stale snapshot'; END IF;
        END IF;
        IF NEW.expires_at IS DISTINCT FROM snapshot_time + interval '60 minutes' THEN RAISE EXCEPTION 'expiry must match evidence validity'; END IF;
        IF TG_OP = 'UPDATE' AND OLD.status = 'candidate' AND NEW.status = 'expired' AND NEW.expires_at > now() THEN RAISE EXCEPTION 'opportunity is not expired'; END IF;
      END IF; RETURN NEW;
    END $$;
    """)
    )
    settings = get_settings()
    app_user = bind.dialect.identifier_preparer.quote(settings.POSTGRES_APP_USER)
    bind.execute(text(f"GRANT SELECT, INSERT ON idempotency_records TO {app_user}"))
    bind.execute(text(f"GRANT SELECT, INSERT, UPDATE ON import_outbox TO {app_user}"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text("""
    CREATE OR REPLACE FUNCTION validate_phase2_links() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE snapshot_product uuid; assessment_product uuid; assessment_snapshot uuid; score_product uuid; score_snapshot uuid;
    DECLARE snapshot_source product_source; DECLARE product_source_value product_source;
    DECLARE snapshot_available boolean; DECLARE snapshot_time timestamptz; DECLARE product_active boolean; DECLARE score_value numeric;
    BEGIN
      IF TG_TABLE_NAME = 'product_assessments' THEN SELECT product_id INTO snapshot_product FROM product_snapshots WHERE id=NEW.product_snapshot_id; IF snapshot_product IS DISTINCT FROM NEW.product_id THEN RAISE EXCEPTION 'assessment snapshot/product mismatch'; END IF;
      ELSIF TG_TABLE_NAME = 'product_scores' THEN SELECT product_id, product_snapshot_id INTO assessment_product, assessment_snapshot FROM product_assessments WHERE id=NEW.product_assessment_id; IF (assessment_product, assessment_snapshot) IS DISTINCT FROM (NEW.product_id, NEW.product_snapshot_id) THEN RAISE EXCEPTION 'score assessment/snapshot/product mismatch'; END IF;
      ELSIF TG_TABLE_NAME = 'product_opportunities' THEN SELECT product_id, product_snapshot_id, total_score INTO score_product, score_snapshot, score_value FROM product_scores WHERE id=NEW.product_score_id; SELECT product_id, source, available, collected_at INTO snapshot_product, snapshot_source, snapshot_available, snapshot_time FROM product_snapshots WHERE id=NEW.product_snapshot_id; SELECT source, is_active INTO product_source_value, product_active FROM products WHERE id=NEW.product_id; IF (score_product, score_snapshot) IS DISTINCT FROM (NEW.product_id, NEW.product_snapshot_id) THEN RAISE EXCEPTION 'opportunity score/snapshot/product mismatch'; END IF; IF snapshot_product IS DISTINCT FROM NEW.product_id THEN RAISE EXCEPTION 'opportunity snapshot/product mismatch'; END IF; IF product_active IS DISTINCT FROM true THEN RAISE EXCEPTION 'active product is required'; END IF; IF snapshot_available IS DISTINCT FROM true THEN RAISE EXCEPTION 'available snapshot is required'; END IF; IF snapshot_source IS DISTINCT FROM product_source_value THEN RAISE EXCEPTION 'snapshot provenance mismatch'; END IF; IF snapshot_time > now() THEN RAISE EXCEPTION 'future snapshot'; END IF; IF snapshot_time < now() - interval '60 minutes' THEN RAISE EXCEPTION 'stale snapshot'; END IF; IF score_value < 70.00 OR NEW.score IS DISTINCT FROM score_value THEN RAISE EXCEPTION 'score below threshold or inconsistent'; END IF;
      END IF; RETURN NEW; END $$;
    """)
    )
    op.drop_table("import_outbox")
    op.drop_table("idempotency_records")
    postgresql.ENUM(name="outbox_status").drop(bind)
