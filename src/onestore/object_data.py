from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
class DecodedProperty:
    """A decoded PropertyID/value pair.

    rgdata_offset/rgdata_length are measured within this PropertySet's rgData.
    For stream-only reference types, rgdata_length is 0.
    """

    prid: PropertyID
    value: Any
    rgdata_offset: int
    rgdata_length: int


@dataclass(frozen=True, slots=True)
class DecodedPropertySet:
    """Decoded PropertySet with deterministic ordering (same as rgPrids order)."""

    c_properties: int
    properties: tuple[DecodedProperty, ...]
    rgdata_size: int
    encoded_size: int


@dataclass(slots=True)
class _RefCursor:
    oids: tuple[CompactID, ...]
    osids: tuple[CompactID, ...] | None
    context_ids: tuple[CompactID, ...] | None
    i_oid: int = 0
    i_osid: int = 0
    i_ctx: int = 0

    def take_oid(self, n: int, *, offset: int | None) -> tuple[CompactID, ...]:
        if n < 0:
            raise OneStoreFormatError("Reference count MUST be non-negative", offset=offset)
        end = self.i_oid + n
        if end > len(self.oids):
            raise OneStoreFormatError("OIDs stream does not contain enough CompactIDs", offset=offset)
        out = self.oids[self.i_oid : end]
        self.i_oid = end
        return out

    def take_osid(self, n: int, *, offset: int | None) -> tuple[CompactID, ...]:
        if self.osids is None:
            raise OneStoreFormatError("OSIDs stream is required but not present", offset=offset)
        if n < 0:
            raise OneStoreFormatError("Reference count MUST be non-negative", offset=offset)
        end = self.i_osid + n
        if end > len(self.osids):
            raise OneStoreFormatError("OSIDs stream does not contain enough CompactIDs", offset=offset)
        out = self.osids[self.i_osid : end]
        self.i_osid = end
        return out

    def take_context(self, n: int, *, offset: int | None) -> tuple[CompactID, ...]:
        if self.context_ids is None:
            raise OneStoreFormatError("ContextIDs stream is required but not present", offset=offset)
        if n < 0:
            raise OneStoreFormatError("Reference count MUST be non-negative", offset=offset)
        end = self.i_ctx + n
        if end > len(self.context_ids):
            raise OneStoreFormatError("ContextIDs stream does not contain enough CompactIDs", offset=offset)
        out = self.context_ids[self.i_ctx : end]
        self.i_ctx = end
        return out


def _decode_property_set_from_reader(
    reader: BinaryReader,
    cursor: _RefCursor,
    *,
    ctx: ParseContext,
) -> DecodedPropertySet:
    """Decode a PropertySet encoded at the current reader position.

    This consumes exactly the bytes for this property set from `reader`.
    """

    start = reader.tell()
    if reader.remaining() < 2:
        raise OneStoreFormatError("PropertySet missing cProperties", offset=reader.tell())

    c_properties = int(reader.read_u16())
    needed_prids = c_properties * 4
    if reader.remaining() < needed_prids:
        raise OneStoreFormatError("PropertySet rgPrids exceeds available data", offset=reader.tell())

    prids = tuple(PropertyID.parse(reader) for _ in range(c_properties))

    # rgData starts immediately after rgPrids and continues with sizes implied by each PropertyID.
    rgdata_start = reader.tell()

    props: list[DecodedProperty] = []
    for prid in prids:
        props.append(_decode_one_property(prid, reader, cursor, rgdata_start=rgdata_start, ctx=ctx))

    rgdata_end = reader.tell()
    rgdata_size = rgdata_end - rgdata_start
    encoded_size = rgdata_end - start

    return DecodedPropertySet(
        c_properties=c_properties,
        properties=tuple(props),
        rgdata_size=int(rgdata_size),
        encoded_size=int(encoded_size),
    )


