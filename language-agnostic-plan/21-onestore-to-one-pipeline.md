# Detailed pipeline: OneStore → MS-ONE (“.one logical layer”)

This document describes the **end-to-end transformation** from raw OneStore bytes to a logical OneNote model.

The goal is to be explicit about sequencing, because many OneStore structures only make sense if parsed in the right order.

---

## Inputs

- `bytes` (or file stream)
- `ParseContext` with:
  - `strict: bool`
  - warning sink
  - `file_size`

## Outputs

- `OneNoteDocumentModel` (internal normalized model)

---

## Phase A — OneStore container parse (structural)

1) **Parse `Header`**
   - Validate format GUID.
   - Extract `fcrTransactionLog`, `fcrFileNodeListRoot`, optional `fcrHashedChunkList`.

2) **Parse `TransactionLog` → `TransactionLogIndex`**
   - Compute `committedNodeCount` for each file node list.

3) **Parse root file node list (typed)**
   - Use committed node limit for the root list.
   - Extract object space references.
   - Build `RootFileNodeListManifests`.

4) **Parse object space manifest lists**
   - For each object space ref:
     - parse the manifest list
     - locate the revision manifest list reference

5) **Parse revision manifest list and split into revisions**
   - Build a `RevisionGraph` per object space:
     - revisions, `ridDependent` edges
     - role/context assignments
     - root references
     - object group list references
     - global ID table sequences

At this point you can already produce a deterministic “OneStore summary” for debugging and snapshot tests.

---

## Phase B — Build resolution context (IDs)

6) **Select the active revision**
   - Choose based on `DEFAULT_CONTEXT` or requested context.
   - Validate that the dependency chain is consistent.

7) **Build effective GID table**
   - If the revision defines a GID sequence, parse/build it.
   - Otherwise inherit from `ridDependent`.

8) **Resolve CompactIDs**
   - Resolve root CompactIDs and any CompactIDs used by object group lists.
   - Keep resolution deterministic and explicit.

This phase produces a stable key space (`ExtendedGUID`) required for object indexing.

---

## Phase C — Object index (objects/properties)

9) **Parse object group lists**
   - For each object group list ref:
     - parse the referenced file node list
     - apply in-scope GID table changes (if any)

10) **Decode object declarations and revisions**

- Decode property sets (`PropertySet`) from object streams.
- Build/merge entries into:

  - `ObjectIndex: Map<ExtendedGUID, ObjectData>`

Where `ObjectData` includes:

- `jcid` (class)
- `properties` (PropertySet)
- optional metadata (timestamps, revision origin)

---

## Phase D — Entity graph

11) **Parse structural entities**

- Document/Section tree
- Pages

12) **Parse page content entities**

- Outlines / outline elements
- RichText + formatting runs
- Tables
- Tags
- Lists

13) **Resolve resources**

- FileDataStore index parse (if not already built in OneStore phase)
- Image/attachment GUID → bytes

---

## Phase E — Normalize

14) Normalize output model:

- stable ordering
- consistent run ranges
- graceful handling of unknown JCIDs/PropertyIDs

---

## Reference mapping (this repo)

- OneStore summary + revisions: `src/aspose/note/_internal/onestore/object_space.py`, `src/aspose/note/_internal/onestore/summary.py`
- MS-ONE read pipeline: `src/aspose/note/_internal/ms_one/reader.py`, `src/aspose/note/_internal/ms_one/object_index.py`
- Entity parsing: `src/aspose/note/_internal/ms_one/entities/*`
