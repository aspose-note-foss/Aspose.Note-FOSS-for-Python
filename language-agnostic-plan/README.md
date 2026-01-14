# Language-agnostic plan: OneNote (.one) parser

This folder describes a **language-agnostic architecture and implementation plan** for a OneNote parser that follows the same layered design as the current Python implementation in this repository.

## Goals

- Parse the **full OneStore container layer** (binary format used by `.one` and `.onetoc2`).
- Build a **logical MS-ONE layer** (“one layer”): objects, revisions, entities (pages, outlines, rich text, images, attachments, tables, tags, lists, etc.).
- Map MS-ONE entities into a **public API** similar to Aspose.Note (Document/Page/Outline/RichText/… + saving/export).
- Provide a **test strategy per layer** (unit/contract/integration) with fixtures and snapshots.

## How to read the plan

- Start with [01-layering-and-interfaces.md](01-layering-and-interfaces.md).
- For exact Aspose.Note-like naming used by this repo, see [32-msone-to-aspose-name-map.md](32-msone-to-aspose-name-map.md).
- Implement the OneStore binary layer using the docs under [10-onestore](10-onestore/00-overview.md).
- Implement the MS-ONE logical layer under [20-one](20-one/00-overview.md).
- Implement the public API mapping under [30-public-api](30-public-api/00-overview.md).
- Follow testing guidance under [40-testing](40-testing/00-overview.md).

## Reference: current Python implementation

This plan is derived from these reference areas:

- OneStore: `src/aspose/note/_internal/onestore/*`
- MS-ONE: `src/aspose/note/_internal/ms_one/*`
- Internal OneNote model: `src/aspose/note/_internal/onenote/*`
- Aspose-like public API: `src/aspose/note/model.py`, `src/aspose/note/saving/*`
- Tests: `tests/test_header.py`, `tests/test_txn_log.py`, `tests/test_file_node_list.py`, `tests/test_ms_one_*`, `tests/test_aspose_note_*`, integration tests in `tests/test_integration_*`

## Non-goals (for v1)

- Writing/serializing `.one` files.
- Full support for `.onetoc2` CRC32 validation (the reference implementation currently has this as TODO).
- Encrypted notebooks (detect and report as unsupported).
