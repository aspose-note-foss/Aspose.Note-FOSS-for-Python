# Content resolution (images, attachments, rich text)

## FileDataStore resolution

Images/attachments are often referenced by a GUID that must be resolved via FileDataStore.

Design:

- Parse and build `FileDataStoreIndex` in the OneStore layer.
- In the MS-ONE layer, keep blob resolution lazy:
  - store `BlobRef` (GUID + offset/length)
  - load bytes only when required (export or explicit access)

## RichText

RichText parsing typically needs:

- base string data (often Unicode atoms)
- per-range style runs
- hyperlink inference (optional)
- list markers (numbering nodes)

Normalize:

- represent text runs as `[start, end)` ranges
- keep formatting attributes in a run object (maps to public `TextRun` + `TextStyle`)

## Attachments

Normalize metadata:

- filename
- content type (if known)
- bytes

## Images

Normalize:

- width/height (if provided)
- raw bytes
- optional original filename

## Robustness

- Provide tolerant fallback decoding for “extended ASCII” text nodes.
- Avoid crashing on unknown embedded-object types; preserve bytes and label unknown.

## Reference mapping

- `src/aspose/note/_internal/ms_one/entities/parsers.py` (rich text, images, attachments)
- `src/aspose/note/_internal/onestore/file_data.py`
