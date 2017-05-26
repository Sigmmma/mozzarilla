from binilla.tag_window import *
from supyr_struct.defs.constants import *

class HaloTagWindow(TagWindow):
    save_as_60 = False

    def __init__(self, master, tag=None, *args, **kwargs):
        app_root   = kwargs.get('app_root', master)
        is_new_tag = kwargs.get('is_new_tag', self.is_new_tag)
        try:
            # if the tag is flagged as 60fps, display it as such
            self.save_as_60 = tag.data.blam_header.flags.fps_60

            # if the tag is new and we are making 60fps tags, display it as such
            self.save_as_60 |= (app_root.config_file.data.\
                                mozzarilla.flags.fps_60) and is_new_tag
        except AttributeError:
            pass
        TagWindow.__init__(self, master, *args, tag=tag, **kwargs)

    def save(self, **kwargs):
        '''Flushes any lingering changes in the widgets to the tag.'''
        flags = self.app_root.config_file.data.mozzarilla.flags
        tag = self.tag
        if hasattr(self.tag, 'calc_internal_data') and flags.calc_internal_data:
            tag.calc_internal_data()

        try:
            tag.data.blam_header.flags.edited_with_mozz = True
            #if flags.fps_60:
            #    tag.data.blam_header.flags.fps_60 = True
            #else:
            #    tag.data.blam_header.flags.fps_60 = False
            tag.data.blam_header.flags.fps_60 = self.save_as_60
        except Exception:
            pass

        TagWindow.save(self, **kwargs)
