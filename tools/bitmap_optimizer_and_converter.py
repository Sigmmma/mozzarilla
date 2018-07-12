import gc

from array import array
from copy import deepcopy
from os.path import getsize, splitext, dirname, join, exists, isfile, relpath
from threading import Thread
from tkinter.filedialog import asksaveasfilename, askdirectory
from time import sleep, time
from traceback import format_exc

from reclaimer.hek.defs.bitm import bitm_def
from reclaimer.hek.defs.objs.bitm import P8_PALETTE
from reclaimer.field_types import *

from binilla.util import *
from binilla.widgets import BinillaWidget, ScrollMenu

curr_dir = get_cwd(__file__)

"""These channel mappings are for swapping MULTIPURPOSE channels from
pc to xbox format and vice versa from 4 channel source to 4 channel target"""
#                      (A, R, G, B)
PC_ARGB_TO_XBOX_ARGB = (1, 3, 2, 0)
XBOX_ARGB_TO_PC_ARGB = (3, 0, 2, 1)

AL_COMBO_TO_AL   = (0, 0)
AL_COMBO_TO_ARGB = (0, 0, 0, 0)


BITMAP_PLATFORMS = ("PC", "XBOX")
MULTI_SWAP_OPTIONS = ("", "XBOX to PC", "PC to XBOX")
P8_MODE_OPTIONS = ("Auto", "Average")
AY8_OPTIONS = ("Alpha", "Intensity")
EXTRACT_TO_OPTIONS = ("", "DDS", "TGA", "PNG")
BITMAP_TYPES = ("2D", "3D", "Cube", "White")
BITMAP_FORMATS = ("A8", "Y8", "AY8", "A8Y8", "????", "????", "R5G6B5",
                  "????", "A1R5G5B5", "A4R4G4B4", "X8R8G8B8", "A8R8G8B8",
                  "????", "????", "DXT1", "DXT3", "DXT5", "P8 Bump")

VALID_FORMAT_ENUMS = frozenset((0, 1, 2, 3, 6, 8, 9, 10, 11, 14, 15, 16, 17))
FORMAT_OPTIONS = (
    "Unchanged",
    "A8", "Y8", "AY8", "A8Y8",
    "R5G6B5", "A1R5G5B5", "A4R4G4B4",
    "X8R8G8B8", "A8R8G8B8",
    "DXT1", "DXT3", "DXT5",
    "P8-Bump")

class ConversionFlags:
    platform = BITMAP_PLATFORMS.index("PC")
    multi_swap = MULTI_SWAP_OPTIONS.index("")
    p8_mode = P8_MODE_OPTIONS.index("Auto")
    mono_channel_to_keep = AY8_OPTIONS.index("Alpha")

    extract_to = EXTRACT_TO_OPTIONS.index("")
    downres = 0
    alpha_bias = 127
    new_format = 0

    swizzled = False
    mono_swap = False
    ck_trans = False
    mip_gen = False


class BitmapInfo:
    type = 0
    format = 0
    swizzled = False
    width = 0
    height = 0
    depth = 0
    mipmaps = 0

    def __init__(self, bitmap_block=None):
        if not bitmap_block:
            return
        self.type = bitmap_block.type.data
        self.format = bitmap_block.format.data
        self.swizzled = bitmap_block.flags.swizzled
        self.width = bitmap_block.width
        self.height = bitmap_block.height
        self.depth = bitmap_block.depth
        self.mipmaps = bitmap_block.mipmaps


class BitmapTagInfo:
    platform = 0
    pixel_data_size = 0
    tiff_data_size = 0
    bitmap_infos = ()

    def __init__(self, bitm_tag=None):
        self.bitmap_infos = []
        if not bitm_tag:
            return

        bitm_data = bitm_tag.data.tagdata
        self.tiff_data_size = bitm_data.compressed_color_plate_data.size
        self.pixel_data_size = bitm_data.processed_pixel_data.size
        for bitmap in bitm_data.bitmaps.STEPTREE:
            self.bitmap_infos.append(BitmapInfo(bitmap))

    @property
    def type(self):
        return 0 if not self.bitmap_infos else self.bitmap_infos[0].type
    @property
    def format(self):
        return 0 if not self.bitmap_infos else self.bitmap_infos[0].format
    @property
    def swizzled(self):
        return 0 if not self.bitmap_infos else self.bitmap_infos[0].swizzled


