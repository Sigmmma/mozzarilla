#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

from binilla.defs.config_def import method_enums, modifier_enums, depths,\
     hotkey_enums, array_counts, app_window, tag_windows, tag_printing,\
     filepath, open_tags, recent_tags, directory_paths, theme_name,\
     tag_window_hotkeys, padding, widths_and_heights, tag_backup
from binilla.defs.style_def import appearance, color, font
from binilla.constants import GUI_NAME, NAME, TOOLTIP, VALUE,\
     VISIBILITY_METADATA, VISIBILITY_HIDDEN
from binilla.widgets.field_widgets.array_frame import DynamicArrayFrame
from binilla.defs import config_tooltips as ttip

from supyr_struct.defs.tag_def import TagDef
from supyr_struct.field_types import *

from mozzarilla.editor_constants import mozz_color_names, mozz_font_names


__all__ = (
    "get", "config_def",
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
    # space for (64 - 6) more enums here

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
    {GUI_NAME:"open sound compiler", NAME:"show_sound_compiler_window"},
    # space for (64 - 17) more enums here

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

mozz_colors = Array("colors",
    SUB_STRUCT=color, SIZE="array_counts.color_count",
    MAX=len(mozz_color_names), MIN=len(mozz_color_names),
    NAME_MAP=mozz_color_names,
    GUI_NAME="Colors"
    )

mozz_fonts = Array("fonts",
    SUB_STRUCT=font, SIZE="array_counts.font_count",
    MAX=len(mozz_font_names), MIN=len(mozz_font_names),
    NAME_MAP=mozz_font_names,
    GUI_NAME="Fonts"
    )

mozz_hotkey = Struct("hotkey",
    BitStruct("combo",
        UBitEnum("modifier", GUI_NAME="", *modifier_enums, SIZE=4),
        UBitEnum("key", GUI_NAME="and", *hotkey_enums, SIZE=28),
        SIZE=4, ORIENT='h', TOOLTIP=ttip.hotkey_combo
        ),
    UEnum32("method", *method_enums, TOOLTIP=ttip.hotkey_method)
    )

mozz_hotkeys = Array(
    "hotkeys", SUB_STRUCT=mozz_hotkey, DYN_NAME_PATH='.method.enum_name',
    SIZE="array_counts.hotkey_count", WIDGET=DynamicArrayFrame,
    GUI_NAME="Main window hotkeys"
    )

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
        EDITABLE=False, VISIBLE=VISIBILITY_METADATA
        ),
    UInt16("last_tags_dir",  VISIBLE=VISIBILITY_METADATA, EDITABLE=False),
    UInt16("sash_position",  VISIBLE=VISIBILITY_METADATA, EDITABLE=False),
    UInt32("last_tool_path", VISIBLE=VISIBILITY_METADATA, EDITABLE=False),
    Pad(64 - 2*4 - 4*1),

    UInt16("tags_dirs_count",     VISIBLE=VISIBILITY_METADATA, EDITABLE=False),
    UInt16("load_dirs_count",     VISIBLE=VISIBILITY_METADATA, EDITABLE=False),
    UInt16("open_mozz_tag_count", VISIBLE=VISIBILITY_METADATA, EDITABLE=False),
    Pad(64 - 2*3),

    Array("tags_dirs", SUB_STRUCT=filepath, SIZE="mozzarilla.tags_dirs_count",
        MIN=1, VISIBLE=VISIBILITY_METADATA),
    Array("load_dirs", SUB_STRUCT=filepath, SIZE="mozzarilla.load_dirs_count",
        NAME_MAP=("last_data_load_dir", "jms_load_dir", "bitmap_load_dir"),
        MIN=3, VISIBLE=VISIBILITY_METADATA
        ),
    Array("open_mozz_tags",
        SUB_STRUCT=open_mozz_tag, SIZE="mozzarilla.open_mozz_tag_count", VISIBLE=VISIBILITY_HIDDEN
        ),
    COMMENT="\nThese are settings specific to Mozzarilla.",
    GUI_NAME="Mozzarilla"
    )

mozz_version_info = Struct("version_info",
    UEnum32("id", ('Mozz', 'zzoM'), VISIBLE=VISIBILITY_METADATA, DEFAULT='zzoM'),
    UInt32("version", DEFAULT=3, VISIBLE=VISIBILITY_METADATA, EDITABLE=False),
    Timestamp32("date_created", EDITABLE=False),
    Timestamp32("date_modified", EDITABLE=False),
    SIZE=16, VISIBLE=VISIBILITY_HIDDEN
    )

mozz_appearance = Container("appearance",
    theme_name,
    widths_and_heights,
    padding,
    depths,
    mozz_colors,
    mozz_fonts,
    GUI_NAME="Appearance", COMMENT=(
        "\nThese settings control how everything looks. Colors, fonts, etc."
        "\nThese settings are what get saved to/loaded from style files.")
    )

mozz_all_hotkeys = Container("all_hotkeys",
    mozz_hotkeys,
    tag_window_hotkeys,
    GUI_NAME="Hotkeys", COMMENT=(
        "\nThese hotkeys control what operations to bind to keystroke"
        "\ncombinations for the main window and the tag windows.")
    )

config_def = TagDef("mozzarilla_config",
    mozz_version_info,  # not visible
    array_counts,  # not visible
    app_window,
    tag_windows,
    tag_printing,
    tag_backup,
    open_tags,  # not visible
    recent_tags,  # not visible
    directory_paths,  # not visible
    mozz_appearance,
    mozz_all_hotkeys,

    mozzarilla,
    ENDIAN='<', ext=".cfg",
    )

mozz_config_version_def = TagDef(mozz_version_info)

def get(): return config_def
