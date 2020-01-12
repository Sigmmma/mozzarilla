import os
import tkinter as tk
import time

from pathlib import Path

from tkinter import messagebox
from traceback import format_exc

from binilla.widgets.binilla_widget import BinillaWidget
from binilla.widgets.scroll_menu import ScrollMenu
from binilla.windows.filedialog import askdirectory, asksaveasfilename

from reclaimer.hek.defs.snd_ import snd__def
from reclaimer.sounds import constants, adpcm
from reclaimer.sounds.blam_sound_bank import BlamSoundBank
from reclaimer.sounds.sound_compilation import compile_sound

from mozzarilla import editor_constants as e_c

if __name__ == "__main__":
    window_base_class = tk.Tk
else:
    window_base_class = tk.Toplevel

curr_dir = str(Path(__file__).parent)

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
    }
sample_rate_names = {
    constants.SAMPLE_RATE_22K: "22kHz",
    constants.SAMPLE_RATE_44K: "44kHz",
    }
encoding_names = {
    constants.ENCODING_MONO: "mono",
    constants.ENCODING_STEREO: "stereo",
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
    constants.COMPRESSION_XBOX_ADPCM,
    #constants.COMPRESSION_OGG,
    constants.COMPRESSION_PCM_16_BE,
    )
sample_rate_menu_values = (
    constants.SAMPLE_RATE_22K,
    constants.SAMPLE_RATE_44K,
    )
encoding_menu_values = (
    constants.ENCODING_MONO,
    constants.ENCODING_STEREO,
    )


