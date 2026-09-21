from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from shopee_affiliate_agent.domain.enums import ProductSource
from shopee_affiliate_agent.services.normalization import (
    NormalizationError,
    canonical_sha256,
    normalize_product,
    normalize_text,
)


def valid(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "external_id": " sku-1 ",
        "title": " Product   title ",
        "price": "10.00",
        "currency": "brl",
        "available": "true",
        "collected_at": datetime.now(UTC) - timedelta(seconds=1),
    }
    data.update(overrides)
    return data


def test_normalizes_text_currency_decimal_and_timestamp() -> None:
    product = normalize_product(valid(), ProductSource.MANUAL)
    assert product.external_id == "sku-1"
    assert product.title == "Product title"
    assert product.price == Decimal("10.00")
    assert product.currency == "BRL"


def test_canonical_hash_is_deterministic() -> None:
    product = normalize_product(valid(), ProductSource.MANUAL)
    assert canonical_sha256(product) == canonical_sha256(product)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/product",
        "https://user:pass@example.test/product",
        "//example.test/product",
    ],
)
def test_rejects_unsafe_url(url: str) -> None:
    with pytest.raises(NormalizationError):
        normalize_product(valid(canonical_url=url), ProductSource.MANUAL)


def test_rejects_future_or_naive_timestamp() -> None:
    with pytest.raises(NormalizationError, match="future"):
        normalize_product(
            valid(collected_at=datetime.now(UTC) + timedelta(minutes=1)), ProductSource.MANUAL
        )
    with pytest.raises(NormalizationError, match="timezone-aware"):
        normalize_product(valid(collected_at=datetime.now()), ProductSource.MANUAL)


@pytest.mark.parametrize("price", [1.1, "-1.00", "1.001", "not-money"])
def test_rejects_invalid_commercial_values(price: object) -> None:
    with pytest.raises(NormalizationError):
        normalize_product(valid(price=price), ProductSource.MANUAL)


def test_utf8_validation() -> None:
    with pytest.raises(NormalizationError):
        normalize_text("\ud800", "title", required=True)
