from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .common_types import CompactID, ExtendedGUID
from .chunk_refs import FileChunkReference64x32, FileNodeChunkReference
from .errors import OneStoreFormatError
from .file_node_list import parse_file_node_list_typed_nodes
from .file_node_types import TypedFileNode
from .file_node_types import (
    DEFAULT_CONTEXT_GCTXID,
    DataSignatureGroupDefinitionFND,
    GlobalIdTableEndFNDX,
    GlobalIdTableEntry2FNDX,
    GlobalIdTableEntry3FNDX,
    GlobalIdTableEntryFNDX,
    GlobalIdTableStart2FND,
    GlobalIdTableStartFNDX,
    ObjectDeclaration2LargeRefCountFND,
    ObjectDeclaration2RefCountFND,
    ObjectSpaceManifestListReferenceFND,
    ObjectSpaceManifestListStartFND,
    ObjectDataEncryptionKeyV2FNDX,
    ObjectGroupEndFND,
    ObjectGroupListReferenceFND,
    ObjectGroupStartFND,
    ObjectInfoDependencyOverridesFND,
    ObjectRevisionWithRefCount2FNDX,
    ObjectRevisionWithRefCountFNDX,
    ReadOnlyObjectDeclaration2LargeRefCountFND,
    ReadOnlyObjectDeclaration2RefCountFND,
    RevisionManifestEndFND,
    RevisionManifestListReferenceFND,
    RevisionManifestListStartFND,
    RevisionManifestStart4FND,
    RevisionManifestStart6FND,
    RevisionManifestStart7FND,
    RevisionRoleAndContextDeclarationFND,
    RevisionRoleDeclarationFND,
    RootObjectReference2FNDX,
    RootObjectReference3FND,
    RootFileNodeListManifests,
    build_root_file_node_list_manifests,
)
from .header import Header
from .io import BinaryReader
from .parse_context import ParseContext
from .txn_log import parse_transaction_log


@dataclass(frozen=True, slots=True)
class ObjectSpaceSummary:
    gosid: ExtendedGUID
    manifest_list_ref: FileNodeChunkReference
    revision_manifest_list_ref: FileNodeChunkReference


@dataclass(frozen=True, slots=True)
class OneStoreObjectSpacesSummary:
    root_gosid: ExtendedGUID
    object_spaces: tuple[ObjectSpaceSummary, ...]


@dataclass(frozen=True, slots=True)
class RevisionRoleContextPair:
    gctxid: ExtendedGUID
    revision_role: int


@dataclass(frozen=True, slots=True)
class RevisionSummary:
    rid: ExtendedGUID
    rid_dependent: ExtendedGUID
    gctxid: ExtendedGUID
    revision_role: int
    odcs_default: int
    has_encryption_marker: bool
    assigned_pairs: tuple[RevisionRoleContextPair, ...]
    encryption_key_ref: FileNodeChunkReference | None = None
    manifest: "RevisionManifestContentSummary | None" = None


@dataclass(frozen=True, slots=True)
class ObjectChangeSummary:
    data_signature_group: ExtendedGUID
    change: (
        ObjectDeclaration2RefCountFND
        | ObjectDeclaration2LargeRefCountFND
        | ReadOnlyObjectDeclaration2RefCountFND
        | ReadOnlyObjectDeclaration2LargeRefCountFND
        | ObjectRevisionWithRefCountFNDX
        | ObjectRevisionWithRefCount2FNDX
    )


@dataclass(frozen=True, slots=True)
class ObjectGroupSummary:
    object_group_id: ExtendedGUID
    ref: FileNodeChunkReference
    start_oid: ExtendedGUID
    changes: tuple[ObjectChangeSummary, ...]
    has_end: bool


@dataclass(frozen=True, slots=True)
class GlobalIdTableSequenceSummary:
    start: GlobalIdTableStartFNDX | GlobalIdTableStart2FND
    ops: tuple[GlobalIdTableEntryFNDX | GlobalIdTableEntry2FNDX | GlobalIdTableEntry3FNDX, ...]


@dataclass(frozen=True, slots=True)
class RevisionResolvedIdsSummary:
    """Step 11 output: resolved IDs without changing existing Step 10 models."""

    rid: ExtendedGUID
    rid_dependent: ExtendedGUID
    # Final effective table at the end of the revision manifest.
    # Stored as a deterministic sorted tuple (index -> guid bytes).
    effective_gid_table: tuple[tuple[int, bytes], ...]
    # Root objects resolved to ExtendedGUID (root_role -> oid).
    resolved_root_objects: tuple[tuple[int, ExtendedGUID], ...]
    # All object IDs encountered in changes (group lists + inline) resolved to ExtendedGUID.
    resolved_change_oids: tuple[ExtendedGUID, ...]


@dataclass(frozen=True, slots=True)
class ObjectSpaceResolvedIdsSummary:
    gosid: ExtendedGUID
    revisions: tuple[RevisionResolvedIdsSummary, ...]


@dataclass(frozen=True, slots=True)
class OneStoreObjectSpacesWithResolvedIds:
    root_gosid: ExtendedGUID
    object_spaces: tuple[ObjectSpaceResolvedIdsSummary, ...]


@dataclass(frozen=True, slots=True)
class RevisionManifestContentSummary:
    object_groups: tuple[ObjectGroupSummary, ...]
    global_id_table: GlobalIdTableSequenceSummary | None
    root_objects: tuple[RootObjectReference2FNDX | RootObjectReference3FND, ...]
    override_nodes: int
    inline_changes: tuple[ObjectChangeSummary, ...]


@dataclass(frozen=True, slots=True)
class ObjectSpaceRevisionsSummary:
    gosid: ExtendedGUID
    manifest_list_ref: FileNodeChunkReference
    revision_manifest_list_ref: FileNodeChunkReference
    revisions: tuple[RevisionSummary, ...]
    role_assignments: tuple[tuple[RevisionRoleContextPair, ExtendedGUID], ...]


@dataclass(frozen=True, slots=True)
class OneStoreObjectSpacesWithRevisions:
    root_gosid: ExtendedGUID
    object_spaces: tuple[ObjectSpaceRevisionsSummary, ...]


