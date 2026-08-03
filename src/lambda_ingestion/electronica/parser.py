from __future__ import annotations

import csv
import io
from typing import Iterator

from src.lambda_ingestion.common.errors import FileParseError
from src.lambda_ingestion.common.parser_base import SalesParser


def _decode_line(line: bytes) -> str:
    try:
        return line.decode("utf-8")
    except UnicodeDecodeError:
        return line.decode("latin-1", errors="replace")


class CsvSalesParser(SalesParser):
    division = "electronica"

    def parse(self, raw_bytes: bytes) -> Iterator[dict]:
        # Decoded per line, not as a single decode() over the whole file: one
        # corrupted line (e.g. the intentional "bad_encoding" corruption from
        # the synthetic generator, a stray non-UTF-8 byte in `product`) must
        # not force the latin-1 fallback onto every other line — that fallback
        # reinterprets valid UTF-8 multi-byte accented characters (tildes, ñ)
        # in unrelated rows as mojibake, corrupting otherwise-clean data.
        lines = raw_bytes.split(b"\n")
        text = "\n".join(_decode_line(line) for line in lines)

        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise FileParseError(stage="parse", cause="empty_or_unreadable_csv")

        yielded_any = False
        for row in reader:
            yielded_any = True
            yield dict(row)

        if not yielded_any:
            raise FileParseError(stage="parse", cause="no_rows_in_csv")
