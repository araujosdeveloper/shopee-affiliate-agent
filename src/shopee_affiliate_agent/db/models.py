from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from shopee_affiliate_agent.db.base import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionMixin,
    utc_now,
)
from shopee_affiliate_agent.domain.enums import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    ApprovalStatus,
    CampaignStatus,
    ChannelType,
    ContentStatus,
    ImportBatchStatus,
    ImportRowStatus,
    OperatorRole,
    OpportunityStatus,
    ProductSource,
    PublicationStatus,
)


class Operator(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, SoftDeleteMixin, Base):
    __tablename__ = "operators"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[OperatorRole] = mapped_column(
        Enum(
            OperatorRole, name="operator_role", values_callable=lambda enum: [e.value for e in enum]
        )
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AffiliateAccount(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, SoftDeleteMixin, Base):
    __tablename__ = "affiliate_accounts"
    __table_args__ = (UniqueConstraint("platform", "external_reference"),)
    platform: Mapped[str] = mapped_column(String(50))
    external_reference: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MediaChannel(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, SoftDeleteMixin, Base):
    __tablename__ = "media_channels"
    __table_args__ = (UniqueConstraint("channel_type", "external_reference"),)
    channel_type: Mapped[ChannelType] = mapped_column(
        Enum(ChannelType, name="channel_type", values_callable=lambda enum: [e.value for e in enum])
    )
    external_reference: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Product(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, SoftDeleteMixin, Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("source", "external_id"),)
    source: Mapped[ProductSource] = mapped_column(
        Enum(
            ProductSource,
            name="product_source",
            values_callable=lambda enum: [e.value for e in enum],
        )
    )
    external_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500))
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProductSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_snapshots"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_non_negative"),
        Index("ix_product_snapshots_product_collected", "product_id", "collected_at"),
    )
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    source: Mapped[ProductSource] = mapped_column(
        Enum(
            ProductSource,
            name="product_source",
            values_callable=lambda enum: [e.value for e in enum],
        )
    )
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="BRL")
    available: Mapped[bool] = mapped_column(Boolean)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)


class Campaign(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, SoftDeleteMixin, Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="valid_period"),
    )
    name: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(
            CampaignStatus,
            name="campaign_status",
            values_callable=lambda enum: [e.value for e in enum],
        )
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AffiliateLink(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, SoftDeleteMixin, Base):
    __tablename__ = "affiliate_links"
    __table_args__ = (UniqueConstraint("affiliate_account_id", "product_id", "campaign_id"),)
    affiliate_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("affiliate_accounts.id", ondelete="RESTRICT")
    )
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    campaign_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=True
    )
    url: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ContentItem(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, SoftDeleteMixin, Base):
    __tablename__ = "content_items"
    __table_args__ = (
        CheckConstraint(
            "status <> 'rejected' OR rejection_reason IS NOT NULL", name="rejection_requires_reason"
        ),
        CheckConstraint(
            "status = 'rejected' OR rejection_reason IS NULL", name="reason_only_for_rejection"
        ),
    )
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    campaign_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(
            ContentStatus,
            name="content_status",
            values_callable=lambda enum: [e.value for e in enum],
        )
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)


class ApprovalRequest(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "status <> 'rejected' OR rejection_reason IS NOT NULL", name="rejection_requires_reason"
        ),
        CheckConstraint(
            "status = 'pending' OR reviewed_at IS NOT NULL", name="decision_requires_review_time"
        ),
    )
    content_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="RESTRICT")
    )
    content_version: Mapped[int] = mapped_column(nullable=False, default=1)
    requested_by_id: Mapped[UUID] = mapped_column(ForeignKey("operators.id", ondelete="RESTRICT"))
    reviewer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("operators.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(
            ApprovalStatus,
            name="approval_status",
            values_callable=lambda enum: [e.value for e in enum],
        )
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)


class Publication(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "publications"
    __table_args__ = (
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL", name="published_requires_time"
        ),
        CheckConstraint("is_automatic = false", name="automatic_forbidden"),
    )
    content_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="RESTRICT")
    )
    media_channel_id: Mapped[UUID] = mapped_column(
        ForeignKey("media_channels.id", ondelete="RESTRICT")
    )
    approval_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="RESTRICT")
    )
    product_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_snapshots.id", ondelete="RESTRICT")
    )
    status: Mapped[PublicationStatus] = mapped_column(
        Enum(
            PublicationStatus,
            name="publication_status",
            values_callable=lambda enum: [e.value for e in enum],
        )
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_automatic: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)


