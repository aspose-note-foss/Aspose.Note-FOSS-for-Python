from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class OneStoreFormatError(Exception):
    message: str
    offset: Optional[int] = None

    def __str__(self) -> str:
        if self.offset is None:
            return self.message
        return f"{self.message} (offset={self.offset})"


@dataclass
class OneStoreWarning:
    message: str
    offset: Optional[int] = None

    def __str__(self) -> str:
        if self.offset is None:
            return self.message
        return f"{self.message} (offset={self.offset})"


class ParseWarning(OneStoreWarning):
    pass
