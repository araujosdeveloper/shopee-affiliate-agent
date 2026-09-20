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
)
from shopee_affiliate_agent.domain.enums import (
    ApprovalStatus,
    CampaignStatus,
    ChannelType,
    ContentStatus,
    OperatorRole,
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
