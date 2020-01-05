#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

import os
import tkinter as tk
import time

from pathlib import Path
from tkinter import messagebox
from traceback import format_exc

from binilla.widgets.binilla_widget import BinillaWidget
from binilla.windows.filedialog import askdirectory, askopenfilename

from reclaimer.hek.defs.antr import antr_def as halo_antr_def
from reclaimer.stubbs.defs.antr import antr_def as stubbs_antr_def
from reclaimer.animation.animation_compression import \
     compress_animation, decompress_animation

from mozzarilla import editor_constants as e_c
from supyr_struct.util import is_path_empty

if __name__ == "__main__":
    window_base_class = tk.Tk
else:
    window_base_class = tk.Toplevel


class AnimationsCompressionWindow(window_base_class, BinillaWidget):
    app_root = None

    _working = False
    _loading = False

    _anims_tree_iids = ()

    def __init__(self, app_root, *args, **kwargs):
        if window_base_class == tk.Toplevel:
            kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
            self.app_root = app_root
        else:
            self.app_root = self

        window_base_class.__init__(self, app_root, *args, **kwargs)
        BinillaWidget.__init__(self, *args, **kwargs)

        #self.title("Model_animations compressor/decompressor")
        self.title("Model_animations decompressor")
        #self.resizable(1, 1)
        self.resizable(0, 0)
        self.update()
        anims_dir = getattr(app_root, "tags_dir", str(Path.cwd()))

        try:
            self.iconbitmap(e_c.MOZZ_ICON_PATH)
        except Exception:
            print("Could not load window icon.")

        self.model_animations_path = tk.StringVar(self)
        self.model_animations_dir = tk.StringVar(self, anims_dir if anims_dir else "")
        self.preserve_compressed = tk.IntVar(self, True)
        self.overwrite = tk.IntVar(self, False)


        # make the frames
        self.main_frame = tk.Frame(self)
        self.anims_info_frame = tk.LabelFrame(
            self, text="Animations info")

        self.model_animations_path_frame = tk.LabelFrame(
            self.main_frame, text="Model_animations path")
        self.model_animations_path_buttons_frame = tk.Frame(self.main_frame)
        self.model_animations_dir_frame = tk.LabelFrame(
            self.main_frame, text="Model_animations dir")
        self.model_animations_dir_buttons_frame  = tk.Frame(self.main_frame)
        self.settings_frame = tk.Frame(self.main_frame)

        self.preserve_compressed_cbtn = tk.Checkbutton(
            self.settings_frame, anchor="w", variable=self.preserve_compressed,
            text="Preserve compressed animation data in tag")
        self.overwrite_cbtn = tk.Checkbutton(
            self.settings_frame, anchor="w", variable=self.overwrite,
            text="Overwrite model_animations tags")

        self.anims_info_tree = tk.ttk.Treeview(
            self.anims_info_frame, selectmode='browse', padding=(0, 0), height=4)
        self.anims_info_vsb = tk.Scrollbar(
            self.anims_info_frame, orient='vertical',
            command=self.anims_info_tree.yview)
        self.anims_info_hsb = tk.Scrollbar(
            self.anims_info_frame, orient='horizontal',
            command=self.anims_info_tree.xview)
        self.anims_info_tree.config(yscrollcommand=self.anims_info_vsb.set,
                                    xscrollcommand=self.anims_info_hsb.set)

        self.model_animations_path_entry = tk.Entry(
            self.model_animations_path_frame, width=50,
            textvariable=self.model_animations_path,
            state=tk.DISABLED)
        self.model_animations_path_browse_button = tk.Button(
            self.model_animations_path_frame, text="Browse",
            command=self.model_animations_path_browse)

        self.model_animations_dir_entry = tk.Entry(
            self.model_animations_dir_frame, width=50,
            textvariable=self.model_animations_dir,
            state=tk.DISABLED)
        self.model_animations_dir_browse_button = tk.Button(
            self.model_animations_dir_frame, text="Browse",
            command=self.model_animations_dir_browse)

        self.compress_button = tk.Button(
            self.model_animations_path_buttons_frame, text="Compress tag",
            command=self.compress_model_animations)
        self.decompress_button = tk.Button(
            self.model_animations_path_buttons_frame, text="Decompress tag",
            command=self.decompress_model_animations)

        self.compress_all_button = tk.Button(
            self.model_animations_dir_buttons_frame, text="Compress all",
            command=self.compress_all_model_animations)
        self.decompress_all_button = tk.Button(
            self.model_animations_dir_buttons_frame, text="Decompress all",
            command=self.decompress_all_model_animations)

        self.populate_animations_info_tree()

        # pack everything
        self.main_frame.pack(fill="both", side='left', pady=3, padx=3)
        #self.anims_info_frame.pack(fill="both", side='left', pady=3, padx=3, expand=True)

        self.model_animations_dir_frame.pack(fill='x')
        self.model_animations_dir_buttons_frame.pack(fill="x", pady=3, padx=3)
        self.model_animations_path_frame.pack(fill='x')
        self.model_animations_path_buttons_frame.pack(fill="x", pady=3, padx=3)
        self.settings_frame.pack(fill="both")

        for w in (self.preserve_compressed_cbtn, self.overwrite_cbtn):
            w.pack(expand=True, fill='both')

        self.model_animations_dir_entry.pack(side='left', fill='x', expand=True)
        self.model_animations_dir_browse_button.pack(side='left')

        self.model_animations_path_entry.pack(side='left', fill='x', expand=True)
        self.model_animations_path_browse_button.pack(side='left')

        self.anims_info_hsb.pack(side="bottom", fill='x')
        self.anims_info_vsb.pack(side="right",  fill='y')
        self.anims_info_tree.pack(side='left', fill='both', expand=True)

        #self.compress_all_button.pack(side='right', fill='both', padx=3, expand=True)
        self.decompress_all_button.pack(side='right', fill='both', padx=3, expand=True)
        #self.compress_button.pack(side='right', fill='both', padx=3, expand=True)
        self.decompress_button.pack(side='right', fill='both', padx=3, expand=True)

        self.apply_style()
        if self.app_root is not self:
            self.transient(self.app_root)

    def populate_animations_info_tree(self):
        anims_tree = self.anims_info_tree
        if not anims_tree['columns']:
            anims_tree['columns'] = ('data', )
            anims_tree.heading("#0")
            anims_tree.heading("data")
            anims_tree.column("#0", minwidth=100, width=100)
            anims_tree.column("data", minwidth=80, width=80, stretch=False)

        for iid in self._anims_tree_iids:
            anims_tree.delete(iid)

        self._anims_tree_iids = []

    def model_animations_dir_browse(self, force=False):
        if not force and (self._working or self._loading):
            return

        dirpath = askdirectory(
            initialdir=self.model_animations_dir.get(), parent=self,
            title="Directory of model_animations to compress/decompress")

        if not dirpath:
            return

        self.app_root.last_load_dir = dirpath
        self.model_animations_dir.set(dirpath)

    def model_animations_path_browse(self, force=False):
        if not force and (self._working or self._loading):
            return

        antr_dir = os.path.dirname(self.model_animations_path.get())
        if self.model_animations_dir.get() and not antr_dir:
            antr_dir = self.model_animations_dir.get()

        fp = askopenfilename(
            initialdir=antr_dir, title="Model_animations to compress/decompress", parent=self,
            filetypes=(("Model animations graph", "*.model_animations"), ('All', '*')))

        if not fp:
            return

        fp = Path(fp)
        if not fp.suffix:
            fp = fp.with_suffix(".model_animations")

        self.app_root.last_load_dir = str(fp.parent)
        self.model_animations_path.set(str(fp))

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

    def compress_all_model_animations(self):
        if not self._working and not self._loading:
            self._working = True
            try:
                self._do_all_compression(True)
            except Exception:
                print(format_exc())
            self._working = False

    def decompress_all_model_animations(self):
        if not self._working and not self._loading:
            self._working = True
            try:
                self._do_all_compression(False)
            except Exception:
                print(format_exc())
            self._working = False

    def compress_model_animations(self):
        if not self._working and not self._loading:
            self._working = True
            try:
                self._do_compression(True)
            except Exception:
                print(format_exc())
            self._working = False

    def decompress_model_animations(self):
        if not self._working and not self._loading:
            self._working = True
            try:
                self._do_compression(False)
            except Exception:
                print(format_exc())
            self._working = False

    def _do_all_compression(self, compress):
        antr_dir = self.model_animations_dir.get()
        while not antr_dir:
            self.model_animations_dir_browse(True)
            antr_dir = self.model_animations_dir.get()
            if not antr_dir and self.warn_cancel():
                print("    Model_animations %sion cancelled." % compress)
                return

        for root, _, files in os.walk(antr_dir):
            for fname in files:
                try:
                    if Path(fname).suffix.lower() != ".model_animations":
                        continue
                    self._do_compression(compress, Path(root, fname))
                except Exception:
                    pass#print(format_exc())

    def _do_compression(self, compress, antr_path=None):
        state = "compress" if compress else "decompress"
        if not antr_path:
            antr_path = self.model_animations_path.get()

        antr_path = Path(antr_path)

        while is_path_empty(antr_path):
            self.model_animations_path_browse(True)
            antr_path = Path(self.model_animations_path.get())
            if is_path_empty(antr_path) and self.warn_cancel():
                return

        print("%sing %s." % (state.capitalize(), antr_path))

        self.app_root.update()
        antr_def = None
        try:
            with antr_path.open('rb') as f:
                f.seek(36)
                tag_type = f.read(4)
                if tag_type == b'antr':
                    f.seek(56)
                    antr_ver = f.read(2)
                    if antr_ver == b'\x00\x05':
                        antr_def = stubbs_antr_def
                    elif antr_ver == b'\x00\x04':
                        antr_def = halo_antr_def
        except Exception:
            pass

        if antr_def is None:
            print("Could not determine model_animation tag version.")
            return

        antr_tag = antr_def.build(filepath=antr_path)
        anims = antr_tag.data.tagdata.animations.STEPTREE
        errors = False
        edited = False
        for anim in anims:
            try:
                if not anim.flags.compressed_data:
                    continue

                if compress:
                    edited |= compress_animation(anim)
                else:
                    edited |= decompress_animation(anim, self.preserve_compressed.get())
            except Exception:
                print(format_exc())
                self.update()
                errors = True

        if not edited:
            print("    No changes made. Not saving.")
            return

        if errors:
            self.update()
            if not messagebox.askyesno(
                    "Model_animations %sing failed" % state,
                    ("Errors occurred while %sing(check console). " % state) +
                     "Do you want to save the model_animations tag anyway?",
                    icon='warning', parent=self):
                print("    Model_animations compilation failed.")
                return

        try:
            if not self.overwrite.get():
                fp = Path(antr_tag.filepath)
                antr_tag.filepath = Path(
                    fp.parent, fp.stem + "_DECOMP" + fp.suffix)

            antr_tag.calc_internal_data()
            antr_tag.serialize(temp=False, backup=False, calc_pointers=False,
                               int_test=False)
            print("    Finished")
        except Exception:
            print(format_exc())
            print("    Could not save %sed model_animations." % state)

    def warn_cancel(self):
        return bool(messagebox.askyesno(
            "Unsaved model_animations",
            "Are you sure you wish to cancel?",
            icon='warning', parent=self))


if __name__ == "__main__":
    AnimationsCompressionWindow(None).mainloop()
