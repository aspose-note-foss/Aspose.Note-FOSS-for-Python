# FileDataStore and hashed chunk list

## FileDataStore

The FileDataStore is where raw embedded blobs are stored (images, attachments).

Recommended API:

- `FileDataStoreIndex`: `GUID -> BlobRef`
- `resolve_blob(guid) -> bytes` (lazy load)

Parsing responsibilities:

- parse file node list that enumerates data store objects
- parse each data store object header:
  - GUID
  - data length
  - padding/alignment rules

## Hashed chunk list

Some files include a hashed chunk list used to validate chunks by MD5.

Recommended behavior:

- parse entries
- expose them for diagnostics
- optional validation mode: compute MD5 for referenced chunks and compare

## Checksums

- `.one` uses CRC32 in some contexts.
- `.onetoc2` CRC32 support may be separate; plan for it explicitly.

## Reference mapping

- FileDataStore: `src/aspose/note/_internal/onestore/file_data.py`
- Hashed chunk list: `src/aspose/note/_internal/onestore/hashed_chunk_list.py`
- CRC: `src/aspose/note/_internal/onestore/crc.py`
- Tests: `tests/test_chunk_refs_and_crc.py`

## Layout reference

- Curated docs: `docs/ms-onestore/11-file-node-types-file-data.md`, `docs/ms-onestore/15-hashed-chunk-list.md`
- Raw spec extract: `../ms-onestore_structures_extract.txt` (2.3.4.1, 2.5.21–2.5.22, 2.6.13)

