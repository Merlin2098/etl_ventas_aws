# End-to-end test of the deployed pipeline (Bronze upload -> ingestion Lambda ->
# Silver -> transform Lambda -> Gold), driven entirely through real S3 Object
# Created events routed via EventBridge, against the AWS infrastructure created
# by `terraform -chdir=infra apply`. Uploads the real sample files under data/
# and polls S3 for the Silver/Gold objects the Lambdas are expected to produce
# (SPEC-004/SPEC-005).
from __future__ import annotations

import datetime
import io
import time
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from src.lambda_ingestion.common.schema import GOLD_SCHEMA

pytestmark = pytest.mark.cloud

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
TEST_DATE = datetime.date(2026, 8, 2)

# One real sample file per division, matching each Lambda's expected format
# (SPEC-005: one Lambda = one parser -> electronica=CSV, supermercado=Excel,
# moda=JSON, marketplace=PDF).
DIVISION_FILES = {
    "electronica": DATA_DIR / f"electronica_{TEST_DATE.isoformat()}.csv",
    "supermercado": DATA_DIR / f"supermercado_{TEST_DATE.isoformat()}.xlsx",
    "moda": DATA_DIR / f"moda_{TEST_DATE.isoformat()}.json",
    "marketplace": DATA_DIR / f"marketplace_{TEST_DATE.isoformat()}.pdf",
}

POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 180


@pytest.fixture(scope="module")
def uploaded_run(aws_client, tf_outputs):
    """Uploads one Bronze file per division and waits for the full pipeline
    (Bronze -> Silver -> Gold) to finish for each before any test reads output."""
    bucket = tf_outputs["data_bucket_name"]["value"]
    s3 = aws_client("s3")
    run_id = str(int(time.time()))

    gold_keys = {}
    for division, source_path in DIVISION_FILES.items():
        assert source_path.exists(), f"missing sample file for {division}: {source_path}"

        bronze_key = f"bronze/{division}/{run_id}_{source_path.name}"
        s3.upload_file(str(source_path), bucket, bronze_key)

        gold_prefix = f"gold/store={division}/date={TEST_DATE.isoformat()}/"

        # Silver/Gold filenames are `part-<request_id>.parquet` (write_silver/write_gold
        # in src/lambda_ingestion/common/s3_writer.py) — the request_id is only known
        # after the Lambda runs, so poll by prefix instead of an exact key.
        _wait_for_object_by_prefix(s3, bucket, f"silver/store={division}/date={TEST_DATE.isoformat()}/part-")
        _wait_for_object_by_prefix(s3, bucket, gold_prefix + "part-")

        gold_keys[division] = _latest_object_key(s3, bucket, gold_prefix)

    return {"bucket": bucket, "gold_keys": gold_keys}


def _wait_for_object_by_prefix(s3, bucket: str, prefix: str, timeout: int = POLL_TIMEOUT_SECONDS) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        if response.get("Contents"):
            return
        time.sleep(POLL_INTERVAL_SECONDS)
    raise AssertionError(f"Timed out waiting for s3://{bucket}/{prefix}* after {timeout}s")


def _latest_object_key(s3, bucket: str, prefix: str) -> str:
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    contents = response.get("Contents", [])
    assert contents, f"no objects found under s3://{bucket}/{prefix}"
    return max(contents, key=lambda obj: obj["LastModified"])["Key"]


@pytest.mark.parametrize("division", list(DIVISION_FILES))
def test_gold_object_was_written(uploaded_run, division):
    assert division in uploaded_run["gold_keys"]


@pytest.mark.parametrize("division", list(DIVISION_FILES))
def test_gold_parquet_matches_schema_and_has_rows(aws_client, uploaded_run, division):
    bucket = uploaded_run["bucket"]
    key = uploaded_run["gold_keys"][division]

    s3 = aws_client("s3")
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()

    table = pq.read_table(io.BytesIO(body))
    assert table.schema.equals(GOLD_SCHEMA)
    assert table.num_rows > 0
