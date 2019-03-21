import ctypes
import gc
import sys
import weakref
import arbytmap as ab

from array import array
from copy import deepcopy
from os.path import getsize, splitext, dirname, join, normpath, exists, isfile, relpath
from threading import Thread
from tkinter.filedialog import asksaveasfilename, askdirectory
from time import sleep, time
from traceback import format_exc

from reclaimer.bitmaps.p8_palette import HALO_P8_PALETTE, STUBBS_P8_PALETTE
from reclaimer.hek.defs.bitm import bitm_def
from reclaimer.field_types import *

from binilla.util import *
from binilla.widgets import BinillaWidget, ScrollMenu
from mozzarilla.field_widgets import HaloBitmapDisplayFrame, HaloBitmapDisplayBase

if __name__ == "__main__":
    bitmap_converter_base_class = tk.Tk
else:
    bitmap_converter_base_class = tk.Toplevel


curr_dir = get_cwd(__file__)

#                      (A, R, G, B)
PC_ARGB_TO_XBOX_ARGB = (1, 3, 2, 0)
XBOX_ARGB_TO_PC_ARGB = (3, 0, 2, 1)

AL_COMBO_TO_AL   = (0, 0)
AL_COMBO_TO_ARGB = (0, 0, 0, 0)


BITMAP_PLATFORMS = ("PC", "XBOX")
MULTI_SWAP_OPTIONS = ("", "PC to XBOX", "XBOX to PC")
AY8_OPTIONS = ("Alpha", "Intensity")
EXTRACT_TO_OPTIONS = ("", "DDS", "TGA", "PNG")
NO_YES_OPTIONS = ("No", "Yes")
BITMAP_TYPES = TYPE_NAME_MAP
BITMAP_FORMATS = FORMAT_NAME_MAP
DXT_ALPHA_FORMATS = (ab.FORMAT_DXT2, ab.FORMAT_DXT3,
                     ab.FORMAT_DXT4, ab.FORMAT_DXT5)

VALID_FORMAT_ENUMS = (0, 1, 2, 3, 6, 8, 9, 10, 11, 14, 15, 16, 17)
PARAM_FORMAT_TO_FORMAT = (-1, ) + VALID_FORMAT_ENUMS
FORMAT_OPTIONS = ("Unchanged", ) + tuple(BITMAP_FORMATS[i] for i in VALID_FORMAT_ENUMS)


platform = sys.platform.lower()
if "linux" in platform:
    platform = "linux"


SetFileAttributesW = None
if platform == "win32":
    TEXT_EDITOR_NAME = "notepad"
    SetFileAttributesW = ctypes.windll.kernel32.SetFileAttributesW
elif platform == "darwin":
    TEXT_EDITOR_NAME = "TextEdit"
elif platform == "linux":
    TEXT_EDITOR_NAME = "vim"
else:
    # idfk
    TEXT_EDITOR_NAME = "nano"


class ConversionFlags:
    platform = BITMAP_PLATFORMS.index("PC")
    multi_swap = MULTI_SWAP_OPTIONS.index("")
    mono_channel_to_keep = AY8_OPTIONS.index("Alpha")

    extract_to = EXTRACT_TO_OPTIONS.index("")
    downres = 0
    alpha_bias = 127
    new_format = 0

    prune_tiff = 0
    swizzled = 0
    mono_swap = 0
    ck_trans = 0
    mip_gen = 0

    extract_path = ""


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
        self.swizzled = bool(bitmap_block.flags.swizzled)
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

        self.platform = bitm_tag.is_xbox_bitmap

    @property
    def type(self):
        return 0 if not self.bitmap_infos else self.bitmap_infos[0].type
    @property
    def format(self):
        return 0 if not self.bitmap_infos else self.bitmap_infos[0].format
    @property
    def swizzled(self):
        return 0 if not self.bitmap_infos else self.bitmap_infos[0].swizzled


def get_will_be_converted(flags, tag_info):
    if flags.platform != tag_info.platform:
        return True
    elif (flags.swizzled != tag_info.swizzled and
          tag_info.format not in (14, 15, 16)):
        return True
    elif (flags.mono_swap and (PARAM_FORMAT_TO_FORMAT[flags.new_format] == 3 or
                               tag_info.format == 3)):
        return True
    elif flags.multi_swap and tag_info.format in (6, 8, 9, 10, 11, 14, 15, 16):
        return True

    for info in tag_info.bitmap_infos:
        if PARAM_FORMAT_TO_FORMAT[flags.new_format] not in (-1, info.format):
            return True
        elif flags.downres and max(info.width, info.height, info.depth) > 4:
            return True
        elif flags.mip_gen and info.mipmaps == 0:
            return True

    return False


def get_channel_mappings(conv_flags, bitmap_info):
    mono_swap = conv_flags.mono_swap
    fmt_s = FORMAT_NAME_MAP[bitmap_info.format]
    fmt_t = PARAM_FORMAT_TO_FORMAT[conv_flags.new_format]
    fmt_t = fmt_s if fmt_t < 0 else FORMAT_NAME_MAP[fmt_t]

    multi_swap = conv_flags.multi_swap
    chan_to_keep = conv_flags.mono_channel_to_keep

    chan_ct_s = ab.CHANNEL_COUNTS[fmt_s]
    chan_ct_t = ab.CHANNEL_COUNTS[fmt_t]
    chan_map = None
    chan_merge_map = None

    if chan_ct_s == 4:
        if chan_ct_t == 4:
            # TAKES CARE OF ALL THE MULTIPURPOSE CHANNEL SWAPPING
            if multi_swap == 1:
                chan_map = PC_ARGB_TO_XBOX_ARGB
            elif multi_swap == 2:
                chan_map = XBOX_ARGB_TO_PC_ARGB

        elif fmt_t == ab.FORMAT_A8L8:
            chan_merge_map = ab.M_ARGB_TO_LA if mono_swap else ab.M_ARGB_TO_AL

        elif fmt_t in (ab.FORMAT_A8, ab.FORMAT_L8, ab.FORMAT_AL8):
            # CONVERTING FROM A 4 CHANNEL FORMAT TO MONOCHROME
            if fmt_t == ab.FORMAT_L8:
                chan_merge_map = ab.M_ARGB_TO_L
            elif fmt_t == ab.FORMAT_A8 or chan_to_keep == 0:
                chan_map = ab.ANYTHING_TO_A
                chan_merge_map = ab.M_ARGB_TO_A
            else:
                chan_merge_map = ab.M_ARGB_TO_L

    elif chan_ct_s == 2:
        # CONVERTING FROM A 2 CHANNEL FORMAT TO OTHER FORMATS
        if fmt_s == ab.FORMAT_AL8:
            chan_map = AL_COMBO_TO_ARGB if chan_ct_t == 4 else AL_COMBO_TO_AL

        elif fmt_s == ab.FORMAT_A8L8:
            if chan_ct_t == 4:
                if mono_swap:
                    chan_map = ab.LA_TO_ARGB
                else:
                    chan_map = ab.AL_TO_ARGB
            elif fmt_t == ab.FORMAT_A8 or (fmt_t == ab.FORMAT_AL8 and
                                           not chan_to_keep):
                chan_map = ab.ANYTHING_TO_A
            elif fmt_t == ab.FORMAT_L8 or (fmt_t == ab.FORMAT_AL8 and
                                           chan_to_keep):
                chan_map = ab.AL_TO_L
            elif mono_swap:
                if fmt_t == ab.FORMAT_A8L8:
                    chan_map = ab.AL_TO_LA
                elif chan_ct_t == 4:
                    chan_map = ab.LA_TO_ARGB

    elif chan_ct_s == 1:
        # CONVERTING FROM A 1 CHANNEL FORMAT TO OTHER FORMATS
        if chan_ct_t == 4:
            if fmt_s == ab.FORMAT_A8:
                chan_map = ab.A_TO_ARGB
            elif fmt_s == ab.FORMAT_L8:
                chan_map = ab.L_TO_ARGB

        elif chan_ct_t == 2:
            if fmt_s == ab.FORMAT_A8:
                chan_map = ab.A_TO_AL
            elif fmt_s == ab.FORMAT_L8:
                chan_map = ab.L_TO_AL

    return chan_map, chan_merge_map


