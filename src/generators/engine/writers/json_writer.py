from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path


def _default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_json(rows: list[dict], fieldnames: list[str], output_path: Path) -> None:
    """`fieldnames` is accepted for signature parity with the other writers
    (see config.FORMAT_WRITERS) but unused: JSON already reflects whatever
    keys are present on each row, moda has no closed set of extra fields to
    filter down to."""
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2, default=_default)
