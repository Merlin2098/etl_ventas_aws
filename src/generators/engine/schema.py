from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal


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
