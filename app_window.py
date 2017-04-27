import os
import tkinter as tk
import zipfile
import mmap

from os.path import dirname, exists, isdir, splitext, realpath
from time import time
from threading import Thread
from traceback import format_exc

from reclaimer.constants import *

# before we do anything, we need to inject these constants so any definitions
# that are built that use them will have them in their descriptor entries.
inject_halo_constants()

from binilla.app_window import *
from reclaimer.hek.handler import HaloHandler
from reclaimer.os_v3_hek.handler import OsV3HaloHandler
from reclaimer.os_v4_hek.handler import OsV4HaloHandler
from reclaimer.misc.handler import MiscHaloLoader
from reclaimer.stubbs.handler import StubbsHandler

from reclaimer.meta.halo1_map import get_map_version, get_map_header,\
     get_tag_index, get_index_magic, get_map_magic, decompress_map

from .ripper.hash_cacher import HashCacher
from .config_def import config_def, guerilla_workspace_def
from .widget_picker import *
from .tag_window import HaloTagWindow
from supyr_struct.defs.bitmaps.dds import dds_def

default_hotkeys.update({
    '<F1>': "show_dependency_viewer",
    '<F2>': "show_tag_scanner",
    '<F3>': "show_search_and_replace",
    #'<F4>': "???",

    '<F5>': "switch_tags_dir",
    '<F6>': "set_tags_dir",
    '<F7>': "add_tags_dir",
    #'<F8>': "???",

    '<F9>': "bitmap_from_dds",
    #'<F10>': "???",
    #'<F11>': "???",
    #'<F12>': "???",
    })

this_curr_dir = os.path.abspath(os.curdir) + PATHDIV
curr_dir = dirname(__file__)

RESERVED_WINDOWS_FILENAME_MAP = {}
INVALID_PATH_CHARS = set([str(i.to_bytes(1, 'little'), 'ascii')
                          for i in range(32)])
for name in ('CON', 'PRN', 'AUX', 'NUL'):
    RESERVED_WINDOWS_FILENAME_MAP[name] = '_' + name
for i in range(1, 9):
    RESERVED_WINDOWS_FILENAME_MAP['COM%s' % i] = '_COM%s' % i
    RESERVED_WINDOWS_FILENAME_MAP['LPT%s' % i] = '_LPT%s' % i
INVALID_PATH_CHARS.add(('<', '>', ':', '"', '/', '\\', '|', '?', '*'))

def sanitize_path(path):
    return path.replace('\\', '/').replace('/', PATHDIV)


def sanitize_filename(name):
    # make sure to rename reserved windows filenames to a valid one
    if name in RESERVED_WINDOWS_FILENAME_MAP:
        return RESERVED_WINDOWS_FILENAME_MAP[name]
    final_name = ''
    for c in name:
        if c not in INVALID_PATH_CHARS:
            final_name += c
    if final_name == '':
        raise Exception('BAD %s CHAR FILENAME' % len(name))
    return final_name


