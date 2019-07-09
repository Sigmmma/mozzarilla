from binilla import editor_constants as b_e_c
from binilla.editor_constants import *
from binilla.widgets.binilla_widget import BinillaWidget
from binilla.widgets.font_config import FontConfig

from supyr_struct.defs.frozen_dict import FrozenDict

v2_mozz_color_names = v1_color_names + ("active_tags_directory", )
mozz_color_names = color_names + ("active_tags_directory", )
mozz_font_names = font_names + ("font_tag_preview", )

channel_name_map   = FrozenDict(a='alpha', r='red', g='green', b='blue')
channel_offset_map = FrozenDict(a=24,      r=16,    g=8,       b=0)

TITLE_WIDTH = b_e_c.TITLE_WIDTH = 28
DEF_STRING_ENTRY_WIDTH = b_e_c.TITLE_WIDTH = 30

if b_e_c.IS_WIN:
    FONT_TAG_PREVIEW_FONT_FAMILY = "System"
    FONT_TAG_PREVIEW_FONT_SIZE   = 12
else:
    FONT_TAG_PREVIEW_FONT_FAMILY = "Open Sans"
    FONT_TAG_PREVIEW_FONT_SIZE   = 12

FONT_TAG_PREVIEW_FONT_WEIGHT = "normal"
FONT_TAG_PREVIEW_FONT_SLANT  = "roman"

BinillaWidget.font_settings.update(
    font_tag_preview=FontConfig(
        family=FONT_TAG_PREVIEW_FONT_FAMILY,
        size=FONT_TAG_PREVIEW_FONT_SIZE,
        weight=FONT_TAG_PREVIEW_FONT_WEIGHT,
        slant=FONT_TAG_PREVIEW_FONT_SLANT,
        )
    )
del b_e_c
del FontConfig
