from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .common_types import CompactID, ExtendedGUID, JCID
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
class FileDataStoreObjectReferenceFND:
    """FileDataStoreObjectReferenceFND (0x094, BaseType=2).

    Contains a FileNodeChunkReference pointing to a FileDataStoreObject (2.6.13) and
    a 16-byte guidReference used for lookup.
    """

    ref: FileNodeChunkReference
    guid_reference: bytes


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


@dataclass(frozen=True, slots=True)
class GlobalIdTableStartFNDX:
    """GlobalIdTableStartFNDX (0x021) — global id table start for .onetoc2.

    Contains a 1-byte Reserved field which MUST be 0.
    """

    reserved: int


@dataclass(frozen=True, slots=True)
class GlobalIdTableStart2FND:
    """GlobalIdTableStart2FND (0x022) — global id table start for .one. MUST contain no data."""


@dataclass(frozen=True, slots=True)
class GlobalIdTableEntryFNDX:
    """GlobalIdTableEntryFNDX (0x024)."""

    index: int
    guid: bytes


@dataclass(frozen=True, slots=True)
class GlobalIdTableEntry2FNDX:
    """GlobalIdTableEntry2FNDX (0x025) — map from dependency revision (.onetoc2)."""

    index_map_from: int
    index_map_to: int


@dataclass(frozen=True, slots=True)
class GlobalIdTableEntry3FNDX:
    """GlobalIdTableEntry3FNDX (0x026) — range copy from dependency revision (.onetoc2)."""

    index_copy_from_start: int
    entries_to_copy: int
    index_copy_to_start: int


@dataclass(frozen=True, slots=True)
class GlobalIdTableEndFNDX:
    """GlobalIdTableEndFNDX (0x028) — MUST contain no data."""


@dataclass(frozen=True, slots=True)
class RootObjectReference2FNDX:
    """RootObjectReference2FNDX (0x059) — root object ref using CompactID."""

    oid_root: CompactID
    root_role: int


@dataclass(frozen=True, slots=True)
class RootObjectReference3FND:
    """RootObjectReference3FND (0x05A) — root object ref using ExtendedGUID."""

    oid_root: ExtendedGUID
    root_role: int


@dataclass(frozen=True, slots=True)
class ObjectInfoDependencyOverridesFND:
    """ObjectInfoDependencyOverridesFND (0x084) — dependency override node.

    If `ref` is fcrNil, override data is stored inline in `inline_data`.
    Otherwise the referenced structure is out-of-line and `inline_data` MUST be empty.
    """

    ref: FileNodeChunkReference | None
    inline_data: bytes


@dataclass(frozen=True, slots=True)
class DataSignatureGroupDefinitionFND:
    """DataSignatureGroupDefinitionFND (0x08C)."""

    data_signature_group: ExtendedGUID


@dataclass(frozen=True, slots=True)
class ObjectGroupListReferenceFND:
    """ObjectGroupListReferenceFND (0x0B0, BaseType=2)."""

    ref: FileNodeChunkReference
    object_group_id: ExtendedGUID


@dataclass(frozen=True, slots=True)
class ObjectGroupStartFND:
    """ObjectGroupStartFND (0x0B4)."""

    oid: ExtendedGUID


@dataclass(frozen=True, slots=True)
class ObjectGroupEndFND:
    """ObjectGroupEndFND (0x0B8). MUST contain no data."""


@dataclass(frozen=True, slots=True)
class ObjectDeclaration2RefCountFND:
    """ObjectDeclaration2RefCountFND (0x0A4)."""

    ref: FileNodeChunkReference
    oid: CompactID
    jcid: JCID
    has_oid_references: bool
    has_osid_references: bool
    ref_count: int


@dataclass(frozen=True, slots=True)
class ObjectDeclaration2LargeRefCountFND:
    """ObjectDeclaration2LargeRefCountFND (0x0A5)."""

    ref: FileNodeChunkReference
    oid: CompactID
    jcid: JCID
    has_oid_references: bool
    has_osid_references: bool
    ref_count: int


