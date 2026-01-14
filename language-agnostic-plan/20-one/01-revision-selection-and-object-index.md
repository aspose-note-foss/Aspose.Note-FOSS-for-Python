# Revision selection and object index

## 1) Select an active revision

OneStore provides many revisions; you must choose the correct one for a viewing context.

Recommended policy (matching the reference intent):

- Prefer a revision assigned to `DEFAULT_CONTEXT` (or equivalent) by role/context assignment nodes.
- If assignments point to an inconsistent revision chain, recover using the `ridDependent` chain (choose the newest revision with a valid dependency chain).

Expose:

- `select_revision(object_space, context) -> RevisionId`

## 2) Build effective Global ID Table (GID)

CompactIDs must be resolved using the GID table sequence.

Rules:

- Each revision may define a GID sequence, or inherit from dependency revision.
- Some lists can contain “in-list” GID table changes; resolution must respect scope.

Expose:

- `build_effective_gid_table(revision) -> GidTable`
- `resolve_compact_id(compact_id, gid_table) -> ExtendedGUID`

## 3) Build an object index

Goal: create a deterministic mapping:

- `ExtendedGUID -> ObjectData`

Where `ObjectData` includes:

- object type/class (JCID)
- property sets
- backlinks/references (optional)

Typical algorithm:

1) Collect object group list references for the chosen revision.
2) For each referenced list:
   - parse list nodes
   - apply any in-scope GID table changes
   - decode object declarations and revisions into object entries
3) Merge into a final map.

Key correctness points:

- Apply revision overrides in the correct order.
- Do not allow unresolved CompactIDs to silently corrupt the index in strict mode.

## Reference mapping

- `src/aspose/note/_internal/ms_one/object_index.py`
- `src/aspose/note/_internal/ms_one/compact_id.py`
- `src/aspose/note/_internal/onestore/object_space.py` (resolved IDs / revisions)
