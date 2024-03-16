import os
import tkinter as tk
import time

from pathlib import Path

from threading import Thread
from tkinter import messagebox
from traceback import format_exc

from binilla.widgets.binilla_widget import BinillaWidget
from binilla.widgets.scroll_menu import ScrollMenu
from binilla.windows.filedialog import askdirectory, asksaveasfilename

from reclaimer.hek.defs.snd_ import snd__def
from reclaimer.sounds import constants, adpcm, playback, ogg
from reclaimer.sounds.blam_sound_bank import BlamSoundBank
from reclaimer.sounds.sound_compilation import compile_sound

from mozzarilla import editor_constants as e_c

try:
    import simpleaudio
except ImportError:
    simpleaudio = None


if __name__ == "__main__":
    window_base_class = tk.Tk
else:
    window_base_class = tk.Toplevel

curr_dir = str(Path(__file__).parent)

AUTO_DETECT     = -1000
COMPATIBILITY   = -2000

MAX_SAMPLE_COUNT = 0x100000

OGG_QUALITY_MIN =  -1.0
OGG_QUALITY_MAX =  10.0

OGG_QUALITY_MODE_FBR     = 0
OGG_QUALITY_MODE_VBR_Q   = 1
OGG_QUALITY_MODE_VBR_A   = 2
OGG_QUALITY_MODE_VBR_LH  = 3
OGG_QUALITY_MODE_VBR_LAH = 4

ogg_quality_mode_names = {
    OGG_QUALITY_MODE_FBR:     "Fixed bitrate",
    OGG_QUALITY_MODE_VBR_Q:   "VBR (base quality)",
    OGG_QUALITY_MODE_VBR_A:   "VBR (avg only)",
    OGG_QUALITY_MODE_VBR_LH:  "VBR (min/max only)",
    OGG_QUALITY_MODE_VBR_LAH: "VBR (min/avg/max)",
    }

auto_detect_names = {
    AUTO_DETECT:     "use source setting",
    COMPATIBILITY:   "max compatibility",
    }

auto_detect_values = (
    AUTO_DETECT,
    COMPATIBILITY,
    )

compression_names = {
    constants.COMPRESSION_PCM_8_SIGNED: "8bit PCM signed",
    constants.COMPRESSION_PCM_8_UNSIGNED: "8bit PCM unsigned",
    constants.COMPRESSION_PCM_16_LE: "16bit PCM",
    constants.COMPRESSION_PCM_16_BE: "16bit PCM",
    constants.COMPRESSION_PCM_24_LE: "24bit PCM",
    constants.COMPRESSION_PCM_24_BE: "24bit PCM",
    constants.COMPRESSION_PCM_32_LE: "32bit PCM",
    constants.COMPRESSION_PCM_32_BE: "32bit PCM",
    constants.COMPRESSION_XBOX_ADPCM: "Xbox ADPCM",
    constants.COMPRESSION_IMA_ADPCM: "IMA ADPCM",
    constants.COMPRESSION_OGG: "Ogg Vorbis",
    **auto_detect_names,
    }
sample_rate_names = {
    constants.SAMPLE_RATE_22K: "22kHz",
    constants.SAMPLE_RATE_44K: "44kHz",
    **auto_detect_names,
    }
encoding_names = {
    constants.ENCODING_MONO: "mono",
    constants.ENCODING_STEREO: "stereo",
    **auto_detect_names,
    }

adpcm_noise_shaping_names = {
    adpcm.NOISE_SHAPING_OFF: "off (recommended)",
    adpcm.NOISE_SHAPING_STATIC: "static",
    adpcm.NOISE_SHAPING_DYNAMIC: "dynamic",
    }
adpcm_lookahead_names = {
    0: "off",
    1: "1 sample",
    2: "2 samples",
    3: "3 samples",
    4: "4 samples",
    5: "5 samples",
    }

compression_menu_values = (
    *auto_detect_values,
    constants.COMPRESSION_XBOX_ADPCM,
    *([constants.COMPRESSION_OGG] if constants.OGGVORBIS_ENCODING_AVAILABLE else []),
    constants.COMPRESSION_PCM_16_BE,
    )
sample_rate_menu_values = (
    *auto_detect_values,
    constants.SAMPLE_RATE_22K,
    constants.SAMPLE_RATE_44K,
    )
encoding_menu_values = (
    *auto_detect_values,
    constants.ENCODING_MONO,
    constants.ENCODING_STEREO,
    )

compression_map = {
    constants.COMPRESSION_PCM_16_LE:  0,
    **{v: k for k, v in constants.halo_1_compressions.items()}
    }
sample_rate_map = {v: k for k, v in constants.halo_1_sample_rates.items()}
encoding_map    = {v: k for k, v in constants.halo_1_encodings.items()}


