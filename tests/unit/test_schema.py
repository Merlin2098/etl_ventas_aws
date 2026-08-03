from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from src.lambda_ingestion.common.errors import RowValidationError
from src.lambda_ingestion.common.schema import (
    GOLD_SCHEMA,
    parse_date,
    parse_free_text_date_es,
    validate_and_normalize,
)


def test_gold_schema_excludes_partition_columns():
    field_names = {field.name for field in GOLD_SCHEMA}
    assert "store" not in field_names
    assert "date" not in field_names
    assert field_names == {
        "sale_id",
        "category",
        "product",
        "quantity",
        "price",
        "total",
        "currency",
        "status",
    }


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("01/08/2026", datetime.date(2026, 8, 1)),
        ("08-01-2026", datetime.date(2026, 8, 1)),
        ("2026/08/01", datetime.date(2026, 8, 1)),
        ("2026-08-01", datetime.date(2026, 8, 1)),
        ("2026-08-01T00:00:00", datetime.date(2026, 8, 1)),
    ],
)
def test_parse_date_known_formats(raw, expected):
    assert parse_date(raw) == expected


def test_parse_date_rejects_free_text_typo():
    assert parse_date("ayer") is None


def test_parse_free_text_date_es():
    assert parse_free_text_date_es("1 de agosto de 2026") == datetime.date(2026, 8, 1)


def test_parse_free_text_date_es_rejects_invalid_month():
    assert parse_free_text_date_es("1 de fecha de 2026") is None


def test_validate_and_normalize_recalculates_total_ignoring_source_total():
    row = {
        "sale_id": "6f2b8d63-2b0e-4e1a-8f5a-1c2b3d4e5f60",
        "date": "01/08/2026",
        "category": "Audio",
        "product": "Parlante",
        "quantity": "3",
        "price": "10.00",
        "total": "999.99",  # must be ignored — always recalculated
    }
    gold_row, date = validate_and_normalize(
        row, division="electronica", stage="validate", correlation_id="c1"
    )
    assert gold_row["total"] == Decimal("30.00")
    assert date == datetime.date(2026, 8, 1)
    assert "store" not in gold_row
    assert "date" not in gold_row


def test_validate_and_normalize_defaults_currency_and_status_when_missing():
    row = {
        "date": "01/08/2026",
        "category": "Audio",
        "product": "Parlante",
        "quantity": "1",
        "price": "10.00",
    }
    gold_row, _ = validate_and_normalize(
        row, division="electronica", stage="validate", correlation_id="c1"
    )
    assert gold_row["currency"] == "PEN"
    assert gold_row["status"] == "UNKNOWN"


def test_validate_and_normalize_uppercases_currency_and_status():
    row = {
        "date": "01/08/2026",
        "category": "Audio",
        "product": "Parlante",
        "quantity": "1",
        "price": "10.00",
        "currency": "usd",
        "status": "paid",
    }
    gold_row, _ = validate_and_normalize(
        row, division="electronica", stage="validate", correlation_id="c1"
    )
    assert gold_row["currency"] == "USD"
    assert gold_row["status"] == "PAID"


def test_validate_and_normalize_generates_sale_id_when_missing():
    row = {
        "date": "01/08/2026",
        "category": "Audio",
        "product": "Parlante",
        "quantity": "1",
        "price": "10.00",
    }
    gold_row, _ = validate_and_normalize(
        row, division="electronica", stage="validate", correlation_id="c1"
    )
    assert gold_row["sale_id"]


@pytest.mark.parametrize(
    "row",
    [
        {
            "date": "01/08/2026",
            "product": "P",
            "quantity": "1",
            "price": "1",
        },  # missing category
        {
            "date": "01/08/2026",
            "category": "C",
            "quantity": "1",
            "price": "1",
        },  # missing product
        {
            "date": "01/08/2026",
            "category": "C",
            "product": "P",
            "quantity": "N/A",
            "price": "1",
        },
        {
            "date": "01/08/2026",
            "category": "C",
            "product": "P",
            "quantity": "1",
            "price": "-5",
        },
        {
            "date": "01/08/2026",
            "category": "C",
            "product": "P",
            "quantity": "-1",
            "price": "1",
        },
        {
            "date": "ayer",
            "category": "C",
            "product": "P",
            "quantity": "1",
            "price": "1",
        },
    ],
)
def test_validate_and_normalize_raises_on_invalid_rows(row):
    with pytest.raises(RowValidationError):
        validate_and_normalize(
            row, division="electronica", stage="validate", correlation_id="c1"
        )
