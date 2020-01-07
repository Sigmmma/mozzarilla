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

from reclaimer.hek.defs.schi import schi_def
from reclaimer.hek.defs.scex import scex_def

window_base_class = tk.Toplevel
if __name__ == "__main__":
    window_base_class = tk.Tk


def scex_to_schi(scex_path):
    scex_tag = scex_def.build(filepath=scex_path)
    schi_tag = schi_def.build()
    schi_tag.filepath = Path(scex_path).with_suffix(".shader_transparent_chicago")

    scex_attrs = scex_tag.data.tagdata.scex_attrs
    schi_attrs = schi_tag.data.tagdata.schi_attrs

    schi_attrs.lens_flare_spacing = scex_attrs.lens_flare_spacing
    schi_attrs.extra_flags.data = scex_attrs.extra_flags.data

    schi_attrs.chicago_shader.parse(initdata=scex_attrs.chicago_shader_extended)
    schi_attrs.lens_flare.parse(initdata=scex_attrs.lens_flare)

    schi_attrs.extra_layers.STEPTREE[:] = scex_attrs.extra_layers.STEPTREE
    schi_attrs.maps.STEPTREE[:] = scex_attrs.four_stage_maps.STEPTREE

    schi_tag.calc_internal_data()

    return schi_tag


class ChicagoShaderConverter(ConverterBase, window_base_class):
    src_ext = "shader_transparent_chicago_extended"
    dst_ext = "shader_transparent_chicago"

    def __init__(self, app_root, *args, **kwargs):
        if isinstance(self, tk.Toplevel):
            kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)

        window_base_class.__init__(self, app_root, *args, **kwargs)
        ConverterBase.__init__(self, app_root, *args, **kwargs)
        kwargs["title"] = "Chicago_extended to chicago converter"
        self.setup_window(*args, **kwargs)

    def setup_window(self, *args, **kwargs):
        ConverterBase.setup_window(self, *args, **kwargs)
        self.pack_widgets()
        self.apply_style()

    def destroy(self):
        ConverterBase.destroy(self)
        window_base_class.destroy(self)

    def convert(self, tag_path):
        return scex_to_schi(tag_path)


if __name__ == "__main__":
    try:
        ChicagoShaderConverter(None).mainloop()
        raise SystemExit(0)
    except Exception:
        print(format_exc())
        input()
