from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator


class SalesParser(ABC):
    division: str

    @abstractmethod
    def parse(self, raw_bytes: bytes) -> Iterator[dict]:
        """Yields raw rows as dicts, unnormalized, exactly as they appear in the source file."""
