from __future__ import annotations

from typing import Any, Iterable

from ..onestore.common_types import CompactID, ExtendedGUID
from ..onestore.object_data import DecodedProperty, DecodedPropertySet

from .errors import MSOneFormatError


def iter_props(pset: DecodedPropertySet) -> Iterable[DecodedProperty]:
    return pset.properties


def get_prop(pset: DecodedPropertySet, property_id_raw: int) -> DecodedProperty | None:
    pid = int(property_id_raw) & 0xFFFFFFFF
    for p in pset.properties:
        if int(p.prid.raw) == pid:
            return p
    return None


def require_prop(pset: DecodedPropertySet, property_id_raw: int, *, msg: str) -> DecodedProperty:
    p = get_prop(pset, property_id_raw)
    if p is None:
        raise MSOneFormatError(msg)
    return p


def get_bool(pset: DecodedPropertySet, property_id_raw: int) -> bool | None:
    p = get_prop(pset, property_id_raw)
    if p is None:
        return None
    if isinstance(p.value, bool):
        return bool(p.value)
    return None


def get_bytes(pset: DecodedPropertySet, property_id_raw: int) -> bytes | None:
    p = get_prop(pset, property_id_raw)
    if p is None:
        return None
    if p.value is None:
        return None
    if isinstance(p.value, (bytes, bytearray, memoryview)):
        return bytes(p.value)
    return None


def get_u32_from_bytes(pset: DecodedPropertySet, property_id_raw: int) -> int | None:
    b = get_bytes(pset, property_id_raw)
    if b is None or len(b) < 4:
        return None
    return int.from_bytes(b[:4], "little", signed=False)


def get_oid(pset: DecodedPropertySet, property_id_raw: int) -> CompactID | ExtendedGUID | None:
    p = get_prop(pset, property_id_raw)
    if p is None:
        return None
    if isinstance(p.value, (CompactID, ExtendedGUID)):
        return p.value
    return None


def get_oid_array(
    pset: DecodedPropertySet, property_id_raw: int
) -> tuple[CompactID, ...] | tuple[ExtendedGUID, ...] | None:
    p = get_prop(pset, property_id_raw)
    if p is None:
        return None
    v: Any = p.value
    if isinstance(v, tuple) and (not v or isinstance(v[0], (CompactID, ExtendedGUID))):
        return v
    return None
