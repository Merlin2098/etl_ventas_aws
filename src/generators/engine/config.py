from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Callable

import yaml

from src.generators.engine.common import format_date_free_text
from src.generators.engine.writers.csv_writer import write_csv
from src.generators.engine.writers.excel_writer import write_excel
from src.generators.engine.writers.json_writer import write_json
from src.generators.engine.writers.pdf_writer import write_pdf

# The single source of truth for what varies per division (format, date
# pattern, extension, product catalog) — sits one level up from engine/, next
# to __init__.py, so it's the first thing visible when opening src/generators/.
CONFIG_PATH = Path(__file__).resolve().parents[1] / "detalle-data.yaml"

# format (YAML) -> writer function. Adding a new source format still requires
# a writer implementation, but the division -> format mapping is data-driven.
FORMAT_WRITERS: dict[str, Callable[[list[dict], Path], None]] = {
    "csv": write_csv,
    "excel": write_excel,
    "json": write_json,
    "pdf": write_pdf,
}

# date_format (YAML) -> formatter function. "iso8601" and "free_text_es" are
# named formats (not strftime patterns); anything else is passed to strftime.
_NAMED_DATE_FORMATTERS: dict[str, Callable[[datetime.date], str]] = {
    "iso8601": lambda d: d.isoformat(),
    "free_text_es": format_date_free_text,
}


@dataclass
class CategoryConfig:
    products: list[str]
    price_min: Decimal
    price_max: Decimal


@dataclass
class DivisionConfig:
    writer: Callable[[list[dict], Path], None]
    date_formatter: Callable[[datetime.date], str]
    ext: str
    categories: dict[str, CategoryConfig]


def _build_date_formatter(date_format: str) -> Callable[[datetime.date], str]:
    named = _NAMED_DATE_FORMATTERS.get(date_format)
    if named is not None:
        return named
    return lambda d, fmt=date_format: d.strftime(fmt)


def _load_divisions(config_path: Path) -> tuple[dict[str, DivisionConfig], list[str]]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    divisions: dict[str, DivisionConfig] = {}
    for division, spec in raw["divisions"].items():
        categories = {
            name: CategoryConfig(
                products=cat["products"],
                price_min=Decimal(str(cat["price_min"])),
                price_max=Decimal(str(cat["price_max"])),
            )
            for name, cat in spec["categories"].items()
        }
        divisions[division] = DivisionConfig(
            writer=FORMAT_WRITERS[spec["format"]],
            date_formatter=_build_date_formatter(spec["date_format"]),
            ext=spec["ext"],
            categories=categories,
        )

    return divisions, list(raw["division_order"])


DIVISIONS, DIVISION_ORDER = _load_divisions(CONFIG_PATH)
