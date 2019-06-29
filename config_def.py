from binilla.config_def import *
from binilla.constants import *
from supyr_struct.field_types import *
from supyr_struct.defs.tag_def import TagDef

mozz_color_names = color_names + ("active_tags_directory", )

mozz_colors = Array("colors",
    SUB_STRUCT=QStruct("color",
        UInt8('r'), UInt8('g'), UInt8('b'),
        ORIENT='h', WIDGET=ColorPickerFrame
        ),
    SIZE=".array_counts.color_count",
    MAX=len(mozz_color_names), MIN=len(mozz_color_names),
    NAME_MAP=mozz_color_names,
    )

mozz_flag_tooltips = (
    "Whether to show the hierarchy window in the main window.",
    "Whether to show the console output in the main window.",
    ("Whether to recalculate certain hidden values when saving.\n" +
     "For all intents and purposes, this should stay on unless\n" +
     "you are doing some form of experimenting or debugging."),
    "When reading scripts, extract names for encounters,\n"
    "command lists, scripts, cutscene titles/camera points/flags,\n"
    "trigger volumes, recorded animations, ai conversations,\n"
    "object names, device groups, and player starting profiles\n"
    "from the scenarios reflexives, rather than script strings.",
    "Whether or not to show the full tags directory in the tag window title."
    )

new_method_enums = (
    # start at 1024 to make sure to provide space for any future binilla methods
    {GUI_NAME:"", NAME:"mozz_divider1", VALUE:1024},
    {GUI_NAME:"MOZZARILLA METHODS", NAME:"mozz_divider2"},
    {GUI_NAME:"choose tags directory", NAME:"set_tags_dir"},
    {GUI_NAME:"switch tags directory", NAME:"switch_tags_dir"},
    {GUI_NAME:"add tags directory",    NAME:"add_tags_dir"},
    {GUI_NAME:"remove tags directory", NAME:"remove_tags_dir"},
    # space for a total of 64 enums here

    {GUI_NAME:"", NAME:"mozz_divider3", VALUE:1024 + 64},
    {GUI_NAME:"open dependency scanner", NAME:"show_dependency_viewer"},
    {GUI_NAME:"open tag scanner", NAME:"show_tag_scanner"},
    {GUI_NAME:"open search and replace", NAME:"show_search_and_replace"},
    {GUI_NAME:"make bitmap(s) from dds", NAME:"bitmap_from_dds"},
    {GUI_NAME:"make bitmap from bitmap source", NAME:"bitmap_from_bitmap_source"},
    {GUI_NAME:"launch pool", NAME:"create_hek_pool_window"},
    {GUI_NAME:"open tag data extractor", NAME:"show_data_extraction_window"},
    {GUI_NAME:"make physics from jms", NAME:"physics_from_jms"},
    {GUI_NAME:"make gbxmodel from jms", NAME:"model_from_jms"},
    {GUI_NAME:"make hud_message_text from hmt", NAME:"hud_message_text_from_hmt"},
    {GUI_NAME:"make bitmap from dds", NAME:"bitmap_from_multiple_dds"},
    {GUI_NAME:"make strings from txt", NAME:"strings_from_txt"},
    {GUI_NAME:"open bitmap source extractor", NAME:"show_bitmap_source_extractor"},
    {GUI_NAME:"open model animations compiler", NAME:"show_animations_compiler_window"},
    {GUI_NAME:"open model animations compression", NAME:"show_animations_compression_window"},
    # space for another 64 enums here

    {GUI_NAME:"", NAME:"mozz_divider4", VALUE:1024 + 64*2},
    {GUI_NAME:"open model converter", NAME:"show_model_converter"},
    {GUI_NAME:"open gbxmodel converter", NAME:"show_gbxmodel_converter"},
    {GUI_NAME:"open collision converter", NAME:"show_collision_converter"},
    {GUI_NAME:"open sbsp converter", NAME:"show_sbsp_converter"},
    {GUI_NAME:"open chicago shader converter", NAME:"show_chicago_shader_converter"},
    {GUI_NAME:"open animations converter", NAME:"show_animations_converter"},
    {GUI_NAME:"open object converter", NAME:"show_object_converter"},
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

open_mozz_tag = Container("open_tag",
    Struct("header",
        UInt16("width"),
        UInt16("height"),
        SInt16("offset_x"),
        SInt16("offset_y"),
        Bool32("flags",
            "minimized",
            ),

        # UPDATE THIS PADDING WHEN ADDING STUFF ABOVE IT
        Pad(48 - 2*4 - 4*1),

        UInt16("def_id_len"),
        UInt16("path_len"),
        UInt16("tags_dir_index"),
        UInt16("handler_index"),
        SIZE=64
        ),

    StrUtf8("def_id", SIZE=".header.def_id_len"),
    StrUtf8("path", SIZE=".header.path_len"),
    )

mozzarilla = Container("mozzarilla",
    Bool16("flags",
        {NAME: "show_hierarchy_window", TOOLTIP: mozz_flag_tooltips[0]},
        {NAME: "show_console_window", TOOLTIP: mozz_flag_tooltips[1]},
        {NAME: "calc_internal_data", TOOLTIP: mozz_flag_tooltips[2]},
        {NAME: "use_scenario_names_in_scripts", TOOLTIP: mozz_flag_tooltips[3]},
        {NAME: "show_full_tags_directory", TOOLTIP: mozz_flag_tooltips[4]},
        DEFAULT=sum([1<<i for i in (0, 1, 2)])
        ),
    UEnum16("selected_handler",
        "halo_1",
        "halo_1_os_v3",
        "halo_1_os_v4",
        "halo_1_misc",
        "stubbs",
        "halo_3",
        EDITABLE=False, VISIBLE=False
        ),
    UInt16("last_tags_dir",  VISIBLE=False, EDITABLE=False),
    UInt16("sash_position",  VISIBLE=False, EDITABLE=False),
    UInt32("last_tool_path", VISIBLE=False, EDITABLE=False),
    Pad(64 - 2*4 - 4*1),

    UInt16("tags_dirs_count",     VISIBLE=False, EDITABLE=False),
    UInt16("load_dirs_count",     VISIBLE=False, EDITABLE=False),
    UInt16("open_mozz_tag_count", VISIBLE=False, EDITABLE=False),
    Pad(64 - 2*3),

    Array("tags_dirs", SUB_STRUCT=filepath, SIZE=".tags_dirs_count",
        MIN=1,  VISIBLE=False),
    Array("load_dirs", SUB_STRUCT=filepath, SIZE=".load_dirs_count",
        NAME_MAP=("last_data_load_dir", "jms_load_dir", "bitmap_load_dir"),
        MIN=3, VISIBLE=False
        ),
    Array("open_mozz_tags",
        SUB_STRUCT=open_mozz_tag, SIZE=".open_mozz_tag_count", VISIBLE=False
        ),
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
    mozz_colors,
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


def get():
    return (config_def, guerilla_workspace_def)
