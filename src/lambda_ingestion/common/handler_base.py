from __future__ import annotations

import datetime
import os

import boto3

from src.lambda_ingestion.common.errors import FileParseError, RowValidationError
from src.lambda_ingestion.common.logging_config import get_logger
from src.lambda_ingestion.common.parser_base import SalesParser
from src.lambda_ingestion.common.s3_writer import write_quarantine, write_silver
from src.lambda_ingestion.common.schema import normalize_silver, parse_date


def process_event(event: dict, context, parser: SalesParser) -> dict:
    """Shared handler flow for every division's ingestion Lambda (SPEC-005
    'Arquitectura interna'): parse -> normalize_silver -> write silver.

    `parser` already knows its division and format; this function contains no
    format-detection logic (SPEC-003/SPEC-005 — one Lambda = one parser). Rows
    that fail Silver-stage validation are routed to quarantine here, same as
    the Gold-stage Lambda does for its own validation failures.
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

    s3_client = boto3.client("s3")
    raw_bytes = s3_client.get_object(Bucket=source_bucket, Key=source_key)[
        "Body"
    ].read()

    try:
        raw_rows = list(parser.parse(raw_bytes))
    except FileParseError as exc:
        log.error("File could not be parsed", extra={"cause": exc.cause})
        raise

    valid_rows: dict[datetime.date, list[dict]] = {}
    errors: dict[datetime.date, list[dict]] = {}
    for raw_row in raw_rows:
        try:
            silver_row, date = normalize_silver(
                raw_row,
                division=division,
                correlation_id=correlation_id,
            )
            valid_rows.setdefault(date, []).append(silver_row)
        except RowValidationError as exc:
            log.warning(
                "Row routed to quarantine",
                extra={"sale_id": exc.sale_id, "cause": exc.cause},
            )
            error_date = parse_date(raw_row.get("date")) or datetime.date.today()
            errors.setdefault(error_date, []).append(
                {"row": raw_row, "error": exc.cause}
            )

    written = {"silver": [], "quarantine": []}
    for date, rows in valid_rows.items():
        uri = write_silver(bucket, division, date, correlation_id, rows)
        if uri:
            written["silver"].append(uri)

    # Delete-then-write still applies to dates that only produced quarantined
    # rows (SPEC-003/SPEC-005): clear any stale Silver partition from a prior run.
    for date in set(errors) - set(valid_rows):
        write_silver(bucket, division, date, correlation_id, [])

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
