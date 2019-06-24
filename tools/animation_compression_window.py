import os
import tkinter as tk
import time

from tkinter import messagebox
from tkinter.filedialog import askdirectory, asksaveasfilename
from traceback import format_exc

from binilla.util import sanitize_path, get_cwd, PATHDIV
from binilla.widgets import BinillaWidget
from reclaimer.hek.defs.antr import antr_def
from reclaimer.animation.animation_compression import \
     compress_animation, decompress_animation

if __name__ == "__main__":
    window_base_class = tk.Tk
else:
    window_base_class = tk.Toplevel

curr_dir = get_cwd(__file__)


class AnimationCompressionWindow(window_base_class, BinillaWidget):
    app_root = None
    tags_dir = ''

    _working = False
    _loading = False

    _anims_tree_iids = ()

    def __init__(self, app_root, *args, **kwargs):
        if window_base_class == tk.Toplevel:
            kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
            self.app_root = app_root
        else:
            self.app_root = self

        BinillaWidget.__init__(self, *args, **kwargs)
        window_base_class.__init__(self, app_root, *args, **kwargs)

        self.title("Model_animations compressor/decompressor")
        self.resizable(1, 1)
        self.update()
        for sub_dirs in ((), ('..', ), ('icons', )):
            try:
                self.iconbitmap(os.path.os.path.join(
                    *((curr_dir,) + sub_dirs + ('mozzarilla.ico', ))
                    ))
                break
            except Exception:
                pass

        tags_dir = getattr(app_root, "tags_dir", "")

        self.tags_dir = tk.StringVar(self, tags_dir if tags_dir else "")
        self.model_animations_path = tk.StringVar(self)


        # make the frames
        self.main_frame = tk.Frame(self)
        self.anims_info_frame = tk.LabelFrame(
            self, text="Animations info")

        self.model_animations_path_frame = tk.LabelFrame(
            self.main_frame, text="Model_animations path")
        self.buttons_frame = tk.Frame(self.main_frame)
        self.settings_frame = tk.Frame(self.main_frame)


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
            self.model_animations_path_frame, width=45,
            textvariable=self.model_animations_path,
            state=tk.DISABLED)
        self.model_animations_path_browse_button = tk.Button(
            self.model_animations_path_frame, text="Browse",
            command=self.model_animations_path_browse)

        self.compress_button = tk.Button(
            self.buttons_frame, text="Compress",
            command=self.compress_model_animations)
        self.decompress_button = tk.Button(
            self.buttons_frame, text="Decompress",
            command=self.decompress_model_animations)

        self.populate_animations_info_tree()

        # pack everything
        self.main_frame.pack(fill="both", side='left', pady=3, padx=3)
        self.anims_info_frame.pack(fill="both", side='left', pady=3, padx=3,
                                   expand=True)

        self.model_animations_path_frame.pack(fill='x')
        self.buttons_frame.pack(fill="x", pady=3, padx=3)
        self.settings_frame.pack(fill="both")

        self.model_animations_path_entry.pack(side='left', fill='x', expand=True)
        self.model_animations_path_browse_button.pack(side='left')

        self.anims_info_hsb.pack(side="bottom", fill='x')
        self.anims_info_vsb.pack(side="right",  fill='y')
        self.anims_info_tree.pack(side='left', fill='both', expand=True)

        self.compress_button.pack(side='right', fill='both', padx=3, expand=True)
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

    def model_animations_path_browse(self, force=False):
        if not force and (self._working or self._loading):
            return

        antr_dir = os.path.dirname(self.model_animations_path.get())
        if self.tags_dir.get() and not antr_dir:
            antr_dir = self.tags_dir.get()

        fp = asksaveasfilename(
            initialdir=antr_dir, title="Model_animations to compress/decompress", parent=self,
            filetypes=(("Model animations graph", "*.model_animations"), ('All', '*')))

        if not fp:
            return

        fp = sanitize_path(fp)
        if not os.path.splitext(fp)[-1]:
            fp += ".model_animations"

        self.app_root.last_load_dir = os.path.dirname(fp)
        self.model_animations_path.set(fp)

        path_pieces = os.path.join(self.app_root.last_load_dir, '').split(
            "%stags%s" % (PATHDIV, PATHDIV))
        if len(path_pieces) > 1:
            self.tags_dir.set(os.path.join(path_pieces[0], "tags"))

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

    def _do_compression(self, compress):
        state = "compress" if compress else "decompress"
        print("%sing animations." % state.capitalize())
        while not self.model_animations_path.get():
            self.model_animations_path_browse(True)
            if (not self.model_animations_path.get()) and self.warn_cancel():
                print("    Model_animations %sion cancelled." % state)
                return

        self.app_root.update()
        antr_tag = antr_def.build(filepath=self.model_animations_path.get())
        anims = antr_tag.data.tagdata.animations.STEPTREE
        errors = False
        for anim in anims:
            try:
                if compress:
                    compress_animation(anim)
                else:
                    decompress_animation(anim)
            except Exception:
                print(format_exc())
                self.update()
                errors = True

        if errors:
            self.update()
            if messagebox.askyesno(
                    "Model_animations %sing failed" % state,
                    ("Errors occurred while %sing(check console). " % state) +
                     "Do you want to save the model_animations tag anyway?",
                    icon='warning', parent=self):
                print("    Model_animations compilation failed.")
                return

        try:
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
    AnimationCompressionWindow(None).mainloop()
