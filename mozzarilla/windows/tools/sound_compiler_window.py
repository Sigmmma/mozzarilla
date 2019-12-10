import os
import tkinter as tk
import time

from tkinter import messagebox
from tkinter.filedialog import askdirectory, asksaveasfilename
from traceback import format_exc

from binilla.util import sanitize_path, get_cwd
from binilla.widgets.binilla_widget import BinillaWidget
from binilla.widgets.scroll_menu import ScrollMenu

from reclaimer.hek.defs.snd_ import snd__def
from reclaimer.sounds.blam_sound_bank import BlamSoundBank
from reclaimer.sounds import constants

if __name__ == "__main__":
    window_base_class = tk.Tk
else:
    window_base_class = tk.Toplevel

curr_dir = get_cwd(__file__)


encoding_names = {
    constants.ENCODING_MONO: "mono",
    constants.ENCODING_STEREO: "stereo",
    }

compression_names = {
    constants.COMPRESSION_PCM_8_SIGNED: "8bit PCM signed",
    constants.COMPRESSION_PCM_8_UNSIGNED: "8bit PCM unsigned",
    constants.COMPRESSION_PCM_16_LE: "16bit PCM",
    constants.COMPRESSION_PCM_16_BE: "16bit PCM",
    constants.COMPRESSION_PCM_24_LE: "24bit PCM",
    constants.COMPRESSION_PCM_24_BE: "24bit PCM",
    constants.COMPRESSION_PCM_32_LE: "32bit PCM",
    constants.COMPRESSION_PCM_32_BE: "32bit PCM",
    constants.COMPRESSION_ADPCM: "ADPCM",
    constants.COMPRESSION_OGG: "Ogg Vorbis",
    }

sample_rate_names = {
    constants.SAMPLE_RATE_22K: "22kHz",
    constants.SAMPLE_RATE_44K: "44kHz",
    }

encoding_menu_values = (
    constants.ENCODING_MONO,
    constants.ENCODING_STEREO,
    )

compression_menu_values = (
    constants.COMPRESSION_PCM_16_LE,
    constants.COMPRESSION_ADPCM,
    constants.COMPRESSION_OGG
    )

sample_rate_menu_values = (
    constants.SAMPLE_RATE_22K,
    constants.SAMPLE_RATE_44K,
    )


