#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

from mozzarilla import editor_constants as e_c
from binilla.windows.tag_window import TagWindow, ConfigWindow
from supyr_struct.util import is_path_empty

__all__ = ("HaloTagWindow", "HaloConfigWindow", )


class HaloTagWindow(TagWindow):
    def __init__(self, master, tag=None, *args, **kwargs):
        app_root   = kwargs.get('app_root', master)
        is_new_tag = kwargs.get('is_new_tag', self.is_new_tag)
        TagWindow.__init__(self, master, *args, tag=tag, **kwargs)

    def post_toplevel_init(self):
        if not is_path_empty(e_c.MOZZ_ICON_PATH):
            self.iconbitmap_filepath = e_c.MOZZ_ICON_PATH

        TagWindow.post_toplevel_init(self)

    def save(self, **kwargs):
        '''Flushes any lingering changes in the widgets to the tag.'''
        flags = self.app_root.config_file.data.mozzarilla.flags
        tag = self.tag
        kwargs.setdefault("calc_pointers", False)
        if hasattr(self.tag, 'calc_internal_data') and flags.calc_internal_data:
            tag.calc_internal_data()

        try:
            tag.data.blam_header.flags.edited_with_mozz = True
        except Exception:
            pass

        TagWindow.save(self, **kwargs)

    @property
    def use_scenario_names_for_script_names(self):
        try:
            return bool(self.app_root.config_file.data.mozzarilla.\
                        flags.use_scenario_names_in_scripts)
        except Exception:
            return False


class HaloConfigWindow(ConfigWindow):

    def post_toplevel_init(self):
        if not is_path_empty(e_c.MOZZ_ICON_PATH):
            self.iconbitmap_filepath = e_c.MOZZ_ICON_PATH

        ConfigWindow.post_toplevel_init(self)
