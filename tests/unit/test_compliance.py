from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from shopee_affiliate_agent.domain.compliance import (
    ComplianceViolation,
    PublicationEvidence,
    validate_content_claims,
    validate_product_source,
    validate_publication,
    validate_snapshot,
)
from shopee_affiliate_agent.domain.enums import ProductSource


@pytest.mark.parametrize("source", list(ProductSource))
def test_accepts_only_explicit_product_sources(source: ProductSource) -> None:
    assert validate_product_source(source) is source


def test_rejects_scraping_source() -> None:
    with pytest.raises(ComplianceViolation, match="not approved"):
        validate_product_source("scraping")


def test_price_requires_collection_time() -> None:
    with pytest.raises(ComplianceViolation, match="requires collected_at"):
        validate_snapshot(Decimal("10.00"), None)


@pytest.mark.parametrize(
    "claim", ["invented_discount", "invented_rating", "false_scarcity", "personal_experience"]
)
def test_forbidden_claims(claim: str) -> None:
    with pytest.raises(ComplianceViolation, match="forbidden claim"):
        validate_content_claims({claim})


def valid_evidence(now: datetime) -> PublicationEvidence:
    return PublicationEvidence(True, now - timedelta(minutes=5), True)


def test_valid_publication_evidence() -> None:
    now = datetime.now(UTC)
    validate_publication(valid_evidence(now), now=now)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"approved_by_human": False}, "human approval"),
        ({"available": False}, "unavailable"),
        ({"is_mass_send": True}, "mass sending"),
        ({"uses_cookie_or_automatic_redirect": True}, "automatic redirects"),
        ({"is_self_purchase": True}, "self-purchase"),
    ],
)
def test_rejects_non_compliant_publication(changes: dict[str, bool], message: str) -> None:
    now = datetime.now(UTC)
    values = valid_evidence(now).__dict__ | changes
    with pytest.raises(ComplianceViolation, match=message):
        validate_publication(PublicationEvidence(**values), now=now)


def test_rejects_stale_snapshot() -> None:
    now = datetime.now(UTC)
    evidence = PublicationEvidence(True, now - timedelta(minutes=61), True)
    with pytest.raises(ComplianceViolation, match="stale"):
        validate_publication(evidence, now=now)
