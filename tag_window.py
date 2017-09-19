from binilla.tag_window import *
from supyr_struct.defs.constants import *

class HaloTagWindow(TagWindow):
    def __init__(self, master, tag=None, *args, **kwargs):
        app_root   = kwargs.get('app_root', master)
        is_new_tag = kwargs.get('is_new_tag', self.is_new_tag)
        TagWindow.__init__(self, master, *args, tag=tag, **kwargs)

    def save(self, **kwargs):
        '''Flushes any lingering changes in the widgets to the tag.'''
        flags = self.app_root.config_file.data.mozzarilla.flags
        tag = self.tag
        if hasattr(self.tag, 'calc_internal_data') and flags.calc_internal_data:
            tag.calc_internal_data()

        try:
            tag.data.blam_header.flags.edited_with_mozz = True
        except Exception:
            pass

        TagWindow.save(self, **kwargs)