class BitmapConverterWindow(tk.Toplevel, BinillaWidget):
    app_root = None
    tag_list_frame = None
    loaded_tags_dir = ''

    prune_tiff = None
    read_only = None
    backup_tags = None
    open_log = None

    conversion_flags = ()
    bitmap_tag_infos = ()

    _processing = False
    _cancel_processing = False
    _populating_settings = False
    _populating_bitmap_info = False

    print_interval = 5

    # these cache references to the settings widgets for iteratively
    # enabling/disabling settings before and after converting.
    checkbuttons = ()
    buttons = ()
    spinboxes = ()
    entries = ()
    menus = ()

    def __init__(self, app_root, *args, **kwargs):
        self.app_root = app_root
        BinillaWidget.__init__(self, *args, **kwargs)
        kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)

        self.conversion_flags = {}
        self.bitmap_tag_infos = {}

        self.title("Bitmap converter")
        self.resizable(0, 1)
        self.update()
        try:
            try:
                self.iconbitmap(join(curr_dir, '..', 'mozzarilla.ico'))
            except Exception:
                self.iconbitmap(join(curr_dir, 'icons', 'mozzarilla.ico'))
        except Exception:
            print("Could not load window icon.")

        # make the tkinter variables
        self.prune_tiff = tk.BooleanVar(self)
        self.read_only = tk.BooleanVar(self)
        self.backup_tags = tk.BooleanVar(self)
        self.open_log = tk.BooleanVar(self, True)

        self.scan_dir_path = tk.StringVar(self)
        self.log_file_path = tk.StringVar(self)

        self.write_trace(self.read_only, lambda *a, s=self:
                         s.convert_button.config(
                             text="Make log" if s.read_only.get()
                             else "Convert"))

        # make the frames
        self.main_frame = tk.Frame(self)
        self.settings_frame = tk.LabelFrame(self.main_frame, text="Settings")
        self.bitmap_info_frame = tk.LabelFrame(self.main_frame, text="Bitmap info")
        self.buttons_frame = tk.Frame(self.main_frame)
        self.tag_list_frame = BitmapConverterList(self)

        self.scan_dir_frame = tk.LabelFrame(
            self.settings_frame, text="Directory to scan")
        self.log_file_frame  = tk.LabelFrame(
            self.settings_frame, text="Output log filepath")
        self.global_params_frame = tk.LabelFrame(
            self.settings_frame, text="Global parameters")
        self.params_frame = tk.Frame(self.settings_frame)


        self.general_params_frame = tk.LabelFrame(
            self.params_frame, text="General parameters")
        self.format_params_frame = tk.LabelFrame(
            self.params_frame, text="Format parameters")

        self.bitmap_index_frame = tk.Frame(self.bitmap_info_frame)


        self.curr_bitmap_label_0 = tk.Label(self.bitmap_index_frame, text="Current")
        self.curr_bitmap_spinbox = tk.Spinbox(self.bitmap_index_frame, width=3,
                                              state="readonly", repeatinterval=5)
        self.curr_bitmap_label_1 = tk.Label(self.bitmap_index_frame, text=" out of ")
        self.max_bitmap_entry = tk.Entry(self.bitmap_index_frame, width=3,
                                         state='disabled')

        self.curr_type_menu = ScrollMenu(self.bitmap_info_frame, menu_width=8,
                                         disabled=True, options=BITMAP_TYPES)
        self.curr_format_menu = ScrollMenu(self.bitmap_info_frame, menu_width=8,
                                           disabled=True, options=BITMAP_FORMATS)
        self.curr_platform_menu = ScrollMenu(self.bitmap_info_frame, menu_width=8,
                                             disabled=True, options=BITMAP_PLATFORMS)
        self.curr_swizzled_menu = ScrollMenu(self.bitmap_info_frame, menu_width=8,
                                             options=("No", "Yes"), disabled=True)
        self.curr_height_entry = tk.Entry(self.bitmap_info_frame, width=12,
                                          state='disabled')
        self.curr_width_entry = tk.Entry(self.bitmap_info_frame, width=12,
                                         state='disabled')
        self.curr_depth_entry = tk.Entry(self.bitmap_info_frame, width=12,
                                         state='disabled')
        self.curr_mip_entry = tk.Entry(self.bitmap_info_frame, width=12,
                                       state='disabled')


        self.scan_dir_entry = tk.Entry(
            self.scan_dir_frame, textvariable=self.scan_dir_path)
        self.scan_dir_browse_button = tk.Button(
            self.scan_dir_frame, text="Browse", command=self.dir_browse)

        self.log_file_entry = tk.Entry(
            self.log_file_frame, textvariable=self.log_file_path)
        self.log_file_browse_button = tk.Button(
            self.log_file_frame, text="Browse", command=self.log_browse)


        self.prune_tiff_cbutton = tk.Checkbutton(
            self.global_params_frame, text="Prune tiff data �",
            variable=self.prune_tiff)
        self.read_only_cbutton = tk.Checkbutton(
            self.global_params_frame, text="Read-only �",
            variable=self.read_only)
        self.backup_tags_cbutton = tk.Checkbutton(
            self.global_params_frame, text="Backup tags �",
            variable=self.backup_tags)
        self.open_log_cbutton = tk.Checkbutton(
            self.global_params_frame, text="Open log when done �",
            variable=self.open_log)

        self.prune_tiff_cbutton.tooltip_string = (
            "Prunes the uncompressed TIFF pixel data\n"
            "from all bitmaps to reduce their filesize.")
        self.read_only_cbutton.tooltip_string = (
            "Does no conversion, and instead writes a\n"
            "log detailing all bitmaps in the directory.")
        self.backup_tags_cbutton.tooltip_string = (
            "Backs up all bitmaps before editing\n"
            "(does nothing if a backup already exists)")
        self.open_log_cbutton.tooltip_string = (
            "Open the conversion log when finished.")


        self.platform_menu = ScrollMenu(self.general_params_frame, menu_width=12,
                                        options=BITMAP_PLATFORMS)
        self.format_menu = ScrollMenu(self.general_params_frame, menu_width=12,
                                      options=FORMAT_OPTIONS)
        self.extract_to_menu = ScrollMenu(self.general_params_frame, menu_width=12,
                                          options=EXTRACT_TO_OPTIONS)
        self.multi_swap_menu = ScrollMenu(self.general_params_frame, menu_width=12,
                                          options=MULTI_SWAP_OPTIONS)
        self.generate_mips_menu = ScrollMenu(self.general_params_frame, menu_width=12,
                                             options=("No", "Yes"))
        self.downres_box = tk.Spinbox(self.general_params_frame, from_=0,
                                      to=12, width=4, state="readonly")

        self.platform_menu.tooltip_string = (
            "The platform to make the tag usable on.")
        self.format_menu.tooltip_string = (
            "The format to convert the bitmap to.")
        self.extract_to_menu.tooltip_string = (
            "The image format to extract the bitmap to.")
        self.multi_swap_menu.tooltip_string = (
            "When converting multipurpose bitmaps to/from\n"
            "Xbox/PC, use this to swap the their color\n"
            "channels so they work on the other platform.")
        self.generate_mips_menu.tooltip_string = (
            "Whether or not to generate all necessary mipmaps.")
        self.downres_box.tooltip_string = (
            "Number of times to cut the bitmaps\n"
            "width, height, and depth in half.")

        self.p8_mode_menu = ScrollMenu(self.format_params_frame, menu_width=10,
                                       options=P8_MODE_OPTIONS)
        self.ay8_channel_src_menu = ScrollMenu(self.format_params_frame, menu_width=10,
                                               options=AY8_OPTIONS)
        self.ck_transparency_menu = ScrollMenu(self.format_params_frame, menu_width=10,
                                               options=("No", "Yes"))
        self.swap_a8y8_menu = ScrollMenu(self.format_params_frame, menu_width=10,
                                         options=("No", "Yes"))
        self.swizzled_menu = ScrollMenu(self.format_params_frame, menu_width=10,
                                        options=("No", "Yes"))
        self.alpha_bias_box = tk.Spinbox(self.format_params_frame, from_=0,
                                         to=255, width=5, state="readonly",
                                         repeatinterval=10)

        self.p8_mode_menu.tooltip_string = (
            "The method used for picking P8-bump normals.\n"
            "Auto emphasizes preserving shadow depth.\n"
            "Average emphasizes preserving smoothness.")
        self.ay8_channel_src_menu.tooltip_string = (
            "HUD meters converted to/from Xbox A8Y8 need to\n"
            "have their intensity and alpha channels swapped.\n"
            "Setting this will swap them when going to/from A8Y8.")
        self.ck_transparency_menu.tooltip_string = (
            "Whether to use color-key transparency when converting\n"
            "to P8-bump or DXT1. These formats support transparency\n"
            "where transparent pixels are also solid black in color.")
        self.swap_a8y8_menu.tooltip_string = (
            "Whether or not to swap the alpha and intensity\n"
            "channels when converting to or from A8Y8.")
        self.swizzled_menu.tooltip_string = (
            "Whether or not to swizzle the bitmap pixels.\n"
            "This does nothing to DXT1/3/5 bitmaps.\n"
            "Xbox bitmaps MUST be swizzled to work.")
        self.alpha_bias_box.tooltip_string = (
            "When converting to DXT1 with transparency, P8-bump,\n"
            "or A1R5G5B5, alpha values below this are rounded to\n"
            "black, while values at or above it round to white.")


        self.scan_button = tk.Button(self.buttons_frame, text="Scan directory",
                                     command=self.scan_pressed)
        self.convert_button = tk.Button(self.buttons_frame, text="Convert",
                                        command=self.convert_pressed)
        self.cancel_button = tk.Button(self.buttons_frame, text="Cancel",
                                       command=self.cancel_pressed)


        self.main_frame.pack(fill='both')
        self.tag_list_frame.pack(expand=True, fill='both')

        self.settings_frame.grid(sticky='news', row=0, column=0)
        self.bitmap_info_frame.grid(sticky='news', row=0, column=1)
        self.buttons_frame.grid(sticky='news', columnspan=2,
                                row=1, column=0, pady=3, padx=3)


        self.scan_button.pack(side='left', expand=True, fill='both', padx=3)
        self.convert_button.pack(side='left', expand=True, fill='both', padx=3)
        self.cancel_button.pack(side='left', expand=True, fill='both', padx=3)

        self.log_file_frame.pack(expand=True, fill='x')
        self.scan_dir_frame.pack(expand=True, fill='x')
        self.global_params_frame.pack(expand=True, fill='x')
        self.params_frame.pack(expand=True, fill='x')

        self.general_params_frame.pack(side='left', expand=True, fill='both')
        self.format_params_frame.pack(side='left', expand=True, fill='both')

        self.scan_dir_entry.pack(side='left', expand=True, fill='x')
        self.scan_dir_browse_button.pack(side='left')

        self.log_file_entry.pack(side='left', expand=True, fill='x')
        self.log_file_browse_button.pack(side='left')


        self.read_only_cbutton.grid(row=0, column=0, sticky='w')
        self.backup_tags_cbutton.grid(row=0, column=1, sticky='w')
        self.open_log_cbutton.grid(row=0, column=2, sticky='w')
        self.prune_tiff_cbutton.grid(row=0, column=3, sticky='w')

        i = 0
        widgets = (self.platform_menu, self.format_menu, self.extract_to_menu,
                   self.multi_swap_menu, self.generate_mips_menu, self.downres_box)
        for name in ("Platform", "Format", "Extract to",
                     "Multi. swap", "Generate mipmaps", "Downres. level"):
            w = widgets[i]
            lbl = tk.Label(self.general_params_frame, text=name)
            lbl.grid(row=i, column=0, sticky='w')
            w.grid(row=i, column=1, sticky='e')
            try:
                if w.tooltip_string:
                    lbl.tooltip_string = w.tooltip_string
                    lbl.config(text=lbl.config()["text"][-1] + " �")
            except AttributeError:
                pass
            i += 1

        i = 0
        widgets = (self.p8_mode_menu, self.ay8_channel_src_menu, self.ck_transparency_menu,
                   self.swap_a8y8_menu, self.swizzled_menu, self.alpha_bias_box)
        for name in ("P8 mode", "AY8 channel source", "Use CK transparency",
                     "Swap A8Y8", "Swizzled", "Alpha bias"):
            w = widgets[i]
            lbl = tk.Label(self.format_params_frame, text=name)
            lbl.grid(row=i, column=0, sticky='w')
            w.grid(row=i, column=1, sticky='e')
            try:
                if w.tooltip_string:
                    lbl.tooltip_string = w.tooltip_string
                    lbl.config(text=lbl.config()["text"][-1] + " �")
            except AttributeError:
                pass
            i += 1


        self.curr_bitmap_label_0.pack(side='left', fill='x')
        self.curr_bitmap_spinbox.pack(side='left', fill='x', expand=True)
        self.curr_bitmap_label_1.pack(side='left', fill='x')
        self.max_bitmap_entry.pack(side='left', fill='x', expand=True)

        self.bitmap_index_frame.grid(row=0, column=0, sticky='we',
                                     columnspan=2, pady=(10, 20))
        i = 1
        widgets = (self.curr_type_menu, self.curr_format_menu,
                   self.curr_platform_menu, self.curr_swizzled_menu,
                   self.curr_width_entry, self.curr_height_entry,
                   self.curr_depth_entry, self.curr_mip_entry)
        for name in ("Type", "Format", "Platform", "Swizzled",
                     "Width", "Height", "Depth", "Mipmaps"):
            w = widgets[i - 1]
            lbl = tk.Label(self.bitmap_info_frame, text=name)
            lbl.grid(row=i, column=0, sticky='w', pady=4)
            w.grid(row=i, column=1, sticky='e')
            try:
                if w.tooltip_string:
                    lbl.tooltip_string = w.tooltip_string
                    lbl.config(text=lbl.config()["text"][-1] + " �")
            except AttributeError:
                pass
            i += 1

        widgets = self.children.values()
        while widgets:
            next_widgets = []
            for w in widgets:
                try:
                    if isinstance(w, ScrollMenu):
                        s = w.tooltip_string
                        w.sel_label.tooltip_string = s
                        w.button_frame.tooltip_string = s
                        w.arrow_button.tooltip_string = s
                    else:
                        next_widgets.extend(w.children.values())
                except Exception:
                    print(format_exc())
                    pass
            widgets = next_widgets

        self.buttons = (self.scan_dir_browse_button, self.scan_button,
                        self.log_file_browse_button, self.convert_button,
                        self.cancel_button)
        self.checkbuttons = (self.prune_tiff_cbutton, self.read_only_cbutton,
                             self.backup_tags_cbutton, self.open_log_cbutton)
        self.spinboxes = (self.downres_box, self.alpha_bias_box)
        self.entries = (self.scan_dir_entry, self.log_file_entry)
        self.menus = (self.platform_menu, self.format_menu,
                      self.extract_to_menu, self.multi_swap_menu,
                      self.generate_mips_menu, self.p8_mode_menu,
                      self.ay8_channel_src_menu, self.ck_transparency_menu,
                      self.swap_a8y8_menu, self.swizzled_menu)

        self.apply_style()
        self.populate_bitmap_info()
        self.populate_settings()

    def destroy(self):
        try:
            self.app_root.tool_windows.pop(self.window_name, None)
        except AttributeError:
            pass
        tk.Toplevel.destroy(self)

    def apply_style(self, seen=None):
        BinillaWidget.apply_style(self, seen)
        self.update()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        self.geometry("%sx%s" % (w, h))
        self.minsize(width=w, height=h)

    def initialize_conversion_flags(self):
        self.conversion_flags = {}
        for fp, info in self.bitmap_tag_infos.items():
            if not info:
                continue

            self.conversion_flags[fp] = flags = ConversionFlags()

            flags.platform = info.platform
            flags.swizzled = info.swizzled

    def scan_pressed(self):
        if self._processing:
            return

        new_tags_dir = self.scan_dir_path.get()
        if not exists(new_tags_dir):
            print("The specified directory to scan does not exist.")
            return

        self.conversion_flags = {}
        self.bitmap_tag_infos = {}
        self.loaded_tags_dir = new_tags_dir

        try: self.scan_thread.join()
        except Exception: pass
        self.disable_settings()
        self.scan_thread = Thread(target=self._scan)
        self.scan_thread.daemon = True
        self.scan_thread.start()

    def _scan(self):
        self._processing = True
        try:
            print("Locating bitmaps...")
            self.initialize_conversion_flags()
            
            s_time = time()
            c_time = s_time
            p_int = self.print_interval

            scan_dir = self.loaded_tags_dir
            for root, _, files in os.walk(scan_dir):
                if not root.endswith(PATHDIV):
                    root += PATHDIV

                rel_root = relpath(root, scan_dir)

                for filename in files:
                    if splitext(filename)[-1].lower() != ".bitmap":
                        continue

                    fp = join(sanitize_path(rel_root), filename)

                    if time() - c_time > p_int:
                        c_time = time()
                        print(' '*4 + fp)
                        if self.app_root:
                            self.app_root.update_idletasks()

                    if self._cancel_processing:
                        print('Bitmap scanning cancelled.\n')
                        self.after(0, self.enable_settings)
                        return

                    bitm_tag = bitm_def.build(filepath=join(root, filename))
                    if not bitm_tag:
                        print("Could not load: %s" % join(root, filename))
                        continue

                    self.conversion_flags[fp] = ConversionFlags()
                    self.bitmap_tag_infos[fp] = BitmapTagInfo(bitm_tag)

            print("Finished in %s seconds." % int(time() - s_time))
        except Exception:
            print(format_exc())

        self.tag_list_frame.build_tag_sort_mappings()
        self.tag_list_frame.display_sorted_tags()
        self.after(0, self.populate_bitmap_info)
        self.after(0, self.populate_settings)
        self.after(0, self.enable_settings)
        self._processing = False

    def convert_pressed(self):
        if self._processing or not self.bitmap_tag_infos:
            return

        try: self.convert_thread.join()
        except Exception: pass
        self.disable_settings()
        self.convert_thread = Thread(target=self._convert)
        self.convert_thread.daemon = True
        self.convert_thread.start()

    def _convert(self):
        self._processing = True
        try:
            pass
        except Exception:
            print(format_exc())

        self.after(0, self.enable_settings)
        self._processing = False

    def cancel_pressed(self):
        if self._processing:
            self._cancel_processing = True

    def enable_settings(self):
        self._enable_disable_settings(False)

    def disable_settings(self):
        self._enable_disable_settings(True)

    def _enable_disable_settings(self, disable):
        new_state = tk.DISABLED if disable else tk.NORMAL
        for w in self.checkbuttons + self.buttons + self.entries:
            w.config(state=new_state)

        if not disable:
            new_state = "readonly"

        for w in self.spinboxes:
            w.config(state=new_state)

        for w in self.menus:
            if disable:
                w.disable()
            else:
                w.enable()

    def populate_settings(self):
        if self._populating_settings:
            return

        self._populating_settings = True
        try:
            for w in (self.platform_menu, self.format_menu,
                      self.multi_swap_menu, self.extract_to_menu,
                      self.generate_mips_menu, self.p8_mode_menu,
                      self.ay8_channel_src_menu, self.ck_transparency_menu,
                      self.swap_a8y8_menu, self.swizzled_menu):
                w.sel_index = -1

            for w in (self.downres_box, self.alpha_bias_box):
                w.delete(0, tk.END)

            conv_flags = self.conversion_flags
            tag_paths = self.tag_list_frame.selected_paths
            comb_flags = None
            for tag_path in tag_paths:
                comb_flags = deepcopy(conv_flags.get(tag_path))
                break

            if not comb_flags:
                comb_flags = ConversionFlags()
                print("Could not locate conversion settings for this/these tags.")

            for fp in tag_paths:
                flags = conv_flags.get(fp)
                if not flags:
                    continue

                for name in ("platform", "multi_swap", "p8_mode",
                             "mono_channel_to_keep", "extract_to", "new_format",
                             "swizzled", "mono_swap", "ck_trans", "mip_gen"):
                    if getattr(flags, name) != getattr(comb_flags, name):
                        setattr(comb_flags, name, -1)

            self.platform_menu.sel_index = comb_flags.platform
            self.multi_swap_menu.sel_index = comb_flags.multi_swap
            self.p8_mode_menu.sel_index = comb_flags.p8_mode
            self.ay8_channel_src_menu.sel_index = comb_flags.mono_channel_to_keep
            self.extract_to_menu.sel_index = comb_flags.extract_to
            self.format_menu.sel_index = comb_flags.new_format
            self.swizzled_menu.sel_index = comb_flags.swizzled
            self.swap_a8y8_menu.sel_index = comb_flags.mono_swap
            self.ck_transparency_menu.sel_index = comb_flags.ck_trans
            self.generate_mips_menu.sel_index = comb_flags.mip_gen

            self.downres_box.delete(0, tk.END)
            self.alpha_bias_box.delete(0, tk.END)
            self.downres_box.insert(0, comb_flags.downres)
            self.downres_box.insert(0, comb_flags.alpha_bias)
        except Exception:
            print(format_exc())
        self._populating_settings = False

    def populate_bitmap_info(self):
        if self._populating_bitmap_info:
            return

        self._populating_bitmap_info = True
        try:
            for w in (self.curr_width_entry, self.curr_height_entry,
                      self.curr_depth_entry, self.curr_mip_entry,
                      self.curr_bitmap_spinbox, self.max_bitmap_entry):
                w.config(state=tk.NORMAL)

            for w in (self.curr_type_menu, self.curr_format_menu,
                      self.curr_platform_menu, self.curr_swizzled_menu):
                w.sel_index = -1

            for w in (self.curr_width_entry, self.curr_height_entry,
                      self.curr_depth_entry, self.curr_mip_entry,
                      self.max_bitmap_entry, self.curr_bitmap_spinbox):
                w.delete(0, tk.END)

            tag_paths = self.tag_list_frame.selected_paths
            if len(tag_paths) == 1:
                for tag_path in tag_paths:
                    bitm_tag_info = self.bitmap_tag_infos.get(tag_path)

                if bitm_tag_info:
                    bitm_ct = len(bitm_tag_info.bitmap_infos)
                    try:
                        i = int(self.curr_bitmap_spinbox.get())
                    except ValueError:
                        i = 0

                    if i >= bitm_ct:
                        self.curr_bitmap_spinbox.set("0")
                        i = 0

                    self.curr_bitmap_spinbox.config(to=bitm_ct - 1)
                    self.curr_bitmap_spinbox.insert(tk.END, str(i))
                    self.max_bitmap_entry.insert(tk.END, str(bitm_ct - 1))
                    if i < bitm_ct:
                        bitm_info = bitm_tag_info.bitmap_infos[i]

                        self.curr_type_menu.sel_index = bitm_info.type
                        self.curr_format_menu.sel_index = bitm_info.format
                        self.curr_platform_menu.sel_index = bitm_tag_info.platform
                        self.curr_swizzled_menu.sel_index = bitm_info.swizzled

                        self.curr_width_entry.insert(tk.END, str(bitm_info.width))
                        self.curr_height_entry.insert(tk.END, str(bitm_info.height))
                        self.curr_depth_entry.insert(tk.END, str(bitm_info.depth))
                        self.curr_mip_entry.insert(tk.END, str(bitm_info.mipmaps))
                else:
                    print("Could not locate bitmap info for: %s" % tag_path)

        except Exception:
            print(format_exc())
            
        for w in (self.curr_width_entry, self.curr_height_entry,
                  self.curr_depth_entry, self.curr_mip_entry):
            w.config(state=tk.DISABLED)

        for w in (self.curr_bitmap_spinbox, self.max_bitmap_entry):
            w.config(state="readonly")

        self._populating_bitmap_info = False

    def dir_browse(self):
        if self._processing:
            return

        dirpath = askdirectory(initialdir=self.scan_dir_path.get(),
                               parent=self, title="Select directory to scan")
        if not dirpath:
            return

        dirpath = sanitize_path(dirpath)
        if not dirpath.endswith(PATHDIV):
            dirpath += PATHDIV

        self.scan_dir_path.set(dirpath)
        if self.app_root:
            self.app_root.last_load_dir = dirname(dirpath)

    def log_browse(self):
        if self._processing:
            return

        fp = asksaveasfilename(
            initialdir=dirname(self.log_file_path.get()),
            title="Save scan log to...", parent=self,
            filetypes=(("bitmap optimizer log", "*.log"), ('All', '*')))

        if not fp:
            return

        if len(splitext(fp)) == 2:
            fp += ".log"

        self.log_file_path.set(sanitize_path(fp))
        if self.app_root:
            self.app_root.last_load_dir = dirname(self.log_file_path.get())

    def convert_bitmap_tag(self, tag, flags, tag_path):
        for i in range(tag.bitmap_count()):
            if not(tag.is_power_of_2_bitmap(i)):
                return False

        new_format = None
        if flags.new_format:
            new_format = FORMAT_NAME_MAP[flags.new_format]

        processing = self.process_bitmap_tag(tag_path)

        bm = ab.Arbytmap()
        bad_bitmaps = tag.sanitize_mipmap_counts()

        if len(bad_bitmaps) > 0:
            print("ERROR: Bad bitmap block(s) encountered in this tag:\n", tag_path)
            error = True
        else:
            error = not tag.parse_bitmap_blocks()

        if error:
            return False

        for i in range(tag.bitmap_count()):
            format_s = FORMAT_NAME_MAP[tag.bitmap_format(i)]
            type   = TYPE_NAME_MAP[tag.bitmap_type(i)]
            format_t = new_format

            #get the texture block to be loaded
            tex_block = list(tag.data.tagdata.processed_pixel_data.data[i])
            tex_info = tag.tex_infos[i]

            if format_t == ab.FORMAT_P8:
                if (format_s in (ab.FORMAT_R5G6B5, ab.FORMAT_A1R5G5B5,
                                 ab.FORMAT_A4R4G4B4, ab.FORMAT_X8R8G8B8,
                                 ab.FORMAT_A8R8G8B8) and type != ab.TYPE_CUBEMAP):
                    format_t = ab.FORMAT_P8
                elif format_s == ab.FORMAT_L8:
                    format_t = ab.FORMAT_X8R8G8B8
                else:
                    format_t = ab.FORMAT_A8R8G8B8

            elif format_t not in ab.VALID_FORMAT_ENUMS:
                format_t = format_s
            else:
                if format_t in ab.DDS_FORMATS and type == "3D":
                    format_t = format_s
                    print("CANNOT CONVERT 3D TEXTURES TO DXT FORMAT.")

                if not flags.mono_channel_to_keep and format_t == ab.FORMAT_A8:
                    format_t = ab.FORMAT_L8

                if (format_s in (ab.FORMAT_A8, ab.FORMAT_L8, ab.FORMAT_AL8) and
                    format_t in (ab.FORMAT_A8, ab.FORMAT_L8, ab.FORMAT_AL8)):
                    tex_info["format"] = format_s = format_t


            channel_mapping, channel_merge_mapping, format_t = \
                             get_channel_mappings(format_s, flags)
            palette_picker = None
            palettize = True

            if format_s == ab.FORMAT_P8:
                palette_picker = P8_PALETTE.argb_array_to_p8_array_auto
            elif format_t != ab.FORMAT_P8:
                palettize = False
            elif ab.CHANNEL_COUNTS[format_s] != 4:
                pass
            elif flags.ck_trans and format_s not in (ab.FORMAT_X8R8G8B8,
                                                     ab.FORMAT_R5G6B5):
                if flags.p8_mode == 0:
                    # auto-bias
                    palette_picker = P8_PALETTE.argb_array_to_p8_array_auto_alpha
                else:
                    # average-bias
                    palette_picker = P8_PALETTE.argb_array_to_p8_array_average_alpha
            elif flags.p8_mode == 0:
                # auto-bias
                palette_picker = P8_PALETTE.argb_array_to_p8_array_auto
            else:
                # average-bias
                palette_picker = P8_PALETTE.argb_array_to_p8_array_average

            # we want to preserve the color key transparency of
            # the original image if converting to the same format
            if (format_s == format_t and
                format_t in (ab.FORMAT_P8, ab.FORMAT_DXT1)):
                ck_transparency = True

            bm.load_new_texture(texture_block=tex_block,
                                texture_info=tex_info)

            # build the initial conversion settings list from the above settings
            conv_settings = dict(
                swizzle_mode=flags.swizzle, one_bit_bias=flags.alpha_bias,
                downres_amount=flags.downres, palettize=palettize,
                color_key_transparency=flags.ck_trans, gamma=gamma,
                mipmap_gen=flags.mip_gen)

            # add the variable settings into the conversion settings list
            conv_settings["format_t"] = format_t
            if channel_mapping is not None:
                conv_settings["channel_mapping"] = channel_mapping
            if channel_merge_mapping is not None:
                conv_settings["channel_merge_mapping"] = channel_merge_mapping
            if palette_picker is not None:
                conv_settings["palette_picker"] = palette_picker

            if conv_settings["format_t"] != ab.FORMAT_P8:
                conv_settings["palettize"] = False


            bm.load_new_conversion_settings(**conv_settings)

            status = True
            if processing:
                status = bm.convert_texture()
                tag.tex_infos[i] = bm.texture_info  # tex_info may have changed

            if flags.extract_to != " ":
                path = bm.filepath
                if tag.bitmap_count() > 1:
                    path += ("_"+str(i))
                bm.save_to_file(output_path=path, ext=flags.extract_to.lower())

            if status and processing:
                tex_root = tag.data.tagdata.processed_pixel_data.data[i]
                tex_root.parse(initdata=bm.texture_block)
                tag.swizzled(i, bm.swizzled)

                #change the bitmap format to the new format
                tag.bitmap_format(i, I_FORMAT_NAME_MAP[format_t])
            elif not (extracting_texture(tag) or self.prune_tiff.get()):
                print("Error occurred while attempting to convert the tag:")
                print(tag_path + "\n")
                return False

        if self.prune_tiff.get():
            tag.data.tagdata.compressed_color_plate_data.data = bytearray()

        if processing:
            tag.sanitize_bitmaps()
            tag.set_platform(flags.platform)
            tag.add_bitmap_padding(flags.platform)

        if processing or self.prune_tiff.get():
            try:
                save_status = tag.serialize()
            except Exception:
                print(format_exc())
                save_status = False
            return save_status
        elif not flags.extract_to:
            return False

        return None

    def get_channel_mappings(self, format_s, flags):
        """Goes through a ton of checks to figure out which channel
        mapping to use for converting(and returns it). Also checks a
        few exception cases where converting to that format would
        be bad and instead resets the target format to the source format"""
        mono_swap = flags.mono_swap
        format_t = flags.new_format
        multi_swap = flags.multi_swap
        channel_to_keep = flags.mono_channel_to_keep

        channel_count = ab.CHANNEL_COUNTS[format_s]
        target_channel_count = ab.CHANNEL_COUNTS[format_t]
        channel_mapping = None
        channel_merge_mapping = None
        if channel_count == 4:
            if target_channel_count == 4:
                """THIS TAKES CARE OF ALL THE MULTIPURPOSE CHANNEL SWAPPING"""
                if multi_swap == 1:
                    #SWAP CHANNELS FROM PC TO XBOX
                    channel_mapping = PC_ARGB_TO_XBOX_ARGB

                elif multi_swap == 2:
                    #SWAP CHANNELS FROM XBOX TO PC
                    channel_mapping = XBOX_ARGB_TO_PC_ARGB

            elif format_t in (ab.FORMAT_A8,  ab.FORMAT_L8,
                              ab.FORMAT_AL8, ab.FORMAT_P8):
                """THIS AND THE NEXT ONE TAKE CARE OF CONVERTING
                FROM A 4 CHANNEL FORMAT TO MONOCHROME"""
                if channel_to_keep:
                    #keep the alpha channel
                    channel_mapping = ab.ANYTHING_TO_A
                    if format_s == ab.FORMAT_P8:
                        channel_merge_mapping = ab.M_ARGB_TO_A
                else:
                    #keep the intensity channel
                    channel_merge_mapping = ab.M_ARGB_TO_L

            elif format_t == ab.FORMAT_A8L8:
                if mono_swap:
                    channel_merge_mapping = ab.M_ARGB_TO_LA
                else:
                    channel_merge_mapping = ab.M_ARGB_TO_AL

        elif channel_count == 2:
            """THIS TAKES CARE OF CONVERTING FROM A
            2 CHANNEL FORMAT TO OTHER FORMATS"""

            if format_s == ab.FORMAT_A8L8:
                if mono_swap:
                    if format_t == ab.FORMAT_A8L8:
                        channel_mapping = ab.AL_TO_LA

                    elif target_channel_count == 4:
                        channel_mapping = ab.LA_TO_ARGB

                elif target_channel_count == 4:
                    channel_mapping = ab.AL_TO_ARGB

                elif format_t in (ab.FORMAT_A8, ab.FORMAT_L8, ab.FORMAT_AL8):
                    if channel_to_keep:
                        #keep the alpha channel
                        channel_mapping = ab.ANYTHING_TO_A
                    else:
                        #keep the intensity channel
                        channel_mapping = ab.AL_TO_L

            elif format_s == ab.FORMAT_AL8:
                if target_channel_count == 4:
                    channel_mapping = AL_COMBO_TO_ARGB
                else:
                    channel_mapping = AL_COMBO_TO_AL

        elif channel_count == 1:
            """THIS TAKES CARE OF CONVERTING FROM A
            1 CHANNEL FORMAT TO OTHER FORMATS"""
            if target_channel_count == 4:
                if format_s == ab.FORMAT_A8:
                    channel_mapping = ab.A_TO_ARGB

                elif format_s == ab.FORMAT_L8:
                    channel_mapping = ab.L_TO_ARGB

            elif target_channel_count == 2:
                if format_s == ab.FORMAT_A8:
                    channel_mapping = ab.A_TO_AL

                elif format_s == ab.FORMAT_L8:
                    channel_mapping = ab.L_TO_AL

        return(channel_mapping, channel_merge_mapping, format_t)

    def extracting_texture(self, tag_path):
        '''determines if a texture extraction is to take place'''
        return self.conversion_flags[tag_path].extract_to != 0

    def process_bitmap_tag(self, tag_path):
        flags = self.conversion_flags[tag_path]
        info = self.bitmap_tag_infos[tag_path]

        if not info.platform:
            format = info.format

            # if all these are true we skip the tag
            if (flags.downres == 0 and flags.multi_swap == 0 and
                 flags.new_format == 0 and flags.mip_gen == False and
                 flags.platform == info.platform and
                 (flags.mono_swap == False or format != FORMAT_A8Y8) and
                 (info.swizzled == flags.swizzled or
                  FORMAT_NAME_MAP[format] in ab.DDS_FORMATS) ):
                return False
        return True

    def get_will_be_processed(self, tag_path):
        info = self.bitmap_tag_infos.get(tag_path)
        if not info:
            return False

        if not info.bitmap_infos or self.read_only.get():
            return False

        return (self.prune_tiff.get() or
                self.process_bitmap_tag(tag_path) or
                self.extracting_texture(tag_path))

    def make_detailed_log(self):
        logstr = ("CE-XBOX Bitmap Converter: tagset scan results\n\n\n"
                  "These are the bitmaps located in the tags folder "
                  "organized by type and then by format.\n\n")

        base_str = "Bitmap %s --- WxHxD: %sx%sx%s --- Mipmaps: %s\n"
        tag_counts = [0, 0, 0]

        formatted_strs = {}
        tag_header_strs = ("2D Textures", "3D Textures", "Cubemaps")

        # so we can sort bitmaps by filesize we'll create a dict to hold all
        # the strings before we concate them so we can sort them later by size
        tag_info_strs = {}

        # add dicts for all three types to the tag_info_strings
        for typ in range(2):
            formatted_strs[typ] = ['' * 18]
            tag_info_strs[typ]  = ['' * 18]

            # add the formats to each of these new dicts
            for fmt in range(len(BITMAP_FORMATS)):
                if "?" not in BITMAP_FORMATS[fmt]:
                    formatted_strs[typ][fmt] = "\n\n%s%s" % (
                        " " * 4, BITMAP_FORMATS[fmt])
                    tag_info_strs[typ][fmt] = {}

        # loop through each tag and create a
        # string that details each bitmap in it
        for fp, info in self.bitmap_tag_infos:
            filesize = (getsize(fp) - info.tiff_data_size()) // 1024
            tagstr = ("\n" + " "*8 + filepath +
                      "\n" + " "*12 + "Compiled tag size = %sKB\n" %
                      ("less than 1" if filesize <= 0 else str(filesize)))

            i = 0
            for bitm_info in info.bitmap_infos:
                tagstr += (" " * 12 + base_str %
                           (i, info.width, info.height, info.depth, info.mipmaps))
                i += 1

            tag_strs = tag_info_strs[info.type][info.format]
            tag_strs.setdefault(filesize, [])
            tag_strs[filesize].append(tagstr)

        # Take all the tag strings generated above and concatenate them
        # to the appropriate b_format string under the appropriate b_type
        for typ in range(2):
            for fmt in VALID_FORMAT_ENUMS:
                for size in reversed(sorted(tag_info_strs[typ][fmt])):
                    for tagstr in tag_info_strs[typ][fmt][size]:
                        tag_counts[typ] += 1
                        formatted_strs[typ][fmt] += tagstr

        #concate all the strings to the
        #log in order of b_type and b_format
        for typ in range(2):
            logstr += "\n\n%s:\n    Count = %s\n%s" % (
                tag_header_strs[typ], tag_counts[typ],
                ''.join(formatted_strs[typ]))

        return logstr


