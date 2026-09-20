"""Create the complete deterministic foundation schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from shopee_affiliate_agent.core.config import get_settings

revision: str = "20260920_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _enum(name: str, values: list[str]) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in (
        ("operator_role", ["admin", "reviewer", "editor"]),
        ("channel_type", ["social", "messaging", "video", "other"]),
        ("product_source", ["manual", "official_import", "approved_api"]),
        ("campaign_status", ["draft", "active", "paused", "ended"]),
        (
            "content_status",
            [
                "draft",
                "pending_review",
                "approved",
                "scheduled",
                "published",
                "retired",
                "rejected",
            ],
        ),
        ("approval_status", ["pending", "approved", "rejected"]),
        ("publication_status", ["pending", "scheduled", "published", "failed", "cancelled"]),
    ):
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "operators",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("role", _enum("operator_role", ["admin", "reviewer", "editor"]), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "affiliate_accounts",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("external_reference", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "media_channels",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column(
            "channel_type",
            _enum("channel_type", ["social", "messaging", "video", "other"]),
            nullable=False,
        ),
        sa.Column("external_reference", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "products",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column(
            "source",
            _enum("product_source", ["manual", "official_import", "approved_api"]),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "product_snapshots",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column(
            "product_id", _uuid(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "source",
            _enum("product_source", ["manual", "official_import", "approved_api"]),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="BRL"),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_payload_hash", sa.String(64), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("price >= 0", name="price_non_negative"),
    )
    op.create_table(
        "campaigns",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "status",
            _enum("campaign_status", ["draft", "active", "paused", "ended"]),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="valid_period"),
    )
    op.create_table(
        "affiliate_links",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column(
            "affiliate_account_id",
            _uuid(),
            sa.ForeignKey("affiliate_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "product_id", _uuid(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "campaign_id",
            _uuid(),
            sa.ForeignKey("campaigns.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "content_items",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column(
            "product_id", _uuid(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "campaign_id",
            _uuid(),
            sa.ForeignKey("campaigns.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "status",
            _enum(
                "content_status",
                [
                    "draft",
                    "pending_review",
                    "approved",
                    "scheduled",
                    "published",
                    "retired",
                    "rejected",
                ],
            ),
            nullable=False,
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("claim_types", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status <> 'rejected' OR rejection_reason IS NOT NULL", name="rejection_requires_reason"
        ),
        sa.CheckConstraint(
            "status = 'rejected' OR rejection_reason IS NULL", name="reason_only_for_rejection"
        ),
    )
    op.create_table(
        "approval_requests",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column(
            "content_item_id",
            _uuid(),
            sa.ForeignKey("content_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("content_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "requested_by_id",
            _uuid(),
            sa.ForeignKey("operators.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "reviewer_id",
            _uuid(),
            sa.ForeignKey("operators.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "status", _enum("approval_status", ["pending", "approved", "rejected"]), nullable=False
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status <> 'rejected' OR rejection_reason IS NOT NULL", name="rejection_requires_reason"
        ),
        sa.CheckConstraint(
            "status = 'pending' OR reviewed_at IS NOT NULL", name="decision_requires_review_time"
        ),
    )
    op.create_table(
        "publications",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column(
            "content_item_id",
            _uuid(),
            sa.ForeignKey("content_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "media_channel_id",
            _uuid(),
            sa.ForeignKey("media_channels.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "approval_request_id",
            _uuid(),
            sa.ForeignKey("approval_requests.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "product_snapshot_id",
            _uuid(),
            sa.ForeignKey("product_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum(
                "publication_status", ["pending", "scheduled", "published", "failed", "cancelled"]
            ),
            nullable=False,
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_automatic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL", name="published_requires_time"
        ),
        sa.CheckConstraint("is_automatic = false", name="automatic_forbidden"),
    )
    op.create_table(
        "performance_daily",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column(
            "affiliate_link_id",
            _uuid(),
            sa.ForeignKey("affiliate_links.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "media_channel_id",
            _uuid(),
            sa.ForeignKey("media_channels.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("commission_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="BRL"),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("clicks >= 0", name="clicks_non_negative"),
        sa.CheckConstraint("orders >= 0", name="orders_non_negative"),
        sa.CheckConstraint("commission_amount >= 0", name="commission_non_negative"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "actor_id", _uuid(), sa.ForeignKey("operators.id", ondelete="RESTRICT"), nullable=True
        ),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(120), nullable=False),
        sa.Column("entity_id", _uuid(), nullable=True),
        sa.Column("decision", sa.String(120), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("event_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
    )

    for table, name, columns in (
        ("operators", "uq_operators_email", ["email"]),
        (
            "affiliate_accounts",
            "uq_affiliate_accounts_platform",
            ["platform", "external_reference"],
        ),
        (
            "media_channels",
            "uq_media_channels_channel_type",
            ["channel_type", "external_reference"],
        ),
        ("products", "uq_products_source", ["source", "external_id"]),
        ("product_snapshots", "uq_product_snapshots_idempotency_key", ["idempotency_key"]),
        ("campaigns", "uq_campaigns_name", ["name"]),
        (
            "affiliate_links",
            "uq_affiliate_links_account_product_campaign",
            ["affiliate_account_id", "product_id", "campaign_id"],
        ),
        ("content_items", "uq_content_items_idempotency_key", ["idempotency_key"]),
        ("approval_requests", "uq_approval_requests_idempotency_key", ["idempotency_key"]),
        ("publications", "uq_publications_idempotency_key", ["idempotency_key"]),
        (
            "performance_daily",
            "uq_performance_daily_link_channel_date",
            ["affiliate_link_id", "media_channel_id", "metric_date"],
        ),
        ("performance_daily", "uq_performance_daily_idempotency_key", ["idempotency_key"]),
        ("audit_events", "uq_audit_events_idempotency_key", ["idempotency_key"]),
    ):
        op.create_unique_constraint(name, table, columns)

    op.create_index("ix_operators_email", "operators", ["email"])
    op.create_index(
        "ix_product_snapshots_product_collected",
        "product_snapshots",
        ["product_id", "collected_at"],
    )
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index(
        "ix_audit_events_entity", "audit_events", ["entity_type", "entity_id", "occurred_at"]
    )

    bind = op.get_bind()
    bind.execute(
        text("""
        CREATE OR REPLACE FUNCTION prevent_audit_event_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'audit_events are append-only'; END;
        $$;
        CREATE OR REPLACE FUNCTION validate_content_status_transition()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.status = OLD.status THEN RETURN NEW; END IF;
            IF NOT ((OLD.status = 'draft' AND NEW.status IN ('pending_review', 'retired')) OR
                    (OLD.status = 'pending_review' AND NEW.status IN ('approved', 'rejected')) OR
                    (OLD.status = 'rejected' AND NEW.status IN ('draft', 'retired')) OR
                    (OLD.status = 'approved' AND NEW.status IN ('scheduled', 'retired')) OR
                    (OLD.status = 'scheduled' AND NEW.status IN ('published', 'retired')) OR
                    (OLD.status = 'published' AND NEW.status = 'retired')) THEN
                RAISE EXCEPTION 'invalid content status transition';
            END IF;
            RETURN NEW;
        END;
        $$;
        CREATE OR REPLACE FUNCTION validate_publication_compliance()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE approval_state approval_status;
        DECLARE approval_version integer;
        DECLARE content_version integer;
        DECLARE snapshot_available boolean;
        DECLARE snapshot_time timestamptz;
        DECLARE snapshot_source product_source;
        DECLARE product_source_value product_source;
        DECLARE content_product_id uuid;
        DECLARE snapshot_product_id uuid;
        BEGIN
            SELECT ar.status, ar.content_version INTO approval_state, approval_version
            FROM approval_requests AS ar
            WHERE ar.id = NEW.approval_request_id AND ar.content_item_id = NEW.content_item_id;
            SELECT ci.version, ci.product_id INTO content_version, content_product_id
            FROM content_items AS ci WHERE ci.id = NEW.content_item_id;
            SELECT product_id, available, collected_at, source
            INTO snapshot_product_id, snapshot_available, snapshot_time, snapshot_source
            FROM product_snapshots AS ps WHERE ps.id = NEW.product_snapshot_id;
            SELECT p.source INTO product_source_value FROM products AS p
            WHERE p.id = snapshot_product_id;
            IF approval_state IS DISTINCT FROM 'approved' THEN RAISE EXCEPTION 'approved human review is required'; END IF;
            IF approval_version IS DISTINCT FROM content_version THEN RAISE EXCEPTION 'approval does not match current content version'; END IF;
            IF snapshot_product_id IS DISTINCT FROM content_product_id THEN RAISE EXCEPTION 'publication snapshot does not belong to content product'; END IF;
            IF snapshot_available IS DISTINCT FROM true THEN RAISE EXCEPTION 'available product snapshot is required'; END IF;
            IF snapshot_source IS DISTINCT FROM product_source_value THEN RAISE EXCEPTION 'snapshot provenance does not match product source'; END IF;
            IF snapshot_time > now() THEN RAISE EXCEPTION 'product snapshot timestamp is in the future'; END IF;
            IF snapshot_time < now() - interval '60 minutes' THEN RAISE EXCEPTION 'product snapshot is stale'; END IF;
            IF NEW.is_automatic THEN RAISE EXCEPTION 'automatic publication is disabled'; END IF;
            RETURN NEW;
        END;
        $$;
        DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events;
        CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation();
        DROP TRIGGER IF EXISTS content_status_transition ON content_items;
        CREATE TRIGGER content_status_transition BEFORE UPDATE OF status ON content_items
            FOR EACH ROW EXECUTE FUNCTION validate_content_status_transition();
        DROP TRIGGER IF EXISTS publication_compliance ON publications;
        CREATE TRIGGER publication_compliance BEFORE INSERT OR UPDATE ON publications
            FOR EACH ROW EXECUTE FUNCTION validate_publication_compliance();
    """)
    )

    settings = get_settings()
    preparer = bind.dialect.identifier_preparer
    migration_user = preparer.quote(settings.POSTGRES_MIGRATION_USER)
    app_user = preparer.quote(settings.POSTGRES_APP_USER)
    bind.execute(text(f"GRANT USAGE, CREATE ON SCHEMA public TO {migration_user}"))
    bind.execute(text(f"GRANT USAGE ON SCHEMA public TO {app_user}"))
    bind.execute(
        text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {app_user}")
    )
    bind.execute(
        text(f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {app_user}")
    )
    bind.execute(
        text(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {migration_user} IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {app_user}"
        )
    )
    bind.execute(
        text(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {migration_user} IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {app_user}"
        )
    )
    bind.execute(text(f"REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM {app_user}"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("DROP FUNCTION IF EXISTS prevent_audit_event_mutation() CASCADE"))
    bind.execute(text("DROP FUNCTION IF EXISTS validate_content_status_transition() CASCADE"))
    bind.execute(text("DROP FUNCTION IF EXISTS validate_publication_compliance() CASCADE"))
    for table in (
        "audit_events",
        "performance_daily",
        "publications",
        "approval_requests",
        "content_items",
        "affiliate_links",
        "campaigns",
        "product_snapshots",
        "products",
        "media_channels",
        "affiliate_accounts",
        "operators",
    ):
        op.drop_table(table)
    for name in (
        "publication_status",
        "approval_status",
        "content_status",
        "campaign_status",
        "product_source",
        "channel_type",
        "operator_role",
    ):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
