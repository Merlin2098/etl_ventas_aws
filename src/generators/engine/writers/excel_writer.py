from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

FIELDNAMES = ["sale_id", "date", "category", "product", "quantity", "price", "currency", "status"]


def write_excel(rows: list[dict], output_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "ventas"
    sheet.append(FIELDNAMES)
    for row in rows:
        sheet.append([row.get(field, "") for field in FIELDNAMES])
    workbook.save(output_path)
