# OneStore layer overview

The OneStore layer parses the **binary container format** used by `.one` and `.onetoc2`.

This layer should be **100% language-agnostic** and should not know about pages, outlines, tags, or any UI concepts.

## Core idea

A OneStore file is a collection of linked structures referenced by **chunk references** (FCR: `(stp, cb)`). The fundamental traversal primitive is:

1) Read a structure header
2) Follow a chunk reference to another region
3) Parse a *file node list* from a chain of fragments
4) Decode nodes (raw + typed) and follow more references

## Recommended outputs

At minimum, implement these outputs:

- `Header`
- `TransactionLogIndex` (committed node limits)
- `RootFileNodeListManifests` (object space refs, etc.)
- `ObjectSpacesSummary` (object space manifest refs + revisions + group refs)

Optionally (but strongly recommended for MS-ONE):

- `ObjectSpacesWithResolvedIds` (CompactID → ExtendedGUID resolution)
- `ObjectSpacesWithRevisions` (effective revision interpretation)
- `FileDataStoreIndex`

## Key submodules

- Binary I/O and safety: bounded reader, endian helpers
- Common types: GUID, chunk refs, compact refs
- Header
- Transaction log
- File node list fragments and file nodes
- Typed file node decoding (by `FileNodeID`)
- Object space and revision manifest parsing
- Optional hashed chunk list + file data store parsing

## Layout details (the missing piece)

If you are implementing the parser from scratch, you will need concrete binary layouts (field sizes/encodings). In this repository those details exist, but they are **not** duplicated inside the plan files by default.

Use these sources:

- Compact structure catalog: `10-onestore/99-layout-reference.md`
- Curated, parser-oriented docs: `docs/ms-onestore/*`
- Raw spec extract: `../ms-onestore_structures_extract.txt`

## Reference implementation mapping (this repo)

- OneStore code: `src/aspose/note/_internal/onestore/*`
- OneStore docs: `docs/ms-onestore/*`
- OneStore tests: `tests/test_header.py`, `tests/test_txn_log.py`, `tests/test_file_node_list.py`, `tests/test_file_node_core.py`, `tests/test_chunk_refs_and_crc.py`, `tests/test_common_types.py`, `tests/test_object_data_structures.py`, `tests/test_io.py`

