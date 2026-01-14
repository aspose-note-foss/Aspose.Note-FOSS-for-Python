# File nodes (core + typed decoding)

## FileNode core

A FileNode has:

- `FileNodeID` (type discriminator)
- size/format fields
- optional `BaseType` describing whether the node embeds data or references a separate chunk

Your core FileNode parser must:

- parse the FileNode header
- determine payload size and obtain payload bytes
- validate invariants that prevent desync (e.g., size bounds)

## Typed decoding

Once you can parse raw FileNodes, implement a typed decoding layer:

- `decode_typed(node: FileNode) -> TypedFileNode`
- dispatch by `FileNodeID`

### Minimum typed nodes for end-to-end reading

Implement typed decoding for at least:

- Root list nodes (object space refs)
- Object space manifest start
- Revision manifest boundaries (start/end)
- Role/context declaration nodes
- Object group list references
- Global ID table sequences
- Root object references
- Encryption marker (detect and fail)

### Handling unknown nodes

Unknown `FileNodeID` values should:

- be preserved as `UnknownFileNode` for debug/snapshots
- be ignorable by higher layers unless they are required for correctness

## Reference mapping

- Core: `src/aspose/note/_internal/onestore/file_node_core.py`
- Types/dispatch: `src/aspose/note/_internal/onestore/file_node_types.py`
- Tests: `tests/test_file_node_core.py`
