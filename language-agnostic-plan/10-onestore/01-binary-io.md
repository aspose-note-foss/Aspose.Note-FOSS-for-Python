# Binary I/O (bounded reader)

A OneStore parser must treat input as **untrusted bytes**:

- Every read must be bounds-checked.
- Every error must identify the **absolute file offset**.
- Prefer slicing readers into subranges to avoid manual offset arithmetic.

## Required primitives

Implement a `BoundedReader` (or similar) with:

- `tell() -> int` absolute position
- `seek(abs_offset)`
- `slice(abs_offset, length) -> BoundedReader` (a sub-reader with its own bounds)
- `read_bytes(n)`
- `read_u8/u16/u32/u64(le)` and `read_i*` as needed
- `read_guid_le()` (OneStore stores GUIDs in mixed-endian layout)

## Error model

- `FormatError(message, offset)` thrown for:
  - out-of-bounds reads
  - size mismatches
  - invalid magic values
  - invalid enum ranges when the spec says MUST

In tolerant mode, a parser may downgrade some MUST checks to warnings, but must **never** allow structural desynchronization.

## Pattern: parse functions

Each parser should:

1) Read fixed header
2) Validate basic invariants
3) Compute sub-slices for variable parts
4) Parse variable parts using sub-readers
5) Validate that the reader ends at the expected boundary

## Common pitfalls

- “Trailer” fields that are located at a fixed position near the end of a fragment.
- References whose size fields include trailing padding in real files.
- `nil` and `zero` chunk references: treat them as sentinels rather than real offsets.

## Reference mapping

- `src/aspose/note/_internal/onestore/io.py`
- `src/aspose/note/_internal/onestore/errors.py`
