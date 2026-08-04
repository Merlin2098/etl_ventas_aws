from __future__ import annotations

import datetime
import io
import os

import boto3
import pyarrow.parquet as pq

from .errors import RowValidationError
from .logging_config import get_logger
from .s3_writer import write_gold, write_quarantine
from .schema import validate_and_normalize


def _partition_date_from_key(key: str) -> datetime.date:
    """Extracts the `date=YYYY-MM-DD` Hive partition segment from a Silver S3 key
    (silver/store=<division>/date=<fecha>/part-*.parquet)."""
    for segment in key.split("/"):
        if segment.startswith("date="):
            return datetime.date.fromisoformat(segment.removeprefix("date="))
    raise ValueError(f"No date= partition segment found in key: {key}")


def process_transform_event(event: dict, context) -> dict:
    """Shared handler flow for every division's transform Lambda (Silver -> Gold):
    read Silver Parquet -> validate_and_normalize -> write gold/quarantine.

    Triggered by the S3 event notification on `silver/store=<division>/` (SPEC-003).
    Unlike the ingestion Lambda (see `handler_base.process_event`), there is no
    format-specific parser here: every division's Silver output is Parquet, already
    field-validated by the ingestion Lambda's `normalize_silver` step.
    """
    division = os.environ["DIVISION"]
    bucket = os.environ["DATA_BUCKET"]
    correlation_id = context.aws_request_id

    log = get_logger(
        service=context.function_name,
        stage="parse",
        document_id="file",
        correlation_id=correlation_id,
    )

    record = event["Records"][0]["s3"]
    source_bucket = record["bucket"]["name"]
    source_key = record["object"]["key"]
    log.info("Processing started", extra={"bucket": source_bucket, "key": source_key})

    # `date` is a Hive partition column (silver/store=<division>/date=<fecha>/...),
    # not a column inside the Silver Parquet file itself, so it's read from the key
    # rather than from each row (mirrors how Gold/Quarantine exclude it too).
    partition_date = _partition_date_from_key(source_key)

    s3_client = boto3.client("s3")
    raw_bytes = s3_client.get_object(Bucket=source_bucket, Key=source_key)[
        "Body"
    ].read()

    silver_rows = pq.read_table(io.BytesIO(raw_bytes)).to_pylist()

    valid_rows: dict[datetime.date, list[dict]] = {}
    errors: dict[datetime.date, list[dict]] = {}
    for silver_row in silver_rows:
        try:
            # `date` is a Hive partition column (silver/store=<division>/date=<fecha>/...),
            # not a column inside the Silver Parquet file, so it's injected back from the
            # partition key here (mirrors scripts/testing/run_local_ingestion.py).
            row_with_date = {**silver_row, "date": partition_date}
            gold_row, date = validate_and_normalize(
                row_with_date,
                division=division,
                stage="validate",
                correlation_id=correlation_id,
            )
            valid_rows.setdefault(date, []).append(gold_row)
        except RowValidationError as exc:
            log.warning(
                "Row routed to quarantine",
                extra={"sale_id": exc.sale_id, "cause": exc.cause},
            )
            errors.setdefault(partition_date, []).append(
                {"row": silver_row, "error": exc.cause}
            )

    written = {"gold": [], "quarantine": []}
    for date, rows in valid_rows.items():
        uri = write_gold(bucket, division, date, correlation_id, rows)
        if uri:
            written["gold"].append(uri)

    # Delete-then-write still applies to dates that only produced quarantined
    # rows (SPEC-003/SPEC-005): clear any stale Gold partition from a prior run.
    for date in set(errors) - set(valid_rows):
        write_gold(bucket, division, date, correlation_id, [])

    for date, error_rows in errors.items():
        uri = write_quarantine(bucket, division, date, correlation_id, error_rows)
        if uri:
            written["quarantine"].append(uri)

    log.info(
        "Processing finished",
        extra={
            "valid_rows": sum(len(v) for v in valid_rows.values()),
            "invalid_rows": sum(len(v) for v in errors.values()),
        },
    )
    return written
