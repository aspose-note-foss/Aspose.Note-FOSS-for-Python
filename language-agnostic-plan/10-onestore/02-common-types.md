# OneStore common types

## GUID

OneStore uses the standard 16-byte GUID, but often stored in a mixed-endian layout (the classic Windows GUID encoding).

Required operations:

- parse GUID from bytes
- compare
- stringify in canonical form

## Chunk references (FCR)

Many structures use a file chunk reference:

- `stp`: absolute file offset (stream position)
- `cb`: byte count

Also define sentinel meanings:

- `nil` reference (often `stp = 0xFFFFFFFFFFFFFFFF`, `cb = 0` or similar sentinel encodings)
- `zero` reference (stp=0, cb=0)

Provide helpers:

- `is_nil()` / `is_zero()`
- `is_in_bounds(file_size)`

## FileNodeChunkReference

Some refs are encoded in a compact form where `stp` and `cb` are stored with different “formats” and may require scaling (e.g., `*8`).

Recommendation:

- store both raw encoded fields and expanded `stp/cb`.
- centralize decoding rules to avoid duplicated bugs.

## CompactID and ExtendedGUID (bridge to MS-ONE)

The OneStore layer should *parse* CompactIDs where they appear but should not interpret them unless it also implements GID resolution.

If you implement resolution at OneStore layer, define:

- `CompactID` (raw fields, plus helpers)
- `ExtendedGUID` (GUID + additional identity components)

## Reference mapping

- `src/aspose/note/_internal/onestore/common_types.py`
- `src/aspose/note/_internal/onestore/chunk_refs.py`
- `src/aspose/note/_internal/ms_one/compact_id.py` (CompactID semantics)
