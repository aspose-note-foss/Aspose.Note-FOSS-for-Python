# OneStore layout reference (structures + fields)

This file exists to remove an implementation blocker: the main plan docs under `10-onestore/*` are intentionally **algorithm- and interface-focused**, but implementing a parser requires concrete binary layouts.

This document provides a **compact “structure catalog”** (field names + sizes + key invariants) and points to the **authoritative in-repo sources**.

## Where to find authoritative layouts in this repo

- Curated docs (recommended starting point): `docs/ms-onestore/*`
  - These files describe the same structures with parsing notes and common real-world deviations.
- Raw spec extract (good for exact field lists and sizes): `../ms-onestore_structures_extract.txt`
  - Extracted from the public [MS-ONESTORE] specification (“Structures” section).
- MS-ONE logical layer extract (properties/entities, for the next layer): `../ms-one_spec_structure.txt`

## Core binary primitives

### Endianness and alignment

- All integer fields are little-endian.
- Structures are aligned on 1-byte boundaries (no implicit padding).

### File chunk references (FCR)

All “references” in OneStore are (offset, size) pairs.

- `FileChunkReference32` (8 bytes)
  - `stp: u32` (absolute file offset)
  - `cb: u32` (byte count)
  - Sentinels: `fcrZero` = `(0,0)`, `fcrNil` = `(0xFFFFFFFF,0)`

- `FileChunkReference64` (16 bytes)
  - `stp: u64`, `cb: u64`

- `FileChunkReference64x32` (12 bytes)
  - `stp: u64`, `cb: u32`
  - Sentinels: `fcrZero` = `(0,0)`, `fcrNil` = `(all_ones,0)`

Implementation notes (from Python parser):

- Always validate `0 <= stp <= file_size`, `0 <= cb <= file_size`, and `stp + cb <= file_size`.
- Treat `cb==0` + sentinel-ish `stp` as “no reference” (don’t follow).

### FileNodeChunkReference (variable)

`FileNodeChunkReference` is the compact reference used inside `FileNode.fnd` when `BaseType` is 1 or 2.

- The **sizes** and **compression/scaling** rules are controlled by the parent `FileNode` header:
  - `StpFormat`:
    - 0: 8 bytes, uncompressed
    - 1: 4 bytes, uncompressed
    - 2: 2 bytes, compressed (multiply by 8)
    - 3: 4 bytes, compressed (multiply by 8)
  - `CbFormat`:
    - 0: 4 bytes, uncompressed
    - 1: 8 bytes, uncompressed
    - 2: 1 byte, compressed (multiply by 8)
    - 3: 2 bytes, compressed (multiply by 8)

## Header (2.3.1)

The header is a **fixed 1024-byte** structure at file offset 0.

Minimum set you need to parse a file:

- `guidFileType: GUID(16)` → `.one` vs `.onetoc2`
- `guidFileFormat: GUID(16)` MUST be `{109ADD3F-911B-49F5-A5D0-1791EDC8AED8}`
- `cTransactionsInLog: u32` MUST NOT be 0
- `fcrTransactionLog: FileChunkReference64x32` MUST NOT be zero/nil
- `fcrFileNodeListRoot: FileChunkReference64x32` MUST NOT be zero/nil
- Optional:
  - `fcrHashedChunkList: FileChunkReference64x32`
  - `fcrFreeChunkList: FileChunkReference64x32`
  - `cbExpectedFileLength: u64` (in practice can mismatch; treat as warning)

Python reference:

- `src/aspose/note/_internal/onestore/header.py` (`Header.parse` enforces strict MUST rules and bounds)
- Curated doc: `docs/ms-onestore/03-header.md`

## Transaction log (2.3.3)

### TransactionLogFragment (2.3.3.1)

A referenced chunk contains:

- `sizeTable: TransactionEntry[]` (N entries, each 8 bytes)
- `nextFragment: FileChunkReference64x32` (12 bytes)
- Some real files include trailing padding bytes inside the referenced chunk size.

Python behavior:

- `sizeTable` length is computed as the largest prefix where `(cb - 12)` becomes a multiple of 8.
- Parsing stops once `Header.cTransactionsInLog` sentinel entries have been seen; `nextFragment` is ignored after that.

### TransactionEntry (2.3.3.2)

- `srcID: u32`
- `value: u32`

Rules:

- Sentinel entry: `srcID == 1`
  - `value` is a CRC in the spec (often not required for read-only parsing)
- Non-sentinel entry:
  - `srcID` is `FileNodeListID`
  - `value` is the **committed node count** for that list after this transaction

Python tolerance:

- Non-sentinel entries with `value == 0` are treated as no-op with a warning.

References:

- `src/aspose/note/_internal/onestore/txn_log.py`
- Curated doc: `docs/ms-onestore/05-transaction-log.md`

## File node lists (2.4)

### FileNodeListHeader (2.4.2) — 16 bytes

