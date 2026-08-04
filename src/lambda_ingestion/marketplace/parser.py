from __future__ import annotations

import io
from typing import Iterator

import pdfplumber

from ..common.errors import FileParseError
from ..common.parser_base import SalesParser

FIELDNAMES = ["sale_id", "date", "category", "product", "quantity", "price", "currency", "status"]
HEADER_ROW = ["ID Venta", "Fecha", "Categoría", "Producto", "Cantidad", "Precio", "Moneda", "Estado"]


class PdfSalesParser(SalesParser):
    division = "marketplace"

    def parse(self, raw_bytes: bytes) -> Iterator[dict]:
        try:
            pdf = pdfplumber.open(io.BytesIO(raw_bytes))
        except Exception as exc:
            raise FileParseError(stage="parse", cause=f"unreadable_pdf: {exc}") from exc

        yielded_any = False
        with pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if not table:
                    continue
                # `repeatRows=1` in the generator (SPEC-007) repeats the header on
                # every page; skip it wherever it appears rather than assuming
                # it's only the first row of the first page.
                for raw_row in table:
                    if raw_row == HEADER_ROW:
                        continue
                    yielded_any = True
                    yield dict(zip(FIELDNAMES, raw_row))

        if not yielded_any:
            raise FileParseError(stage="parse", cause="no_table_extracted_from_pdf")
