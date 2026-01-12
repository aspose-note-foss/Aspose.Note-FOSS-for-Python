from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from .chunk_refs import FileChunkReference64x32
from .crc import crc32_rfc3309
from .errors import OneStoreFormatError
from .file_node_list import parse_file_node_list_typed_nodes
from .file_node_types import FileDataStoreListReferenceFND, build_root_file_node_list_manifests
from .hashed_chunk_list import parse_hashed_chunk_list_entries
from .header import Header
from .io import BinaryReader
from .object_space import parse_object_spaces_with_revisions
from .parse_context import ParseContext
from .txn_log import parse_transaction_log


def _uuid_str_from_bytes_le(b: bytes) -> str:
    return str(uuid.UUID(bytes_le=bytes(b))).lower()


def _eg_str(eg) -> str:
    # ExtendedGUID.as_str() returns canonical UUID string for guid part; n is separate.
    # Keep a stable composite representation.
    return f"{eg.as_str()}:{int(eg.n)}"


def _hex_id(n: int) -> str:
    return f"0x{int(n):03X}"


def _count_filenode_ids_for_list(
    data: bytes | bytearray | memoryview,
    first_fragment: FileChunkReference64x32,
    *,
    last_count_by_list_id: dict[int, int],
    ctx: ParseContext,
) -> dict[str, int]:
    out = parse_file_node_list_typed_nodes(
        BinaryReader(data),
        first_fragment,
        last_count_by_list_id=last_count_by_list_id,
        ctx=ctx,
    )

    counts: dict[str, int] = {}
    for tn in out.nodes:
        key = _hex_id(tn.node.header.file_node_id)
        counts[key] = counts.get(key, 0) + 1

    return counts


@dataclass(frozen=True, slots=True)
class SimpleTableSummary:
    """A deterministic, JSON-serializable snapshot summary for SimpleTable.one."""

    data: dict

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.data, ensure_ascii=False, indent=indent, sort_keys=True) + "\n"