class PerformanceDaily(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "performance_daily"
    __table_args__ = (
        UniqueConstraint("affiliate_link_id", "media_channel_id", "metric_date"),
        CheckConstraint("clicks >= 0", name="clicks_non_negative"),
        CheckConstraint("orders >= 0", name="orders_non_negative"),
        CheckConstraint("commission_amount >= 0", name="commission_non_negative"),
    )
    affiliate_link_id: Mapped[UUID] = mapped_column(
        ForeignKey("affiliate_links.id", ondelete="RESTRICT")
    )
    media_channel_id: Mapped[UUID] = mapped_column(
        ForeignKey("media_channels.id", ondelete="RESTRICT")
    )
    metric_date: Mapped[date] = mapped_column(Date)
    clicks: Mapped[int] = mapped_column(default=0)
    orders: Mapped[int] = mapped_column(default=0)
    commission_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="BRL")
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_entity", "entity_type", "entity_id", "occurred_at"),)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("operators.id", ondelete="RESTRICT"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(120))
    entity_id: Mapped[UUID | None] = mapped_column(nullable=True)
    decision: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)


class ImportBatch(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint(
            "total_rows >= 0 AND accepted_rows >= 0 AND rejected_rows >= 0 AND duplicate_rows >= 0",
            name="non_negative_counts",
        ),
    )
    source: Mapped[ProductSource] = mapped_column(
        Enum(
            ProductSource,
            name="product_source",
            values_callable=lambda enum: [e.value for e in enum],
        )
    )
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str] = mapped_column(String(100))
    payload_sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[ImportBatchStatus] = mapped_column(
        Enum(
            ImportBatchStatus,
            name="import_batch_status",
            values_callable=lambda enum: [e.value for e in enum],
        )
    )
    total_rows: Mapped[int] = mapped_column(default=0)
    accepted_rows: Mapped[int] = mapped_column(default=0)
    rejected_rows: Mapped[int] = mapped_column(default=0)
    duplicate_rows: Mapped[int] = mapped_column(default=0)
    requested_by_id: Mapped[UUID] = mapped_column(ForeignKey("operators.id", ondelete="RESTRICT"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)


class ImportRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_rows"
    __table_args__ = (
        UniqueConstraint("import_batch_id", "row_number"),
        Index("ix_import_rows_hash", "row_sha256"),
    )
    import_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT")
    )
    row_number: Mapped[int]
    external_id: Mapped[str] = mapped_column(String(255))
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    normalized_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[ImportRowStatus] = mapped_column(
        Enum(
            ImportRowStatus,
            name="import_row_status",
            values_callable=lambda enum: [e.value for e in enum],
        )
    )
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    product_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=True
    )
    product_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("product_snapshots.id", ondelete="RESTRICT"), nullable=True
    )
    row_sha256: Mapped[str] = mapped_column(String(64))


class ProductAssessment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "product_assessments"
    __table_args__ = tuple(
        CheckConstraint(f"{name} BETWEEN 0 AND 100", name=f"{name}_range")
        for name in (
            "conversion_potential",
            "net_commission",
            "product_quality",
            "price_stock_stability",
            "niche_fit",
            "video_demonstration_potential",
            "cancellation_quality",
        )
    )
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    product_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_snapshots.id", ondelete="RESTRICT")
    )
    conversion_potential: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    net_commission: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    product_quality: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    price_stock_stability: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    niche_fit: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    video_demonstration_potential: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    cancellation_quality: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    assessed_by_id: Mapped[UUID] = mapped_column(ForeignKey("operators.id", ondelete="RESTRICT"))
    rule_version: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProductScore(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "product_scores"
    __table_args__ = (CheckConstraint("total_score BETWEEN 0 AND 100", name="total_score_range"),)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    product_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_snapshots.id", ondelete="RESTRICT")
    )
    product_assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_assessments.id", ondelete="RESTRICT")
    )
    rule_version: Mapped[str] = mapped_column(String(80))
    weights: Mapped[dict[str, Any]] = mapped_column(JSON)
    components: Mapped[dict[str, Any]] = mapped_column(JSON)
    total_score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)


class ProductOpportunity(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "product_opportunities"
    __table_args__ = (CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    product_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_snapshots.id", ondelete="RESTRICT")
    )
    product_score_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_scores.id", ondelete="RESTRICT")
    )
    status: Mapped[OpportunityStatus] = mapped_column(
        Enum(
            OpportunityStatus,
            name="opportunity_status",
            values_callable=lambda enum: [e.value for e in enum],
        )
    )
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    shortlisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)


class OperationalAlert(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "operational_alerts"
    alert_type: Mapped[AlertType] = mapped_column(
        Enum(AlertType, name="alert_type", values_callable=lambda enum: [e.value for e in enum])
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(
            AlertSeverity,
            name="alert_severity",
            values_callable=lambda enum: [e.value for e in enum],
        )
    )
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[UUID]
    message: Mapped[str] = mapped_column(String(500))
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, name="alert_status", values_callable=lambda enum: [e.value for e in enum])
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("operators.id", ondelete="RESTRICT"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
