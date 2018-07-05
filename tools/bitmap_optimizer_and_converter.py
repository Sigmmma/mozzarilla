import gc

from array import array
from os.path import getsize, splitext, dirname
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


#used when displaying the format and type in windows
BITMAP_TYPES = ("2D", "3D", "Cube", "White")
BITMAP_FORMATS = ("A8", "Y8", "AY8", "A8Y8", "????", "????", "R5G6B5",
                  "????", "A1R5G5B5", "A4R4G4B4", "X8R8G8B8", "A8R8G8B8",
                  "????", "????", "DXT1", "DXT3", "DXT5", "P8 Bump")

VALID_FORMATS = (0, 1, 2, 3, 6, 8, 9, 10, 11, 14, 15, 16, 17)


class ConversionFlags:
    platform = "xbox"   # "xbox"   "pc"
    multi_swap = ""     # ""   "to_xbox"   "to_pc"
    p8_mode = "auto"    # ""   "average"   "auto"
    mono_channel_to_keep = "alpha"  # ""   "alpha"   "intensity"

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
    tags_dir = ''
    handler = HaloHandler(valid_def_ids=())

    prune_tiff = None
    read_only = None
    backup_tags = None
    open_log = None

    _processing = False

    def __init__(self, app_root, *args, **kwargs):
        self.handler.reset_tags()
        if "bitm" not in self.handler.defs:
            self.handler.add_def(bitm_def)

        self.app_root = app_root
        kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)

        self.title("Bitmap optimizer and converter")
        self.minsize(width=400, height=340)
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

        # make the tkinter variables
        self.prune_tiff = tk.BooleanVar(self)
        self.read_only = tk.BooleanVar(self)
        self.backup_tags = tk.BooleanVar(self)
        self.open_log = tk.BooleanVar(self, True)

        self.scan_dir_path = tk.StringVar(self)
        self.log_file_path = tk.StringVar(self)

        # make the frames
        self.settings_frame = tk.LabelFrame(self, text="Settings")
        self.bitmap_info_frame = tk.LabelFrame(self, text="Bitmap info")
        self.buttons_frame = tk.Frame(self)

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
                                              state='disabled')
        self.curr_bitmap_label_1 = tk.Label(self.bitmap_index_frame, text=" out of ")
        self.max_bitmap_entry = tk.Entry(self.bitmap_index_frame, width=3,
                                         state='disabled')

        self.curr_type_menu = ScrollMenu(self.bitmap_info_frame, menu_width=8,
                                         disabled=True)
        self.curr_format_menu = ScrollMenu(self.bitmap_info_frame, menu_width=8,
                                           disabled=True)
        self.curr_platform_menu = ScrollMenu(self.bitmap_info_frame, menu_width=8,
                                             disabled=True)
        self.curr_height_entry = tk.Entry(self.bitmap_info_frame, width=12,
                                          state='disabled')
        self.curr_width_entry = tk.Entry(self.bitmap_info_frame, width=12,
                                         state='disabled')
        self.curr_depth_entry = tk.Entry(self.bitmap_info_frame, width=12,
                                         state='disabled')
        self.curr_swizzled_entry = tk.Entry(self.bitmap_info_frame, width=12,
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
            self.global_params_frame, text="Open log when finished",
            variable=self.open_log)


        self.platform_menu = ScrollMenu(self.general_params_frame, menu_width=10)
        self.format_menu = ScrollMenu(self.general_params_frame, menu_width=10)
        self.extract_to_menu = ScrollMenu(self.general_params_frame, menu_width=10)
        self.multi_swap_menu = ScrollMenu(self.general_params_frame, menu_width=10)
        self.downres_box = tk.Spinbox(self.general_params_frame, width=10)


        self.p8_mode_menu = ScrollMenu(self.format_params_frame, menu_width=10)
        self.swizzled_menu = ScrollMenu(self.format_params_frame, menu_width=10)
        self.swap_a8y8_menu = ScrollMenu(self.format_params_frame, menu_width=10)
        self.ck_trans_menu = ScrollMenu(self.format_params_frame, menu_width=10)
        self.alpha_bias_box = tk.Spinbox(self.format_params_frame, width=10)


        self.scan_button = tk.Button(self.buttons_frame, text="Scan")
        self.convert_button = tk.Button(self.buttons_frame, text="Convert")
        self.cancel_button = tk.Button(self.buttons_frame, text="Cancel")


        self.settings_frame.grid(sticky='w', row=0, column=0)
        self.bitmap_info_frame.grid(sticky='nws', row=0, column=1)
        self.buttons_frame.grid(sticky='wse', columnspan=2, row=1, column=0,
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


        self.prune_tiff_cbutton.grid(row=0, column=1, sticky='w')
        self.read_only_cbutton.grid(row=0, column=0, sticky='w')
        self.backup_tags_cbutton.grid(row=1, column=1, sticky='w')
        self.open_log_cbutton.grid(row=1, column=0, sticky='w')


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
                     "Use DXT1 alpha", "Alpha bias"):
            lbl = tk.Label(self.format_params_frame, text=name)
            lbl.grid(row=i, column=0, sticky='w')
            i += 1


        self.curr_bitmap_label_0.pack(side='left', fill='x')
        self.curr_bitmap_spinbox.pack(side='left', fill='x', expand=True)
        self.curr_bitmap_label_1.pack(side='left', fill='x')
        self.max_bitmap_entry.pack(side='left', fill='x', expand=True)

        self.bitmap_index_frame.grid(row=0, column=0, sticky='we', columnspan=2)
        self.curr_type_menu.grid(row=1, column=1, sticky='e')
        self.curr_format_menu.grid(row=2, column=1, sticky='e')
        self.curr_platform_menu.grid(row=3, column=1, sticky='e')
        self.curr_width_entry.grid(row=4, column=1, sticky='e')
        self.curr_height_entry.grid(row=5, column=1, sticky='e')
        self.curr_depth_entry.grid(row=6, column=1, sticky='e')
        self.curr_swizzled_entry.grid(row=7, column=1, sticky='e')
        self.curr_mip_entry.grid(row=8, column=1, sticky='e')
        i = 1
        for name in ("Type", "Format", "Platform",
                     "Width", "Height", "Depth", "Swizzled", "Mipmaps"):
            lbl = tk.Label(self.bitmap_info_frame, text=name)
            lbl.grid(row=i, column=0, sticky='w', pady=4)
            i += 1

        self.apply_style()
        self.tag_list_window = BitmapConverterListWindow(self)

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

        self.app_root.last_load_dir = dirname(dirpath)
        self.scan_dir_path.set(dirpath)

    def log_browse(self):
        if self._processing:
            return
        fp = asksaveasfilename(
            initialdir=dirname(self.log_file_path.get()),
            title="Save scan log to...", parent=self,
            filetypes=(("bitmap optimizer log", "*.log"), ('All', '*')))
        if not fp:
            return

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
            for fmt in VALID_FORMATS:
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

            elif format_t not in ab.VALID_FORMATS:
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
        self.title("Loaded bitmap tags")

        self.resizable(1, 1)
        self.minsize(width=300, height=50)

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
        for fmt in VALID_FORMATS:
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


BitmapConverterWindow(None)
