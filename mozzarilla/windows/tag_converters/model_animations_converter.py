#!/usr/bin/env python3
#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

try:
    from .converter_base import ConverterBase
except (ImportError, SystemError):
    from converter_base import ConverterBase

from pathlib import Path
import threadsafe_tkinter as tk

from traceback import format_exc

from reclaimer.hek.defs.antr import antr_def
from reclaimer.os_hek.defs.magy import magy_def

window_base_class = tk.Toplevel
if __name__ == "__main__":
    window_base_class = tk.Tk


def magy_to_antr(magy_path):
    magy_tag = magy_def.build(filepath=magy_path)
    antr_tag = antr_def.build()
    antr_tag.filepath = Path(magy_path).with_suffix(".model_animations")

    magy_attrs = magy_tag.data.tagdata
    antr_attrs = antr_tag.data.tagdata

    antr_attrs.objects.STEPTREE[:] = magy_attrs.objects.STEPTREE
    antr_attrs.units.STEPTREE[:] = magy_attrs.units.STEPTREE
    antr_attrs.weapons.STEPTREE[:] = magy_attrs.weapons.STEPTREE
    antr_attrs.vehicles.STEPTREE[:] = magy_attrs.vehicles.STEPTREE
    antr_attrs.devices.STEPTREE[:] = magy_attrs.devices.STEPTREE
    antr_attrs.unit_damages.STEPTREE[:] = magy_attrs.unit_damages.STEPTREE
    antr_attrs.fp_animations.STEPTREE[:] = magy_attrs.fp_animations.STEPTREE
    antr_attrs.sound_references.STEPTREE[:] = magy_attrs.sound_references.STEPTREE
    antr_attrs.nodes.STEPTREE[:] = magy_attrs.nodes.STEPTREE
    antr_attrs.animations.STEPTREE[:] = magy_attrs.animations.STEPTREE

    antr_attrs.limp_body_node_radius = magy_attrs.limp_body_node_radius
    antr_attrs.flags.data = magy_attrs.flags.data

    antr_tag.calc_internal_data()

    return antr_tag


class ModelAnimationsConverter(ConverterBase, window_base_class):
    src_ext = "model_animations_yelo"
    dst_ext = "model_animations"

    def __init__(self, app_root, *args, **kwargs):
        if isinstance(self, tk.Toplevel):
            kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)

        window_base_class.__init__(self, app_root, *args, **kwargs)
        ConverterBase.__init__(self, app_root, *args, **kwargs)
        self.setup_window(*args, **kwargs)

    def setup_window(self, *args, **kwargs):
        ConverterBase.setup_window(self, *args, **kwargs)
        self.pack_widgets()
        self.apply_style()

    def destroy(self):
        ConverterBase.destroy(self)
        window_base_class.destroy(self)

    def convert(self, tag_path):
        return magy_to_antr(tag_path)


if __name__ == "__main__":
    try:
        ModelAnimationsConverter(None).mainloop()
        raise SystemExit(0)
    except Exception:
        print(format_exc())
        input()
