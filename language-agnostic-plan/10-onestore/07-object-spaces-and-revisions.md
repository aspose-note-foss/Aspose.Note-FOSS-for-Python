# Object spaces and revision manifests

This is the “container-to-logical bridge” within OneStore.

## Step-by-step pipeline

1) Parse header.
2) Parse transaction log to compute committed node limits.
3) Parse root file node list (typed) → extract object space refs.
4) For each object space:
   - parse its manifest list
   - extract revision manifest list reference
5) Parse revision manifest list and split it into revisions.
6) For each revision:
   - parse revision content (ordering/state machine)
   - collect:
     - dependency revision ID
     - object group list refs
     - global id table sequences
     - root object refs
     - role/context assignments

## Revision splitting

Revisions are delimited by specific start/end file nodes. The exact IDs differ between `.one` and `.onetoc2`.

Recommendations:

- Implement a generic revision splitter that accepts:
  - start node types
  - end node type
  - version-specific “must appear” sequences

## Revision correctness checks

Enforce checks that prevent misinterpretation:

- first node of revision list must be a revision-manifest-list start
- `ridDependent` must refer to a previous revision (in-list)
- role/context assignments use “last assignment wins” semantics
- object group list references must not be nil

## Reference mapping

- Code: `src/aspose/note/_internal/onestore/object_space.py`
- Summary builder: `src/aspose/note/_internal/onestore/summary.py`
- Spec docs: `docs/ms-onestore/*` and revision parsing doc referenced from code comments

## Layout reference

- Compact layout catalog: `10-onestore/99-layout-reference.md` (FileNodeID catalog for manifests/revisions)
- Curated docs: `docs/ms-onestore/16-root-file-node-list.md`, `docs/ms-onestore/17-revision-manifest-parsing.md`
- Raw spec extract: `../ms-onestore_structures_extract.txt` (root file node list + revision manifest constraints)

