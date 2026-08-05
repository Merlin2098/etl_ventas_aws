from __future__ import annotations

import datetime
from pathlib import Path

from src.generators.engine.common import build_faker, generate_row, maybe_corrupt
from src.generators.engine.config import DIVISIONS, DIVISION_ORDER


def test_maybe_corrupt_never_changes_row_at_zero_error_rate():
    row = {
        "sale_id": "x",
        "date": "01/08/2026",
        "category": "Audio",
        "product": "P",
        "quantity": 1,
        "price": 10,
        "currency": "PEN",
        "status": "PENDING",
    }
    assert maybe_corrupt(row, "csv", 0.0) == row


def test_maybe_corrupt_always_changes_row_at_full_error_rate():
    row = {
        "sale_id": "x",
        "date": "01/08/2026",
        "category": "Audio",
        "product": "P",
        "quantity": 1,
        "price": 10,
        "currency": "PEN",
        "status": "PENDING",
    }
    corrupted = [maybe_corrupt(dict(row), "csv", 1.0) for _ in range(20)]
    assert any(c != row for c in corrupted)


def test_divisions_cover_expected_four():
    assert set(DIVISIONS.keys()) == {
        "electronica",
        "supermercado",
        "moda",
        "marketplace",
    }
    assert DIVISION_ORDER == [
        "electronica",
        "supermercado",
        "moda",
        "marketplace",
    ]


def test_generate_sales_cli_writes_four_files_without_upload(tmp_path: Path):
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "data_generator" / "generate_sales.py"),
            "--division",
            "all",
            "--date",
            "2026-08-01",
            "--rows",
            "5",
            "--no-upload",
            "--seed",
            "1",
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    assert result.returncode == 0, result.stderr

    expected_files = {
        "electronica_2026-08-01.csv",
        "supermercado_2026-08-01.xlsx",
        "moda_2026-08-01.json",
        "marketplace_2026-08-01.pdf",
    }
    partition_dir = tmp_path / "date=2026-08-01"
    actual_files = {p.name for p in partition_dir.iterdir()}
    assert expected_files == actual_files


def test_generate_sales_cli_week_writes_seven_partition_folders(tmp_path: Path):
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "data_generator" / "generate_sales.py"),
            "--division",
            "electronica",
            "--date",
            "2026-08-07",
            "--week",
            "--rows",
            "5",
            "--no-upload",
            "--seed",
            "1",
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    assert result.returncode == 0, result.stderr

    expected_partitions = {f"date=2026-08-0{d}" for d in range(1, 8)}
    actual_partitions = {p.name for p in tmp_path.iterdir()}
    assert expected_partitions == actual_partitions


def test_generate_row_populates_only_its_own_division_extra_fields():
    """SPEC-009 §2: division-specific fields (ej. serial_number for electronica)
    must be set only for their own division, None for the other three."""
    date = datetime.date(2026, 8, 1)
    fake = build_faker(1)

    all_extra_fields = {
        "serial_number",
        "warranty_months",
        "manufacturer",
        "model",
        "cashier",
        "loyalty_points",
        "promotion_applied",
        "register_number",
        "size",
        "color",
        "collection",
        "season",
        "return_reason",
        "seller_id",
        "marketplace_fee",
        "commission_pct",
        "shipping_provider",
    }
    own_fields = {
        "electronica": {"serial_number", "warranty_months", "manufacturer", "model"},
        "supermercado": {"cashier", "loyalty_points", "promotion_applied", "register_number"},
        "moda": {"size", "color", "collection", "season", "return_reason"},
        "marketplace": {"seller_id", "marketplace_fee", "commission_pct", "shipping_provider"},
    }

    for division in DIVISION_ORDER:
        config = DIVISIONS[division]
        record = generate_row(division, date, fake, config)
        populated = {
            field for field in all_extra_fields if getattr(record, field) is not None
        }
        # return_reason is optional even within moda (only some RETURNED/EXCHANGED
        # rows get one), so it can't be asserted present on every single row.
        assert populated <= own_fields[division]
        assert populated & (all_extra_fields - own_fields[division]) == set()


def test_generate_division_electronica_csv_header_matches_its_own_fieldnames(tmp_path: Path):
    """SPEC-009 §2: the generated CSV for a division must expose only that
    division's own columns (base + its extra_fields), not a blank column for
    every other division's fields. CSV is the one format easy to assert on as
    plain text; xlsx/pdf/json are covered indirectly by config.fieldnames
    (test_generate_row_populates_only_its_own_division_extra_fields) and by
    the marketplace parser round-trip test (tests/unit/test_parsers.py)."""
    from scripts.data_generator.generate_sales import generate_division

    output_path = generate_division(
        division="electronica",
        date=datetime.date(2026, 8, 1),
        rows=5,
        error_rate=0.0,
        output_dir=tmp_path,
        upload=False,
        seed=1,
    )
    header = output_path.read_text(encoding="utf-8").splitlines()[0]
    assert set(header.split(",")) == set(DIVISIONS["electronica"].fieldnames)
