from __future__ import annotations

import datetime
import os
from pathlib import Path

import boto3


def bronze_key(division: str, date: datetime.date, ext: str) -> str:
    date_str = date.isoformat()
    return f"bronze/{division}/date={date_str}/{division}_{date_str}.{ext}"


def upload_to_bronze(
    local_path: Path, division: str, date: datetime.date, ext: str
) -> str:
    bucket = os.environ["DATA_BUCKET"]
    key = bronze_key(division, date, ext)
    boto3.client("s3").upload_file(str(local_path), bucket, key)
    return f"s3://{bucket}/{key}"
