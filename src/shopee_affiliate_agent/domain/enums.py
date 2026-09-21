from enum import StrEnum


class ProductSource(StrEnum):
    MANUAL = "manual"
    OFFICIAL_IMPORT = "official_import"
    APPROVED_API = "approved_api"


class ContentStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    RETIRED = "retired"
    REJECTED = "rejected"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PublicationStatus(StrEnum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChannelType(StrEnum):
    SOCIAL = "social"
    MESSAGING = "messaging"
    VIDEO = "video"
    OTHER = "other"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class OperatorRole(StrEnum):
    ADMIN = "admin"
    REVIEWER = "reviewer"
    EDITOR = "editor"


class ImportBatchStatus(StrEnum):
    RECEIVED = "received"
    VALIDATING = "validating"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImportRowStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"


class OpportunityStatus(StrEnum):
    CANDIDATE = "candidate"
    SHORTLISTED = "shortlisted"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class AlertType(StrEnum):
    STALE_SNAPSHOT = "stale_snapshot"
    UNAVAILABLE_PRODUCT = "unavailable_product"
    IMPORT_FAILED = "import_failed"
    IMPORT_PARTIALLY_COMPLETED = "import_partially_completed"
    HIGH_SCORE_OPPORTUNITY = "high_score_opportunity"
    INVALID_SOURCE_DATA = "invalid_source_data"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
