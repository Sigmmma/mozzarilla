import os
import tkinter as tk

from os.path import splitext, dirname, join, relpath, basename, isfile, exists
from tkinter import messagebox
from tkinter.filedialog import askdirectory, asksaveasfilename
from traceback import format_exc

from binilla.util import sanitize_path, is_in_dir, get_cwd
from binilla.widgets import BinillaWidget
from reclaimer.jms import read_jms, MergedJmsModel
from reclaimer.hek.defs.mod2 import mod2_def
from reclaimer.hek.defs.objs.matrices import quaternion_to_matrix, Matrix
from reclaimer.hek.model_compilation import compile_gbxmodel

if __name__ == "__main__":
    model_compiler_base_class = tk.Tk
else:
    model_compiler_base_class = tk.Toplevel

curr_dir = get_cwd(__file__)

class ModelCompilerWindow(model_compiler_base_class, BinillaWidget):
    app_root = None
    tags_dir = ''

    merged_jms = None
    mod2_tag = None

    shader_paths = ()
    shader_types = ()

    def __init__(self, app_root, *args, **kwargs):
        if model_compiler_base_class == tk.Toplevel:
            kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
            self.app_root = app_root
        else:
            self.app_root = self

        model_compiler_base_class.__init__(self, app_root, *args, **kwargs)

        self.title("Gbxmodel compiler")
        self.resizable(0, 1)
        self.update()
        try:
            try:
                self.iconbitmap(join(curr_dir, '..', 'mozzarilla.ico'))
            except Exception:
                self.iconbitmap(join(curr_dir, 'icons', 'mozzarilla.ico'))
        except Exception:
            print("Could not load window icon.")


        self.tags_dir = tk.StringVar(self)
        self.jms_dir = tk.StringVar(self)
        self.gbxmodel_path = tk.StringVar(self)


        # make the frames
        self.main_frame = tk.Frame(self)
        self.settings_frame = tk.LabelFrame(self.main_frame, text="Settings")
        self.jms_info_frame = tk.LabelFrame(self.main_frame, text="Jms info")
        self.buttons_frame = tk.Frame(self.main_frame)

        self.jms_dir_frame = tk.LabelFrame(
            self.settings_frame, text="Jms files folder")
        self.tags_dir_frame = tk.LabelFrame(
            self.settings_frame, text="Tags directory root folder")
        self.gbxmodel_path_frame = tk.LabelFrame(
            self.settings_frame, text="Gbxmodel output path")


        self.jms_dir_entry = tk.Entry(
            self.jms_dir_frame, textvariable=self.jms_dir, state=tk.DISABLED)
        self.jms_dir_browse_button = tk.Button(
            self.jms_dir_frame, text="Browse", command=self.jms_dir_browse)


        self.tags_dir_entry = tk.Entry(
            self.tags_dir_frame, textvariable=self.tags_dir, state=tk.DISABLED)
        self.tags_dir_browse_button = tk.Button(
            self.tags_dir_frame, text="Browse", command=self.tags_dir_browse)


        self.gbxmodel_path_entry = tk.Entry(
            self.gbxmodel_path_frame, textvariable=self.gbxmodel_path,
            state=tk.DISABLED)
        self.gbxmodel_path_browse_button = tk.Button(
            self.gbxmodel_path_frame, text="Browse",
            command=self.gbxmodel_path_browse)


        self.load_button = tk.Button(
            self.buttons_frame, text="Load JMS models",
            command=self.load_models)
        self.compile_button = tk.Button(
            self.buttons_frame, text="Compile Gbxmodel",
            command=self.compile_gbxmodel)

        # pack everything
        self.main_frame.pack(fill='both')

        self.settings_frame.grid(sticky='news', row=0, column=0)
        self.jms_info_frame.grid(sticky='news', row=0, column=1)
        self.buttons_frame.grid(sticky='news', columnspan=2,
                                row=1, column=0, pady=3, padx=3)

        self.jms_dir_frame.pack(expand=True, fill='x')
        self.tags_dir_frame.pack(expand=True, fill='x')
        self.gbxmodel_path_frame.pack(expand=True, fill='x')

        self.jms_dir_entry.pack(side='left', expand=True, fill='x')
        self.jms_dir_browse_button.pack(side='left')

        self.gbxmodel_path_entry.pack(side='left', expand=True, fill='x')
        self.gbxmodel_path_browse_button.pack(side='left')

        self.tags_dir_entry.pack(side='left', expand=True, fill='x')
        self.tags_dir_browse_button.pack(side='left')

        self.load_button.pack(side='left', expand=True, fill='both', padx=3)
        self.compile_button.pack(side='left', expand=True, fill='both', padx=3)

    def jms_dir_browse(self):
        dirpath = askdirectory(
            initialdir=self.jms_dir.get(), parent=self,
            title="Select the folder of jms models to compile...")

        dirpath = join(sanitize_path(dirpath), "")
        if not dirpath:
            return

        tags_dir = self.tags_dir.get()
        data_dir = join(dirname(tags_dir), "data", "")

        if tags_dir and data_dir and basename(dirpath).lower() == "models":
            object_dir = dirname(dirpath)

            if object_dir and is_in_dir(object_dir, data_dir):
                tag_path = join(object_dir, basename(object_dir))
                tag_path = join(tags_dir, relpath(tag_path, data_dir))
                self.gbxmodel_path.set(tag_path + ".gbxmodel")

        self.app_root.last_load_dir = dirname(dirpath)
        self.jms_dir.set(dirpath)

    def tags_dir_browse(self):
        tags_dir = askdirectory(
            initialdir=self.tags_dir.get(), parent=self,
            title="Select the root of the tags directory")

        tags_dir = sanitize_path(join(tags_dir, ""))
        if not tags_dir:
            return

        self.app_root.last_load_dir = dirname(tags_dir)
        self.tags_dir.set(tags_dir)

    def gbxmodel_path_browse(self):
        fp = asksaveasfilename(
            initialdir=dirname(self.gbxmodel_path.get()),
            title="Save gbxmodel to...", parent=self,
            filetypes=(("Gearbox model", "*.gbxmodel"), ('All', '*')))

        if not fp:
            return

        fp = sanitize_path(fp)
        if not splitext(fp)[-1]:
            fp += ".gbxmodel"

        self.app_root.last_load_dir = dirname(fp)
        self.gbxmodel_path.set(fp)

    def apply_style(self, seen=None):
        BinillaWidget.apply_style(self, seen)
        self.update()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        self.geometry("%sx%s" % (w, h))
        self.minsize(width=w, height=h)

    def destroy(self):
        try:
            self.app_root.tool_windows.pop(self.window_name, None)
        except AttributeError:
            pass
        model_compiler_base_class.destroy(self)

    def load_models(self):
        models_dir = self.jms_dir.get()
        if not models_dir:
            return


        print("Locating jms files...")
        fps = []
        for _, __, files in os.walk(models_dir):
            for fname in files:
                if fname.lower().endswith(".jms"):
                    fps.append(join(models_dir, fname))

            break

        if not fps:
            print("    No valid jms files found in the folder.")
            return

        self.mod2_tag = self.merged_jms = None

        jms_datas = []
        print("Loading jms files...")
        self.app_root.update()
        for fp in fps:
            try:
                print("    %s" % fp)
                self.app_root.update()
                with open(fp, "r") as f:
                    jms_datas.append(read_jms(f.read(), '',
                                              basename(fp).split('.')[0]))
            except Exception:
                print(format_exc())
                print("    Could not parse jms file.")
                self.app_root.update()

        if not jms_datas:
            print("    No valid jms files found.")
            return

        first_crc = None
        for jms_data in jms_datas:
            if first_crc is None:
                first_crc = jms_data.node_list_checksum
            elif first_crc != jms_data.node_list_checksum:
                print("    Warning, not all node list checksums match.")
                break


        print("Parsing and merging jms files...")
        self.app_root.update()
        self.merged_jms = merged_jms = MergedJmsModel()
        errors_occurred = False
        for jms_data in jms_datas:
            errors = merged_jms.merge_jms_model(jms_data)
            errors_occurred |= bool(errors)
            if errors:
                print("    Errors in '%s'" % jms_data.name)
                for error in errors:
                    print("        " + error)

            self.app_root.update()

        if errors_occurred:
            print("    Cannot load all jms files.")
            return

        u_scale, v_scale = merged_jms.calc_uv_scales()
        merged_jms.u_scale = max(1.0, u_scale)
        merged_jms.v_scale = max(1.0, v_scale)
        parented_nodes = set()
        # setup the parent node hierarchy
        for parent_idx in range(len(merged_jms.nodes)):
            node = merged_jms.nodes[parent_idx]
            if node.first_child > 0:
                sib_idx = node.first_child
                while sib_idx >= 0:
                    parented_nodes.add(sib_idx)
                    sib_node = merged_jms.nodes[sib_idx]
                    sib_node.parent_index = parent_idx
                    sib_idx = sib_node.sibling_index


        try:
            if isfile(self.gbxmodel_path.get()):
                self.mod2_tag = mod2_def.build(filepath=self.gbxmodel_path.get())
        except Exception:
            pass

        if not self.mod2_tag:
            print("    Existing gbxmodel not detected. A new one will be created.")

        print("    Finished")

    def compile_gbxmodel(self):
        if not self.merged_jms:
            return

        updating = self.mod2_tag is not None
        if updating:
            print("Updating existing gbxmodel tag.")
            mod2_tag = self.mod2_tag
        else:
            print("Creating new gbxmodel tag.")
            mod2_tag = mod2_def.build()

        self.app_root.update()

        errors = compile_gbxmodel(mod2_tag, self.merged_jms)
        if errors:
            for error in errors:
                print(error)

            return

        if not updating:
            while not self.gbxmodel_path.get():
                self.gbxmodel_path_browse()
                if not self.gbxmodel_path.get():
                    if messagebox.askyesno(
                            "Unsaved gbxmodel",
                            "Are you sure you wish to cancel saving?",
                            icon='warning', parent=self):
                        print("    Gbxmodel compilation cancelled.")
                        return

            mod2_tag.filepath = self.gbxmodel_path.get()

        try:
            mod2_tag.calc_internal_data()
            mod2_tag.serialize(temp=False, backup=False, calc_pointers=False,
                               int_test=False)
            print("    Finished")
        except Exception:
            print(format_exc())
            print("    Could not save compiled gbxmodel.")


if __name__ == "__main__":
    ModelCompilerWindow(None).mainloop()
