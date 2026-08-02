from __future__ import annotations

import csv
import io
from typing import Iterator

from src.lambda_ingestion.common.errors import FileParseError
from src.lambda_ingestion.common.parser_base import SalesParser


class CsvSalesParser(SalesParser):
    division = "electronica"

    def parse(self, raw_bytes: bytes) -> Iterator[dict]:
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = raw_bytes.decode("latin-1", errors="replace")

        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise FileParseError(stage="parse", cause="empty_or_unreadable_csv")

        yielded_any = False
        for row in reader:
            yielded_any = True
            yield dict(row)

        if not yielded_any:
            raise FileParseError(stage="parse", cause="no_rows_in_csv")
