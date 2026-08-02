from __future__ import annotations

from src.lambda_ingestion.common.handler_base import process_event
from src.lambda_ingestion.electronica.parser import CsvSalesParser

_parser = CsvSalesParser()


def handler(event, context):
    return process_event(event, context, _parser)
