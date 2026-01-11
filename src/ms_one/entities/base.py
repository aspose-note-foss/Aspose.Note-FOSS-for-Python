from __future__ import annotations

from dataclasses import dataclass

from onestore.common_types import ExtendedGUID
from onestore.object_data import DecodedPropertySet


@dataclass(frozen=True, slots=True)
class BaseNode:
    oid: ExtendedGUID
    jcid_index: int
    raw_properties: DecodedPropertySet | None


@dataclass(frozen=True, slots=True)
class UnknownNode(BaseNode):
    pass