- `uintMagic: u64` MUST be `0xA4567AB1F5F7F4C4`
- `FileNodeListID: u32` MUST be `>= 0x10`
- `nFragmentSequence: u32` (0,1,2,...) within the same list

### FileNodeListFragment (2.4.1)

A fragment is stored in a referenced chunk `(stp, cb)`.

Logical fields:

- `header: FileNodeListHeader` (16)
- `rgFileNodes: byte stream` of `FileNode` structures (variable)
- `padding: bytes` (ignored)
- `nextFragment: FileChunkReference64x32` (12) at **fixed position** `stp + cb - (12 + 8)`
- `footer: u64` MUST be `0x8BC215C38233BA4B` at the end

Stop conditions while reading `rgFileNodes` (best practice / matches Python parser):

- Not enough space for a 4-byte `FileNode` header before `nextFragment`.
- Encounter `ChunkTerminatorFND (FileNodeID=0x0FF)`.
- Reach committed node limit (from the transaction log) for that list.
- Heuristic: if next 4 bytes are `0x00000000`, treat it as padding and stop.

Python references:

- `src/aspose/note/_internal/onestore/file_node_list.py`
- Curated doc: `docs/ms-onestore/06-file-node-list.md`

## FileNode core (2.4.3)

### FileNode header (packed bits, 4 bytes)

Interpret the first `u32` as bit fields (from least-significant bits upward) with widths:

`[10, 13, 2, 2, 4, 1]` → `(FileNodeID, Size, StpFormat, CbFormat, BaseType, Reserved)`

Rules:

- `Size` is total node size in bytes (includes these 4 header bytes)
- `Reserved` MUST be 1 (warn-only is usually fine)
- If `BaseType == 0` then `CbFormat MUST be 0` and both `StpFormat/CbFormat` are ignored
- If `BaseType in {1,2}`, `fnd` begins with a `FileNodeChunkReference` with formats defined above
- `ChunkTerminatorFND` (`FileNodeID==0x0FF`) MUST have `Size==4` (no payload)

Python reference:

- `src/aspose/note/_internal/onestore/file_node_core.py`
- Curated doc: `docs/ms-onestore/07-file-node-core.md`

## Typed FileNodes: minimum ID catalog

This is the “router table” you need to extract object spaces, revisions, and objects.

The full list is in `../ms-onestore_structures_extract.txt` (FileNodeID table) and in curated docs under `docs/ms-onestore/08..11-*.md`.

Common “must support” IDs for end-to-end reading:

- Root list / object spaces:
  - `0x008` ObjectSpaceManifestListReference (BaseType=2)
  - `0x004` ObjectSpaceManifestRoot (BaseType=0)
  - `0x090` FileDataStoreListReference (BaseType=2)

- Object space manifest list:
  - `0x00C` ObjectSpaceManifestListStart (BaseType=0)
  - `0x010` RevisionManifestListReference (BaseType=2)

- Revision manifest list:
  - `0x014` RevisionManifestListStart (BaseType=0)
  - `0x01B` RevisionManifestStart4 (.onetoc2)
  - `0x01E` RevisionManifestStart6 (.one)
  - `0x01F` RevisionManifestStart7 (.one)
  - `0x01C` RevisionManifestEnd
  - `0x05C` RevisionRoleDeclaration
  - `0x05D` RevisionRoleAndContextDeclaration

- Root objects:
  - `0x059` RootObjectReference2 (.onetoc2)
  - `0x05A` RootObjectReference3 (.one)

- Global ID table:
  - `0x021` GlobalIdTableStart (.onetoc2)
  - `0x022` GlobalIdTableStart2 (.one)
  - `0x024` GlobalIdTableEntry
  - `0x025` GlobalIdTableEntry2 (.onetoc2)
  - `0x026` GlobalIdTableEntry3 (.onetoc2)
  - `0x028` GlobalIdTableEnd

- Object groups:
  - `0x0B0` ObjectGroupListReference (BaseType=2)
  - `0x0B4` ObjectGroupStart
  - `0x0B8` ObjectGroupEnd

- Object declarations / revisions (object data is referenced by FileNodeChunkReference):
  - `0x041` / `0x042` ObjectRevisionWithRefCount
  - `0x02D` / `0x02E` ObjectDeclarationWithRefCount
  - `0x0A4` / `0x0A5` ObjectDeclaration2*RefCount
  - `0x072` / `0x073` ObjectDeclarationFileData3*RefCount
  - `0x0C4` / `0x0C5` ReadOnlyObjectDeclaration2*RefCount

- Encryption marker:
  - `0x07C` ObjectDataEncryptionKeyV2 (treat as “encrypted ⇒ unsupported” in v1)

- Hashed chunk list:
  - `0x0C2` HashedChunkDescriptor2 (BaseType=1)

Python references:

- `src/aspose/note/_internal/onestore/file_node_types.py` (typed parsers + dispatch)
- `src/aspose/note/_internal/onestore/object_space.py` (revision parsing/state machine)
