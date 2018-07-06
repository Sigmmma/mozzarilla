import gc

from array import array
from os.path import getsize, splitext, dirname, join
from threading import Thread
from tkinter.filedialog import asksaveasfilename, askdirectory
from time import sleep, time
from traceback import format_exc

from reclaimer.hek.handler import HaloHandler
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


EXTRACT_TO_OPTIONS = ("", "DDS", "TGA", "PNG")
MULTI_SWAP_OPTIONS = ("", "XBOX --> PC", "PC --> XBOX")
P8_MODE_OPTIONS = ("Auto", "Average")
AY8_OPTIONS = ("Alpha", "Intensity")
BITMAP_PLATFORMS = ("XBOX", "PC")
BITMAP_TYPES = ("2D", "3D", "Cube", "White")
BITMAP_FORMATS = ("A8", "Y8", "AY8", "A8Y8", "????", "????", "R5G6B5",
                  "????", "A1R5G5B5", "A4R4G4B4", "X8R8G8B8", "A8R8G8B8",
                  "????", "????", "DXT1", "DXT3", "DXT5", "P8 Bump")

VALID_FORMAT_ENUMS = (0, 1, 2, 3, 6, 8, 9, 10, 11, 14, 15, 16, 17)
VALID_FORMATS = tuple(BITMAP_FORMATS[i] for i in VALID_FORMAT_ENUMS)

class ConversionFlags:
    platform = "XBOX"
    multi_swap = ""
    p8_mode = "Auto"
    mono_channel_to_keep = "Alpha"

    extract_to = " "
    downres = 0
    cutoff_bias = 127
    new_format = None
    gamma = 1.0

    swizzled = False
    mono_swap = False
    ck_trans = False
    mip_gen = False


