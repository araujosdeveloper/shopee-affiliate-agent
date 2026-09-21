import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from shopee_affiliate_agent.domain.enums import ProductSource

SPACE_PATTERN = re.compile(r"\s+")
TWOPLACES = Decimal("0.01")


class NormalizationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class NormalizedProduct:
    external_id: str
    title: str
    price: Decimal
    currency: str
    available: bool
    collected_at: datetime
    source: ProductSource
    canonical_url: str | None = None
    category: str | None = None
    source_payload_hash: str | None = None


def normalize_text(value: object, field: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise NormalizationError("validation_error", f"{field} is required")
        return None
    if not isinstance(value, str):
        raise NormalizationError("validation_error", f"{field} must be text")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise NormalizationError("validation_error", f"{field} must be valid UTF-8") from exc
    normalized = SPACE_PATTERN.sub(" ", value.strip())
    if required and not normalized:
        raise NormalizationError("validation_error", f"{field} is required")
    return normalized or None


def normalize_product(
    data: dict[str, Any], source: ProductSource, *, now: datetime | None = None
) -> NormalizedProduct:
    external_id = normalize_text(data.get("external_id"), "external_id", required=True)
    title = normalize_text(data.get("title"), "title", required=True)
    currency = (normalize_text(data.get("currency"), "currency", required=True) or "").upper()
    if currency != "BRL":
        raise NormalizationError("validation_error", "only BRL currency is accepted")
    price_value = data.get("price")
    if isinstance(price_value, float):
        raise NormalizationError("validation_error", "price must not be a float")
    try:
        price = Decimal(str(price_value))
    except (InvalidOperation, ValueError) as exc:
        raise NormalizationError("validation_error", "price must be Decimal") from exc
    if price < 0 or price != price.quantize(TWOPLACES):
        raise NormalizationError("validation_error", "price must be non-negative with two decimals")
    available_value = data.get("available")
    if isinstance(available_value, bool):
        available = available_value
    elif isinstance(available_value, str) and available_value.strip().lower() in {"true", "false"}:
        available = available_value.strip().lower() == "true"
    else:
        raise NormalizationError("validation_error", "available must be true or false")
    collected_value = data.get("collected_at")
    try:
        collected_at = (
            collected_value
            if isinstance(collected_value, datetime)
            else datetime.fromisoformat(str(collected_value).replace("Z", "+00:00"))
        )
    except ValueError as exc:
        raise NormalizationError("validation_error", "collected_at must be ISO 8601") from exc
    if collected_at.tzinfo is None or collected_at.utcoffset() is None:
        raise NormalizationError("validation_error", "collected_at must be timezone-aware")
    collected_at = collected_at.astimezone(UTC)
    if collected_at > (now or datetime.now(UTC)):
        raise NormalizationError("future_snapshot", "collected_at must not be in the future")
    url = normalize_text(data.get("canonical_url"), "canonical_url")
    if url:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise NormalizationError(
                "validation_error", "canonical_url must be HTTPS without credentials"
            )
    return NormalizedProduct(
        external_id=external_id or "",
        title=title or "",
        price=price,
        currency=currency,
        available=available,
        collected_at=collected_at,
        source=source,
        canonical_url=url,
        category=normalize_text(data.get("category"), "category"),
        source_payload_hash=normalize_text(data.get("source_payload_hash"), "source_payload_hash"),
    )


def canonical_data(product: NormalizedProduct) -> dict[str, Any]:
    result = asdict(product)
    result["price"] = format(product.price, ".2f")
    result["collected_at"] = product.collected_at.isoformat().replace("+00:00", "Z")
    result["source"] = product.source.value
    return result


def canonical_sha256(product: NormalizedProduct) -> str:
    value = json.dumps(
        canonical_data(product), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def payload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
