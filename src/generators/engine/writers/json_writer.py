from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path


def _default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_json(rows: list[dict], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2, default=_default)
