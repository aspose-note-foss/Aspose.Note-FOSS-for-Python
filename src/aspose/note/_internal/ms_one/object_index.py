from __future__ import annotations

from dataclasses import dataclass

from ..onestore.common_types import CompactID, ExtendedGUID, JCID
from ..onestore.errors import OneStoreFormatError
from ..onestore.io import BinaryReader
from ..onestore.chunk_refs import FileChunkReference64x32
from ..onestore.file_node_list import parse_file_node_list_typed_nodes
from ..onestore.file_node_types import (
    DataSignatureGroupDefinitionFND,
    GlobalIdTableStart2FND,
    GlobalIdTableStartFNDX,
    ObjectGroupEndFND,
    ObjectDeclaration2LargeRefCountFND,
    ObjectDeclaration2RefCountFND,
    ObjectRevisionWithRefCount2FNDX,
    ObjectRevisionWithRefCountFNDX,
    ReadOnlyObjectDeclaration2LargeRefCountFND,
    ReadOnlyObjectDeclaration2RefCountFND,
)
from ..onestore.object_data import DecodedPropertySet, parse_object_space_object_prop_set_from_ref
from ..onestore.parse_context import ParseContext

from ..onestore import object_space as _os

from .compact_id import EffectiveGidTable, resolve_compact_id


def _resolve_reference_values(
    props: DecodedPropertySet,
    gid_table: dict[int, bytes] | None,
    *,
    ctx: ParseContext,
) -> DecodedPropertySet:
    """Resolve OID/OID-array property values to ExtendedGUIDs using the provided table.

    ObjectSpaceObjectPropSet decodes reference values as CompactIDs from its internal
    streams. Those CompactIDs are only meaningful relative to the Global ID Table that
    is in-scope at the point where the object group list entry was emitted, which can
    differ from the revision's effective table due to in-list table sequences.
    """

    if gid_table is None:
        return props

    # DecodedPropertySet is frozen; rebuild deterministically.
    from ..onestore.object_data import DecodedProperty, DecodedPropertySet as _DPS

    def _resolve_value(v):
        t2 = type(v)

        # Direct reference values.
        if isinstance(v, CompactID):
            return _os._resolve_compact_id_to_extended_guid(v, gid_table, ctx=ctx, offset=None)

        # Reference arrays.
        if isinstance(v, tuple) and v and isinstance(v[0], CompactID):
            return tuple(_os._resolve_compact_id_to_extended_guid(x, gid_table, ctx=ctx, offset=None) for x in v)

        # Nested PropertySet.
        if isinstance(v, _DPS):
            return _resolve_reference_values(v, gid_table, ctx=ctx)

        # Array of nested PropertySet(s).
        if isinstance(v, tuple) and v and isinstance(v[0], _DPS):
            return tuple(_resolve_reference_values(x, gid_table, ctx=ctx) for x in v)

        return v

    out: list[DecodedProperty] = []
    for p in props.properties:
        t = int(p.prid.prop_type)
        v = p.value
        # Fast-path common cases to keep behavior stable.
        if t == 0x09 and isinstance(v, tuple) and not v:
            out.append(DecodedProperty(prid=p.prid, value=tuple(), rgdata_offset=p.rgdata_offset, rgdata_length=p.rgdata_length))
            continue
        if t in (0x0B, 0x0D) and isinstance(v, tuple) and not v:
            out.append(DecodedProperty(prid=p.prid, value=tuple(), rgdata_offset=p.rgdata_offset, rgdata_length=p.rgdata_length))
            continue

        v2 = _resolve_value(v)
        if v2 is not v:
            out.append(DecodedProperty(prid=p.prid, value=v2, rgdata_offset=p.rgdata_offset, rgdata_length=p.rgdata_length))
        else:
            out.append(p)

    return DecodedPropertySet(
        c_properties=props.c_properties,
        properties=tuple(out),
        rgdata_size=props.rgdata_size,
        encoded_size=props.encoded_size,
    )


@dataclass(frozen=True, slots=True)
class ObjectRecord:
    oid: ExtendedGUID
    jcid: JCID | None
    properties: DecodedPropertySet | None
    ref_stp: int | None
    ref_cb: int | None


@dataclass(frozen=True, slots=True)
class ObjectIndex:
    objects_by_oid: dict[ExtendedGUID, ObjectRecord]

    def get(self, oid: ExtendedGUID) -> ObjectRecord | None:
        return self.objects_by_oid.get(oid)


def _is_prop_set_jcid(jcid: JCID | None) -> bool:
    return bool(jcid is not None and jcid.is_property_set)


def build_object_index_from_object_groups(
    data: bytes | bytearray | memoryview,
    object_groups: tuple[object, ...],
    *,
    effective_gid_table: EffectiveGidTable | None,
    last_count_by_list_id: dict[int, int],
    ctx: ParseContext,
) -> ObjectIndex:
    """Build an object index from revision manifest object groups.

    Assumption for v1: the chosen revision's object group list(s) contain enough
    declarations to reconstruct the current object graph for common .one files.
    """

    objects: dict[ExtendedGUID, ObjectRecord] = {}
    apply_object_groups(
        objects,
        data,
        object_groups,
        effective_gid_table=effective_gid_table,
        last_count_by_list_id=last_count_by_list_id,
        ctx=ctx,
    )
    return ObjectIndex(objects_by_oid=objects)