class SoundCompilerWindow(window_base_class, BinillaWidget):
    app_root = None
    tag_player = None
    src_player = None

    blam_sound_bank = None
    snd__tag = None

    source_dir = None
    sound_path = None

    generate_mouth_data = None
    split_into_smaller_chunks = None

    update_mode = None

    compression = None
    sample_rate = None
    encoding = None
    chunk_size_string = None

    # divide by 2 as the chunk size we want to show to users is in
    # samples, but the chunk size the pipeline works with is in bytes.
    # each sample is a sint16, so we divide by sizeof(sint16)
    min_chunk_size = constants.DEF_SAMPLE_CHUNK_SIZE // 2
    max_chunk_size = constants.MAX_SAMPLE_CHUNK_SIZE // 2
    chunk_size = min_chunk_size

    adpcm_lookahead = None
    adpcm_noise_shaping = None

    ogg_bitrate_fixed = 96000
    ogg_bitrate_min   = 96000
    ogg_bitrate_avg   = 96000
    ogg_bitrate_max   = 96000
    ogg_quality       = 0.4

    _is_new_tag = False
    _compiling = False
    _loading = False
    _saving = False

    _pr_tree_iids = ()
    _iid_to_pr_and_perm = ()
    _play_objects = ()

    def __init__(self, app_root, *args, **kwargs):
        self.src_player = playback.SoundSourcePlayer()
        self.tag_player = playback.SoundTagPlayer()
        if window_base_class == tk.Toplevel:
            kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
            self.app_root = app_root
        else:
            self.app_root = self

        window_base_class.__init__(self, app_root, *args, **kwargs)
        BinillaWidget.__init__(self, *args, **kwargs)

        self.title("Sound compiler")
        self.resizable(1, 1)
        self.update()
        try:
            self.iconbitmap(e_c.MOZZ_ICON_PATH)
        except Exception:
            print("Could not load window icon.")

        self.source_dir = tk.StringVar(self)
        self.sound_path = tk.StringVar(self)

        self.generate_mouth_data = tk.IntVar(self, 0)
        self.sapien_pcm_hack     = tk.IntVar(self, 0)
        self.split_into_smaller_chunks = tk.IntVar(self, 1)

        self.compression = tk.IntVar(self, constants.COMPRESSION_PCM_16_BE)
        self.sample_rate = tk.IntVar(self, constants.SAMPLE_RATE_22K)
        self.encoding    = tk.IntVar(self, constants.ENCODING_MONO)
        self.update_mode = tk.IntVar(self, constants.SOUND_COMPILE_MODE_PRESERVE)

        self.adpcm_lookahead        = tk.IntVar(self, 3)
        self.adpcm_noise_shaping    = tk.IntVar(self, adpcm.NOISE_SHAPING_OFF)
        self.adpcm_fit_to_blocksize = tk.IntVar(self, 1)

        self.chunk_size_string = tk.StringVar(self, str(self.chunk_size))
        self.chunk_size_string.trace("w", lambda *a, s=self: s._spinbox_value_change(
            s.chunk_size_string, "chunk_size", int, s.min_chunk_size, MAX_SAMPLE_COUNT, 1
            ))

        self.ogg_bitrate_fixed_string = tk.StringVar(self, self.ogg_bitrate_fixed//1000)
        self.ogg_bitrate_min_string   = tk.StringVar(self, self.ogg_bitrate_min//1000)
        self.ogg_bitrate_avg_string   = tk.StringVar(self, self.ogg_bitrate_avg//1000)
        self.ogg_bitrate_max_string   = tk.StringVar(self, self.ogg_bitrate_max//1000)
        self.ogg_quality_string       = tk.StringVar(self, self.ogg_quality*10)
        self.ogg_quality_mode         = tk.IntVar(self, 1)
        for name in ("ogg_bitrate_min", "ogg_bitrate_avg",
                     "ogg_bitrate_max", "ogg_bitrate_fixed"):
            tk_var = getattr(self, name + "_string")
            tk_var.trace("w", lambda *a, s=self, tkv=tk_var, n=name: 
                s._spinbox_value_change(tkv, n, int, 1, 1000, 1000)
                )

        self.ogg_quality_string.trace("w", lambda *a, s=self: s._spinbox_value_change(
            s.ogg_quality_string, "ogg_quality", float, OGG_QUALITY_MIN, OGG_QUALITY_MAX, 0.1
            ))

        # make the frames
        self.main_frame = tk.Frame(self)
        self.sample_info_frame = tk.LabelFrame(
            self, text="Import info")

        self.dirs_frame = tk.LabelFrame(
            self.main_frame, text="Directories")
        self.buttons_frame = tk.Frame(self.main_frame)
        self.settings_frame = tk.Frame(
            self.main_frame)

        self.source_dir_frame = tk.LabelFrame(
            self.dirs_frame, text="Sound source files folder")
        self.sound_path_frame = tk.LabelFrame(
            self.dirs_frame, text="Sound tag output path")

        self.general_frame = tk.LabelFrame(
            self.settings_frame, text="General settings")
        self.adpcm_frame = tk.LabelFrame(
            self.settings_frame, text="ADPCM settings")
        self.ogg_frame = tk.LabelFrame(
            self.settings_frame, text="OggVorbis settings")
        self.misc_frame = tk.LabelFrame(
            self.settings_frame, text="Misc settings")

        self.compile_mode_replace_rbtn = tk.Radiobutton(
            self.general_frame, anchor="w", justify="left",
            variable=self.update_mode, value=constants.SOUND_COMPILE_MODE_NEW,
            text="Completely ignore and overwrite\nany tag that may exist")
        self.compile_mode_preserve_rbtn = tk.Radiobutton(
            self.general_frame, anchor="w", justify="left",
            variable=self.update_mode, value=constants.SOUND_COMPILE_MODE_PRESERVE,
            text="Preserve existing tag settings\nbut recompile all sample data")
        self.compile_mode_additive_rbtn = tk.Radiobutton(
            self.general_frame, anchor="w", justify="left",
            variable=self.update_mode, value=constants.SOUND_COMPILE_MODE_ADDITIVE,
            text="Preserve all existing tag data\nincluding existing audio samples")

        self.compression_label = tk.Label(self.general_frame, text="Compression �")
        self.compression_menu = ScrollMenu(
            self.general_frame,  variable=self.compression, menu_width=15,
            options=tuple(
                compression_names[const] for const in compression_menu_values
                )
            )
        self.sample_rate_label = tk.Label(self.general_frame, text="Sample rate �")
        self.sample_rate_menu = ScrollMenu(
            self.general_frame, variable=self.sample_rate, menu_width=15,
            options=tuple(
                sample_rate_names[const] for const in sample_rate_menu_values
                ),
            )
        self.encoding_label = tk.Label(self.general_frame, text="Encoding �")
        self.encoding_menu = ScrollMenu(
            self.general_frame, variable=self.encoding, menu_width=15,
            options=tuple(
                encoding_names[const] for const in encoding_menu_values
                ),
            )

        self.compression_label.tooltip_string = (
            "Determines what compression method to use for storing audio samples.\n\n"
            "use source setting:\n"
            "\tIf possible, use the same compression as the source files.\n"
            "max compatibility:\n"
            "\tUse Xbox ADPCM, as every engine can play it(xbox/pc/ce/mcc).\n"
            "Xbox ADPCM:\n"
            "\tUse Xbox ADPCM. Compresses to 28.125% as large as 16bit PCM.\n"
            "Ogg Vorbis:\n"
            "\tHigh quality audio that has a large range of compression options.\n"
            "\tMay cause issues with short sounds not playing(use Xbox ADPCM),\n"
            "\tor really long sounds that weren't chopped into smaller chunks.\n"
            "\tNOTE: Not usable on xbox, stubbs, or shadowrun.\n"
            "16bit PCM:\n"
            "\tHighest quality, but also largest(completely uncompressed).\n"
            "\tMay cause issues with tools(sapien/guerilla) not playing the audio."
            )
        self.sample_rate_label.tooltip_string = (
            "Determines what sample rate to store the audio samples at.\n\n"
            "use source setting:\n"
            "\tIf possible, use the same sample rate as the source files.\n"
            "max compatibility:\n"
            "\tUse 22kHz, as there are no cases where the engine wont play it.\n"
            "22kHz:\n"
            "\tUse sample rate of 22050Hz.\n"
            "44kHz:\n"
            "\tUse sample rate of 44100Hz.\n"
            "\tNOTE: The engine has a harder time playing this reliably.\n"
            "\tUnless you are compiling music, steer away from 44kHz."
            )
        self.encoding_label.tooltip_string = (
            "Determines whether to compile audio to mono or stereo.\n\n"
            "use source setting:\n"
            "\tIf possible, use the same encoding as the source files.\n"
            "max compatibility:\n"
            "\tUse mono, as there are no cases where the engine wont play it.\n"
            "mono:\n"
            "\tSingle audio channel. Stereo source files will have mono tracks\n"
            "\tgenerated from them by averaging the left and right channels.\n"
            "stereo:\n"
            "\tDual audio channels. Mono source files will have stereo tracks\n"
            "\tgenerated by using the mono as-is for left and right channels.\n"
            "\tNOTE: The engine has a harder time playing this reliably.\n"
            "\tUnless you are compiling music, steer away from stereo."
            )

        self.adpcm_lookahead_label = tk.Label(
            self.adpcm_frame, text="Lookahead prediction �")
        self.adpcm_lookahead_menu = ScrollMenu(
            self.adpcm_frame, variable=self.adpcm_lookahead,
            menu_width=17, options=adpcm_lookahead_names
            )
        self.adpcm_noise_shaping_label = tk.Label(
            self.adpcm_frame, text="Noise shaping �")
        self.adpcm_noise_shaping_menu = ScrollMenu(
            self.adpcm_frame, variable=self.adpcm_noise_shaping,
            menu_width=17, options=adpcm_noise_shaping_names
            )
        self.adpcm_fit_to_blocksize_cbtn = tk.Checkbutton(
            self.adpcm_frame, variable=self.adpcm_fit_to_blocksize,
            anchor="w", text="Fit to ADPCM blocksize �")
        self.adpcm_lookahead_label.tooltip_string = (
            "Number of samples to look ahead when determining minimum\n"
            "ADPCM error. Higher numbers are typically better."
            )
        self.adpcm_noise_shaping_label.tooltip_string = (
            "The type of noise shaping algorithm to apply to the sound.\n"
            "Noise shaping is a form of dithering, but for audio.\n"
            "Results will vary, so always test after turning this on."
            )
        self.adpcm_fit_to_blocksize_cbtn.tooltip_string = (
            "If set, truncates ADPCM sounds to the lowest multiple of\n"
            "64 samples. If not set, pads up to nearest multiple by\n"
            "repeating the last sample until the end of the block."
            )

        for param in ("min", "avg", "max", "fixed"):
            name    = "ogg_bitrate_%s" % param
            tk_var  = getattr(self, name + "_string")
            label   = tk.Label(self.ogg_frame, text="Bitrate %s(kbit/s) �" % param)
            spinbox = tk.Spinbox(
                self.ogg_frame, increment=1, width=8, from_=1, to=1000,
                justify="right", textvariable=tk_var
                )
            setattr(self, name + "_label", label)
            setattr(self, name + "_spinbox", spinbox)
            spinbox.bind('<Return>', lambda *a, s=self, tkv=tk_var, n=name: 
                self._spinbox_value_change(tkv, n, int, 1, 1000, 1000, True)
                )
            ttname = (
                "average" if param == "avg" else
                "only"    if param == "fixed" else
                "%simum" % param
                )

            label.tooltip_string = spinbox.tooltip_string = (
                "The %s bitrate the stream will be at any given time.\n" % ttname
                ) + (
                "Does not have an effect unless the quality mode is set\n"
                "to one of the modes that this bitrate is included in.\n"
                "NOTE: The Vorbis encoder will do its best to respect these\n"
                "\tsettings, however any that are out of range will be\n"
                "\tclamped to whatever the encoder decides. If it fails to\n"
                "\tdecide, an error will be thrown and compiling will stop."
                )

        self.ogg_quality_mode_label = tk.Label(
            self.ogg_frame, text="Quality mode �")
        self.ogg_quality_mode_menu = ScrollMenu(
            self.ogg_frame, variable=self.ogg_quality_mode,
            menu_width=17, options=ogg_quality_mode_names
            )
        self.ogg_quality_label = tk.Label(
            self.ogg_frame, text="Base quality �"
            )
        self.ogg_quality_spinbox = tk.Spinbox(
            self.ogg_frame, from_=OGG_QUALITY_MIN, to=OGG_QUALITY_MAX, justify="right",
            increment=0.5, width=8, textvariable=self.ogg_quality_string
            )
        self.ogg_quality_spinbox.bind('<Return>', lambda *a, s=self, tkv=tk_var, n=name: 
            self._spinbox_value_change(
                self.ogg_quality_string, "ogg_quality", float, 
                OGG_QUALITY_MIN, OGG_QUALITY_MAX, 0.1, update_spinbox=True
                )
            )

        self.ogg_quality_mode_label.tooltip_string = (
            "Determines what parameters to use for compressing the stream.\n"
            "Fixed bitrate:\n"
            "\tBitrate does not vary, and is always the fixed rate.\n"
            "VBR (base quality):\n"
            "\tBitrate varies based on the audio and base quality value.\n"
            "VBR (avg only):\n"
            "\tBitrate varies with no min/max limits, but averages to the avg.\n"
            "VBR (min/max only):\n"
            "\tBitrate varies between the min/max limits, but no specific average.\n"
            "VBR (min/avg/max):\n"
            "\tBitrate varies between the min/max limits, and averages to the avg."
            )
        self.ogg_quality_label.tooltip_string = self.ogg_quality_spinbox.tooltip_string = (
            "A simple variable-bitrate selection mechanism designed for\n"
            "users who don't have exact bitrate limits in mind. Does not\n"
            "have an effect unless the quality mode is set to VBR base quality.\n"
            "Ranges from -1 (small, worst quality) to 10 (large, best quality)."
            )

        self.compression_menu.sel_index = 0
        self.sample_rate_menu.sel_index = 0
        self.encoding_menu.sel_index = 0

        self.generate_mouth_data_cbtn = tk.Checkbutton(
            self.misc_frame, variable=self.generate_mouth_data,
            anchor="w", text="Generate mouth data �")
        self.split_into_smaller_chunks_cbtn = tk.Checkbutton(
            self.misc_frame, variable=self.split_into_smaller_chunks,
            anchor="w", text="Split into chunks �")
        self.sapien_pcm_hack_cbtn = tk.Checkbutton(
            self.misc_frame, variable=self.sapien_pcm_hack,
            anchor="w", text="Apply hackfix to enable 16bit PCM to play in Sapien �")
        self.chunk_size_label = tk.Label(
            self.misc_frame, text="Chunk size �")
        self.chunk_size_spinbox = tk.Spinbox(
            self.misc_frame, from_=self.min_chunk_size,
            to=self.max_chunk_size, increment=1024*4, width=12,
            textvariable=self.chunk_size_string, justify="right")

        self.generate_mouth_data_cbtn.tooltip_string = (
            "Whether or not to generate mouth data for this sound.\n"
            "Mouth data animates a characters mouth to the sound."
            )
        self.split_into_smaller_chunks_cbtn.tooltip_string = (
            "Whether or not to split long sounds into pieces.\n"
            "Long sounds may not play properly ingame, and this\n"
            "setting is recommended if the sound is over a few seconds."
            )
        self.sapien_pcm_hack_cbtn.tooltip_string = (
            "Original HEK sapien has a bug where it cannot play\n"
            "16bit PCM audio if the compression in the body of\n"
            "the tag is set to 'none'. As a hack, we can set it\n"
            "to OGG, but this prevents it from playing in Guerilla."
            )
        self.chunk_size_label.tooltip_string = self.chunk_size_spinbox.tooltip_string = (
            'The number of samples per chunk to split long sounds into.'
            )


        self._pr_info_tree = tk.ttk.Treeview(
            self.sample_info_frame, selectmode='browse', padding=(0, 0), height=4)
        self.sample_info_vsb = tk.Scrollbar(
            self.sample_info_frame, orient='vertical',
            command=self._pr_info_tree.yview)
        self.sample_info_hsb = tk.Scrollbar(
            self.sample_info_frame, orient='horizontal',
            command=self._pr_info_tree.xview)
        self.stop_playback_button = tk.Button(
            self.sample_info_frame, text="Stop audio playback",
            command=lambda s=self: (
                self.src_player.stop_all_sounds() or
                self.tag_player.stop_all_sounds()
                )
            )

        self._pr_info_tree.config(yscrollcommand=self.sample_info_vsb.set,
                                  xscrollcommand=self.sample_info_hsb.set)
    
        self._pr_info_tree.bind('<Double-Button-1>', self.activate_item)
        self._pr_info_tree.bind('<Return>', self.activate_item)

        self.source_dir_entry = tk.Entry(
            self.source_dir_frame, textvariable=self.source_dir, state=tk.DISABLED)
        self.source_dir_browse_button = tk.Button(
            self.source_dir_frame, text="Browse", command=self.source_dir_browse)


        self.sound_path_entry = tk.Entry(
            self.sound_path_frame,
            textvariable=self.sound_path,
            state=tk.DISABLED)
        self.sound_path_browse_button = tk.Button(
            self.sound_path_frame, text="Browse",
            command=self.sound_path_browse)


        self.load_button = tk.Button(
            self.buttons_frame, text="Load files",
            command=self.load_source_files)
        self.compile_button = tk.Button(
            self.buttons_frame, text="Compile sound",
            command=self.compile_sound)

        self.populate_sample_info_tree()

        # pack everything
        self.main_frame.pack(fill="both", side='left', pady=3, padx=3)
        self.sample_info_frame.pack(
            fill="both", side='left', padx=3, pady=3, expand=True
            )

        for w in (self.dirs_frame, self.buttons_frame, self.settings_frame):
            w.pack(fill="both", padx=3, pady=3)

        self.source_dir_frame.pack(fill='x')
        self.sound_path_frame.pack(fill='x')

        self.source_dir_entry.pack(side='left', fill='x', expand=True)
        self.source_dir_browse_button.pack(side='left')

        self.sound_path_entry.pack(side='left', fill='x', expand=True)
        self.sound_path_browse_button.pack(side='left')

        self.stop_playback_button.pack(side="bottom", fill='x', padx=5, pady=5)
        self.sample_info_hsb.pack(side="bottom", fill='x')
        self.sample_info_vsb.pack(side="right",  fill='y')
        self._pr_info_tree.pack(side='left', fill='both', expand=True)

        self.load_button.pack(side='left', fill='both', padx=3, expand=True)
        self.compile_button.pack(side='right', fill='both', padx=3, expand=True)

        for w in (
                self.general_frame, self.adpcm_frame,
                *([self.ogg_frame] if constants.OGGVORBIS_ENCODING_AVAILABLE else []),
                self.misc_frame
                ):
            w.pack(expand=True, fill='both', pady=(0, 3))

        for i, row in enumerate((
                (self.compression_label, self.compression_menu, self.compile_mode_replace_rbtn),
                (self.sample_rate_label, self.sample_rate_menu, self.compile_mode_preserve_rbtn),
                (self.encoding_label,    self.encoding_menu,    self.compile_mode_additive_rbtn),
                )):
            for j, w in enumerate(row):
                w.grid(row=i, column=j, sticky="w", padx=10)

        for i, row in enumerate((
                (self.adpcm_lookahead_label, self.adpcm_lookahead_menu, self.adpcm_fit_to_blocksize_cbtn),
                (self.adpcm_noise_shaping_label, self.adpcm_noise_shaping_menu, ),
                )):
            for j, w in enumerate(row):
                w.grid(row=i, column=j, sticky="nws", padx=(10, 0), pady=(0, 5))

        for i, row in enumerate((
                (self.ogg_quality_mode_label,  self.ogg_quality_label,       self.ogg_bitrate_fixed_label),
                (self.ogg_quality_mode_menu,   self.ogg_quality_spinbox,     self.ogg_bitrate_fixed_spinbox),
                (self.ogg_bitrate_min_label,   self.ogg_bitrate_avg_label,   self.ogg_bitrate_max_label),
                (self.ogg_bitrate_min_spinbox, self.ogg_bitrate_avg_spinbox, self.ogg_bitrate_max_spinbox),
                )):
            for j, w in enumerate(row):
                w.grid(row=j, column=i, sticky="nws", padx=(10, 0), pady=(0, 5))

        for i, row in enumerate((
                ((self.chunk_size_label, 1), (self.chunk_size_spinbox, 1), (self.split_into_smaller_chunks_cbtn, 1)),
                ((self.sapien_pcm_hack_cbtn, 2), (self.generate_mouth_data_cbtn, 1)),
                )):
            j = 0
            for w, span in row:
                w.grid(row=i, column=j, sticky="nws", columnspan=span, padx=(5, 5))
                j += span

        self.apply_style()
        if self.app_root is not self:
            self.transient(self.app_root)
    
    @property
    def target_settings(self):
        try:
            tagdata     = self.snd__tag.data.tagdata
            sound_bank  = self.blam_sound_bank
        except AttributeError:
            tagdata = sound_bank = None

        # these are the compression settings for the imported sound bank,
        # existing sound tag, and user-selected values respectively
        # NOTE: these target values are from the set of values in constants
        #       that start with COMPRESSION_ , SAMPLE_RATE_ , and ENCODING_
        comp_bank, sr_bank, enc_bank = (None, None, None)
        comp_tag,  sr_tag,  enc_tag  = (None, None, None)
        comp_sel    = self.selected_compression
        sr_sel      = self.selected_sample_rate
        enc_sel     = self.selected_encoding

        auto_comp, auto_sr, auto_enc = (
            v == AUTO_DETECT for v in (comp_sel, sr_sel, enc_sel)
            )

        # if updating/adding, we can't change the sample rate or encoding
        # because they're specified for the entire tag, so we have to
        # force those settings to what's currently set in the tag.
        use_tag_vals = not self._is_new_tag and (
            self.update_mode.get() == constants.SOUND_COMPILE_MODE_ADDITIVE
            )

        # figure out any auto-values we may use in the tag
        if use_tag_vals and tagdata:
            # NOTE: not using tagdata.compression.data as it may not be correct
            comp_tag = 0
            for pr in tagdata.pitch_ranges.STEPTREE:
                for perm in pr.permutations.STEPTREE:
                    comp_tag = perm.compression.data
                    break

            comp_tag, sr_tag, enc_tag = (
                mapping.get(enum)
                for mapping, enum in (
                    (constants.halo_1_compressions, comp_tag),
                    (constants.halo_1_sample_rates, tagdata.sample_rate.data),
                    (constants.halo_1_encodings,    tagdata.encoding.data),
                    )
                )

        # figure out any auto-values we may use in the sound bank samples
        if sound_bank:
            for pr in sound_bank.pitch_ranges.values():
                for perm in pr.permutations.values():
                    if comp_bank is None:
                        comp_bank   = perm.source_compression
                    sr_bank     = max(sr_bank  or 0, perm.source_sample_rate)
                    enc_bank    = max(enc_bank or 0, perm.source_encoding)

            if comp_bank and comp_bank not in compression_map:
                # if compression isn't supported, change to closest supported
                comp_bank = (
                    constants.COMPRESSION_PCM_16_BE if comp_bank in (
                        constants.COMPRESSION_PCM_16_LE,
                        constants.COMPRESSION_PCM_24_LE,
                        constants.COMPRESSION_PCM_24_BE,
                        constants.COMPRESSION_PCM_32_LE,
                        constants.COMPRESSION_PCM_32_BE,
                        ) else 
                    constants.COMPRESSION_XBOX_ADPCM if comp_bank in (
                        constants.COMPRESSION_PCM_8_SIGNED, 
                        constants.COMPRESSION_PCM_8_UNSIGNED, 
                        ) else
                    None
                    )

            if sr_bank and sr_bank not in sample_rate_map:
                # if sample rate isn't one of the ones we support, round it
                sr_bank = max(1, min(2, int(
                    round(sr_bank / constants.SAMPLE_RATE_22K)
                    ))) * constants.SAMPLE_RATE_22K

            if enc_bank and enc_bank not in encoding_map:
                # encoding isn't supported, throw an error
                raise ValueError("Unsupported encoding in sound bank: '%s'" % enc_bank)

        # figure out what our target values are based on requirement/preference
        target_comp = (
            comp_tag  if comp_tag  is not None and use_tag_vals     else
            comp_bank if comp_bank in compression_map and auto_comp else
            comp_sel  if comp_sel  in compression_map               else
            # all engines can play xbadpcm
            constants.COMPRESSION_XBOX_ADPCM
            )
        target_sr   = (
            sr_tag    if sr_tag is not None and use_tag_vals    else
            sr_bank   if sr_bank in sample_rate_map and auto_sr else
            sr_sel    if sr_sel  in sample_rate_map             else
            # 44khz can't always be played, so 22khz is most compatible
            constants.SAMPLE_RATE_22K
            )
        target_enc  = (
            enc_tag   if enc_tag is not None and use_tag_vals  else
            enc_bank  if enc_bank in encoding_map and auto_enc else
            enc_sel   if enc_sel in encoding_map               else
            # stereo sound can't always be played, so mono is more compatible
            constants.ENCODING_MONO
            )

        return target_comp, target_sr, target_enc

    @property
    def target_compression(self): return self.target_settings[0]
    @property
    def target_sample_rate(self): return self.target_settings[1]
    @property
    def target_encoding(self):    return self.target_settings[2]

    @property
    def selected_compression(self):
        try:
            return compression_menu_values[self.compression.get()]
        except IndexError:
            return None

    @property
    def selected_sample_rate(self):
        try:
            return sample_rate_menu_values[self.sample_rate.get()]
        except IndexError:
            return None

    @property
    def selected_encoding(self):
        try:
            return encoding_menu_values[self.encoding.get()]
        except IndexError:
            return None

    def _spinbox_value_change(
            self, tk_var, property_name, num_type, 
            min_val, max_val, scale, update_spinbox=False
            ):
        try:
            new_val = num_type(tk_var.get())
        except ValueError:
            return

        if max_val is not None and new_val > max_val: 
            new_val = max_val

        if min_val is not None and new_val < min_val: 
            new_val = min_val

        if update_spinbox:
            tk_var.set(str(("%.20f" % new_val)).rstrip("0").rstrip("."))

        setattr(self, property_name, num_type(new_val * scale))
        spinbox = getattr(self, property_name + "_spinbox", None)
        if None not in (spinbox, min_val, max_val):
            spinbox.configure(from_=min_val, to=max_val)

    def activate_item(self, e=None):
        iid = self._pr_info_tree.focus()
        if iid is None or iid not in self._iid_to_pr_and_perm:
            return

        try:
            is_tag, pr_index, perm_index = self._iid_to_pr_and_perm[iid]
            player  = self.tag_player if is_tag else self.src_player
            player.pitch_range_index = pr_index
            player.permutation_index = perm_index

            # initiate a queued, threaded play of the sound
            if not constants.PLAYBACK_AVAILABLE:
                print("Audio playback unavailable.")
            elif player.get_wave_id(pr_index, perm_index):
                player.play_sound()
        except Exception:
            print(format_exc())

    def populate_sample_info_tree(self):
        pr_tree = self._pr_info_tree
        if not pr_tree['columns']:
            pr_tree['columns'] = ('data', )
            pr_tree.heading("#0")
            pr_tree.heading("data")
            pr_tree.column("#0", minwidth=150, width=150)
            pr_tree.column("data", minwidth=130, width=130, stretch=False)

        for iid in self._pr_tree_iids:
            pr_tree.delete(iid)

        self.src_player.stop_all_sounds()
        self.tag_player.stop_all_sounds()

        self._pr_tree_iids = []
        self._iid_to_pr_and_perm = {}

        source_files_iid = pr_tree.insert(
            '', 'end', text='Source file pitch ranges',
            tags=('item',), )
        snd__tag_iid = pr_tree.insert(
            '', 'end', text='Sound tag pitch ranges',
            tags=('item',), )
        self._pr_tree_iids.append(source_files_iid)
        self._pr_tree_iids.append(snd__tag_iid)

        if self.blam_sound_bank:
            self.src_player.sound_bank = self.blam_sound_bank

            for i, pr_name in enumerate(sorted(self.blam_sound_bank.pitch_ranges)):
                pitch_range = self.blam_sound_bank.pitch_ranges[pr_name]
                pitch_range_iid = pr_tree.insert(
                    source_files_iid, 'end', text='%s' % pr_name,
                    tags=('item',), values=(len(pitch_range.permutations),))

                for j, perm_name in enumerate(sorted(pitch_range.permutations)):
                    perm = pitch_range.permutations[perm_name]
                    perm_iid = pr_tree.insert(
                        pitch_range_iid, 'end', tags=('item',),
                        text=perm_name, values=("Click 2x to play/stop", )
                        )

                    iids = [perm_iid]

                    iids.append(pr_tree.insert(
                        perm_iid, 'end', text="Compression", tags=('item',),
                        values=(compression_names.get(
                            perm.source_compression, "<INVALID>"), )))
                    iids.append(pr_tree.insert(
                        perm_iid, 'end', text="Sample rate", tags=('item',),
                        values=("%sHz" % perm.source_sample_rate), ))
                    iids.append(pr_tree.insert(
                        perm_iid, 'end', text="Encoding", tags=('item',),
                        values=(encoding_names.get(
                            perm.source_encoding, "<INVALID>"), )))
                    iids.append(pr_tree.insert(
                        perm_iid, 'end', text="Size", tags=('item',),
                        values=("%s bytes" % len(perm.source_sample_data), )))

                    for iid in iids:
                        self._iid_to_pr_and_perm[iid] = (False, i, j)
        else:
            self.src_player.sound_bank = None

        if self.snd__tag:
            tagdata = self.snd__tag.data.tagdata
            self.tag_player.sound_data = tagdata
            self.tag_player.big_endian_pcm = True

            sample_rate_const = constants.halo_1_sample_rates.get(
                tagdata.sample_rate.data)
            encoding_const = tagdata.encoding.data

            sample_rate_str = sample_rate_names.get(
                sample_rate_const, "<INVALID>")
            encoding_str = encoding_names.get(
                encoding_const, "<INVALID>")

            pr_tree.insert(
                snd__tag_iid, 'end', text="Sample rate", tags=('item',),
                values=(sample_rate_str, ))
            pr_tree.insert(
                snd__tag_iid, 'end', text="Encoding", tags=('item',),
                values=(encoding_str, ))
            for i, pitch_range in enumerate(tagdata.pitch_ranges.STEPTREE):
                pitch_range_iid = pr_tree.insert(
                    snd__tag_iid, 'end', text=pitch_range.name, tags=('item',),
                    values=(len(pitch_range.permutations.STEPTREE),))
                for j, perm in enumerate(pitch_range.permutations.STEPTREE):
                    perm_iid = pr_tree.insert(
                        pitch_range_iid, 'end', tags=('item',),
                        text=perm.name, values=("Click 2x to play/stop", )
                        )

                    iids = [perm_iid]

                    iids.append(pr_tree.insert(
                        perm_iid, 'end', text="Compression", tags=('item',),
                        values=(
                            compression_names.get(
                                constants.halo_1_compressions.get(
                                    perm.compression.data),
                                "<INVALID>"),
                            )))
                    iids.append(pr_tree.insert(
                        perm_iid, 'end', text="Audio data size", tags=('item',),
                        values=("%s bytes" % len(perm.samples.data), )))
                    iids.append(pr_tree.insert(
                        perm_iid, 'end', text="Mouth data size", tags=('item',),
                        values=("%s bytes" % len(perm.mouth_data.data), )))

                    for iid in iids:
                        self._iid_to_pr_and_perm[iid] = (True, i, j)
        else:
            self.tag_player.sound_data = None

    def source_dir_browse(self):
        if self._compiling or self._loading or self._saving:
            return

        source_dir = self.source_dir.get()
        dirpath = askdirectory(
            initialdir=source_dir, parent=self,
            title="Select the folder of %s files to compile..." % '/'.join(
                s.strip(".") for s in constants.SUPPORTED_IMPORT_EXTS
                )
            )

        if not dirpath:
            return

        self.app_root.last_load_dir = os.path.dirname(dirpath)
        self.source_dir.set(dirpath)

    def sound_path_browse(self, force=False):
        if not force and (self._compiling or self._loading or self._saving):
            return

        snd__dir = os.path.dirname(self.sound_path.get())
        fp = asksaveasfilename(
            initialdir=snd__dir, title="Save sound to...", parent=self,
            filetypes=(("Sound", "*.sound"), ('All', '*')))

        if not fp:
            return

        if not os.path.splitext(fp)[-1]:
            fp += ".sound"

        self.app_root.last_load_dir = os.path.dirname(fp)
        self.sound_path.set(fp)

    def apply_style(self, seen=None):
        BinillaWidget.apply_style(self, seen)
        self.update()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry("%sx%s" % (w, h))
        self.minsize(width=w, height=h)

    def destroy(self):
        try:
            self.app_root.tool_windows.pop(self.window_name, None)
        except AttributeError:
            pass
        window_base_class.destroy(self)

    def load_source_files(self):
        if not self._compiling and not self._loading and not self._saving:
            self._loading = True
            try:
                self._load_source_files()
            except Exception:
                print(format_exc())
            try:
                self.populate_sample_info_tree()
            except Exception:
                print(format_exc())
            self._loading = False

    def compile_sound(self):
        if not self._compiling and not self._loading and not self._saving:
            self._compiling = True
            try:
                self._compile_sound()
            except Exception:
                print(format_exc())

            self._loading = True
            try:
                self.populate_sample_info_tree()
            except Exception:
                print(format_exc())
            self._loading = False
            self._compiling = False

    def _load_source_files(self):
        sounds_dir = self.source_dir.get()
        if not sounds_dir:
            return

        start = time.time()
        print("Loading wav files...")
        blam_sound_bank = BlamSoundBank.create_from_directory(sounds_dir)

        if blam_sound_bank is None:
            print("    Errors occurred while loading wav files.")
            return
        elif not blam_sound_bank.pitch_ranges:
            print("    No valid wav files found in the folder.")
            return

        self.snd__tag = None
        try:
            tagpath = self.sound_path.get()
            if tagpath:
                print("Loading sound tag...")
                self.snd__tag = snd__def.build(filepath=tagpath)
        except Exception:
            pass

        self._is_new_tag = not self.snd__tag
        if self._is_new_tag:
            print("    Existing sound tag not detected or could not be loaded.\n"
                  "        A new sound tag will be created.")
        else:
            tagdata = self.snd__tag.data.tagdata
            self.adpcm_fit_to_blocksize.set(
                bool(tagdata.flags.fit_to_adpcm_blocksize)
                )
            self.split_into_smaller_chunks.set(
                bool(tagdata.flags.split_long_sound_into_permutations))
            self.generate_mouth_data.set(
                "dialog" in tagdata.sound_class.enum_name)

        self.blam_sound_bank = blam_sound_bank
        print("Finished loading files. Took %s seconds.\n" %
              str(time.time() - start).split('.')[0])

    def _compile_sound(self):
        sound_bank = self.blam_sound_bank
        if not sound_bank:
            return

        # insert settings into sound_bank and check their sanity
        sound_bank.chunk_size  = (
            self.chunk_size * constants.channel_counts[self.target_encoding]
            )
        sound_bank.compression = self.target_compression
        sound_bank.sample_rate = self.target_sample_rate
        sound_bank.encoding    = self.target_encoding
        sound_bank.adpcm_fit_to_blocksize = self.adpcm_fit_to_blocksize.get()
        sound_bank.adpcm_noise_shaping = self.adpcm_noise_shaping.get()
        sound_bank.adpcm_lookahead = self.adpcm_lookahead.get()
        sound_bank.split_into_smaller_chunks = bool(self.split_into_smaller_chunks.get())

        qmode = self.ogg_quality_mode.get()

        sound_bank.ogg_bitrate_lower     = -1
        sound_bank.ogg_bitrate_nominal   = -1
        sound_bank.ogg_bitrate_upper     = -1
        # for easier comprehension by users, we let quality go from -1 to 10
        # and just divide by 10 when actually passing it to the encoder.
        sound_bank.ogg_quality_setting   = self.ogg_quality
        sound_bank.ogg_use_quality_value = qmode == OGG_QUALITY_MODE_VBR_Q

        use_avg     = qmode in (OGG_QUALITY_MODE_VBR_A, OGG_QUALITY_MODE_VBR_LAH)
        use_bounds  = qmode in (OGG_QUALITY_MODE_VBR_LH, OGG_QUALITY_MODE_VBR_LAH)
        use_quality = qmode == OGG_QUALITY_MODE_FBR

        sound_bank.ogg_bitrate_nominal = (
            self.ogg_bitrate_avg   if use_avg         else
            self.ogg_bitrate_fixed if not use_quality else
            -1
            )
        if use_bounds:
            sound_bank.ogg_bitrate_lower = self.ogg_bitrate_min
            sound_bank.ogg_bitrate_upper = self.ogg_bitrate_max
        else:
            sound_bank.ogg_bitrate_lower = sound_bank.ogg_bitrate_nominal
            sound_bank.ogg_bitrate_upper = sound_bank.ogg_bitrate_nominal

        # check validity of settings
        errors = []
        if sound_bank.compression != constants.COMPRESSION_OGG:
             pass
        elif use_bounds:
            if sound_bank.ogg_bitrate_lower > sound_bank.ogg_bitrate_upper:
                errors.append("Error: vorbis min bitrate is higher than max.")

            if use_avg and sound_bank.ogg_bitrate_lower > sound_bank.ogg_bitrate_nominal:
                errors.append("Error: vorbis min bitrate is higher than avg.")

            if use_avg and sound_bank.ogg_bitrate_upper < sound_bank.ogg_bitrate_nominal:
                errors.append("Error: vorbis max bitrate is lower than avg.")
        
        if errors:
            print("\n".join(errors))
            return

        print("Compiling...")
        while not self.sound_path.get():
            self.sound_path_browse(True)
            if not self.sound_path.get() and self.warn_cancel():
                print("    Sound compilation cancelled.")
                return

        if self._is_new_tag:
            print("Creating new sound tag.")
            self.snd__tag = snd__def.build()
        else:
            print("Updating existing sound tag.")

        self.snd__tag.filepath = self.sound_path.get()

        self.update()

        try:
            print("Paritioning and compressing permutations...", end="")
            self.update()
            sound_bank.compress_samples()
            print(" Done.")

            if self.generate_mouth_data.get():
                print("Generating mouth data...", end="")
                sound_bank.generate_mouth_data()
                print(" Done.")

        except ogg.VorbisEncoderSetupError:
            print("Current OggVorbis settings are invalid.")
            return

        except Exception:
            print("\n", format_exc(), sep="")
            print("    Error occurred while partitoning and compressing.")
            return

        self.update()

        errors = compile_sound(
            self.snd__tag, sound_bank,
            update_mode=(
                constants.SOUND_COMPILE_MODE_NEW 
                if self._is_new_tag else
                self.update_mode.get()
                ),
            sapien_pcm_hack=self.sapien_pcm_hack.get()
            )

        if errors:
            for error in errors:
                print(error)

            self.update()
            if not messagebox.askyesno(
                    "Sound compilation failed",
                    "Errors occurred while compiling sound(check console). "
                    "Do you want to save the sound tag anyway?",
                    icon='warning', parent=self):
                print("    Sound compilation failed.")
                return

        try:
            self.snd__tag.calc_internal_data()
            self.snd__tag.serialize(temp=False, backup=False,
                                    calc_pointers=False, int_test=False)
            print("    Finished")
        except Exception:
            print(format_exc())
            print("    Could not save compiled sound.")

    def warn_cancel(self):
        return bool(messagebox.askyesno(
            "Unsaved sound",
            "Are you sure you wish to cancel?",
            icon='warning', parent=self))


if __name__ == "__main__":
    SoundCompilerWindow(None).mainloop()
