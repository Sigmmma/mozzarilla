#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

from supyr_struct.defs.tag_def import TagDef
from supyr_struct.field_types import *

__all__ = (
    "get", "guerilla_workspace_def",
    )


def reflexives_size(parent=None, new_value=None, **kwargs):
    if parent is None:
        raise KeyError()
    if new_value is None:
        return parent.reflexive_count * 4

    parent.reflexive_count = new_value // 4


def has_next_tag(rawdata=None, **kwargs):
    '''Returns whether or not there is another block in the stream.'''
    try:
        offset = kwargs.get('offset')
        try:
            offset += kwargs.get('root_offset')
        except Exception:
            pass
        return rawdata.peek(4, offset) == b'\x01\x00\x00\x00'
    except AttributeError:
        return False

reflexive_counts = {
    "actv": 1, "tagc": 1, "mgs2": 1, "lens": 1,
    "elec": 2,
    "bitm": 3, "sky ": 3, "phys": 3,
    "obje": 6, "eqip": 6, "garb": 6, "scen": 6,
    "plac": 6, "mach": 6, "lifi": 6, "ctrl": 6,
    "proj": 7,
    "unit": 8,
    "mode": 12, "mod2": 12,
    "antr": 22,
    "coll": 15, "bipd": 15,
    "matg": 19,
    "sbsp": 53,
    "scnr": 61,
    # This is incomplete
    }

window_header = Struct("window_header",
    UInt32("struct_size", DEFAULT=44),
    UInt32("unknown1"),
    UInt32("unknown2", DEFAULT=1),
    # These raw bytes seem to be some sort of window coordinates, but idc
    BytesRaw("unknown3", DEFAULT=b'\xff'*16, SIZE=16),

    QStruct("t_l_corner", SInt32("x"), SInt32("y"), ORIENT="h"),
    QStruct("b_r_corner", SInt32("x"), SInt32("y"), ORIENT="h"),
    SIZE=44
    )

open_halo_tag = Container("open_tag",
    UInt32("is_valid_tag", DEFAULT=1),
    window_header,
    UInt8("filepath_len"),
    StrRawAscii("filepath", SIZE='.filepath_len'),
    Pad(8),
    UInt16("reflexive_count"),

    # this seems to contain the indices that the
    # reflexives were on when the tag was last open
    SInt32Array("reflexive_indices", SIZE=reflexives_size),
    )

guerilla_workspace_def = TagDef("guerilla_workspace",
    window_header,
    WhileArray("tags",
        SUB_STRUCT=open_halo_tag,
        CASE=has_next_tag
        ),
    UInt32("eof_marker"),

    ENDIAN='<', ext=".cfg"
    )


def get(): return guerilla_workspace_def
