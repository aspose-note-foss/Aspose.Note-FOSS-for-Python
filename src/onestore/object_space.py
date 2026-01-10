from __future__ import annotations

from dataclasses import dataclass

from .common_types import ExtendedGUID
from .chunk_refs import FileChunkReference64x32, FileNodeChunkReference
from .errors import OneStoreFormatError
from .file_node_list import parse_file_node_list_typed_nodes
from .file_node_types import TypedFileNode
from .file_node_types import (
    ObjectSpaceManifestListReferenceFND,
    ObjectSpaceManifestListStartFND,
    RevisionManifestListReferenceFND,
    RevisionManifestListStartFND,
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
