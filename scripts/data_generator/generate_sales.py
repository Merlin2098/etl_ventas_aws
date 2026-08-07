from __future__ import annotations

import argparse
import datetime
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.generators.engine.common import (  # noqa: E402
    build_faker,
    generate_row,
    maybe_corrupt,
)
from src.generators.engine.config import DIVISION_ORDER, DIVISIONS  # noqa: E402
from src.generators.engine.uploader import upload_to_bronze  # noqa: E402


def generate_division(
    division: str,
    date: datetime.date,
    rows: int,
    error_rate: float,
    output_dir: Path,
    upload: bool,
    seed: int | None,
) -> Path:
    config = DIVISIONS[division]
    fake = build_faker(seed)

    records = []
    for _ in range(rows):
        record = generate_row(division, date, fake, config)
        row = asdict(record)
        row["date"] = config.date_formatter(record.date)
        row = maybe_corrupt(row, config.ext, error_rate)
        # SaleRecord carries every division's optional fields (schema.py); keep
        # only this division's own columns (config.fieldnames, SPEC-002) so
        # e.g. Electrónica's file doesn't show a blank seller_id column.
        row = {field: row.get(field) for field in config.fieldnames}
        records.append(row)

    date_str = date.isoformat()
    partition_dir = output_dir / f"date={date_str}" / division
    partition_dir.mkdir(parents=True, exist_ok=True)
    output_path = partition_dir / f"{division}_{date_str}.{config.ext}"
    config.writer(records, config.fieldnames, output_path)

    print(f"[{division}] generated {rows} rows -> {output_path}")

    if upload:
        uri = upload_to_bronze(output_path, division, date, config.ext)
        print(f"[{division}] uploaded -> {uri}")

    return output_path


def prompt_date(label: str, *, allow_blank: bool = False) -> datetime.date | None:
    """Prompts on stdin until a valid YYYY-MM-DD date is entered. If
    `allow_blank`, an empty line returns None (caller decides the default)."""
    while True:
        raw = input(label).strip()
        if not raw and allow_blank:
            return None
        try:
            return datetime.date.fromisoformat(raw)
        except ValueError:
            print(f"Fecha inválida: {raw!r} — usá el formato YYYY-MM-DD.")


def prompt_dates() -> list[datetime.date]:
    """Interactively asks for a start date and an optional end date, returning
    every date in that range (inclusive, oldest first). A blank end date
    generates a single day."""
    start = prompt_date("Fecha inicio (YYYY-MM-DD): ")
    end = prompt_date(
        "Fecha fin (YYYY-MM-DD, Enter para un solo día): ", allow_blank=True
    )
    if end is None:
        return [start]
    if end < start:
        start, end = end, start
    return date_range(start, end)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic RetailCorp sales files."
    )
    parser.add_argument(
        "--division",
        default="all",
        choices=[*DIVISION_ORDER, "all"],
        help="Division to generate, or 'all' to run the five in sequence.",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=350,
        help="Number of rows to generate (200-500 typical).",
    )
    parser.add_argument(
        "--error-rate",
        type=float,
        default=0.05,
        help="Fraction of rows with intentional corruption (0.0-1.0).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "data"),
        help="Local directory for generated files.",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Optional seed for reproducibility."
    )

    upload_group = parser.add_mutually_exclusive_group()
    upload_group.add_argument("--upload", dest="upload", action="store_true")
    upload_group.add_argument("--no-upload", dest="upload", action="store_false")
    parser.set_defaults(upload=False)

    return parser.parse_args(argv)


def date_range(start: datetime.date, end: datetime.date) -> list[datetime.date]:
    """Every date from `start` to `end`, inclusive, oldest first."""
    days = (end - start).days
    return [start + datetime.timedelta(days=offset) for offset in range(days + 1)]


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    dates = prompt_dates()

    divisions = DIVISION_ORDER if args.division == "all" else [args.division]
    for date in dates:
        for division in divisions:
            # A single base seed reused verbatim across every (date, division) would
            # make every day's file identical. Derive a per-run seed from it instead,
            # so --seed still gives reproducible-but-distinct output across a range.
            seed = (
                None
                if args.seed is None
                else args.seed + date.toordinal() + hash(division) % 1000
            )
            generate_division(
                division=division,
                date=date,
                rows=args.rows,
                error_rate=args.error_rate,
                output_dir=output_dir,
                upload=args.upload,
                seed=seed,
            )


if __name__ == "__main__":
    main()
