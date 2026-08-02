from __future__ import annotations

import datetime
import uuid
from decimal import Decimal, InvalidOperation

import pyarrow as pa

from src.lambda_ingestion.common.errors import RowValidationError

# Gold Parquet columns only. `store` and `date` are Hive partition columns
# (gold/store=<division>/date=<fecha>/) and are intentionally excluded here
# to avoid duplicate columns when the Glue Crawler catalogs the table.
GOLD_SCHEMA = pa.schema(
    [
        pa.field("sale_id", pa.string(), nullable=False),
        pa.field("category", pa.string(), nullable=False),
        pa.field("product", pa.string(), nullable=False),
        pa.field("quantity", pa.int32(), nullable=False),
        pa.field("price", pa.decimal128(10, 2), nullable=False),
        pa.field("total", pa.decimal128(10, 2), nullable=False),
    ]
)

MONTHS_ES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

# Date formats known per source layout (SPEC-002 "Fechas" / SPEC-007 divisions.py).
_STRPTIME_FORMATS = ("%d/%m/%Y", "%m-%d-%Y", "%Y/%m/%d", "%Y-%m-%d")


def parse_free_text_date_es(value: str) -> datetime.date | None:
    """Parses "<día> de <mes> de <año>" (Marketplace free-text date, SPEC-005)."""
    parts = value.strip().lower().split(" de ")
    if len(parts) != 3:
        return None
    day_str, month_name, year_str = parts
    month = MONTHS_ES.get(month_name.strip())
    if month is None:
        return None
    try:
        return datetime.date(int(year_str.strip()), month, int(day_str.strip()))
    except (ValueError, TypeError):
        return None


def parse_date(value: object) -> datetime.date | None:
    if isinstance(value, datetime.date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in _STRPTIME_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # ISO 8601 timestamp (Moda) or plain ISO date.
    try:
        return datetime.date.fromisoformat(text[:10])
    except ValueError:
        pass
    return parse_free_text_date_es(text)


def _parse_positive_int(value: object) -> int | None:
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _parse_positive_decimal(value: object) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result > 0 else None


def validate_and_normalize(
    raw_row: dict, division: str, stage: str, correlation_id: str
) -> tuple[dict, datetime.date]:
    """Validates a raw row against the Gold contract (SPEC-002) and normalizes it.

    Returns (gold_row, date) where gold_row matches GOLD_SCHEMA (no store/date columns)
    and date is the normalized partition value. Raises RowValidationError on any rule
    violation (SPEC-005 "Validaciones").
    """
    sale_id = raw_row.get("sale_id")
    if not sale_id or not _is_uuid(sale_id):
        sale_id = str(uuid.uuid4())

    date = parse_date(raw_row.get("date"))
    if date is None:
        raise RowValidationError(
            stage=stage,
            cause="invalid_date",
            sale_id=sale_id,
            correlation_id=correlation_id,
        )

    category = raw_row.get("category")
    if not isinstance(category, str) or not category.strip():
        raise RowValidationError(
            stage=stage,
            cause="missing_category",
            sale_id=sale_id,
            correlation_id=correlation_id,
        )

    product = raw_row.get("product")
    if not isinstance(product, str) or not product.strip():
        raise RowValidationError(
            stage=stage,
            cause="missing_product",
            sale_id=sale_id,
            correlation_id=correlation_id,
        )

    quantity = _parse_positive_int(raw_row.get("quantity"))
    if quantity is None:
        raise RowValidationError(
            stage=stage,
            cause="invalid_quantity",
            sale_id=sale_id,
            correlation_id=correlation_id,
        )

    price = _parse_positive_decimal(raw_row.get("price"))
    if price is None:
        raise RowValidationError(
            stage=stage,
            cause="invalid_price",
            sale_id=sale_id,
            correlation_id=correlation_id,
        )

    total = (price * quantity).quantize(Decimal("0.01"))

    gold_row = {
        "sale_id": sale_id,
        "category": category,
        "product": product,
        "quantity": quantity,
        "price": price,
        "total": total,
    }
    return gold_row, date


def _is_uuid(value: object) -> bool:
    try:
        uuid.UUID(str(value), version=4)
        return True
    except (ValueError, AttributeError, TypeError):
        return False