@dataclass(frozen=True, slots=True)
class ReadOnlyObjectDeclaration2RefCountFND:
    """ReadOnlyObjectDeclaration2RefCountFND (0x0C4)."""

    base: ObjectDeclaration2RefCountFND
    md5_hash: bytes


@dataclass(frozen=True, slots=True)
class ReadOnlyObjectDeclaration2LargeRefCountFND:
    """ReadOnlyObjectDeclaration2LargeRefCountFND (0x0C5)."""

    base: ObjectDeclaration2LargeRefCountFND
    md5_hash: bytes


@dataclass(frozen=True, slots=True)
class HashedChunkDescriptor2FND:
    """HashedChunkDescriptor2FND (0x0C2, BaseType=1).

    Provides an MD5 hash for the blob referenced by `blob_ref`.
    """

    blob_ref: FileNodeChunkReference
    guid_hash: bytes


@dataclass(frozen=True, slots=True)
class ObjectRevisionWithRefCountFNDX:
    """ObjectRevisionWithRefCountFNDX (0x041)."""

    ref: FileNodeChunkReference
    oid: CompactID
    has_oid_references: bool
    has_osid_references: bool
    ref_count: int


@dataclass(frozen=True, slots=True)
class ObjectRevisionWithRefCount2FNDX:
    """ObjectRevisionWithRefCount2FNDX (0x042)."""

    ref: FileNodeChunkReference
    oid: CompactID
    has_oid_references: bool
    has_osid_references: bool
    ref_count: int


KnownFileNodeType = (
    ObjectSpaceManifestRootFND
    | ObjectSpaceManifestListReferenceFND
    | FileDataStoreListReferenceFND
    | FileDataStoreObjectReferenceFND
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
    | GlobalIdTableStartFNDX
    | GlobalIdTableStart2FND
    | GlobalIdTableEntryFNDX
    | GlobalIdTableEntry2FNDX
    | GlobalIdTableEntry3FNDX
    | GlobalIdTableEndFNDX
    | RootObjectReference2FNDX
    | RootObjectReference3FND
    | ObjectInfoDependencyOverridesFND
    | DataSignatureGroupDefinitionFND
    | ObjectGroupListReferenceFND
    | ObjectGroupStartFND
    | ObjectGroupEndFND
    | ObjectDeclaration2RefCountFND
    | ObjectDeclaration2LargeRefCountFND
    | ReadOnlyObjectDeclaration2RefCountFND
    | ReadOnlyObjectDeclaration2LargeRefCountFND
    | ObjectRevisionWithRefCountFNDX
    | ObjectRevisionWithRefCount2FNDX
    | HashedChunkDescriptor2FND
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
        msg = "FileDataStoreListReferenceFND MUST have BaseType==2"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)
    if node.chunk_ref is None:
        raise OneStoreFormatError(
            "FileDataStoreListReferenceFND MUST contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 0:
        msg = "FileDataStoreListReferenceFND MUST contain no data beyond FileNodeChunkReference"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)

    return FileDataStoreListReferenceFND(ref=node.chunk_ref)


def _parse_file_data_store_object_reference_fnd(node: FileNode, ctx: ParseContext) -> FileDataStoreObjectReferenceFND:
    # Spec (docs/ms-onestore/11-file-node-types-file-data.md): BaseType=2, FileNodeChunkReference + 16-byte GUID.
    if node.header.base_type != 2:
        msg = "FileDataStoreObjectReferenceFND MUST have BaseType==2"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)
    if node.chunk_ref is None:
        raise OneStoreFormatError(
            "FileDataStoreObjectReferenceFND MUST contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 16:
        msg = "FileDataStoreObjectReferenceFND payload MUST be 16-byte guidReference"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)

    # Best-effort: clamp/pad to 16 bytes in tolerant mode.
    guid_reference = bytes(node.fnd)
    if len(guid_reference) < 16:
        guid_reference = guid_reference.ljust(16, b"\x00")
    elif len(guid_reference) > 16:
        guid_reference = guid_reference[:16]
    return FileDataStoreObjectReferenceFND(ref=node.chunk_ref, guid_reference=guid_reference)


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


