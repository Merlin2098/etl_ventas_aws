from __future__ import annotations

import datetime
import os

import boto3

from src.lambda_ingestion.common.errors import FileParseError, RowValidationError
from src.lambda_ingestion.common.logging_config import get_logger
from src.lambda_ingestion.common.parser_base import SalesParser
from src.lambda_ingestion.common.s3_writer import write_gold, write_quarantine
from src.lambda_ingestion.common.schema import parse_date, validate_and_normalize


def process_event(event: dict, context, parser: SalesParser) -> dict:
    """Shared handler flow for every division (SPEC-005 'Arquitectura interna'):
    parse -> validate_and_normalize -> write gold/quarantine.

    `parser` already knows its division and format; this function contains no
    format-detection logic (SPEC-003/SPEC-005 — one Lambda = one parser).
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
            gold_row, date = validate_and_normalize(
                raw_row,
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
            error_date = parse_date(raw_row.get("date")) or datetime.date.today()
            errors.setdefault(error_date, []).append(
                {"row": raw_row, "error": exc.cause}
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
