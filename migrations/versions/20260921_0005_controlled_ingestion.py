"""Add controlled ingestion and commercial intelligence domain."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from shopee_affiliate_agent.core.config import get_settings

revision: str = "20260921_0005"
down_revision: str | None = "20260920_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _enum(name: str, values: list[str]) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    enums = {
        "import_batch_status": [
            "received",
            "validating",
            "processing",
            "completed",
            "partially_completed",
            "failed",
            "cancelled",
        ],
        "import_row_status": ["pending", "accepted", "rejected", "duplicate"],
        "opportunity_status": ["candidate", "shortlisted", "dismissed", "expired"],
        "alert_type": [
            "stale_snapshot",
            "unavailable_product",
            "import_failed",
            "import_partially_completed",
            "high_score_opportunity",
            "invalid_source_data",
        ],
        "alert_severity": ["info", "warning", "critical"],
        "alert_status": ["open", "acknowledged", "resolved"],
    }
    for name, values in enums.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    common = [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]
    op.create_table(
        "import_batches",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source",
            _enum("product_source", ["manual", "official_import", "approved_api"]),
            nullable=False,
        ),
        sa.Column("filename", sa.String(255)),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column(
            "status", _enum("import_batch_status", enums["import_batch_status"]), nullable=False
        ),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "requested_by_id",
            _uuid(),
            sa.ForeignKey("operators.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        *common,
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "total_rows >= 0 AND accepted_rows >= 0 AND rejected_rows >= 0 AND duplicate_rows >= 0",
            name="non_negative_counts",
        ),
        sa.CheckConstraint(
            "status NOT IN ('completed','partially_completed','failed','cancelled') OR completed_at IS NOT NULL",
            name="terminal_completed_at",
        ),
        sa.CheckConstraint(
            "status NOT IN ('completed','partially_completed') OR total_rows = accepted_rows + rejected_rows + duplicate_rows",
            name="final_counts_match",
        ),
    )
    op.create_index("ix_import_batches_payload_sha256", "import_batches", ["payload_sha256"])
    op.create_table(
        "import_rows",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "import_batch_id",
            _uuid(),
            sa.ForeignKey("import_batches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(), nullable=False),
        sa.Column("normalized_data", postgresql.JSONB()),
        sa.Column("status", _enum("import_row_status", enums["import_row_status"]), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.String(500)),
        sa.Column("product_id", _uuid(), sa.ForeignKey("products.id", ondelete="RESTRICT")),
        sa.Column(
            "product_snapshot_id",
            _uuid(),
            sa.ForeignKey("product_snapshots.id", ondelete="RESTRICT"),
        ),
        sa.Column("row_sha256", sa.String(64), nullable=False),
        *[
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        ],
        sa.UniqueConstraint("import_batch_id", "row_number"),
        sa.CheckConstraint("row_number > 0", name="positive_row_number"),
    )
    op.create_index("ix_import_rows_hash", "import_rows", ["row_sha256"])
    dimensions = [
        "conversion_potential",
        "net_commission",
        "product_quality",
        "price_stock_stability",
        "niche_fit",
        "video_demonstration_potential",
        "cancellation_quality",
    ]
    op.create_table(
        "product_assessments",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "product_id", _uuid(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "product_snapshot_id",
            _uuid(),
            sa.ForeignKey("product_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *[sa.Column(name, sa.Numeric(5, 2), nullable=False) for name in dimensions],
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "assessed_by_id",
            _uuid(),
            sa.ForeignKey("operators.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("rule_version", sa.String(80), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *[
            sa.CheckConstraint(f"{name} BETWEEN 0 AND 100", name=f"{name}_range")
            for name in dimensions
        ],
    )
    op.create_table(
        "product_scores",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "product_id", _uuid(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "product_snapshot_id",
            _uuid(),
            sa.ForeignKey("product_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "product_assessment_id",
            _uuid(),
            sa.ForeignKey("product_assessments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("rule_version", sa.String(80), nullable=False),
        sa.Column("weights", postgresql.JSONB(), nullable=False),
        sa.Column("components", postgresql.JSONB(), nullable=False),
        sa.Column("total_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.CheckConstraint("total_score BETWEEN 0 AND 100", name="total_score_range"),
    )
    op.create_table(
        "product_opportunities",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "product_id", _uuid(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "product_snapshot_id",
            _uuid(),
            sa.ForeignKey("product_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "product_score_id",
            _uuid(),
            sa.ForeignKey("product_scores.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status", _enum("opportunity_status", enums["opportunity_status"]), nullable=False
        ),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shortlisted_at", sa.DateTime(timezone=True)),
        sa.Column("dismissed_at", sa.DateTime(timezone=True)),
        sa.Column("dismissed_reason", sa.Text()),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        *[
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        ],
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),
        sa.CheckConstraint("expires_at > generated_at", name="valid_expiry"),
        sa.CheckConstraint(
            "(status = 'shortlisted') = (shortlisted_at IS NOT NULL)", name="shortlist_timestamp"
        ),
        sa.CheckConstraint(
            "(status = 'dismissed') = (dismissed_at IS NOT NULL AND dismissed_reason IS NOT NULL)",
            name="dismissal_fields",
        ),
    )
    op.create_table(
        "operational_alerts",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("alert_type", _enum("alert_type", enums["alert_type"]), nullable=False),
        sa.Column("severity", _enum("alert_severity", enums["alert_severity"]), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", _uuid(), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("status", _enum("alert_status", enums["alert_status"]), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "acknowledged_by_id", _uuid(), sa.ForeignKey("operators.id", ondelete="RESTRICT")
        ),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        *[
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        ],
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status = 'open' OR acknowledged_at IS NOT NULL", name="acknowledged_timestamp"
        ),
        sa.CheckConstraint(
            "(status = 'resolved') = (resolved_at IS NOT NULL)", name="resolved_timestamp"
        ),
    )
    bind.execute(
        text("""
    CREATE FUNCTION validate_phase2_links() RETURNS trigger LANGUAGE plpgsql AS $$
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
        IF product_active IS DISTINCT FROM true THEN RAISE EXCEPTION 'active product is required'; END IF;
        IF snapshot_available IS DISTINCT FROM true THEN RAISE EXCEPTION 'available snapshot is required'; END IF;
        IF snapshot_source IS DISTINCT FROM product_source_value THEN RAISE EXCEPTION 'snapshot provenance mismatch'; END IF;
        IF snapshot_time > now() THEN RAISE EXCEPTION 'future snapshot'; END IF;
        IF snapshot_time < now() - interval '60 minutes' THEN RAISE EXCEPTION 'stale snapshot'; END IF;
        IF score_value < 70.00 OR NEW.score IS DISTINCT FROM score_value THEN RAISE EXCEPTION 'score below threshold or inconsistent'; END IF;
      END IF; RETURN NEW;
    END $$;
    CREATE TRIGGER validate_assessment_links BEFORE INSERT ON product_assessments FOR EACH ROW EXECUTE FUNCTION validate_phase2_links();
    CREATE TRIGGER validate_score_links BEFORE INSERT ON product_scores FOR EACH ROW EXECUTE FUNCTION validate_phase2_links();
    CREATE TRIGGER validate_opportunity_links BEFORE INSERT OR UPDATE ON product_opportunities FOR EACH ROW EXECUTE FUNCTION validate_phase2_links();
    CREATE FUNCTION prevent_immutable_phase2_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION '% records are immutable', TG_TABLE_NAME; END $$;
    CREATE TRIGGER immutable_product_snapshots BEFORE UPDATE OR DELETE ON product_snapshots FOR EACH ROW EXECUTE FUNCTION prevent_immutable_phase2_mutation();
    CREATE TRIGGER immutable_product_assessments BEFORE UPDATE OR DELETE ON product_assessments FOR EACH ROW EXECUTE FUNCTION prevent_immutable_phase2_mutation();
    CREATE TRIGGER immutable_product_scores BEFORE UPDATE OR DELETE ON product_scores FOR EACH ROW EXECUTE FUNCTION prevent_immutable_phase2_mutation();
    CREATE FUNCTION validate_opportunity_transition() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF NEW.status <> OLD.status AND NOT (OLD.status='candidate' AND NEW.status IN ('shortlisted','dismissed','expired')) THEN RAISE EXCEPTION 'invalid opportunity transition'; END IF; RETURN NEW; END $$;
    CREATE TRIGGER opportunity_transition BEFORE UPDATE ON product_opportunities FOR EACH ROW EXECUTE FUNCTION validate_opportunity_transition();
    CREATE FUNCTION validate_import_batch_transition() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF NEW.status <> OLD.status AND NOT (
        (OLD.status='received' AND NEW.status IN ('validating','processing','failed','cancelled')) OR
        (OLD.status='validating' AND NEW.status IN ('processing','failed','cancelled')) OR
        (OLD.status='processing' AND NEW.status IN ('completed','partially_completed','failed','cancelled'))
      ) THEN RAISE EXCEPTION 'invalid import batch transition'; END IF; RETURN NEW; END $$;
    CREATE TRIGGER import_batch_transition BEFORE UPDATE ON import_batches FOR EACH ROW EXECUTE FUNCTION validate_import_batch_transition();
    CREATE FUNCTION validate_alert_transition() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF NEW.status <> OLD.status AND NOT ((OLD.status='open' AND NEW.status IN ('acknowledged','resolved')) OR (OLD.status='acknowledged' AND NEW.status='resolved')) THEN RAISE EXCEPTION 'invalid alert transition'; END IF; RETURN NEW; END $$;
    CREATE TRIGGER alert_transition BEFORE UPDATE ON operational_alerts FOR EACH ROW EXECUTE FUNCTION validate_alert_transition();
    """)
    )
    settings = get_settings()
    preparer = bind.dialect.identifier_preparer
    app_user = preparer.quote(settings.POSTGRES_APP_USER)
    bind.execute(
        text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON import_batches, import_rows, product_opportunities, operational_alerts TO {app_user}"
        )
    )
    bind.execute(text(f"GRANT SELECT, INSERT ON product_assessments, product_scores TO {app_user}"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text(
            "DROP FUNCTION IF EXISTS validate_alert_transition() CASCADE; DROP FUNCTION IF EXISTS validate_import_batch_transition() CASCADE; DROP FUNCTION IF EXISTS validate_opportunity_transition() CASCADE; DROP FUNCTION IF EXISTS prevent_immutable_phase2_mutation() CASCADE; DROP FUNCTION IF EXISTS validate_phase2_links() CASCADE"
        )
    )
    for table in (
        "operational_alerts",
        "product_opportunities",
        "product_scores",
        "product_assessments",
        "import_rows",
        "import_batches",
    ):
        op.drop_table(table)
    for name in (
        "alert_status",
        "alert_severity",
        "alert_type",
        "opportunity_status",
        "import_row_status",
        "import_batch_status",
    ):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
