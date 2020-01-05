#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

from binilla.defs.v1_config_def import v1_general, v1_array_counts,\
     tag_window_hotkeys, padding, directory_paths, v1_app_window, \
     recent_tags, open_tags
from binilla.defs.v1_style_def import v1_widths_and_heights,\
     color, depths

from supyr_struct.defs.tag_def import TagDef
from supyr_struct.field_types import *

from mozzarilla.defs.config_def import mozz_hotkeys, mozzarilla
from mozzarilla.editor_constants import v2_mozz_color_names


__all__ = (
    "get", "v2_config_def",
    )

mozz_v2_version_info = Struct("version_info",
    UEnum32("id", ('Mozz', 'zzoM'), DEFAULT='zzoM'),
    UInt32("version", DEFAULT=2),
    )

v2_mozz_colors = Array("colors",
    SUB_STRUCT=color, SIZE="array_counts.color_count",
    MAX=len(v2_mozz_color_names), MIN=len(v2_mozz_color_names),
    NAME_MAP=v2_mozz_color_names,
    GUI_NAME="Colors"
    )

v2_config_def = TagDef("mozzarilla_v2_config",
    mozz_v2_version_info,
    v1_general,
    v1_array_counts,
    v1_app_window,
    v1_widths_and_heights,
    padding,
    depths,
    open_tags,
    recent_tags,
    directory_paths,
    v2_mozz_colors,
    mozz_hotkeys,
    tag_window_hotkeys,

    mozzarilla,
    ENDIAN='<', ext=".cfg",
    )


def get():
    return v2_config_def
