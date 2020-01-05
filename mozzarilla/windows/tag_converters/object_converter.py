#!/usr/bin/env python3
#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

from pathlib import Path

try:
    from .converter_base import ConverterBase
except (ImportError, SystemError):
    from converter_base import ConverterBase
import threadsafe_tkinter as tk

from traceback import format_exc

from binilla.widgets.scroll_menu import ScrollMenu

from reclaimer.os_v4_hek.defs.obje import obje_def
from reclaimer.os_v4_hek.defs.bipd import bipd_def
from reclaimer.os_v4_hek.defs.vehi import vehi_def
from reclaimer.os_v4_hek.defs.weap import weap_def
from reclaimer.os_v4_hek.defs.eqip import eqip_def
from reclaimer.os_v4_hek.defs.garb import garb_def
from reclaimer.os_v4_hek.defs.proj import proj_def
from reclaimer.os_v4_hek.defs.scen import scen_def
from reclaimer.os_v4_hek.defs.mach import mach_def
from reclaimer.os_v4_hek.defs.ctrl import ctrl_def
from reclaimer.os_v4_hek.defs.lifi import lifi_def
from reclaimer.os_v4_hek.defs.plac import plac_def
from reclaimer.os_v4_hek.defs.ssce import ssce_def

window_base_class = tk.Toplevel
if __name__ == "__main__":
    window_base_class = tk.Tk


def get_obje_def(obje_type):
    if obje_type == "biped":
        return bipd_def
    elif obje_type == "vehicle":
        return vehi_def
    elif obje_type == "weapon":
        return weap_def
    elif obje_type == "equipment":
        return eqip_def
    elif obje_type == "garbage":
        return garb_def
    elif obje_type == "projectile":
        return proj_def
    elif obje_type == "scenery":
        return scen_def
    elif obje_type == "device_machine":
        return mach_def
    elif obje_type == "device_control":
        return ctrl_def
    elif obje_type == "device_light_fixture":
        return lifi_def
    elif obje_type == "placeholder":
        return plac_def
    elif obje_type == "sound_scenery":
        return ssce_def
    else:
        return obje_def


def obje_to_obje(obje_path, src_type, dst_type):
    src_def = get_obje_def(src_type)
    dst_def = get_obje_def(dst_type)
    if not(src_def and dst_def) or src_def is dst_def:
        return

    src_tag = src_def.build(filepath=obje_path)
    dst_tag = dst_def.build()
    dst_tag.filepath = Path(obje_path).with_suffix("." + dst_type)

    src_tagdata = src_tag.data.tagdata
    dst_tagdata = dst_tag.data.tagdata

    dst_tagdata.obje_attrs = src_tagdata.obje_attrs

    if (hasattr(dst_tagdata, "devi_attrs") and
        hasattr(src_tagdata, "devi_attrs")):
        dst_tagdata.devi_attrs = src_tagdata.devi_attrs

    if (hasattr(dst_tagdata, "unit_attrs") and
        hasattr(src_tagdata, "unit_attrs")):
        dst_tagdata.unit_attrs = src_tagdata.unit_attrs

    if (hasattr(dst_tagdata, "item_attrs") and
        hasattr(src_tagdata, "item_attrs")):
        dst_tagdata.item_attrs = src_tagdata.item_attrs

    dst_tag.calc_internal_data()

    return dst_tag


class ObjectConverter(ConverterBase, window_base_class):
    object_types = (
        "vehicle", "biped", "weapon", "equipment", "garbage",
        "device_machine", "device_control", "device_light_fixture",
        "projectile", "sound_scenery", "scenery",
        )

    def __init__(self, app_root, *args, **kwargs):
        if isinstance(self, tk.Toplevel):
            kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)

        window_base_class.__init__(self, app_root, *args, **kwargs)
        ConverterBase.__init__(self, app_root, *args, **kwargs)
        kwargs["title"] = "Object to object converter"
        self.setup_window(*args, **kwargs)

    @property
    def src_ext(self):
        try:
            return self.object_types[self.src_menu.sel_index]
        except Exception:
            return ""

    @property
    def dst_ext(self):
        try:
            return self.object_types[self.dst_menu.sel_index]
        except Exception:
            return ""

    @property
    def src_exts(self): return self.object_types

    def setup_window(self, *args, **kwargs):
        ConverterBase.setup_window(self, *args, **kwargs)

        self.settings_frame = tk.LabelFrame(self, text="Conversion settings")
        self.from_label = tk.Label(self.settings_frame, text="from")
        self.src_menu = ScrollMenu(
            self.settings_frame, options=self.object_types, menu_width=20,
            sel_index=0,
            )
        self.to_label = tk.Label(self.settings_frame, text="to")
        self.dst_menu = ScrollMenu(
            self.settings_frame, options=self.object_types, menu_width=20,
            sel_index=10,
            )

        self.pack_widgets()
        self.apply_style()

    def pack_widgets(self):
        ConverterBase.pack_widgets(self)

        # pack everything
        self.settings_frame.pack(fill='both', anchor='nw')
        self.from_label.pack(padx=(10, 0), pady=10, anchor='w', side='left')
        self.src_menu.pack(padx=(10, 0), pady=10, fill='x',
                           anchor='w', side='left')
        self.to_label.pack(padx=(10, 0), pady=10, anchor='w', side='left')
        self.dst_menu.pack(padx=(10, 0), pady=10, fill='x',
                           anchor='w', side='left')

    def destroy(self):
        ConverterBase.destroy(self)
        window_base_class.destroy(self)

    def tag_path_browse(self):
        curr_tag_path = self.tag_path.get()
        ConverterBase.tag_path_browse(self)
        if curr_tag_path == self.tag_path.get(): return

        try:
            ext = Path(curr_tag_path).suffix[1:].lower()
            self.src_menu.sel_index = self.object_types.index(ext)
        except Exception:
            pass

    def convert(self, tag_path):
        return obje_to_obje(tag_path, self.src_ext, self.dst_ext)


if __name__ == "__main__":
    try:
        ObjectConverter(None).mainloop()
        raise SystemExit(0)
    except Exception:
        print(format_exc())
        input()
