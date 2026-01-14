# Implementation checklists

These checklists help ensure each layer is implemented with predictable behavior and adequate tests.

## OneStore layer checklist

- [ ] Bounded reader with absolute offsets
- [ ] `FormatError(offset)` for all structural failures
- [ ] Header parse + strict invariants + warning mode
- [ ] Transaction log parse with `cTransactionsInLog` limit semantics
- [ ] FileNodeListFragment chain parser (terminator + `nextFragment`)
- [ ] FileNode parser (size checks, base-type handling)
- [ ] Typed file node decoding for the minimum set
- [ ] Object space manifest parsing
- [ ] Revision manifest splitting and ordering/state machine
- [ ] Global ID table parsing and effective-table inheritance
- [ ] CompactID → ExtendedGUID resolution
- [ ] FileDataStore parsing + lazy blob resolution
- [ ] Hashed chunk list parsing (+ optional MD5 validation)
- [ ] CRC32 `.one` support (+ `.onetoc2` plan if needed)

## MS-ONE layer checklist

- [ ] Revision selection (context + recovery)
- [ ] Object index builder (deterministic)
- [ ] Property access helpers
- [ ] Entity dispatcher by JCID
- [ ] Parsers: Page tree, Outline/OutlineElement, RichText runs, Images, Attachments, Tables
- [ ] Tags and numbering
- [ ] Tolerant degradation for unknown JCIDs/PropertyIDs
- [ ] Internal normalized model stable across versions

## Public API layer checklist

- [ ] Public DOM types (Document/Page/Outline/…)
- [ ] Mapping adapter from internal model to DOM
- [ ] Save/export interface
- [ ] PDF export (text, images, tables)
- [ ] Image extraction and text extraction utilities
- [ ] Clear exception mapping

## Tests checklist

- [ ] OneStore unit tests (reader/header/txn/nodes/object streams)
- [ ] OneStore summary snapshot tests (object spaces, revision graph)
- [ ] MS-ONE object index unit tests
- [ ] MS-ONE entity unit tests with synthetic object indices
- [ ] Integration tests with real `.one` fixtures
- [ ] Public API DOM tests
- [ ] Export smoke tests (PDF)
