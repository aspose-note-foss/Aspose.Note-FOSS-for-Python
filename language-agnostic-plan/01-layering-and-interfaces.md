# Layering and interfaces (language-agnostic)

A robust OneNote parser is easiest to implement as **three layers** with strict boundaries:

1) **OneStore binary layer** (`.one` / `.onetoc2` container)
2) **MS-ONE logical layer** (objects/revisions/entities)
3) **Public API layer** (Aspose.Note-like DOM + saving/export)

This document defines the recommended module boundaries and cross-layer interfaces.

---

## 1) OneStore layer: responsibilities

### Responsibilities

- Provide a safe, bounded binary reader.
- Parse the core container structures:
  - header
  - transaction log
  - (optional) free chunk list (if you need allocation maps)
  - file node list fragments → file node lists
  - file nodes (raw and typed)
  - object spaces summary and revision manifests
  - file data store + hashed chunk list (optional validation)
- Enforce structural invariants and detect unsupported features (encryption, unknown required nodes).

### Output interface (minimal)

Implement a “OneStore view” that the MS-ONE layer can consume without knowing any parsing details:

- `Header` (file format, important FCRs)
- `TransactionLogIndex` (committed node limits per file-node-list)
- `ObjectSpacesSummary`:
  - list of object spaces (IDs + manifest list refs)
  - list of revisions per object space, including:
    - revision IDs, dependency IDs
    - role/context assignments
    - root references
    - object group list references
    - global id table sequences
- `FileDataStoreIndex` (GUID → blob range or blob bytes)

The OneStore layer should also provide a “raw bytes resolver”:

- `read_chunk(fcr) -> bytes`
- `read_file_node_list(fcr, committed_limit) -> list<FileNode>`

---

## 2) MS-ONE logical layer: responsibilities

### Responsibilities

- Select the “active revision” for a given context.
- Build an **object index** (ExtendedGUID → ObjectData/PropertySet) for that revision.
- Decode objects into an entity graph:
  - Document/Section/Page
  - Outline/OutlineElement
  - RichText + style runs
  - Image/Attachment (logical); public API maps to `Image`/`AttachedFile`
  - Tables
  - Tags (logical); public API maps to `NoteTag`
  - Lists/numbering
- Provide a stable, testable internal representation (“internal OneNote model”) independent of the public API.

### Input interface

The MS-ONE layer consumes:

- `ObjectSpacesSummary` + revision manifests
- Global ID table building/resolution
- Access to object group lists and object data
- FileDataStore resolution

### Output interface

- `OneNoteDocumentModel` (internal), containing normalized entities and decoded content.

---

## 3) Public API layer: responsibilities

### Responsibilities

- Expose a user-facing DOM similar to Aspose.Note:
  - Document/Page/Outline/RichText/Image/AttachedFile/Table/NoteTag
- Provide saving/export:
  - PDF export (layout + fonts + images)
  - Save images to disk
  - Extract text
- Keep API layer independent of OneStore binary details.

### Input interface

- `OneNoteDocumentModel` from the MS-ONE layer.

---

## Cross-cutting concerns

### Error handling

- **Binary errors**: structural violations, out-of-bounds, invalid values → `FormatError` with absolute offsets.
- **Semantic errors**: missing expected logical roots, unsupported features → `SemanticError` without offsets.
- **Warnings**: tolerant parsing should record warnings with context and continue.

Recommendation:

- `strict` flag in `ParseContext` (or similar).
- `WarningSink` (collect warnings, or log, or ignore).

### Determinism

- Ensure stable iteration order and stable IDs in outputs.
- Provide deterministic “summaries” to snapshot in tests.

### Incremental parsing

- Allow parsing only to the needed depth:
  - `OneStoreSummary` only
  - `ObjectSpaces + Resolved IDs` without decoding full entities
  - Full MS-ONE entity graph

---

## Suggested package/module layout

This is a neutral layout you can adapt to any language:

- `io/` → bounded reader, endian helpers
- `onestore/` → header, txn log, file nodes, manifests, object spaces, file data store
- `ms_one/` → compact IDs, GID tables, object index, entity parsers
- `onenote_model/` → internal normalized model
- `public_api/` → Aspose-like DOM classes and adapters
- `export/` → PDF/image/text export
- `tests/` → unit + integration + fixture helpers