class Mozzarilla(Binilla):
    app_name = 'Mozzarilla'
    version = '0.9.18'
    log_filename = 'mozzarilla.log'
    debug = 0

    _mozzarilla_initialized = False

    styles_dir = dirname(__file__) + s_c.PATHDIV + "styles"
    config_path = dirname(__file__) + '%smozzarilla.cfg' % PATHDIV
    config_def = config_def
    config_version = 2

    handlers = (
        HaloHandler,
        OsV3HaloHandler,
        OsV4HaloHandler,
        MiscHaloLoader,
        StubbsHandler,
        )

    handler_names = (
        "Halo 1",
        "Halo 1 OS v3",
        "Halo 1 OS v4",
        "Halo 1 Misc",
        "Stubbs the Zombie",
        )

    # names of the handlers that MUST load tags from within their tags_dir
    tags_dir_relative = set((
        "Halo 1",
        "Halo 1 OS v3",
        "Halo 1 OS v4",
        "Stubbs the Zombie",
        ))

    tags_dirs = ()

    _curr_handler_index = 0
    _curr_tags_dir_index = 0

    widget_picker = def_halo_widget_picker

    tool_windows = None

    window_panes = None
    directory_frame = None
    directory_frame_width = 200

    def __init__(self, *args, **kwargs):
        self.debug = kwargs.pop('debug', self.debug)

        # gotta give it a default handler or else the
        # config file will fail to be created as updating
        # the config requires using methods in the handler.
        kwargs['handler'] = MiscHaloLoader(debug=self.debug)
        self.tags_dir_relative = set(self.tags_dir_relative)
        self.tags_dirs = [("%stags%s" % (this_curr_dir,  s_c.PATHDIV)).lower()]

        Binilla.__init__(self, *args, **kwargs)

        self.file_menu.insert_command("Exit", label="Load guerilla config",
                                      command=self.load_guerilla_config)
        self.file_menu.insert_separator("Exit")

        self.settings_menu.delete(0, "end")  # clear the menu
        self.settings_menu.add_command(label="Set tags directory",
                                       command=self.set_tags_dir)
        self.settings_menu.add_command(label="Add tags directory",
                                       command=self.add_tags_dir)
        self.settings_menu.add_command(label="Remove tags directory",
                                       command=self.remove_tags_dir)

        self.settings_menu.add_separator()
        self.settings_menu.add_command(
            label="Edit config", command=self.show_config_file)
        self.settings_menu.add_separator()
        self.settings_menu.add_command(
            label="Load style", command=self.apply_style)
        self.settings_menu.add_command(
            label="Save current style", command=self.make_style)

        # make the tools and tag set menus
        self.tools_menu = tk.Menu(self.main_menu, tearoff=0)
        self.defs_menu = tk.Menu(self.main_menu, tearoff=0)

        self.main_menu.add_cascade(label="Tag set", menu=self.defs_menu)
        self.main_menu.add_cascade(label="Tools", menu=self.tools_menu)

        for i in range(len(self.handler_names)):
            self.defs_menu.add_command(command=lambda i=i:
                                       self.select_defs(i, manual=True))

        self.tools_menu.add_command(
            label="Dependency viewer", command=self.show_dependency_viewer)
        self.tools_menu.add_command(
            label="Tags directory scanner", command=self.show_tag_scanner)
        self.tools_menu.add_command(
            label="Search and replace", command=self.show_search_and_replace)
        self.tools_menu.add_separator()
        self.tools_menu.add_command(
            label="Tag extractor", command=self.show_tag_extractor_window)
        self.tools_menu.add_command(
            label="Tag hashcacher", command=self.show_hashcacher_window)
        self.tools_menu.add_separator()
        self.tools_menu.add_command(
            label="Bitmap from DDS", command=self.bitmap_from_dds)

        self.defs_menu.add_separator()
        self.handlers = list(self.handlers)
        self.handler_names = list(self.handler_names)

        self.select_defs(manual=False)
        self.tool_windows = {}
        self.hashcacher = HashCacher()
        self._mozzarilla_initialized = True

        self.make_window_panes()
        self.make_directory_frame(self.window_panes)
        self.make_io_text(self.window_panes)

        try:
            if self.config_file.data.header.flags.load_last_workspace:
                self.load_last_workspace()
        except AttributeError:
            pass

        if self.directory_frame is not None:
            self.directory_frame.highlight_tags_dir(self.tags_dir)
        self.update_window_settings()

    @property
    def tags_dir(self):
        try:
            return self.tags_dirs[self._curr_tags_dir_index]
        except IndexError:
            return None

    @tags_dir.setter
    def tags_dir(self, new_val):
        handler = self.handlers[self._curr_handler_index]
        new_val = sanitize_path(new_val)
        self.tags_dirs[self._curr_tags_dir_index] = handler.tagsdir = new_val

    def add_tags_dir(self, e=None, tags_dir=None, manual=True):
        if tags_dir is None:
            tags_dir = askdirectory(initialdir=self.tags_dir, parent=self,
                                    title="Select the tags directory to add")

        if not tags_dir:
            return

        tags_dir = sanitize_path(tags_dir).lower()
        if tags_dir and not tags_dir.endswith(s_c.PATHDIV):
            tags_dir += s_c.PATHDIV

        if tags_dir in self.tags_dirs:
            if manual:
                print("That tags directory already exists.")
            return

        self.tags_dirs.append(tags_dir)
        self.switch_tags_dir(index=len(self.tags_dirs) - 1, manual=False)

        if self.directory_frame is not None:
            self.directory_frame.add_root_dir(tags_dir)

        if manual:
            self.last_load_dir = tags_dir
            curr_index = self._curr_tags_dir_index
            print("Tags directory is currently:\n    %s\n" % self.tags_dir)

    def remove_tags_dir(self, e=None, index=None, manual=True):
        dirs_count = len(self.tags_dirs)
        # need at least 2 tags dirs to delete one manually
        if dirs_count < 2 and manual:
            return

        if index is None:
            index = self._curr_tags_dir_index

        new_index = self._curr_tags_dir_index
        if index <= new_index:
            new_index = max(0, new_index - 1)

        tags_dir = self.tags_dirs[index]
        del self.tags_dirs[index]
        if self.directory_frame is not None:
            self.directory_frame.del_root_dir(tags_dir)

        self.switch_tags_dir(index=new_index, manual=False)

        if manual:
            print("Tags directory is currently:\n    %s\n" % self.tags_dir)

    def set_tags_dir(self, e=None, tags_dir=None, manual=True):
        if tags_dir is None:
            tags_dir = askdirectory(initialdir=self.tags_dir, parent=self,
                                    title="Select the tags directory to add")

        if not tags_dir:
            return

        tags_dir = sanitize_path(tags_dir).lower()
        if tags_dir and not tags_dir.endswith(s_c.PATHDIV):
            tags_dir += s_c.PATHDIV

        if tags_dir in self.tags_dirs:
            print("That tags directory already exists.")
            return

        if self.directory_frame is not None:
            self.directory_frame.set_root_dir(tags_dir)
            self.directory_frame.highlight_tags_dir(self.tags_dir)
        self.tags_dir = tags_dir

        if manual:
            print("Tags directory is currently:\n    %s\n" % self.tags_dir)

    def switch_tags_dir(self, e=None, index=None, manual=True):
        if index is None:
            index = (self._curr_tags_dir_index + 1) % len(self.tags_dirs)
        if self._curr_tags_dir_index == index:
            return

        self._curr_tags_dir_index = index
        self.handler.tagsdir = self.tags_dir

        if self.directory_frame is not None:
            self.directory_frame.highlight_tags_dir(self.tags_dir)

        for handler in self.handlers:
            try: handler.tagsdir = self.tags_dir
            except Exception: pass

        if manual:
            self.last_load_dir = self.tags_dir
            print("Tags directory is currently:\n    %s\n" % self.tags_dir)

    def apply_config(self, e=None):
        Binilla.apply_config(self)
        config_data = self.config_file.data
        mozz = config_data.mozzarilla
        self._curr_handler_index = mozz.selected_handler.data
        tags_dirs = mozz.tags_dirs

        try:
            self.select_defs()
        except Exception:
            pass

        for i in range(len(self.tags_dirs)):
            self.remove_tags_dir(i, manual=False)

        
        self._curr_tags_dir_index = 0
        for tags_dir in tags_dirs:
            self.add_tags_dir(tags_dir=tags_dir.path, manual=False)
        self.switch_tags_dir(
            index=min(mozz.last_tags_dir, len(self.tags_dirs)), manual=False)

        if not self.tags_dir:
            self.tags_dir = (
                self.curr_dir + "%stags%s" % (s_c.PATHDIV,  s_c.PATHDIV))

        for handler in self.handlers:
            try: handler.tagsdir = self.tags_dir
            except Exception: pass

    def bitmap_from_dds(self, e=None):
        fp = askopenfilename(initialdir=self.last_load_dir, parent=self,
                             filetypes=(("DDS image", "*.dds"), ("All", "*")),
                             title="Select the dds to turn into a bitmap tag")

        if not fp:
            return

        try:
            dds_tag = dds_def.build(filepath=fp)
            dds_head = dds_tag.data.header
            caps  = dds_head.caps
            caps2 = dds_head.caps2
            pixelformat = dds_head.dds_pixelformat
            pf_flags = pixelformat.flags
            dds_pixels = dds_tag.data.pixel_data
            if caps2.cubemap and not(caps2.pos_x and caps2.neg_x and
                                     caps2.pos_y and caps2.neg_y and
                                     caps2.pos_z and caps2.neg_z):
                raise TypeError(
                    "DDS image is malformed and does not " +
                    "contain all six necessary cubemap faces.")
                
            elif not dds_head.flags.pixelformat:
                raise TypeError(
                    "DDS image is malformed and does not " +
                    "contain a pixelformat structure.")
        except Exception:
            print("Could not load dds image")
            return

        p_of_2 = set([1 << i for i in range(32)])
        self.last_load_dir = dirname(fp.lower())

        # make the tag window
        window = self.load_tags(filepaths='', def_id='bitm')
        if not window:
            return
        window = window[0]

        # get the bitmap tag and make a new bitmap block
        bitm_tag = window.tag
        bitm_data = bitm_tag.data.tagdata
        bitm_data.bitmaps.STEPTREE.append()
        bitm_block = bitm_data.bitmaps.STEPTREE[-1]
        bitm_block.bitm_id.set_to("bitm")

        # get the dimensions
        width = dds_head.width
        height = dds_head.height
        depth = dds_head.depth
        if not caps2.volume:
            depth = 1

        # set up the dimensions
        bitm_block.width = width
        bitm_block.height = height
        bitm_block.depth = depth

        # set the mipmap count
        if dds_head.caps.mipmaps:
            bitm_block.mipmaps = max(dds_head.mipmap_count-1, 0)

        # set up the flags
        fcc = pixelformat.four_cc.enum_name
        min_w = min_h = min_d = 1
        if fcc in ("DXT1", "DXT2", "DXT3", "DXT4", "DXT5"):
            bitm_block.flags.compressed = True
            min_w = min_h = 4
        bitm_block.flags.power_of_2_dim = True  # even if it isn't actually a
        # power of 2 texture, this flag need to be checked or tool will bitch

        bitm_block.format.data = -1
        bpp = 8  # bits per pixel

        # choose bitmap format
        if fcc == "DXT1":
            bitm_data.format.data = 0
            bitm_block.format.set_to("dxt1")
            bpp = 4
        elif fcc in ("DXT2", "DXT3"):
            bitm_data.format.data = 1
            bitm_block.format.set_to("dxt3")
        elif fcc in ("DXT4", "DXT5"):
            bitm_data.format.data = 2
            bitm_block.format.set_to("dxt5")
        elif pf_flags.RGB:
            bitcount = pixelformat.rgb_bitcount
            bitm_data.format.data = 4
            bpp = 32
            if pf_flags.has_alpha and bitcount == 32:
                bitm_block.format.set_to("a8r8g8b8")
            elif bitcount == 32:
                bitm_block.format.set_to("x8r8g8b8")
            elif bitcount in (15, 16):
                bpp = 16
                bitm_data.format.data = 3
                a_mask = pixelformat.a_bitmask
                r_mask = pixelformat.r_bitmask
                g_mask = pixelformat.g_bitmask
                b_mask = pixelformat.b_bitmask
                # shift the masks right until they're all the same scale
                while a_mask and not(a_mask&1): a_mask = a_mask >> 1
                while r_mask and not(r_mask&1): r_mask = r_mask >> 1
                while g_mask and not(g_mask&1): g_mask = g_mask >> 1
                while b_mask and not(b_mask&1): b_mask = b_mask >> 1

                mask_set = set((a_mask, r_mask, g_mask, b_mask))
                if mask_set == set((31, 63, 0)):
                    bitm_block.format.set_to("r5g6b5")
                elif mask_set == set((1, 31)):
                    bitm_block.format.set_to("a1r5g5b5")
                elif mask_set == set((15, )):
                    bitm_block.format.set_to("a4r4g4b4")

        elif pf_flags.alpha_only:
            bitm_block.format.set_to("a8")

        elif pf_flags.luminance:
            if pf_flags.has_alpha:
                bitm_block.format.set_to("a8y8")
            else:
                bitm_block.format.set_to("y8")

        if bitm_block.format.data == -1:
            bitm_block.format.data = bpp = 0
            print("Unknown dds image format.")

        # make sure the number of mipmaps is accurate
        face_count = 6 if caps2.cubemap else 1
        w, h, d = width, height, depth
        pixel_counts = []

        # make a list of all the pixel counts of all the mipmaps.
        for mip in range(bitm_block.mipmaps):
            pixel_counts.append(w*h*d)
            w, h, d = (max(w//2, min_w),
                       max(h//2, min_h),
                       max(d//2, min_d))

        # see how many mipmaps can fit in the number of pixels in the dds file.
        while True:
            if (sum(pixel_counts)*bpp*face_count)//8 <= len(dds_pixels):
                break

            pixel_counts.pop(-1)

            #the mipmap count is zero and the bitmap still will
            #not fit within the space provided. Something's wrong
            if len(pixel_counts) == 0:
                print("Size of the pixel data is too small to read even " +
                      "the fullsize image from. This dds file is malformed.")
                break

        if len(pixel_counts) != bitm_block.mipmaps:
            print("Mipmap count is too high for the number of pixels stored " +
                  "in the dds file. The mipmap count has been reduced from " +
                  "%s to %s." % (bitm_block.mipmaps, len(pixel_counts)))

        bitm_block.mipmaps = len(pixel_counts)

        # choose the texture type
        pixels = dds_pixels
        if caps2.volume:
            bitm_data.type.data = 1
            bitm_block.type.set_to("texture_3d")
        elif caps2.cubemap:
            # gotta rearrange the mipmaps and cubemap faces
            pixels = b''
            mip_count = bitm_block.mipmaps + 1
            images = [None]*6*(mip_count)
            pos = 0

            # dds images store all mips for one face next to each
            # other, and then the next set of mips for the next face.
            for face in range(6):
                w, h, d = width, height, depth
                for mip in range(mip_count):
                    i = mip*6 + face
                    image_size = (bpp*w*h*d)//8
                    images[i] = dds_pixels[pos: pos + image_size]
                    
                    w, h, d = (max(w//2, min_w),
                               max(h//2, min_h),
                               max(d//2, min_d))
                    pos += image_size

            for image in images:
                pixels += image

            bitm_data.type.data = 2
            bitm_block.type.set_to("cubemap")

        # place the pixels from the dds tag into the bitmap tag
        bitm_data.processed_pixel_data.data = pixels

        # reload the window to display the newly entered info
        window.reload()
        # prompt the user to save the tag somewhere
        self.save_tag_as()

    def load_last_workspace(self):
        if self._mozzarilla_initialized:
            Binilla.load_last_workspace(self)

    def load_guerilla_config(self):
        fp = askopenfilename(initialdir=self.last_load_dir, parent=self,
                             title="Select the tag to load",
                             filetypes=(('Guerilla config', '*.cfg'),
                                        ('All', '*')))

        if not fp:
            return

        self.last_load_dir = dirname(fp)
        workspace = guerilla_workspace_def.build(filepath=fp)

        pad_x = self.io_text.winfo_rootx() - self.winfo_x()
        pad_y = self.io_text.winfo_rooty() - self.winfo_y()

        tl_corner = workspace.data.window_header.t_l_corner
        br_corner = workspace.data.window_header.b_r_corner

        self.geometry("%sx%s+%s+%s" % (
            br_corner.x - tl_corner.x - pad_x,
            br_corner.y - tl_corner.y - pad_y,
            tl_corner.x, tl_corner.y))

        for tag in workspace.data.tags:
            if not tag.is_valid_tag:
                continue

            windows = self.load_tags(tag.filepath)
            if not windows:
                continue

            w = windows[0]

            tl_corner = tag.window_header.t_l_corner
            br_corner = tag.window_header.b_r_corner

            self.place_window_relative(w, pad_x + tl_corner.x,
                                          pad_y + tl_corner.y)
            w.geometry("%sx%s" % (br_corner.x - tl_corner.x,
                                  br_corner.y - tl_corner.y))

    def load_tags(self, filepaths=None, def_id=None):
        tags_dir = self.tags_dir
        # if there is not tags directory, this can be loaded normally
        if tags_dir is None:
            return Binilla.load_tags(self, filepaths, def_id)

        if isinstance(filepaths, tk.Event):
            filepaths = None
        if filepaths is None:
            filetypes = [('All', '*')]
            defs = self.handler.defs
            for id in sorted(defs.keys()):
                filetypes.append((id, defs[id].ext))
            filepaths = askopenfilenames(initialdir=self.last_load_dir,
                                         filetypes=filetypes, parent=self,
                                         title="Select the tag to load")
            if not filepaths:
                return

        if isinstance(filepaths, str):
            # account for a stupid bug with certain versions of windows
            if filepaths.startswith('{'):
                filepaths = re.split("\}\W\{", filepaths[1:-1])
            else:
                filepaths = (filepaths, )

        sani = sanitize_path
        handler_name = self.handler_names[self._curr_handler_index]

        sanitized_paths = [sani(path).lower() for path in filepaths]

        # make sure all the chosen tag paths are relative
        # to the current tags directory if they must be
        if handler_name in self.tags_dir_relative:
            for path in sanitized_paths:
                if (not path) or len(path.lower().split(tags_dir.lower())) == 2:
                    continue
    
                print("Specified tag(s) are not located in the tags directory")
                return

        windows = Binilla.load_tags(self, sanitized_paths, def_id)

        if not windows:
            print("You might need to change the tag set to load these tag(s).")
            return ()

        return windows

    def load_tag_as(self, e=None):
        '''Prompts the user for a tag to load and loads it.'''
        if self.def_selector_window:
            return

        filetypes = [('All', '*')]
        defs = self.handler.defs
        for def_id in sorted(defs.keys()):
            filetypes.append((def_id, defs[def_id].ext))

        fp = askopenfilename(initialdir=self.last_load_dir,
                             filetypes=filetypes, parent=self,
                             title="Select the tag to load")

        if not fp:
            return

        fp = fp.lower()

        self.last_load_dir = dirname(fp)
        dsw = DefSelectorWindow(
            self, title="Which tag is this", action=lambda def_id:
            self.load_tags(filepaths=fp, def_id=def_id))
        self.def_selector_window = dsw
        self.place_window_relative(self.def_selector_window, 30, 50)

    def make_config(self, filepath=None):
        if filepath is None:
            filepath = self.config_path

        # create the config file from scratch
        self.config_file = self.config_def.build()
        self.config_file.filepath = filepath

        data = self.config_file.data

        # make sure these have as many entries as they're supposed to
        for block in (data.directory_paths, data.widgets.depths, data.colors):
            block.extend(len(block.NAME_MAP))

        tags_dirs = data.mozzarilla.tags_dirs
        for tags_dir in self.tags_dirs:
            tags_dirs.append()
            tags_dirs[-1].path = tags_dir

        self.update_config()

        c_hotkeys = data.hotkeys
        c_tag_window_hotkeys = data.tag_window_hotkeys

        for k_set, b in ((default_hotkeys, c_hotkeys),
                         (default_tag_window_hotkeys, c_tag_window_hotkeys)):
            default_keys = k_set
            hotkeys = b
            for combo, method in k_set.items():
                hotkeys.append()
                keys = hotkeys[-1].combo

                modifier, key = read_hotkey_string(combo)
                keys.modifier.set_to(modifier)
                keys.key.set_to(key)

                hotkeys[-1].method.set_to(method)

    def make_tag_window(self, tag, focus=True, window_cls=None):
        if window_cls is None:
            window_cls = HaloTagWindow
        w = Binilla.make_tag_window(self, tag, focus=focus,
                                    window_cls=window_cls)
        self.update_tag_window_title(w)
        return w

    def make_window_panes(self):
        self.window_panes = tk.PanedWindow(
            self.root_frame, sashrelief='raised', sashwidth=8,
            bd=self.frame_depth, bg=self.frame_bg_color)
        self.window_panes.pack(anchor='nw', fill='both', expand=True)

    def make_io_text(self, master=None):
        if not self._initialized:
            return
        if master is None:
            master = self.root_frame
        Binilla.make_io_text(self, master)

    def make_directory_frame(self, master=None):
        if not self._initialized:
            return
        if master is None:
            master = self.root_frame
        self.directory_frame = DirectoryFrame(self)
        self.directory_frame.pack(expand=True, fill='both')

    def new_tag(self, e=None):
        if self.def_selector_window:
            return

        dsw = DefSelectorWindow(
            self, title="Select a tag to create", action=lambda def_id:
            self.load_tags(filepaths='', def_id=def_id))
        self.def_selector_window = dsw
        self.place_window_relative(self.def_selector_window, 30, 50)

    def save_tag(self, tag=None):
        if isinstance(tag, tk.Event):
            tag = None
        if tag is None:
            if self.selected_tag is None:
                return
            tag = self.selected_tag

        if tag is self.config_file:
            return self.save_config()

        # change the tags filepath to be relative to the current tags directory
        if hasattr(tag, "rel_filepath"):
            tag.filepath = tag.tags_dir + tag.rel_filepath

        Binilla.save_tag(self, tag)
        return tag

    def save_tag_as(self, tag=None, filepath=None):
        if isinstance(tag, tk.Event):
            tag = None
        if tag is None:
            if self.selected_tag is None:
                return
            tag = self.selected_tag

        if not hasattr(tag, "serialize"):
            return

        if filepath is None:
            ext = tag.ext
            filepath = asksaveasfilename(
                initialdir=dirname(tag.filepath), parent=self,
                defaultextension=ext, title="Save tag as...",
                filetypes=[(ext[1:], "*" + ext), ('All', '*')])
        else:
            filepath = tag.filepath

        if not filepath:
            return

        # make sure the filepath is sanitized
        filepath = sanitize_path(filepath).lower()
        if len(filepath.split(tag.tags_dir)) != 2:
            print("Cannot save outside the tags directory")
            return

        tag.rel_filepath = filepath.split(tag.tags_dir)[-1]

        Binilla.save_tag_as(self, tag, filepath)

        self.update_tag_window_title(self.get_tag_window_by_tag(tag))
        return tag

    def select_defs(self, menu_index=None, manual=True):
        names = self.handler_names
        if menu_index is None:
            try:
                names[self._curr_handler_index]
            except Exception:
                self._curr_handler_index = 0
            menu_index = self._curr_handler_index

        name = names[menu_index]
        handler = self.handlers[menu_index]

        if handler is None or handler is self.handler:
            return

        if manual:
            print("Changing tag set to %s" % name)
            self.io_text.update_idletasks()

        if isinstance(handler, type):
            self.handlers[menu_index] = handler(debug=self.debug)

        self.handler = self.handlers[menu_index]

        entryconfig = self.defs_menu.entryconfig
        for i in range(len(names)):
            entryconfig(i, label=names[i])

        entryconfig(menu_index, label=("%s %s" % (name, u'\u2713')))
        if manual:
            print("    Finished")

        self._curr_handler_index = menu_index

        self.config_file.data.mozzarilla.selected_handler.data = menu_index

    def set_handler(self, handler=None, index=None, name=None):
        if handler is not None:
            handler_index = self.handlers.index(handler)
            self._curr_handler_index = handler_index
            self.handler = handler
        elif index is not None:
            self._curr_handler_index = handler_index
            self.handler = self.handlers[handler_index]
        elif name is not None:
            handler_index = self.handler_names.index(name)
            self._curr_handler_index = handler_index
            self.handler = self.handlers[handler_index]

    def show_dependency_viewer(self, e=None):
        w = self.tool_windows.get("dependency_window")
        if w is not None:
            try: w.destroy()
            except Exception: pass
            del self.tool_windows["dependency_window"]
            return

        if not hasattr(self.handler, 'tag_ref_cache'):
            print("Change the current tag set.")
            return

        self.tool_windows["dependency_window"] = w = DependencyWindow(self)
        self.place_window_relative(w, 30, 50); w.focus_set()

    def show_tag_scanner(self, e=None):
        w = self.tool_windows.get("tag_scanner_window")
        if w is not None:
            try: w.destroy()
            except Exception: pass
            del self.tool_windows["tag_scanner_window"]
            return

        if not hasattr(self.handler, 'tag_ref_cache'):
            print("Change the current tag set.")
            return

        self.tool_windows["tag_scanner_window"] = w = TagScannerWindow(self)
        self.place_window_relative(w, 30, 50); w.focus_set()

    def show_hashcacher_window(self, e=None):
        if not self.debug_mode:
            print("Still working on this")
            return
        w = self.tool_windows.get("hashcacher_window")
        if w is not None:
            try: w.destroy()
            except Exception: pass
            del self.tool_windows["hashcacher_window"]
            return

        self.tool_windows["hashcacher_window"] = w = HashcacherWindow(self)
        self.place_window_relative(w, 30, 50); w.focus_set()

    def show_tag_extractor_window(self, e=None):
        if not self.debug_mode:
            print("Still working on this")
            return
        w = self.tool_windows.get("tag_extractor_window")
        if w is not None:
            try: w.destroy()
            except Exception: pass
            del self.tool_windows["tag_extractor_window"]
            return

        self.tool_windows["tag_extractor_window"] = w = TagExtractorWindow(self)
        self.place_window_relative(w, 30, 50); w.focus_set()

    def show_search_and_replace(self, e=None):
        w = self.tool_windows.get("s_and_r_window")
        if w is not None:
            try: w.destroy()
            except Exception: pass
            del self.tool_windows["s_and_r_window"]
            return

        self.tool_windows["s_and_r_window"] = w = SearchAndReplaceWindow(self)
        self.place_window_relative(w, 30, 50); w.focus_set()

    def update_config(self, config_file=None):
        if config_file is None:
            config_file = self.config_file
        Binilla.update_config(self, config_file)

        config_data = config_file.data
        mozz = config_data.mozzarilla
        tags_dirs = mozz.tags_dirs

        mozz.selected_handler.data = self._curr_handler_index
        mozz.last_tags_dir = self._curr_tags_dir_index

        sani = self.handler.sanitize_path
        del tags_dirs[:]
        for tags_dir in self.tags_dirs:
            tags_dirs.append()
            tags_dirs[-1].path = sani(tags_dir)

        if mozz.flags.show_hierarchy_window and mozz.flags.show_console_window:
            try:
                # idk if this value can ever be negative, so i'm using abs
                mozz.sash_position = abs(self.window_panes.sash_coord(0)[0])
            except Exception:
                pass

    def update_tag_window_title(self, window):
        if not hasattr(window, 'tag'):
            return

        tag = window.tag
        if tag is self.config_file:
            window.update_title('%s %s config' % (self.app_name, self.version))
        if not hasattr(tag, 'tags_dir'):
            return

        tags_dir = tag.tags_dir

        try:
            if tag is self.config_file or not tags_dir:
                return
            handler_name = self.handler_names[self._curr_handler_index]
            if handler_name not in self.tags_dir_relative:
                return
            handler_i = self.handlers.index(window.handler)
            title = "[%s][%s] %s" % (
                self.handler_names[handler_i], tags_dir[:-1], tag.rel_filepath)
        except Exception:
            pass
        window.update_title(title)

    def update_window_settings(self):
        if not self._initialized:
            return

        Binilla.update_window_settings(self)
        try:
            for m in (self.defs_menu, self.tools_menu):
                m.config(bg=self.default_bg_color, fg=self.text_normal_color)

            self.window_panes.config(
                bg=self.frame_bg_color, bd=self.frame_depth)
            self.directory_frame.apply_style()
            for w in self.tool_windows.values():
                if w is not None:
                    w.apply_style()

            try:
                mozz = self.config_file.data.mozzarilla
                show_hierarchy = mozz.flags.show_hierarchy_window
                show_console = mozz.flags.show_console_window
                sash_pos = mozz.sash_position
                self.window_panes.forget(self.directory_frame)
                self.window_panes.forget(self.io_frame)

                if show_hierarchy:
                    self.directory_frame.pack(fill='both', expand=True)
                    self.window_panes.add(self.directory_frame)
                if show_console:
                    self.io_frame.pack(fill='both', expand=True)
                    self.window_panes.add(self.io_frame)

                # if both window panes are shown, we need to position the sash
                if show_hierarchy and show_console and sash_pos != 0:
                    try:
                        self.update_idletasks()
                        self.window_panes.sash_place(0, sash_pos, 1)
                    except Exception:
                        pass
            except Exception:
                print(format_exc())
        except AttributeError: print(format_exc())
        except Exception: print(format_exc())


class DependencyWindow(tk.Toplevel, BinillaWidget):

    app_root = None
    handler = None

    _zipping = False
    stop_zipping = False

    def __init__(self, app_root, *args, **kwargs): 
        self.handler = app_root.handler
        self.app_root = app_root
        kwargs.update(width=400, height=500, bd=0,
                      highlightthickness=0, bg=self.default_bg_color)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)

        tagset = app_root.handler_names[app_root._curr_handler_index]
        self.title("[%s] Tag dependency viewer" % tagset)
        self.minsize(width=400, height=100)

        # make the tkinter variables
        self.tag_filepath = tk.StringVar(self)

        # make the frames
        self.filepath_frame = tk.LabelFrame(self, text="Select a tag")
        self.button_frame = tk.LabelFrame(self, text="Actions")

        self.display_button = tk.Button(
            self.button_frame, width=25, text='Show dependencies',
            command=self.populate_dependency_tree)

        self.zip_button = tk.Button(
            self.button_frame, width=25, text='Zip tag recursively',
            command=self.recursive_zip)

        self.dependency_window = DependencyFrame(self, app_root=self.app_root)

        self.filepath_entry = tk.Entry(
            self.filepath_frame, textvariable=self.tag_filepath)
        self.browse_button = tk.Button(
            self.filepath_frame, text="Browse", command=self.browse)

        self.display_button.pack(padx=4, pady=2, side='left')
        self.zip_button.pack(padx=4, pady=2, side='right')

        self.filepath_entry.pack(padx=(4, 0), pady=2, side='left',
                                 expand=True, fill='x')
        self.browse_button.pack(padx=(0, 4), pady=2, side='left')

        self.filepath_frame.pack(fill='x', padx=1)
        self.button_frame.pack(fill='x', padx=1)
        self.dependency_window.pack(fill='both', padx=1, expand=True)

        self.transient(app_root)
        self.apply_style()
 
    def apply_style(self):
        self.config(bg=self.default_bg_color)
        for w in (self.filepath_frame, self.button_frame):
            w.config(fg=self.text_normal_color, bg=self.default_bg_color)

        for w in (self.display_button, self.zip_button, self.browse_button):
            w.config(bg=self.button_color, activebackground=self.button_color,
                     fg=self.text_normal_color, bd=self.button_depth,
                     disabledforeground=self.text_disabled_color)

        self.filepath_entry.config(
            bd=self.entry_depth,
            bg=self.entry_normal_color, fg=self.text_normal_color,
            disabledbackground=self.entry_disabled_color,
            disabledforeground=self.text_disabled_color,
            selectbackground=self.entry_highlighted_color,
            selectforeground=self.text_highlighted_color)

        self.dependency_window.apply_style()

    def browse(self):
        filetypes = [('All', '*')]

        defs = self.app_root.handler.defs
        for def_id in sorted(defs.keys()):
            filetypes.append((def_id, defs[def_id].ext))
        fp = askopenfilename(initialdir=self.app_root.last_load_dir,
                             filetypes=filetypes,
                             parent=self, title="Select a tag")

        if not fp:
            return

        fp = sanitize_path(fp).lower()
        self.app_root.last_load_dir = dirname(fp)
        self.tag_filepath.set(fp)

    def destroy(self):
        self.app_root.tool_windows.pop("dependency_window", None)
        self.stop_zipping = True
        tk.Toplevel.destroy(self)

    def get_tag(self, filepath):
        handler = self.handler
        def_id = handler.get_def_id(filepath)

        tag = handler.tags.get(def_id, {}).get(handler.sanitize_path(filepath))
        if tag is not None:
            return tag
        try:
            return handler.build_tag(filepath=filepath)
        except Exception:
            pass

    def get_dependencies(self, tag):
        handler = self.handler
        def_id = tag.def_id
        dependency_cache = handler.tag_ref_cache.get(def_id)
        tags_dir = self.dependency_window.tags_dir

        if not dependency_cache:
            return ()

        nodes = handler.get_nodes_by_paths(handler.tag_ref_cache[def_id],
                                           tag.data)

        dependencies = []

        for node in nodes:
            # if the node's filepath is empty, just skip it
            if not node.filepath:
                continue
            try:
                ext = '.' + node.tag_class.enum_name
                if (self.handler.treat_mode_as_mod2 and (
                    ext == '.model' and not exists(
                        tags_dir + node.filepath + ext))):
                    ext = '.gbxmodel'
            except Exception:
                ext = ''
            dependencies.append(node.filepath + ext)
        return dependencies

    def populate_dependency_tree(self):
        filepath = self.tag_filepath.get()
        if not filepath:
            return

        app = self.app_root
        handler = self.handler = app.handler
        sani = sanitize_path

        handler_name = app.handler_names[app._curr_handler_index]
        if handler_name not in app.tags_dir_relative:
            print("Change the current tag set.")
            return
        else:
            tags_dir = handler.tagsdir.lower()

        filepath = sani(filepath.lower())
        rel_filepath = filepath.split(tags_dir)
        if len(rel_filepath) != 2:
            print("Specified tag is not located within the tags directory")
            return

        tag = self.get_tag(filepath)
        if tag is None:
            print("Could not load tag:\n    %s" % filepath)
            return

        self.dependency_window.handler = handler
        self.dependency_window.tags_dir = tags_dir
        self.dependency_window.root_tag_path = tag.filepath
        self.dependency_window.root_tag_text = rel_filepath[-1]

        self.dependency_window.reload()

    def recursive_zip(self):
        if self._zipping:
            return
        try: self.zip_thread.join()
        except Exception: pass
        self.zip_thread = Thread(target=self._recursive_zip)
        self.zip_thread.daemon = True
        self.zip_thread.start()

    def _recursive_zip(self):
        self._zipping = True
        try:
            self.do_recursive_zip()
        except Exception:
            print(format_exc())
        self._zipping = False

    def do_recursive_zip(self):
        tag_path = self.tag_filepath.get().lower()
        if not tag_path:
            return

        app = self.app_root
        handler = self.handler = app.handler
        sani = sanitize_path

        handler_name = app.handler_names[app._curr_handler_index]
        if handler_name not in app.tags_dir_relative:
            print("Change the current tag set.")
            return
        else:
            tags_dir = handler.tagsdir.lower()

        tag_path = sani(tag_path)
        if len(tag_path.split(tags_dir)) != 2:
            print("Specified tag is not located within the tags directory")
            return

        tagzip_path = asksaveasfilename(
            initialdir=self.app_root.last_load_dir, parent=self,
            title="Save zipfile to...", filetypes=(("zipfile", "*.zip"), ))

        if not tagzip_path:
            return

        tag = self.get_tag(tag_path)
        if tag is None:
            print("Could not load tag:\n    %s" % tag_path)
            return

        # make the zipfile to put everything in
        tagzip_path = splitext(tagzip_path)[0] + ".zip"

        tags_to_zip = [tag_path.split(tags_dir)[-1]]
        new_tags_to_zip = []
        seen_tags = set()

        with zipfile.ZipFile(tagzip_path, mode='w') as tagzip:
            # loop over all the tags and add them to the zipfile
            while tags_to_zip:
                for rel_tag_path in tags_to_zip:
                    tag_path = tags_dir + rel_tag_path
                    if self.stop_zipping:
                        print('Recursive zip operation cancelled.\n')
                        return

                    if rel_tag_path in seen_tags:
                        continue
                    seen_tags.add(rel_tag_path)

                    try:
                        print("Adding '%s' to zipfile" % rel_tag_path)
                        app.update_idletasks()
                        tag = self.get_tag(tag_path)
                        new_tags_to_zip.extend(self.get_dependencies(tag))

                        # try to conserve memory a bit
                        del tag

                        tagzip.write(tag_path, arcname=rel_tag_path)
                    except Exception:
                        print("    Could not add '%s' to zipfile." %
                              rel_tag_path)

                # replace the tags to zip with the newly collected ones
                tags_to_zip[:] = new_tags_to_zip
                del new_tags_to_zip[:]

        print("\nRecursive zip completed.\n")


class TagScannerWindow(tk.Toplevel, BinillaWidget):

    app_root = None
    handler = None

    _scanning = False
    stop_scanning = False
    print_interval = 5

    listbox_index_to_def_id = ()

    def __init__(self, app_root, *args, **kwargs): 
        self.handler = handler = app_root.handler
        self.app_root = app_root
        kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)

        ext_id_map = handler.ext_id_map
        self.listbox_index_to_def_id = [
            ext_id_map[ext] for ext in sorted(ext_id_map.keys())
            if ext_id_map[ext] in handler.tag_ref_cache]

        tagset = app_root.handler_names[app_root._curr_handler_index]

        self.title("[%s] Tag directory scanner" % tagset)
        self.minsize(width=400, height=250)
        self.resizable(0, 0)

        # make the tkinter variables
        self.directory_path = tk.StringVar(self)
        self.logfile_path = tk.StringVar(self)

        # make the frames
        self.directory_frame = tk.LabelFrame(self, text="Directory to scan")
        self.logfile_frame = tk.LabelFrame(self, text="Output log filepath")
        self.def_ids_frame = tk.LabelFrame(
            self, text="Select which tag types to scan")
        self.button_frame = tk.Frame(self.def_ids_frame)

        self.scan_button = tk.Button(
            self.button_frame, text='Scan directory',
            width=20, command=self.scan_directory)
        self.cancel_button = tk.Button(
            self.button_frame, text='Cancel scan',
            width=20, command=self.cancel_scan)
        self.select_all_button = tk.Button(
            self.button_frame, text='Select all',
            width=20, command=self.select_all)
        self.deselect_all_button = tk.Button(
            self.button_frame, text='Deselect all',
            width=20, command=self.deselect_all)

        self.directory_entry = tk.Entry(
            self.directory_frame, textvariable=self.directory_path)
        self.dir_browse_button = tk.Button(
            self.directory_frame, text="Browse", command=self.dir_browse)

        self.logfile_entry = tk.Entry(
            self.logfile_frame, textvariable=self.logfile_path,)
        self.log_browse_button = tk.Button(
            self.logfile_frame, text="Browse", command=self.log_browse)

        self.def_ids_scrollbar = tk.Scrollbar(
            self.def_ids_frame, orient="vertical")
        self.def_ids_listbox = tk.Listbox(
            self.def_ids_frame, selectmode='multiple', highlightthickness=0)
        self.def_ids_scrollbar.config(command=self.def_ids_listbox.yview)

        for def_id in self.listbox_index_to_def_id:
            tag_ext = handler.id_ext_map[def_id].split('.')[-1]
            self.def_ids_listbox.insert('end', tag_ext)

            # these tag types are massive, so by
            # default dont set them to be scanned
            if def_id in ("sbsp", "scnr"):
                continue
            self.def_ids_listbox.select_set('end')

        for w in (self.directory_entry, self.logfile_entry):
            w.pack(padx=(4, 0), pady=2, side='left', expand=True, fill='x')

        for w in (self.dir_browse_button, self.log_browse_button):
            w.pack(padx=(0, 4), pady=2, side='left')

        for w in (self.scan_button, self.cancel_button):
            w.pack(padx=4, pady=2)

        for w in (self.deselect_all_button, self.select_all_button):
            w.pack(padx=4, pady=2, side='bottom')

        self.def_ids_listbox.pack(side='left', fill="both", expand=True)
        self.def_ids_scrollbar.pack(side='left', fill="y")
        self.button_frame.pack(side='left', fill="y")

        self.directory_frame.pack(fill='x', padx=1)
        self.logfile_frame.pack(fill='x', padx=1)
        self.def_ids_frame.pack(fill='x', padx=1, expand=True)

        self.transient(app_root)

        self.directory_entry.insert(0, handler.tagsdir)
        self.logfile_entry.insert(0, this_curr_dir + "tag_scanner.log")
        self.apply_style()

    def apply_style(self):
        self.config(bg=self.default_bg_color)        
        for w in(self.directory_frame, self.logfile_frame, self.def_ids_frame):
            w.config(fg=self.text_normal_color, bg=self.default_bg_color)

        self.button_frame.config(bg=self.default_bg_color)

        for w in (self.scan_button, self.cancel_button,
                  self.select_all_button, self.deselect_all_button,
                  self.dir_browse_button, self.log_browse_button):
            w.config(bg=self.button_color, activebackground=self.button_color,
                     fg=self.text_normal_color, bd=self.button_depth,
                     disabledforeground=self.text_disabled_color)

        for w in (self.directory_entry, self.logfile_entry):
            w.config(bd=self.entry_depth,
                bg=self.entry_normal_color, fg=self.text_normal_color,
                disabledbackground=self.entry_disabled_color,
                disabledforeground=self.text_disabled_color,
                selectbackground=self.entry_highlighted_color,
                selectforeground=self.text_highlighted_color)

        self.def_ids_listbox.config(
            bg=self.enum_normal_color, fg=self.text_normal_color,
            selectbackground=self.enum_highlighted_color,
            selectforeground=self.text_highlighted_color)

    def deselect_all(self):
        self.def_ids_listbox.select_clear(0, 'end')

    def select_all(self):
        for i in range(len(self.listbox_index_to_def_id)):
            self.def_ids_listbox.select_set(i)

    def get_tag(self, filepath):
        handler = self.handler
        def_id = handler.get_def_id(filepath)

        tag = handler.tags.get(def_id, {}).get(handler.sanitize_path(filepath))
        if tag is not None:
            return tag
        try:
            return handler.build_tag(filepath=filepath)
        except Exception:
            pass

    def dir_browse(self):
        dirpath = askdirectory(initialdir=self.directory_path.get(),
                               parent=self, title="Select directory to scan")

        if not dirpath:
            return

        dirpath = sanitize_path(dirpath).lower()
        if not dirpath.endswith(PATHDIV):
            dirpath += PATHDIV

        self.app_root.last_load_dir = dirname(dirpath)
        if len(dirpath.split(self.handler.tagsdir)) != 2:
            print("Chosen directory is not located within the tags directory")
            return

        self.directory_path.set(dirpath)

    def log_browse(self):
        filepath = asksaveasfilename(
            initialdir=dirname(self.logfile_entry.get()),
            title="Save scan log to...", parent=self,
            filetypes=(("tag scanner log", "*.log"), ('All', '*')))

        if not filepath:
            return

        filepath = sanitize_path(filepath)
        self.app_root.last_load_dir = dirname(filepath)

        self.logfile_path.set(filepath)

    def destroy(self):
        self.app_root.tool_windows.pop("tag_scanner_window", None)
        self.stop_scanning = True
        tk.Toplevel.destroy(self)

    def cancel_scan(self):
        self.stop_scanning = True

    def scan_directory(self):
        if self._scanning:
            return
        try: self.scan_thread.join()
        except Exception: pass
        self.scan_thread = Thread(target=self._scan_directory)
        self.scan_thread.daemon = True
        self.scan_thread.start()

    def _scan_directory(self):
        self._scanning = True
        try:
            self.scan()
        except Exception:
            print(format_exc())
        self._scanning = False

    def scan(self):
        app = self.app_root
        handler = self.handler
        sani = sanitize_path
        self.stop_scanning = False

        tagsdir = self.handler.tagsdir.lower()
        dirpath = sani(self.directory_path.get().lower())
        logpath = sani(self.logfile_path.get())

        if len(dirpath.split(tagsdir)) != 2:
            print("Chosen directory is not located within the tags directory")
            return

        #this is the string to store the entire debug log
        log_name = "HEK Tag Scanner log"
        debuglog = "\n%s%s%s\n\n" % (
            "-"*30, log_name, "-" * (50-len(log_name)))
        debuglog += "tags directory = %s\nscan directory = %s\n\n" % (
            tagsdir, dirpath)
        debuglog += "broken dependencies are listed below\n"

        get_nodes = handler.get_nodes_by_paths
        get_tagref_invalid = handler.get_tagref_invalid

        s_time = time()
        c_time = s_time
        p_int = self.print_interval

        all_tag_paths = {self.listbox_index_to_def_id[int(i)]: [] for i in
                         self.def_ids_listbox.curselection()}
        ext_id_map = handler.ext_id_map
        id_ext_map = handler.id_ext_map

        print("Locating tags...")

        for root, directories, files in os.walk(dirpath):
            if not root.endswith(PATHDIV):
                root += PATHDIV

            root = root.split(tagsdir)[-1]

            for filename in files:
                filepath = sani(root + filename)

                if time() - c_time > p_int:
                    c_time = time()
                    print(' '*4 + filepath)
                    app.update_idletasks()

                if self.stop_scanning:
                    print('Tag scanning operation cancelled.\n')
                    return

                tag_paths = all_tag_paths.get(
                    ext_id_map.get(splitext(filename)[-1].lower()))

                if tag_paths is not None:
                    tag_paths.append(filepath)

        # make the debug string by scanning the tags directory
        for def_id in sorted(all_tag_paths.keys()):
            tag_ref_paths = handler.tag_ref_cache[def_id]

            app.update_idletasks()
            print("Scanning '%s' tags..." % id_ext_map[def_id][1:])
            tags_coll = all_tag_paths[def_id]

            # always display the first tag's filepath
            c_time = time() - p_int + 1

            for filepath in sorted(tags_coll):
                if self.stop_scanning:
                    print('Tag scanning operation cancelled.\n')
                    break

                if time() - c_time > p_int:
                    c_time = time()
                    print(' '*4 + filepath)
                    app.update_idletasks()

                tag = self.get_tag(tagsdir + filepath)
                if tag is None:
                    continue

                try:
                    missed = get_nodes(tag_ref_paths, tag.data,
                                       get_tagref_invalid)

                    if not missed:
                        continue

                    debuglog += "\n\n%s\n" % filepath
                    block_name = None

                    for block in missed:
                        if block.NAME != block_name:
                            debuglog += '%s%s\n' % (' '*4, block.NAME)
                            block_name = block.NAME
                        try:
                            ext = '.' + block.tag_class.enum_name
                        except Exception:
                            ext = ''
                        debuglog += '%s%s\n' % (' '*8, block.STEPTREE + ext)

                except Exception:
                    print("    Could not scan '%s'" % tag.filepath)
                    continue

            if self.stop_scanning:
                break

        print("\nScanning took %s seconds." % int(time() - s_time))
        print("Writing logfile to %s..." % logpath)
        app.update_idletasks()

        # make and write to the logfile
        try:
            handler.make_log_file(debuglog, logpath)
            print("Scan completed.\n")
            return
        except Exception:
            pass

        print("Could not create log. Printing log to console instead.\n\n")
        for line in debuglog.split('\n'):
            try:
                print(line)
            except Exception:
                print("<COULD NOT PRINT THIS LINE>")

        print("Scan completed.\n")


class DirectoryFrame(BinillaWidget, tk.Frame):
    app_root = None

    def __init__(self, master, *args, **kwargs):
        kwargs.setdefault('app_root', master)
        self.app_root = kwargs.pop('app_root')

        kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
        tk.Frame.__init__(self, master, *args, **kwargs)

        #self.controls_frame = tk.Frame(self, highlightthickness=0, height=100)
        self.hierarchy_frame = HierarchyFrame(self, app_root=self.app_root)

        #self.controls_frame.pack(fill='both')
        self.hierarchy_frame.pack(fill='both', expand=True)
        self.apply_style()

    def set_root_dir(self, root_dir):
        self.hierarchy_frame.set_root_dir(root_dir)

    def add_root_dir(self, root_dir):
        self.hierarchy_frame.add_root_dir(root_dir)

    def del_root_dir(self, root_dir):
        self.hierarchy_frame.del_root_dir(root_dir)

    def highlight_tags_dir(self, root_dir):
        self.hierarchy_frame.highlight_tags_dir(root_dir)

    def apply_style(self):
        #self.controls_frame.config(bg=self.default_bg_color)
        self.hierarchy_frame.apply_style()


class HierarchyFrame(BinillaWidget, tk.Frame):
    tags_dir = ''
    app_root = None
    tags_dir_items = ()

    def __init__(self, master, *args, **kwargs):
        kwargs.update(bg=self.default_bg_color, bd=self.listbox_depth,
            relief='sunken', highlightthickness=0)
        kwargs.setdefault('app_root', master)
        self.app_root = kwargs.pop('app_root')
        tk.Frame.__init__(self, master, *args, **kwargs)

        self.tags_dir = self.app_root.tags_dir
        self.tag_dirs_frame = tk.Frame(self, highlightthickness=0)

        self.tag_dirs_tree = tk.ttk.Treeview(
            self.tag_dirs_frame, selectmode='browse', padding=(0, 0))
        self.scrollbar_y = tk.Scrollbar(
            self.tag_dirs_frame, orient='vertical',
            command=self.tag_dirs_tree.yview)
        self.tag_dirs_tree.config(yscrollcommand=self.scrollbar_y.set)

        self.tag_dirs_tree.bind('<<TreeviewOpen>>', self.open_selected)
        self.tag_dirs_tree.bind('<<TreeviewClose>>', self.close_selected)
        self.tag_dirs_tree.bind('<Double-Button-1>', self.activate_item)
        self.tag_dirs_tree.bind('<Return>', self.activate_item)

        self.tag_dirs_frame.pack(fill='both', side='left', expand=True)

        self.tag_dirs_tree.pack(side='left', fill='both', expand=True)
        self.scrollbar_y.pack(side='right', fill='y')

        self.reload()
        self.apply_style()

    def apply_style(self):
        self.tag_dirs_frame.config(bg=self.default_bg_color)

        dir_tree = self.tag_dirs_tree
        dir_tree.tag_configure(
            'item', background=self.entry_normal_color,
            foreground=self.text_normal_color)
        self.highlight_tags_dir()

    def reload(self):
        dir_tree = self.tag_dirs_tree
        dir_tree['columns'] = ('size', )
        dir_tree.heading("#0", text='path')
        dir_tree.heading("size", text='filesize')
        dir_tree.column("#0", minwidth=100, width=100)
        dir_tree.column("size", minwidth=100, width=100, stretch=False)

        for tags_dir in self.tags_dir_items:
            dir_tree.delete(tags_dir)

        self.tags_dir_items = []

        for tags_dir in self.app_root.tags_dirs:
            self.add_root_dir(tags_dir)

    def set_root_dir(self, root_dir):
        dir_tree = self.tag_dirs_tree
        curr_root_dir = self.app_root.tags_dir

        tags_dir_index = dir_tree.index(curr_root_dir)
        dir_tree.delete(curr_root_dir)
        self.insert_root_dir(root_dir)

    def add_root_dir(self, root_dir):
        self.insert_root_dir(root_dir)

    def insert_root_dir(self, root_dir, index='end'):
        iid = self.tag_dirs_tree.insert(
            '', index, iid=root_dir, text=root_dir[:-1],
            tags=(root_dir, 'tagdir'))
        self.tags_dir_items.append(iid)
        self.destroy_subitems(iid)

    def del_root_dir(self, root_dir):
        self.tag_dirs_tree.delete(root_dir)

    def destroy_subitems(self, directory):
        '''
        Destroys all the given items subitems and creates an empty
        subitem so as to give the item the appearance of being expandable.
        '''
        dir_tree = self.tag_dirs_tree

        for child in dir_tree.get_children(directory):
            dir_tree.delete(child)

        # add an empty node to make an "expand" button appear
        dir_tree.insert(directory, 'end')

    def generate_subitems(self, directory):
        dir_tree = self.tag_dirs_tree

        for root, subdirs, files in os.walk(directory):
            for subdir in sorted(subdirs):
                folderpath = directory + subdir + PATHDIV
                dir_tree.insert(
                    directory, 'end', text=subdir,
                    iid=folderpath, tags=('item',))

                # loop over each of the new items, give them
                # at least one item so they can be expanded.
                self.destroy_subitems(folderpath)
            for file in sorted(files):
                try:
                    filesize = os.stat(directory + file).st_size
                    if filesize < 1024:
                        filesize = str(filesize) + " bytes"
                    elif filesize < 1024**2:
                        filesize = str(round(filesize/1024, 3)) + " Kb"
                    else:
                        filesize = str(round(filesize/(1024**2), 3)) + " Mb"
                except Exception:
                    filesize = 'COULDNT CALCULATE'
                dir_tree.insert(directory, 'end', text=file,
                                iid=directory + file, tags=('item',),
                values=(filesize, ))

            # just do the toplevel of the hierarchy
            break

    def get_item_tags_dir(self, iid):
        '''Returns the tags directory of the given item'''
        dir_tree = self.tag_dirs_tree
        prev_parent = iid
        parent = dir_tree.parent(prev_parent)
        
        while parent:
            prev_parent = parent
            parent = dir_tree.parent(prev_parent)

        return prev_parent

    def open_selected(self, e=None):
        dir_tree = self.tag_dirs_tree
        tag_path = dir_tree.focus()
        for child in dir_tree.get_children(tag_path):
            dir_tree.delete(child)

        if tag_path:
            self.generate_subitems(tag_path)

    def close_selected(self, e=None):
        dir_tree = self.tag_dirs_tree
        tag_path = dir_tree.focus()
        if tag_path is None:
            return

        if isdir(tag_path):
            self.destroy_subitems(tag_path)

    def highlight_tags_dir(self, tags_dir=None):
        app = self.app_root
        dir_tree = self.tag_dirs_tree
        if tags_dir is None:
              tags_dir = self.app_root.tags_dir
        for td in app.tags_dirs:
            if td == tags_dir:
                dir_tree.tag_configure(
                    td, background=self.entry_highlighted_color,
                    foreground=self.text_highlighted_color)
            else:
                dir_tree.tag_configure(
                    td, background=self.entry_normal_color,
                    foreground=self.text_normal_color)

    def activate_item(self, e=None):
        dir_tree = self.tag_dirs_tree
        tag_path = dir_tree.focus()
        if tag_path is None:
            return

        try:
            app = self.app_root
            tags_dir = self.get_item_tags_dir(tag_path)
            self.highlight_tags_dir(tags_dir)
            app.switch_tags_dir(index=app.tags_dirs.index(tags_dir))
        except Exception:
            print(format_exc())

        if isdir(tag_path):
            return

        try:
            app.load_tags(filepaths=tag_path)
        except Exception:
            print(format_exc())


class DependencyFrame(HierarchyFrame):
    root_tag_path = ''
    root_tag_text = None
    _initialized = False
    handler = None

    def __init__(self, master, *args, **kwargs):
        HierarchyFrame.__init__(self, master, *args, **kwargs)
        self.handler = self.app_root.handler
        self._initialized = True

    def apply_style(self):
        HierarchyFrame.apply_style(self)
        self.tag_dirs_tree.tag_configure(
            'badref', foreground=self.invalid_path_color,
            background=self.entry_normal_color)

    def get_item_tags_dir(*args, **kwargs): pass

    def highlight_tags_dir(*args, **kwargs): pass

    def reload(self):
        dir_tree = self.tag_dirs_tree
        dir_tree["columns"]=("dependency")
        dir_tree.heading("#0", text='Filepath')
        dir_tree.heading("dependency", text='Dependency path')

        if not self._initialized:
            return

        for item in dir_tree.get_children():
            try: dir_tree.delete(item)
            except Exception: pass

        root = self.root_tag_path
        text = self.root_tag_text
        if text is None:
            text = root

        iid = self.tag_dirs_tree.insert(
            '', 'end', iid=self.root_tag_path, text=text,
            tags=(root, 'item'), values=('', root))
        self.destroy_subitems(iid)

    def get_dependencies(self, tag_path):
        tag = self.master.get_tag(tag_path)
        if tag is None:
            print(("Unable to load '%s'.\n" % tag_path) +
                  "    You may need to change the tag set to load this tag.")
            return ()
        handler = self.handler
        d_id = tag.def_id
        dependency_cache = handler.tag_ref_cache.get(d_id)

        if not dependency_cache:
            return ()

        dependencies = []

        for block in handler.get_nodes_by_paths(dependency_cache, tag.data):
            # if the node's filepath is empty, just skip it
            if not block.filepath:
                continue
            dependencies.append(block)
        return dependencies

    def destroy_subitems(self, iid):
        '''
        Destroys all the given items subitems and creates an empty
        subitem so as to give the item the appearance of being expandable.
        '''
        dir_tree = self.tag_dirs_tree

        for child in dir_tree.get_children(iid):
            dir_tree.delete(child)

        # add an empty node to make an "expand" button appear
        tag_path = dir_tree.item(iid)['values'][-1]
        if not exists(tag_path):
            dir_tree.item(iid, tags=('badref', ))
        elif self.get_dependencies(tag_path):
            dir_tree.insert(iid, 'end')

    def close_selected(self, e=None):
        dir_tree = self.tag_dirs_tree
        iid = dir_tree.focus()
        if iid:
            self.destroy_subitems(iid)

    def generate_subitems(self, parent_iid):
        tags_dir = self.tags_dir
        dir_tree = self.tag_dirs_tree
        parent_tag_path = dir_tree.item(parent_iid)['values'][-1]

        if not exists(parent_tag_path):
            return

        for tag_ref_block in self.get_dependencies(parent_tag_path):
            try:
                ext = '.' + tag_ref_block.tag_class.enum_name
                if (self.handler.treat_mode_as_mod2 and (
                    ext == '.model' and not exists(
                        tags_dir + tag_ref_block.filepath + ext))):
                    ext = '.gbxmodel'
            except Exception:
                ext = ''
            tag_path = tag_ref_block.filepath + ext

            dependency_name = tag_ref_block.NAME
            last_block = tag_ref_block
            parent = last_block.parent
            while parent is not None and hasattr(parent, 'NAME'):
                name = parent.NAME
                f_type = parent.TYPE
                if f_type.is_array:
                    index = parent.index(last_block)
                    dependency_name = '[%s].%s' % (index, dependency_name)
                elif name not in ('tagdata', 'data'):
                    if not last_block.TYPE.is_array:
                        name += '.'
                    dependency_name = name + dependency_name
                last_block = parent
                parent = last_block.parent

            # slice off the extension and the period
            dependency_name = dependency_name.split('.', 1)[-1]

            iid = dir_tree.insert(
                parent_iid, 'end', text=tag_path, tags=('item',),
                values=(dependency_name, tags_dir + tag_path))

            self.destroy_subitems(iid)

    def activate_item(self, e=None):
        dir_tree = self.tag_dirs_tree
        active = dir_tree.focus()
        if active is None:
            return
        tag_path = dir_tree.item(active)['values'][-1]

        try:
            app = self.app_root
            tags_dir = self.get_item_tags_dir(tag_path)
            self.highlight_tags_dir(tags_dir)
        except Exception:
            print(format_exc())

        if isdir(tag_path):
            return

        try:
            app.load_tags(filepaths=tag_path)
        except Exception:
            print(format_exc())


class SearchAndReplaceWindow(BinillaWidget, tk.Toplevel):

    def __init__(self, app_root, *args, **kwargs):
        self.app_root = app_root
        kwargs.update(width=450, height=270, bd=0, highlightthickness=0)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)

        self.title("Search and Replace(beta)")
        self.minsize(width=450, height=270)
        self.resizable(1, 0)

        # make the tkinter variables
        self.find_var = tk.StringVar(self)
        self.replace_var = tk.StringVar(self)

        # make the frames
        self.comment_frame = tk.Frame(
            self, relief='sunken', bd=self.comment_depth,
            bg=self.comment_bg_color)
        self.find_frame = tk.LabelFrame(self, text="Find this")
        self.replace_frame = tk.LabelFrame(self, text="Replace with this")

        self.search_button = tk.Button(
            self, text='Count occurrances', width=20, command=self.search)
        self.replace_button = tk.Button(
            self, text='Replace occurrances', width=20, command=self.replace)

        self.find_entry = tk.Entry(
            self.find_frame, textvariable=self.find_var)
        self.replace_entry = tk.Entry(
            self.replace_frame, textvariable=self.replace_var)
        self.comment = tk.Label(
            self.comment_frame, anchor='nw', bg=self.comment_bg_color,
            justify='left', font=self.app_root.comment_font,
            text="""Things to note:
  Only strings can be found/replaced. If you type in a number,
  a string consisting of that number will be searched/replaced.

  If the replacement is too long to use, you will be alerted.

  You cannot undo/redo these replacements, so be careful.""")

        self.comment.pack(side='left', fill='both', expand=True)
        self.comment_frame.pack(fill='both', expand=True)

        self.find_frame.pack(fill="x", expand=True, padx=5)
        self.find_entry.pack(fill="x", expand=True, padx=5, pady=2)
        self.search_button.pack(fill="x", anchor='center', padx=5, pady=(0,4))

        self.replace_frame.pack(fill="x", expand=True, padx=5)
        self.replace_entry.pack(fill="x", expand=True, padx=5, pady=2)
        self.replace_button.pack(fill="x", anchor='center', padx=5, pady=(0,4))

        self.apply_style()
        self.transient(app_root)

    def apply_style(self):
        self.config(bg=self.default_bg_color)
        for w in (self.find_frame, self.replace_frame):
            w.config(fg=self.text_normal_color, bg=self.default_bg_color)

        for w in (self.search_button, self.replace_button):
            w.config(bg=self.button_color, activebackground=self.button_color,
                     fg=self.text_normal_color, bd=self.button_depth,
                     disabledforeground=self.text_disabled_color)

        for w in (self.find_entry, self.replace_entry):
            w.config(bd=self.entry_depth,
                bg=self.entry_normal_color, fg=self.text_normal_color,
                disabledbackground=self.entry_disabled_color,
                disabledforeground=self.text_disabled_color,
                selectbackground=self.entry_highlighted_color,
                selectforeground=self.text_highlighted_color)

    def destroy(self):
        self.app_root.tool_windows.pop("s_and_r_window", None)
        tk.Toplevel.destroy(self)

    def search(self, e=None):
        self.search_and_replace()

    def replace(self, e=None):
        self.search_and_replace(True)

    def search_and_replace(self, replace=False):
        app_root = self.app_root
        try:
            window = app_root.get_tag_window_by_tag(app_root.selected_tag)
        except Exception:
            window = None

        if window is None:
            return

        find = self.find_var.get()
        replace = self.replace_var.get()

        f_widgets = window.field_widget.f_widgets.values()
        nodes = window.tag.data
        occurances = 0

        while nodes:
            new_nodes = []
            for node in nodes:
                if not isinstance(node, list):
                    continue

                attrs = range(len(node))
                if hasattr(node, 'STEPTREE'):
                    attrs = tuple(attrs) + ('STEPTREE',)
                for i in attrs:
                    val = node[i]
                    if not isinstance(val, str) or find != val:
                        continue

                    if not replace:
                        occurances += 1
                        continue

                    desc = node.get_desc(i)
                    f_type = desc['TYPE']

                    field_max = desc.get('MAX', f_type.max)
                    if field_max is None:
                        field_max = desc.get('SIZE')
                    if f_type.sizecalc(replace) > field_max:
                        print("String replacement must be less than " +
                               "%s bytes when encoded, not %s." % (
                                   field_max, f_type.sizecalc(replace)))
                        continue

                    occurances += 1
                    node[i] = replace
                try:
                    if isinstance(node, list):
                        new_nodes.extend(node)
                    if hasattr(node, 'STEPTREE'):
                        new_nodes.append(node.STEPTREE)
                except Exception:
                    pass

            nodes = new_nodes

        if not replace:
            print('Found %s occurances' % occurances)
            return

        while f_widgets:
            new_f_widgets = []
            for w in f_widgets:
                try: new_f_widgets.extend(w.f_widgets.values())
                except Exception: pass

                if not hasattr(w, 'entry_string'):
                    continue

                try:
                    desc = w.desc
                    f_type = desc['TYPE']

                    # dont want to run this unless the nodes type is a string
                    if not isinstance(f_type.node_cls, str):
                        continue

                    field_max = w.field_max
                    if field_max is None:
                        field_max = desc.get('SIZE')

                    if f_type.sizecalc(replace) > field_max:
                        #print("Replacement string too long to fit.")
                        continue
                except AttributeError:
                    continue

                e_str = w.entry_string
                if find == e_str.get():
                    e_str.set(replace)

            f_widgets = new_f_widgets

        print('Found and replaced %s occurances' % occurances)


class TagExtractorWindow(BinillaWidget, tk.Toplevel):
    app_root = None
    map_path = None
    out_dir = None

    index_magic = None  # the magic DETECTED for this type of map
    map_magic = None  # the magic CALCULATED for this map

    _map_loaded = False
    _extracting = False


    map_data = None  # the complete uncompressed map
    map_is_compressed = False

    # these are the different pieces of the map as parsed blocks
    map_header = None
    tag_index = None

    def __init__(self, app_root, *args, **kwargs):
        self.app_root = app_root
        kwargs.update(width=520, height=450, bd=0, highlightthickness=0)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)

        self.title("Tag Extractor")
        self.minsize(width=520, height=450)

        # make the tkinter variables
        self.map_path = tk.StringVar(self)
        self.out_dir = tk.StringVar(self)
        self.use_resource_names = tk.IntVar(self)
        self.use_hashcaches = tk.IntVar(self)
        self.use_heuristics = tk.IntVar(self)
        try:
            self.out_dir.set(self.app_root.tags_dir)
        except Exception:
            pass
        self.use_resource_names.set(1)

        self.map_path.set("Click browse to load a map for extraction")

        # make the window pane
        self.panes = tk.PanedWindow(self, sashwidth=4)

        # make the frames
        self.map_frame = tk.LabelFrame(self, text="Map to extract from")
        self.map_select_frame = tk.Frame(self.map_frame)
        self.map_action_frame = tk.Frame(self.map_frame)
        self.deprotect_frame = tk.LabelFrame(self, text="Deprotection settings")
        self.out_dir_frame = tk.LabelFrame(self, text="Location to extract to")

        self.explorer_frame = tk.Frame(self.panes)
        self.add_del_frame = tk.Frame(self.explorer_frame)
        self.queue_frame = tk.Frame(self.panes)

        self.panes.add(self.explorer_frame)
        self.panes.add(self.queue_frame)

        # make the entries
        self.map_path_entry = tk.Entry(
            self.map_select_frame, textvariable=self.map_path, state='disabled')
        self.map_path_browse_button = tk.Button(
            self.map_select_frame, text="Browse",
            command=self.map_path_browse, width=6)

        self.out_dir_entry = tk.Entry(
            self.out_dir_frame, textvariable=self.out_dir, state='disabled')
        self.out_dir_browse_button = tk.Button(
            self.out_dir_frame, text="Browse",
            command=self.out_dir_browse, width=6)
        '''
        self.def_ids_scrollbar = tk.Scrollbar(
            self.def_ids_frame, orient="vertical")
        self.def_ids_listbox = tk.Listbox(
            self.def_ids_frame, selectmode='multiple', highlightthickness=0)
        self.def_ids_scrollbar.config(command=self.def_ids_listbox.yview)
        '''
        self.map_info_text = tk.Text(
            self.map_frame, font=self.app_root.fixed_font,
            state='disabled', height=8)

        # make the buttons
        self.begin_button = tk.Button(
            self.map_action_frame, text="Begin extraction",
            command=self.begin_extraction)
        self.cancel_button = tk.Button(
            self.map_action_frame, text="Cancel extraction",
            command=self.cancel_extraction)

        self.use_resource_names_checkbutton = tk.Checkbutton(
            self.deprotect_frame, text="Use resource names",
            variable=self.use_resource_names)
        self.use_hashcaches_checkbutton = tk.Checkbutton(
            self.deprotect_frame, text="Use hashcaches",
            variable=self.use_hashcaches)
        self.use_heuristics_checkbutton = tk.Checkbutton(
            self.deprotect_frame, text="Use heuristics",
            variable=self.use_heuristics)
        self.deprotect_button = tk.Button(
            self.deprotect_frame, text="Deprotect names",
            command=self.deprotect_names)

        self.add_button = tk.Button(self.add_del_frame, text="Add", width=4,
                                    command=self.queue_add)
        self.del_button = tk.Button(self.add_del_frame, text="Del", width=4,
                                    command=self.queue_del)

        self.add_all_button = tk.Button(
            self.add_del_frame, text="Add\nAll", width=4,
            command=self.queue_add_all)
        self.del_all_button = tk.Button(
            self.add_del_frame, text="Del\nAll", width=4,
            command=self.queue_del_all)

        # pack everything
        self.map_path_entry.pack(
            padx=(4, 0), pady=2, side='left', expand=True, fill='x')
        self.map_path_browse_button.pack(padx=(0, 4), pady=2, side='left')

        self.cancel_button.pack(side='right', padx=4, pady=4)
        self.begin_button.pack(side='right', padx=4, pady=4)

        self.use_resource_names_checkbutton.pack(side='left', padx=4, pady=4)
        self.use_hashcaches_checkbutton.pack(side='left', padx=4, pady=4)
        self.use_heuristics_checkbutton.pack(side='left', padx=4, pady=4)
        self.deprotect_button.pack(side='right', padx=4, pady=4)

        self.map_select_frame.pack(fill='x', expand=True, padx=1)
        self.map_info_text.pack(fill='x', expand=True, padx=1)
        self.map_action_frame.pack(fill='x', expand=True, padx=1)

        self.out_dir_entry.pack(
            padx=(4, 0), pady=2, side='left', expand=True, fill='x')
        self.out_dir_browse_button.pack(padx=(0, 4), pady=2, side='left')

        self.add_button.pack(side='top', padx=2, pady=4)
        self.del_button.pack(side='top', padx=2, pady=(0, 20))
        self.add_all_button.pack(side='top', padx=2, pady=(20, 0))
        self.del_all_button.pack(side='top', padx=2, pady=4)

        self.explorer_frame.pack(fill='both', padx=1, expand=True)
        self.add_del_frame.pack(side='right', anchor='center')
        self.queue_frame.pack(fill='y', padx=1, expand=True)

        self.map_frame.pack(fill='x', padx=1)
        self.out_dir_frame.pack(fill='x', padx=1)
        self.deprotect_frame.pack(fill='x', padx=1)
        self.panes.pack(fill='both', expand=True)

        self.panes.paneconfig(self.explorer_frame, sticky='nsew')
        self.panes.paneconfig(self.queue_frame, sticky='nsew')

        self.apply_style()
        self.transient(app_root)

    def destroy(self):
        self.app_root.tool_windows.pop("tag_extractor_window", None)
        tk.Toplevel.destroy(self)

    def queue_add(self, e=None):
        if not self._map_loaded:
            return

    def queue_del(self, e=None):
        if not self._map_loaded:
            return

    def queue_add_all(self, e=None):
        if not self._map_loaded:
            return

    def queue_del_all(self, e=None):
        if not self._map_loaded:
            return

    def load_map(self, map_path=None):
        try:
            if map_path is None:
                map_path = self.map_path.get()
            try:
                if not exists(map_path):
                    return
            except Exception:
                return

            self.map_path.set(map_path)

            with open(map_path, 'r+b') as f:
                comp_map_data = mmap.mmap(f.fileno(), 0)

            self.map_header = get_map_header(comp_map_data)
            self.map_data = decompress_map(comp_map_data, self.map_header)
            self.map_is_compressed = len(comp_map_data) < len(self.map_data)

            self.index_magic = get_index_magic(self.map_header)
            self.map_magic = get_map_magic(self.map_header)

            self.tag_index = get_tag_index(self.map_data, self.map_header)
            self._map_loaded = True

            self.display_map_info()
            try: comp_map_data.close()
            except Exception: pass
        except Exception:
            try: comp_map_data.close()
            except Exception: pass
            self.display_map_info(
                "Could not load map.\nCheck console window for error.")
            raise

    def deprotect_names(self, e=None):
        if not self._map_loaded:
            return
        self.reload_map_explorer()

    def begin_extraction(self, e=None):
        if not self._map_loaded:
            return

    def cancel_extraction(self, e=None):
        if not self._map_loaded:
            return

    def reload_map_explorer(self, mode="hierarchy"):
        if not self._map_loaded:
            return

    def display_map_info(self, string=None):
        if not self._map_loaded:
            return
        if string is None:
            try:
                header = self.map_header
                index = self.tag_index
                comp_size = "Uncompressed"
                if self.map_is_compressed:
                    comp_size = len(self.map_data)

                string = ((
                    "Engine == %s   Map type == %s   Decompressed size == %s\n" +
                    "Map name   == '%s'\n" +
                    "Build date == '%s'\n" +
                    "Index magic  == %s   Map magic == %s\n" +
                    "Index offset == %s   Tag count == %s\n" +
                    "Index header offset  == %s   Metadata length == %s\n" +
                    "Vertex object count  == %s   Model data offset == %s\n" +
                    "Indices object count == %s   Indices offset == %s"
                    ) %
                (get_map_version(header), header.map_type.enum_name, comp_size,
                 header.map_name,
                 header.build_date,
                 self.index_magic, self.map_magic,
                 index.tag_index_offset, index.tag_count,
                 header.tag_index_header_offset, header.tag_index_meta_len,
                 index.vertex_object_count, index.model_raw_data_offset,
                 index.indices_object_count, index.indices_offset,
                 ))
            except Exception:
                string = ""
                print(format_exc())
        try:
            self.map_info_text.config(state='normal')
            self.map_info_text.delete('1.0', 'end')
            self.map_info_text.insert('end', string)
        finally:
            self.map_info_text.config(state='disabled')

    def apply_style(self):
        self.config(bg=self.default_bg_color)
        # pane style
        self.panes.config(bd=self.frame_depth, bg=self.frame_bg_color)
        self.map_info_text.config(fg=self.text_disabled_color,
                                  bg=self.entry_disabled_color)

        # frame styles
        for w in (self.map_select_frame, self.map_action_frame,
                  self.explorer_frame, self.add_del_frame, self.queue_frame):
            w.config(bg=self.default_bg_color)

        # label frame styles
        for w in (self.map_frame, self.out_dir_frame, self.deprotect_frame):
            w.config(fg=self.text_normal_color, bg=self.default_bg_color)

        # button styles
        for w in (self.use_resource_names_checkbutton,
                  self.use_hashcaches_checkbutton,
                  self.use_heuristics_checkbutton,
                  self.add_button, self.del_button,
                  self.add_all_button, self.del_all_button,
                  self.deprotect_button, self.begin_button, self.cancel_button,
                  self.map_path_browse_button, self.out_dir_browse_button):
            w.config(bg=self.button_color, activebackground=self.button_color,
                     fg=self.text_normal_color, bd=self.button_depth,
                     disabledforeground=self.text_disabled_color)

        # entry styles
        for w in (self.map_path_entry, self.out_dir_entry):
            w.config(bd=self.entry_depth,
                bg=self.entry_normal_color, fg=self.text_normal_color,
                disabledbackground=self.entry_disabled_color,
                disabledforeground=self.text_disabled_color,
                selectbackground=self.entry_highlighted_color,
                selectforeground=self.text_highlighted_color)

    def map_path_browse(self):
        fp = askopenfilename(
            initialdir=self.app_root.last_load_dir,
            title="Select map to load", parent=self,
            filetypes=(("Halo mapfile", "*.map"),
                       ("Halo mapfile(extra sauce)", "*.yelo"), ("All", "*")) )

        if not fp:
            return

        fp = sanitize_path(fp).lower()
        self.app_root.last_load_dir = dirname(fp)
        self.map_path.set(fp)
        self.load_map()

    def out_dir_browse(self):
        dirpath = askdirectory(initialdir=self.out_dir.get(), parent=self,
                               title="Select the extraction directory")

        if not dirpath:
            return

        dirpath = sanitize_path(dirpath).lower()
        if not dirpath.endswith(PATHDIV):
            dirpath += PATHDIV

        self.out_dir.set(dirpath)


class HashcacherWindow(tk.Toplevel, BinillaWidget):
    app_root = None
    tags_dir = None
    hash_name = None

    _hashing = False

    def __init__(self, app_root, *args, **kwargs):
        self.app_root = app_root
        kwargs.update(width=400, height=300, bd=0, highlightthickness=0)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)

        self.title("Hashcacher")
        self.minsize(width=400, height=300)

        self.tags_dir = tk.StringVar(self)
        self.hash_name = tk.StringVar(self)
        try:
            tags_dir = app_root.tags_dir
            if tags_dir:
                self.tags_dir.set(tags_dir)
        except Exception:
            pass

        # add the tags folder path box
        self.tags_dir_frame = tk.LabelFrame(
            self, text="Select the tags directory to hash")
        self.tags_dir_entry = tk.Entry(
            self.tags_dir_frame, textvariable=self.tags_dir)
        self.tags_dir_entry.config(width=47, state=DISABLED)

        # add the hashcache name box
        self.hash_name_frame = tk.LabelFrame(
            self, text="Enter a valid hashcache name")
        self.hash_name_entry = tk.Entry(
            self.hash_name_frame, textvariable=self.hash_name)
        self.hash_name_entry.config(width=47)

        # add the hashcache description box
        self.hash_desc_frame = tk.LabelFrame(
            self, text="Enter a hashcache description")
        self.hash_desc_text = tk.Text(self.hash_desc_frame)
        self.hash_desc_text.config(height=50, wrap='word')

        # add the buttons
        self.btn_select_tags = tk.Button(
            self.tags_dir_frame, text="Browse", width=15,
            command=self.select_tags_folder)
        self.btn_build_cache = tk.Button(
            self.hash_name_frame, text="Build hashcache",
            width=15, command=self.build_hashcache)

        # pack everything
        self.tags_dir_frame.pack(padx=4, pady=4, fill='x')
        self.hash_name_frame.pack(padx=4, pady=4, fill='x')
        self.hash_desc_frame.pack(padx=4, pady=4, fill='x')
        self.hash_desc_text.pack(padx=4, pady=4, expand=True, fill='both')

        for entry in (self.tags_dir_entry, self.hash_name_entry):
            entry.pack(side='left', padx=4, pady=2, expand=True, fill='x')

        for button in (self.btn_select_tags, self.btn_build_cache):
            button.pack(side='right', padx=4, pady=2)

        # REMOVE THESE LINES WHEN READY FOR PUBLIC USAGE
        self.hash_name.set('Halo_1_Default')
        self.hash_desc_text.insert(
            'end', 'All the tags that are used in the original Halo 1 ' +
            'singleplayer, multiplayer, and ui maps.\n' +
            'This should always be used, and as the base cache.')
        # REMOVE THESE LINES WHEN READY FOR PUBLIC USAGE

        self.apply_style()

    def destroy(self):
        self.app_root.tool_windows.pop("hashcacher_window", None)
        tk.Toplevel.destroy(self)
        self.app_root.hashcacher.stop_hashing = True

    def select_tags_folder(self):
        tags_dir = askdirectory(initialdir=self.tags_dir.get(), parent=self,
                                title="Select tags folder...")
        if tags_dir:
            tags_dir = tags_dir.replace('/','\\') + '\\'
            self.tags_dir.set(tags_dir)

    def build_hashcache(self):
        if self._hashing:
            return
        try: self.build_thread.join()
        except Exception: pass
        self.build_thread = Thread(target=self._build_hashcache)
        self.build_thread.daemon = True
        self.build_thread.start()

    def _build_hashcache(self):
        self._hashing = True
        try:
            try:
                hash_name = sanitize_filename(self.hash_name.get())
            except Exception:
                hash_name = ''

            hash_desc = self.hash_desc_text.get(1.0, 'end')
            hasher, tag_lib = self.app_root.hashcacher, self.app_root.handler
            hasher.stop_hashing = False

            if not hash_name:
                print('enter a valid hashcache name.')
            elif not hash_desc:
                print('enter a hashcache description.')
            elif not hasattr(tag_lib, 'tag_ref_cache'):
                print("Change the current tag set.")
            else:
                # set the hashcacher's tag_lib to the currently selected handler
                tag_lib.tagsdir = self.tags_dir.get()
                hasher.tag_lib = tag_lib
                hasher.build_hashcache(hash_name, hash_desc)
        except Exception:
            print(format_exc())
        self._hashing = False

    def apply_style(self):
        self.config(bg=self.default_bg_color)
        self.hash_desc_text.config(fg=self.text_normal_color,
                                   bg=self.entry_normal_color)

        # label frame styles
        for w in (self.tags_dir_frame, self.hash_name_frame,
                  self.hash_desc_frame):
            w.config(fg=self.text_normal_color, bg=self.default_bg_color)

        # button styles
        for w in (self.btn_select_tags, self.btn_build_cache):
            w.config(bg=self.button_color, activebackground=self.button_color,
                     fg=self.text_normal_color, bd=self.button_depth,
                     disabledforeground=self.text_disabled_color)

        # entry styles
        for w in (self.tags_dir_entry, self.hash_name_entry):
            w.config(bd=self.entry_depth,
                bg=self.entry_normal_color, fg=self.text_normal_color,
                disabledbackground=self.entry_disabled_color,
                disabledforeground=self.text_disabled_color,
                selectbackground=self.entry_highlighted_color,
                selectforeground=self.text_highlighted_color)