class SoundCompilerWindow(window_base_class, BinillaWidget):
    app_root = None

    blam_sound_bank = None
    snd__tag = None
    
    wav_dir = None
    sound_path = None
    
    generate_mouth_data = None
    split_to_adpcm_blocksize = None
    split_into_smaller_chunks = None

    encoding = None
    compression = None
    sample_rate = None
    update_mode = None

    _compiling = False
    _loading = False
    _saving = False

    _wav_tree_iids = ()

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
        for sub_dirs in ((), ('..', '..'), ('icons', )):
            try:
                self.iconbitmap(os.path.os.path.join(
                    *((curr_dir,) + sub_dirs + ('mozzarilla.ico', ))
                    ))
                break
            except Exception:
                pass

        self.wav_dir = tk.StringVar(self)
        self.sound_path = tk.StringVar(self)

        self.generate_mouth_data = tk.IntVar(self, 0)
        self.split_to_adpcm_blocksize = tk.IntVar(self, 0)
        self.split_into_smaller_chunks = tk.IntVar(self, 1)

        self.encoding = tk.IntVar(self, constants.ENCODING_MONO)
        self.compression = tk.IntVar(self, constants.COMPRESSION_PCM_16_LE)
        self.sample_rate = tk.IntVar(self, constants.SAMPLE_RATE_22K)
        self.update_mode = tk.IntVar(self, constants.SOUND_COMPILE_MODE_PRESERVE)

        # make the frames
        self.main_frame = tk.Frame(self)
        self.wav_info_frame = tk.LabelFrame(
            self, text="Wav files info")

        self.dirs_frame = tk.LabelFrame(
            self.main_frame, text="Directories")
        self.buttons_frame = tk.Frame(self.main_frame)
        self.settings_frame = tk.LabelFrame(
            self.main_frame, text="Compilation settings")

        self.wav_dir_frame = tk.LabelFrame(
            self.dirs_frame, text="Wav files folder")
        self.sound_path_frame = tk.LabelFrame(
            self.dirs_frame, text="Sound output path")

        self.update_mode_frame = tk.LabelFrame(
            self.main_frame, text="What to do with existing sound tag")
        self.processing_frame = tk.Frame(self.settings_frame)
        self.flags_frame = tk.Frame(self.settings_frame)


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
            self.processing_frame,  variable=self.compression, menu_width=5,
            options=tuple(
                compression_names[const] for const in compression_menu_values
                )
            )
        self.encoding_menu = ScrollMenu(
            self.processing_frame, variable=self.encoding, menu_width=5,
            options=tuple(
                encoding_names[const] for const in encoding_menu_values
                )
            )
        self.sample_rate_menu = ScrollMenu(
            self.processing_frame, variable=self.sample_rate, menu_width=5,
            options=tuple(
                sample_rate_names[const] for const in sample_rate_menu_values
                )
            )
        self.encoding_menu.sel_index = 0
        self.compression_menu.sel_index = 0
        self.sample_rate_menu.sel_index = 0

        self.generate_mouth_data_cbtn = tk.Checkbutton(
            self.flags_frame, variable=self.generate_mouth_data,
            anchor="w", text="Generate mouth data")
        self.split_to_adpcm_blocksize_cbtn = tk.Checkbutton(
            self.flags_frame, variable=self.split_to_adpcm_blocksize,
            anchor="w", text="Split to ADPCM blocksize")
        self.split_into_smaller_chunks_cbtn = tk.Checkbutton(
            self.flags_frame, variable=self.split_into_smaller_chunks,
            anchor="w", text="Split long sounds into pieces")


        self.wav_info_tree = tk.ttk.Treeview(
            self.wav_info_frame, selectmode='browse', padding=(0, 0), height=4)
        self.wav_info_vsb = tk.Scrollbar(
            self.wav_info_frame, orient='vertical',
            command=self.wav_info_tree.yview)
        self.wav_info_hsb = tk.Scrollbar(
            self.wav_info_frame, orient='horizontal',
            command=self.wav_info_tree.xview)
        self.wav_info_tree.config(yscrollcommand=self.wav_info_vsb.set,
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
        self.wav_info_tree.pack(side='left', fill='both', expand=True)

        self.load_button.pack(side='left', fill='both', padx=3, expand=True)
        self.compile_button.pack(side='right', fill='both', padx=3, expand=True)

        for w in (self.processing_frame, self.flags_frame):
            w.pack(expand=True, fill='both')
        
        for w in (self.compile_mode_replace_rbtn,
                  self.compile_mode_preserve_rbtn,
                  self.compile_mode_additive_rbtn,):
            w.pack(expand=True, fill='both')

        for w in (self.compression_menu, self.sample_rate_menu,
                  self.encoding_menu):
            w.pack(expand=True, side='left', fill='both')

        for w in (self.generate_mouth_data_cbtn,
                  self.split_to_adpcm_blocksize_cbtn,
                  self.split_into_smaller_chunks_cbtn,):
            w.pack(expand=True, fill='both')

        self.apply_style()
        if self.app_root is not self:
            self.transient(self.app_root)

    def populate_wav_info_tree(self):
        wav_tree = self.wav_info_tree
        if not wav_tree['columns']:
            wav_tree['columns'] = ('data', )
            wav_tree.heading("#0")
            wav_tree.heading("data")
            wav_tree.column("#0", minwidth=100, width=100)
            wav_tree.column("data", minwidth=80, width=80, stretch=False)

        for iid in self._wav_tree_iids:
            wav_tree.delete(iid)

        self._wav_tree_iids = []

        if not self.blam_sound_bank:
            return
        '''
        nodes_iid = wav_tree.insert('', 'end', text="Nodes", tags=('item',),
                                    values=(len(self.blam_sound_bank.nodes),))
        self._wav_tree_iids.append(nodes_iid)
        nodes = self.blam_sound_bank.nodes
        for node in nodes:
            iid = wav_tree.insert(nodes_iid, 'end', text=node.name, tags=('item',))
            parent_name = child_name = sibling_name = "NONE"
            if node.sibling_index >= 0:
                sibling_name = nodes[node.sibling_index].name

            wav_tree.insert(iid, 'end', text="Next sibling",
                            values=(sibling_name, ), tags=('item',),)
        '''


    def wav_dir_browse(self):
        if self._compiling or self._loading or self._saving:
            return

        wav_dir = self.wav_dir.get()
        dirpath = askdirectory(
            initialdir=wav_dir, parent=self,
            title="Select the folder of wav files to compile...")

        dirpath = os.path.join(sanitize_path(dirpath), "")
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

        fp = sanitize_path(fp)
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
            encoding_const = tagdata.encoding.data
            compression_const = constants.halo_1_compressions.get(
                tagdata.compression.data)
            sample_rate_const = constants.halo_1_sample_rates.get(
                tagdata.sample_rate.data)

            if encoding_const in encoding_menu_values:
                self.encoding.set(
                    encoding_menu_values.index(encoding_const))

            if compression_const in compression_menu_values:
                self.compression.set(
                    compression_menu_values.index(compression_const))

            if sample_rate_const in sample_rate_menu_values:
                self.sample_rate.set(
                    sample_rate_menu_values.index(sample_rate_const))

            self.split_into_smaller_chunks.set(
                bool(tagdata.flags.split_long_sound_into_permutations))
            self.split_to_adpcm_blocksize.set(
                bool(tagdata.flags.fit_to_adpcm_blocksize))
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
            if (not self.sound_path.get()) and self.warn_cancel():
                print("    Sound compilation cancelled.")
                return

        if self.snd__tag is None:
            print("Creating new sound tag.")
            self.snd__tag = snd__def.build()
            self.snd__tag.filepath = self.sound_path.get()
        else:
            print("Updating existing sound tag.")

        self.update()

        self.blam_sound_bank.encoding = self.encoding.get()
        self.blam_sound_bank.compression = self.compression.get()
        self.blam_sound_bank.sample_rate = self.sample_rate.get()
        self.blam_sound_bank.split_into_smaller_chunks = bool(self.split_into_smaller_chunks.get())
        self.blam_sound_bank.split_to_adpcm_blocksize = bool(self.split_to_adpcm_blocksize.get())
        self.blam_sound_bank.generate_mouth_data = bool(self.generate_mouth_data.get())

        errors = compile_sound(
            self.snd__tag, self.blam_sound_bank, self.update_mode.get())

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