class SoundCompilerWindow(window_base_class, BinillaWidget):
    app_root = None

    blam_sound_bank = None
    snd__tag = None

    wav_dir = None
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

    _compiling = False
    _loading = False
    _saving = False

    _pr_tree_iids = ()

    def __init__(self, app_root, *args, **kwargs):
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

        self.wav_dir = tk.StringVar(self)
        self.sound_path = tk.StringVar(self)

        self.generate_mouth_data = tk.IntVar(self, 0)
        self.split_into_smaller_chunks = tk.IntVar(self, 1)

        self.compression = tk.IntVar(self, constants.COMPRESSION_PCM_16_LE)
        self.sample_rate = tk.IntVar(self, constants.SAMPLE_RATE_22K)
        self.encoding = tk.IntVar(self, constants.ENCODING_MONO)
        self.update_mode = tk.IntVar(self, constants.SOUND_COMPILE_MODE_PRESERVE)

        self.adpcm_lookahead = tk.IntVar(self, 3)
        self.adpcm_noise_shaping = tk.IntVar(self, adpcm.NOISE_SHAPING_OFF)

        self.chunk_size_string = tk.StringVar(self, str(self.chunk_size))
        self.chunk_size_string.trace(
            "w", lambda *a, s=self: s.set_chunk_size())

        # make the frames
        self.main_frame = tk.Frame(self)
        self.wav_info_frame = tk.LabelFrame(
            self, text="Import info")

        self.dirs_frame = tk.LabelFrame(
            self.main_frame, text="Directories")
        self.buttons_frame = tk.Frame(self.main_frame)
        self.settings_frame = tk.Frame(
            self.main_frame)

        self.wav_dir_frame = tk.LabelFrame(
            self.dirs_frame, text="Wav files folder")
        self.sound_path_frame = tk.LabelFrame(
            self.dirs_frame, text="Sound output path")

        self.update_mode_frame = tk.LabelFrame(
            self.main_frame, text="What to do with existing sound tag")
        self.processing_frame = tk.LabelFrame(
            self.settings_frame, text="Format settings")
        self.adpcm_frame = tk.LabelFrame(
            self.settings_frame, text="ADPCM settings")
        self.misc_frame = tk.LabelFrame(
            self.settings_frame, text="Misc settings")


        self.compile_mode_replace_rbtn = tk.Radiobutton(
            self.update_mode_frame, anchor="w",
            variable=self.update_mode, value=constants.SOUND_COMPILE_MODE_NEW,
            text="Erase everything(create from scratch)")
        self.compile_mode_preserve_rbtn = tk.Radiobutton(
            self.update_mode_frame, anchor="w",
            variable=self.update_mode, value=constants.SOUND_COMPILE_MODE_PRESERVE,
            text="Preserve tag values(skip fractions and such)")
        self.compile_mode_additive_rbtn = tk.Radiobutton(
            self.update_mode_frame, anchor="w",
            variable=self.update_mode, value=constants.SOUND_COMPILE_MODE_ADDITIVE,
            text="Erase nothing(only add/update permutations)")


        self.compression_menu = ScrollMenu(
            self.processing_frame,  variable=self.compression, menu_width=10,
            options=tuple(
                compression_names[const] for const in compression_menu_values
                )
            )
        self.sample_rate_menu = ScrollMenu(
            self.processing_frame, variable=self.sample_rate, menu_width=5,
            options=tuple(
                sample_rate_names[const] for const in sample_rate_menu_values
                )
            )
        self.encoding_menu = ScrollMenu(
            self.processing_frame, variable=self.encoding, menu_width=5,
            options=tuple(
                encoding_names[const] for const in encoding_menu_values
                )
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
        self.adpcm_lookahead_label.tooltip_string = self.adpcm_lookahead_menu.tooltip_string = (
            "Number of samples to look ahead when determining minimum\n"
            "ADPCM error. Higher numbers are typically better."
            )
        self.adpcm_noise_shaping_label.tooltip_string = self.adpcm_noise_shaping_menu.tooltip_string = (
            "The type of noise shaping algorithm to apply to the sound.\n"
            "Noise shaping is a form of dithering, but for audio.\n"
            "Results will vary, so always test after turning this on."
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
        self.chunk_size_label = tk.Label(
            self.misc_frame, text="Chunk size �")
        self.chunk_size_spinbox = tk.Spinbox(
            self.misc_frame, from_=self.min_chunk_size,
            to=self.max_chunk_size, increment=1024*4,
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
        self.chunk_size_label.tooltip_string = self.chunk_size_spinbox.tooltip_string = (
            'The number of samples per chunk to split long sounds into.\n'
            'NOTE 1:\tThis is for mono. A value of 2 equals 1 stereo sample.\n'
            'NOTE 2:\tThis will be rounded down to a multiple of 64 for ADPCM.'
            )


        self._pr_info_tree = tk.ttk.Treeview(
            self.wav_info_frame, selectmode='browse', padding=(0, 0), height=4)
        self.wav_info_vsb = tk.Scrollbar(
            self.wav_info_frame, orient='vertical',
            command=self._pr_info_tree.yview)
        self.wav_info_hsb = tk.Scrollbar(
            self.wav_info_frame, orient='horizontal',
            command=self._pr_info_tree.xview)
        self._pr_info_tree.config(yscrollcommand=self.wav_info_vsb.set,
                                  xscrollcommand=self.wav_info_hsb.set)

        self.wav_dir_entry = tk.Entry(
            self.wav_dir_frame, textvariable=self.wav_dir, state=tk.DISABLED)
        self.wav_dir_browse_button = tk.Button(
            self.wav_dir_frame, text="Browse", command=self.wav_dir_browse)


        self.sound_path_entry = tk.Entry(
            self.sound_path_frame,
            textvariable=self.sound_path,
            state=tk.DISABLED)
        self.sound_path_browse_button = tk.Button(
            self.sound_path_frame, text="Browse",
            command=self.sound_path_browse)


        self.load_button = tk.Button(
            self.buttons_frame, text="Load wav files",
            command=self.load_wav_files)
        self.compile_button = tk.Button(
            self.buttons_frame, text="Compile sound",
            command=self.compile_sound)

        self.populate_wav_info_tree()

        # pack everything
        self.main_frame.pack(fill="both", side='left', pady=3, padx=3)
        self.wav_info_frame.pack(fill="both", side='left', pady=3, padx=3,
                                 expand=True)

        self.dirs_frame.pack(fill="x")
        self.buttons_frame.pack(fill="x", pady=3, padx=3)
        self.update_mode_frame.pack(fill='both')
        self.settings_frame.pack(fill="both")

        self.wav_dir_frame.pack(fill='x')
        self.sound_path_frame.pack(fill='x')

        self.wav_dir_entry.pack(side='left', fill='x', expand=True)
        self.wav_dir_browse_button.pack(side='left')

        self.sound_path_entry.pack(side='left', fill='x', expand=True)
        self.sound_path_browse_button.pack(side='left')

        self.wav_info_hsb.pack(side="bottom", fill='x')
        self.wav_info_vsb.pack(side="right",  fill='y')
        self._pr_info_tree.pack(side='left', fill='both', expand=True)

        self.load_button.pack(side='left', fill='both', padx=3, expand=True)
        self.compile_button.pack(side='right', fill='both', padx=3, expand=True)

        for w in (self.processing_frame, self.adpcm_frame, self.misc_frame):
            w.pack(expand=True, fill='both')

        for w in (self.compile_mode_replace_rbtn,
                  self.compile_mode_preserve_rbtn,
                  self.compile_mode_additive_rbtn,):
            w.pack(expand=True, fill='both')

        for w in (self.compression_menu,
                  self.sample_rate_menu,
                  self.encoding_menu):
            w.pack(expand=True, side='left', fill='both')

        i = 0
        for w, lbl in (
                (self.adpcm_lookahead_menu, self.adpcm_lookahead_label),
                (self.adpcm_noise_shaping_menu, self.adpcm_noise_shaping_label)
                ):
            lbl.grid(row=i, column=0, sticky="w", padx=(17, 0))
            w.grid(row=i, column=2, sticky="news", padx=(10, 0))
            i += 1


        self.generate_mouth_data_cbtn.grid(
            row=0, column=0, sticky="news", padx=(17, 0))
        self.split_into_smaller_chunks_cbtn.grid(
            row=0, column=1, sticky="news", padx=(17, 0))
        self.chunk_size_label.grid(
            row=1, column=0, sticky="w", padx=(17, 0))
        self.chunk_size_spinbox.grid(
            row=1, column=1, sticky="news", padx=(10, 10))

        self.apply_style()
        if self.app_root is not self:
            self.transient(self.app_root)

    def set_chunk_size(self):
        try:
            new_chunk_size = int(self.chunk_size_string.get())
            if new_chunk_size >= self.min_chunk_size:
                self.chunk_size = new_chunk_size
                return

            self.chunk_size = self.min_chunk_size
        except Exception:
            return

        self.chunk_size_string.set(
            str(("%.20f" % self.chunk_size)).rstrip("0").rstrip("."))

    def populate_wav_info_tree(self):
        pr_tree = self._pr_info_tree
        if not pr_tree['columns']:
            pr_tree['columns'] = ('data', )
            pr_tree.heading("#0")
            pr_tree.heading("data")
            pr_tree.column("#0", minwidth=150, width=150)
            pr_tree.column("data", minwidth=80, width=80, stretch=False)

        for iid in self._pr_tree_iids:
            pr_tree.delete(iid)

        self._pr_tree_iids = []

        wav_files_iid = pr_tree.insert(
            '', 'end', text='WAV pitch ranges',
            tags=('item',), )
        snd__tag_iid = pr_tree.insert(
            '', 'end', text='Sound pitch ranges',
            tags=('item',), )
        self._pr_tree_iids.append(wav_files_iid)
        self._pr_tree_iids.append(snd__tag_iid)

        if not self.blam_sound_bank:
            return

        for pr_name in sorted(self.blam_sound_bank.pitch_ranges):
            pitch_range = self.blam_sound_bank.pitch_ranges[pr_name]

            pitch_range_iid = pr_tree.insert(
                wav_files_iid, 'end', text='%s' % pr_name,
                tags=('item',), values=(len(pitch_range.permutations),))
            for perm_name in sorted(pitch_range.permutations):
                perm = pitch_range.permutations[perm_name]
                iid = pr_tree.insert(pitch_range_iid, 'end', tags=('item',),
                                      text=perm_name)
                pr_tree.insert(
                    iid, 'end', text="Compression", tags=('item',),
                    values=(compression_names.get(
                        perm.source_compression, "<INVALID>"), ))
                pr_tree.insert(
                    iid, 'end', text="Sample rate", tags=('item',),
                    values=("%sHz" % perm.source_sample_rate), )
                pr_tree.insert(
                    iid, 'end', text="Encoding", tags=('item',),
                    values=(encoding_names.get(
                        perm.source_encoding, "<INVALID>"), ))
                pr_tree.insert(
                    iid, 'end', text="Size", tags=('item',),
                    values=("%s bytes" % len(perm.source_sample_data), ))


        if not self.snd__tag:
            return

        sample_rate_const = constants.halo_1_sample_rates.get(
            self.snd__tag.data.tagdata.sample_rate.data)
        encoding_const = self.snd__tag.data.tagdata.encoding.data

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
        for pitch_range in self.snd__tag.data.tagdata.pitch_ranges.STEPTREE:
            pitch_range_iid = pr_tree.insert(
                snd__tag_iid, 'end', text=pitch_range.name, tags=('item',),
                values=(len(pitch_range.permutations.STEPTREE),))
            for perm in pitch_range.permutations.STEPTREE:
                iid = pr_tree.insert(pitch_range_iid, 'end', tags=('item',),
                                     text=perm.name)
                pr_tree.insert(
                    iid, 'end', text="Compression", tags=('item',),
                    values=(
                        compression_names.get(
                            constants.halo_1_compressions.get(
                                perm.compression.data),
                            "<INVALID>"),
                        ))
                pr_tree.insert(
                    iid, 'end', text="Size", tags=('item',),
                    values=("%s bytes" % len(perm.samples.data), ))

    def wav_dir_browse(self):
        if self._compiling or self._loading or self._saving:
            return

        wav_dir = self.wav_dir.get()
        dirpath = askdirectory(
            initialdir=wav_dir, parent=self,
            title="Select the folder of wav files to compile...")

        if not dirpath:
            return

        self.app_root.last_load_dir = os.path.dirname(dirpath)
        self.wav_dir.set(dirpath)

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

    def load_wav_files(self):
        if not self._compiling and not self._loading and not self._saving:
            self._loading = True
            try:
                self._load_wav_files()
            except Exception:
                print(format_exc())
            try:
                self.populate_wav_info_tree()
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
            self._compiling = False

    def _load_wav_files(self):
        sounds_dir = self.wav_dir.get()
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

        try:
            self.snd__tag = snd__def.build(filepath=self.sound_path.get())
        except Exception:
            self.snd__tag = None

        if not self.snd__tag:
            print("    Existing sound tag not detected or could not be loaded.\n"
                  "        A new sound tag will be created.")
        else:
            tagdata = self.snd__tag.data.tagdata
            compression_const = constants.halo_1_compressions.get(
                tagdata.compression.data)
            sample_rate_const = constants.halo_1_sample_rates.get(
                tagdata.sample_rate.data)
            encoding_const = tagdata.encoding.data

            if compression_const in compression_menu_values:
                self.compression.set(
                    compression_menu_values.index(compression_const))

            if sample_rate_const in sample_rate_menu_values:
                self.sample_rate.set(
                    sample_rate_menu_values.index(sample_rate_const))

            if encoding_const in encoding_menu_values:
                self.encoding.set(
                    encoding_menu_values.index(encoding_const))

            self.split_into_smaller_chunks.set(
                bool(tagdata.flags.split_long_sound_into_permutations))
            self.generate_mouth_data.set(
                "dialog" in tagdata.sound_class.enum_name)

        self.blam_sound_bank = blam_sound_bank
        print("Finished loading wav files. Took %s seconds.\n" %
              str(time.time() - start).split('.')[0])

    def _compile_sound(self):
        if not self.blam_sound_bank:
            return

        print("Compiling...")
        while not self.sound_path.get():
            self.sound_path_browse(True)
            if not self.sound_path.get() and self.warn_cancel():
                print("    Sound compilation cancelled.")
                return

        if self.snd__tag is None:
            print("Creating new sound tag.")
            self.snd__tag = snd__def.build()
        else:
            print("Updating existing sound tag.")

        self.snd__tag.filepath = self.sound_path.get()

        self.update()

        self.blam_sound_bank.chunk_size = self.chunk_size * 2
        self.blam_sound_bank.compression = compression_menu_values[
            self.compression.get()]
        self.blam_sound_bank.sample_rate = sample_rate_menu_values[
            self.sample_rate.get()]
        self.blam_sound_bank.encoding = encoding_menu_values[
            self.encoding.get()]
        self.blam_sound_bank.adpcm_noise_shaping = self.adpcm_noise_shaping.get()
        self.blam_sound_bank.adpcm_lookahead = self.adpcm_lookahead.get()
        self.blam_sound_bank.split_into_smaller_chunks = bool(self.split_into_smaller_chunks.get())

        try:
            print("Paritioning and compressing permutations...", end="")
            self.update()
            self.blam_sound_bank.compress_samples()
            print(" Done.")

            if self.generate_mouth_data.get():
                print("Generating mouth data...", end="")
                self.blam_sound_bank.generate_mouth_data()
                print(" Done.")
        except Exception:
            print("\n", format_exc(), sep="")
            print("    Error occurred while partitoning and compressing.")
            return

        self.update()

        errors = compile_sound(
            self.snd__tag, self.blam_sound_bank,
            update_mode=self.update_mode.get())

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
