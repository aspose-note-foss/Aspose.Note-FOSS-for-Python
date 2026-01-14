# Entity parsing (MS-ONE entities)

This stage turns the object index into a graph of entities.

## Building blocks

### Property access layer

Implement helpers that:

- read typed property values from `PropertySet`
- handle missing/unknown properties
- provide tolerant fallbacks

Recommended API:

- `get_u32(props, pid) -> optional<u32>`
- `get_string(props, pid) -> optional<string>`
- `get_compact_id(props, pid) -> optional<CompactID>`
- `get_children(props) -> list<ExtendedGUID>`

### Entity dispatcher

Dispatch by JCID:

- `parse_entity(jcid, object, context) -> Entity`

Unknown JCIDs should degrade to `UnknownEntity` in tolerant mode.

## Core entity set (minimum viable)

Implement parsers for:

- `Notebook/Section` structure (hierarchy)
- `Page` (title, metadata)
- `Outline` and `OutlineElement`
- `RichText` with style runs
- `Image` (embedded blob GUID + dimensions)
- `Attachment` (blob GUID + filename)
- `Table` (rows/cells)
- `Tag` (including icons/labels)
- list/numbering nodes

## Reference mapping

- `src/aspose/note/_internal/ms_one/reader.py`
- `src/aspose/note/_internal/ms_one/property_access.py`
- `src/aspose/note/_internal/ms_one/entities/base.py`
- `src/aspose/note/_internal/ms_one/entities/parsers.py`
- `src/aspose/note/_internal/ms_one/entities/structure.py`
