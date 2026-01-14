# Object data and properties (OneStore object streams)

Object data encodes the actual property sets that higher layers interpret.

## What to implement

- `PropertyType` enum (includes scalar, blob, reference, nested set, array-of-sets)
- `Property` (ID + type + value)
- `PropertySet` (list of Property)
- Stream decoders:
  - OIDs stream (CompactIDs)
  - OSIDs stream (object space IDs)
  - Context IDs
  - PropertySet stream

## Reference-style decoding approach

- Read a property header that provides type + ID.
- For each type:
  - fixed-size scalars: read directly
  - no-data: value is implied
  - length-prefixed blob: read length then bytes
  - references: read an index into a separate reference stream (validate bounds)
  - nested property set: recurse with strict size accounting

## Correctness rules

- All stream lengths must be consistent.
- Reference counts must be non-negative.
- Any leftover bytes after a full decode is a structural error in strict mode.

## Reference mapping

- Code: `src/aspose/note/_internal/onestore/object_data.py`
- Tests: `tests/test_object_data_structures.py`