def _is_nil_filenode_ref(ref: FileNodeChunkReference) -> bool:
    # fcrNil is encoded as all-ones for stp and zero cb in the *raw* fields.
    if ref.cb_format == 0:
        cb_bits = 32
    elif ref.cb_format == 1:
        cb_bits = 64
    elif ref.cb_format == 2:
        cb_bits = 8
    elif ref.cb_format == 3:
        cb_bits = 16
    else:
        cb_bits = 64

    if ref.stp_format == 0:
        stp_bits = 64
    elif ref.stp_format == 1:
        stp_bits = 32
    elif ref.stp_format == 2:
        stp_bits = 16
    elif ref.stp_format == 3:
        stp_bits = 32
    else:
        stp_bits = 64

    max_stp = (1 << stp_bits) - 1
    max_cb = (1 << cb_bits) - 1
    _ = max_cb  # silence unused in case of future expansion
    return int(ref.raw_stp) == max_stp and int(ref.raw_cb) == 0


def _parse_global_id_table_start_fndx(node: FileNode, ctx: ParseContext) -> GlobalIdTableStartFNDX:
    _require_base_type(node, 0, ctx=ctx, message="GlobalIdTableStartFNDX MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "GlobalIdTableStartFNDX MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 1:
        raise OneStoreFormatError(
            "GlobalIdTableStartFNDX payload MUST be 1 byte",
            offset=node.header.offset,
        )
    reserved = int(node.fnd[0])
    if reserved != 0:
        msg = "GlobalIdTableStartFNDX.Reserved MUST be 0"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)
    return GlobalIdTableStartFNDX(reserved=reserved)


