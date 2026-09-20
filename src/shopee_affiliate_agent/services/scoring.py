from dataclasses import dataclass, fields
from decimal import ROUND_HALF_UP, Decimal


class InvalidScore(ValueError):
    """Raised when score inputs or weights are outside the accepted domain."""


@dataclass(frozen=True)
class ScoreWeights:
    conversion_potential: Decimal = Decimal("30")
    net_commission: Decimal = Decimal("20")
    product_quality: Decimal = Decimal("15")
    price_stock_stability: Decimal = Decimal("10")
    niche_fit: Decimal = Decimal("10")
    video_demonstration_potential: Decimal = Decimal("10")
    cancellation_quality: Decimal = Decimal("5")

    def __post_init__(self) -> None:
        values = [getattr(self, field.name) for field in fields(self)]
        if any(value < 0 or value > 100 for value in values):
            raise InvalidScore("weights must be between 0 and 100")
        if sum(values, Decimal("0")) != Decimal("100"):
            raise InvalidScore("weights must total 100")


@dataclass(frozen=True)
class ScoreInputs:
    conversion_potential: Decimal
    net_commission: Decimal
    product_quality: Decimal
    price_stock_stability: Decimal
    niche_fit: Decimal
    video_demonstration_potential: Decimal
    cancellation_quality: Decimal

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if not isinstance(value, Decimal):
                raise InvalidScore(f"{field.name} must be Decimal")
            if value < 0 or value > 100:
                raise InvalidScore(f"{field.name} must be between 0 and 100")


class DeterministicScoringService:
    def __init__(self, weights: ScoreWeights | None = None) -> None:
        self.weights = weights or ScoreWeights()

    def calculate(self, inputs: ScoreInputs) -> Decimal:
        total = sum(
            (
                getattr(inputs, field.name) * getattr(self.weights, field.name)
                for field in fields(inputs)
            ),
            Decimal("0"),
        ) / Decimal("100")
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
