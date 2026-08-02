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
        record = generate_row(division, date, fake, config.categories)
        row = asdict(record)
        row["date"] = config.date_formatter(record.date)
        row = maybe_corrupt(row, config.ext, error_rate)
        records.append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = date.isoformat()
    output_path = output_dir / f"{division}_{date_str}.{config.ext}"
    config.writer(records, output_path)

    print(f"[{division}] generated {rows} rows -> {output_path}")

    if upload:
        uri = upload_to_bronze(output_path, division, date, config.ext)
        print(f"[{division}] uploaded -> {uri}")

    return output_path


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
        "--date",
        default=datetime.date.today().isoformat(),
        help="Business date (YYYY-MM-DD). Defaults to today.",
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


def main() -> None:
    args = parse_args()
    date = datetime.date.fromisoformat(args.date)
    output_dir = Path(args.output_dir)

    divisions = DIVISION_ORDER if args.division == "all" else [args.division]
    for division in divisions:
        generate_division(
            division=division,
            date=date,
            rows=args.rows,
            error_rate=args.error_rate,
            output_dir=output_dir,
            upload=args.upload,
            seed=args.seed,
        )


if __name__ == "__main__":
    main()