class BitmapConverterWindow(tk.Toplevel, BinillaWidget):
    app_root = None
    tag_list_window = None
    help_window = None
    tags_dir = ''
    handler = None

    prune_tiff = None
    read_only = None
    backup_tags = None
    open_log = None

    _processing = False

    def __init__(self, app_root, *args, **kwargs):
        if self.handler is None:
            BitmapConverterWindow.handler = HaloHandler(valid_def_ids=())
        self.handler.reset_tags()
        if "bitm" not in self.handler.defs:
            self.handler.add_def(bitm_def)

        self.app_root = app_root
        kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)

        self.title("Bitmap converter")
        self.resizable(0, 0)
        self.update()
        try:
            try:
                self.iconbitmap(join(curr_dir, '..', 'mozzarilla.ico'))
            except Exception:
                self.iconbitmap(join(curr_dir, 'icons', 'mozzarilla.ico'))
        except Exception:
            print("Could not load window icon.")

        self.default_flags = ConversionFlags()

        self.menubar = tk.Menu(self)
        self.menubar.add_command(label="Toggle all bitmaps to Xbox")
        self.menubar.add_command(label="Invert selection")
        self.menubar.add_command(label="Help", command=self.show_help)
        self.config(menu=self.menubar)

        # make the tkinter variables
        self.prune_tiff = tk.BooleanVar(self)
        self.read_only = tk.BooleanVar(self)
        self.backup_tags = tk.BooleanVar(self)
        self.open_log = tk.BooleanVar(self, True)

        self.scan_dir_path = tk.StringVar(self)
        self.log_file_path = tk.StringVar(self)

        # make the frames
        self.main_frame = tk.Frame(self)
        self.settings_frame = tk.LabelFrame(self.main_frame, text="Settings")
        self.bitmap_info_frame = tk.LabelFrame(self.main_frame, text="Bitmap info")
        self.buttons_frame = tk.Frame(self.main_frame)

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
                                           disabled=True, options=VALID_FORMATS)
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
            self.global_params_frame, text="Prune tiff data",
            variable=self.prune_tiff)
        self.read_only_cbutton = tk.Checkbutton(
            self.global_params_frame, text="Read-only",
            variable=self.read_only)
        self.backup_tags_cbutton = tk.Checkbutton(
            self.global_params_frame, text="Backup tags",
            variable=self.backup_tags)
        self.open_log_cbutton = tk.Checkbutton(
            self.global_params_frame, text="Open log when done",
            variable=self.open_log)


        self.platform_menu = ScrollMenu(self.general_params_frame, menu_width=10,
                                        options=BITMAP_PLATFORMS)
        self.format_menu = ScrollMenu(self.general_params_frame, menu_width=10,
                                      options=VALID_FORMATS)
        self.extract_to_menu = ScrollMenu(self.general_params_frame, menu_width=10,
                                          options=EXTRACT_TO_OPTIONS, sel_index=0)
        self.multi_swap_menu = ScrollMenu(self.general_params_frame, menu_width=10,
                                          options=MULTI_SWAP_OPTIONS, sel_index=0)
        self.downres_box = tk.Spinbox(self.general_params_frame, from_=0,
                                   to=10, width=3, state="readonly")

        self.p8_mode_menu = ScrollMenu(self.format_params_frame, menu_width=10,
                                       options=P8_MODE_OPTIONS, sel_index=0)
        self.swizzled_menu = ScrollMenu(self.format_params_frame, menu_width=10,
                                        options=("No", "Yes"), sel_index=0)
        self.swap_a8y8_menu = ScrollMenu(self.format_params_frame, menu_width=10,
                                        options=("No", "Yes"), sel_index=0)
        self.ck_trans_menu = ScrollMenu(self.format_params_frame, menu_width=10,
                                        options=("No", "Yes"), sel_index=0)
        self.alpha_bias_box = tk.Spinbox(self.format_params_frame, from_=0,
                                         to=255, width=5, state="readonly",
                                         repeatinterval=5)


        self.scan_button = tk.Button(self.buttons_frame, text="Scan")
        self.convert_button = tk.Button(self.buttons_frame, text="Convert")
        self.cancel_button = tk.Button(self.buttons_frame, text="Cancel")


        self.main_frame.pack(expand=True, fill='both')

        self.settings_frame.grid(sticky='news', row=0, column=0)
        self.bitmap_info_frame.grid(sticky='news', row=0, column=1)
        self.buttons_frame.grid(sticky='news', columnspan=2, row=1, column=0,
                                pady=3, padx=3)


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
        self.prune_tiff_cbutton.grid(row=1, column=0, sticky='w')


        self.platform_menu.grid(row=0, column=1, sticky='e')
        self.format_menu.grid(row=1, column=1, sticky='e')
        self.extract_to_menu.grid(row=2, column=1, sticky='e')
        self.multi_swap_menu.grid(row=3, column=1, sticky='e')
        self.downres_box.grid(row=4, column=1, sticky='e')
        i = 0
        for name in ("Platform", "Format", "Extract to",
                     "Multi. swap", "Downres. level"):
            lbl = tk.Label(self.general_params_frame, text=name)
            lbl.grid(row=i, column=0, sticky='w')
            i += 1

        self.p8_mode_menu.grid(row=0, column=1, sticky='e')
        self.swizzled_menu.grid(row=1, column=1, sticky='e')
        self.swap_a8y8_menu.grid(row=2, column=1, sticky='e')
        self.ck_trans_menu.grid(row=3, column=1, sticky='e')
        self.alpha_bias_box.grid(row=4, column=1, sticky='e')
        i = 0
        for name in ("P8 mode", "Swizzled", "Swap A8Y8",
                     "Make DXT1 alpha", "Alpha bias"):
            lbl = tk.Label(self.format_params_frame, text=name)
            lbl.grid(row=i, column=0, sticky='w')
            i += 1


        self.curr_bitmap_label_0.pack(side='left', fill='x')
        self.curr_bitmap_spinbox.pack(side='left', fill='x', expand=True)
        self.curr_bitmap_label_1.pack(side='left', fill='x')
        self.max_bitmap_entry.pack(side='left', fill='x', expand=True)

        self.bitmap_index_frame.grid(row=0, column=0, sticky='we',
                                     columnspan=2, pady=(10, 20))
        self.curr_type_menu.grid(row=1, column=1, sticky='e')
        self.curr_format_menu.grid(row=2, column=1, sticky='e')
        self.curr_platform_menu.grid(row=3, column=1, sticky='e')
        self.curr_swizzled_menu.grid(row=4, column=1, sticky='e')
        self.curr_width_entry.grid(row=5, column=1, sticky='e')
        self.curr_height_entry.grid(row=6, column=1, sticky='e')
        self.curr_depth_entry.grid(row=7, column=1, sticky='e')
        self.curr_mip_entry.grid(row=8, column=1, sticky='e')
        i = 1
        for name in ("Type", "Format", "Platform", "Swizzled",
                     "Width", "Height", "Depth", "Mipmaps"):
            lbl = tk.Label(self.bitmap_info_frame, text=name)
            lbl.grid(row=i, column=0, sticky='w', pady=4)
            i += 1

        self.apply_style()
        self.tag_list_window = BitmapConverterListWindow(self)
        self.reset_bitmap_info()

    def show_help(self):
        try:
            if self.help_window is None:
                self.help_window = BitmapConverterHelpWindow(self)
        except Exception:
            print(format_exc())
            pass

    def close_help(self):
        try:
            self.help_window.destroy()
        except Exception:
            pass

    def apply_style(self, seen=None):
        BinillaWidget.apply_style(self, seen)
        self.update()
        w = self.main_frame.winfo_reqwidth()
        h = self.main_frame.winfo_reqheight()
        self.geometry("%sx%s" % (w, h))
        self.minsize(width=w, height=h)

    def reset_bitmap_info(self):
        for w in (self.curr_type_menu, self.curr_format_menu,
                  self.curr_platform_menu, self.curr_swizzled_menu):
            w.sel_index = -1

        for w in (self.curr_width_entry, self.curr_height_entry,
                  self.curr_depth_entry, self.curr_mip_entry,
                  self.max_bitmap_entry, self.curr_bitmap_spinbox):
            w.delete(0, tk.END)

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
        self.app_root.last_load_dir = dirname(self.log_file_path.get())

    #used when doing a read-only scan of a tagset to figure out what's what
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
        tags = self.handler.tags.get('bitm', ())
        for filepath in tags:
            tag = tags[filepath]
            filesize = (getsize(tag.filepath) -
                        tag.color_plate_data_bytes_size()) // 1024
            tagstr = ("\n" + " "*8 + filepath +
                      "\n" + " "*12 + "Compiled tag size = %sKB\n" %
                      ("less than 1" if filesize <= 0 else str(filesize)))

            for i in range(tag.bitmap_count()):
                tagstr += (" " * 12 + base_str %
                           (i, tag.bitmap_width(i), tag.bitmap_height(i),
                            tag.bitmap_depth(i), tag.bitmap_mipmaps_count(i)) )

            tag_strs = tag_info_strs[tag.bitmap_type()][tag.bitmap_format()]
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

    def convert_bitmap_tag(self, tag, **kwargs):
        '''tons of possibilities here. not gonna try to name
        them. Basically this is the main conversion routine'''
        conversion_flags = tag.tag_conversion_settings
        for i in range(tag.bitmap_count()):
            if not(tag.is_power_of_2_bitmap(i)):
                conversion_report[tag_path] = False
                return False

        if conversion_flags[NEW_FORMAT] < 0:
            new_format = None
        else:
            new_format = FORMAT_NAME_MAP[conversion_flags[NEW_FORMAT]]

        processing = process_bitmap_tag(tag)

        bm = ab.Arbytmap()
        bad_bitmaps = tag.sanitize_mipmap_counts()

        if len(bad_bitmaps) > 0:
            print("ERROR: Bad bitmap block(s) encountered in this tag:\n", tag_path)
            load_status = False
        else:
            load_status = tag.parse_bitmap_blocks()

        #If an error was encountered during the load
        #attempt or the conversion was cancelled we quit
        if root_window and (not load_status or root_window.conversion_cancelled):
            conversion_report[tag_path] = False
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

                if not(channel_to_keep) and format_t == ab.FORMAT_A8:
                    format_t = ab.FORMAT_L8

                if (format_s in (ab.FORMAT_A8, ab.FORMAT_L8, ab.FORMAT_AL8) and
                    format_t in (ab.FORMAT_A8, ab.FORMAT_L8, ab.FORMAT_AL8)):
                    tex_info["format"] = format_s = format_t


            channel_mapping, channel_merge_mapping, format_t = \
                             get_channel_mappings(format_s, mono_swap, format_t,
                                                  multi_swap, channel_to_keep)
            palette_picker = None
            palettize = True

            if format_s == ab.FORMAT_P8:
                palette_picker = P8_PALETTE.argb_array_to_p8_array_auto
            elif format_t != ab.FORMAT_P8:
                palettize = False
            elif ab.CHANNEL_COUNTS[format_s] != 4:
                pass
            elif ck_transparency and format_s not in (ab.FORMAT_X8R8G8B8,
                                                    ab.FORMAT_R5G6B5):
                if p8_mode == 0:
                    # auto-bias
                    palette_picker = P8_PALETTE.argb_array_to_p8_array_auto_alpha
                else:
                    # average-bias
                    palette_picker = P8_PALETTE.argb_array_to_p8_array_average_alpha
            elif p8_mode == 0:
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

            bm.load_new_texture(texture_block = tex_block,
                                texture_info = tex_info)

            # build the initial conversion settings list from the above settings
            conv_settings = dict(
                swizzle_mode=swizzle_mode, one_bit_bias=alpha_cutoff_bias,
                downres_amount=downres_amount, palettize=palettize,
                color_key_transparency=ck_transparency,
                gamma=gamma, mipmap_gen=mipmap_gen)

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

            if export_format != " ":
                path = bm.filepath
                if tag.bitmap_count() > 1:
                    path += ("_"+str(i))
                bm.save_to_file(output_path=path, ext=export_format.lower())

            if status and processing:
                tex_root = tag.data.tagdata.processed_pixel_data.data[i]
                tex_root.parse(initdata=bm.texture_block)
                tag.swizzled(bm.swizzled, i)

                #change the bitmap format to the new format
                tag.bitmap_format(i, I_FORMAT_NAME_MAP[format_t])
            elif not (extracting_texture(tag) or prune_tiff):
                print("Error occurred while attempting to convert the tag:")
                print(tag_path+"\n")
                conversion_report[tag_path] = False
                return False

        if prune_tiff:
            tag.data.tagdata.compressed_color_plate_data.data = bytearray()

        if processing:
            tag.sanitize_bitmaps()
            tag.set_platform(save_as_xbox)
            tag.processed_by_hboc(True)
            tag.add_bitmap_padding(save_as_xbox)

        if processing or prune_tiff:
            try:
                save_status = tag.serialize()
                conversion_report[tag_path] = True
            except Exception:
                print(format_exc())
                conversion_report[tag_path] = save_status = False
            return save_status
        elif export_format == " ":
            conversion_report[tag_path] = False
            return False

        conversion_report[tag_path] = None
        return None

    def get_channel_mappings(self, format_s, mono_swap, format_t,
                             multi_swap, channel_to_keep):
        """Goes through a ton of checks to figure out which channel
        mapping to use for converting(and returns it). Also checks a
        few exception cases where converting to that format would
        be bad and instead resets the target format to the source format"""

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

    def extracting_texture(self, tag):
        '''determines if a texture extraction is to take place'''
        return tag.tag_conversion_settings[EXTRACT_TO] != " "

    def process_bitmap_tag(self, tag):
        flags = tag.tag_conversion_settings

        # check if the bitmap has already been processed, or
        # is a PC bitmap or if we are just creating a debug log
        if tag.processed_by_hboc or not(tag.is_xbox_bitmap):
            format = tag.bitmap_format()

            # if all these are true we skip the tag
            if ( flags[DOWNRES]==0 and flags[MULTI_SWAP] == 0 and
                 flags[NEW_FORMAT] == FORMAT_NONE and flags[MIP_GEN]== False and
                 tag.is_xbox_bitmap == flags[PLATFORM] and
                 (flags[MONO_SWAP] == False or format!= FORMAT_A8Y8) and
                 (tag.swizzled() == flags[SWIZZLED] or
                  FORMAT_NAME_MAP[format] in ab.DDS_FORMATS) ):
                return False
        return True

    def get_will_be_processed(self, tag_path):
        if tag_path not in self.handler.tags.get("bitm", ()):
            return False

        tag = self.handler.tags["bitm"][tag_path]
        if tag.bitmap_count() == 0 or self.read_only.get():
            return False

        return (self.prune_tiff.get() or
                self.process_bitmap_tag(tag) or
                self.extracting_texture(tag))