def _as_fcr64x32(ref: FileNodeChunkReference, *, offset: int | None = None) -> FileChunkReference64x32:
    # FileNodeChunkReference can be encoded with scaled formats; the parser already
    # expands to absolute stp/cb.
    stp = int(ref.stp)
    cb = int(ref.cb)

    if stp < 0 or stp > 0xFFFFFFFFFFFFFFFF:
        raise OneStoreFormatError("FileNodeChunkReference.stp is out of range", offset=offset)
    if cb < 0 or cb > 0xFFFFFFFF:
        raise OneStoreFormatError("FileNodeChunkReference.cb is out of range for FileChunkReference64x32", offset=offset)

    return FileChunkReference64x32(stp=stp, cb=cb)


def _require_first_typed_node(
    typed_nodes: tuple[TypedFileNode, ...], expected_type: type, *, message: str, offset: int | None
):
    if not typed_nodes:
        raise OneStoreFormatError(message, offset=offset)

    first = typed_nodes[0]
    if not isinstance(first.typed, expected_type):
        raise OneStoreFormatError(message, offset=first.node.header.offset)

    return first.typed


def parse_object_spaces_summary(
    data: bytes | bytearray | memoryview,
    *,
    ctx: ParseContext | None = None,
) -> OneStoreObjectSpacesSummary:
    """End-to-end object space bootstrap (Step 9).

    Parses:
    - Header
    - Transaction Log (for committed count limiting)
    - Root file node list manifests (0x004/0x008/0x090)
    - For each object space: its manifest list start (0x00C) and the last revision list ref (0x010)
    - The corresponding revision manifest list start (0x014)

    Returns a minimal deterministic summary structure. Revision manifests themselves
    are not parsed yet (Step 10).
    """

    if ctx is None:
        ctx = ParseContext(strict=True)

    # Establish file_size early and ensure header parsing MUSTs are enforced.
    header = Header.parse(BinaryReader(data), ctx=ctx)

    last_count_by_list_id = parse_transaction_log(BinaryReader(data), header, ctx=ctx)

    root_typed = parse_file_node_list_typed_nodes(
        BinaryReader(data),
        header.fcr_file_node_list_root,
        last_count_by_list_id=last_count_by_list_id,
        ctx=ctx,
    )

    manifests: RootFileNodeListManifests = build_root_file_node_list_manifests(root_typed.nodes, ctx=ctx)

    object_spaces: list[ObjectSpaceSummary] = []

    for os_ref in manifests.object_space_refs:
        if not isinstance(os_ref, ObjectSpaceManifestListReferenceFND):
            # Defensive: build_root_file_node_list_manifests guarantees types.
            continue

        manifest_list_fcr = _as_fcr64x32(os_ref.ref)
        os_manifest_list = parse_file_node_list_typed_nodes(
            BinaryReader(data),
            manifest_list_fcr,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ctx,
        )

        start = _require_first_typed_node(
            os_manifest_list.nodes,
            ObjectSpaceManifestListStartFND,
            message="Object space manifest list MUST start with ObjectSpaceManifestListStartFND",
            offset=manifest_list_fcr.stp,
        )

        if ctx.strict and start.gosid != os_ref.gosid:
            raise OneStoreFormatError(
                "ObjectSpaceManifestListStartFND.gosid MUST match the referring ObjectSpaceManifestListReferenceFND.gosid",
                offset=os_manifest_list.nodes[0].node.header.offset,
            )

        rev_refs: list[RevisionManifestListReferenceFND] = []
        for tn in os_manifest_list.nodes:
            if isinstance(tn.typed, RevisionManifestListReferenceFND):
                rev_refs.append(tn.typed)

        if not rev_refs:
            raise OneStoreFormatError(
                "Object space manifest list MUST contain at least one RevisionManifestListReferenceFND",
                offset=manifest_list_fcr.stp,
            )

        # Rule: if multiple refs exist, only the last one is active.
        last_rev_ref = rev_refs[-1]

        rev_list_fcr = _as_fcr64x32(last_rev_ref.ref)
        rev_list = parse_file_node_list_typed_nodes(
            BinaryReader(data),
            rev_list_fcr,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ctx,
        )

        rev_start = _require_first_typed_node(
            rev_list.nodes,
            RevisionManifestListStartFND,
            message="Revision manifest list MUST start with RevisionManifestListStartFND",
            offset=rev_list_fcr.stp,
        )

        if ctx.strict and rev_start.gosid != os_ref.gosid:
            raise OneStoreFormatError(
                "RevisionManifestListStartFND.gosid MUST match object space gosid",
                offset=rev_list.nodes[0].node.header.offset,
            )

        object_spaces.append(
            ObjectSpaceSummary(
                gosid=os_ref.gosid,
                manifest_list_ref=os_ref.ref,
                revision_manifest_list_ref=last_rev_ref.ref,
            )
        )

    return OneStoreObjectSpacesSummary(
        root_gosid=manifests.root.gosid_root,
        object_spaces=tuple(object_spaces),
    )


def _eg_sort_key(eg: ExtendedGUID) -> tuple[bytes, int]:
    return (eg.guid, int(eg.n))


def _pair_sort_key(pair: RevisionRoleContextPair) -> tuple[bytes, int, int]:
    g, n = _eg_sort_key(pair.gctxid)
    return (g, n, int(pair.revision_role))


