from datetime import UTC, datetime

import pytest

from shopee_affiliate_agent.services.imports import ImportFileError, parse_official_csv

HEADER = b"external_id,title,price,currency,available,collected_at\n"


def row(**changes: str) -> bytes:
    values = {
        "external_id": "1",
        "title": "Product",
        "price": "10.00",
        "currency": "BRL",
        "available": "true",
        "collected_at": datetime.now(UTC).isoformat(),
    }
    values.update(changes)
    return (",".join(values.values()) + "\n").encode()


def test_valid_csv_and_partial_invalid_row() -> None:
    parsed = parse_official_csv(HEADER + row() + row(price="bad"))
    assert parsed[0].normalized is not None
    assert parsed[1].error_code == "validation_error"


@pytest.mark.parametrize(
    "payload", [b"\xff", b"", b"external_id,title\n1,x\n", HEADER.replace(b"\n", b",unknown\n")]
)
def test_rejects_invalid_structural_csv(payload: bytes) -> None:
    with pytest.raises(ImportFileError):
        parse_official_csv(payload)


def test_rejects_size_and_row_limits() -> None:
    with pytest.raises(ImportFileError, match="5 MiB"):
        parse_official_csv(b"x" * (5 * 1024 * 1024 + 1))
    with pytest.raises(ImportFileError, match="10000"):
        parse_official_csv(HEADER + row() * 10001)


def test_formula_is_preserved_as_text_and_never_executed() -> None:
    parsed = parse_official_csv(HEADER + row(title="=1+1"))
    assert parsed[0].raw_data["title"] == "=1+1"
