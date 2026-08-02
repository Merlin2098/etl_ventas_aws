from __future__ import annotations

from src.lambda_ingestion.common.handler_base import process_event
from src.lambda_ingestion.moda.parser import JsonSalesParser

_parser = JsonSalesParser()


def handler(event, context):
    return process_event(event, context, _parser)
