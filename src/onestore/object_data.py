from __future__ import annotations

from dataclasses import dataclass

from .common_types import CompactID
from .errors import OneStoreFormatError
from .io import BinaryReader
from .parse_context import ParseContext


@dataclass(frozen=True, slots=True)
class ObjectSpaceObjectStreamHeader:
    """ObjectSpaceObjectStreamHeader (2.6.5).

    Bit layout (u32 LE):
    - Count: 24 bits
    - Reserved: 6 bits (MUST be 0)
    - ExtendedStreamsPresent: 1 bit
    - OsidStreamNotPresent: 1 bit
    """

    raw: int
    count: int
    reserved: int
    extended_streams_present: bool
    osid_stream_not_present: bool

    @classmethod
    def from_u32(cls, value: int) -> "ObjectSpaceObjectStreamHeader":
        value &= 0xFFFFFFFF
        count = value & 0xFFFFFF
        reserved = (value >> 24) & 0x3F
        extended = bool((value >> 30) & 1)
        osid_not_present = bool((value >> 31) & 1)
        return cls(
            raw=value,
            count=int(count),
            reserved=int(reserved),
            extended_streams_present=extended,
            osid_stream_not_present=osid_not_present,
        )

    @classmethod
    def parse(cls, reader: BinaryReader, *, ctx: ParseContext) -> "ObjectSpaceObjectStreamHeader":
        raw = int(reader.read_u32())
        out = cls.from_u32(raw)
        if out.reserved != 0:
            msg = "ObjectSpaceObjectStreamHeader.Reserved MUST be 0"
            if ctx.strict:
                raise OneStoreFormatError(msg, offset=reader.tell() - 4)
            ctx.warn(msg, offset=reader.tell() - 4)
        return out


@dataclass(frozen=True, slots=True)
class ObjectSpaceObjectStream:
    header: ObjectSpaceObjectStreamHeader
    body: tuple[CompactID, ...]

    @classmethod
    def parse(cls, reader: BinaryReader, *, ctx: ParseContext) -> "ObjectSpaceObjectStream":
        header = ObjectSpaceObjectStreamHeader.parse(reader, ctx=ctx)
        # Each CompactID is a u32.
        needed = header.count * 4
        if reader.remaining() < needed:
            raise OneStoreFormatError(
                "ObjectSpaceObjectStream body exceeds available data",
                offset=reader.tell(),
            )
        body = tuple(CompactID.parse(reader) for _ in range(header.count))
        return cls(header=header, body=body)


@dataclass(frozen=True, slots=True)
class PropertyID:
    """PropertyID (2.6.6)."""

    raw: int
    prop_id: int
    prop_type: int
    bool_value: bool

    @classmethod
    def from_u32(cls, value: int) -> "PropertyID":
        value &= 0xFFFFFFFF
        prop_id = value & 0x03FFFFFF
        prop_type = (value >> 26) & 0x1F
        bool_value = bool((value >> 31) & 1)
        return cls(raw=value, prop_id=int(prop_id), prop_type=int(prop_type), bool_value=bool_value)

    @classmethod
    def parse(cls, reader: BinaryReader) -> "PropertyID":
        return cls.from_u32(int(reader.read_u32()))


@dataclass(frozen=True, slots=True)
class PropertySet:
    """PropertySet (2.6.7), structural parse.

    We intentionally do not decode rgData into typed property values yet.
    """

    c_properties: int
    rg_prids: tuple[PropertyID, ...]
    rg_data: bytes

    @classmethod
    def parse_from_tail(cls, reader: BinaryReader, *, ctx: ParseContext) -> "PropertySet":
        """Parse a PropertySet from a bounded reader and consume all remaining bytes.

        This is a structural parse: rgData is kept as raw bytes.
        """

        if reader.remaining() < 2:
            raise OneStoreFormatError("PropertySet missing cProperties", offset=reader.tell())

        c_properties = int(reader.read_u16())

        # prids are u32 each.
        needed_prids = c_properties * 4
        if reader.remaining() < needed_prids:
            raise OneStoreFormatError(
                "PropertySet rgPrids exceeds available data",
                offset=reader.tell(),
            )

        rg_prids = tuple(PropertyID.parse(reader) for _ in range(c_properties))

        # Remaining bytes are rgData (possibly including object-level padding; handled by caller).
        rg_data = reader.read_bytes(reader.remaining())
        return cls(c_properties=c_properties, rg_prids=rg_prids, rg_data=bytes(rg_data))


