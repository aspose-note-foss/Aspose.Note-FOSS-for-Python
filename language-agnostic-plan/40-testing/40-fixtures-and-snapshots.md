# Fixtures and snapshots

## Fixture types

1) **Micro-fixtures**: raw byte arrays for a single structure (header, txn log fragment, file node).
2) **Mini `.one` fixtures**: small files with one page and one feature.
3) **Feature fixtures**: medium files focusing on one complex feature (tables, tags, history).
4) **Stress fixtures**: large files (optional) used only in nightly builds.

## Snapshot strategy

Snapshots are valuable for:

- OneStore summaries (object spaces, revision graphs)
- MS-ONE normalized summaries (entity counts, titles, resource hashes)
- public DOM tree summaries

Recommendations:

- Snapshot in JSON.
- Keep snapshots stable by:
  - sorting maps by stable keys
  - hashing bytes instead of storing full blobs
  - avoiding non-deterministic ordering

## Fixture repository layout

Suggested layout (language-agnostic):

- `testfiles/` raw `.one` files
- `tests/snapshots/` JSON snapshots
- `tests/fixtures/` byte-level fixtures

## Reference mapping

- This repo uses `testfiles/*.one` and `tests/snapshots/*`.
- Some tests already snapshot summaries; expand that pattern to cover object spaces and entity graphs.
