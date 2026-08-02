from __future__ import annotations


class PipelineError(Exception):
    def __init__(
        self, stage: str, cause: str, sale_id: str = "", correlation_id: str = ""
    ):
        self.stage = stage
        self.cause = cause
        self.sale_id = sale_id
        self.correlation_id = correlation_id
        super().__init__(f"[{stage}] {cause}")


class RowValidationError(PipelineError):
    """Single row invalid — routed to quarantine, does not interrupt the file."""


class FileParseError(PipelineError):
    """Whole file unreadable or corrupt — no output written to Gold."""