class BitmapConverterListWindow(tk.Toplevel, BinillaWidget):
    listboxes = ()
    reverse_listbox = False
    populating = False
    sort_method = 'path'

    def __init__(self, master, **options):
        tk.Toplevel.__init__(self, master, **options )

        self.initialize_sort_maps()

        self.protocol("WM_DELETE_WINDOW", lambda *a: None)
        self.title("Bitmap converter: Tags list")
        self.minsize(width=300, height=50)
        self.resizable(1, 1)
        self.update()
        try:
            try:
                self.iconbitmap(join(curr_dir, '..', 'mozzarilla.ico'))
            except Exception:
                self.iconbitmap(join(curr_dir, 'icons', 'mozzarilla.ico'))
        except Exception:
            print("Could not load window icon.")

        self.menubar = tk.Menu(self)
        self.sort_menu = tk.Menu(self.menubar, tearoff=False)
        self.types_menu = tk.Menu(self.menubar, tearoff=False)
        self.formats_menu = tk.Menu(self.menubar, tearoff=False)

        self.sort_menu.add_command(
            label="Filepath", command=lambda:
            self.display_sorted_tags('path', True))
        self.sort_menu.add_command(
            label="Filesize", command=lambda:
            self.display_sorted_tags('size', True))
        self.sort_menu.add_command(
            label="Bitmap type", command=lambda:
            self.display_sorted_tags('type', True))
        self.sort_menu.add_command(
            label="Bitmap format", command=lambda:
            self.display_sorted_tags('format', True))

        self.menubar.add_cascade(label="Sort by", menu=self.sort_menu)
        self.menubar.add_cascade(label="Types shown", menu=self.types_menu)
        self.menubar.add_cascade(label="Formats shown", menu=self.formats_menu)
        self.config(menu=self.menubar)

        for typ in range(len(BITMAP_TYPES)):
            self.types_menu.add_command(
                label="%s %s" % (BITMAP_TYPES[typ], u'\u2713'),
                command=lambda t=typ: self.toggle_types_allowed(t))

        i = 0
        for fmt in VALID_FORMAT_ENUMS:
            self.formats_menu.add_command(
                label="%s %s" % (BITMAP_FORMATS[fmt], u'\u2713'),
                command=lambda i=i, f=fmt:self.toggle_formats_allowed(i, f))
            i += 1

        self.vsb = tk.Scrollbar(self, orient="vertical")
        self.hsb = tk.Scrollbar(self, orient="horizontal")
        self.listboxes = []
        self.listboxes.append(
            tk.Listbox(self, yscrollcommand=self._path_scrolled,
                       xscrollcommand=self.hsb.set))
        self.listboxes.append(tk.Listbox(
            self, width=11, yscrollcommand=self._format_scrolled))
        self.listboxes.append(tk.Listbox(
            self, width=6, yscrollcommand=self._type_scrolled))
        self.listboxes.append(tk.Listbox(
            self, width=8, yscrollcommand=self._size_scrolled))

        self.hsb.config(command=self.path_listbox.xview)
        self.vsb.config(command=self._scroll_all_yviews)
        self.listboxes[0].bind('<<ListboxSelect>>', self.set_selected_tags_list)

        for i in range(len(self.listboxes)):
            self.listboxes[i].config(selectmode=tk.EXTENDED, highlightthickness=0)
            self.listboxes[i].bind('<<ListboxSelect>>',
                                   lambda idx=i: self.select_path_listbox(idx))

        self.hsb.pack(side="bottom", fill="x")
        self.vsb.pack(side="right",  fill="y")
        self.path_listbox.pack(side="left", fill="both", expand=True)
        for listbox in self.listboxes[1: ]:
            listbox.pack(side="left", fill="both")

        self.transient(self.master)

        '''
        for i in range(30):
            self.path_listbox.insert(tk.END, "asdf\\qwer\\%s.bitmap" % i)
            self.format_listbox.insert(tk.END, BITMAP_FORMATS[i % 18])
            self.type_listbox.insert(tk.END, BITMAP_TYPES[i % 4])
            self.size_listbox.insert(tk.END, str(i))'''
        self.apply_style()

    @property
    def path_listbox(self): return self.listboxes[0]
    @property
    def format_listbox(self): return self.listboxes[1]
    @property
    def type_listbox(self): return self.listboxes[2]
    @property
    def size_listbox(self): return self.listboxes[3]

    def reset_lists(self):
        for listbox in self.listboxes:
            listbox.delete(0, END)

    def initialize_sort_maps(self):
        self.tag_display_map = []
        self.selected_tags = []

        self.formats_shown = [True] * len(BITMAP_FORMATS)
        self.types_shown   = [True] * len(BITMAP_TYPES)
        self.type_format_map = []
        self.size_map = {}

        for typ in range(4):
            self.type_format_map.append([])
            for fmt in range(18):
                self.type_format_map[typ].append([])

    def set_selected_tags_list(self, event=None):
        '''used to set which tags are selected when the tags listbox
        is clicked so we can easily edit their conversion variables'''
        self.selected_tags = []
        indices = self.path_listbox.curselection()
        if len(indices) > 1:
            for i in indices:
                self.selected_tags.append(self.tag_display_map[int(i)])
        elif len(indices) == 1:
            self.selected_tags = [self.tag_display_map[int(indices[0])]]
            self.master.update_window_settings()

    def invert_selection(self):
        if not self.master.tags_loaded:
            return

        self.tag_list_listbox.selection_clear(first=0, last=tk.END)
        for index in range(len(self.displayed_tag_index_mapping)):
            filepath = self.displayed_tag_index_mapping[index]

            #if the index wasn't selected we select it
            if filepath not in self.selected_tags:
                self.tag_list_listbox.selection_set(index)
        self.set_selected_tags_list()

    def select_path_listbox(self, src_listbox_index=None):
        listbox = self.listboxes[src_listbox_index]
        if len(listbox.curselection()) > 0:
            self.path_listbox.selection_set(listbox.curselection()[0])
            self.set_selected_tags_list()

    def toggle_types_allowed(self, typ):
        typ_str = BITMAP_TYPES[typ]
        self.types_shown[typ] = not self.types_shown[typ]
        if self.formats_shown[typ]:
            typ_str += " " + u'\u2713'

        self.types_menu.entryconfig(menu_element, label=typ_str)
        self.display_sorted_tags()

    def toggle_formats_allowed(self, menu_element, fmt):
        fmt_str = BITMAP_FORMATS[fmt]
        self.formats_shown[fmt] = not self.formats_shown[fmt]
        if self.formats_shown[fmt]:
            fmt_str += " " + u'\u2713'

        self.formats_menu.entryconfig(menu_element, label=fmt_str)
        self.display_sorted_tags()

    def display_sorted_tags(self, sort_by=None, allow_reverse=False):
        if sort_by is None:
            sort_by = self.sort_method

        self.reverse_listbox = not self.reverse_listbox and allow_reverse
        self.build_display_map(sort_by)
        self.populate_tag_list_boxes()

    def build_display_map(self, sort_by):
        if not self.master.handler.tags_loaded or self.populating:
            return

        self.tag_display_map = []
        bitmaps = self.handler.tags["bitm"]
        if sort_by == 'path':
            for path in sorted(bitmaps.keys()):
                tag = bitmaps[path]
                if tag and tag.bitmap_count()!= 0:
                    if (self.formats_shown[tag.bitmap_format()] and
                        self.types_shown[tag.bitmap_type()]):
                        display_map.append(path)

        elif sort_by == 'size':
            size_mapping = sorted(self.size_map)
            for tagsize in size_mapping:
                for path in self.size_map[tagsize]:
                    tag = bitmaps[path]
                    if (self.formats_shown[tag.bitmap_format()] and
                        self.types_shown[tag.bitmap_type()]):
                        display_map.append(path)

        elif sort_by == 'format':
            for typ in range(len(self.types_shown)):
                for fmt in range(len(self.formats_shown)):
                    if self.formats_shown[fmt] and self.types_shown[typ]:
                        display_map.extend(self.type_format_map[typ][fmt])

        elif sort_by == 'type':
            for fmt in range(len(self.formats_shown)):
                for typ in range(len(self.types_shown)):
                    if self.formats_shown[fmt] and self.types_shown[typ]:
                        display_map.extend(self.type_format_map[typ][fmt])

        self.sort_method = sort_by
        if self.reverse_listbox:
            display_map.reverse()

    def build_tag_sort_mappings(self):
        for tagpath in self.master.handler.tags["bitm"]:
            tag = self.master.handler.tags["bitm"][tagpath]
            size = tag.pixel_data_bytes_size()

            if not size in self.bitmaps_indexed_by_size:
                self.size_map[size] = []

            self.type_format_map[tag.bitmap_type()][tag.bitmap_format()].append(tagpath)
            self.size_map[size].append(tagpath)

    def populate_tag_list_boxes(self):
        if self.populating:
            return

        self.populating = True
        try:
            self.reset_lists()
            for i in range(len(self.tag_display_map)):
                filepath = self.tag_display_map[i]
                tag = self.handler.tags["bitm"][filepath]
                size = tag.pixel_data_bytes_size()
                if size < 1024:
                    size_str += str(bitmap_size) + "  B"
                elif size < 1024**2:
                    size_str += str((size + 512) // 1024) + "  KB"
                else:
                    size_str += str((size + 1024**2 // 2) // 1024**2) + "  MB"

                self.set_listbox_entry_color(tk.END, filepath)
                self.path_listbox.insert(tk.END, filepath)
                self.format_listbox.insert(tk.END, BITMAP_FORMATS[tag.bitmap_format()])
                self.type_listbox.insert(tk.END, BITMAP_TYPES[tag.bitmap_type()])
                self.size_listbox.insert(tk.END, size_str)
        except Exception:
            print(format_exc())

        self.populating = False

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


#BitmapConverterWindow(None)

class BitmapConverterHelpWindow(tk.Toplevel, BinillaWidget):

    def __init__(self, *a, **options):
        tk.Toplevel.__init__(self, *a, **options)

        self.title("Bitmap Converter Help")
        self.geometry("440x400")
        self.resizable(0, 1)
        self.minsize(width=300, height=100)
        self.update()
        try:
            try:
                self.iconbitmap(join(curr_dir, '..', 'mozzarilla.ico'))
            except Exception:
                self.iconbitmap(join(curr_dir, 'icons', 'mozzarilla.ico'))
        except Exception:
            print("Could not load window icon.")

        self.protocol("WM_DELETE_WINDOW", self.close_help)

        #Make the menu bar
        self.help_window_menubar = tk.Menu(self)
        strings = ("Steps to using this program",
                   "Global Parameters", "General Parameters",
                   "Multipurpose Swap", "Format Specific Parameters",
                   "Format Conversion", "Miscellaneous")

        for i in range(len(strings)):
            self.help_window_menubar.add_command(label=strings[i],
                             command=lambda i=i:(self.change_displayed_help(i)))

        self.config(menu=self.help_window_menubar)
        self.help_window_scrollbar_y = tk.Scrollbar(self, orient="vertical")

        self.displayed_help_text_box = tk.Text(
            self, bg='#ece9d8', state=tk.NORMAL,
            yscrollcommand=self.help_window_scrollbar_y.set)
        self.displayed_help_text_box.insert(
            tk.INSERT, "Click a button on the menubar above.")
        self.displayed_help_text_box.config(state=tk.NORMAL, wrap=tk.WORD)

        self.help_window_scrollbar_y.config(
            command=self.displayed_help_text_box.yview)

        self.help_window_scrollbar_y.pack(side="right", fill="y")
        self.displayed_help_text_box.pack(side="left",fill="both", expand=True)
        self.transient(self.master)
        self.apply_style()

    def close_help(self):
        self.master.help_window = None
        tk.Toplevel.destroy(self)

    def change_displayed_help(self, help_type):
        self.displayed_help_text_box.delete('0.0', tk.END)

        if help_type == 0:
            new_help_string = ('Steps:\n\n1: click "Browse..." and select the folder containing bitmaps that you want to operate on. ' +
                               'This does not have to be a root tags folder, just a folder containing bitmap tags.\n\n' +
                               '2: Hit "Load" and wait for the program to say it is finished indexing and loading all the tags.\n\n' +
                               '3: Choose a tag or multiple tags in the "tag List" window and, in the main window, specify what format you ' +
                               'want them converted to, how many times to cut the resolution in half, and any other conversion settings.\n\n' +
                               '4: Hit "Run"\n\n5: Go make a sandwich cause this may take a while.....\n\n' +
                               '6: Once the conversion is finished, a debug log will be created in the folder where the bitmap converter is ' +
                               "located and the tag list will be cleared. The log's name will be the timestamp of when it was created.")

        elif help_type == 1:
            new_help_string = ("---Prune Tiff data---\n   Removes the uncompressed original TIFF data from the tag to" +
                               ' reduce its size. This data is pruned by tool when the tag is compiled into a map, but if you wish to reduce'+
                               ' the size of your tags folder or reduce the size of tags you upload to Halomaps, then this may come of use.'+
                               '\n\n\n---Backup old tags---\n   Tells the program to rename the tag being modified with a ".backup" extension' +
                               ' after it has completely written the new, modified tag. Only the oldest backup will be kept.'+
                               '\n\n\n---Read only mode---\n   Prevents the program from making edits to tags. Instead, a detailed log will be' +
                               ' created containing a list of all the bitmaps located in the folder that was specified. The bitmaps will be sorted' +
                               ' by type(2d, 3d, cubemap), then format(r5g6b5, dxt1, a8r8g8b8, etc), then the number of bytes the pixel data takes up.'+
                               '\n\n\n---Write debug log---\n   Tells the program to write a log of any successes and errors encountered while' +
                               ' preforming the conversion. If a tag is skipped it will be reported as an error.')
        elif help_type == 2:
            new_help_string = ('---Save as Xbox/PC tag---\n   Xbox and PC bitmaps are slightly different in the way they are saved. Xbox has the' +
                               ' pixel data for each bitmap padded to a certain multiple of bytes and cubemaps have the order of their mipmaps and' +
                               ' faces changed. A few other differences exist, but these all make a big difference. Save to the correct format.' +
                               '\n\n---Save as swizzled/un-swizzled---\n   Texture swizzling is not supported on PC Halo, but is required for good' +
                               ' preformance in non-DXT bitmaps on Xbox Halo. Swizzling swaps pixels around in a texture and makes them unviewable to' +
                               ' humans. For PC, save as un-swizzled; for Xbox, save as swizzled. DXT textures can not be swizzled so'+" don't"+' worry.' +
                               '\n\n---Number of times to halve resolution---\n   I tried to think of a shorter way to phrase it, I really did. This is' +
                               ' pretty obvious, but what' + " isn't" + ' so obvious is that if a bitmap has mipmaps the way the program will halve' +
                               ' resolution is by removing however many of the biggest mipmaps you tell it to.' +
                               '\n   If no mipmaps exist (HUD elements for example) the program will use a slower method of downresing, using a simple' +
                               ' bilinear filter to merge pixels.')
        elif help_type == 3:
            new_help_string = ('   PC multipurpose bitmaps channel usage:\nAlpha: Color Change\nRed: Detail Mask\nGreen:' +
                               ' Self Illumination\nBlue: Specular\Reflection\n\n   Xbox multipurpose bitmaps channel usage:' +
                               ' \nAlpha: Detail Mask\nRed: Specular\Reflection\nGreen: Self Illumination\nBlue: Color change\n\n   This program can swap the' +
                               ' channels from PC order to Xbox order or vice versa. If you want to swap them though, make sure you are converting to a' +
                               " format that supports all the channels that you want to keep. For example, swapping an Xbox texture's channels to PC will" +
                               ' require an alpha channel in the new texture if you want to keep the color change channel.\n\n***NOTE*** If a' +
                               ' multipurpose swap setting is used then it will override the "Swap A8Y8 channels" setting if it is also set.')
        elif help_type == 4:
            new_help_string = ("---Alpha cutoff bias---\n   Some formats (DXT1 and A1R5G5B5) are able to have an alpha channel, but it's limited to one bit." +
                               ' This means the only possible values are solid white or solid black. "Alpha cutoff bias" is used as the divider where' +
                               ' an alpha value above it is considered solid white and a value below it is considered solid black. The default value is 127.' +
                               '\n\n---P-8 Bump Conversion Mode---\n   P8-bump only has a palette of 250 colors to choose from and when you compress a 32bit' +
                               ' or 16bit texture to it you are likely to lose some detail. This palette does not at all cover the full range of normals that' +
                               ' you may see in a normal map, and in fact actually misses a lot of the top left, top right, bottom left, and bottom right' +
                               ' tangent vectors that you may see. The two modes I have created each use the palette differently to achieve different results.' +
                               "\n   I could go into the specifics of this problem and how/why these two conversion methods exist, but here's the short simple" +
                               ' answer: Auto-bias is good when you want to preserve the depth of the normal map and Average-bias is good when you want to' +
                               ' preserve the smoothness of the normal map. Auto-bias sacrifices smoothness to allow the normal maps to stay vibrant and strong' +
                               " while Average-bias sacrifices the depth and strength of the normal map to allow the color gradient to stay more or less smooth." +
                               '\n   The default, and usually the best mode to use, is Auto-bias as the drop in smoothness is usually unnoticible.' +
                               '\n\n---Monochrome channel to keep---\n   In A8 format only the alpha data is stored and the intensity channel(RGB merged) is' +
                               ' assumed to be solid black.\n   In Y8 only the intensity channel is stored and the alpha is assumed to be solid white.' +
                               '\n   In AY8 only the pixel data of 1 channel is stored (just like in A8 and Y8), but this pixel data is used for both the' +
                               ' alpha and intensity channels. That means the same exact image is shared between the alpha and intensity channels no' +
                               ' matter what. This is useful for reticles for example.\n   This setting serves two purposes; to specify whether you want to' +
                               ' convert to A8 or Y8 when you select "A8/Y8*", and to specify which one of these two channels to keep when you convert to AY8.' +
                               ' Since only either the alpha or intensity pixel data is saved when converting to AY8 you need to specify which to use.' +
                               ' The default setting is intensity.\n\n---Swap A8Y8 channels---\n   On PC, HUD textures used in meters(like health and ammo)' +
                               ' have to be 32bit color. The RGB channels are used for the image that is displayed and the alpha is used for the gradient mask'
                               ' that erases parts of the meter if they are below a certain value.\n   On XBOX, HUD textures used in meters(like health and' +
                               ' ammo) have to be in a monochrome format. The alpha channel is used for the image that is displayed and the intensity channel' +
                               ' is used for the gradient mask that erases parts of the meter if they are below a certain value.\n   HUD meters converted from' +
                               ' PC to Xbox need to have their intensity and alpha channels swapped. This setting will swap them when you convert to or from' +
                               " an A8Y8 bitmap.\n\n---Color-Key Transparency---\n   You may know the DXT formats by Guerilla's names:" +
                               '"Compressed with color-key transparency"(DXT1), "Compressed with explicit alpha"(DXT3), and "Compressed with interpolated alpha"' +
                               '(DXT5). DXT1 bitmaps are actually capable of having an alpha channel, though it has some strict limitations. First off the alpha' +
                               " channel is 1bit, meaning either solid white or solid black. The other, BIGGER, limitation is that if a pixel's alpha is set to" +
                               ' full black then the red, green, and blue for that pixel are also full black.\n   This type of alpha channel is perfect for things' +
                               " where it renders as transparency, like on the holes for the warthog's chaingun belt, but should NEVER be used for things" +
                               ' where the alpha channel does not function as transparency, like in a multipurpose map or the base map in an environment shader.' +
                               '\n   This setting also determines whether or not an alpha channel is saved with P8 bitmaps. A transparent pixel, just like in DXT1'+
                               ', will be solid black in color.\n\n"Alpha cutoff bias" affects what is determined to be white and what is determined to be black.')
        elif help_type == 5:
            new_help_string = ('---Format to convert to---\nMore or less straight forward, but there are a few miscellaneous things you' +
                               ' should be aware of before you convert formats.\n\n* This program is capable of converting to the DXT formats,' +
                               ' though it uses a slightly different method for compression than Tool uses. This different method actually creates' +
                               ' better UI textures compressed as DXT5 than Tool, having little to no artifacts in most cases. My compression method' +
                               " isn't perfect though, and is absolute poopy crap when compressing normal maps to DXT. If a texture doesn't look good" +
                               ' as DXT when tool creates it try having tool compress it as 32 bit color and have this program turn it into DXT.' +
                               " The results may shock you.\n\n* Not all the formats this program can convert to are" +
                               ' supported by Custom Edition. P8-bump, A8Y8, AY8, Y8, and A8 are Xbox only formats.\n\n* Converting to 32bit color was' +
                               ' an afterthought and as such I did not make a button specifically for it. You CAN convert the Xbox only formats(P8,' +
                               ' A8Y8, AY8, Y8, A8) to 32 bit color though, as this would be the only way to make a usable Custom Edition texture from' +
                               ' them. When a bitmap whose format is one of these(or a dxt format), the "P8*/32Bit"' + " button's function will be" +
                               " converting the bitmaps to 32 bit color. If a 32 or 16 bit texture is selected though, the button's function will " +
                               ' be converting to P-8 bump. If a mixture of these formats is selected the appropriate conversion will be used.' +
                               '\n\n* Bitmaps that are not a power of 2 dimensions will be skipped entirely. So much of this program revolves around' +
                               ' the bitmaps being in power of 2 dimensions that I did not want to try and rework all of it just to get those very' +
                               ' rare bitmap types incorporated. The CMD window will notify you of any bitmaps that are not power of 2 dimensions' +
                               ' and/or corrupt.\n\n---Extract to---\nSelf explanatory, but there are a few things you should be aware of.\n   1: ' +
                               'The folder that you selected when you hit "Browse" and "Load" will be considered as the "tags" folder. The folder that ' +
                               'the "tags" folder is in will have a "data" folder created in it'+"(if it doesn't already exist) and that is where the " +
                               'extracted bitmaps will be placed.\n   2: TGA can not handle having exactly 2 channels(A8Y8), nor can it handle 16 bit color ' +
                               'in the form of R5G6B6 or A4R4G4B4, nor ANY of the DXT formats. DDS will be used if you try to export one of these to TGA')
        elif help_type == 6:
            new_help_string = ('* If the program encounters an error it will be displayed on the Python CLI screen (the black empty CMD screen).' +
                               '\n\n* If you wish to move the windows independent of each other click "Un-dock Windows" on the menu bar.' +
                               '\n\n* The "tag List" window can sort the tags 4 different ways. If the same sorting method is clicked again it' +
                               ' will reverse the order the tags are displayed.\n\n* If you want to only show certain types of tags you can' +
                               ' enable and disable which ones show up in the tag List window. Look under the "Enable/Disable Types" and' +
                               ' "Enable/Disable Formats" and uncheck the types/formats you' + " don't want to show up." +
                               '\n\n* I was originally planning a preview thumbnail, but because it would slow down browsing through tags and' +
                               ' would be more annoying to implement than I care to deal with, I decided not to. Just deal with it and open' +
                               ' the tags in guerilla to see what they look like.\n\n* During the tag load/conversion process the text box at' +
                               ' the bottom of the main window will give information on which tag is being processed.' +
                               '\n\n* A tag being highlighted in green signifies that, based on the tags current conversion settings, it will be' +
                               ' processed in some way when "Run" is clicked. If a tag is white it will be ignored when "Run" is clicked.' +
                               '\n\n* The "Selected tag Information" window will display information about the selected tag, but ONLY if JUST one' +
                               ' tag is selected. If more than one tag is selected the info displayed will not update. Selecting a different bitmap' +
                               'index on the same window will change which bitmap the window is displaying information about.' +
                               '\n\n* If the program seems to be frozen then check the Python CLI screen(the black empty CMD screen). If it shows an' +
                               ' error then the program may indeed have frozen or crashed. If not then just give it time. Depending on how you are' +
                               ' converting it and the bitmaps dimensions, a conversion may take from a tenth of a second to 3 minutes.' +
                               " BUT AT LEAST IT'S AUTOMATED RIGHT?!?!?!\n\nMade by Moses")
        else:
            new_help_string = ""

        self.displayed_help_text_box.insert(tk.INSERT, new_help_string)
