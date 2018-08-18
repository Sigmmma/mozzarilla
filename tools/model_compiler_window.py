import os
import tkinter as tk
import time

from os.path import splitext, dirname, join, relpath, basename, isfile, exists
from tkinter import messagebox
from tkinter.filedialog import askdirectory, asksaveasfilename
from traceback import format_exc

from binilla.util import sanitize_path, is_in_dir, get_cwd, PATHDIV
from binilla.widgets import BinillaWidget, ScrollMenu
from reclaimer.hek.defs.mod2 import mod2_def
from reclaimer.model.jms import read_jms, MergedJmsModel
from reclaimer.model.model_compilation import compile_gbxmodel, generate_shader

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

    _compiling = False
    _loading = False

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


        self.superhigh_lod_cutoff = tk.StringVar(self)
        self.high_lod_cutoff = tk.StringVar(self)
        self.medium_lod_cutoff = tk.StringVar(self)
        self.low_lod_cutoff = tk.StringVar(self)
        self.superlow_lod_cutoff = tk.StringVar(self)

        tags_dir = getattr(app_root, "tags_dir", "")

        self.optimize_level = tk.IntVar(self)
        self.tags_dir = tk.StringVar(self, tags_dir if tags_dir else "")
        self.jms_dir = tk.StringVar(self)
        self.gbxmodel_path = tk.StringVar(self)


        # make the frames
        self.main_frame = tk.Frame(self)
        self.dirs_frame = tk.LabelFrame(self.main_frame, text="Directories")
        self.settings_frame = tk.LabelFrame(self.main_frame, text="Settings")
        self.lods_frame = tk.LabelFrame(self.main_frame, text="LOD Cutoffs")
        self.jms_info_frame = tk.LabelFrame(self.main_frame, text="Jms info")
        self.buttons_frame = tk.Frame(self.main_frame)

        self.jms_dir_frame = tk.LabelFrame(
            self.dirs_frame, text="Jms files folder")
        self.tags_dir_frame = tk.LabelFrame(
            self.dirs_frame, text="Tags directory root folder")
        self.gbxmodel_path_frame = tk.LabelFrame(
            self.dirs_frame, text="Gbxmodel output path")


        self.superhigh_lod_label = tk.Label(self.lods_frame, text="Superhigh")
        self.high_lod_label = tk.Label(self.lods_frame, text="High")
        self.medium_lod_label = tk.Label(self.lods_frame, text="Medium")
        self.low_lod_label = tk.Label(self.lods_frame, text="Low")
        self.superlow_lod_label = tk.Label(self.lods_frame, text="Superlow")
        self.superhigh_lod_cutoff_entry = tk.Entry(
            self.lods_frame, textvariable=self.superhigh_lod_cutoff)
        self.high_lod_cutoff_entry = tk.Entry(
            self.lods_frame, textvariable=self.high_lod_cutoff)
        self.medium_lod_cutoff_entry = tk.Entry(
            self.lods_frame, textvariable=self.medium_lod_cutoff)
        self.low_lod_cutoff_entry = tk.Entry(
            self.lods_frame, textvariable=self.low_lod_cutoff)
        self.superlow_lod_cutoff_entry = tk.Entry(
            self.lods_frame, textvariable=self.superlow_lod_cutoff)

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


        self.optimize_label = tk.Label(
            self.settings_frame, text="Vertex optimization")
        self.optimize_menu = ScrollMenu(
            self.settings_frame, menu_width=20,
            options=("None", "Exact", "Loose"))
        self.optimize_menu.sel_index = 0


        self.load_button = tk.Button(
            self.buttons_frame, text="Load JMS models",
            command=self.load_models)
        self.compile_button = tk.Button(
            self.buttons_frame, text="Compile Gbxmodel",
            command=self.compile_gbxmodel)

        # pack everything
        self.main_frame.pack(fill='both')

        self.dirs_frame.grid(sticky='news', row=0, column=0, columnspan=4)
        self.settings_frame.grid(sticky='news', row=1, column=0, columnspan=4)
        self.jms_info_frame.grid(sticky='news', row=2, column=1, columnspan=3)
        self.buttons_frame.grid(sticky='news', row=3, column=0,
                                columnspan=4, pady=3, padx=3)
        self.lods_frame.grid(sticky='news', row=0, column=5)


        self.superhigh_lod_label.grid(
            sticky='nes', row=0, column=0, pady=3, padx=3)
        self.high_lod_label.grid(
            sticky='nes', row=1, column=0, pady=3, padx=3)
        self.medium_lod_label.grid(
            sticky='nes', row=2, column=0, pady=3, padx=3)
        self.low_lod_label.grid(
            sticky='nes', row=3, column=0, pady=3, padx=3)
        self.superlow_lod_label.grid(
            sticky='nes', row=4, column=0, pady=3, padx=3)
        self.superhigh_lod_cutoff_entry.grid(
            sticky='news', row=0, column=1, pady=3, padx=3)
        self.high_lod_cutoff_entry.grid(
            sticky='news', row=1, column=1, pady=3, padx=3)
        self.medium_lod_cutoff_entry.grid(
            sticky='news', row=2, column=1, pady=3, padx=3)
        self.low_lod_cutoff_entry.grid(
            sticky='news', row=3, column=1, pady=3, padx=3)
        self.superlow_lod_cutoff_entry.grid(
            sticky='news', row=4, column=1, pady=3, padx=3)


        self.jms_dir_frame.pack(expand=True, fill='x')
        self.tags_dir_frame.pack(expand=True, fill='x')
        self.gbxmodel_path_frame.pack(expand=True, fill='x')

        self.jms_dir_entry.pack(side='left', expand=True, fill='x')
        self.jms_dir_browse_button.pack(side='left')

        self.gbxmodel_path_entry.pack(side='left', expand=True, fill='x')
        self.gbxmodel_path_browse_button.pack(side='left')

        self.tags_dir_entry.pack(side='left', expand=True, fill='x')
        self.tags_dir_browse_button.pack(side='left')

        self.optimize_label.pack(side='left', expand=True)
        self.optimize_menu.pack(side='left', expand=True)

        self.load_button.pack(side='left', expand=True, fill='both', padx=3)
        self.compile_button.pack(side='left', expand=True, fill='both', padx=3)

        self.apply_style()

    def jms_dir_browse(self):
        if self._compiling or self._loading:
            return

        tags_dir = self.tags_dir.get()
        data_dir = join(dirname(dirname(tags_dir)), "data", "")
        jms_dir = self.jms_dir.get()
        if tags_dir and not jms_dir:
            jms_dir = data_dir

        dirpath = askdirectory(
            initialdir=jms_dir, parent=self,
            title="Select the folder of jms models to compile...")

        dirpath = join(sanitize_path(dirpath), "")
        if not dirpath:
            return

        if tags_dir and data_dir and basename(dirpath).lower() == "models":
            object_dir = dirname(dirpath)

            if object_dir and is_in_dir(object_dir, data_dir):
                tag_path = join(object_dir, basename(object_dir))
                tag_path = join(tags_dir, relpath(tag_path, data_dir))
                self.gbxmodel_path.set(tag_path + ".gbxmodel")

        self.app_root.last_load_dir = dirname(dirpath)
        self.jms_dir.set(dirpath)
        if not self.tags_dir.get():
            path_pieces = self.app_root.last_load_dir.split(
                "%sdata%s" % (PATHDIV, PATHDIV))
            if len(path_pieces) > 1:
                self.tags_dir.set(join(path_pieces[0], "tags"))

    def tags_dir_browse(self):
        if self._compiling or self._loading:
            return

        tags_dir = askdirectory(
            initialdir=self.tags_dir.get(), parent=self,
            title="Select the root of the tags directory")

        tags_dir = sanitize_path(join(tags_dir, ""))
        if not tags_dir:
            return

        self.app_root.last_load_dir = dirname(tags_dir)
        self.tags_dir.set(tags_dir)

    def gbxmodel_path_browse(self, force=False):
        if not force and (self._compiling or self._loading):
            return

        mod2_dir = dirname(self.gbxmodel_path.get())
        if self.tags_dir.get() and not mod2_dir:
            mod2_dir = self.tags_dir.get()

        fp = asksaveasfilename(
            initialdir=mod2_dir,
            title="Save gbxmodel to...", parent=self,
            filetypes=(("Gearbox model", "*.gbxmodel"), ('All', '*')))

        if not fp:
            return

        fp = sanitize_path(fp)
        if not splitext(fp)[-1]:
            fp += ".gbxmodel"

        self.app_root.last_load_dir = dirname(fp)
        self.gbxmodel_path.set(fp)
        if not self.tags_dir.get():
            path_pieces = self.app_root.last_load_dir.split(
                "%stags%s" % (PATHDIV, PATHDIV))
            if len(path_pieces) > 1:
                self.tags_dir.set(join(path_pieces[0], "tags"))

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
        if not self._compiling and not self._loading:
            self._loading = True
            try:
                self._load_models()
            except Exception:
                print(format_exc())
            self._loading = False

    def compile_gbxmodel(self):
        if not self._compiling and not self._loading:
            self._compiling = True
            try:
                self._compile_gbxmodel()
            except Exception:
                print(format_exc())
            self._compiling = False

    def _load_models(self):
        models_dir = self.jms_dir.get()
        if not models_dir:
            return

        start = time.time()
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
        optimize_level = max(0, self.optimize_menu.sel_index)

        jms_datas = []
        print("Loading jms files...")
        self.app_root.update()
        for fp in fps:
            try:
                print("    %s" % fp.replace('/', '\\').split("\\")[-1])
                self.app_root.update()
                with open(fp, "r") as f:
                    jms_datas.append(read_jms(f.read(), '',
                                              basename(fp).split('.')[0]))
                jms_data = jms_datas[-1]
                if optimize_level:
                    old_vert_ct = len(jms_data.verts)
                    print("        Optimizing...", end='')
                    jms_data.optimize_geometry(optimize_level == 1)
                    print(" Removed %s verts" %
                          (old_vert_ct - len(jms_data.verts)))

                print("        Calculating normals...")
                jms_data.calculate_vertex_normals()
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


        print("Merging jms data...")
        self.app_root.update()
        self.merged_jms = merged_jms = MergedJmsModel()
        errors_occurred = False
        for jms_data in jms_datas:
            errors = merged_jms.merge_jms_model(jms_data)
            errors_occurred |= bool(errors)
            if errors:
                print("    Errors in '%s'" % jms_data.name)
                for error in errors:
                    print("        ", error, sep='')

            self.app_root.update()

        mod2_path = self.gbxmodel_path.get()
        tags_dir = self.tags_dir.get()

        shaders_dir = join(dirname(mod2_path), "shaders", '')
        tags_dir = self.tags_dir.get()
        has_local_shaders = exists(shaders_dir) and exists(tags_dir)
        if errors_occurred:
            print("    Cannot load all jms files.")
        elif isfile(mod2_path):
            try:
                self.mod2_tag = mod2_def.build(filepath=mod2_path)

                tagdata = self.mod2_tag.data.tagdata
                self.superhigh_lod_cutoff.set(str(tagdata.superhigh_lod_cutoff))
                self.high_lod_cutoff.set(str(tagdata.high_lod_cutoff))
                self.medium_lod_cutoff.set(str(tagdata.medium_lod_cutoff))
                self.low_lod_cutoff.set(str(tagdata.low_lod_cutoff))
                self.superlow_lod_cutoff.set(str(tagdata.superlow_lod_cutoff))

                # get any shaders in the gbxmodel and set the shader_path
                # and shader_type for any matching materials in the jms
                shdr_refs = {}
                for shdr_ref in tagdata.shaders.STEPTREE:
                    shdr_name = shdr_ref.shader.filepath.split("\\")[-1].lower()
                    shdr_refs.setdefault(shdr_name, []).append(shdr_ref)


                for mat in merged_jms.materials:
                    shdr_ref = shdr_refs.get(mat.name, [""]).pop(0)
                    if shdr_ref:
                        mat.shader_type = shdr_ref.shader.tag_class.enum_name
                        mat.shader_path = shdr_ref.shader.filepath

                local_shaders = {}
                if has_local_shaders and is_in_dir(shaders_dir, tags_dir):
                    # fill in any missing shader paths with ones found nearby
                    for _, __, files in os.walk(shaders_dir):
                        for filename in files:
                            name, ext = splitext(filename)
                            if ext.lower().startswith(".shader"):
                                local_shaders.setdefault(
                                    name.split("\\")[-1].lower(), []).append(
                                        join(shaders_dir, filename))
                        break

                    for mat in merged_jms.materials:
                        shdr_path = local_shaders.get(mat.name, [""]).pop(0)
                        if "shader" in mat.shader_type or not shdr_path:
                            continue

                        # shader type isnt set. Try to detect its location and
                        # type if possible, or set it to a default value if not
                        shdr_path = shdr_path.lower().replace("/", "\\")
                        name, ext = splitext(shdr_path)
                        mat.shader_path = relpath(name, tags_dir).strip("\\")
                        mat.shader_type = ext.strip(".")
            except Exception:
                pass
        else:
            for mat in merged_jms.materials:
                if mat.shader_type in ("shader", ""):
                    mat.shader_path = join(shaders_dir, mat.name)
                    mat.shader_type = "shader_model"


        if not self.mod2_tag:
            print("    Existing gbxmodel not detected or could not be loaded. "
                  "A new one will be created.")

        print("Finished loading models. Took %s seconds.\n" %
              str(time.time() - start).split('.')[0])

    def _compile_gbxmodel(self):
        if not self.merged_jms:
            return

        try:
            superhigh_lod_cutoff = self.superhigh_lod_cutoff.get().strip(" ")
            high_lod_cutoff = self.high_lod_cutoff.get().strip(" ")
            medium_lod_cutoff = self.medium_lod_cutoff.get().strip(" ")
            low_lod_cutoff = self.low_lod_cutoff.get().strip(" ")
            superlow_lod_cutoff = self.superlow_lod_cutoff.get().strip(" ")

            if not superhigh_lod_cutoff: superhigh_lod_cutoff = "0"
            if not high_lod_cutoff: high_lod_cutoff = "0"
            if not medium_lod_cutoff: medium_lod_cutoff = "0"
            if not low_lod_cutoff: low_lod_cutoff = "0"
            if not superlow_lod_cutoff: superlow_lod_cutoff = "0"

            superhigh_lod_cutoff = float(superhigh_lod_cutoff)
            high_lod_cutoff = float(high_lod_cutoff)
            medium_lod_cutoff = float(medium_lod_cutoff)
            low_lod_cutoff = float(low_lod_cutoff)
            superlow_lod_cutoff = float(superlow_lod_cutoff)
        except ValueError:
            print("LOD cutoffs are invalid.")
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
            print("Gbxmodel compilation failed.")
            return

        tags_dir = self.tags_dir.get()
        if tags_dir:
            try:
                data_dir = join(dirname(dirname(tags_dir)), "data", "")
                for mat in self.merged_jms.materials:
                    generate_shader(mat, tags_dir, data_dir)
            except Exception:
                print(format_exc())
                print("Failed to generate shader tags.")

        tagdata = mod2_tag.data.tagdata
        tagdata.superhigh_lod_cutoff = superhigh_lod_cutoff
        tagdata.high_lod_cutoff = high_lod_cutoff
        tagdata.medium_lod_cutoff = medium_lod_cutoff
        tagdata.low_lod_cutoff = low_lod_cutoff
        tagdata.superlow_lod_cutoff = superlow_lod_cutoff

        if not updating:
            while not self.gbxmodel_path.get():
                self.gbxmodel_path_browse(True)
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
