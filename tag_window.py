from binilla.tag_window import *
from supyr_struct.defs.constants import *

class HaloTagWindow(TagWindow):

    def __init__(self, master, tag=None, *args, **kwargs):
        try:
            tag.tags_dir = master.tags_dir
            if not tag.tags_dir.endswith(PATHDIV):
                tag.tags_dir += PATHDIV
            tag.rel_filepath = sanitize_path(tag.filepath)
            tag.rel_filepath = tag.rel_filepath.split(tag.tags_dir)[-1]
        except Exception:
            print(format_exc())

        TagWindow.__init__(self, master, tag, *args, **kwargs)

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
