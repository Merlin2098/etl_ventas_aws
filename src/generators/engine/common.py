from __future__ import annotations

import random
import uuid
from decimal import Decimal, ROUND_HALF_UP

from faker import Faker

from src.generators.engine.schema import SaleRecord

CORRUPTION_TYPES = (
    "missing_field",
    "invalid_type",
    "bad_date",
    "negative_value",
)
CSV_ONLY_CORRUPTION = "bad_encoding"

MONTHS_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


# Field name -> Spanish header label, covering the 8 base fields (SPEC-002)
# plus every division-specific field (SPEC-002 "Campos específicos por
# división"). Used by pdf_writer to
# render a human-readable header regardless of which fields a division emits.
FIELD_LABELS_ES: dict[str, str] = {
    "sale_id": "ID Venta",
    "date": "Fecha",
    "category": "Categoría",
    "product": "Producto",
    "quantity": "Cantidad",
    "price": "Precio",
    "currency": "Moneda",
    "status": "Estado",
    "serial_number": "N° Serie",
    "warranty_months": "Garantía (meses)",
    "manufacturer": "Fabricante",
    "model": "Modelo",
    "cashier": "Cajero",
    "loyalty_points": "Puntos Lealtad",
    "promotion_applied": "Promoción Aplicada",
    "register_number": "N° Caja",
    "size": "Talla",
    "color": "Color",
    "collection": "Colección",
    "season": "Temporada",
    "return_reason": "Motivo Devolución",
    "seller_id": "ID Vendedor",
    "marketplace_fee": "Comisión Marketplace",
    "commission_pct": "% Comisión",
    "shipping_provider": "Transportista",
}


def format_date_free_text(date) -> str:
    """Free-text date '<día> de <mes> de <año>' per SPEC-007 / SPEC-005 (Marketplace)."""
    return f"{date.day} de {MONTHS_ES[date.month]} de {date.year}"


def build_faker(seed: int | None) -> Faker:
    fake = Faker("es_ES")
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)
    return fake


def _round_price(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _generate_extra_fields(division: str, config, status: str) -> dict:
    """Division-specific fields (SPEC-002). Closed-catalog fields (ej.
    manufacturer, size) come from `config.extra_fields` (declared in
    detalle-data.yaml); free-form identifiers (ej. serial_number, seller_id)
    are generated directly here — see config.FREE_FORM_FIELDS for which
    fields fall in which bucket per division."""
    extra: dict = {name: random.choice(values) for name, values in config.extra_fields.items()}

    if division == "electronica":
        extra["serial_number"] = f"SN-{uuid.uuid4().hex[:10].upper()}"
        extra["model"] = f"MDL-{random.randint(1000, 9999)}"
    elif division == "supermercado":
        extra["register_number"] = f"CAJA-{random.randint(1, 8):02d}"
    elif division == "moda":
        # return_reason only applies to a fraction of RETURNED/EXCHANGED rows,
        # not to every row of the division (SPEC-008 #14).
        if status in ("RETURNED", "EXCHANGED") and random.random() < 0.6:
            extra["return_reason"] = random.choice(config.extra_fields["return_reason"])
        else:
            extra.pop("return_reason", None)
    elif division == "marketplace":
        extra["seller_id"] = f"SELLER-{random.randint(1000, 9999)}"

    return extra


def generate_row(division: str, date, fake: Faker, config) -> SaleRecord:
    """`config` is a DivisionConfig (see src/generators/engine/config.py), loaded
    from src/generators/detalle-data.yaml. `category`/`product` are emitted using
    a randomly chosen alias spelling to simulate inconsistent source catalogs
    (SPEC-008 #7, #9); the canonical name only drives price/product selection."""
    category_name = random.choice(list(config.categories.keys()))
    category = config.categories[category_name]
    product = random.choice(category.products)
    quantity = random.randint(1, 10)
    price = _round_price(
        Decimal(
            str(random.uniform(float(category.price_min), float(category.price_max)))
        )
    )
    category_written = random.choice(category.category_aliases)
    product_written = random.choice(category.product_aliases.get(product, [product]))
    status = random.choice(config.statuses)
    return SaleRecord(
        sale_id=str(uuid.uuid4()),
        date=date,
        category=category_written,
        product=product_written,
        quantity=quantity,
        price=price,
        currency=random.choice(config.currencies),
        status=status,
        **_generate_extra_fields(division, config, status),
    )


def maybe_corrupt(row: dict, ext: str, error_rate: float) -> dict:
    """Applies a random intentional corruption to `row` with probability `error_rate`.

    `row` is the dict form of a SaleRecord (already formatted per division), as it
    will be handed to the writer. `ext` is the division's output extension (from
    DivisionConfig.ext, src/generators/detalle-data.yaml) — used to gate the
    CSV-only corruption without hardcoding division names here. Corrupted fields
    intentionally fail Lambda-side validation (SPEC-005) so they land in
    quarantine (SPEC-002/SPEC-006).
    """
    if random.random() >= error_rate:
        return row

    choices = list(CORRUPTION_TYPES) + ([CSV_ONLY_CORRUPTION] if ext == "csv" else [])
    corruption = random.choice(choices)
    corrupted = dict(row)

    if corruption == "missing_field":
        field = random.choice(["product", "category"])
        corrupted.pop(field, None)
    elif corruption == "invalid_type":
        corrupted["quantity"] = "N/A"
    elif corruption == "bad_date":
        corrupted["date"] = "ayer"
    elif corruption == "negative_value":
        field = random.choice(["quantity", "price"])
        try:
            corrupted[field] = -abs(float(corrupted[field]))
        except (TypeError, ValueError):
            corrupted[field] = -1
    elif corruption == CSV_ONLY_CORRUPTION:
        corrupted["product"] = f"{corrupted.get('product', 'Producto')}\udcff"

    return corrupted
