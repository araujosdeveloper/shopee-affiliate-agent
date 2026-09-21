from decimal import Decimal

from shopee_affiliate_agent.services.commerce import (
    OPPORTUNITY_POLICY_VERSION,
    OPPORTUNITY_THRESHOLD,
)


def test_opportunity_policy_is_fixed_and_versioned() -> None:
    assert OPPORTUNITY_POLICY_VERSION == "commercial-opportunity-v1"
    assert OPPORTUNITY_THRESHOLD == Decimal("70.00")
    assert Decimal("69.99") < OPPORTUNITY_THRESHOLD
    assert Decimal("70.00") >= OPPORTUNITY_THRESHOLD
