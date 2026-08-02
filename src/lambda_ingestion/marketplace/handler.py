from __future__ import annotations

from src.lambda_ingestion.common.handler_base import process_event
from src.lambda_ingestion.marketplace.parser import PdfSalesParser

_parser = PdfSalesParser()


def handler(event, context):
    return process_event(event, context, _parser)
