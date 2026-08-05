from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from src.generators.engine.common import FIELD_LABELS_ES


def write_pdf(rows: list[dict], fieldnames: list[str], output_path: Path) -> None:
    header_labels = [FIELD_LABELS_ES[field] for field in fieldnames]
    doc = SimpleDocTemplate(str(output_path), pagesize=letter)
    data = [header_labels]
    for row in rows:
        data.append([str(row.get(field, "")) for field in fieldnames])

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
