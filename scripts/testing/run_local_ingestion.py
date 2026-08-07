# Exercises the real ingestion pipeline (parser -> normalize_silver -> validate_and_normalize)
# against a file already on disk, without touching AWS. Mirrors handler_base's
# process_event and transform_handler_base's process_transform_event, but reads/writes
# local files instead of S3, so it validates the same business logic that runs inside
# each Lambda (ingestion + transform).
# Usage: python scripts/testing/run_local_ingestion.py
#   (runs all 4 divisions against data/<division>_<date>.<ext>, defaulting to today)
# Usage: python scripts/testing/run_local_ingestion.py --division electronica --file data/electronica_2026-08-02.csv
# Usage: python scripts/testing/run_local_ingestion.py --division electronica --file data/electronica_2026-08-02.csv --stage silver
from __future__ import annotations

import argparse
import datetime
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.generators.engine.config import DIVISION_ORDER, DIVISIONS  # noqa: E402
from src.lambda_ingestion.common.errors import FileParseError, RowValidationError  # noqa: E402
from src.lambda_ingestion.common.parser_base import SalesParser  # noqa: E402
from src.lambda_ingestion.common.schema import (  # noqa: E402
    GOLD_SCHEMA,
    SILVER_SCHEMA,
    normalize_silver,
    parse_date,
    validate_and_normalize,
)
from src.lambda_ingestion.electronica.parser import CsvSalesParser  # noqa: E402
from src.lambda_ingestion.marketplace.parser import PdfSalesParser  # noqa: E402
from src.lambda_ingestion.moda.parser import JsonSalesParser  # noqa: E402
from src.lambda_ingestion.supermercado.parser import ExcelSalesParser  # noqa: E402

PARSERS: dict[str, type[SalesParser]] = {
    "electronica": CsvSalesParser,
    "supermercado": ExcelSalesParser,
    "moda": JsonSalesParser,
    "marketplace": PdfSalesParser,
}


def _default_bronze_path(division: str, date: datetime.date, data_dir: Path) -> Path:
    """Resolves data/date=<date>/<division>/<division>_<date>.<ext>, matching
    generate_sales.py's own output naming, so `--division all` can locate each
    Bronze file without the caller having to pass --file explicitly."""
    ext = DIVISIONS[division].ext
    date_str = date.isoformat()
    return data_dir / f"date={date_str}" / division / f"{division}_{date_str}.{ext}"


def _default(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)


def _write_json(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, default=_default, indent=2), encoding="utf-8")


def run_bronze_to_silver(
    division: str, file_path: Path, out_dir: Path, correlation_id: str
) -> dict[datetime.date, list[dict]]:
    """Parses the Bronze file and normalizes it to Silver rows, writing one local
    Parquet file per date partition. Returns the in-memory silver rows keyed by date
    so `run_silver_to_gold` can chain off them without re-reading from disk."""
    parser = PARSERS[division]()
    raw_bytes = file_path.read_bytes()

    try:
        raw_rows = list(parser.parse(raw_bytes))
    except FileParseError as exc:
        print(f"[{division}] FILE PARSE FAILED: {exc.cause}")
        return {}

    print(f"[{division}] parsed {len(raw_rows)} raw rows from {file_path}")

    silver_rows: dict[datetime.date, list[dict]] = {}
    errors: dict[datetime.date, list[dict]] = {}
    for raw_row in raw_rows:
        try:
            silver_row, date = normalize_silver(raw_row, division=division, correlation_id=correlation_id)
            silver_rows.setdefault(date, []).append(silver_row)
        except RowValidationError as exc:
            error_date = parse_date(raw_row.get("date")) or datetime.date.today()
            errors.setdefault(error_date, []).append({"row": raw_row, "error": exc.cause})

    total_silver = sum(len(v) for v in silver_rows.values())
    total_errors = sum(len(v) for v in errors.values())
    print(f"[{division}] silver_rows={total_silver} quarantine_rows={total_errors}")

    silver_dir = out_dir / "silver"
    silver_dir.mkdir(parents=True, exist_ok=True)
    for date, rows in silver_rows.items():
        out_path = silver_dir / f"{division}_{date.isoformat()}.parquet"
        table = pa.Table.from_pylist(rows, schema=SILVER_SCHEMA)
        pq.write_table(table, out_path)
        print(f"[{division}] wrote {out_path} ({len(rows)} rows)")

    quarantine_dir = out_dir / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    for date, error_rows in errors.items():
        out_path = quarantine_dir / f"silver_{division}_{date.isoformat()}.json"
        _write_json(out_path, error_rows)
        print(f"[{division}] wrote {out_path} ({len(error_rows)} rows)")

    return silver_rows


