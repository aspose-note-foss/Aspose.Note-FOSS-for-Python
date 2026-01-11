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
JCID_NUMBER_LIST_NODE_INDEX = 0x0012
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

# Lists
PID_NUMBER_LIST_FORMAT = 0x1C001C1A  # NumberListFormat -> WzInAtom
PID_LIST_NODES = 0x24001C26  # ListNodes -> OID array
PID_LIST_RESTART = 0x14001CB7  # ListRestart -> i32
PID_LIST_MSAA_INDEX = 0x10001D0E  # ListMSAAIndex -> u16

# Text formatting / paragraph styles
PID_TEXT_RUN_INDEX = 0x1C001E12  # TextRunIndex (ArrayOfUINT32s encoded as bytes)
PID_TEXT_RUN_FORMATTING = 0x24001E13  # TextRunFormatting (OID array)

PID_BOLD = 0x08001C04
PID_ITALIC = 0x08001C05
PID_UNDERLINE = 0x08001C06
PID_STRIKETHROUGH = 0x08001C07
PID_SUPERSCRIPT = 0x08001C08
PID_SUBSCRIPT = 0x08001C09
PID_FONT = 0x1C001C0A  # WzInAtom
PID_FONT_SIZE = 0x10001C0B  # FontSize (u16 half-points)
PID_FONT_COLOR = 0x14001C0C  # COLORREF (u32)
PID_HIGHLIGHT = 0x14001C0D  # Highlight COLORREF (u32)

PID_HYPERLINK = 0x08001E14
PID_WZ_HYPERLINK_URL = 0x1C001E20  # WzHyperlinkUrl (WzInAtom)

# Embedded objects inside RichText runs
PID_TEXT_RUN_DATA_OBJECT = 0x24003458  # TextRunDataObject (OID array)

# Alternate text storage observed in SimpleTable.one
PID_TEXT_EXTENDED_ASCII = 0x1C003498  # TextExtendedAscii (non-null-terminated bytes)

# Note tags
PID_NOTE_TAG_SHAPE = 0x10003464
PID_NOTE_TAG_HIGHLIGHT_COLOR = 0x14003465
PID_NOTE_TAG_TEXT_COLOR = 0x14003466
PID_NOTE_TAG_LABEL = 0x1C003468  # WzInAtom
PID_NOTE_TAG_CREATED = 0x1400346E
PID_NOTE_TAG_COMPLETED = 0x1400346F
PID_NOTE_TAG_DEFINITION_OID = 0x20003488

# NoteTagStates shows up as prtArrayOfPropertyValues in the decoder, which encodes a different
# high-byte than the spec's base value (observed: 0x40003489). Accept both.
PID_NOTE_TAG_STATES = 0x40003489
PID_NOTE_TAG_STATES_ALT = 0x04003489

# Misc useful properties (not all used in v1)
PID_AUTHOR = 0x1C001D75
PID_CREATION_TIMESTAMP = 0x14001D09
PID_LAST_MODIFIED_TIMESTAMP = 0x18001D77