def _parse_revision_manifest_list_revisions(
    data: bytes | bytearray | memoryview,
    nodes: tuple[TypedFileNode, ...],
    *,
    last_count_by_list_id: dict[int, int],
    ctx: ParseContext,
) -> tuple[tuple[RevisionSummary, ...], tuple[tuple[RevisionRoleContextPair, ExtendedGUID], ...]]:
    if not nodes:
        raise OneStoreFormatError("Revision manifest list is empty", offset=0)
    if not isinstance(nodes[0].typed, RevisionManifestListStartFND):
        raise OneStoreFormatError(
            "Revision manifest list MUST start with RevisionManifestListStartFND",
            offset=nodes[0].node.header.offset,
        )

    started_rids: set[ExtendedGUID] = set()
    revisions: list[RevisionSummary] = []

    # Last assignment wins for (context, role) -> rid.
    role_assignments: dict[RevisionRoleContextPair, ExtendedGUID] = {}

    current_rid: ExtendedGUID | None = None
    current_rid_dependent: ExtendedGUID | None = None
    current_gctxid: ExtendedGUID | None = None
    current_revision_role: int | None = None
    current_odcs_default: int | None = None
    current_has_encryption_marker = False
    current_encryption_ref: FileNodeChunkReference | None = None
    current_encryption_required = False
    current_manifest_pos = 0
    current_manifest_nodes: list[TypedFileNode] = []
    current_start_kind: str | None = None

    # Temporary map, finalized after role assignments are known.
    revision_index_by_rid: dict[ExtendedGUID, int] = {}

    for tn in nodes[1:]:
        typed = tn.typed

        if current_rid is None:
            # Outside a revision manifest.
            if isinstance(typed, (RevisionManifestStart4FND, RevisionManifestStart6FND, RevisionManifestStart7FND)):
                if isinstance(typed, RevisionManifestStart7FND):
                    rid = typed.base.rid
                    rid_dependent = typed.base.rid_dependent
                    gctxid = typed.gctxid
                    revision_role = typed.base.revision_role
                    odcs_default = typed.base.odcs_default
                elif isinstance(typed, RevisionManifestStart6FND):
                    rid = typed.rid
                    rid_dependent = typed.rid_dependent
                    gctxid = DEFAULT_CONTEXT_GCTXID
                    revision_role = typed.revision_role
                    odcs_default = typed.odcs_default
                else:
                    rid = typed.rid
                    rid_dependent = typed.rid_dependent
                    gctxid = DEFAULT_CONTEXT_GCTXID
                    revision_role = typed.revision_role
                    odcs_default = typed.odcs_default

                if rid.is_zero():
                    raise OneStoreFormatError("RevisionManifestStart*.rid MUST NOT be zero", offset=tn.node.header.offset)

                if rid in started_rids:
                    raise OneStoreFormatError(
                        "RevisionManifestStart*.rid MUST be unique within the revision manifest list",
                        offset=tn.node.header.offset,
                    )

                if not rid_dependent.is_zero() and rid_dependent not in started_rids:
                    raise OneStoreFormatError(
                        "ridDependent MUST refer to a previously declared revision in the same revision manifest list",
                        offset=tn.node.header.offset,
                    )

                started_rids.add(rid)

                current_rid = rid
                current_rid_dependent = rid_dependent
                current_gctxid = gctxid
                current_revision_role = int(revision_role)
                current_odcs_default = int(odcs_default)
                current_has_encryption_marker = False
                current_encryption_ref = None
                current_encryption_required = int(odcs_default) == 0x0002
                current_manifest_pos = 1
                current_manifest_nodes = []
                current_start_kind = "onetoc2" if isinstance(typed, RevisionManifestStart4FND) else "one"
                continue

            if isinstance(typed, RevisionManifestEndFND):
                raise OneStoreFormatError(
                    "RevisionManifestEndFND without a matching start",
                    offset=tn.node.header.offset,
                )

            if isinstance(typed, RevisionRoleDeclarationFND):
                if typed.rid not in started_rids:
                    raise OneStoreFormatError(
                        "RevisionRoleDeclarationFND.rid MUST refer to a preceding revision manifest in this list",
                        offset=tn.node.header.offset,
                    )
                key = RevisionRoleContextPair(gctxid=DEFAULT_CONTEXT_GCTXID, revision_role=int(typed.revision_role))
                role_assignments[key] = typed.rid
                continue

            if isinstance(typed, RevisionRoleAndContextDeclarationFND):
                if typed.rid not in started_rids:
                    raise OneStoreFormatError(
                        "RevisionRoleAndContextDeclarationFND.rid MUST refer to a preceding revision manifest in this list",
                        offset=tn.node.header.offset,
                    )
                key = RevisionRoleContextPair(gctxid=typed.gctxid, revision_role=int(typed.revision_role))
                role_assignments[key] = typed.rid
                continue

            if isinstance(typed, ObjectDataEncryptionKeyV2FNDX):
                # Encryption marker outside a manifest is unexpected; keep parsing safely.
                ctx.warn("ObjectDataEncryptionKeyV2FNDX appears outside a revision manifest", offset=tn.node.header.offset)
                continue

            # Other nodes (object data, unknown types) are ignored at this stage.
            continue

        # Inside a revision manifest.
        current_manifest_pos += 1
        current_manifest_nodes.append(tn)

        if current_manifest_pos == 2:
            if current_encryption_required and not isinstance(typed, ObjectDataEncryptionKeyV2FNDX):
                raise OneStoreFormatError(
                    "Encrypted revision manifest MUST have ObjectDataEncryptionKeyV2FNDX as the second FileNode",
                    offset=tn.node.header.offset,
                )
            if isinstance(typed, ObjectDataEncryptionKeyV2FNDX):
                current_has_encryption_marker = True
                current_encryption_ref = typed.ref
        else:
            if isinstance(typed, ObjectDataEncryptionKeyV2FNDX):
                ctx.warn(
                    "ObjectDataEncryptionKeyV2FNDX appears not as the second node in a revision manifest",
                    offset=tn.node.header.offset,
                )
                current_has_encryption_marker = True
                current_encryption_ref = typed.ref

        if isinstance(typed, (RevisionRoleDeclarationFND, RevisionRoleAndContextDeclarationFND)):
            raise OneStoreFormatError(
                "Revision role declarations MUST be outside revision manifest boundaries",
                offset=tn.node.header.offset,
            )

        if isinstance(typed, RevisionManifestEndFND):
            assert current_rid is not None
            assert current_rid_dependent is not None
            assert current_gctxid is not None
            assert current_revision_role is not None
            assert current_odcs_default is not None

            idx = len(revisions)
            revision_index_by_rid[current_rid] = idx

            # Parse manifest content (Step 11): for .one/.onetoc2, still without object data decoding.
            content = _parse_revision_manifest_content(
                data,
                current_manifest_nodes,
                start_kind=current_start_kind,
                last_count_by_list_id=last_count_by_list_id,
                ctx=ctx,
            )

            revisions.append(
                RevisionSummary(
                    rid=current_rid,
                    rid_dependent=current_rid_dependent,
                    gctxid=current_gctxid,
                    revision_role=int(current_revision_role),
                    odcs_default=int(current_odcs_default),
                    has_encryption_marker=bool(current_has_encryption_marker),
                    encryption_key_ref=current_encryption_ref,
                    assigned_pairs=(),
                    manifest=content,
                )
            )

            current_rid = None
            current_rid_dependent = None
            current_gctxid = None
            current_revision_role = None
            current_odcs_default = None
            current_has_encryption_marker = False
            current_encryption_ref = None
            current_encryption_required = False
            current_manifest_pos = 0
            current_manifest_nodes = []
            current_start_kind = None
            continue

    if current_rid is not None:
        raise OneStoreFormatError(
            "Revision manifest list ended inside a revision manifest (missing RevisionManifestEndFND)",
            offset=nodes[-1].node.header.offset,
        )

    # Finalize assigned_pairs per revision based on last-assignment table.
    pairs_by_rid: dict[ExtendedGUID, list[RevisionRoleContextPair]] = {}
    for pair, rid in role_assignments.items():
        pairs_by_rid.setdefault(rid, []).append(pair)

    finalized: list[RevisionSummary] = []
    for rev in revisions:
        pairs = pairs_by_rid.get(rev.rid, [])
        pairs_sorted = tuple(sorted(pairs, key=_pair_sort_key))
        finalized.append(
            RevisionSummary(
                rid=rev.rid,
                rid_dependent=rev.rid_dependent,
                gctxid=rev.gctxid,
                revision_role=rev.revision_role,
                odcs_default=rev.odcs_default,
                has_encryption_marker=rev.has_encryption_marker,
                encryption_key_ref=rev.encryption_key_ref,
                assigned_pairs=pairs_sorted,
                manifest=rev.manifest,
            )
        )

    assignments_sorted = tuple(
        sorted(
            ((pair, rid) for pair, rid in role_assignments.items()),
            key=lambda pr: (_pair_sort_key(pr[0]), _eg_sort_key(pr[1])),
        )
    )

    return (tuple(finalized), assignments_sorted)