def run_silver_to_gold(
    division: str, silver_rows: dict[datetime.date, list[dict]], out_dir: Path, correlation_id: str
) -> None:
    """Reads Silver rows (already in memory, or re-read from local Parquet) and
    validates/normalizes them to Gold, writing local Gold Parquet output (matching
    write_gold's real format) and quarantine JSON (matching write_quarantine's)."""
    gold_dir = out_dir / "gold"
    gold_dir.mkdir(parents=True, exist_ok=True)
    quarantine_dir = out_dir / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    for date, rows in silver_rows.items():
        valid_rows: list[dict] = []
        errors: list[dict] = []
        for silver_row in rows:
            # `date` is a Hive partition column (silver/store=<division>/date=<fecha>/...),
            # not a column inside the Silver Parquet file, so it's injected back from the
            # partition key here — mirrors how transform_handler_base.py reads it from the
            # S3 key rather than from each row.
            row_with_date = {**silver_row, "date": date}
            try:
                gold_row, _ = validate_and_normalize(
                    row_with_date, division=division, stage="validate", correlation_id=correlation_id
                )
                valid_rows.append(gold_row)
            except RowValidationError as exc:
                errors.append({"row": silver_row, "error": exc.cause})

        print(f"[{division}] {date.isoformat()}: gold_rows={len(valid_rows)} quarantine_rows={len(errors)}")

        if valid_rows:
            out_path = gold_dir / f"{division}_{date.isoformat()}.parquet"
            table = pa.Table.from_pylist(valid_rows, schema=GOLD_SCHEMA)
            pq.write_table(table, out_path)
            print(f"[{division}] wrote {out_path} ({len(valid_rows)} rows)")

        if errors:
            out_path = quarantine_dir / f"gold_{division}_{date.isoformat()}.json"
            _write_json(out_path, errors)
            print(f"[{division}] wrote {out_path} ({len(errors)} rows)")


def run(division: str, file_path: Path, out_dir: Path, stage: str) -> int:
    correlation_id = str(uuid.uuid4())

    silver_rows = run_bronze_to_silver(division, file_path, out_dir, correlation_id)
    if not silver_rows and stage != "silver":
        return 1

    if stage in ("gold", "both"):
        run_silver_to_gold(division, silver_rows, out_dir, correlation_id)

    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one or all divisions' parser + Silver/Gold normalization locally, no AWS involved."
    )
    parser.add_argument(
        "--division",
        default="all",
        choices=[*sorted(PARSERS), "all"],
        help="Division to run, or 'all' (default) to run the 4 in sequence.",
    )
    parser.add_argument(
        "--file",
        help="Path to a Bronze-format sample file. Only valid with a single --division; "
        "if omitted, defaults to data/<division>_<date>.<ext> (see --date).",
    )
    parser.add_argument(
        "--date",
        default=datetime.date.today().isoformat(),
        help="Business date (YYYY-MM-DD) used to resolve the default --file path. Defaults to today.",
    )
    parser.add_argument(
        "--stage",
        default="both",
        choices=["silver", "gold", "both"],
        help="Which stage(s) to run: 'silver' only, 'gold' (implies running silver first in-memory), or 'both' (default).",
    )
    parser.add_argument(
        "--out-dir",
        default=str(REPO_ROOT / "data" / "local_run"),
        help="Where to write local silver/gold/quarantine output.",
    )
    args = parser.parse_args(argv)

    if args.file and args.division == "all":
        parser.error("--file requires a specific --division, not 'all'.")

    return args


def main() -> None:
    args = parse_args()
    date = datetime.date.fromisoformat(args.date)
    out_dir = Path(args.out_dir)
    divisions = DIVISION_ORDER if args.division == "all" else [args.division]

    exit_code = 0
    for division in divisions:
        file_path = Path(args.file) if args.file else _default_bronze_path(division, date, REPO_ROOT / "data")
        if not file_path.exists():
            print(f"[{division}] SKIPPED: Bronze file not found at {file_path}")
            exit_code = 1
            continue
        division_exit_code = run(division, file_path, out_dir, args.stage)
        exit_code = exit_code or division_exit_code

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
