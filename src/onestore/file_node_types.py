from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .common_types import ExtendedGUID
from .chunk_refs import FileNodeChunkReference
from .errors import OneStoreFormatError
from .file_node_core import FileNode
from .io import BinaryReader
from .parse_context import ParseContext


# Step 8: FileNodeID routing + initial real FileNode types.
# The goal is to keep the core FileNode parser generic and add type-specific parsing here.


@dataclass(frozen=True, slots=True)
class ObjectSpaceManifestRootFND:
    """ObjectSpaceManifestRootFND (0x004) — root object space identity."""

    gosid_root: ExtendedGUID


@dataclass(frozen=True, slots=True)
class ObjectSpaceManifestListReferenceFND:
    """ObjectSpaceManifestListReferenceFND (0x008, BaseType=2).

    Contains a FileNodeChunkReference (already parsed into FileNode.chunk_ref) and a gosid.
    """

    ref: FileNodeChunkReference
    gosid: ExtendedGUID


@dataclass(frozen=True, slots=True)
class FileDataStoreListReferenceFND:
    """FileDataStoreListReferenceFND (0x090, BaseType=2).

    Contains only a FileNodeChunkReference pointing to a file node list with FileDataStoreObjectReferenceFND nodes.
    """

    ref: FileNodeChunkReference


KnownFileNodeType = ObjectSpaceManifestRootFND | ObjectSpaceManifestListReferenceFND | FileDataStoreListReferenceFND


@dataclass(frozen=True, slots=True)
class TypedFileNode:
    node: FileNode
    typed: KnownFileNodeType | None
    raw_bytes: bytes | None = None


FileNodeTypeParser = Callable[[FileNode, ParseContext], KnownFileNodeType]


def _parse_object_space_manifest_root_fnd(node: FileNode, ctx: ParseContext) -> ObjectSpaceManifestRootFND:
    # Spec (docs/ms-onestore/08-file-node-types-manifests.md): payload is ExtendedGUID (20 bytes).
    if node.header.base_type != 0:
        raise OneStoreFormatError(
            "ObjectSpaceManifestRootFND MUST have BaseType==0",
            offset=node.header.offset,
        )
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "ObjectSpaceManifestRootFND MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 20:
        raise OneStoreFormatError(
            "ObjectSpaceManifestRootFND payload MUST be 20 bytes",
            offset=node.header.offset,
        )

    eg = ExtendedGUID.parse(BinaryReader(node.fnd))
    return ObjectSpaceManifestRootFND(gosid_root=eg)


