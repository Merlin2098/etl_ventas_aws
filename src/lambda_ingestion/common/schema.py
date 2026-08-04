from __future__ import annotations

import datetime
import uuid
from decimal import Decimal, InvalidOperation

import pyarrow as pa

from .errors import RowValidationError

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
        pa.field("currency", pa.string(), nullable=False),
        pa.field("status", pa.string(), nullable=False),
    ]
)

# Silver Parquet columns. Same partition scheme as Gold (silver/store=<division>/date=<fecha>/)
# but without `total` (recomputed only in Gold) and with `sale_id` nullable (passthrough from
# the source row if present; generation of a missing sale_id is a Gold-only concern).
SILVER_SCHEMA = pa.schema(
    [
        pa.field("sale_id", pa.string(), nullable=True),
        pa.field("category", pa.string(), nullable=False),
        pa.field("product", pa.string(), nullable=False),
        pa.field("quantity", pa.int32(), nullable=False),
        pa.field("price", pa.decimal128(10, 2), nullable=False),
        pa.field("currency", pa.string(), nullable=False),
        pa.field("status", pa.string(), nullable=False),
    ]
)

# Applied when the source row omits currency/status or sends an unrecognized
# value — kept as passthrough metadata (no cross-division homologation yet,
# SPEC-008 #5/#10 explicitly defer that to a later stage).
DEFAULT_CURRENCY = "PEN"
DEFAULT_STATUS = "UNKNOWN"

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


def _normalize_core(
    raw_row: dict, division: str, stage: str, correlation_id: str
) -> tuple[dict, datetime.date]:
    """Shared field-level validation/normalization for both Silver and Gold stages
    (date, category, product, quantity, price, currency, status). Does not touch
    `sale_id` or `total` — those are resolved by each stage's own entry point
    (see `normalize_silver` and `validate_and_normalize`).

    Raises RowValidationError on any rule violation (SPEC-005 "Validaciones").
    Accepts either a raw parser row or an already-typed Silver row: `parse_date`
    handles both `datetime.date` and string inputs, making this idempotent.
    """
    sale_id = raw_row.get("sale_id") or ""

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

    currency = raw_row.get("currency")
    currency = currency.strip().upper() if isinstance(currency, str) and currency.strip() else DEFAULT_CURRENCY

    status = raw_row.get("status")
    status = status.strip().upper() if isinstance(status, str) and status.strip() else DEFAULT_STATUS

    row = {
        "category": category,
        "product": product,
        "quantity": quantity,
        "price": price,
        "currency": currency,
        "status": status,
    }
    return row, date


def normalize_silver(
    raw_row: dict, division: str, correlation_id: str
) -> tuple[dict, datetime.date]:
    """Silver stage: field-level validation/normalization only. Does not generate a
    missing `sale_id` (kept nullable/passthrough) and does not compute `total`
    (both are Gold-only concerns, see `validate_and_normalize`).

    Returns (silver_row, date) where silver_row matches SILVER_SCHEMA.
    """
    row, date = _normalize_core(raw_row, division, stage="silver_normalize", correlation_id=correlation_id)
    sale_id = raw_row.get("sale_id")
    row["sale_id"] = sale_id if isinstance(sale_id, str) else None
    return row, date


def validate_and_normalize(
    raw_row: dict, division: str, stage: str, correlation_id: str
) -> tuple[dict, datetime.date]:
    """Validates a row against the Gold contract (SPEC-002) and normalizes it.

    Accepts either a raw parser row or an already-normalized Silver row (a strict
    subset of a raw row's fields) — see `_normalize_core`.

    Returns (gold_row, date) where gold_row matches GOLD_SCHEMA (no store/date columns)
    and date is the normalized partition value. Raises RowValidationError on any rule
    violation (SPEC-005 "Validaciones").
    """
    row, date = _normalize_core(raw_row, division, stage, correlation_id)

    sale_id = raw_row.get("sale_id")
    if not sale_id or not _is_uuid(sale_id):
        sale_id = str(uuid.uuid4())

    total = (row["price"] * row["quantity"]).quantize(Decimal("0.01"))

    gold_row = {
        "sale_id": sale_id,
        "category": row["category"],
        "product": row["product"],
        "quantity": row["quantity"],
        "price": row["price"],
        "total": total,
        "currency": row["currency"],
        "status": row["status"],
    }
    return gold_row, date


def _is_uuid(value: object) -> bool:
    try:
        uuid.UUID(str(value), version=4)
        return True
    except (ValueError, AttributeError, TypeError):
        return False
