from __future__ import annotations

from dataclasses import dataclass, field

from .errors import ParseWarning


@dataclass(slots=True)
class ParseContext:
    """Parsing context for strict/tolerant modes.

    For now Step 4 primarily uses `strict` and `file_size`. Tolerant parsing is
    planned later; this context keeps the surface area small while enabling
    warnings collection.
    """

    strict: bool = True
    warnings: list[ParseWarning] = field(default_factory=list)
    file_size: int | None = None
    path: str | None = None

    def warn(self, message: str, *, offset: int | None = None) -> None:
        self.warnings.append(ParseWarning(message=message, offset=offset))