def _resolve_zero_eg() -> ExtendedGUID:
    return ExtendedGUID(guid=b"\x00" * 16, n=0)


def _is_nil_ref(ref: FileNodeChunkReference) -> bool:
    return ref.cb == 0 and ref.stp in (0, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF)


def _parse_object_group_list(
    data: bytes | bytearray | memoryview,
    ref: FileNodeChunkReference,
    object_group_id: ExtendedGUID,
    *,
    last_count_by_list_id: dict[int, int],
    ctx: ParseContext,
) -> ObjectGroupSummary:
    if _is_nil_ref(ref):
        raise OneStoreFormatError("ObjectGroupListReferenceFND ref MUST NOT be fcrNil", offset=0)

    group_list_fcr = _as_fcr64x32(ref)
    group_list = parse_file_node_list_typed_nodes(
        BinaryReader(data),
        group_list_fcr,
        last_count_by_list_id=last_count_by_list_id,
        ctx=ctx,
    )

    start = _require_first_typed_node(
        group_list.nodes,
        ObjectGroupStartFND,
        message="Object group list MUST start with ObjectGroupStartFND",
        offset=group_list_fcr.stp,
    )

    if ctx.strict and start.oid != object_group_id:
        raise OneStoreFormatError(
            "ObjectGroupStartFND.oid MUST match the referring ObjectGroupListReferenceFND.ObjectGroupID",
            offset=group_list.nodes[0].node.header.offset,
        )
    if not ctx.strict and start.oid != object_group_id:
        ctx.warn(
            "ObjectGroupStartFND.oid does not match ObjectGroupListReferenceFND.ObjectGroupID",
            offset=group_list.nodes[0].node.header.offset,
        )

    zero_sig = _resolve_zero_eg()
    current_sig = zero_sig
    changes: list[ObjectChangeSummary] = []
    has_end = False

    for tn in group_list.nodes[1:]:
        t = tn.typed
        if isinstance(t, DataSignatureGroupDefinitionFND):
            current_sig = t.data_signature_group
            continue
        if isinstance(t, ObjectGroupEndFND):
            has_end = True
            break
        if isinstance(
            t,
            (
                ObjectDeclaration2RefCountFND,
                ObjectDeclaration2LargeRefCountFND,
                ReadOnlyObjectDeclaration2RefCountFND,
                ReadOnlyObjectDeclaration2LargeRefCountFND,
                ObjectRevisionWithRefCountFNDX,
                ObjectRevisionWithRefCount2FNDX,
            ),
        ):
            changes.append(ObjectChangeSummary(data_signature_group=current_sig, change=t))

    # Determinism: keep original order but store as tuple.
    return ObjectGroupSummary(
        object_group_id=object_group_id,
        ref=ref,
        start_oid=start.oid,
        changes=tuple(changes),
        has_end=has_end,
    )


def _resolve_oids_in_object_group_list(
    data: bytes | bytearray | memoryview,
    ref: FileNodeChunkReference,
    *,
    initial_table: dict[int, bytes] | None,
    last_count_by_list_id: dict[int, int],
    ctx: ParseContext,
) -> tuple[ExtendedGUID, ...]:
    """Resolve CompactIDs inside an object group list, honoring in-list GID table scope.

    Object group lists are separate file node lists; real-world files can include
    GlobalIdTableStart* sequences inside these lists.
    """

    if _is_nil_ref(ref):
        raise OneStoreFormatError("ObjectGroupListReferenceFND ref MUST NOT be fcrNil", offset=0)

    group_list_fcr = _as_fcr64x32(ref)
    group_list = parse_file_node_list_typed_nodes(
        BinaryReader(data),
        group_list_fcr,
        last_count_by_list_id=last_count_by_list_id,
        ctx=ctx,
    )

    if not group_list.nodes:
        return ()

    current_table: dict[int, bytes] | None = initial_table
    resolved: list[ExtendedGUID] = []

    i = 0
    while i < len(group_list.nodes):
        t = group_list.nodes[i].typed
        if t is None:
            i += 1
            continue

        if isinstance(t, (GlobalIdTableStartFNDX, GlobalIdTableStart2FND)):
            seq, new_i = _parse_global_id_table_sequence(list(group_list.nodes), i, ctx=ctx)
            current_table = _build_gid_table_from_sequence(
                seq,
                dependency=initial_table,
                ctx=ctx,
                offset=group_list.nodes[i].node.header.offset,
            )
            i = new_i
            continue

        if isinstance(t, ObjectGroupEndFND):
            break

        # Resolve CompactIDs in known object change node types.
        for oid in _iter_compact_ids_from_change(t):
            resolved.append(_resolve_compact_id_to_extended_guid(oid, current_table, ctx=ctx, offset=None))

        i += 1

    return tuple(resolved)


