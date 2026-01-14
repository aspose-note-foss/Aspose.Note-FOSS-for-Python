# Testing strategy overview

A OneNote parser benefits from **layered tests**, matching the layered architecture.

## Test layers

1) OneStore unit tests (binary correctness)
2) MS-ONE unit/contract tests (object index + entity parsing)
3) Public API tests (DOM behavior)
4) Integration tests (end-to-end on real `.one` fixtures)

## Principles

- Prefer small, targeted unit tests for low-level parsers.
- Use snapshot/golden tests for summaries and DOM trees.
- Add a few larger fixtures for end-to-end regressions.
- Make every failure actionable:
  - include file name
  - include offsets for binary errors
  - include object IDs/JCIDs for semantic errors

## Reference mapping

Existing tests in this repo are a good blueprint:

- OneStore: `tests/test_header.py`, `tests/test_txn_log.py`, `tests/test_file_node_list.py`, `tests/test_file_node_core.py`, `tests/test_common_types.py`, `tests/test_chunk_refs_and_crc.py`, `tests/test_object_data_structures.py`, `tests/test_io.py`
- MS-ONE: `tests/test_ms_one_*`
- API: `tests/test_aspose_note_*`, `tests/test_pdf_export.py`
- Integration fixtures: `tests/test_integration_*` using `testfiles/*.one`
