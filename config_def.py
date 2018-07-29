from binilla.config_def import *
from binilla.constants import *
from supyr_struct.field_types import *
from supyr_struct.defs.tag_def import TagDef

mozz_flag_tooltips = (
    "Whether to show the hierarchy window in the main window.",
    "Whether to show the console output in the main window.",
    ("Whether to recalculate certain hidden values when saving.\n" +
     "For all intents and purposes, this should stay on unless\n" +
     "you are doing some form of experimenting or debugging."),
    "",
    "Whether or not to show the full tags directory in the tag window title."
    )

new_method_enums = (
    {GUI_NAME:"", NAME:"mozz_divider1", VALUE:1024},
    {GUI_NAME:"MOZZARILLA METHODS", NAME:"mozz_divider2"},
    {GUI_NAME:"choose tags directory", NAME:"set_tags_dir"},
    {GUI_NAME:"switch tags directory", NAME:"switch_tags_dir"},
    {GUI_NAME:"add tags directory",    NAME:"add_tags_dir"},
    {GUI_NAME:"remove tags directory", NAME:"remove_tags_dir"},

    {GUI_NAME:"", NAME:"mozz_divider3", VALUE:1024 + 64},
    {GUI_NAME:"open dependency scanner", NAME:"show_dependency_viewer"},
    {GUI_NAME:"open tag scanner", NAME:"show_tag_scanner"},
    {GUI_NAME:"open search and replace", NAME:"show_search_and_replace"},
    {GUI_NAME:"make bitmap from dds", NAME:"bitmap_from_dds"},
    {GUI_NAME:"make bitmap from bitmap source", NAME:"bitmap_from_bitmap_source"},
    {GUI_NAME:"launch pool", NAME:"create_hek_pool_window"},
    {GUI_NAME:"open tag data extractor", NAME:"show_data_extraction_window"},
    )

method_enums += new_method_enums

hotkey = Struct("hotkey",
    BitStruct("combo",
        UBitEnum("modifier", GUI_NAME="", *modifier_enums, SIZE=4),
        UBitEnum("key", GUI_NAME="and", *hotkey_enums, SIZE=28),
        SIZE=4, ORIENT='h',
        ),
    UEnum32("method", *method_enums)
    )

config_header = Struct("header",
    LUEnum32("id", ('Mozz', 'zzoM'), VISIBLE=False, DEFAULT='zzoM'),
    INCLUDE=config_header
    )

hotkeys = Array(
    "hotkeys", SUB_STRUCT=hotkey, DYN_NAME_PATH='.method.enum_name',
    SIZE=".array_counts.hotkey_count", WIDGET=DynamicArrayFrame)

tag_window_hotkeys = Array(
    "tag_window_hotkeys", SUB_STRUCT=hotkey, DYN_NAME_PATH='.method.enum_name',
    SIZE=".array_counts.tag_window_hotkey_count", WIDGET=DynamicArrayFrame)

mozzarilla = Container("mozzarilla",
    Bool16("flags",
        {NAME: "show_hierarchy_window", TOOLTIP: mozz_flag_tooltips[0]},
        {NAME: "show_console_window", TOOLTIP: mozz_flag_tooltips[1]},
        {NAME: "calc_internal_data", TOOLTIP: mozz_flag_tooltips[2]},
        {NAME: "unused", VISIBLE: False},
        {NAME: "show full tags directory", TOOLTIP: mozz_flag_tooltips[4]},
        DEFAULT=sum([1<<i for i in (0, 1, 2)])
        ),
    UEnum16("selected_handler",
        "halo_1",
        "halo_1_os_v3",
        "halo_1_os_v4",
        "halo_1_misc",
        "stubbs",
        EDITABLE=False, VISIBLE=False
        ),
    UInt16("last_tags_dir",  VISIBLE=False, EDITABLE=False),
    UInt16("sash_position",  VISIBLE=False, EDITABLE=False),
    UInt32("last_tool_path", VISIBLE=False, EDITABLE=False),
    Pad(64 - 2*4 - 4*1),

    UInt16("tags_dirs_count",  VISIBLE=False, EDITABLE=False, MIN=1),
    Pad(64 - 2*1),

    Array("tags_dirs",  SUB_STRUCT=filepath, SIZE=".tags_dirs_count", MIN=1),
    COMMENT="\nThese are settings specific to Mozzarilla.\n"
    )

config_def = TagDef("mozzarilla_config",
    config_header,
    array_counts,
    app_window,
    widgets,
    open_tags,
    recent_tags,
    directory_paths,
    colors,
    hotkeys,
    tag_window_hotkeys,

    mozzarilla,
    ENDIAN='<', ext=".cfg",
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
    Pad(24),
    #UInt32("unknown1"),
    #UInt32("unknown2", DEFAULT=1),
    # These raw bytes seem to be some sort of window coordinates, but idc
    #BytesRaw("unknown3", DEFAULT=b'\xff'*16, SIZE=16),

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
