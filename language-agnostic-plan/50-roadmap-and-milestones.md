# Roadmap and milestones

This roadmap assumes you want a practical reader that matches the reference behavior, with good tests and incremental deliverables.

## Milestone 0 — Project skeleton

- Create modules for the 3 layers.
- Add a bounded binary reader with endianness helpers.
- Add an error model: `FormatError(offset)`, `SemanticError`, `Warning`.
- Add fixture runner and snapshot system.

**Exit criteria**

- Can open files and read primitives safely.
- Unit tests for reader and bounds pass.

## Milestone 1 — OneStore header + transaction log

- Parse header (strict invariants, FCR sanity).
- Parse transaction log and compute committed node limits.

**Exit criteria**

- Unit tests cover:
  - known-good header
  - invalid GUID/fields
  - txn log splitting and limit behavior

## Milestone 2 — File node lists + file nodes

- Parse FileNodeListFragments chain.
- Parse raw FileNodes.
- Add typed dispatch for a small initial set:
  - root list refs
  - object space refs
  - revision boundaries

**Exit criteria**

- Can parse the root file node list and extract object-space references.
- Unit tests for fragment chaining and terminator behavior.

## Milestone 3 — Object spaces + revision manifests (container-level correctness)

- Parse object space manifest lists.
- Parse revision manifest lists.
- Implement revision splitting and ordering checks.
- Extract role/context assignments and root refs.

**Exit criteria**

- Deterministic “summary” output per file for snapshot testing.

## Milestone 4 — Global ID table + CompactID resolution

- Implement GID table parsing and effective-table inheritance.
- Implement CompactID → ExtendedGUID resolution.
- Re-parse object group lists in the correct GID scope.

**Exit criteria**

- Tests validate:
  - uniqueness rules
  - dependency chain correctness
  - stable resolution of object roots

## Milestone 5 — Object index + MS-ONE entity graph

- Build object index for selected revision.
- Decode property sets.
- Implement entity parsers for:
  - page tree, outlines, rich text
  - images/attachments (via FileDataStore)
  - tables, tags, lists

**Exit criteria**

- Integration tests pass on a suite of `.one` fixtures.

## Milestone 6 — Public API mapping + exports

- Map internal model to public DOM.
- Implement PDF export (first pass).
- Add image save + text extraction.

**Exit criteria**

- Public API tests pass for DOM structure.
- PDF export smoke tests pass.

## Milestone 7 — Hardening

- Fuzz/robustness tests on OneStore layer.
- Performance tuning (streaming, caching file chunks).
- Expand `.onetoc2` support if needed.
