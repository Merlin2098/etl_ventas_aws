from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.generators.engine.common import build_faker, generate_row
from src.generators.engine.config import DIVISIONS
from src.lambda_ingestion.electronica.parser import CsvSalesParser
from src.lambda_ingestion.marketplace.parser import PdfSalesParser
from src.lambda_ingestion.moda.parser import JsonSalesParser
from src.lambda_ingestion.supermercado.parser import ExcelSalesParser

PARSERS = {
    "electronica": CsvSalesParser(),
    "supermercado": ExcelSalesParser(),
    "moda": JsonSalesParser(),
    "marketplace": PdfSalesParser(),
}


def _generate_clean_rows(division: str, date: datetime.date, count: int) -> list[dict]:
    fake = build_faker(seed=123)
    config = DIVISIONS[division]
    rows = []
    for _ in range(count):
        record = generate_row(division, date, fake, config)
        row = {
            "sale_id": record.sale_id,
            "date": config.date_formatter(record.date),
            "category": record.category,
            "product": record.product,
            "quantity": record.quantity,
            "price": record.price,
            "currency": record.currency,
            "status": record.status,
        }
        rows.append(row)
    return rows


@pytest.mark.parametrize("division", list(DIVISIONS.keys()))
def test_parser_round_trips_generator_output(tmp_path: Path, division: str):
    date = datetime.date(2026, 8, 1)
    rows = _generate_clean_rows(division, date, count=20)

    config = DIVISIONS[division]
    output_path = tmp_path / f"{division}.{config.ext}"
    config.writer(rows, output_path)

    parser = PARSERS[division]
    parsed_rows = list(parser.parse(output_path.read_bytes()))

    assert len(parsed_rows) == 20
    first = parsed_rows[0]
    assert first["sale_id"] == rows[0]["sale_id"]
    assert Decimal(str(first["price"])) == rows[0]["price"]


def test_csv_parser_raises_file_parse_error_on_empty_input():
    from src.lambda_ingestion.common.errors import FileParseError

    with pytest.raises(FileParseError):
        list(PARSERS["electronica"].parse(b""))


def test_json_parser_raises_file_parse_error_on_invalid_json():
    from src.lambda_ingestion.common.errors import FileParseError

    with pytest.raises(FileParseError):
        list(PARSERS["moda"].parse(b"not json"))
