"""Minimal MS-ONE spec identifiers needed for v1 entity extraction.

These values are sourced from ms-one_spec_structure.txt (generated from [MS-ONE]).

We intentionally keep this minimal and avoid scattering magic hex constants.
"""

from __future__ import annotations

# JCID indices (JCID.raw & 0xFFFF)
JCID_SECTION_NODE_INDEX = 0x0007
JCID_PAGE_SERIES_NODE_INDEX = 0x0008
JCID_PAGE_NODE_INDEX = 0x000B
JCID_OUTLINE_NODE_INDEX = 0x000C
JCID_OUTLINE_ELEMENT_NODE_INDEX = 0x000D
JCID_RICH_TEXT_OE_NODE_INDEX = 0x000E
JCID_IMAGE_NODE_INDEX = 0x0011
JCID_TABLE_NODE_INDEX = 0x0022
JCID_TABLE_ROW_NODE_INDEX = 0x0023
JCID_TABLE_CELL_NODE_INDEX = 0x0024
JCID_TITLE_NODE_INDEX = 0x002C
JCID_PAGE_METADATA_INDEX = 0x0030
JCID_SECTION_METADATA_INDEX = 0x0031
JCID_EMBEDDED_FILE_NODE_INDEX = 0x0035
JCID_PAGE_MANIFEST_NODE_INDEX = 0x0037

# PropertyID.raw values (u32) (PropertyID.type is encoded in upper bits)
PID_ELEMENT_CHILD_NODES = 0x24001C20  # OID array
PID_CONTENT_CHILD_NODES = 0x24001C1F  # OID array

# PageSeries properties
PID_CHILD_GRAPH_SPACE_ELEMENT_NODES = 0x2C001D63  # ObjectSpaceID array (CompactID array)

# Observed in SimpleTable.one: PageSeries uses a different property for its page list.
PID_PAGE_SERIES_CHILD_NODES = 0x24003442

# Alias with spec name for clarity.
PID_META_DATA_OBJECTS_ABOVE_GRAPH_SPACE = PID_PAGE_SERIES_CHILD_NODES
PID_SECTION_DISPLAY_NAME = 0x1C00349B  # prtFourBytesOfLengthFollowedByData -> WzInAtom

PID_CACHED_TITLE_STRING = 0x1C001CF3  # WzInAtom
PID_CACHED_TITLE_STRING_FROM_PAGE = 0x1C001D3C  # WzInAtom

PID_RICH_EDIT_TEXT_UNICODE = 0x1C001C22  # RichEditTextUnicode -> WzInAtom

# Alternate text storage observed in SimpleTable.one
PID_TEXT_EXTENDED_ASCII = 0x1C003498  # TextExtendedAscii (non-null-terminated bytes)

# Misc useful properties (not all used in v1)
PID_AUTHOR = 0x1C001D75
PID_CREATION_TIMESTAMP = 0x14001D09
PID_LAST_MODIFIED_TIMESTAMP = 0x18001D77