def _parse_global_id_table_sequence(
    manifest_nodes: list[TypedFileNode],
    start_index: int,
    *,
    ctx: ParseContext,
) -> tuple[GlobalIdTableSequenceSummary, int]:
    start_t = manifest_nodes[start_index].typed
    assert isinstance(start_t, (GlobalIdTableStartFNDX, GlobalIdTableStart2FND))

    ops: list[GlobalIdTableEntryFNDX | GlobalIdTableEntry2FNDX | GlobalIdTableEntry3FNDX] = []

    # MUST: destination indices must be unique within a sequence.
    # Avoid O(cEntriesToCopy) validation by tracking destination intervals.
    dest_points: set[int] = set()
    dest_ranges: list[tuple[int, int]] = []  # inclusive

    def _dest_has_overlap(start: int, end: int) -> bool:
        if start > end:
            return False
        for p in dest_points:
            if start <= p <= end:
                return True
        for a, b in dest_ranges:
            if not (end < a or b < start):
                return True
        return False

    def _dest_add_point(p: int) -> None:
        if _dest_has_overlap(p, p):
            raise OneStoreFormatError(
                "Global ID table destination index MUST be unique within a sequence",
                offset=manifest_nodes[i].node.header.offset,
            )
        dest_points.add(p)

    def _dest_add_range(start: int, end: int) -> None:
        if start > end:
            return
        if _dest_has_overlap(start, end):
            raise OneStoreFormatError(
                "Global ID table destination index range MUST NOT overlap within a sequence",
                offset=manifest_nodes[i].node.header.offset,
            )
        dest_ranges.append((start, end))

    # MUST: direct GUID values must be unique within a sequence.
    # For 0x025/0x026, GUID uniqueness depends on the dependency revision and is validated later.
    seen_direct_guid: set[bytes] = set()

    i = start_index + 1
    while i < len(manifest_nodes):
        t = manifest_nodes[i].typed
        if isinstance(t, GlobalIdTableEndFNDX):
            return (GlobalIdTableSequenceSummary(start=start_t, ops=tuple(ops)), i + 1)
        if isinstance(t, (GlobalIdTableStartFNDX, GlobalIdTableStart2FND)):
            raise OneStoreFormatError(
                "GlobalIdTableStart* encountered before GlobalIdTableEndFNDX",
                offset=manifest_nodes[i].node.header.offset,
            )
        if isinstance(t, GlobalIdTableEntryFNDX):
            _dest_add_point(int(t.index))
            if t.guid in seen_direct_guid:
                raise OneStoreFormatError(
                    "GlobalIdTableEntryFNDX.guid MUST be unique within a sequence",
                    offset=manifest_nodes[i].node.header.offset,
                )
            seen_direct_guid.add(t.guid)
            ops.append(t)
            i += 1
            continue
        if isinstance(t, GlobalIdTableEntry2FNDX):
            for v in (int(t.index_map_from), int(t.index_map_to)):
                if v >= 0xFFFFFF:
                    msg = "GlobalIdTableEntry2FNDX indices MUST be < 0xFFFFFF"
                    if ctx.strict:
                        raise OneStoreFormatError(msg, offset=manifest_nodes[i].node.header.offset)
                    ctx.warn(msg, offset=manifest_nodes[i].node.header.offset)
                    break
            _dest_add_point(int(t.index_map_to))
            ops.append(t)
            i += 1
            continue

        if isinstance(t, GlobalIdTableEntry3FNDX):
            for v in (int(t.index_copy_from_start), int(t.index_copy_to_start)):
                if v >= 0xFFFFFF:
                    msg = "GlobalIdTableEntry3FNDX indices MUST be < 0xFFFFFF"
                    if ctx.strict:
                        raise OneStoreFormatError(msg, offset=manifest_nodes[i].node.header.offset)
                    ctx.warn(msg, offset=manifest_nodes[i].node.header.offset)
                    break
            c = int(t.entries_to_copy)
            if c < 0:
                raise OneStoreFormatError(
                    "GlobalIdTableEntry3FNDX.cEntriesToCopy MUST be non-negative",
                    offset=manifest_nodes[i].node.header.offset,
                )
            if c > 0:
                end = int(t.index_copy_to_start) + c - 1
                if end >= 0xFFFFFF:
                    msg = "GlobalIdTableEntry3FNDX destination range MUST be < 0xFFFFFF"
                    if ctx.strict:
                        raise OneStoreFormatError(msg, offset=manifest_nodes[i].node.header.offset)
                    ctx.warn(msg, offset=manifest_nodes[i].node.header.offset)
                _dest_add_range(int(t.index_copy_to_start), end)
            ops.append(t)
            i += 1
            continue

        raise OneStoreFormatError(
            "Unexpected FileNode inside global id table sequence",
            offset=manifest_nodes[i].node.header.offset,
        )

    raise OneStoreFormatError(
        "Global id table sequence missing GlobalIdTableEndFNDX",
        offset=manifest_nodes[-1].node.header.offset if manifest_nodes else 0,
    )


