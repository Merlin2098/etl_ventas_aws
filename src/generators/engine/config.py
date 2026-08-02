from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.generators.common import format_date_free_text
from src.generators.writers.csv_writer import write_csv
from src.generators.writers.excel_writer import write_excel
from src.generators.writers.json_writer import write_json
from src.generators.writers.pdf_writer import write_pdf


@dataclass
class DivisionConfig:
    writer: Callable[[list[dict], Path], None]
    date_formatter: Callable[[datetime.date], str]
    ext: str


DIVISIONS: dict[str, DivisionConfig] = {
    "electronica": DivisionConfig(
        writer=write_csv,
        date_formatter=lambda d: d.strftime("%d/%m/%Y"),
        ext="csv",
    ),
    "supermercado": DivisionConfig(
        writer=write_excel,
        date_formatter=lambda d: d.strftime("%m-%d-%Y"),
        ext="xlsx",
    ),
    "moda": DivisionConfig(
        writer=write_json,
        date_formatter=lambda d: d.isoformat(),
        ext="json",
    ),
    "hogar": DivisionConfig(
        writer=write_csv,
        date_formatter=lambda d: d.strftime("%Y/%m/%d"),
        ext="csv",
    ),
    "marketplace": DivisionConfig(
        writer=write_pdf,
        date_formatter=format_date_free_text,
        ext="pdf",
    ),
}

DIVISION_ORDER = ["electronica", "supermercado", "moda", "hogar", "marketplace"]
