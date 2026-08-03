from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

FIELDNAMES = ["sale_id", "date", "category", "product", "quantity", "price", "currency", "status"]
HEADER_LABELS = ["ID Venta", "Fecha", "Categoría", "Producto", "Cantidad", "Precio", "Moneda", "Estado"]


def write_pdf(rows: list[dict], output_path: Path) -> None:
    doc = SimpleDocTemplate(str(output_path), pagesize=letter)
    data = [HEADER_LABELS]
    for row in rows:
        data.append([str(row.get(field, "")) for field in FIELDNAMES])

    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dddddd")),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    doc.build([table])