def _parse_revision_manifest_content(
    data: bytes | bytearray | memoryview,
    manifest_nodes: list[TypedFileNode],
    *,
    start_kind: str | None,
    last_count_by_list_id: dict[int, int],
    ctx: ParseContext,
) -> RevisionManifestContentSummary:
    object_groups: list[ObjectGroupSummary] = []
    root_objects: list[RootObjectReference2FNDX | RootObjectReference3FND] = []
    inline_changes: list[ObjectChangeSummary] = []
    override_nodes = 0
    gid_table: GlobalIdTableSequenceSummary | None = None

    zero_sig = _resolve_zero_eg()
    current_sig = zero_sig

    # State machine based on docs/ms-onestore/17-revision-manifest-parsing.md.
    # We keep it strict on ordering but permissive on unknown nodes.
    phase = "pre"  # pre (groups) -> post_roots (no groups, no gid start) ; post_gid behaves like post_roots
    i = 0
    while i < len(manifest_nodes):
        t = manifest_nodes[i].typed
        if t is None:
            i += 1
            continue

        # Skip encryption marker here (already validated positionally above).
        if isinstance(t, ObjectDataEncryptionKeyV2FNDX):
            i += 1
            continue

        if isinstance(t, ObjectInfoDependencyOverridesFND):
            override_nodes += 1
            i += 1
            continue

        if isinstance(t, DataSignatureGroupDefinitionFND):
            current_sig = t.data_signature_group
            i += 1
            continue

        if isinstance(t, ObjectGroupListReferenceFND):
            if start_kind != "one":
                raise OneStoreFormatError(
                    "ObjectGroupListReferenceFND is only expected in .one revision manifests",
                    offset=manifest_nodes[i].node.header.offset,
                )
            if phase != "pre":
                raise OneStoreFormatError(
                    "Object group sequences MUST appear before the global id table and before root refs",
                    offset=manifest_nodes[i].node.header.offset,
                )
            if i + 1 >= len(manifest_nodes) or not isinstance(manifest_nodes[i + 1].typed, ObjectInfoDependencyOverridesFND):
                raise OneStoreFormatError(
                    "ObjectGroupListReferenceFND MUST be immediately followed by ObjectInfoDependencyOverridesFND",
                    offset=manifest_nodes[i].node.header.offset,
                )
            grp = _parse_object_group_list(
                data,
                t.ref,
                t.object_group_id,
                last_count_by_list_id=last_count_by_list_id,
                ctx=ctx,
            )
            object_groups.append(grp)
            override_nodes += 1
            i += 2
            continue

        if isinstance(t, (GlobalIdTableStartFNDX, GlobalIdTableStart2FND)):
            if gid_table is not None:
                raise OneStoreFormatError(
                    "Revision manifest MUST contain at most one global id table sequence",
                    offset=manifest_nodes[i].node.header.offset,
                )
            if phase != "pre":
                raise OneStoreFormatError(
                    "Global id table sequence MUST appear before root refs and object declarations",
                    offset=manifest_nodes[i].node.header.offset,
                )
            gid_table, new_i = _parse_global_id_table_sequence(manifest_nodes, i, ctx=ctx)
            phase = "post_roots"
            i = new_i
            continue

        if isinstance(t, RootObjectReference3FND):
            if start_kind == "onetoc2":
                raise OneStoreFormatError(
                    "RootObjectReference3FND is not expected in .onetoc2 revision manifests",
                    offset=manifest_nodes[i].node.header.offset,
                )
            root_objects.append(t)
            phase = "post_roots"
            i += 1
            continue

        if isinstance(t, RootObjectReference2FNDX):
            if start_kind != "onetoc2":
                raise OneStoreFormatError(
                    "RootObjectReference2FNDX is only expected in .onetoc2 revision manifests",
                    offset=manifest_nodes[i].node.header.offset,
                )
            if gid_table is not None:
                # Per doc 17, root refs precede global id table in .onetoc2.
                msg = "RootObjectReference2FNDX appeared after the global id table"
                if ctx.strict:
                    raise OneStoreFormatError(msg, offset=manifest_nodes[i].node.header.offset)
                ctx.warn(msg, offset=manifest_nodes[i].node.header.offset)
            root_objects.append(t)
            i += 1
            continue

        if isinstance(
            t,
            (
                ObjectDeclaration2RefCountFND,
                ObjectDeclaration2LargeRefCountFND,
                ReadOnlyObjectDeclaration2RefCountFND,
                ReadOnlyObjectDeclaration2LargeRefCountFND,
                ObjectRevisionWithRefCountFNDX,
                ObjectRevisionWithRefCount2FNDX,
            ),
        ):
            if start_kind != "onetoc2":
                # In .one these typically live in object group lists, not inline.
                ctx.warn(
                    "Object declaration/revision node encountered inline in a .one revision manifest",
                    offset=manifest_nodes[i].node.header.offset,
                )
            if gid_table is None:
                msg = "Object declarations/revisions MUST follow the global id table sequence"
                if ctx.strict:
                    raise OneStoreFormatError(msg, offset=manifest_nodes[i].node.header.offset)
                ctx.warn(msg, offset=manifest_nodes[i].node.header.offset)
            inline_changes.append(ObjectChangeSummary(data_signature_group=current_sig, change=t))
            phase = "post_roots"
            i += 1
            continue

        # Unknown/unsupported nodes are ignored for now (object data, etc.).
        i += 1

    # RootRole uniqueness within a manifest.
    seen_roles: set[int] = set()
    for ro in root_objects:
        if ro.root_role in seen_roles:
            msg = "RootRole MUST NOT appear more than once within a revision manifest"
            if ctx.strict:
                raise OneStoreFormatError(msg, offset=0)
            ctx.warn(msg, offset=0)
        seen_roles.add(ro.root_role)

    return RevisionManifestContentSummary(
        object_groups=tuple(object_groups),
        global_id_table=gid_table,
        root_objects=tuple(root_objects),
        override_nodes=int(override_nodes),
        inline_changes=tuple(inline_changes),
    )


def _sorted_gid_table_items(table: dict[int, bytes]) -> tuple[tuple[int, bytes], ...]:
    return tuple(sorted(((int(k), bytes(v)) for k, v in table.items()), key=lambda kv: kv[0]))


def _resolve_compact_id_to_extended_guid(
    oid: CompactID,
    table: dict[int, bytes] | None,
    *,
    ctx: ParseContext,
    offset: int | None,
) -> ExtendedGUID:
    if table is None:
        msg = "CompactID resolution requires an in-scope Global ID Table"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=offset)
        ctx.warn(msg, offset=offset)
        return ExtendedGUID(guid=b"\x00" * 16, n=int(oid.n))

    guid = table.get(int(oid.guid_index))
    if guid is None:
        msg = f"CompactID.guidIndex {int(oid.guid_index)} is not present in the effective Global ID Table"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=offset)
        ctx.warn(msg, offset=offset)
        return ExtendedGUID(guid=b"\x00" * 16, n=int(oid.n))

    return ExtendedGUID(guid=guid, n=int(oid.n))