def convert_bitmap_tag(tag, conv_flags, bitmap_info):
    for i in range(tag.bitmap_count()):
        if not tag.is_power_of_2_bitmap(i):
            return False

    new_format = BITMAP_FORMATS[
        PARAM_FORMAT_TO_FORMAT[conv_flags.new_format]]

    extract_ext = EXTRACT_TO_OPTIONS[conv_flags.extract_to]
    ck_trans = conv_flags.ck_trans

    do_conversion = get_will_be_converted(conv_flags, bitmap_info)
    if not do_conversion and not extract_ext:
        return True

    arb = ab.Arbytmap()
    if tag.sanitize_mipmap_counts():
        print("ERROR: Bad mipmap counts in this tag:\n%s\t\n" % tag.filepath)
        return False

    tag.parse_bitmap_blocks()
    pixel_data = tag.data.tagdata.processed_pixel_data.data

    for i in range(tag.bitmap_count()):
        typ   = BITMAP_TYPES[tag.bitmap_type(i)]
        fmt_s = BITMAP_FORMATS[tag.bitmap_format(i)]
        fmt_t = fmt_s if conv_flags.new_format <= 0 else new_format

        #get the texture block to be loaded
        tex_block = list(pixel_data[i])
        tex_info = tag.tex_infos[i]

        if fmt_t == ab.FORMAT_P8_BUMP and typ in (ab.TYPE_CUBEMAP, ab.TYPE_3D):
            print("Cannot convert cubemaps or 3d textures to P8.")
            fmt_t = fmt_s
        elif fmt_t in ab.DDS_FORMATS and typ == ab.TYPE_3D:
            print("Cannot convert 3D textures to DXT formats.")
            fmt_t = fmt_s

        if (fmt_s in (ab.FORMAT_A8, ab.FORMAT_L8, ab.FORMAT_AL8) and
            fmt_t in (ab.FORMAT_A8, ab.FORMAT_L8, ab.FORMAT_AL8)):
            tex_info["format"] = fmt_s = fmt_t

        chan_map, chan_merge_map = get_channel_mappings(conv_flags, bitmap_info)
        palette_picker = None
        palettize = fmt_t == ab.FORMAT_P8_BUMP

        # we want to preserve the color key transparency of
        # the original image if converting to the same format
        if fmt_s == fmt_t and fmt_t in (ab.FORMAT_P8_BUMP, ab.FORMAT_DXT1):
            # also need to make sure channels aren't being swapped around
            if not conv_flags.multi_swap:
                ck_trans = True

        if ab.CHANNEL_COUNTS[fmt_s] == 4:
            if not ck_trans or fmt_s in (ab.FORMAT_X8R8G8B8, ab.FORMAT_R5G6B5):
                palette_picker = tag.p8_palette.argb_array_to_p8_array_best_fit
            else:
                palette_picker = tag.p8_palette.argb_array_to_p8_array_best_fit_alpha

        arb.load_new_texture(texture_block=tex_block, texture_info=tex_info)

        # build the initial conversion settings list from the above settings
        conv_settings = dict(
            swizzle_mode=conv_flags.swizzled, palettize=palettize,
            one_bit_bias=conv_flags.alpha_bias, palette_picker=palette_picker,
            downres_amount=conv_flags.downres, target_format=fmt_t,
            color_key_transparency=ck_trans, mipmap_gen=conv_flags.mip_gen,
            channel_mapping=chan_map, channel_merge_mapping=chan_merge_map)

        arb.load_new_conversion_settings(**conv_settings)

        if extract_ext and conv_flags.extract_path:
            path = conv_flags.extract_path
            if tag.bitmap_count() > 1:
                path = join(path, str(i))
            arb.save_to_file(output_path=path, ext=extract_ext)

        if do_conversion:
            success = arb.convert_texture()
            tag.tex_infos[i] = arb.texture_info  # tex_info may have changed

            if success:
                tex_root = pixel_data[i]
                tex_root.parse(initdata=arb.texture_block)
                tag.swizzled(i, arb.swizzled)

                #change the bitmap format to the new format
                tag.bitmap_format(i, I_FORMAT_NAME_MAP[arb.format])
            else:
                print("Error occurred while converting:\n\t%s\n" % tag.filepath)
                return False

    if do_conversion:
        tag.sanitize_bitmaps()
        tag.set_platform(conv_flags.platform)
        tag.add_bitmap_padding(conv_flags.platform)

    return True