def build_simpletable_summary(
    data: bytes | bytearray | memoryview,
    *,
    ctx: ParseContext | None = None,
) -> SimpleTableSummary:
    if ctx is None:
        ctx = ParseContext(strict=True)

    header = Header.parse(BinaryReader(data), ctx=ctx)
    last_count_by_list_id = parse_transaction_log(BinaryReader(data), header, ctx=ctx)

    root_list_counts = _count_filenode_ids_for_list(
        data,
        header.fcr_file_node_list_root,
        last_count_by_list_id=last_count_by_list_id,
        ctx=ParseContext(strict=True, file_size=ctx.file_size),
    )

    root_typed = parse_file_node_list_typed_nodes(
        BinaryReader(data),
        header.fcr_file_node_list_root,
        last_count_by_list_id=last_count_by_list_id,
        ctx=ParseContext(strict=True, file_size=ctx.file_size),
    )
    manifests = build_root_file_node_list_manifests(root_typed.nodes, ctx=ParseContext(strict=True, file_size=ctx.file_size))

    # Step 10+ summary: object spaces and revisions
    step10 = parse_object_spaces_with_revisions(data, ctx=ParseContext(strict=True, file_size=ctx.file_size))

    object_spaces_out: list[dict] = []
    object_group_refs: list[FileChunkReference64x32] = []

    for os in step10.object_spaces:
        revs: list[dict] = []
        for rev in os.revisions:
            manifest = rev.manifest
            root_object_count = 0 if manifest is None else len(manifest.root_objects)
            object_group_count = 0 if manifest is None else len(manifest.object_groups)
            inline_change_count = 0 if manifest is None else len(manifest.inline_changes)

            if manifest is not None:
                for grp in manifest.object_groups:
                    object_group_refs.append(FileChunkReference64x32(stp=int(grp.ref.stp), cb=int(grp.ref.cb)))

            revs.append(
                {
                    "rid": _eg_str(rev.rid),
                    "ridDependent": _eg_str(rev.rid_dependent),
                    "gctxid": _eg_str(rev.gctxid),
                    "revisionRole": int(rev.revision_role),
                    "odcsDefault": int(rev.odcs_default),
                    "hasEncryptionMarker": bool(rev.has_encryption_marker),
                    "rootObjectCount": int(root_object_count),
                    "objectGroupCount": int(object_group_count),
                    "inlineChangeCount": int(inline_change_count),
                }
            )

        object_spaces_out.append(
            {
                "gosid": _eg_str(os.gosid),
                "revisionCount": int(len(os.revisions)),
                "revisions": revs,
            }
        )

    # Optional lists
    file_data_store_guids: list[str] = []
    if manifests.file_data_store_list_ref is not None:
        fcr = FileChunkReference64x32(
            stp=int(manifests.file_data_store_list_ref.ref.stp),
            cb=int(manifests.file_data_store_list_ref.ref.cb),
        )
        file_data_counts = _count_filenode_ids_for_list(
            data,
            fcr,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ParseContext(strict=True, file_size=ctx.file_size),
        )
        lst = parse_file_node_list_typed_nodes(
            BinaryReader(data),
            fcr,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ParseContext(strict=True, file_size=ctx.file_size),
        )
        for tn in lst.nodes:
            if tn.typed is None:
                continue
            if hasattr(tn.typed, "guid_reference"):
                file_data_store_guids.append(_uuid_str_from_bytes_le(getattr(tn.typed, "guid_reference")))
        file_data_store_guids.sort()
    else:
        file_data_counts = {}

    # Hashed chunk list
    hashed_entries = parse_hashed_chunk_list_entries(
        data,
        ctx=ParseContext(strict=True, file_size=ctx.file_size),
        validate_md5=False,
    )

    # Aggregate FileNodeID counts across referenced object group lists (can be large; keep compact)
    object_group_id_counts: dict[str, int] = {}
    for fcr in object_group_refs:
        try:
            counts = _count_filenode_ids_for_list(
                data,
                fcr,
                last_count_by_list_id=last_count_by_list_id,
                ctx=ParseContext(strict=True, file_size=ctx.file_size),
            )
        except OneStoreFormatError:
            # Keep snapshot generation robust; parsing errors will be caught by dedicated tests.
            continue
        for k, v in counts.items():
            object_group_id_counts[k] = object_group_id_counts.get(k, 0) + int(v)

    object_group_id_counts = {k: object_group_id_counts[k] for k in sorted(object_group_id_counts.keys())}

    out = {
        "schemaVersion": 1,
        "fixture": {
            "byteSize": int(len(data)),
            "crc32Rfc3309": int(crc32_rfc3309(data)),
        },
        "header": {
            "guidFileType": str(header.file_type_uuid).lower(),
            "guidFileFormat": str(header.file_format_uuid).lower(),
            "cTransactionsInLog": int(header.c_transactions_in_log),
            "hasFileDataStoreList": bool(manifests.file_data_store_list_ref is not None),
            "hasHashedChunkList": bool(
                not header.fcr_hashed_chunk_list.is_zero() and not header.fcr_hashed_chunk_list.is_nil()
            ),
        },
        "root": {
            "rootGosid": _eg_str(step10.root_gosid),
            "objectSpaceCount": int(len(step10.object_spaces)),
            "objectSpaceGosids": sorted([_eg_str(os.gosid) for os in step10.object_spaces]),
        },
        "objectSpaces": object_spaces_out,
        "fileNodeIdCounts": {
            "rootList": {k: root_list_counts[k] for k in sorted(root_list_counts.keys())},
            "objectGroupsTotal": object_group_id_counts,
            "fileDataStoreList": {k: file_data_counts[k] for k in sorted(file_data_counts.keys())},
        },
        "fileDataStore": {
            "guidReferenceCount": int(len(file_data_store_guids)),
            "guidReferences": file_data_store_guids,
        },
        "hashedChunkList": {
            "entryCount": int(len(hashed_entries)),
        },
    }

    return SimpleTableSummary(data=out)
