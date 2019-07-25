from traceback import format_exc

from binilla.widgets import field_widgets
from binilla.constants import DYN_NAME_PATH, DYN_I
from binilla.widgets.field_widgets.enum_frame import DynamicEnumFrame

__all__ = (
    "HaloScriptTextFrame", "HaloHudMessageTextFrame", "DependencyFrame",
    "FontCharacterDisplayFrame", "FontCharacterFrame", "HaloBitmapDisplayFrame",
    "HaloBitmapDisplayButton", "HaloBitmapTagFrame", "HaloBitmapDisplayBase",
    "Halo2BitmapDisplayButton", "Halo2BitmapTagFrame", "Halo3BitmapDisplayFrame",
    "Halo3BitmapDisplayButton", "Halo3BitmapTagFrame", "HaloColorEntry",
    "HaloUInt32ColorPickerFrame", "MeterImageDisplayFrame", "MeterImageFrame",
    "HaloRawdataFrame", "HaloScriptSourceFrame", "SoundSampleFrame",
    "ReflexiveFrame",
    ) + tuple(field_widgets.__all__)

from binilla.widgets.field_widgets import *

from mozzarilla.widgets.field_widgets.computed_text_frames import \
     HaloScriptTextFrame, HaloHudMessageTextFrame
from mozzarilla.widgets.field_widgets.dependency_frame import DependencyFrame
from mozzarilla.widgets.field_widgets.font_display_frame import \
     FontCharacterDisplayFrame, FontCharacterFrame
from mozzarilla.widgets.field_widgets.halo_1_bitmap_display import \
     HaloBitmapDisplayFrame, HaloBitmapDisplayButton, HaloBitmapTagFrame,\
     HaloBitmapDisplayBase
from mozzarilla.widgets.field_widgets.halo_2_bitmap_display import \
     Halo2BitmapDisplayButton, Halo2BitmapTagFrame
from mozzarilla.widgets.field_widgets.halo_3_bitmap_display import \
     Halo3BitmapDisplayFrame, Halo3BitmapDisplayButton, Halo3BitmapTagFrame
from mozzarilla.widgets.field_widgets.halo_color_picker_frame import \
     HaloUInt32ColorPickerFrame, HaloColorEntry
from mozzarilla.widgets.field_widgets.meter_display_frame import \
     MeterImageDisplayFrame, MeterImageFrame
from mozzarilla.widgets.field_widgets.rawdata_frames import HaloRawdataFrame,\
     HaloScriptSourceFrame, SoundSampleFrame
from mozzarilla.widgets.field_widgets.reflexive_frame import ReflexiveFrame


# replace the DynamicEnumFrame with one that has a specialized option generator
def halo_dynamic_enum_generate_options(self, opt_index=None):
    desc = self.desc
    options = {0: "-1. NONE"}

    dyn_name_path = desc.get(DYN_NAME_PATH)
    if self.node is None:
        if opt_index is None:
            return options
        return None
    elif not dyn_name_path:
        print("Missing DYN_NAME_PATH path in dynamic enumerator.")
        print(self.parent.get_root().def_id, self.name)
        if opt_index is None:
            return options
        return None

    try:
        p_out, p_in = dyn_name_path.split(DYN_I)

        # We are ALWAYS going to go to the parent, so we need to slice
        if p_out.startswith('..'): p_out = p_out.split('.', 1)[-1]
        array = self.parent.get_neighbor(p_out)

        options_to_generate = range(len(array))
        if opt_index is not None:
            options_to_generate = (
                (opt_index - 1, ) if opt_index - 1 in
                options_to_generate else ())

        for i in options_to_generate:
            name = array[i].get_neighbor(p_in)
            if isinstance(name, list):
                name = repr(name).strip("[").strip("]")
            else:
                name = str(name)

            if p_in.endswith('.filepath'):
                # if it is a dependency filepath
                options[i + 1] = '%s. %s' % (
                    i, name.replace('/', '\\').split('\\')[-1])
            options[i + 1] = '%s. %s' % (i, name)
        last_option_index = len(array)
    except Exception:
        print(format_exc())
        last_option_index = 0

    if opt_index is None:
        self.option_cache = options
        self.options_sane = True
        if self.sel_menu is not None:
            self.sel_menu.options_menu_sane = False
            self.sel_menu.max_index = last_option_index
        return options
    return options.get(opt_index, None)

DynamicEnumFrame.generate_options = halo_dynamic_enum_generate_options
