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