def _decode_one_property(
    prid: PropertyID,
    reader: BinaryReader,
    cursor: _RefCursor,
    *,
    rgdata_start: int,
    ctx: ParseContext,
) -> DecodedProperty:
    """Decode a single property value from rgData and/or reference streams."""

    t = int(prid.prop_type)
    rg_off = int(reader.tell() - rgdata_start)

    # 0x1: NoData
    if t == 0x01:
        return DecodedProperty(prid=prid, value=None, rgdata_offset=rg_off, rgdata_length=0)

    # 0x2: Bool (value in boolValue bit)
    if t == 0x02:
        return DecodedProperty(prid=prid, value=bool(prid.bool_value), rgdata_offset=rg_off, rgdata_length=0)

    # Fixed-size values in rgData
    fixed_sizes = {0x03: 1, 0x04: 2, 0x05: 4, 0x06: 8}
    if t in fixed_sizes:
        n = fixed_sizes[t]
        if reader.remaining() < n:
            raise OneStoreFormatError("PropertySet rgData fixed-size value exceeds available data", offset=reader.tell())
        raw = reader.read_bytes(n)
        return DecodedProperty(prid=prid, value=bytes(raw), rgdata_offset=rg_off, rgdata_length=n)

    # Variable-size container
    if t == 0x07:
        start = reader.tell()
        box = PrtFourBytesOfLengthFollowedByData.parse(reader, ctx=ctx)
        length = int(reader.tell() - start)
        return DecodedProperty(prid=prid, value=bytes(box.data), rgdata_offset=rg_off, rgdata_length=length)

    # Reference types: value(s) come from the corresponding streams.
    if t == 0x08:  # OID
        (oid,) = cursor.take_oid(1, offset=reader.tell())
        return DecodedProperty(prid=prid, value=oid, rgdata_offset=rg_off, rgdata_length=0)
    if t == 0x09:  # OID array (count in rgData as u32)
        if reader.remaining() < 4:
            raise OneStoreFormatError("PropertySet missing OID array length", offset=reader.tell())
        count = int(reader.read_u32())
        oids = cursor.take_oid(count, offset=reader.tell() - 4)
        return DecodedProperty(prid=prid, value=tuple(oids), rgdata_offset=rg_off, rgdata_length=4)

    if t == 0x0A:  # OSID
        (osid,) = cursor.take_osid(1, offset=reader.tell())
        return DecodedProperty(prid=prid, value=osid, rgdata_offset=rg_off, rgdata_length=0)
    if t == 0x0B:  # OSID array
        if reader.remaining() < 4:
            raise OneStoreFormatError("PropertySet missing OSID array length", offset=reader.tell())
        count = int(reader.read_u32())
        osids = cursor.take_osid(count, offset=reader.tell() - 4)
        return DecodedProperty(prid=prid, value=tuple(osids), rgdata_offset=rg_off, rgdata_length=4)

    if t == 0x0C:  # ContextID
        (cid,) = cursor.take_context(1, offset=reader.tell())
        return DecodedProperty(prid=prid, value=cid, rgdata_offset=rg_off, rgdata_length=0)
    if t == 0x0D:  # ContextID array
        if reader.remaining() < 4:
            raise OneStoreFormatError("PropertySet missing ContextID array length", offset=reader.tell())
        count = int(reader.read_u32())
        cids = cursor.take_context(count, offset=reader.tell() - 4)
        return DecodedProperty(prid=prid, value=tuple(cids), rgdata_offset=rg_off, rgdata_length=4)

    # prtArrayOfPropertyValues (currently: array of nested PropertySet)
    if t == 0x10:
        start = reader.tell()
        if reader.remaining() < 4:
            raise OneStoreFormatError("prtArrayOfPropertyValues missing cProperties", offset=reader.tell())
        c = int(reader.read_u32())
        if c == 0:
            return DecodedProperty(prid=prid, value=tuple(), rgdata_offset=rg_off, rgdata_length=4)

        if reader.remaining() < 4:
            raise OneStoreFormatError("prtArrayOfPropertyValues missing prid", offset=reader.tell())
        elem_prid = PropertyID.parse(reader)
        if elem_prid.prop_type != 0x11:
            msg = "prtArrayOfPropertyValues.prid.type MUST be 0x11 (PropertySet)"
            if ctx.strict:
                raise OneStoreFormatError(msg, offset=start)
            ctx.warn(msg, offset=start)

        items: list[DecodedPropertySet] = []
        for _ in range(c):
            items.append(_decode_property_set_from_reader(reader, cursor, ctx=ctx))

        length = int(reader.tell() - start)
        return DecodedProperty(prid=prid, value=tuple(items), rgdata_offset=rg_off, rgdata_length=length)

    # Nested PropertySet
    if t == 0x11:
        start = reader.tell()
        nested = _decode_property_set_from_reader(reader, cursor, ctx=ctx)
        length = int(reader.tell() - start)
        return DecodedProperty(prid=prid, value=nested, rgdata_offset=rg_off, rgdata_length=length)

    raise OneStoreFormatError(f"Unsupported PropertyID.type 0x{t:02X}", offset=reader.tell())


