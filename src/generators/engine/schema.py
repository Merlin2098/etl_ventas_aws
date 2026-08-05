from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class SaleRecord:
    sale_id: str
    date: datetime.date
    category: str
    product: str
    quantity: int
    price: Decimal
    currency: str
    status: str

    # Electrónica (SPEC-009 §2). None for every other division.
    serial_number: Optional[str] = None
    warranty_months: Optional[int] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None

    # Supermercado (SPEC-009 §2). None for every other division.
    cashier: Optional[str] = None
    loyalty_points: Optional[int] = None
    promotion_applied: Optional[bool] = None
    register_number: Optional[str] = None

    # Moda (SPEC-009 §2). None for every other division; return_reason is also
    # optional within Moda (only set for a fraction of RETURNED/EXCHANGED rows).
    size: Optional[str] = None
    color: Optional[str] = None
    collection: Optional[str] = None
    season: Optional[str] = None
    return_reason: Optional[str] = None

    # Marketplace (SPEC-009 §2). None for every other division.
    seller_id: Optional[str] = None
    marketplace_fee: Optional[Decimal] = None
    commission_pct: Optional[Decimal] = None
    shipping_provider: Optional[str] = None
