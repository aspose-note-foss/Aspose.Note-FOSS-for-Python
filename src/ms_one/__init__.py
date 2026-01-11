"""MS-ONE entity reader built on top of the MS-ONESTORE container reader."""

from .errors import MSOneFormatError
from .reader import parse_section_file

__all__ = [
    "MSOneFormatError",
    "parse_section_file",
]