def _parse_global_id_table_start2_fnd(node: FileNode, ctx: ParseContext) -> GlobalIdTableStart2FND:
    _require_base_type(node, 0, ctx=ctx, message="GlobalIdTableStart2FND MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "GlobalIdTableStart2FND MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 0:
        raise OneStoreFormatError(
            "GlobalIdTableStart2FND MUST contain no data",
            offset=node.header.offset,
        )
    return GlobalIdTableStart2FND()


def _parse_global_id_table_entry_fndx(node: FileNode, ctx: ParseContext) -> GlobalIdTableEntryFNDX:
    _require_base_type(node, 0, ctx=ctx, message="GlobalIdTableEntryFNDX MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "GlobalIdTableEntryFNDX MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 20:
        raise OneStoreFormatError(
            "GlobalIdTableEntryFNDX payload MUST be 20 bytes",
            offset=node.header.offset,
        )
    r = BinaryReader(node.fnd)
    index = int(r.read_u32())
    guid = r.read_bytes(16)
    if r.remaining() != 0:
        raise OneStoreFormatError(
            "GlobalIdTableEntryFNDX parse did not consume full payload",
            offset=node.header.offset,
        )
    if index >= 0xFFFFFF:
        raise OneStoreFormatError(
            "GlobalIdTableEntryFNDX.index MUST be < 0xFFFFFF",
            offset=node.header.offset,
        )
    if guid == b"\x00" * 16:
        raise OneStoreFormatError(
            "GlobalIdTableEntryFNDX.guid MUST NOT be all-zero",
            offset=node.header.offset,
        )
    return GlobalIdTableEntryFNDX(index=index, guid=guid)


def _parse_global_id_table_entry2_fndx(node: FileNode, ctx: ParseContext) -> GlobalIdTableEntry2FNDX:
    _require_base_type(node, 0, ctx=ctx, message="GlobalIdTableEntry2FNDX MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "GlobalIdTableEntry2FNDX MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 8:
        raise OneStoreFormatError(
            "GlobalIdTableEntry2FNDX payload MUST be 8 bytes",
            offset=node.header.offset,
        )
    r = BinaryReader(node.fnd)
    index_map_from = int(r.read_u32())
    index_map_to = int(r.read_u32())
    if r.remaining() != 0:
        raise OneStoreFormatError(
            "GlobalIdTableEntry2FNDX parse did not consume full payload",
            offset=node.header.offset,
        )
    if index_map_from >= 0xFFFFFF or index_map_to >= 0xFFFFFF:
        msg = "GlobalIdTableEntry2FNDX indices MUST be < 0xFFFFFF"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)
    return GlobalIdTableEntry2FNDX(index_map_from=index_map_from, index_map_to=index_map_to)


def _parse_global_id_table_entry3_fndx(node: FileNode, ctx: ParseContext) -> GlobalIdTableEntry3FNDX:
    _require_base_type(node, 0, ctx=ctx, message="GlobalIdTableEntry3FNDX MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "GlobalIdTableEntry3FNDX MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 12:
        raise OneStoreFormatError(
            "GlobalIdTableEntry3FNDX payload MUST be 12 bytes",
            offset=node.header.offset,
        )
    r = BinaryReader(node.fnd)
    index_copy_from_start = int(r.read_u32())
    entries_to_copy = int(r.read_u32())
    index_copy_to_start = int(r.read_u32())
    if r.remaining() != 0:
        raise OneStoreFormatError(
            "GlobalIdTableEntry3FNDX parse did not consume full payload",
            offset=node.header.offset,
        )
    for v in (index_copy_from_start, index_copy_to_start):
        if v >= 0xFFFFFF:
            msg = "GlobalIdTableEntry3FNDX indices MUST be < 0xFFFFFF"
            if ctx.strict:
                raise OneStoreFormatError(msg, offset=node.header.offset)
            ctx.warn(msg, offset=node.header.offset)
            break
    return GlobalIdTableEntry3FNDX(
        index_copy_from_start=index_copy_from_start,
        entries_to_copy=entries_to_copy,
        index_copy_to_start=index_copy_to_start,
    )


def _parse_global_id_table_end_fndx(node: FileNode, ctx: ParseContext) -> GlobalIdTableEndFNDX:
    _require_base_type(node, 0, ctx=ctx, message="GlobalIdTableEndFNDX MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "GlobalIdTableEndFNDX MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 0:
        raise OneStoreFormatError(
            "GlobalIdTableEndFNDX MUST contain no data",
            offset=node.header.offset,
        )
    return GlobalIdTableEndFNDX()


def _parse_root_object_reference2_fndx(node: FileNode, ctx: ParseContext) -> RootObjectReference2FNDX:
    _require_base_type(node, 0, ctx=ctx, message="RootObjectReference2FNDX MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "RootObjectReference2FNDX MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 8:
        raise OneStoreFormatError(
            "RootObjectReference2FNDX payload MUST be 8 bytes",
            offset=node.header.offset,
        )
    r = BinaryReader(node.fnd)
    oid_root = CompactID.parse(r)
    root_role = int(r.read_u32())
    if r.remaining() != 0:
        raise OneStoreFormatError(
            "RootObjectReference2FNDX parse did not consume full payload",
            offset=node.header.offset,
        )
    return RootObjectReference2FNDX(oid_root=oid_root, root_role=root_role)


def _parse_root_object_reference3_fnd(node: FileNode, ctx: ParseContext) -> RootObjectReference3FND:
    _require_base_type(node, 0, ctx=ctx, message="RootObjectReference3FND MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "RootObjectReference3FND MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 24:
        raise OneStoreFormatError(
            "RootObjectReference3FND payload MUST be 24 bytes",
            offset=node.header.offset,
        )
    r = BinaryReader(node.fnd)
    oid_root = ExtendedGUID.parse(r)
    root_role = int(r.read_u32())
    if r.remaining() != 0:
        raise OneStoreFormatError(
            "RootObjectReference3FND parse did not consume full payload",
            offset=node.header.offset,
        )
    return RootObjectReference3FND(oid_root=oid_root, root_role=root_role)


def _parse_object_info_dependency_overrides_fnd(node: FileNode, ctx: ParseContext) -> ObjectInfoDependencyOverridesFND:
    # Some real-world files encode this node with BaseType==1 or BaseType==0.
    # For safe parsing we accept:
    # - BaseType in (1,2): ref is in FileNodeChunkReference
    # - BaseType==0: no ref; treat as inline override data
    if node.header.base_type not in (0, 1, 2):
        msg = "ObjectInfoDependencyOverridesFND has unexpected BaseType"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)

    ref = node.chunk_ref
    inline_data = node.fnd

    if ref is None:
        # Inline-only encoding.
        if len(inline_data) >= 1024:
            raise OneStoreFormatError(
                "Inline ObjectInfoDependencyOverrideData MUST be smaller than 1024 bytes",
                offset=node.header.offset,
            )
        return ObjectInfoDependencyOverridesFND(ref=None, inline_data=bytes(inline_data))

    if _is_nil_filenode_ref(ref):
        if len(inline_data) >= 1024:
            raise OneStoreFormatError(
                "Inline ObjectInfoDependencyOverrideData MUST be smaller than 1024 bytes",
                offset=node.header.offset,
            )
    else:
        if len(inline_data) != 0:
            msg = "ObjectInfoDependencyOverridesFND MUST NOT contain inline data when ref is not fcrNil"
            if ctx.strict:
                raise OneStoreFormatError(msg, offset=node.header.offset)
            ctx.warn(msg, offset=node.header.offset)

    return ObjectInfoDependencyOverridesFND(ref=ref, inline_data=bytes(inline_data))


def _parse_data_signature_group_definition_fnd(node: FileNode, ctx: ParseContext) -> DataSignatureGroupDefinitionFND:
    _require_base_type(node, 0, ctx=ctx, message="DataSignatureGroupDefinitionFND MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "DataSignatureGroupDefinitionFND MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 20:
        raise OneStoreFormatError(
            "DataSignatureGroupDefinitionFND payload MUST be 20 bytes",
            offset=node.header.offset,
        )
    eg = ExtendedGUID.parse(BinaryReader(node.fnd))
    return DataSignatureGroupDefinitionFND(data_signature_group=eg)


def _parse_object_group_list_reference_fnd(node: FileNode, ctx: ParseContext) -> ObjectGroupListReferenceFND:
    if node.header.base_type not in (1, 2):
        msg = "ObjectGroupListReferenceFND MUST have BaseType==1 or BaseType==2"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)
    if node.chunk_ref is None:
        raise OneStoreFormatError(
            "ObjectGroupListReferenceFND MUST contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 20:
        raise OneStoreFormatError(
            "ObjectGroupListReferenceFND payload MUST end with 20-byte ExtendedGUID",
            offset=node.header.offset,
        )
    object_group_id = ExtendedGUID.parse(BinaryReader(node.fnd))
    return ObjectGroupListReferenceFND(ref=node.chunk_ref, object_group_id=object_group_id)


def _parse_object_group_start_fnd(node: FileNode, ctx: ParseContext) -> ObjectGroupStartFND:
    _require_base_type(node, 0, ctx=ctx, message="ObjectGroupStartFND MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "ObjectGroupStartFND MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 20:
        raise OneStoreFormatError(
            "ObjectGroupStartFND payload MUST be 20 bytes",
            offset=node.header.offset,
        )
    oid = ExtendedGUID.parse(BinaryReader(node.fnd))
    return ObjectGroupStartFND(oid=oid)


def _parse_object_group_end_fnd(node: FileNode, ctx: ParseContext) -> ObjectGroupEndFND:
    _require_base_type(node, 0, ctx=ctx, message="ObjectGroupEndFND MUST have BaseType==0")
    if node.chunk_ref is not None:
        raise OneStoreFormatError(
            "ObjectGroupEndFND MUST not contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 0:
        raise OneStoreFormatError(
            "ObjectGroupEndFND MUST contain no data",
            offset=node.header.offset,
        )
    return ObjectGroupEndFND()


def _parse_object_declaration2_body(
    node: FileNode, *, ctx: ParseContext, body_bytes: bytes
) -> tuple[CompactID, JCID, bool, bool]:
    r = BinaryReader(body_bytes)
    oid = CompactID.parse(r)
    jcid = JCID.parse(r)
    flags = int(r.read_u8())
    if r.remaining() != 0:
        raise OneStoreFormatError(
            "ObjectDeclaration2Body parse did not consume full payload",
            offset=node.header.offset,
        )
    has_oid_refs = bool(flags & 0x01)
    has_osid_refs = bool(flags & 0x02)
    reserved = (flags >> 2) & 0x3F
    if reserved != 0:
        msg = "ObjectDeclaration2Body.fReserved2 MUST be 0"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)

    try:
        jcid.validate()
    except OneStoreFormatError as e:
        if ctx.strict:
            raise OneStoreFormatError(str(e), offset=node.header.offset)
        ctx.warn(str(e), offset=node.header.offset)

    return (oid, jcid, has_oid_refs, has_osid_refs)


def _parse_object_declaration2_refcount_fnd(node: FileNode, ctx: ParseContext) -> ObjectDeclaration2RefCountFND:
    if node.header.base_type not in (1, 2):
        msg = "ObjectDeclaration2RefCountFND MUST have BaseType==1 or BaseType==2"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)
    if node.chunk_ref is None:
        raise OneStoreFormatError(
            "ObjectDeclaration2RefCountFND MUST contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 10:
        raise OneStoreFormatError(
            "ObjectDeclaration2RefCountFND payload MUST be 10 bytes",
            offset=node.header.offset,
        )
    body = node.fnd[:9]
    ref_count = int(node.fnd[9])
    oid, jcid, has_oid_refs, has_osid_refs = _parse_object_declaration2_body(node, ctx=ctx, body_bytes=body)
    return ObjectDeclaration2RefCountFND(
        ref=node.chunk_ref,
        oid=oid,
        jcid=jcid,
        has_oid_references=has_oid_refs,
        has_osid_references=has_osid_refs,
        ref_count=ref_count,
    )


def _parse_object_declaration2_large_refcount_fnd(node: FileNode, ctx: ParseContext) -> ObjectDeclaration2LargeRefCountFND:
    if node.header.base_type not in (1, 2):
        msg = "ObjectDeclaration2LargeRefCountFND MUST have BaseType==1 or BaseType==2"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)
    if node.chunk_ref is None:
        raise OneStoreFormatError(
            "ObjectDeclaration2LargeRefCountFND MUST contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 13:
        raise OneStoreFormatError(
            "ObjectDeclaration2LargeRefCountFND payload MUST be 13 bytes",
            offset=node.header.offset,
        )
    body = node.fnd[:9]
    r = BinaryReader(node.fnd[9:])
    ref_count = int(r.read_u32())
    if r.remaining() != 0:
        raise OneStoreFormatError(
            "ObjectDeclaration2LargeRefCountFND parse did not consume full payload",
            offset=node.header.offset,
        )
    oid, jcid, has_oid_refs, has_osid_refs = _parse_object_declaration2_body(node, ctx=ctx, body_bytes=body)
    return ObjectDeclaration2LargeRefCountFND(
        ref=node.chunk_ref,
        oid=oid,
        jcid=jcid,
        has_oid_references=has_oid_refs,
        has_osid_references=has_osid_refs,
        ref_count=ref_count,
    )


def _parse_readonly_object_declaration2_refcount_fnd(node: FileNode, ctx: ParseContext) -> ReadOnlyObjectDeclaration2RefCountFND:
    if node.header.base_type not in (1, 2):
        msg = "ReadOnlyObjectDeclaration2RefCountFND MUST have BaseType==1 or BaseType==2"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)
    if node.chunk_ref is None:
        raise OneStoreFormatError(
            "ReadOnlyObjectDeclaration2RefCountFND MUST contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 26:
        raise OneStoreFormatError(
            "ReadOnlyObjectDeclaration2RefCountFND payload MUST be 26 bytes",
            offset=node.header.offset,
        )
    body = node.fnd[:9]
    ref_count = int(node.fnd[9])
    oid, jcid, has_oid_refs, has_osid_refs = _parse_object_declaration2_body(node, ctx=ctx, body_bytes=body)
    base = ObjectDeclaration2RefCountFND(
        ref=node.chunk_ref,
        oid=oid,
        jcid=jcid,
        has_oid_references=has_oid_refs,
        has_osid_references=has_osid_refs,
        ref_count=ref_count,
    )

    md5_hash = bytes(node.fnd[10:26])
    if len(md5_hash) != 16:
        raise OneStoreFormatError(
            "ReadOnlyObjectDeclaration2RefCountFND.md5Hash MUST be 16 bytes",
            offset=node.header.offset,
        )
    return ReadOnlyObjectDeclaration2RefCountFND(base=base, md5_hash=md5_hash)


def _parse_readonly_object_declaration2_large_refcount_fnd(
    node: FileNode, ctx: ParseContext
) -> ReadOnlyObjectDeclaration2LargeRefCountFND:
    if node.header.base_type not in (1, 2):
        msg = "ReadOnlyObjectDeclaration2LargeRefCountFND MUST have BaseType==1 or BaseType==2"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)
    if node.chunk_ref is None:
        raise OneStoreFormatError(
            "ReadOnlyObjectDeclaration2LargeRefCountFND MUST contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 29:
        raise OneStoreFormatError(
            "ReadOnlyObjectDeclaration2LargeRefCountFND payload MUST be 29 bytes",
            offset=node.header.offset,
        )
    body = node.fnd[:9]
    r = BinaryReader(node.fnd[9:13])
    ref_count = int(r.read_u32())
    if r.remaining() != 0:
        raise OneStoreFormatError(
            "ReadOnlyObjectDeclaration2LargeRefCountFND parse did not consume refcount",
            offset=node.header.offset,
        )

    oid, jcid, has_oid_refs, has_osid_refs = _parse_object_declaration2_body(node, ctx=ctx, body_bytes=body)
    base = ObjectDeclaration2LargeRefCountFND(
        ref=node.chunk_ref,
        oid=oid,
        jcid=jcid,
        has_oid_references=has_oid_refs,
        has_osid_references=has_osid_refs,
        ref_count=ref_count,
    )

    md5_hash = bytes(node.fnd[13:29])
    if len(md5_hash) != 16:
        raise OneStoreFormatError(
            "ReadOnlyObjectDeclaration2LargeRefCountFND.md5Hash MUST be 16 bytes",
            offset=node.header.offset,
        )
    return ReadOnlyObjectDeclaration2LargeRefCountFND(base=base, md5_hash=md5_hash)


def _parse_hashed_chunk_descriptor2_fnd(node: FileNode, ctx: ParseContext) -> HashedChunkDescriptor2FND:
    # Spec (docs/ms-onestore/15-hashed-chunk-list.md): BaseType=1, FileNodeChunkReference + 16-byte MD5.
    if node.header.base_type != 1:
        msg = "HashedChunkDescriptor2FND MUST have BaseType==1"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)
    if node.chunk_ref is None:
        raise OneStoreFormatError(
            "HashedChunkDescriptor2FND MUST contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 16:
        raise OneStoreFormatError(
            "HashedChunkDescriptor2FND payload MUST be 16 bytes (MD5)",
            offset=node.header.offset,
        )

    guid_hash = bytes(node.fnd)
    return HashedChunkDescriptor2FND(blob_ref=node.chunk_ref, guid_hash=guid_hash)


def _parse_object_revision_with_refcount_fndx(node: FileNode, ctx: ParseContext) -> ObjectRevisionWithRefCountFNDX:
    if node.header.base_type not in (1, 2):
        msg = "ObjectRevisionWithRefCountFNDX MUST have BaseType==1 or BaseType==2"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)
    if node.chunk_ref is None:
        raise OneStoreFormatError(
            "ObjectRevisionWithRefCountFNDX MUST contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 5:
        raise OneStoreFormatError(
            "ObjectRevisionWithRefCountFNDX payload MUST be 5 bytes",
            offset=node.header.offset,
        )
    r = BinaryReader(node.fnd)
    oid = CompactID.parse(r)
    flags = int(r.read_u8())
    if r.remaining() != 0:
        raise OneStoreFormatError(
            "ObjectRevisionWithRefCountFNDX parse did not consume full payload",
            offset=node.header.offset,
        )
    has_oid_refs = bool(flags & 0x01)
    has_osid_refs = bool(flags & 0x02)
    ref_count = int((flags >> 2) & 0x3F)
    return ObjectRevisionWithRefCountFNDX(
        ref=node.chunk_ref,
        oid=oid,
        has_oid_references=has_oid_refs,
        has_osid_references=has_osid_refs,
        ref_count=ref_count,
    )


def _parse_object_revision_with_refcount2_fndx(node: FileNode, ctx: ParseContext) -> ObjectRevisionWithRefCount2FNDX:
    if node.header.base_type not in (1, 2):
        msg = "ObjectRevisionWithRefCount2FNDX MUST have BaseType==1 or BaseType==2"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)
    if node.chunk_ref is None:
        raise OneStoreFormatError(
            "ObjectRevisionWithRefCount2FNDX MUST contain a FileNodeChunkReference",
            offset=node.header.offset,
        )
    if len(node.fnd) != 12:
        raise OneStoreFormatError(
            "ObjectRevisionWithRefCount2FNDX payload MUST be 12 bytes",
            offset=node.header.offset,
        )
    r = BinaryReader(node.fnd)
    oid = CompactID.parse(r)
    flags_u32 = int(r.read_u32())
    ref_count = int(r.read_u32())
    if r.remaining() != 0:
        raise OneStoreFormatError(
            "ObjectRevisionWithRefCount2FNDX parse did not consume full payload",
            offset=node.header.offset,
        )
    has_oid_refs = bool(flags_u32 & 0x01)
    has_osid_refs = bool(flags_u32 & 0x02)
    reserved = (flags_u32 >> 2) & 0x3FFFFFFF
    if reserved != 0:
        msg = "ObjectRevisionWithRefCount2FNDX.Reserved MUST be 0"
        if ctx.strict:
            raise OneStoreFormatError(msg, offset=node.header.offset)
        ctx.warn(msg, offset=node.header.offset)
    return ObjectRevisionWithRefCount2FNDX(
        ref=node.chunk_ref,
        oid=oid,
        has_oid_references=has_oid_refs,
        has_osid_references=has_osid_refs,
        ref_count=ref_count,
    )


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
    0x021: _parse_global_id_table_start_fndx,
    0x022: _parse_global_id_table_start2_fnd,
    0x024: _parse_global_id_table_entry_fndx,
    0x025: _parse_global_id_table_entry2_fndx,
    0x026: _parse_global_id_table_entry3_fndx,
    0x028: _parse_global_id_table_end_fndx,
    0x059: _parse_root_object_reference2_fndx,
    0x05A: _parse_root_object_reference3_fnd,
    0x084: _parse_object_info_dependency_overrides_fnd,
    0x08C: _parse_data_signature_group_definition_fnd,
    0x090: _parse_file_data_store_list_reference_fnd,
    0x094: _parse_file_data_store_object_reference_fnd,
    0x0A4: _parse_object_declaration2_refcount_fnd,
    0x0A5: _parse_object_declaration2_large_refcount_fnd,
    0x0B0: _parse_object_group_list_reference_fnd,
    0x0B4: _parse_object_group_start_fnd,
    0x0B8: _parse_object_group_end_fnd,
    0x0C4: _parse_readonly_object_declaration2_refcount_fnd,
    0x0C5: _parse_readonly_object_declaration2_large_refcount_fnd,
    0x0C2: _parse_hashed_chunk_descriptor2_fnd,
    0x041: _parse_object_revision_with_refcount_fndx,
    0x042: _parse_object_revision_with_refcount2_fndx,
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
