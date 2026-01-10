from __future__ import annotations

from dataclasses import dataclass

from .common_types import ExtendedGUID
from .chunk_refs import FileChunkReference64x32, FileNodeChunkReference
from .errors import OneStoreFormatError
from .file_node_list import parse_file_node_list_typed_nodes
from .file_node_types import TypedFileNode
from .file_node_types import (
    DEFAULT_CONTEXT_GCTXID,
    ObjectSpaceManifestListReferenceFND,
    ObjectSpaceManifestListStartFND,
    ObjectDataEncryptionKeyV2FNDX,
    RevisionManifestEndFND,
    RevisionManifestListReferenceFND,
    RevisionManifestListStartFND,
    RevisionManifestStart4FND,
    RevisionManifestStart6FND,
    RevisionManifestStart7FND,
    RevisionRoleAndContextDeclarationFND,
    RevisionRoleDeclarationFND,
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
    nodes: tuple[TypedFileNode, ...], *, ctx: ParseContext
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
    current_encryption_required = False
    current_manifest_pos = 0

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
                current_encryption_required = int(odcs_default) == 0x0002
                current_manifest_pos = 1
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

        if current_manifest_pos == 2:
            if current_encryption_required and not isinstance(typed, ObjectDataEncryptionKeyV2FNDX):
                raise OneStoreFormatError(
                    "Encrypted revision manifest MUST have ObjectDataEncryptionKeyV2FNDX as the second FileNode",
                    offset=tn.node.header.offset,
                )
            if isinstance(typed, ObjectDataEncryptionKeyV2FNDX):
                current_has_encryption_marker = True
        else:
            if isinstance(typed, ObjectDataEncryptionKeyV2FNDX):
                ctx.warn(
                    "ObjectDataEncryptionKeyV2FNDX appears not as the second node in a revision manifest",
                    offset=tn.node.header.offset,
                )
                current_has_encryption_marker = True

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
            revisions.append(
                RevisionSummary(
                    rid=current_rid,
                    rid_dependent=current_rid_dependent,
                    gctxid=current_gctxid,
                    revision_role=int(current_revision_role),
                    odcs_default=int(current_odcs_default),
                    has_encryption_marker=bool(current_has_encryption_marker),
                    assigned_pairs=(),
                )
            )

            current_rid = None
            current_rid_dependent = None
            current_gctxid = None
            current_revision_role = None
            current_odcs_default = None
            current_has_encryption_marker = False
            current_encryption_required = False
            current_manifest_pos = 0
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
                assigned_pairs=pairs_sorted,
            )
        )

    assignments_sorted = tuple(
        sorted(
            ((pair, rid) for pair, rid in role_assignments.items()),
            key=lambda pr: (_pair_sort_key(pr[0]), _eg_sort_key(pr[1])),
        )
    )

    return (tuple(finalized), assignments_sorted)


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

        revisions, assignments = _parse_revision_manifest_list_revisions(rev_list.nodes, ctx=ctx)

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