def apply_object_groups(
    objects: dict[ExtendedGUID, ObjectRecord],
    data: bytes | bytearray | memoryview,
    object_groups: tuple[object, ...],
    *,
    effective_gid_table: EffectiveGidTable | None,
    last_count_by_list_id: dict[int, int],
    ctx: ParseContext,
) -> None:
    """Apply object group list changes into an existing objects dict.

    This is used to build the effective object state for a target revision by
    replaying changes across the ridDependent chain.
    """

    initial_table = None if effective_gid_table is None else dict(effective_gid_table.by_index)

    # object_groups is expected to contain onestore.object_space.ObjectGroupSummary.
    for grp in object_groups:
        ref = getattr(grp, "ref", None)
        if ref is None:
            continue
        if int(getattr(ref, "cb", 0)) <= 0:
            continue

        group_list = parse_file_node_list_typed_nodes(
            BinaryReader(data),
            FileChunkReference64x32(stp=int(ref.stp), cb=int(ref.cb)),
            last_count_by_list_id=last_count_by_list_id,
            ctx=ctx,
        )

        current_table: dict[int, bytes] | None = initial_table

        i = 0
        while i < len(group_list.nodes):
            t = group_list.nodes[i].typed
            if t is None:
                i += 1
                continue

            if isinstance(t, (GlobalIdTableStartFNDX, GlobalIdTableStart2FND)):
                seq, new_i = _os._parse_global_id_table_sequence(list(group_list.nodes), i, ctx=ctx)
                current_table = _os._build_gid_table_from_sequence(
                    seq,
                    dependency=initial_table,
                    ctx=ctx,
                    offset=group_list.nodes[i].node.header.offset,
                )
                i = new_i
                continue

            if isinstance(t, ObjectGroupEndFND):
                break

            if isinstance(t, DataSignatureGroupDefinitionFND):
                i += 1
                continue

            change = t

            if not isinstance(
                change,
                (
                    ObjectDeclaration2RefCountFND,
                    ObjectDeclaration2LargeRefCountFND,
                    ReadOnlyObjectDeclaration2RefCountFND,
                    ReadOnlyObjectDeclaration2LargeRefCountFND,
                    ObjectRevisionWithRefCountFNDX,
                    ObjectRevisionWithRefCount2FNDX,
                ),
            ):
                i += 1
                continue

            ref2 = getattr(change, "ref", None)
            oid_compact: CompactID | None = getattr(change, "oid", None)
            jcid: JCID | None = getattr(change, "jcid", None)

            if isinstance(change, (ReadOnlyObjectDeclaration2RefCountFND, ReadOnlyObjectDeclaration2LargeRefCountFND)):
                jcid = change.base.jcid
                ref2 = change.base.ref
                oid_compact = change.base.oid

            if oid_compact is None:
                i += 1
                continue

            # Use onestore's resolver to mirror strict/tolerant semantics.
            oid = _os._resolve_compact_id_to_extended_guid(oid_compact, current_table, ctx=ctx, offset=None)

            if isinstance(change, (ObjectRevisionWithRefCountFNDX, ObjectRevisionWithRefCount2FNDX)):
                prior = objects.get(oid)
                prior_jcid = None if prior is None else prior.jcid
                ref_stp = None if ref2 is None else int(ref2.stp)
                ref_cb = None if ref2 is None else int(ref2.cb)

                props: DecodedPropertySet | None = None
                if _is_prop_set_jcid(prior_jcid) and ref_stp is not None and ref_cb is not None and ref_cb > 0:
                    try:
                        ps = parse_object_space_object_prop_set_from_ref(
                            data,
                            stp=ref_stp,
                            cb=ref_cb,
                            ctx=ctx,
                        )
                        props = _resolve_reference_values(ps.decode_property_set(ctx=ctx), current_table, ctx=ctx)
                    except OneStoreFormatError:
                        ctx.warn("Failed to decode ObjectSpaceObjectPropSet for object revision", offset=ref_stp)
                        props = None

                objects[oid] = ObjectRecord(
                    oid=oid,
                    jcid=prior_jcid,
                    properties=props if props is not None else (None if prior is None else prior.properties),
                    ref_stp=ref_stp,
                    ref_cb=ref_cb,
                )
                i += 1
                continue

            props: DecodedPropertySet | None = None
            ref_stp: int | None = None
            ref_cb: int | None = None

            if ref2 is not None:
                ref_stp = int(ref2.stp)
                ref_cb = int(ref2.cb)

            if _is_prop_set_jcid(jcid) and ref_stp is not None and ref_cb is not None and ref_cb > 0:
                try:
                    ps = parse_object_space_object_prop_set_from_ref(
                        data,
                        stp=ref_stp,
                        cb=ref_cb,
                        ctx=ctx,
                    )
                    props = _resolve_reference_values(ps.decode_property_set(ctx=ctx), current_table, ctx=ctx)
                except OneStoreFormatError:
                    ctx.warn("Failed to decode ObjectSpaceObjectPropSet for object", offset=ref_stp)
                    props = None

            objects[oid] = ObjectRecord(
                oid=oid,
                jcid=jcid,
                properties=props,
                ref_stp=ref_stp,
                ref_cb=ref_cb,
            )

            i += 1
            continue
