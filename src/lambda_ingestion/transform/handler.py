from __future__ import annotations

from ..common.transform_handler_base import process_transform_event


def handler(event, context):
    return process_transform_event(event, context)