def decode_property_set(
    prop_set: PropertySet,
    *,
    oids: tuple[CompactID, ...],
    osids: tuple[CompactID, ...] | None,
    context_ids: tuple[CompactID, ...] | None,
    ctx: ParseContext,
) -> DecodedPropertySet:
    """Decode a structurally parsed PropertySet (Step 12) into typed values (Step 13).

    Reference values are returned as CompactID(s) extracted from the corresponding streams.
    No GUID resolution is done at this layer.
    """

    r = BinaryReader(prop_set.rg_data)
    cursor = _RefCursor(oids=oids, osids=osids, context_ids=context_ids)

    props: list[DecodedProperty] = []
    rgdata_start = r.tell()
    for prid in prop_set.rg_prids:
        props.append(_decode_one_property(prid, r, cursor, rgdata_start=rgdata_start, ctx=ctx))

    rem = int(r.remaining())
    if rem != 0:
        # ObjectSpaceObjectPropSet may include 0..7 bytes of zero padding after the PropertySet.
        # Treat that as acceptable even in strict mode.
        tail = r.peek_bytes(rem)
        if not (rem <= 7 and tail == b"\x00" * rem):
            msg = "PropertySet rgData was not fully consumed"
            if ctx.strict:
                raise OneStoreFormatError(msg, offset=r.tell())
            ctx.warn(msg, offset=r.tell())

    # These are not MUST-level invariants, but are useful sanity signals.
    if cursor.i_oid != len(cursor.oids):
        ctx.warn("OIDs stream was not fully consumed", offset=None)
    if cursor.osids is not None and cursor.i_osid != len(cursor.osids):
        ctx.warn("OSIDs stream was not fully consumed", offset=None)
    if cursor.context_ids is not None and cursor.i_ctx != len(cursor.context_ids):
        ctx.warn("ContextIDs stream was not fully consumed", offset=None)

    rgdata_size = len(prop_set.rg_data)
    encoded_size = 2 + 4 * int(prop_set.c_properties) + rgdata_size
    return DecodedPropertySet(
        c_properties=int(prop_set.c_properties),
        properties=tuple(props),
        rgdata_size=int(rgdata_size),
        encoded_size=int(encoded_size),
    )


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

        return cls(
            oids=oids,
            osids=osids,
            context_ids=context_ids,
            property_set=prop,
            padding=b"",
        )

    def decode_property_set(self, *, ctx: ParseContext) -> DecodedPropertySet:
        """Decode the embedded PropertySet using this prop set's reference streams."""

        return decode_property_set(
            self.property_set,
            oids=self.oids.body,
            osids=None if self.osids is None else self.osids.body,
            context_ids=None if self.context_ids is None else self.context_ids.body,
            ctx=ctx,
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
