from __future__ import annotations

import json
from typing import Iterator

from src.lambda_ingestion.common.errors import FileParseError
from src.lambda_ingestion.common.parser_base import SalesParser


class JsonSalesParser(SalesParser):
    division = "moda"

    def parse(self, raw_bytes: bytes) -> Iterator[dict]:
        try:
            data = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise FileParseError(
                stage="parse", cause=f"unreadable_json: {exc}"
            ) from exc

        if not isinstance(data, list) or not data:
            raise FileParseError(stage="parse", cause="empty_or_non_list_json")

        for row in data:
            if isinstance(row, dict):
                yield row