def _build_gid_table_from_sequence(
    seq: GlobalIdTableSequenceSummary,
    *,
    dependency: dict[int, bytes] | None,
    ctx: ParseContext,
    offset: int | None,
) -> dict[int, bytes]:
    """Build a new table from a single global id table sequence.

    The table is defined by the sequence entries. Operations 0x025/0x026 pull
    entries from the dependency table.
    """

    table: dict[int, bytes] = {}
    guid_to_index: dict[bytes, int] = {}

    def _add(index: int, guid: bytes) -> None:
        if index >= 0xFFFFFF:
            msg = "Global ID Table index MUST be < 0xFFFFFF"
            if ctx.strict:
                raise OneStoreFormatError(msg, offset=offset)
            ctx.warn(msg, offset=offset)
            return
        if index in table:
            raise OneStoreFormatError("Global ID Table indices MUST be unique", offset=offset)
        if guid in guid_to_index:
            raise OneStoreFormatError("Global ID Table GUIDs MUST be unique", offset=offset)
        table[index] = guid
        guid_to_index[guid] = index

    dep = dependency

    for op in seq.ops:
        if isinstance(op, GlobalIdTableEntryFNDX):
            _add(int(op.index), bytes(op.guid))
            continue

        if isinstance(op, GlobalIdTableEntry2FNDX):
            if dep is None:
                msg = "GlobalIdTableEntry2FNDX requires a dependency revision Global ID Table"
                if ctx.strict:
                    raise OneStoreFormatError(msg, offset=offset)
                ctx.warn(msg, offset=offset)
                continue

            frm = int(op.index_map_from)
            to = int(op.index_map_to)
            if frm >= 0xFFFFFF or to >= 0xFFFFFF:
                msg = "GlobalIdTableEntry2FNDX indices MUST be < 0xFFFFFF"
                if ctx.strict:
                    raise OneStoreFormatError(msg, offset=offset)
                ctx.warn(msg, offset=offset)
                continue

            g = dep.get(frm)
            if g is None:
                raise OneStoreFormatError(
                    "GlobalIdTableEntry2FNDX.iIndexMapFrom MUST exist in the dependency table",
                    offset=offset,
                )
            _add(to, g)
            continue

        if isinstance(op, GlobalIdTableEntry3FNDX):
            if dep is None:
                msg = "GlobalIdTableEntry3FNDX requires a dependency revision Global ID Table"
                if ctx.strict:
                    raise OneStoreFormatError(msg, offset=offset)
                ctx.warn(msg, offset=offset)
                continue

            frm0 = int(op.index_copy_from_start)
            to0 = int(op.index_copy_to_start)
            count = int(op.entries_to_copy)
            if frm0 >= 0xFFFFFF or to0 >= 0xFFFFFF:
                msg = "GlobalIdTableEntry3FNDX indices MUST be < 0xFFFFFF"
                if ctx.strict:
                    raise OneStoreFormatError(msg, offset=offset)
                ctx.warn(msg, offset=offset)
                continue
            if count < 0:
                raise OneStoreFormatError("GlobalIdTableEntry3FNDX.cEntriesToCopy MUST be non-negative", offset=offset)
            if count == 0:
                continue
            if to0 + count - 1 >= 0xFFFFFF:
                msg = "GlobalIdTableEntry3FNDX destination indices MUST be < 0xFFFFFF"
                if ctx.strict:
                    raise OneStoreFormatError(msg, offset=offset)
                ctx.warn(msg, offset=offset)
                continue

            for k in range(count):
                frm = frm0 + k
                to = to0 + k
                g = dep.get(frm)
                if g is None:
                    raise OneStoreFormatError(
                        "GlobalIdTableEntry3FNDX source range MUST exist in the dependency table",
                        offset=offset,
                    )
                _add(to, g)
            continue

    return table


def _iter_compact_ids_from_change(change: object) -> Iterable[CompactID]:
    # CompactIDs appear in ObjectDeclaration2* and ObjectRevisionWithRefCount*.
    if isinstance(change, ObjectDeclaration2RefCountFND):
        yield change.oid
    elif isinstance(change, ObjectDeclaration2LargeRefCountFND):
        yield change.oid
    elif isinstance(change, ReadOnlyObjectDeclaration2RefCountFND):
        yield change.base.oid
    elif isinstance(change, ReadOnlyObjectDeclaration2LargeRefCountFND):
        yield change.base.oid
    elif isinstance(change, ObjectRevisionWithRefCountFNDX):
        yield change.oid
    elif isinstance(change, ObjectRevisionWithRefCount2FNDX):
        yield change.oid


def parse_object_spaces_with_resolved_ids(
    data: bytes | bytearray | memoryview,
    *,
    ctx: ParseContext | None = None,
) -> OneStoreObjectSpacesWithResolvedIds:
    """Step 11 helper: builds effective Global ID Tables and resolves CompactIDs.

    This does not modify the Step 10 output dataclasses.
    """

    if ctx is None:
        ctx = ParseContext(strict=True)

    # We need last_count_by_list_id for re-parsing referenced object group lists.
    header = Header.parse(BinaryReader(data), ctx=ctx)
    last_count_by_list_id = parse_transaction_log(BinaryReader(data), header, ctx=ctx)

    step10 = parse_object_spaces_with_revisions(data, ctx=ctx)

    out_object_spaces: list[ObjectSpaceResolvedIdsSummary] = []

    for os in step10.object_spaces:
        # rid -> effective table at end of the manifest
        tables_by_rid: dict[ExtendedGUID, dict[int, bytes]] = {}
        resolved_revs: list[RevisionResolvedIdsSummary] = []

        for rev in os.revisions:
            dep_table: dict[int, bytes] | None = None
            if not rev.rid_dependent.is_zero():
                dep_table = tables_by_rid.get(rev.rid_dependent)
                if dep_table is None:
                    # Defensive: Step 10 already enforces ridDependent ordering.
                    raise OneStoreFormatError(
                        "ridDependent MUST refer to a previously built revision table",
                        offset=None,
                    )

            # Base table (fallback) comes from the dependency revision.
            table_before = dep_table

            table_after = table_before
            if rev.manifest is not None and rev.manifest.global_id_table is not None:
                table_after = _build_gid_table_from_sequence(
                    rev.manifest.global_id_table,
                    dependency=dep_table,
                    ctx=ctx,
                    offset=None,
                )

            # End-of-manifest effective table: if a sequence exists, it becomes active; otherwise keep dependency.
            effective = table_after
            tables_by_rid[rev.rid] = {} if effective is None else dict(effective)

            resolved_root_objects: list[tuple[int, ExtendedGUID]] = []
            resolved_change_oids: list[ExtendedGUID] = []

            if rev.manifest is not None:
                # Resolve CompactIDs using the revision's effective table when available.
                table_for_revision = table_after if table_after is not None else table_before

                # Root refs.
                for ro in rev.manifest.root_objects:
                    if isinstance(ro, RootObjectReference3FND):
                        resolved_root_objects.append((int(ro.root_role), ro.oid_root))
                    elif isinstance(ro, RootObjectReference2FNDX):
                        eg = _resolve_compact_id_to_extended_guid(
                            ro.oid_root,
                            table_for_revision,
                            ctx=ctx,
                            offset=None,
                        )
                        resolved_root_objects.append((int(ro.root_role), eg))

                # Object group changes (from referenced lists).
                for grp in rev.manifest.object_groups:
                    resolved_change_oids.extend(
                        _resolve_oids_in_object_group_list(
                            data,
                            grp.ref,
                            initial_table=table_for_revision,
                            last_count_by_list_id=last_count_by_list_id,
                            ctx=ctx,
                        )
                    )

                # Inline changes.
                for ch in rev.manifest.inline_changes:
                    for oid in _iter_compact_ids_from_change(ch.change):
                        resolved_change_oids.append(
                            _resolve_compact_id_to_extended_guid(oid, table_for_revision, ctx=ctx, offset=None)
                        )

            # Determinism: sort root objects by (role, oid).
            resolved_root_objects_sorted = tuple(
                sorted(
                    resolved_root_objects,
                    key=lambda p: (int(p[0]), _eg_sort_key(p[1])),
                )
            )

            resolved_revs.append(
                RevisionResolvedIdsSummary(
                    rid=rev.rid,
                    rid_dependent=rev.rid_dependent,
                    effective_gid_table=_sorted_gid_table_items(tables_by_rid[rev.rid]),
                    resolved_root_objects=resolved_root_objects_sorted,
                    resolved_change_oids=tuple(resolved_change_oids),
                )
            )

        out_object_spaces.append(
            ObjectSpaceResolvedIdsSummary(
                gosid=os.gosid,
                revisions=tuple(resolved_revs),
            )
        )

    return OneStoreObjectSpacesWithResolvedIds(
        root_gosid=step10.root_gosid,
        object_spaces=tuple(out_object_spaces),
    )


