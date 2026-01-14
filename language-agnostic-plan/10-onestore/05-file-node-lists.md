# File node lists and fragments

## Concept

A **FileNodeList** is stored as a chain of **FileNodeListFragments**. Each fragment contains:

- fragment header (magic, fragment ID)
- a sequence of file nodes
- a fixed-position `nextFragment` reference
- padding/alignment

## Parsing algorithm

1) Start from an FCR `(stp, cb)`.
2) Read fragment header and validate magic.
3) Determine the “node bytes region” (everything before the fixed `nextFragment` region).
4) Iterate nodes:
   - read 4-byte node header marker
   - stop if marker indicates terminator
   - parse file node header to know its byte length
   - read node bytes
5) Validate terminator rules.
6) Follow `nextFragment` until nil/zero.

## Committed node limits

The parser should accept a `committed_limit` value (from transaction log) that limits how many nodes are returned from the chain.

Important: committed limit is in **nodes**, not bytes.

## Output forms

Expose both:

- `parse_file_node_list_raw(...) -> list<RawNodeBytes>`
- `parse_file_node_list_nodes(...) -> list<FileNode>`
- `parse_file_node_list_typed_nodes(...) -> list<TypedFileNode>`

## Robustness heuristics

- Some files have zero padding in the node bytes region; treat a `0x00000000` marker as end-of-nodes.
- Treat both `nil` and `zero` chunk refs as end markers defensively.

## Reference mapping

- Spec docs: `docs/ms-onestore/06-file-node-list.md`
- Code: `src/aspose/note/_internal/onestore/file_node_list.py`
- Tests: `tests/test_file_node_list.py`
