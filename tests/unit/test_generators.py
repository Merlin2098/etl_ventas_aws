from __future__ import annotations

from pathlib import Path

from src.generators.common import maybe_corrupt
from src.generators.divisions import DIVISIONS, DIVISION_ORDER


def test_maybe_corrupt_never_changes_row_at_zero_error_rate():
    row = {
        "sale_id": "x",
        "date": "01/08/2026",
        "category": "Audio",
        "product": "P",
        "quantity": 1,
        "price": 10,
    }
    assert maybe_corrupt(row, "electronica", 0.0) == row


def test_maybe_corrupt_always_changes_row_at_full_error_rate():
    row = {
        "sale_id": "x",
        "date": "01/08/2026",
        "category": "Audio",
        "product": "P",
        "quantity": 1,
        "price": 10,
    }
    corrupted = [maybe_corrupt(dict(row), "electronica", 1.0) for _ in range(20)]
    assert any(c != row for c in corrupted)


def test_divisions_cover_expected_five():
    assert set(DIVISIONS.keys()) == {
        "electronica",
        "supermercado",
        "moda",
        "hogar",
        "marketplace",
    }
    assert DIVISION_ORDER == [
        "electronica",
        "supermercado",
        "moda",
        "hogar",
        "marketplace",
    ]


def test_generate_sales_cli_writes_five_files_without_upload(tmp_path: Path):
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "generate_sales.py"),
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
        "hogar_2026-08-01.csv",
        "marketplace_2026-08-01.pdf",
    }
    actual_files = {p.name for p in tmp_path.iterdir()}
    assert expected_files == actual_files
