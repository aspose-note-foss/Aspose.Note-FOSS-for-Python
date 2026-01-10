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


@dataclass(frozen=True, slots=True)
class ObjectSpaceManifestListStartFND:
    """ObjectSpaceManifestListStartFND (0x00C) — first node in an object space manifest list."""

    gosid: ExtendedGUID


@dataclass(frozen=True, slots=True)
class RevisionManifestListReferenceFND:
    """RevisionManifestListReferenceFND (0x010, BaseType=2).

    Contains only a FileNodeChunkReference pointing to the revision manifest list.
    """

    ref: FileNodeChunkReference


@dataclass(frozen=True, slots=True)
class RevisionManifestListStartFND:
    """RevisionManifestListStartFND (0x014) — first node in a revision manifest list.

    nInstance MUST be ignored.
    """

    gosid: ExtendedGUID
    n_instance: int


DEFAULT_CONTEXT_GCTXID = ExtendedGUID(guid=b"\x00" * 16, n=0)


@dataclass(frozen=True, slots=True)
class RevisionManifestStart4FND:
    """RevisionManifestStart4FND (0x01B) — start of a revision manifest in .onetoc2.

    odcsDefault MUST be 0 and MUST be ignored.
    timeCreation MUST be ignored.
    """

    rid: ExtendedGUID
    rid_dependent: ExtendedGUID
    revision_role: int
    odcs_default: int


@dataclass(frozen=True, slots=True)
class RevisionManifestStart6FND:
    """RevisionManifestStart6FND (0x01E) — start of a revision manifest for default context in .one."""

    rid: ExtendedGUID
    rid_dependent: ExtendedGUID
    revision_role: int
    odcs_default: int


@dataclass(frozen=True, slots=True)
class RevisionManifestStart7FND:
    """RevisionManifestStart7FND (0x01F) — start of a revision manifest for a specific context in .one."""

    base: RevisionManifestStart6FND
    gctxid: ExtendedGUID


@dataclass(frozen=True, slots=True)
class RevisionManifestEndFND:
    """RevisionManifestEndFND (0x01C) — end of a revision manifest. MUST contain no data."""


@dataclass(frozen=True, slots=True)
class RevisionRoleDeclarationFND:
    """RevisionRoleDeclarationFND (0x05C) — add revision role for default context."""

    rid: ExtendedGUID
    revision_role: int


@dataclass(frozen=True, slots=True)
class RevisionRoleAndContextDeclarationFND:
    """RevisionRoleAndContextDeclarationFND (0x05D) — add revision role for a specific context."""

    rid: ExtendedGUID
    revision_role: int
    gctxid: ExtendedGUID


@dataclass(frozen=True, slots=True)
class ObjectDataEncryptionKeyV2FNDX:
    """ObjectDataEncryptionKeyV2FNDX (0x07C, BaseType=2) — encryption marker.

    Contains a FileNodeChunkReference (already parsed into FileNode.chunk_ref).
    The referenced structure's contents are currently ignored (Step 10 scope).
    """

    ref: FileNodeChunkReference


KnownFileNodeType = (
    ObjectSpaceManifestRootFND
    | ObjectSpaceManifestListReferenceFND
    | FileDataStoreListReferenceFND
    | ObjectSpaceManifestListStartFND
    | RevisionManifestListReferenceFND
    | RevisionManifestListStartFND
    | RevisionManifestStart4FND
    | RevisionManifestStart6FND
    | RevisionManifestStart7FND
    | RevisionManifestEndFND
    | RevisionRoleDeclarationFND
    | RevisionRoleAndContextDeclarationFND
    | ObjectDataEncryptionKeyV2FNDX
)


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


def _parse_object_space_manifest_list_start_fnd(node: FileNode, ctx: ParseContext) -> ObjectSpaceManifestListStartFND:
    # Spec (docs/ms-onestore/08-file-node-types-manifests.md): payload is ExtendedGUID (20 bytes).
    if node.header.base_type != 0:
        raise OneStoreFormatError(
            "ObjectSpaceManifestListStartFND MUST have BaseType==0",
            offset=node.header.offset,
        )
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "ObjectSpaceManifestListStartFND MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 20:
        raise OneStoreFormatError(
            "ObjectSpaceManifestListStartFND payload MUST be 20 bytes",
            offset=node.header.offset,
        )

    gosid = ExtendedGUID.parse(BinaryReader(node.fnd))
    return ObjectSpaceManifestListStartFND(gosid=gosid)


