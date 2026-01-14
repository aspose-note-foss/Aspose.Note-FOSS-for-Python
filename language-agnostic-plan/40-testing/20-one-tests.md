# MS-ONE layer tests

## 1) Object index tests

- Effective GID table inheritance across `ridDependent` chain
- CompactID resolution correctness
- Object group list replay ordering
- Unknown object types degrade in tolerant mode

## 2) Entity parsing tests (unit)

Create small “synthetic object index” fixtures (not full `.one` files) that validate:

- Page hierarchy and ordering
- RichText:
  - run segmentation correctness
  - style attributes (bold/italic/underline, font, color)
  - hyperlink runs
- Lists:
  - marker detection
  - numbering format
- Tags:
  - tag IDs and propagation
- Tables:
  - cell content parsing
- Images/attachments:
  - GUID resolution to bytes
  - filename inference

## 3) Contract tests vs real `.one` fixtures

For a selected fixture set (like the ones in `testfiles/`):

- parse entities and snapshot a normalized summary
- compare to expected counts/structure

Example summary fields:

- pages: number, titles
- outlines: count and ordering
- images: count, byte hashes, filenames
- attachments: count, filenames
- tags: counts and ids

## Reference mapping

- The repo already has MS-ONE tests for tags/tables and several integrations for images/attachments/history.
- Gaps: explicit object-index tests, numbering/list tests (one file is empty in this repo), tolerant-mode degradation tests.