class BitmapConverterWindow(bitmap_converter_base_class, BinillaWidget):
    app_root = None
    tag_list_frame = None
    loaded_tags_dir = ''
    last_load_dir = ''

    use_stubbs_p8 = None
    read_only = None
    backup_tags = None
    open_log = None

    conversion_flags = ()
    bitmap_tag_infos = ()
    bitmap_display_windows = ()

    _processing = False
    _cancel_processing = False
    _populating_settings = False
    _populating_bitmap_info = False
    _settings_enabled = True

    print_interval = 5

    # these cache references to the settings widgets for iteratively
    # enabling/disabling settings before and after converting.
    checkbuttons = ()
    buttons = ()
    spinboxes = ()
    menus = ()

    bitm_def = bitm_def

    def __init__(self, app_root, *args, **kwargs):
        BinillaWidget.__init__(self, *args, **kwargs)
        if bitmap_converter_base_class == tk.Toplevel:
            kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
            self.app_root = app_root
        else:
            self.app_root = self
        bitmap_converter_base_class.__init__(self, app_root, *args, **kwargs)

        self.conversion_flags = {}
        self.bitmap_tag_infos = {}
        self.bitmap_display_windows = {}

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
        self.read_only = tk.BooleanVar(self)
        self.backup_tags = tk.BooleanVar(self, True)
        self.open_log = tk.BooleanVar(self, True)
        self.use_stubbs_p8 = tk.BooleanVar(self)

        self.scan_dir_path = tk.StringVar(self)
        self.data_dir_path = tk.StringVar(self)
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
        self.tagset_info_frame = tk.Frame(self.main_frame)
        self.tag_list_frame = BitmapConverterList(self)

        self.log_file_frame  = tk.LabelFrame(
            self.settings_frame, text="Scan log filepath")
        self.scan_dir_frame = tk.LabelFrame(
            self.settings_frame, text="Directory to scan")
        self.data_dir_frame = tk.LabelFrame(
            self.settings_frame, text="Directory to extract data to")
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
                                              state="readonly", repeatinterval=5,
                                              command=lambda *a, s=self:
                                              s.populate_bitmap_info())
        self.curr_bitmap_label_1 = tk.Label(self.bitmap_index_frame, text=" to ")
        self.max_bitmap_entry = tk.Entry(self.bitmap_index_frame, width=3,
                                         state='disabled')

        self.curr_type_menu = ScrollMenu(self.bitmap_info_frame, menu_width=8,
                                         disabled=True, options=BITMAP_TYPES)
        self.curr_format_menu = ScrollMenu(self.bitmap_info_frame, menu_width=8,
                                           disabled=True, options=BITMAP_FORMATS)
        self.curr_swizzled_menu = ScrollMenu(self.bitmap_info_frame, menu_width=8,
                                             options=NO_YES_OPTIONS, disabled=True)
        self.curr_platform_menu = ScrollMenu(self.bitmap_info_frame, menu_width=8,
                                             disabled=True, options=BITMAP_PLATFORMS)
        self.curr_has_tiff_menu = ScrollMenu(self.bitmap_info_frame, menu_width=8,
                                             options=NO_YES_OPTIONS, disabled=True)
        self.curr_height_entry = tk.Entry(self.bitmap_info_frame, width=12,
                                          state='disabled')
        self.curr_width_entry = tk.Entry(self.bitmap_info_frame, width=12,
                                         state='disabled')
        self.curr_depth_entry = tk.Entry(self.bitmap_info_frame, width=12,
                                         state='disabled')
        self.curr_mip_entry = tk.Entry(self.bitmap_info_frame, width=12,
                                       state='disabled')

        self.log_file_entry = tk.Entry(
            self.log_file_frame, textvariable=self.log_file_path,
            state=tk.DISABLED)
        self.log_file_browse_button = tk.Button(
            self.log_file_frame, text="Browse", command=self.log_browse)

        self.scan_dir_entry = tk.Entry(
            self.scan_dir_frame, textvariable=self.scan_dir_path,
            state=tk.DISABLED)
        self.scan_dir_browse_button = tk.Button(
            self.scan_dir_frame, text="Browse", command=self.scan_dir_browse)

        self.data_dir_entry = tk.Entry(
            self.data_dir_frame, textvariable=self.data_dir_path,
            state=tk.DISABLED)
        self.data_dir_browse_button = tk.Button(
            self.data_dir_frame, text="Browse", command=self.data_dir_browse)


        self.read_only_cbutton = tk.Checkbutton(
            self.global_params_frame, text="Read-only �",
            variable=self.read_only, command=self.update_all_path_colors)
        self.backup_tags_cbutton = tk.Checkbutton(
            self.global_params_frame, text="Backup tags �",
            variable=self.backup_tags)
        self.open_log_cbutton = tk.Checkbutton(
            self.global_params_frame, text="Show log �",
            variable=self.open_log)
        self.use_stubbs_p8_cbutton = tk.Checkbutton(
            self.global_params_frame, text="Use Stubbs p8 palette �",
            variable=self.use_stubbs_p8)


        self.read_only_cbutton.tooltip_string = (
            "Does no conversion, and instead writes a\n"
            "log detailing all bitmaps in the directory.")
        self.backup_tags_cbutton.tooltip_string = (
            "Backs up all bitmaps before editing\n"
            "(does nothing if a backup already exists)")
        self.open_log_cbutton.tooltip_string = (
            "Open the conversion log when finished.")
        self.use_stubbs_p8_cbutton.tooltip_string = (
            "Use Stubbs the Zombie's p8-bump palette\n"
            "instead of Halo's for P8-bump textures.")


        self.platform_menu = ScrollMenu(
            self.general_params_frame, menu_width=12,
            options=BITMAP_PLATFORMS, callback=lambda *a, s=self:
            s.set_conversion_flag(self.platform_menu, "platform"))
        self.format_menu = ScrollMenu(
            self.general_params_frame, menu_width=12,
            options=FORMAT_OPTIONS, callback=lambda *a, s=self:
            s.set_conversion_flag(self.format_menu, "new_format"))
        self.extract_to_menu = ScrollMenu(
            self.general_params_frame, menu_width=12,
            options=EXTRACT_TO_OPTIONS, callback=lambda *a, s=self:
            s.set_conversion_flag(self.extract_to_menu, "extract_to"))
        self.prune_tiff_menu = ScrollMenu(
            self.general_params_frame, menu_width=12,
            options=NO_YES_OPTIONS, callback=lambda *a, s=self:
            s.set_conversion_flag(self.prune_tiff_menu, "prune_tiff"))
        self.generate_mips_menu = ScrollMenu(
            self.general_params_frame, menu_width=12,
            options=NO_YES_OPTIONS, callback=lambda *a, s=self:
            s.set_conversion_flag(self.generate_mips_menu, "mip_gen"))
        self.downres_box = tk.Spinbox(
            self.general_params_frame, from_=0, to=12, width=16,
            state="readonly", command=lambda *a, s=self:
            s.set_conversion_flag(self.downres_box, "downres"))


        self.platform_menu.tooltip_string = (
            "The platform to make the tag usable on.")
        self.format_menu.tooltip_string = (
            "The format to convert the bitmap to.")
        self.extract_to_menu.tooltip_string = (
            "The image format to extract the bitmap to.")
        self.prune_tiff_menu.tooltip_string = (
            "Prunes the uncompressed TIFF pixel data\n"
            "from all bitmaps to reduce their filesize.")
        self.generate_mips_menu.tooltip_string = (
            "Whether or not to generate all necessary mipmaps.")
        self.downres_box.tooltip_string = (
            "Number of times to cut the bitmaps\n"
            "width, height, and depth in half.")

        self.ay8_channel_src_menu = ScrollMenu(
            self.format_params_frame, menu_width=10,
            options=AY8_OPTIONS, callback=lambda *a, s=self:
            s.set_conversion_flag(self.ay8_channel_src_menu, "mono_channel_to_keep"))
        self.ck_transparency_menu = ScrollMenu(
            self.format_params_frame, menu_width=10,
            options=NO_YES_OPTIONS, callback=lambda *a, s=self:
            s.set_conversion_flag(self.ck_transparency_menu, "ck_trans"))
        self.swap_a8y8_menu = ScrollMenu(
            self.format_params_frame, menu_width=10,
            options=NO_YES_OPTIONS, callback=lambda *a, s=self:
            s.set_conversion_flag(self.swap_a8y8_menu, "mono_swap"))
        self.multi_swap_menu = ScrollMenu(
            self.format_params_frame, menu_width=10,
            options=MULTI_SWAP_OPTIONS, callback=lambda *a, s=self:
            s.set_conversion_flag(self.multi_swap_menu, "multi_swap"))
        self.swizzled_menu = ScrollMenu(
            self.format_params_frame, menu_width=10,
            options=NO_YES_OPTIONS, callback=lambda *a, s=self:
            s.set_conversion_flag(self.swizzled_menu, "swizzled"))
        self.alpha_bias_box = tk.Spinbox(
            self.format_params_frame, from_=0, to=255, width=14,
            state="readonly", repeatinterval=10, command=lambda *a, s=self:
            s.set_conversion_flag(self.alpha_bias_box, "alpha_bias"))


        self.ay8_channel_src_menu.tooltip_string = (
            "HUD meters converted to/from Xbox A8Y8 need to\n"
            "have their intensity and alpha channels swapped.\n"
            "Setting this will swap them when going to/from A8Y8.")
        self.ck_transparency_menu.tooltip_string = (
            "Whether to use color-key transparency when converting\n"
            "to p8-bump or DXT1. These formats support transparency\n"
            "where transparent pixels are also solid black in color.")
        self.swap_a8y8_menu.tooltip_string = (
            "Whether or not to swap the alpha and intensity\n"
            "channels when converting to or from A8Y8.")
        self.multi_swap_menu.tooltip_string = (
            "When converting multipurpose bitmaps to/from\n"
            "Xbox/PC, use this to swap the their color\n"
            "channels so they work on the other platform.")
        self.swizzled_menu.tooltip_string = (
            "Whether or not to swizzle the bitmap pixels.\n"
            "This does nothing to DXT1/3/5 bitmaps.\n"
            "Xbox bitmaps MUST be swizzled to work.")
        self.alpha_bias_box.tooltip_string = (
            "When converting to DXT1 with transparency, p8-bump,\n"
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
        self.data_dir_frame.pack(expand=True, fill='x')
        self.global_params_frame.pack(expand=True, fill='x')
        self.params_frame.pack(expand=True, fill='x')

        self.general_params_frame.pack(side='left', expand=True, fill='both')
        self.format_params_frame.pack(side='left', expand=True, fill='both')

        self.log_file_entry.pack(side='left', expand=True, fill='x')
        self.log_file_browse_button.pack(side='left')

        self.scan_dir_entry.pack(side='left', expand=True, fill='x')
        self.scan_dir_browse_button.pack(side='left')

        self.data_dir_entry.pack(side='left', expand=True, fill='x')
        self.data_dir_browse_button.pack(side='left')


        self.read_only_cbutton.grid(row=0, column=0, sticky='w')
        self.backup_tags_cbutton.grid(row=0, column=1, sticky='w')
        self.open_log_cbutton.grid(row=0, column=2, sticky='w')
        self.use_stubbs_p8_cbutton.grid(row=0, column=3, sticky='w')

        i = 0
        widgets = (self.platform_menu, self.format_menu, self.extract_to_menu,
                   self.prune_tiff_menu, self.generate_mips_menu, self.downres_box)
        for name in ("Platform", "Format", "Extract to",
                     "Prune TIFF data", "Generate mipmaps", "Downres. level"):
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
        widgets = (self.ay8_channel_src_menu, self.ck_transparency_menu,
                   self.swap_a8y8_menu, self.multi_swap_menu,
                   self.swizzled_menu, self.alpha_bias_box)
        for name in ("AY8 channel source", "Use CK transparency",
                     "Swap A8Y8", "Multi. swap",
                     "Swizzled", "Alpha bias"):
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
                                     columnspan=2, pady=(5, 10))
        i = 1
        widgets = (self.curr_type_menu, self.curr_format_menu,
                   self.curr_swizzled_menu,
                   self.curr_platform_menu, self.curr_has_tiff_menu,
                   self.curr_width_entry, self.curr_height_entry,
                   self.curr_depth_entry, self.curr_mip_entry)
        for name in ("Type", "Format", "Swizzled", "Platform", "Has TIFF",
                     "Width", "Height", "Depth", "Mipmaps"):
            w = widgets[i - 1]
            lbl = tk.Label(self.bitmap_info_frame, text=name)
            lbl.grid(row=i, column=0, sticky='w', pady=3)
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
            widgets = next_widgets

        self.buttons = (self.scan_dir_browse_button, self.scan_button,
                        self.log_file_browse_button, self.convert_button)
        self.checkbuttons = (self.read_only_cbutton, self.backup_tags_cbutton,
                             self.open_log_cbutton, self.use_stubbs_p8_cbutton)
        self.spinboxes = (self.downres_box, self.alpha_bias_box)
        self.menus = (self.platform_menu, self.format_menu,
                      self.extract_to_menu, self.prune_tiff_menu,
                      self.multi_swap_menu, self.generate_mips_menu,
                      self.ay8_channel_src_menu, self.ck_transparency_menu,
                      self.swap_a8y8_menu, self.swizzled_menu)

        self.apply_style()
        self.populate_bitmap_info()
        self.populate_settings()

        if self.app_root is not self:
            self.transient(self.app_root)

    def update_all_path_colors(self):
        update_color = self.tag_list_frame.update_path_listbox_entry_color
        for i in range(self.tag_list_frame.path_listbox.size()):
            update_color(i)

    def destroy(self):
        try:
            self.app_root.tool_windows.pop(self.window_name, None)
        except AttributeError:
            pass
        bitmap_converter_base_class.destroy(self)

    def apply_style(self, seen=None):
        BinillaWidget.apply_style(self, seen)
        self.update()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry("%sx%s" % (w, h))
        self.minsize(width=w, height=h)

    def show_log_in_text_editor(self):
        Thread(target=self._show_log_in_text_editor, daemon=True).start()

    def _show_log_in_text_editor(self):
        try:
            log_path = self.log_file_path.get()
            if not exists(log_path):
                return

            do_subprocess(TEXT_EDITOR_NAME, (), (log_path, ),
                          proc_controller=ProcController(abandon=True),
                          stdout=None, stderr=None, stdin=None)
        except Exception:
            print(format_exc())

    def set_conversion_flag(self, widget, flag_name):
        new_value = -1
        if isinstance(widget, ScrollMenu):
            new_value = widget.sel_index
        elif isinstance(widget, tk.Spinbox):
            new_value = int(widget.get())

        if new_value < 0:
            return

        conv_flags = self.conversion_flags
        path_listbox = self.tag_list_frame.path_listbox
        update_color = self.tag_list_frame.update_path_listbox_entry_color
        for i in path_listbox.curselection():
            fp = path_listbox.get(i)

            bitm_tag_info = self.bitmap_tag_infos.get(fp)
            if flag_name == "new_format" and bitm_tag_info:
                fmt = PARAM_FORMAT_TO_FORMAT[new_value]
                if bitm_tag_info.type == 1 and fmt in (14, 15, 16):
                    print("Cannot convert 3D textures to DXT.")
                    continue
                elif bitm_tag_info.type == 2 and fmt == 17:
                    print("Cannot convert cubemaps textures to P8.")
                    continue

            if conv_flags.get(fp):
                setattr(conv_flags[fp], flag_name, new_value)

            update_color(i)

    def initialize_conversion_flags(self):
        data_dir = self.data_dir_path.get()
        for fp, info in self.bitmap_tag_infos.items():
            if not info:
                continue

            self.conversion_flags[fp] = flags = ConversionFlags()

            flags.platform = info.platform
            flags.swizzled = info.swizzled
            flags.extract_path = splitext(join(data_dir, fp))[0]

    def scan_pressed(self):
        if self._processing:
            return

        new_tags_dir = self.scan_dir_path.get()
        if not exists(new_tags_dir):
            print("The specified directory to scan does not exist.")
            return

        self.conversion_flags = {}
        self.bitmap_tag_infos = {}
        self.bitmap_display_windows = {}
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

                    try:
                        bitm_tag = self.bitm_def.build(filepath=join(root, filename))
                    except Exception:
                        print(format_exc())
                        bitm_tag = None

                    if not bitm_tag:
                        print("Could not load: %s" % join(root, filename))
                        continue

                    self.bitmap_tag_infos[fp] = BitmapTagInfo(bitm_tag)

            print("    Finished in %s seconds." % int(time() - s_time))
        except Exception:
            print(format_exc())

        self.initialize_conversion_flags()
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
        s_time = time()
        c_time = s_time

        if self.read_only.get():
            print("Creating log...")
            try:
                if self.make_log() and self.open_log.get():
                    self.show_log_in_text_editor()
            except Exception:
                print(format_exc())
                print("Could not create log")

        else:
            print("Converting bitmaps...")
            tags_dir = self.loaded_tags_dir
    
            for fp in sorted(self.bitmap_tag_infos):
                try:
                    if self._cancel_processing:
                        print("Conversion cancelled by user.")
                        break

                    bitmap_info = self.bitmap_tag_infos[fp]
                    conv_flags = self.conversion_flags[fp]
                    pruning = conv_flags.prune_tiff
                    extracting = conv_flags.extract_to != 0
                    converting = get_will_be_converted(conv_flags, bitmap_info)
                    if pruning or converting or extracting:
                        tag = self.bitm_def.build(filepath=join(tags_dir, fp))
                        if pruning:
                            tag.data.tagdata.compressed_color_plate_data.data = bytearray()

                        if converting or extracting:
                            convert_bitmap_tag(tag, conv_flags, bitmap_info)

                        if converting or pruning:
                            tag.serialize(temp=False, calc_pointers=False,
                                          backup=self.backup_tags.get())

                        self.bitmap_tag_infos.pop(fp, None)
                        self.conversion_flags.pop(fp, None)
                        self.bitmap_display_windows.pop(fp, None)

                        del tag
                        gc.collect()
                except Exception:
                    print(format_exc())
                    print("Could not convert: %s" % fp)

        print("    Finished in %s seconds." % int(time() - s_time))

        self._processing = self._cancel_processing = False
        self.after(0, self.enable_settings)
        self.after(0, self.tag_list_frame.display_sorted_tags)

    def cancel_pressed(self):
        if self._processing:
            self._cancel_processing = True

    def enable_settings(self):
        self._enable_disable_settings(False)

    def disable_settings(self):
        self._enable_disable_settings(True)

    def _enable_disable_settings(self, disable):
        if disable != self._settings_enabled:
            return

        new_state = tk.DISABLED if disable else tk.NORMAL
        for w in self.checkbuttons + self.buttons:
            w.config(state=new_state)

        self._settings_enabled = not disable
        if disable:
            self._settings_enabled = False
            new_state = "readonly"

        for w in self.spinboxes:
            w.config(state=new_state)

        for w in self.menus:
            if disable:
                w.disable()
            else:
                w.enable()

    def populate_settings(self):
        if self._populating_settings or self._processing:
            return

        self._populating_settings = True
        settings_enabled = self._settings_enabled
        try:
            self.enable_settings()
            menus = (self.platform_menu, self.format_menu,
                     self.extract_to_menu, self.prune_tiff_menu,
                     self.multi_swap_menu, self.generate_mips_menu,
                     self.ay8_channel_src_menu, self.ck_transparency_menu,
                     self.swap_a8y8_menu, self.swizzled_menu)
            for w in menus:
                w.sel_index = -1

            for w in (self.downres_box, self.alpha_bias_box):
                w.delete(0, tk.END)

            conv_flags = self.conversion_flags
            tag_paths = self.tag_list_frame.selected_paths
            comb_flags = None
            if not tag_paths:
                self._populating_settings = False
                return

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

                for name in ("platform", "multi_swap", "prune_tiff",
                             "mono_channel_to_keep", "extract_to", "new_format",
                             "swizzled", "mono_swap", "ck_trans", "mip_gen",
                             "downres", "alpha_bias"):
                    if getattr(flags, name) != getattr(comb_flags, name):
                        setattr(comb_flags, name, -1)

            self.platform_menu.sel_index = comb_flags.platform
            self.multi_swap_menu.sel_index = comb_flags.multi_swap
            self.ay8_channel_src_menu.sel_index = comb_flags.mono_channel_to_keep
            self.extract_to_menu.sel_index = comb_flags.extract_to
            self.prune_tiff_menu.sel_index = comb_flags.prune_tiff
            self.format_menu.sel_index = comb_flags.new_format
            self.swizzled_menu.sel_index = comb_flags.swizzled
            self.swap_a8y8_menu.sel_index = comb_flags.mono_swap
            self.ck_transparency_menu.sel_index = comb_flags.ck_trans
            self.generate_mips_menu.sel_index = comb_flags.mip_gen

            for w in menus:
                if w.sel_index < 0:
                    w.update_label("<mixed values>")

            for name, w in (("downres", self.downres_box),
                            ("alpha_bias", self.alpha_bias_box)):
                w.delete(0, tk.END)
                val = getattr(comb_flags, name)
                w.insert(0, str(val) if val >= 0 else "<mixed values>")

            if not settings_enabled:
                self.disable_settings()
        except Exception:
            print(format_exc())
        self._populating_settings = False

    def populate_bitmap_info(self):
        if self._populating_bitmap_info or self._processing:
            return

        self._populating_bitmap_info = True
        try:
            try:
                i = int(self.curr_bitmap_spinbox.get())
            except ValueError:
                i = 0

            for w in (self.curr_width_entry, self.curr_height_entry,
                      self.curr_depth_entry, self.curr_mip_entry,
                      self.curr_bitmap_spinbox, self.max_bitmap_entry):
                w.config(state=tk.NORMAL)

            for w in (self.curr_type_menu, self.curr_format_menu,
                      self.curr_swizzled_menu,
                      self.curr_platform_menu, self.curr_has_tiff_menu):
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

                    if i >= bitm_ct:
                        i = 0

                    self.curr_bitmap_spinbox.insert(tk.END, str(i))
                    self.curr_bitmap_spinbox.config(to=bitm_ct - 1)
                    self.max_bitmap_entry.insert(tk.END, str(bitm_ct - 1))
                    if i < bitm_ct:
                        bitm_info = bitm_tag_info.bitmap_infos[i]

                        self.curr_type_menu.sel_index = bitm_info.type
                        self.curr_format_menu.sel_index = bitm_info.format
                        self.curr_swizzled_menu.sel_index = bitm_info.swizzled
                        self.curr_platform_menu.sel_index = bitm_tag_info.platform
                        self.curr_has_tiff_menu.sel_index = bitm_tag_info.tiff_data_size > 0

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

    def scan_dir_browse(self):
        if self._processing:
            return

        load_dir = self.scan_dir_path.get()
        if not load_dir:
            load_dir = self.app_root.last_load_dir
        dirpath = askdirectory(initialdir=load_dir,
                               parent=self, title="Select directory to scan")
        if not dirpath:
            return

        dirpath = sanitize_path(dirpath)
        if not dirpath.endswith(PATHDIV):
            dirpath += PATHDIV

        self.scan_dir_path.set(dirpath)
        if self.app_root:
            self.app_root.last_load_dir = dirname(dirpath)

    def data_dir_browse(self):
        if self._processing:
            return

        load_dir = self.data_dir_path.get()
        if not load_dir:
            load_dir = self.app_root.last_load_dir
        dirpath = askdirectory(initialdir=self.data_dir_path.get(),
                               parent=self, title="Select directory to scan")
        if not dirpath:
            return

        dirpath = sanitize_path(dirpath)
        if not dirpath.endswith(PATHDIV):
            dirpath += PATHDIV

        curr_data_dir = self.data_dir_path.get()
        for flags in self.conversion_flags.values():
            if not flags:
                continue

            flags.extract_path = join(
                dirpath, relpath(flags.extract_path, curr_data_dir))

        self.data_dir_path.set(dirpath)

    def log_browse(self):
        if self._processing:
            return

        load_dir = dirname(self.log_file_path.get())
        if not load_dir:
            load_dir = self.app_root.last_load_dir
        fp = asksaveasfilename(
            initialdir=load_dir, title="Save scan log to...", parent=self,
            filetypes=(("bitmap optimizer log", "*.log"), ('All', '*')))

        if not fp:
            return

        if not splitext(fp)[-1]:
            fp += ".log"

        self.log_file_path.set(sanitize_path(fp))
        if self.app_root:
            self.app_root.last_load_dir = dirname(self.log_file_path.get())

    def get_will_be_processed(self, tag_path):
        info = self.bitmap_tag_infos.get(tag_path)
        if self.read_only.get() or (not info or not info.bitmap_infos):
            return False

        if self.conversion_flags[tag_path].prune_tiff and info.tiff_data_size:
            return True
        elif self.conversion_flags[tag_path].extract_to != 0:
            return True
        return get_will_be_converted(self.conversion_flags[tag_path],
                                     self.bitmap_tag_infos[tag_path])

    def make_log(self):
        attempts = 0
        success = True

        while attempts < 2:
            log_file_path = self.log_file_path.get()
            try:
                if not exists(dirname(log_file_path)):
                    log_file_path = None

                if not log_file_path.endswith(".log"):
                    log_file_path += ".log"
            except Exception:
                log_file_path = None

            attempts += 1
            if attempts < 2 and not log_file_path:
                self._processing = False
                self.log_file_path.set("")
                self.log_browse()

        logstr = "Mozzarilla Bitmap Converter tagset log:\n\n"

        total_size = 0
        tiff_data_size = 0
        for filename, info in self.bitmap_tag_infos.items():
            total_size += getsize(normpath(join(self.loaded_tags_dir, filename)))
            tiff_data_size += info.tiff_data_size

        logstr += "%s bitmaps total\n%sKB of bitmap data\n%sKB of TIFF data" % (
            len(self.bitmap_tag_infos), total_size // 1024, tiff_data_size // 1024)

        formatted_strs = {}
        tag_counts = [0, 0, 0]
        tag_header_strs = ("2D Textures", "3D Textures", "Cubemaps")
        base_str = "Bitmap %s\t--- WxHxD: %sx%sx%s\t--- Mipmaps: %s\n"

        tag_info_strs = {}

        for typ in range(3):
            formatted_strs[typ] = [''] * 18
            tag_info_strs[typ]  = [''] * 18

            for fmt in range(len(BITMAP_FORMATS)):
                if "?" not in BITMAP_FORMATS[fmt]:
                    formatted_strs[typ][fmt] = "\n\n\t%s" % BITMAP_FORMATS[fmt]
                    tag_info_strs[typ][fmt] = {}

        for filename, info in self.bitmap_tag_infos.items():
            fp = normpath(join(self.loaded_tags_dir, filename))
            filesize = (getsize(fp) - info.tiff_data_size) // 1024
            tagstr = ("\n\t\t" + fp +
                      "\n\t\t\tCompiled tag size\t= %sKB\n" %
                      ("less than 1" if filesize <= 0 else str(filesize)))

            if info.tiff_data_size > 0:
                tagstr += "\t\t\tTIFF data size\t= %sKB\n" % (
                    "less than 1" if info.tiff_data_size < 1024
                    else info.tiff_data_size // 1024)

            i = 0
            for bitm_info in info.bitmap_infos:
                tagstr += ("\t\t\t" + base_str %
                           (i, bitm_info.width, bitm_info.height,
                            bitm_info.depth, bitm_info.mipmaps))
                i += 1

            tag_strs = tag_info_strs[info.type][info.format]
            tag_strs.setdefault(filesize, [])
            tag_strs[filesize].append(tagstr)

        for typ in range(3):
            for fmt in VALID_FORMAT_ENUMS:
                for size in reversed(sorted(tag_info_strs[typ][fmt])):
                    for tagstr in tag_info_strs[typ][fmt][size]:
                        tag_counts[typ] += 1
                        formatted_strs[typ][fmt] += tagstr

        for typ in range(3):
            logstr += "\n\n%s:\n\tCount = %s%s" % (
                tag_header_strs[typ], tag_counts[typ],
                ''.join(formatted_strs[typ]))

        if log_file_path:
            try:
                with open(log_file_path, "w") as f:
                    f.write(logstr)
            except Exception:
                print(format_exc())
                success = False
        else:
            print(logstr)
            success = False

        return success


class BitmapConverterList(tk.Frame, BinillaWidget, HaloBitmapDisplayBase):
    listboxes = ()
    reverse_listbox = False
    toggle_to = True
    sort_method = 'path'

    displayed_paths = ()
    selected_paths = ()

    _populating = False

    format_count = 18
    type_count = 4

    def __init__(self, master, **options):
        tk.Frame.__init__(self, master, **options)

        self.formats_shown = [True] * self.format_count
        self.types_shown   = [True] * self.type_count
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
            label="Sort Ascending", command=lambda:
            self.display_sorted_tags(None, False))
        self.sort_menu.add_command(
            label="Sort Descending", command=lambda:
            self.display_sorted_tags(None, True))
        self.sort_menu.add_separator()

        self.sort_menu.add_command(
            label="Sort by Filepath", command=lambda:
            self.display_sorted_tags('path'))
        self.sort_menu.add_command(
            label="Sort by Bitmap data size", command=lambda:
            self.display_sorted_tags('size'))
        self.sort_menu.add_command(
            label="Sort by Bitmap format", command=lambda:
            self.display_sorted_tags('format'))
        self.sort_menu.add_command(
            label="Sort by Bitmap type", command=lambda:
            self.display_sorted_tags('type'))

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
            tk.Listbox(self, height=5, exportselection=False,
                       yscrollcommand=self._path_scrolled,
                       xscrollcommand=self.hsb.set))
        self.listboxes.append(
            tk.Listbox(self, width=8, height=5, exportselection=False,
                       yscrollcommand=self._size_scrolled))
        self.listboxes.append(
            tk.Listbox(self, width=11, height=5, exportselection=False,
                       yscrollcommand=self._format_scrolled))
        self.listboxes.append(
            tk.Listbox(self, width=6, height=5, exportselection=False,
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
            self.listboxes[i].bind('<Double-Button-1>', lambda e, idx=i:
                                   self.display_selected_tag(idx))
            self.listboxes[i].bind('<Return>', lambda e, idx=i:
                                   self.display_selected_tag(idx))
            if i != 0:
                self.listboxes[i].bind('<<ListboxSelect>>', lambda e, idx=i:
                                       self.select_path_listbox(idx))

        self.hsb.pack(side="bottom", fill="x")
        self.vsb.pack(side="right",  fill="y")
        self.path_listbox.pack(side="left", fill="both", expand=True)
        for listbox in self.listboxes[1: ]:
            listbox.pack(side="left", fill="both")

        self.apply_style()

    def get_p8_palette(self, tag=None):
        if not self.master.use_stubbs_p8 or not self.master.use_stubbs_p8.get():
            return HALO_P8_PALETTE
        return STUBBS_P8_PALETTE

    @property
    def path_listbox(self): return self.listboxes[0]
    @property
    def size_listbox(self): return self.listboxes[1]
    @property
    def format_listbox(self): return self.listboxes[2]
    @property
    def type_listbox(self): return self.listboxes[3]

    def apply_style(self, seen=None):
        BinillaWidget.apply_style(self, seen)
        self.populate_tag_list_boxes()

    def post_rightclick_menu(self, event, menu):
        self.update_sort_menu()
        menu.post(event.x_root, event.y_root)

    def reset_listboxes(self):
        self.selected_paths = set()
        self.displayed_paths = []
        for listbox in self.listboxes:
            listbox.delete(0, tk.END)

    def set_selected_tags_list(self, event=None):
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
        self.display_sorted_tags()
        self.master.populate_settings()

    def update_sort_menu(self):
        sort_menu_strs = []
        for i in range(10):
            try:
                label = self.sort_menu.entryconfig(i)["label"][-1]
            except Exception:
                label = ""

            sort_menu_strs.append(label.rstrip(u' \u2713'))

        sort_menu_strs[0] = "Toggle all to %s" % BITMAP_PLATFORMS[int(self.toggle_to)]

        if self.reverse_listbox:
            sort_menu_strs[4] += u' \u2713'
        else:
            sort_menu_strs[3] += u' \u2713'

        if self.sort_method == 'path':
            sort_menu_strs[6] += u' \u2713'
        elif self.sort_method == 'size':
            sort_menu_strs[7] += u' \u2713'
        elif self.sort_method == 'format':
            sort_menu_strs[8] += u' \u2713'
        elif self.sort_method == 'type':
            sort_menu_strs[9] += u' \u2713'

        for i in range(len(sort_menu_strs)):
            if sort_menu_strs[i]:
                self.sort_menu.entryconfig(i, label=sort_menu_strs[i])

    def invert_selection(self):
        for i in range(self.path_listbox.size()):
            fp = self.path_listbox.get(i)
            if fp in self.selected_paths:
                self.selected_paths.remove(fp)
            else:
                self.selected_paths.add(fp)

        self.synchronize_selection()
        self.set_selected_tags_list()

    def synchronize_selection(self):
        self.path_listbox.selection_clear(0, tk.END)
        for i in range(self.path_listbox.size()):
            if self.path_listbox.get(i) in self.selected_paths:
                self.path_listbox.selection_set(i)

    def display_selected_tag(self, src_listbox_index=0):
        self.select_path_listbox(src_listbox_index)
        if len(self.selected_paths) != 1 or not self.master.loaded_tags_dir:
            return

        for tag_path in self.selected_paths:
            break

        display_frame = self.master.bitmap_display_windows.get(tag_path)
        if display_frame is None or display_frame() is None:
            tags_dir = self.master.loaded_tags_dir
            tag = self.master.bitm_def.build(filepath=join(tags_dir, tag_path))

            if not tag:
                print("Could not load the tag: %s" % tag_path)
                return

            # the bitmap display frame requires tags_dir to see
            # it as an actual tag rather than a meta tag
            tag.tags_dir = tags_dir

            w = tk.Toplevel(self.master)
            display_frame = weakref.ref(HaloBitmapDisplayFrame(w, tag))

            display_frame().change_textures(self.get_textures(tag))
            display_frame().pack(expand=True, fill="both")

            w.title("Preview: %s" % tag_path)
            w.transient(self.master)

            self.master.bitmap_display_windows[tag_path] = display_frame

        w.update_idletasks()
        display_frame().focus_set()
        self.master.place_window_relative(w)

    def select_path_listbox(self, src_listbox_index=0):
        src_listbox = self.listboxes[src_listbox_index]

        if len(src_listbox.curselection()) > 0:
            self.path_listbox.selection_set(src_listbox.curselection()[0])
            self.set_selected_tags_list()

        if src_listbox_index > 0:
            src_listbox.selection_clear(0, tk.END)

        self.master.populate_bitmap_info()
        self.master.populate_settings()

    def toggle_types_allowed(self, menu_idx, typ):
        if typ == -1:
            for typ in range(self.type_count):
                self.types_shown[typ] = not self.types_shown[typ]
                typ_str = BITMAP_TYPES[typ]
                if self.types_shown[typ]: typ_str += u' \u2713'

                self.types_menu.entryconfig(typ + 1, label=typ_str)
            self.display_sorted_tags()
            return

        typ_str = BITMAP_TYPES[typ]
        self.types_shown[typ] = not self.types_shown[typ]
        if self.types_shown[typ]: typ_str += u' \u2713'

        self.types_menu.entryconfig(menu_idx, label=typ_str)
        self.display_sorted_tags()

    def toggle_formats_allowed(self, menu_idx, fmt):
        if fmt == -1:
            i = 1 if menu_idx == 0 else 0
            for fmt in range(self.format_count):
                if fmt in VALID_FORMAT_ENUMS:
                    self.formats_shown[fmt] = not self.formats_shown[fmt]
                    fmt_str = BITMAP_FORMATS[fmt]
                    if self.formats_shown[fmt]: fmt_str += u' \u2713'

                    self.formats_menu.entryconfig(i, label=fmt_str)
                    i += 1
            self.display_sorted_tags()
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

        remove = set()
        for fp, info in self.master.bitmap_tag_infos.items():
            if not info.pixel_data_size in self.size_map:
                self.size_map[info.pixel_data_size] = []

            try:
                self.type_format_map[info.type][info.format]
                self.size_map[info.pixel_data_size]

                self.type_format_map[info.type][info.format].append(fp)
                self.size_map[info.pixel_data_size].append(fp)
            except IndexError:
                remove.add(fp)

        for fp in remove:
            self.master.conversion_flags.pop(fp, None)
            self.master.bitmap_tag_infos.pop(fp, None)

    def display_sorted_tags(self, sort_by=None, reverse=None):
        if sort_by is None:
            sort_by = self.sort_method

        if reverse is not None:
            self.reverse_listbox = reverse

        self.sort_displayed_tags(sort_by)
        self.after(0, self.populate_tag_list_boxes)

    def sort_displayed_tags(self, sort_by):
        self.displayed_paths = displayed_paths = []
        if not self.master.bitmap_tag_infos:
            return

        if sort_by == 'path':
            for path in sorted(self.master.bitmap_tag_infos.keys()):
                info = self.master.bitmap_tag_infos[path]
                if (self.formats_shown[info.format] and
                    self.types_shown[info.type]):
                    displayed_paths.append(path)

        elif sort_by == 'size':
            for tagsize in sorted(self.size_map):
                for path in self.size_map[tagsize]:
                    info = self.master.bitmap_tag_infos[path]
                    if (self.formats_shown[info.format] and
                        self.types_shown[info.type]):
                        displayed_paths.append(path)

        elif sort_by == 'format':
            for fmt in range(len(self.formats_shown)):
                for typ in range(len(self.types_shown)):
                    if self.formats_shown[fmt] and self.types_shown[typ]:
                        displayed_paths.extend(self.type_format_map[typ][fmt])

        elif sort_by == 'type':
            for typ in range(len(self.types_shown)):
                for fmt in range(len(self.formats_shown)):
                    if self.formats_shown[fmt] and self.types_shown[typ]:
                        displayed_paths.extend(self.type_format_map[typ][fmt])
        else:
            for path in self.master.bitmap_tag_infos.keys():
                info = self.master.bitmap_tag_infos[path]
                if (self.formats_shown[info.format] and
                    self.types_shown[info.type]):
                    displayed_paths.append(path)

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

                self.update_path_listbox_entry_color(tk.END)

            self.synchronize_selection()
        except Exception:
            print(format_exc())

        self._populating = False

    def update_path_listbox_entry_color(self, i):
        fp = self.path_listbox.get(i)
        if self.master.get_will_be_processed(fp):
            self.path_listbox.itemconfig(i, bg='dark green', fg='white')
        else:
            self.path_listbox.itemconfig(i, bg=self.enum_normal_color,
                                         fg=self.text_normal_color,)

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


if __name__ == "__main__":
    BitmapConverterWindow(None).mainloop()
