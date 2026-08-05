from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook


def write_excel(rows: list[dict], fieldnames: list[str], output_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "ventas"
    sheet.append(fieldnames)
    for row in rows:
        sheet.append([row.get(field, "") for field in fieldnames])
    workbook.save(output_path)
