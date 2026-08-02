from __future__ import annotations

from src.lambda_ingestion.common.handler_base import process_event
from src.lambda_ingestion.hogar.parser import HogarSalesParser

_parser = HogarSalesParser()


def handler(event, context):
    return process_event(event, context, _parser)
