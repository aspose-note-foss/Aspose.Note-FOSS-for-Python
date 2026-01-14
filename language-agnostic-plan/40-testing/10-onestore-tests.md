# OneStore layer tests

## 1) Binary reader tests

- Endianness primitives (`u8/u16/u32/u64`, signed variants)
- Bounds enforcement (read past end raises `FormatError(offset)`)
- Slice reader correctness (absolute offsets preserved)

## 2) Common type tests

- GUID decode/encode round-trips
- FCR nil/zero detection
- Compressed chunk ref decoding (including `*8` scaling)

## 3) Header tests

- Valid `.one` header parses
- Invalid format GUID rejects
- Out-of-bounds FCR rejects
- Non-zero MUST fields reject in strict mode
- Expected file length mismatch yields warning (tolerant)

## 4) Transaction log tests

- Fragment chaining
- Transaction splitting with sentinel
- `cTransactionsInLog` limit behavior (stop early)
- Ignore invalid `nextFragment` once limit reached

## 5) File node list + node tests

- Fragment header/footer magic
- Terminator behavior and enforced `stpNext` rules
- Committed node limit (node count)
- Defensive handling of zero padding in node region

## 6) Typed node tests

For each typed decoder, add:

- known-good bytes fixture
- invariant violations
- unknown node behavior (degrade vs strict)

## 7) Object spaces + revisions tests

Add deterministic summary snapshots:

- object space refs
- revision count + dependency chain
- role/context mapping
- object group list refs

## 8) FileDataStore and hashed chunk list

- FileDataStore object framing and padding
- GUID → blob bytes resolution
- Hashed chunk list entry parsing
- Optional MD5 validation path

## Reference mapping

- Existing OneStore unit tests in this repo cover sections 1–5 and object-data streams.
- Gaps to add: object spaces/revisions, gid table resolution, file data store, hashed chunk list.
