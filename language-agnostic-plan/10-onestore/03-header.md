# OneStore header

## Responsibilities

- Determine file type (`.one` vs `.onetoc2`) and format version.
- Provide references (FCRs) to root structures:
  - transaction log
  - root file node list
  - optional hashed chunk list
- Provide file-length expectations and validation context.

## Parsing steps

1) Read fixed-size header.
2) Validate:
   - file format GUID matches known values
   - required FCRs are non-nil and within bounds
   - `cTransactionsInLog != 0`
   - reserved/debug fields are zero when spec says MUST
3) Collect warnings for non-fatal mismatches (e.g., expected file length differs).

## Output

- `Header` object containing:
  - `guidFileFormat`
  - `fcrTransactionLog`
  - `fcrFileNodeListRoot`
  - `fcrHashedChunkList` (optional)
  - `cbExpectedFileLength` (optional)
  - `cTransactionsInLog`

## Reference mapping

- Spec docs: `docs/ms-onestore/03-header.md`
- Code: `src/aspose/note/_internal/onestore/header.py`
- Tests: `tests/test_header.py`
