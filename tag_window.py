from binilla.tag_window import *
from supyr_struct.defs.constants import *

class HaloTagWindow(TagWindow):

    def save(self, **kwargs):
        '''Flushes any lingering changes in the widgets to the tag.'''
        flags = self.app_root.config_file.data.mozzarilla.flags
        tag = self.tag
        if hasattr(self.tag, 'calc_internal_data') and flags.calc_internal_data:
            tag.calc_internal_data()

        try:
            tag.data.blam_header.flags.edited_with_mozz = True
            if flags.fps_60:
                tag.data.blam_header.flags.fps_60 = True
            else:
                tag.data.blam_header.flags.fps_60 = False
        except Exception:
            pass

        TagWindow.save(self, **kwargs)
