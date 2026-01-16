# Transaction log

The transaction log is used to compute **committed node limits** for file node lists.

## Why it matters

A file node list can be longer than the committed (visible) portion; the transaction log specifies how many nodes are committed for each list. Many parsers must respect this limit to avoid parsing future/uncommitted nodes.

## Parsing model

- The transaction log is a chain of fragments referenced by an initial FCR.
- Each fragment contains a table of updates.
- Updates are grouped into transactions separated by a sentinel.
- Only the first `cTransactionsInLog` transactions are applied.

## Output

- `TransactionLogIndex`: map `FileNodeListID -> committedNodeCount`

## Robustness rules

- Defensive parsing: referenced chunk sizes may include trailing padding.
- Once the transaction limit is reached, ignore any further fragments even if `nextFragment` is garbage.

## Reference mapping

- Spec docs: `docs/ms-onestore/05-transaction-log.md`
- Code: `src/aspose/note/_internal/onestore/txn_log.py`
- Tests: `tests/test_txn_log.py`

## Layout reference

- Compact layout catalog: `10-onestore/99-layout-reference.md` (2.3.3)
- Raw spec extract: `../ms-onestore_structures_extract.txt` (2.3.3.1 / 2.3.3.2)

