#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#
from traceback import format_exc

from binilla.widgets.field_widgets.enum_frame import DynamicEnumFrame
from binilla.constants import DYN_NAME_PATH, DYN_I

__all__ = ("DynamicEnumFrame", )


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
                trimmed_name = name.replace('/', '\\').split('\\')[-1]
                if trimmed_name.strip():
                    name = trimmed_name

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
