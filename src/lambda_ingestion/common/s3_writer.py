from __future__ import annotations

import datetime
import io
import json

import boto3
import pyarrow as pa
import pyarrow.parquet as pq

from src.lambda_ingestion.common.schema import GOLD_SCHEMA


def _gold_prefix(division: str, date: datetime.date) -> str:
    return f"gold/store={division}/date={date.isoformat()}/"


def _quarantine_prefix(division: str, date: datetime.date) -> str:
    return f"quarantine/store={division}/date={date.isoformat()}/"


def _delete_prefix(s3_client, bucket: str, prefix: str) -> None:
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if keys:
            s3_client.delete_objects(Bucket=bucket, Delete={"Objects": keys})


def write_gold(
    bucket: str,
    division: str,
    date: datetime.date,
    request_id: str,
    rows: list[dict],
) -> str | None:
    """Delete-then-write the Gold partition for division+date (SPEC-003 'último gana').

    Returns the written S3 URI, or None if there were no valid rows (no empty
    Parquet file is written, per SPEC-005).
    """
    s3_client = boto3.client("s3")
    prefix = _gold_prefix(division, date)
    _delete_prefix(s3_client, bucket, prefix)

    if not rows:
        return None

    table = pa.Table.from_pylist(rows, schema=GOLD_SCHEMA)
    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    buffer.seek(0)

    key = f"{prefix}part-{request_id}.parquet"
    s3_client.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue())
    return f"s3://{bucket}/{key}"


def write_quarantine(
    bucket: str,
    division: str,
    date: datetime.date,
    request_id: str,
    errors: list[dict],
) -> str | None:
    """Writes invalid rows as a JSON error report. Quarantine files accumulate
    across invocations (no delete-then-write) to preserve error history."""
    if not errors:
        return None

    s3_client = boto3.client("s3")
    key = f"{_quarantine_prefix(division, date)}errors-{request_id}.json"
    body = json.dumps(errors, ensure_ascii=False, default=str, indent=2)
    s3_client.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"))
    return f"s3://{bucket}/{key}"