def _parse_revision_manifest_list_reference_fnd(
    node: FileNode, ctx: ParseContext
) -> RevisionManifestListReferenceFND:
    # Spec: BaseType=2, only FileNodeChunkReference.
    if node.header.base_type != 2:
        raise OneStoreFormatError(
            "RevisionManifestListReferenceFND MUST have BaseType==2",
            offset=node.header.offset,
        )
    if node.chunk_ref is None:
        raise OneStoreFormatError(
            "RevisionManifestListReferenceFND MUST contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 0:
        raise OneStoreFormatError(
            "RevisionManifestListReferenceFND MUST contain no data beyond FileNodeChunkReference",
            offset=node.header.offset,
        )

    return RevisionManifestListReferenceFND(ref=node.chunk_ref)


def _parse_revision_manifest_list_start_fnd(node: FileNode, ctx: ParseContext) -> RevisionManifestListStartFND:
    # Spec: gosid (20 bytes) + nInstance (u32). nInstance MUST be ignored.
    if node.header.base_type != 0:
        raise OneStoreFormatError(
            "RevisionManifestListStartFND MUST have BaseType==0",
            offset=node.header.offset,
        )
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "RevisionManifestListStartFND MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 24:
        raise OneStoreFormatError(
            "RevisionManifestListStartFND payload MUST be 24 bytes",
            offset=node.header.offset,
        )

    r = BinaryReader(node.fnd)
    gosid = ExtendedGUID.parse(r)
    n_instance = r.read_u32()
    if r.remaining() != 0:
        raise OneStoreFormatError(
            "RevisionManifestListStartFND parse did not consume full payload",
            offset=node.header.offset,
        )

    return RevisionManifestListStartFND(gosid=gosid, n_instance=int(n_instance))


def _require_base_type(
    node: FileNode,
    expected: int,
    *,
    ctx: ParseContext,
    message: str,
) -> None:
    if node.header.base_type != expected:
        if ctx.strict:
            raise OneStoreFormatError(message, offset=node.header.offset)
        ctx.warn(message, offset=node.header.offset)


def _parse_revision_manifest_start4_fnd(node: FileNode, ctx: ParseContext) -> RevisionManifestStart4FND:
    # Spec (2.5.6): rid (20) + ridDependent (20) + timeCreation (8 ignore) + RevisionRole (4) + odcsDefault (2 must be 0 ignore)
    _require_base_type(node, 0, ctx=ctx, message="RevisionManifestStart4FND MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "RevisionManifestStart4FND MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 54:
        raise OneStoreFormatError(
            "RevisionManifestStart4FND payload MUST be 54 bytes",
            offset=node.header.offset,
        )

    r = BinaryReader(node.fnd)
    rid = ExtendedGUID.parse(r)
    rid_dependent = ExtendedGUID.parse(r)
    _ = r.read_u64()  # timeCreation: MUST be ignored
    revision_role = int(r.read_u32())
    odcs_default = int(r.read_u16())

    if r.remaining() != 0:
        raise OneStoreFormatError(
            "RevisionManifestStart4FND parse did not consume full payload",
            offset=node.header.offset,
        )

    if rid.is_zero():
        raise OneStoreFormatError(
            "RevisionManifestStart4FND.rid MUST NOT be zero",
            offset=node.header.offset,
        )

    if odcs_default != 0:
        msg = "RevisionManifestStart4FND.odcsDefault MUST be 0 (and MUST be ignored)"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)

    return RevisionManifestStart4FND(
        rid=rid,
        rid_dependent=rid_dependent,
        revision_role=revision_role,
        odcs_default=odcs_default,
    )


def _parse_revision_manifest_start6_fnd(node: FileNode, ctx: ParseContext) -> RevisionManifestStart6FND:
    # Spec (2.5.7): rid (20) + ridDependent (20) + RevisionRole (4) + odcsDefault (2)
    _require_base_type(node, 0, ctx=ctx, message="RevisionManifestStart6FND MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "RevisionManifestStart6FND MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 46:
        raise OneStoreFormatError(
            "RevisionManifestStart6FND payload MUST be 46 bytes",
            offset=node.header.offset,
        )

    r = BinaryReader(node.fnd)
    rid = ExtendedGUID.parse(r)
    rid_dependent = ExtendedGUID.parse(r)
    revision_role = int(r.read_u32())
    odcs_default = int(r.read_u16())
    if r.remaining() != 0:
        raise OneStoreFormatError(
            "RevisionManifestStart6FND parse did not consume full payload",
            offset=node.header.offset,
        )

    if rid.is_zero():
        raise OneStoreFormatError(
            "RevisionManifestStart6FND.rid MUST NOT be zero",
            offset=node.header.offset,
        )

    if odcs_default not in (0x0000, 0x0002):
        msg = "RevisionManifestStart6FND.odcsDefault MUST be 0x0000 or 0x0002"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)

    return RevisionManifestStart6FND(
        rid=rid,
        rid_dependent=rid_dependent,
        revision_role=revision_role,
        odcs_default=odcs_default,
    )


def _parse_revision_manifest_start7_fnd(node: FileNode, ctx: ParseContext) -> RevisionManifestStart7FND:
    # Spec (2.5.8): base (Start6, 46 bytes) + gctxid (20 bytes)
    _require_base_type(node, 0, ctx=ctx, message="RevisionManifestStart7FND MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "RevisionManifestStart7FND MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 66:
        raise OneStoreFormatError(
            "RevisionManifestStart7FND payload MUST be 66 bytes",
            offset=node.header.offset,
        )

    r = BinaryReader(node.fnd)
    rid = ExtendedGUID.parse(r)
    rid_dependent = ExtendedGUID.parse(r)
    revision_role = int(r.read_u32())
    odcs_default = int(r.read_u16())
    gctxid = ExtendedGUID.parse(r)
    if r.remaining() != 0:
        raise OneStoreFormatError(
            "RevisionManifestStart7FND parse did not consume full payload",
            offset=node.header.offset,
        )

    base = RevisionManifestStart6FND(
        rid=rid,
        rid_dependent=rid_dependent,
        revision_role=revision_role,
        odcs_default=odcs_default,
    )

    if rid.is_zero():
        raise OneStoreFormatError(
            "RevisionManifestStart7FND.base.rid MUST NOT be zero",
            offset=node.header.offset,
        )

    if odcs_default not in (0x0000, 0x0002):
        msg = "RevisionManifestStart7FND.base.odcsDefault MUST be 0x0000 or 0x0002"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)

    return RevisionManifestStart7FND(base=base, gctxid=gctxid)


def _parse_revision_manifest_end_fnd(node: FileNode, ctx: ParseContext) -> RevisionManifestEndFND:
    _require_base_type(node, 0, ctx=ctx, message="RevisionManifestEndFND MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "RevisionManifestEndFND MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 0:
        raise OneStoreFormatError(
            "RevisionManifestEndFND MUST contain no data",
            offset=node.header.offset,
        )
    return RevisionManifestEndFND()


def _parse_revision_role_declaration_fnd(node: FileNode, ctx: ParseContext) -> RevisionRoleDeclarationFND:
    _require_base_type(node, 0, ctx=ctx, message="RevisionRoleDeclarationFND MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "RevisionRoleDeclarationFND MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 24:
        raise OneStoreFormatError(
            "RevisionRoleDeclarationFND payload MUST be 24 bytes",
            offset=node.header.offset,
        )

    r = BinaryReader(node.fnd)
    rid = ExtendedGUID.parse(r)
    revision_role = int(r.read_u32())
    if r.remaining() != 0:
        raise OneStoreFormatError(
            "RevisionRoleDeclarationFND parse did not consume full payload",
            offset=node.header.offset,
        )

    if rid.is_zero():
        msg = "RevisionRoleDeclarationFND.rid MUST NOT be zero"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)

    return RevisionRoleDeclarationFND(rid=rid, revision_role=revision_role)


def _parse_revision_role_and_context_declaration_fnd(
    node: FileNode, ctx: ParseContext
) -> RevisionRoleAndContextDeclarationFND:
    _require_base_type(node, 0, ctx=ctx, message="RevisionRoleAndContextDeclarationFND MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "RevisionRoleAndContextDeclarationFND MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 44:
        raise OneStoreFormatError(
            "RevisionRoleAndContextDeclarationFND payload MUST be 44 bytes",
            offset=node.header.offset,
        )

    r = BinaryReader(node.fnd)
    rid = ExtendedGUID.parse(r)
    revision_role = int(r.read_u32())
    gctxid = ExtendedGUID.parse(r)
    if r.remaining() != 0:
        raise OneStoreFormatError(
            "RevisionRoleAndContextDeclarationFND parse did not consume full payload",
            offset=node.header.offset,
        )

    if rid.is_zero():
        msg = "RevisionRoleAndContextDeclarationFND.rid MUST NOT be zero"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)

    return RevisionRoleAndContextDeclarationFND(rid=rid, revision_role=revision_role, gctxid=gctxid)


def _parse_object_data_encryption_key_v2_fndx(node: FileNode, ctx: ParseContext) -> ObjectDataEncryptionKeyV2FNDX:
    # Spec (2.5.19): BaseType=2 and the payload is empty; ref is in FileNodeChunkReference.
    _require_base_type(node, 2, ctx=ctx, message="ObjectDataEncryptionKeyV2FNDX MUST have BaseType==2")
    if node.chunk_ref is None:
        raise OneStoreFormatError(
            "ObjectDataEncryptionKeyV2FNDX MUST contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 0:
        raise OneStoreFormatError(
            "ObjectDataEncryptionKeyV2FNDX MUST contain no data beyond FileNodeChunkReference",
            offset=node.header.offset,
        )
    return ObjectDataEncryptionKeyV2FNDX(ref=node.chunk_ref)


FILE_NODE_TYPE_PARSERS: dict[int, FileNodeTypeParser] = {
    0x004: _parse_object_space_manifest_root_fnd,
    0x008: _parse_object_space_manifest_list_reference_fnd,
    0x00C: _parse_object_space_manifest_list_start_fnd,
    0x010: _parse_revision_manifest_list_reference_fnd,
    0x014: _parse_revision_manifest_list_start_fnd,
    0x01B: _parse_revision_manifest_start4_fnd,
    0x01C: _parse_revision_manifest_end_fnd,
    0x01E: _parse_revision_manifest_start6_fnd,
    0x01F: _parse_revision_manifest_start7_fnd,
    0x05C: _parse_revision_role_declaration_fnd,
    0x05D: _parse_revision_role_and_context_declaration_fnd,
    0x07C: _parse_object_data_encryption_key_v2_fndx,
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
