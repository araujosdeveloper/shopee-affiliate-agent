from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shopee_affiliate_agent.domain.enums import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    ImportBatchStatus,
    ImportRowStatus,
    OpportunityStatus,
    ProductSource,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProductCreate(BaseModel):
    source: ProductSource
    external_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    canonical_url: str | None = None
    category: str | None = Field(default=None, max_length=255)


class ProductUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    canonical_url: str | None = None
    category: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    version: int = Field(ge=1)


class ProductOut(ORMModel):
    id: UUID
    source: ProductSource
    external_id: str
    title: str
    canonical_url: str | None
    category: str | None
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class SnapshotCreate(BaseModel):
    price: Decimal
    currency: str
    available: bool
    collected_at: datetime
    source_payload_hash: str | None = None

    @field_validator("price", mode="before")
    @classmethod
    def reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("float is not accepted")
        return value


class SnapshotOut(ORMModel):
    id: UUID
    product_id: UUID
    source: ProductSource
    price: Decimal
    currency: str
    available: bool
    collected_at: datetime
    source_payload_hash: str | None
    idempotency_key: str
    created_at: datetime


class ManualImportCreate(ProductCreate, SnapshotCreate):
    pass


class BatchOut(ORMModel):
    id: UUID
    source: ProductSource
    filename: str | None
    content_type: str
    payload_sha256: str
    status: ImportBatchStatus
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    duplicate_rows: int
    requested_by_id: UUID
    started_at: datetime | None
    completed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class RowOut(ORMModel):
    id: UUID
    import_batch_id: UUID
    row_number: int
    external_id: str
    normalized_data: dict[str, Any] | None
    status: ImportRowStatus
    error_code: str | None
    error_message: str | None
    product_id: UUID | None
    product_snapshot_id: UUID | None
    created_at: datetime
    updated_at: datetime


class AssessmentCreate(BaseModel):
    product_snapshot_id: UUID
    conversion_potential: Decimal
    net_commission: Decimal
    product_quality: Decimal
    price_stock_stability: Decimal
    niche_fit: Decimal
    video_demonstration_potential: Decimal
    cancellation_quality: Decimal
    evidence: dict[str, Any] = Field(default_factory=dict)
    rule_version: str = Field(default="commercial-score-v1", max_length=80)

    @field_validator(
        "conversion_potential",
        "net_commission",
        "product_quality",
        "price_stock_stability",
        "niche_fit",
        "video_demonstration_potential",
        "cancellation_quality",
        mode="before",
    )
    @classmethod
    def decimal_only(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("float is not accepted")
        return value


class AssessmentOut(ORMModel):
    id: UUID
    product_id: UUID
    product_snapshot_id: UUID
    conversion_potential: Decimal
    net_commission: Decimal
    product_quality: Decimal
    price_stock_stability: Decimal
    niche_fit: Decimal
    video_demonstration_potential: Decimal
    cancellation_quality: Decimal
    evidence: dict[str, Any]
    assessed_by_id: UUID
    rule_version: str
    created_at: datetime


class ScoreOut(ORMModel):
    id: UUID
    product_id: UUID
    product_snapshot_id: UUID
    product_assessment_id: UUID
    rule_version: str
    weights: dict[str, Any]
    components: dict[str, Any]
    total_score: Decimal
    calculated_at: datetime


class OpportunityOut(ORMModel):
    id: UUID
    product_id: UUID
    product_snapshot_id: UUID
    product_score_id: UUID
    status: OpportunityStatus
    score: Decimal
    reason_codes: list[str]
    generated_at: datetime
    expires_at: datetime
    shortlisted_at: datetime | None
    dismissed_at: datetime | None
    dismissed_reason: str | None
    version: int


class VersionAction(BaseModel):
    version: int = Field(ge=1)


class DismissAction(VersionAction):
    reason: str = Field(min_length=1, max_length=500)


class AlertOut(ORMModel):
    id: UUID
    alert_type: AlertType
    severity: AlertSeverity
    entity_type: str
    entity_id: UUID
    message: str
    status: AlertStatus
    detected_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    acknowledged_by_id: UUID | None
    version: int
