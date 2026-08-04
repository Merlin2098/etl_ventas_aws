from __future__ import annotations

from ..common.handler_base import process_event
from .parser import PdfSalesParser

_parser = PdfSalesParser()


def handler(event, context):
    return process_event(event, context, _parser)
