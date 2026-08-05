from __future__ import annotations

import csv
from pathlib import Path


def write_csv(rows: list[dict], fieldnames: list[str], output_path: Path) -> None:
    with output_path.open(
        "w", newline="", encoding="utf-8", errors="surrogateescape"
    ) as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
