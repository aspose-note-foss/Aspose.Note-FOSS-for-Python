from __future__ import annotations

from dataclasses import dataclass

from onestore.common_types import ExtendedGUID
from onestore.object_data import DecodedPropertySet

from .base import BaseNode


@dataclass(frozen=True, slots=True)
class Section(BaseNode):
    display_name: str | None
    children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class PageSeries(BaseNode):
    children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class Page(BaseNode):
    title: str | None
    children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class Title(BaseNode):
    children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class Outline(BaseNode):
    children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class OutlineElement(BaseNode):
    children: tuple[BaseNode, ...]
    content_children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class RichText(BaseNode):
    text: str | None


@dataclass(frozen=True, slots=True)
class Image(BaseNode):
    alt_text: str | None


@dataclass(frozen=True, slots=True)
class Table(BaseNode):
    children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class TableRow(BaseNode):
    children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class TableCell(BaseNode):
    children: tuple[BaseNode, ...]


@dataclass(frozen=True, slots=True)
class SectionMetaData(BaseNode):
    raw: DecodedPropertySet | None


@dataclass(frozen=True, slots=True)
class PageMetaData(BaseNode):
    raw: DecodedPropertySet | None


@dataclass(frozen=True, slots=True)
class PageManifest(BaseNode):
    children: tuple[BaseNode, ...]
    content_children: tuple[BaseNode, ...]
