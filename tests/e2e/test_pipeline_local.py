# End-to-end test of the full pipeline (generate -> Bronze -> Silver -> Gold/quarantine)
# against locally generated synthetic data, entirely offline (no AWS). Reuses the same
# generator and pipeline functions the demo's CLI scripts use — this test does not
# reimplement pipeline logic, it drives the real code path with a fixed seed so runs
# are reproducible.
from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from scripts.data_generator.generate_sales import generate_division
from scripts.testing.run_local_ingestion import run_bronze_to_silver, run_silver_to_gold
from src.generators.engine.config import DIVISION_ORDER, DIVISIONS
from src.lambda_ingestion.common.schema import GOLD_SCHEMA, SILVER_SCHEMA

TEST_DATE = datetime.date(2026, 8, 2)
SEED = 12345
ROWS_PER_DIVISION = 350
ERROR_RATE = 0.05


@pytest.fixture(scope="module")
def pipeline_run(tmp_path_factory):
    """Generates fresh Bronze files for all 4 divisions with a fixed seed, then
    runs each through Bronze -> Silver -> Gold/quarantine locally. Module-scoped
    since generation + full pipeline run is expensive to repeat per test."""
    bronze_dir = tmp_path_factory.mktemp("bronze")
    out_dir = tmp_path_factory.mktemp("local_run")

    results = {}
    for division in DIVISION_ORDER:
        bronze_path = generate_division(
            division=division,
            date=TEST_DATE,
            rows=ROWS_PER_DIVISION,
            error_rate=ERROR_RATE,
            output_dir=bronze_dir,
            upload=False,
            seed=SEED,
        )
        silver_rows = run_bronze_to_silver(
            division, bronze_path, out_dir, correlation_id=f"e2e-{division}"
        )
        run_silver_to_gold(division, silver_rows, out_dir, correlation_id=f"e2e-{division}")
        results[division] = {"bronze_path": bronze_path, "silver_rows": silver_rows}

    return {"out_dir": out_dir, "divisions": results}


@pytest.mark.parametrize("division", DIVISION_ORDER)
def test_bronze_file_was_generated(pipeline_run, division):
    bronze_path = pipeline_run["divisions"][division]["bronze_path"]
    assert bronze_path.exists()
    assert bronze_path.stat().st_size > 0


@pytest.mark.parametrize("division", DIVISION_ORDER)
def test_silver_parquet_matches_schema_and_has_rows(pipeline_run, division):
    silver_path = pipeline_run["out_dir"] / "silver" / f"{division}_{TEST_DATE.isoformat()}.parquet"
    assert silver_path.exists(), f"no Silver output written for {division}"

    table = pq.read_table(silver_path)
    assert table.schema.equals(SILVER_SCHEMA)
    assert table.num_rows > 0


@pytest.mark.parametrize("division", DIVISION_ORDER)
def test_gold_parquet_matches_schema_and_has_rows(pipeline_run, division):
    gold_path = pipeline_run["out_dir"] / "gold" / f"{division}_{TEST_DATE.isoformat()}.parquet"
    assert gold_path.exists(), f"no Gold output written for {division}"

    table = pq.read_table(gold_path)
    assert table.schema.equals(GOLD_SCHEMA)
    assert table.num_rows > 0


@pytest.mark.parametrize("division", DIVISION_ORDER)
def test_row_counts_are_consistent_across_stages(pipeline_run, division):
    """Every row that reaches Silver must reach Gold too: the Gold-stage checks
    are the same field rules Silver already enforced (SPEC-005), so nothing should
    additionally fail once a row is Silver-shaped."""
    silver_rows = pipeline_run["divisions"][division]["silver_rows"]
    silver_count = sum(len(rows) for rows in silver_rows.values())

    gold_path = pipeline_run["out_dir"] / "gold" / f"{division}_{TEST_DATE.isoformat()}.parquet"
    gold_count = pq.read_table(gold_path).num_rows

    assert gold_count == silver_count
    # Sanity bound: with ERROR_RATE=0.05, most but not all rows should survive Silver.
    assert 0 < silver_count < ROWS_PER_DIVISION


@pytest.mark.parametrize("division", DIVISION_ORDER)
def test_gold_total_equals_price_times_quantity(pipeline_run, division):
    gold_path = pipeline_run["out_dir"] / "gold" / f"{division}_{TEST_DATE.isoformat()}.parquet"
    rows = pq.read_table(gold_path).to_pylist()
    assert rows, f"no Gold rows for {division}"

    for row in rows:
        expected_total = (Decimal(row["price"]) * row["quantity"]).quantize(Decimal("0.01"))
        assert Decimal(row["total"]) == expected_total


@pytest.mark.parametrize("division", DIVISION_ORDER)
def test_gold_output_has_no_mojibake_in_text_fields(pipeline_run, division):
    """Regression guard: a single intentionally-corrupted row (bad_encoding, CSV-only)
    must not corrupt accented characters (tildes/ñ) in every other row of the file —
    see the per-line decode fix in CsvSalesParser."""
    gold_path = pipeline_run["out_dir"] / "gold" / f"{division}_{TEST_DATE.isoformat()}.parquet"
    rows = pq.read_table(gold_path).to_pylist()

    for row in rows:
        for field in ("category", "product"):
            value = row[field]
            assert "�" not in value, f"mojibake found in {division}.{field}: {value!r}"


def test_all_known_category_aliases_appear_uncorrupted_in_gold(pipeline_run):
    """Cross-checks every category alias declared in detalle-data.yaml against Gold
    output: each alias that contains an accented character must appear byte-for-byte
    as declared, never as a mangled variant."""
    accented_aliases = set()
    for division_config in DIVISIONS.values():
        for category_config in division_config.categories.values():
            for alias in category_config.category_aliases:
                if any(c in alias for c in "áéíóúñÁÉÍÓÚÑ"):
                    accented_aliases.add(alias)

    assert accented_aliases, "expected at least one accented category alias in the fixture data"

    seen_categories = set()
    for division in DIVISION_ORDER:
        gold_path = pipeline_run["out_dir"] / "gold" / f"{division}_{TEST_DATE.isoformat()}.parquet"
        rows = pq.read_table(gold_path).to_pylist()
        seen_categories.update(row["category"] for row in rows)

    matched = accented_aliases & seen_categories
    assert matched, "none of the accented aliases showed up in Gold output for this run/seed"
    for alias in matched:
        assert alias in seen_categories