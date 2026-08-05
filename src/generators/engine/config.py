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

# Base fields present for every division (SPEC-002 esquema unificado), in the
# fixed order writers/parsers rely on. Division-specific fields (SPEC-009 §2)
# are appended after these, in the order listed below.
BASE_FIELDNAMES: list[str] = [
    "sale_id",
    "date",
    "category",
    "product",
    "quantity",
    "price",
    "currency",
    "status",
]

# Division-specific fields with a free-form generated value (identifiers,
# not a closed catalog) — generated in engine/common.py::generate_row, so
# they don't live under `extra_fields` in the YAML like manufacturer/size/etc.
# Listed here (not derived from the YAML) purely to fix their position within
# each division's `fieldnames`, matching the order generate_row emits them.
FREE_FORM_FIELDS: dict[str, list[str]] = {
    "electronica": ["serial_number", "model"],
    "supermercado": ["register_number"],
    "moda": [],
    "marketplace": ["seller_id"],
}


@dataclass
class CategoryConfig:
    products: list[str]
    price_min: Decimal
    price_max: Decimal
    # Variantes de escritura del nombre de categoría / producto (SPEC-008 #7, #9).
    # Un solo elemento (el nombre canónico) si no se declaran alias en el YAML.
    category_aliases: list[str]
    product_aliases: dict[str, list[str]]


@dataclass
class DivisionConfig:
    writer: Callable[[list[dict], list[str], dict[str, str], Path], None]
    date_formatter: Callable[[datetime.date], str]
    ext: str
    categories: dict[str, CategoryConfig]
    # Catálogos propios del sistema origen (SPEC-008 #5, #10). Pueden repetir
    # valores para sesgar la frecuencia (p.ej. la mayoría de ventas en PEN).
    currencies: list[str]
    statuses: list[str]
    # Catálogos cerrados para los campos específicos de división (SPEC-009 §2),
    # keyed by field name (ej. {"manufacturer": [...], "warranty_months": [...]}).
    # Vacío para divisiones sin campos de catálogo cerrado propios.
    extra_fields: dict[str, list]
    # sale_id..status (BASE_FIELDNAMES) + los campos propios de esta división
    # (claves de extra_fields + FREE_FORM_FIELDS[division]), en el orden en que
    # generate_row los produce. Es lo que cada writer usa como columnas de salida.
    fieldnames: list[str]


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
                category_aliases=cat.get("category_aliases", [name]),
                product_aliases=cat.get("product_aliases", {}),
            )
            for name, cat in spec["categories"].items()
        }
        extra_fields = spec.get("extra_fields", {})
        fieldnames = (
            list(BASE_FIELDNAMES)
            + list(extra_fields.keys())
            + FREE_FORM_FIELDS.get(division, [])
        )
        divisions[division] = DivisionConfig(
            writer=FORMAT_WRITERS[spec["format"]],
            date_formatter=_build_date_formatter(spec["date_format"]),
            ext=spec["ext"],
            categories=categories,
            currencies=spec["currencies"],
            statuses=spec["statuses"],
            extra_fields=extra_fields,
            fieldnames=fieldnames,
        )

    return divisions, list(raw["division_order"])


DIVISIONS, DIVISION_ORDER = _load_divisions(CONFIG_PATH)
