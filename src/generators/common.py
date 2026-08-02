from __future__ import annotations

import random
import uuid
from decimal import Decimal, ROUND_HALF_UP

from faker import Faker

from src.generators.schema import SaleRecord

# category -> (products, price_min, price_max)
CATALOG: dict[str, dict[str, tuple[list[str], Decimal, Decimal]]] = {
    "electronica": {
        "Audio": (
            ["Audífonos Bluetooth", "Parlante Portátil", "Barra de Sonido"],
            Decimal("15"),
            Decimal("300"),
        ),
        "Computación": (
            ["Laptop 14''", "Mouse Inalámbrico", "Teclado Mecánico"],
            Decimal("20"),
            Decimal("1200"),
        ),
        "Telefonía": (
            ["Smartphone Gama Media", "Funda Protectora", "Cargador Rápido"],
            Decimal("10"),
            Decimal("900"),
        ),
    },
    "supermercado": {
        "Almacén": (
            ["Arroz 1kg", "Aceite de Girasol", "Fideos Largos"],
            Decimal("1"),
            Decimal("8"),
        ),
        "Lácteos": (
            ["Leche Entera 1L", "Yogur Natural", "Queso Fresco"],
            Decimal("1"),
            Decimal("12"),
        ),
        "Bebidas": (
            ["Agua Mineral 500ml", "Gaseosa Cola 2L", "Jugo de Naranja"],
            Decimal("1"),
            Decimal("10"),
        ),
    },
    "moda": {
        "Calzado": (
            ["Zapatillas Urbanas", "Botas de Cuero", "Sandalias"],
            Decimal("20"),
            Decimal("150"),
        ),
        "Ropa": (
            ["Polera Básica", "Jean Slim Fit", "Chaqueta de Invierno"],
            Decimal("10"),
            Decimal("120"),
        ),
        "Accesorios": (
            ["Gorra", "Cinturón de Cuero", "Bufanda"],
            Decimal("5"),
            Decimal("60"),
        ),
    },
    "hogar": {
        "Cocina": (
            ["Sartén Antiadherente", "Juego de Ollas", "Licuadora"],
            Decimal("10"),
            Decimal("150"),
        ),
        "Decoración": (
            ["Cojín Decorativo", "Lámpara de Mesa", "Espejo de Pared"],
            Decimal("8"),
            Decimal("100"),
        ),
        "Limpieza": (
            ["Detergente 1L", "Escoba", "Trapero"],
            Decimal("2"),
            Decimal("25"),
        ),
    },
    "marketplace": {
        "Deportes": (
            ["Balón de Fútbol", "Bicicleta Urbana", "Mancuernas 5kg"],
            Decimal("10"),
            Decimal("400"),
        ),
        "Juguetería": (
            ["Set de Bloques", "Muñeca Articulada", "Auto a Control Remoto"],
            Decimal("5"),
            Decimal("80"),
        ),
        "Mascotas": (
            ["Alimento para Perro 3kg", "Correa Ajustable", "Cama para Gato"],
            Decimal("5"),
            Decimal("70"),
        ),
    },
}

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


def generate_row(division: str, date, fake: Faker) -> SaleRecord:
    categories = CATALOG[division]
    category = random.choice(list(categories.keys()))
    products, price_min, price_max = categories[category]
    product = random.choice(products)
    quantity = random.randint(1, 10)
    price = _round_price(
        Decimal(str(random.uniform(float(price_min), float(price_max))))
    )
    return SaleRecord(
        sale_id=str(uuid.uuid4()),
        date=date,
        category=category,
        product=product,
        quantity=quantity,
        price=price,
    )


def maybe_corrupt(row: dict, division: str, error_rate: float) -> dict:
    """Applies a random intentional corruption to `row` with probability `error_rate`.

    `row` is the dict form of a SaleRecord (already formatted per division), as it
    will be handed to the writer. Corrupted fields intentionally fail Lambda-side
    validation (SPEC-005) so they land in quarantine (SPEC-002/SPEC-006).
    """
    if random.random() >= error_rate:
        return row

    is_csv_division = division in ("electronica", "hogar")
    choices = list(CORRUPTION_TYPES) + (
        [CSV_ONLY_CORRUPTION] if is_csv_division else []
    )
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
