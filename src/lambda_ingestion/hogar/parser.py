from __future__ import annotations

from src.lambda_ingestion.electronica.parser import CsvSalesParser


class HogarSalesParser(CsvSalesParser):
    division = "hogar"