@dataclass(frozen=True, slots=True)
class ObjectSpaceObjectPropSet:
    """ObjectSpaceObjectPropSet (2.6.1), structural parse.

    Parsed components:
    - OIDs stream (always present)
    - Optional OSIDs stream
    - Optional ContextIDs stream
    - PropertySet (structural)
    - Padding (0..7 bytes), expected to be zero

    NOTE: This layer does not resolve CompactIDs or decode PropertySet values.
    """

    oids: ObjectSpaceObjectStream
    osids: ObjectSpaceObjectStream | None
    context_ids: ObjectSpaceObjectStream | None
    property_set: PropertySet
    padding: bytes

    @classmethod
    def parse(cls, reader: BinaryReader, *, ctx: ParseContext) -> "ObjectSpaceObjectPropSet":
        start = reader.tell()

        oids = ObjectSpaceObjectStream.parse(reader, ctx=ctx)

        osids: ObjectSpaceObjectStream | None = None
        context_ids: ObjectSpaceObjectStream | None = None

        if oids.header.osid_stream_not_present:
            if oids.header.extended_streams_present:
                msg = "OIDs header is inconsistent: ExtendedStreamsPresent set while OsidStreamNotPresent is true"
                if ctx.strict:
                    raise OneStoreFormatError(msg, offset=start)
                ctx.warn(msg, offset=start)
        else:
            osids = ObjectSpaceObjectStream.parse(reader, ctx=ctx)
            # If OSIDs header indicates an additional stream, parse ContextIDs.
            if osids.header.extended_streams_present:
                context_ids = ObjectSpaceObjectStream.parse(reader, ctx=ctx)

        # Remaining bytes: PropertySet + padding.
        tail = BinaryReader(reader.read_bytes(reader.remaining()))
        prop = PropertySet.parse_from_tail(tail, ctx=ctx)

        # Split padding heuristically: up to 7 trailing zeros.
        rg = prop.rg_data
        pad_len = 0
        max_scan = min(7, len(rg))
        for k in range(max_scan, 0, -1):
            if rg[-k:] == b"\x00" * k:
                pad_len = k
                break

        padding = rg[-pad_len:] if pad_len else b""
        if padding and padding != b"\x00" * len(padding):
            # Defensive: should never happen due to check above.
            raise OneStoreFormatError("ObjectSpaceObjectPropSet padding MUST be zero", offset=start)

        if padding and ctx.strict:
            # Keep strict about MUST=0 padding bytes; our heuristic only extracts zeros.
            pass

        prop_no_pad = PropertySet(
            c_properties=prop.c_properties,
            rg_prids=prop.rg_prids,
            rg_data=rg[:-pad_len] if pad_len else rg,
        )

        return cls(
            oids=oids,
            osids=osids,
            context_ids=context_ids,
            property_set=prop_no_pad,
            padding=padding,
        )


def parse_object_space_object_prop_set_from_ref(
    data: bytes | bytearray | memoryview,
    *,
    stp: int,
    cb: int,
    ctx: ParseContext,
) -> ObjectSpaceObjectPropSet:
    """Convenience helper to parse an ObjectSpaceObjectPropSet from a file offset/size."""

    if stp < 0 or cb < 0:
        raise OneStoreFormatError("stp/cb MUST be non-negative", offset=None)

    r = BinaryReader(data).view(int(stp), int(cb))
    return ObjectSpaceObjectPropSet.parse(r, ctx=ctx)


@dataclass(frozen=True, slots=True)
class PrtFourBytesOfLengthFollowedByData:
    cb: int
    data: bytes

    @classmethod
    def parse(cls, reader: BinaryReader, *, ctx: ParseContext) -> "PrtFourBytesOfLengthFollowedByData":
        start = reader.tell()
        cb = int(reader.read_u32())
        if cb >= 0x40000000:
            msg = "prtFourBytesOfLengthFollowedByData.cb MUST be < 0x40000000"
            if ctx.strict:
                raise OneStoreFormatError(msg, offset=start)
            ctx.warn(msg, offset=start)
        if reader.remaining() < cb:
            raise OneStoreFormatError("prtFourBytesOfLengthFollowedByData exceeds available data", offset=start)
        data = reader.read_bytes(cb)
        return cls(cb=cb, data=bytes(data))


@dataclass(frozen=True, slots=True)
class PrtArrayOfPropertyValues:
    """prtArrayOfPropertyValues (2.6.9), structural parse.

    Full decoding requires parsing embedded PropertySet elements, which is deferred.
    """

    c_properties: int
    prid: PropertyID | None
    raw_data: bytes

    @classmethod
    def parse(cls, reader: BinaryReader, *, ctx: ParseContext) -> "PrtArrayOfPropertyValues":
        start = reader.tell()
        c = int(reader.read_u32())
        if c == 0:
            return cls(c_properties=0, prid=None, raw_data=b"")

        if reader.remaining() < 4:
            raise OneStoreFormatError("prtArrayOfPropertyValues missing prid", offset=start)
        prid = PropertyID.parse(reader)
        if prid.prop_type != 0x11:
            msg = "prtArrayOfPropertyValues.prid.type MUST be 0x11 (PropertySet)"
            if ctx.strict:
                raise OneStoreFormatError(msg, offset=start)
            ctx.warn(msg, offset=start)

        raw = reader.read_bytes(reader.remaining())
        return cls(c_properties=c, prid=prid, raw_data=bytes(raw))
