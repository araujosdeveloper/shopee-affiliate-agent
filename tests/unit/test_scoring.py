from decimal import Decimal

import pytest

from shopee_affiliate_agent.services.scoring import (
    DeterministicScoringService,
    InvalidScore,
    ScoreInputs,
    ScoreWeights,
)


def inputs(value: str = "50") -> ScoreInputs:
    score = Decimal(value)
    return ScoreInputs(score, score, score, score, score, score, score)


@pytest.mark.parametrize(("value", "expected"), [("0", "0.00"), ("50", "50.00"), ("100", "100.00")])
def test_weighted_score_bounds(value: str, expected: str) -> None:
    assert DeterministicScoringService().calculate(inputs(value)) == Decimal(expected)


def test_weighted_score_uses_all_dimensions() -> None:
    values = ScoreInputs(
        conversion_potential=Decimal("100"),
        net_commission=Decimal("50"),
        product_quality=Decimal("80"),
        price_stock_stability=Decimal("40"),
        niche_fit=Decimal("60"),
        video_demonstration_potential=Decimal("20"),
        cancellation_quality=Decimal("100"),
    )
    assert DeterministicScoringService().calculate(values) == Decimal("69.00")


@pytest.mark.parametrize("value", [Decimal("-0.01"), Decimal("100.01")])
def test_rejects_out_of_range_input(value: Decimal) -> None:
    with pytest.raises(InvalidScore, match="between 0 and 100"):
        ScoreInputs(
            value,
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
        )


def test_rejects_float_input() -> None:
    with pytest.raises(InvalidScore, match="must be Decimal"):
        ScoreInputs(
            1.0, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")
        )  # type: ignore[arg-type]


def test_weights_must_total_one_hundred() -> None:
    with pytest.raises(InvalidScore, match="total 100"):
        ScoreWeights(conversion_potential=Decimal("29"))


def test_weights_must_be_in_range() -> None:
    with pytest.raises(InvalidScore, match="between 0 and 100"):
        ScoreWeights(conversion_potential=Decimal("130"), net_commission=Decimal("-80"))
