from __future__ import annotations

import pytest

from src.lambda_ingestion.common.s3_event import extract_s3_location


def test_extract_s3_location_from_s3_notification_envelope():
    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "data-platform-dev-184670914470-datalake"},
                    "object": {"key": "bronze/date=2026-08-02/electronica/ventas.csv"},
                }
            }
        ]
    }
    bucket, key = extract_s3_location(event)
    assert bucket == "data-platform-dev-184670914470-datalake"
    assert key == "bronze/date=2026-08-02/electronica/ventas.csv"


def test_extract_s3_location_from_s3_notification_decodes_url_encoded_key():
    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "data-platform-dev-184670914470-datalake"},
                    "object": {"key": "bronze/date=2026-08-02/electronica/ventas+de+agosto.csv"},
                }
            }
        ]
    }
    bucket, key = extract_s3_location(event)
    assert bucket == "data-platform-dev-184670914470-datalake"
    assert key == "bronze/date=2026-08-02/electronica/ventas de agosto.csv"


def test_extract_s3_location_from_eventbridge_envelope():
    event = {
        "detail": {
            "bucket": {"name": "data-platform-dev-184670914470-datalake"},
            "object": {"key": "silver/store=electronica/date=2026-08-02/part-abc.parquet"},
        }
    }
    bucket, key = extract_s3_location(event)
    assert bucket == "data-platform-dev-184670914470-datalake"
    assert key == "silver/store=electronica/date=2026-08-02/part-abc.parquet"


def test_extract_s3_location_from_eventbridge_does_not_decode_key():
    event = {
        "detail": {
            "bucket": {"name": "data-platform-dev-184670914470-datalake"},
            "object": {"key": "bronze/date=2026-08-02/electronica/ventas+de+agosto.csv"},
        }
    }
    bucket, key = extract_s3_location(event)
    assert key == "bronze/date=2026-08-02/electronica/ventas+de+agosto.csv"


def test_extract_s3_location_raises_on_unrecognized_shape():
    with pytest.raises(ValueError):
        extract_s3_location({"unexpected": "shape"})