def _parse_object_space_manifest_list_reference_fnd(
    node: FileNode, ctx: ParseContext
) -> ObjectSpaceManifestListReferenceFND:
    # Spec: BaseType=2, leading FileNodeChunkReference, then ExtendedGUID (20 bytes).
    if node.header.base_type != 2:
        raise OneStoreFormatError(
            "ObjectSpaceManifestListReferenceFND MUST have BaseType==2",
            offset=node.header.offset,
        )
    if node.chunk_ref is None:
        raise OneStoreFormatError(
            "ObjectSpaceManifestListReferenceFND MUST contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 20:
        raise OneStoreFormatError(
            "ObjectSpaceManifestListReferenceFND payload MUST end with 20-byte ExtendedGUID",
            offset=node.header.offset,
        )

    gosid = ExtendedGUID.parse(BinaryReader(node.fnd))
    if gosid.is_zero():
        raise OneStoreFormatError(
            "ObjectSpaceManifestListReferenceFND.gosid MUST NOT be zero",
            offset=node.header.offset,
        )

    assert node.chunk_ref is not None
    return ObjectSpaceManifestListReferenceFND(ref=node.chunk_ref, gosid=gosid)


def _parse_file_data_store_list_reference_fnd(node: FileNode, ctx: ParseContext) -> FileDataStoreListReferenceFND:
    # Spec (docs/ms-onestore/11-file-node-types-file-data.md): BaseType=2, only FileNodeChunkReference.
    if node.header.base_type != 2:
        raise OneStoreFormatError(
            "FileDataStoreListReferenceFND MUST have BaseType==2",
            offset=node.header.offset,
        )
    if node.chunk_ref is None:
        raise OneStoreFormatError(
            "FileDataStoreListReferenceFND MUST contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 0:
        raise OneStoreFormatError(
            "FileDataStoreListReferenceFND MUST contain no data beyond FileNodeChunkReference",
            offset=node.header.offset,
        )

    return FileDataStoreListReferenceFND(ref=node.chunk_ref)


FILE_NODE_TYPE_PARSERS: dict[int, FileNodeTypeParser] = {
    0x004: _parse_object_space_manifest_root_fnd,
    0x008: _parse_object_space_manifest_list_reference_fnd,
    0x090: _parse_file_data_store_list_reference_fnd,
}


def parse_typed_file_node(
    node: FileNode,
    *,
    ctx: ParseContext,
    warn_unknown_ids: set[int] | None = None,
    parsers: dict[int, FileNodeTypeParser] | None = None,
) -> TypedFileNode:
    """Parse a FileNode into a typed node when the FileNodeID is known.

    - Known IDs: returns a TypedFileNode with a parsed `typed` payload and performs MUST validations.
    - Unknown IDs: emits a warning (once per id when warn_unknown_ids is provided) and keeps raw bytes.
    """

    table = FILE_NODE_TYPE_PARSERS if parsers is None else parsers
    parser = table.get(node.header.file_node_id)
    if parser is None:
        if warn_unknown_ids is None:
            ctx.warn(f"Unknown FileNodeID 0x{node.header.file_node_id:03X}", offset=node.header.offset)
        else:
            if node.header.file_node_id not in warn_unknown_ids:
                warn_unknown_ids.add(node.header.file_node_id)
                ctx.warn(f"Unknown FileNodeID 0x{node.header.file_node_id:03X}", offset=node.header.offset)
        return TypedFileNode(node=node, typed=None)

    return TypedFileNode(node=node, typed=parser(node, ctx))


@dataclass(frozen=True, slots=True)
class RootFileNodeListManifests:
    """A minimal structured view of root list manifest nodes.

    Currently only supports the manifest types needed to bootstrap object spaces:
    - ObjectSpaceManifestRootFND (0x004)
    - ObjectSpaceManifestListReferenceFND (0x008)
    """

    root: ObjectSpaceManifestRootFND
    object_space_refs: tuple[ObjectSpaceManifestListReferenceFND, ...]
    file_data_store_list_ref: FileDataStoreListReferenceFND | None


def build_root_file_node_list_manifests(
    typed_nodes: tuple[TypedFileNode, ...], *, ctx: ParseContext
) -> RootFileNodeListManifests:
    roots: list[tuple[ObjectSpaceManifestRootFND, int]] = []
    refs: list[tuple[ObjectSpaceManifestListReferenceFND, int]] = []
    file_data_refs: list[tuple[FileDataStoreListReferenceFND, int]] = []

    allowed_ids_strict = {0x004, 0x008, 0x090}

    for tn in typed_nodes:
        if ctx.strict and tn.node.header.file_node_id not in allowed_ids_strict:
            raise OneStoreFormatError(
                "Root file node list MUST contain only 0x004/0x008/0x090 FileNodeIDs",
                offset=tn.node.header.offset,
            )

        if isinstance(tn.typed, ObjectSpaceManifestRootFND):
            roots.append((tn.typed, tn.node.header.offset))
        elif isinstance(tn.typed, ObjectSpaceManifestListReferenceFND):
            refs.append((tn.typed, tn.node.header.offset))
        elif isinstance(tn.typed, FileDataStoreListReferenceFND):
            file_data_refs.append((tn.typed, tn.node.header.offset))
        else:
            if ctx.strict and tn.node.header.file_node_id in allowed_ids_strict:
                # Allowed ID but unparsed/unknown => treat as hard failure in strict mode.
                raise OneStoreFormatError(
                    f"Root file node list FileNodeID 0x{tn.node.header.file_node_id:03X} could not be parsed",
                    offset=tn.node.header.offset,
                )

    if len(roots) != 1:
        raise OneStoreFormatError(
            "Root file node list MUST contain exactly one ObjectSpaceManifestRootFND",
            offset=typed_nodes[0].node.header.offset if typed_nodes else 0,
        )

    if not refs:
        raise OneStoreFormatError(
            "Root file node list MUST contain at least one ObjectSpaceManifestListReferenceFND",
            offset=typed_nodes[0].node.header.offset if typed_nodes else 0,
        )

    if len(file_data_refs) > 1:
        raise OneStoreFormatError(
            "Root file node list MUST contain zero or one FileDataStoreListReferenceFND",
            offset=file_data_refs[1][1],
        )

    # MUST: gosid values must be unique and non-zero (per-type parser checks non-zero).
    seen: set[tuple[bytes, int]] = set()
    for r, off in refs:
        key = (r.gosid.guid, r.gosid.n)
        if key in seen:
            raise OneStoreFormatError(
                "ObjectSpaceManifestListReferenceFND.gosid MUST be unique",
                offset=off,
            )
        seen.add(key)

    # MUST: root gosid must match one of the refs.
    root, root_off = roots[0]
    if not any(r.gosid == root.gosid_root for r, _ in refs):
        raise OneStoreFormatError(
            "ObjectSpaceManifestRootFND.gosidRoot MUST match one of ObjectSpaceManifestListReferenceFND.gosid",
            offset=root_off,
        )

    file_data_ref = file_data_refs[0][0] if file_data_refs else None
    return RootFileNodeListManifests(
        root=root,
        object_space_refs=tuple(r for r, _ in refs),
        file_data_store_list_ref=file_data_ref,
    )
