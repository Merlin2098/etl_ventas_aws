from __future__ import annotations

from ..common.handler_base import process_event
from .parser import CsvSalesParser

_parser = CsvSalesParser()


def handler(event, context):
    return process_event(event, context, _parser)
