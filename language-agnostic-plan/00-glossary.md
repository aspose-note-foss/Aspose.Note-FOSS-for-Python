# Glossary

This glossary uses Microsoft OneNote terminology; many names appear in both spec documents and in the reference implementation.

## File/container level

- **OneStore**: the container format used by `.one` and `.onetoc2`. It contains chunks and linked lists of *file nodes*.
- **STP / CB**: `stp` is a file offset (stream position), `cb` is a byte count (chunk length). Many references are encoded as `(stp, cb)`.
- **FCR (File Chunk Reference)**: a reference to a chunk of bytes in the file, typically `(stp, cb)` with sentinel values for nil/zero.
- **Hashed Chunk List**: optional structure for MD5 validation of some chunks.
- **FileDataStore**: a OneStore substructure that stores raw binary blobs (images/attachments).

## File node level

- **FileNodeList**: a logical list stored as a chain of *FileNodeListFragments*.
- **FileNodeListFragment**: a fragment containing a sequence of file nodes and a `nextFragment` reference.
- **FileNode**: a typed record identified by `FileNodeID` and a small header, optionally referencing other chunks.
- **Typed FileNode**: parsed/decoded representation of a FileNode for a specific `FileNodeID`.

## Object spaces and revisions

- **Object Space**: a logical namespace of objects inside OneStore.
- **Revision**: a versioned view of object space content; revisions can depend on earlier revisions.
- **Revision Manifest**: a file-node sequence that describes a revision boundary and lists object groups, GID tables, and roots.
- **Object Group List**: references to lists of object declarations/changes.

## IDs and object model

- **CompactID**: a compact reference (often 32-bit) that must be resolved using the Global ID Table.
- **ExtendedGUID**: an expanded, globally unique ID (GUID + additional info) used as stable object keys.
- **Property Set**: a set of typed properties describing an entity/object.
- **JCID**: “Jet Class ID” / class identifier used to tag object types.

## Public API layer

- **DOM**: Document Object Model used by the public API: Document/Page/Outline/RichText/Image/AttachedFile/Table/NoteTag etc.
- **Saving/Export**: converting DOM to PDF/images/text.
