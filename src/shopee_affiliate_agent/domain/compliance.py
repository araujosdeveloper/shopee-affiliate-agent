from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from shopee_affiliate_agent.domain.enums import ProductSource


class ComplianceViolation(ValueError):
    """Raised when a non-negotiable compliance rule is violated."""


FORBIDDEN_CLAIM_TYPES = frozenset(
    {"invented_discount", "invented_rating", "false_scarcity", "personal_experience"}
)


def validate_product_source(source: ProductSource | str) -> ProductSource:
    try:
        return ProductSource(source)
    except ValueError as exc:
        raise ComplianceViolation("product source is not approved") from exc


def validate_snapshot(price: Decimal, collected_at: datetime | None) -> None:
    if price < 0:
        raise ComplianceViolation("price cannot be negative")
    if collected_at is None:
        raise ComplianceViolation("price requires collected_at")
    if collected_at.tzinfo is None:
        raise ComplianceViolation("collected_at must be timezone-aware")


def validate_content_claims(claim_types: set[str]) -> None:
    forbidden = claim_types & FORBIDDEN_CLAIM_TYPES
    if forbidden:
        raise ComplianceViolation("content includes a forbidden claim type")


@dataclass(frozen=True)
class PublicationEvidence:
    approved_by_human: bool
    snapshot_collected_at: datetime
    available: bool
    is_mass_send: bool = False
    uses_cookie_or_automatic_redirect: bool = False
    is_self_purchase: bool = False


def validate_publication(
    evidence: PublicationEvidence,
    *,
    now: datetime | None = None,
    max_snapshot_age: timedelta = timedelta(minutes=60),
) -> None:
    current_time = now or datetime.now(UTC)
    if not evidence.approved_by_human:
        raise ComplianceViolation("human approval is required")
    if evidence.snapshot_collected_at.tzinfo is None:
        raise ComplianceViolation("snapshot timestamp must be timezone-aware")
    if current_time - evidence.snapshot_collected_at > max_snapshot_age:
        raise ComplianceViolation("price and availability validation is stale")
    if not evidence.available:
        raise ComplianceViolation("product is unavailable")
    if evidence.is_mass_send:
        raise ComplianceViolation("mass sending is forbidden")
    if evidence.uses_cookie_or_automatic_redirect:
        raise ComplianceViolation("cookies and automatic redirects are forbidden")
    if evidence.is_self_purchase:
        raise ComplianceViolation("self-purchase through an affiliate link is forbidden")