def parse_object_spaces_with_revisions(
    data: bytes | bytearray | memoryview,
    *,
    ctx: ParseContext | None = None,
) -> OneStoreObjectSpacesWithRevisions:
    """End-to-end object space + revision manifest list parsing (Step 10).

    Builds on Step 9 and additionally parses each object space's revision manifest list into:
    - per-revision rid + dependency
    - revision role/context assignments (last assignment wins)
    - presence of encryption marker (0x07C)

    Object data inside revision manifests is intentionally ignored at this step.
    """

    if ctx is None:
        ctx = ParseContext(strict=True)

    header = Header.parse(BinaryReader(data), ctx=ctx)
    last_count_by_list_id = parse_transaction_log(BinaryReader(data), header, ctx=ctx)

    root_typed = parse_file_node_list_typed_nodes(
        BinaryReader(data),
        header.fcr_file_node_list_root,
        last_count_by_list_id=last_count_by_list_id,
        ctx=ctx,
    )
    manifests: RootFileNodeListManifests = build_root_file_node_list_manifests(root_typed.nodes, ctx=ctx)

    out_object_spaces: list[ObjectSpaceRevisionsSummary] = []

    for os_ref in manifests.object_space_refs:
        if not isinstance(os_ref, ObjectSpaceManifestListReferenceFND):
            continue

        manifest_list_fcr = _as_fcr64x32(os_ref.ref)
        os_manifest_list = parse_file_node_list_typed_nodes(
            BinaryReader(data),
            manifest_list_fcr,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ctx,
        )

        start = _require_first_typed_node(
            os_manifest_list.nodes,
            ObjectSpaceManifestListStartFND,
            message="Object space manifest list MUST start with ObjectSpaceManifestListStartFND",
            offset=manifest_list_fcr.stp,
        )
        if ctx.strict and start.gosid != os_ref.gosid:
            raise OneStoreFormatError(
                "ObjectSpaceManifestListStartFND.gosid MUST match the referring ObjectSpaceManifestListReferenceFND.gosid",
                offset=os_manifest_list.nodes[0].node.header.offset,
            )

        rev_refs: list[RevisionManifestListReferenceFND] = []
        for tn in os_manifest_list.nodes:
            if isinstance(tn.typed, RevisionManifestListReferenceFND):
                rev_refs.append(tn.typed)
        if not rev_refs:
            raise OneStoreFormatError(
                "Object space manifest list MUST contain at least one RevisionManifestListReferenceFND",
                offset=manifest_list_fcr.stp,
            )

        last_rev_ref = rev_refs[-1]
        rev_list_fcr = _as_fcr64x32(last_rev_ref.ref)
        rev_list = parse_file_node_list_typed_nodes(
            BinaryReader(data),
            rev_list_fcr,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ctx,
        )

        rev_start = _require_first_typed_node(
            rev_list.nodes,
            RevisionManifestListStartFND,
            message="Revision manifest list MUST start with RevisionManifestListStartFND",
            offset=rev_list_fcr.stp,
        )
        if ctx.strict and rev_start.gosid != os_ref.gosid:
            raise OneStoreFormatError(
                "RevisionManifestListStartFND.gosid MUST match object space gosid",
                offset=rev_list.nodes[0].node.header.offset,
            )

        revisions, assignments = _parse_revision_manifest_list_revisions(
            data,
            rev_list.nodes,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ctx,
        )

        # Step 11 validation: if any revision manifest in this object space has 0x07C,
        # then require it for all manifests in strict mode.
        if revisions:
            any_marker = any(r.has_encryption_marker for r in revisions)
            if any_marker:
                missing = [r for r in revisions if not r.has_encryption_marker]
                if missing:
                    msg = "If any revision manifest in an object space is encrypted, all manifests MUST include the encryption marker"
                    if ctx.strict:
                        raise OneStoreFormatError(msg, offset=0)
                    ctx.warn(msg, offset=0)

                refs = {r.encryption_key_ref for r in revisions if r.encryption_key_ref is not None}
                if len(refs) > 1:
                    ctx.warn(
                        "Encryption key reference differs across revision manifests in the same object space",
                        offset=0,
                    )

        out_object_spaces.append(
            ObjectSpaceRevisionsSummary(
                gosid=os_ref.gosid,
                manifest_list_ref=os_ref.ref,
                revision_manifest_list_ref=last_rev_ref.ref,
                revisions=revisions,
                role_assignments=assignments,
            )
        )

    return OneStoreObjectSpacesWithRevisions(
        root_gosid=manifests.root.gosid_root,
        object_spaces=tuple(out_object_spaces),
    )
