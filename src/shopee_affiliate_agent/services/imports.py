import csv
import io
from dataclasses import dataclass
from typing import Any

from shopee_affiliate_agent.domain.enums import ProductSource
from shopee_affiliate_agent.services.normalization import NormalizationError, normalize_product

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 10_000
REQUIRED_COLUMNS = {"external_id", "title", "price", "currency", "available", "collected_at"}
OPTIONAL_COLUMNS = {"canonical_url", "category", "source_payload_hash"}
ALLOWED_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS


class ImportFileError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ParsedRow:
    row_number: int
    raw_data: dict[str, str]
    normalized: dict[str, Any] | None
    error_code: str | None = None
    error_message: str | None = None


def parse_official_csv(payload: bytes) -> list[ParsedRow]:
    if len(payload) > MAX_IMPORT_BYTES:
        raise ImportFileError("import_limit_exceeded", "file exceeds 5 MiB")
    try:
        content = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ImportFileError("invalid_import_file", "file must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(content, newline=""))
    if not reader.fieldnames:
        raise ImportFileError("invalid_import_file", "CSV header is required")
    columns = set(reader.fieldnames)
    missing, unknown = REQUIRED_COLUMNS - columns, columns - ALLOWED_COLUMNS
    if missing:
        raise ImportFileError(
            "invalid_import_file", f"missing columns: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise ImportFileError(
            "invalid_import_file", f"unknown columns: {', '.join(sorted(unknown))}"
        )
    rows: list[ParsedRow] = []
    for row_number, raw in enumerate(reader, start=2):
        if len(rows) >= MAX_IMPORT_ROWS:
            raise ImportFileError("import_limit_exceeded", "file exceeds 10000 rows")
        safe_raw = {key: value for key, value in raw.items() if key in ALLOWED_COLUMNS}
        try:
            product = normalize_product(safe_raw, ProductSource.OFFICIAL_IMPORT)
            from shopee_affiliate_agent.services.normalization import canonical_data

            rows.append(ParsedRow(row_number, safe_raw, canonical_data(product)))
        except NormalizationError as exc:
            rows.append(ParsedRow(row_number, safe_raw, None, exc.code, str(exc)[:500]))
    return rows
