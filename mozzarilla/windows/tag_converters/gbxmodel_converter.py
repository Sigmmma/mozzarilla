#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

from traceback import format_exc
try:
    from . import model_converter
except (ImportError, SystemError):
    import model_converter


model_converter.window_base_class = model_converter.tk.Toplevel
if __name__ == "__main__":
    model_converter.window_base_class = model_converter.tk.Tk


class GbxmodelConverter(model_converter.ConverterBase,
                        model_converter.window_base_class):
    to_gbxmodel = False
    src_ext = "gbxmodel"
    dst_ext = "model"

    __init__ = model_converter.ModelConverter.__init__
    setup_window = model_converter.ModelConverter.setup_window
    apply_style = model_converter.ModelConverter.apply_style
    destroy = model_converter.ModelConverter.destroy
    convert = model_converter.ModelConverter.convert


if __name__ == "__main__":
    try:
        GbxmodelConverter(None).mainloop()
        raise SystemExit(0)
    except Exception:
        print(format_exc())
        input()