class BitmapConverterList(tk.Frame, BinillaWidget):
    listboxes = ()
    reverse_listbox = False
    toggle_to = True
    sort_method = 'path'

    displayed_paths = ()
    selected_paths = ()

    _populating = False

    def __init__(self, master, **options):
        tk.Frame.__init__(self, master, **options )

        self.formats_shown = [True] * len(BITMAP_FORMATS)
        self.types_shown   = [True] * len(BITMAP_TYPES)
        self.displayed_paths = []
        self.selected_paths = set()
        self.build_tag_sort_mappings()

        self.sort_menu = tk.Menu(self, tearoff=False)
        self.types_menu = tk.Menu(self, tearoff=False)
        self.formats_menu = tk.Menu(self, tearoff=False)

        self.sort_menu.add_command(
            label="Toggle all to %s" % BITMAP_PLATFORMS[int(self.toggle_to)],
            command=self.toggle_all)
        self.sort_menu.add_command(
            label="Invert selection", command=self.invert_selection)
        self.sort_menu.add_separator()

        self.sort_menu.add_command(
            label="Sort by Filepath", command=lambda:
            self.display_sorted_tags('path', True))
        self.sort_menu.add_command(
            label="Sort by Filesize", command=lambda:
            self.display_sorted_tags('size', True))
        self.sort_menu.add_command(
            label="Sort by Bitmap type", command=lambda:
            self.display_sorted_tags('type', True))
        self.sort_menu.add_command(
            label="Sort by Bitmap format", command=lambda:
            self.display_sorted_tags('format', True))

        self.types_menu.add_command(
            label="Toggle all", command=lambda:
            self.toggle_types_allowed(0, -1))
        for typ in range(len(BITMAP_TYPES)):
            self.types_menu.add_command(
                label=BITMAP_TYPES[typ] + u' \u2713',
                command=lambda t=typ: self.toggle_types_allowed(t + 1, t))

        self.formats_menu.add_command(
            label="Toggle all", command=lambda:
            self.toggle_formats_allowed(0, -1))
        i = 1
        for fmt in VALID_FORMAT_ENUMS:
            self.formats_menu.add_command(
                label=BITMAP_FORMATS[fmt] + u' \u2713',
                command=lambda i=i, f=fmt:self.toggle_formats_allowed(i, f))
            i += 1

        self.vsb = tk.Scrollbar(self, orient="vertical")
        self.hsb = tk.Scrollbar(self, orient="horizontal")
        self.listboxes = []
        self.listboxes.append(
            tk.Listbox(self, height=5,
                       yscrollcommand=self._path_scrolled,
                       xscrollcommand=self.hsb.set))
        self.listboxes.append(
            tk.Listbox(self, width=8, height=5,
                       yscrollcommand=self._size_scrolled))
        self.listboxes.append(
            tk.Listbox(self, width=11, height=5,
                       yscrollcommand=self._format_scrolled))
        self.listboxes.append(
            tk.Listbox(self, width=6, height=5,
                       yscrollcommand=self._type_scrolled))

        self.path_listbox.bind("<Button-3>", lambda e, m=self.sort_menu:
                               self.post_rightclick_menu(e, m))
        self.size_listbox.bind("<Button-3>", lambda e, m=self.sort_menu:
                               self.post_rightclick_menu(e, m))
        self.format_listbox.bind("<Button-3>", lambda e, m=self.formats_menu:
                                 self.post_rightclick_menu(e, m))
        self.type_listbox.bind("<Button-3>", lambda e, m=self.types_menu:
                               self.post_rightclick_menu(e, m))

        self.hsb.config(command=self.path_listbox.xview)
        self.vsb.config(command=self._scroll_all_yviews)
        self.listboxes[0].bind('<<ListboxSelect>>', self.set_selected_tags_list)

        for i in range(len(self.listboxes)):
            self.listboxes[i].config(selectmode=tk.EXTENDED, highlightthickness=0)
            if i != 0:
                self.listboxes[i].bind('<<ListboxSelect>>', lambda e, idx=i:
                                       self.select_path_listbox(idx))

        self.hsb.pack(side="bottom", fill="x")
        self.vsb.pack(side="right",  fill="y")
        self.path_listbox.pack(side="left", fill="both", expand=True)
        for listbox in self.listboxes[1: ]:
            listbox.pack(side="left", fill="both")

        '''for i in range(30):
            self.path_listbox.insert(tk.END, "asdf\\qwer\\%s.bitmap" % i)
            self.format_listbox.insert(tk.END, BITMAP_FORMATS[i % 18])
            self.type_listbox.insert(tk.END, BITMAP_TYPES[i % 4])
            self.size_listbox.insert(tk.END, str(i))'''
        self.apply_style()

    @property
    def path_listbox(self): return self.listboxes[0]
    @property
    def size_listbox(self): return self.listboxes[1]
    @property
    def format_listbox(self): return self.listboxes[2]
    @property
    def type_listbox(self): return self.listboxes[3]

    def post_rightclick_menu(self, event, menu):
        menu.post(event.x_root, event.y_root)

    def reset_listboxes(self):
        self.selected_paths = set()
        self.displayed_paths = []
        for listbox in self.listboxes:
            listbox.delete(0, tk.END)

    def set_selected_tags_list(self, event=None):
        '''used to set which tags are selected when the tags listbox
        is clicked so we can easily edit their conversion variables'''
        selected = set(self.path_listbox.curselection())
        if len(selected) == 1:
            self.selected_paths.clear()
        else:
            for i in range(self.path_listbox.size()):
                if i not in selected:
                    fp = self.path_listbox.get(i)
                    if fp in self.selected_paths:
                        self.selected_paths.remove(fp)

        for i in selected:
            self.selected_paths.add(self.path_listbox.get(i))

        self.master.populate_bitmap_info()
        self.master.populate_settings()

    def toggle_all(self):
        for flags in self.master.conversion_flags.values():
            flags.swizzled = flags.platform = self.toggle_to

        self.toggle_to = not self.toggle_to
        self.sort_menu.entryconfig(0, label="Toggle all to %s" %
                                   BITMAP_PLATFORMS[int(self.toggle_to)])
        self.display_sorted_tags()

    def invert_selection(self):
        self.path_listbox.selection_clear(first=0, last=tk.END)
        for i in range(self.path_listbox.size()):
            fp = self.path_listbox.get(i)
            if fp not in self.selected_paths:
                self.path_listbox.selection_set(i)
            else:
                self.selected_paths.remove(fp)

        self.set_selected_tags_list()

    def select_path_listbox(self, src_listbox_index=None):
        src_listbox = self.listboxes[src_listbox_index]
        if len(src_listbox.curselection()) > 0:
            self.path_listbox.selection_set(src_listbox.curselection()[0])
            self.set_selected_tags_list()

        self.master.populate_bitmap_info()
        self.master.populate_settings()

    def toggle_types_allowed(self, menu_idx, typ):
        if typ == -1:
            for typ in range(len(BITMAP_TYPES)):
                self.types_shown[typ] = not self.types_shown[typ]
                typ_str = BITMAP_TYPES[typ]
                if self.types_shown[typ]: typ_str += u' \u2713'

                self.types_menu.entryconfig(typ + 1, label=typ_str)
            return

        typ_str = BITMAP_TYPES[typ]
        self.types_shown[typ] = not self.types_shown[typ]
        if self.types_shown[typ]: typ_str += u' \u2713'

        self.types_menu.entryconfig(menu_idx, label=typ_str)
        self.display_sorted_tags()

    def toggle_formats_allowed(self, menu_idx, fmt):
        if fmt == -1:
            i = 1 if menu_idx == 0 else 0
            for fmt in range(len(BITMAP_FORMATS)):
                if fmt in VALID_FORMAT_ENUMS:
                    self.formats_shown[fmt] = not self.formats_shown[fmt]
                    fmt_str = BITMAP_FORMATS[fmt]
                    if self.formats_shown[fmt]: fmt_str += u' \u2713'

                    self.formats_menu.entryconfig(i, label=fmt_str)
                    i += 1
            return

        fmt_str = BITMAP_FORMATS[fmt]
        self.formats_shown[fmt] = not self.formats_shown[fmt]
        if self.formats_shown[fmt]: fmt_str += u' \u2713'

        self.formats_menu.entryconfig(menu_idx, label=fmt_str)
        self.display_sorted_tags()

    def build_tag_sort_mappings(self):
        self.selected_paths = set()
        self.displayed_paths = []
        self.type_format_map = []
        self.size_map = {}

        for typ in range(4):
            self.type_format_map.append([])
            for fmt in range(18):
                self.type_format_map[typ].append([])

        for fp, info in self.master.bitmap_tag_infos.items():
            if not info.pixel_data_size in self.size_map:
                self.size_map[info.pixel_data_size] = []

            self.type_format_map[info.type][info.format].append(fp)
            self.size_map[info.pixel_data_size].append(fp)

    def display_sorted_tags(self, sort_by=None, allow_reverse=False):
        if sort_by is None:
            sort_by = self.sort_method

        self.reverse_listbox = not self.reverse_listbox and allow_reverse
        self.sort_displayed_tags(sort_by)
        self.after(0, self.populate_tag_list_boxes)

    def sort_displayed_tags(self, sort_by):
        if not self.master.bitmap_tag_infos:
            return

        bitmap_tag_infos = self.master.bitmap_tag_infos
        self.displayed_paths = displayed_paths = []
        if sort_by == 'path':
            for path in sorted(bitmap_tag_infos.keys()):
                info = bitmap_tag_infos[path]
                if (self.formats_shown[info.format] and
                    self.types_shown[info.type]):
                    displayed_paths.append(path)

        elif sort_by == 'size':
            for tagsize in sorted(self.size_map):
                for path in self.size_map[tagsize]:
                    info = bitmap_tag_infos[path]
                    if (self.formats_shown[info.format] and
                        self.types_shown[info.type]):
                        displayed_paths.append(path)

        elif sort_by == 'format':
            for typ in range(len(self.types_shown)):
                for fmt in range(len(self.formats_shown)):
                    if self.formats_shown[fmt] and self.types_shown[typ]:
                        displayed_paths.extend(self.type_format_map[typ][fmt])

        elif sort_by == 'type':
            for fmt in range(len(self.formats_shown)):
                for typ in range(len(self.types_shown)):
                    if self.formats_shown[fmt] and self.types_shown[typ]:
                        displayed_paths.extend(self.type_format_map[typ][fmt])

        self.sort_method = sort_by
        if self.reverse_listbox:
            displayed_paths.reverse()

    def populate_tag_list_boxes(self):
        if self._populating:
            return

        self._populating = True
        try:
            for listbox in self.listboxes:
                listbox.delete(0, tk.END)

            for fp in self.displayed_paths:
                info = self.master.bitmap_tag_infos[fp]
                size = info.pixel_data_size
                if size < 1024:
                    size_str = str(size) + "  B"
                elif size < 1024**2:
                    size_str = str((size + 512) // 1024) + "  KB"
                else:
                    size_str = str((size + 1024**2 // 2) // 1024**2) + "  MB"

                self.path_listbox.insert(tk.END, fp)
                self.format_listbox.insert(tk.END, BITMAP_FORMATS[info.format])
                self.type_listbox.insert(tk.END, BITMAP_TYPES[info.type])
                self.size_listbox.insert(tk.END, size_str)

                self.set_listbox_entry_color(tk.END, fp)
        except Exception:
            print(format_exc())

        self._populating = False

    def set_listbox_entry_color(self, listbox_index, filepath):
        if self.master.get_will_be_processed(filepath):
            self.path_listbox.itemconfig(listbox_index, bg='dark green', fg='white')
        else:
            self.path_listbox.itemconfig(listbox_index, bg='white', fg='black')

    def _scroll_all_yviews(self, *args):
        for listbox in self.listboxes:
            listbox.yview(*args)

    def _sync_yviews(self, src_listbox, *args):
        for listbox in self.listboxes:
            if listbox is not src_listbox and src_listbox.yview() != listbox.yview():
                listbox.yview_moveto(args[0])
        self.vsb.set(*args)

    def _path_scrolled(self, *args):
        self._sync_yviews(self.path_listbox, *args)

    def _format_scrolled(self, *args):
        self._sync_yviews(self.format_listbox, *args)

    def _type_scrolled(self, *args):
        self._sync_yviews(self.type_listbox, *args)

    def _size_scrolled(self, *args):
        self._sync_yviews(self.size_listbox, *args)

BitmapConverterWindow(None)
