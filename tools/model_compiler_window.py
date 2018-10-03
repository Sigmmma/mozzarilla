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
from reclaimer.model.jms import read_jms, write_jms, MergedJmsModel, JmsModel
from reclaimer.model.dae import jms_model_from_dae
from reclaimer.model.obj import jms_model_from_obj
from reclaimer.model.model_compilation import compile_gbxmodel, generate_shader

if __name__ == "__main__":
    model_compiler_base_class = tk.Tk
else:
    model_compiler_base_class = tk.Toplevel

curr_dir = get_cwd(__file__)

shader_types = (
    "model",
    "environment",
    "transparent_chicago",
    "transparent_chicago_extended",
    "transparent_generic",
    "transparent_glass",
    "transparent_meter",
    "transparent_plasma",
    "transparent_water",
    )
shader_type_map = {"shader_" + shader_types[i]: i
                   for i in range(len(shader_types))}

class ModelCompilerWindow(model_compiler_base_class, BinillaWidget):
    app_root = None
    tags_dir = ''

    jms_models = ()
    merged_jms = None
    mod2_tag = None

    shader_paths = ()
    shader_types = ()

    _compiling = False
    _loading = False
    _saving = False
    _editing_shader_path = False

    _jms_tree_iids = ()

    def __init__(self, app_root, *args, **kwargs):
        if model_compiler_base_class == tk.Toplevel:
            kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
            self.app_root = app_root
        else:
            self.app_root = self

        BinillaWidget.__init__(self, *args, **kwargs)
        model_compiler_base_class.__init__(self, app_root, *args, **kwargs)

        self.title("Gbxmodel compiler")
        self.resizable(1, 0)
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
        self.shader_path_string_var = tk.StringVar(self)

        tags_dir = getattr(app_root, "tags_dir", "")

        self.optimize_level = tk.IntVar(self)
        self.tags_dir = tk.StringVar(self, tags_dir if tags_dir else "")
        self.jms_dir = tk.StringVar(self)
        self.gbxmodel_path = tk.StringVar(self)


        # make the frames
        self.main_frame = tk.Frame(self)
        self.jms_info_frame = tk.LabelFrame(
            self, text="Model info")

        self.dirs_frame = tk.LabelFrame(
            self.main_frame, text="Directories")
        self.buttons_frame = tk.Frame(self.main_frame)
        self.settings_frame = tk.LabelFrame(
            self.main_frame, text="Compilation settings")

        self.jms_dir_frame = tk.LabelFrame(
            self.dirs_frame, text="Source models folder")
        self.tags_dir_frame = tk.LabelFrame(
            self.dirs_frame, text="Tags directory root folder")
        self.gbxmodel_path_frame = tk.LabelFrame(
            self.dirs_frame, text="Gbxmodel output path")

        self.lods_frame = tk.LabelFrame(
            self.settings_frame, text="LOD cutoffs")
        self.shaders_frame = tk.LabelFrame(
            self.settings_frame, text="Shaders")


        self.optimize_label = tk.Label(
            self.settings_frame, justify="right",
            text=("Vertex optimization\n(Set before loading)"))
        self.optimize_menu = ScrollMenu(
            self.settings_frame, menu_width=5,
            options=("None", "Exact", "Loose"))
        self.optimize_menu.sel_index = 1

        self.jms_info_tree = tk.ttk.Treeview(
            self.jms_info_frame, selectmode='browse', padding=(0, 0), height=4)
        self.jms_info_vsb = tk.Scrollbar(
            self.jms_info_frame, orient='vertical',
            command=self.jms_info_tree.yview)
        self.jms_info_hsb = tk.Scrollbar(
            self.jms_info_frame, orient='horizontal',
            command=self.jms_info_tree.xview)
        self.jms_info_tree.config(yscrollcommand=self.jms_info_vsb.set,
                                  xscrollcommand=self.jms_info_hsb.set)

        self.shader_names_menu = ScrollMenu(
            self.shaders_frame, menu_width=10, callback=self.select_shader,
            option_getter=self.get_shader_names, options_volatile=True)
        self.shader_types_menu = ScrollMenu(
            self.shaders_frame, menu_width=20, options=shader_types,
            callback=self.select_shader_type)
        self.shader_path_browse_button = tk.Button(
            self.shaders_frame, text="Browse", width=6,
            command=self.browse_shader_path)
        self.shader_path_entry = tk.Entry(
            self.shaders_frame, textvariable=self.shader_path_string_var)

        self.write_trace(self.shader_path_string_var, self.shader_path_edited)


        self.superhigh_lod_label = tk.Label(self.lods_frame, text="Superhigh")
        self.high_lod_label = tk.Label(self.lods_frame, text="High")
        self.medium_lod_label = tk.Label(self.lods_frame, text="Medium")
        self.low_lod_label = tk.Label(self.lods_frame, text="Low")
        self.superlow_lod_label = tk.Label(self.lods_frame, text="Superlow")
        self.superhigh_lod_cutoff_entry = tk.Entry(
            self.lods_frame, textvariable=self.superhigh_lod_cutoff,
            width=6, justify='right')
        self.high_lod_cutoff_entry = tk.Entry(
            self.lods_frame, textvariable=self.high_lod_cutoff,
            width=6, justify='right')
        self.medium_lod_cutoff_entry = tk.Entry(
            self.lods_frame, textvariable=self.medium_lod_cutoff,
            width=6, justify='right')
        self.low_lod_cutoff_entry = tk.Entry(
            self.lods_frame, textvariable=self.low_lod_cutoff,
            width=6, justify='right')
        self.superlow_lod_cutoff_entry = tk.Entry(
            self.lods_frame, textvariable=self.superlow_lod_cutoff,
            width=6, justify='right')


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
            self.buttons_frame, text="Load models",
            command=self.load_models)
        self.save_button = tk.Button(
            self.buttons_frame, text="Save models as JMS",
            command=self.save_models)
        self.compile_button = tk.Button(
            self.buttons_frame, text="Compile Gbxmodel",
            command=self.compile_gbxmodel)

        self.populate_model_info_tree()

        # pack everything
        self.main_frame.pack(fill="both", side='left', pady=3, padx=3)
        self.jms_info_frame.pack(fill="both", side='left', pady=3, padx=3,
                                 expand=True)

        self.dirs_frame.pack(fill="x")
        self.buttons_frame.pack(fill="x", pady=3, padx=3)
        self.settings_frame.pack(fill="both", expand=True)


        self.superhigh_lod_label.grid(sticky='e', row=0, column=0, padx=3, pady=1)
        self.high_lod_label.grid(sticky='e', row=1, column=0, padx=3, pady=1)
        self.medium_lod_label.grid(sticky='e', row=2, column=0, padx=3, pady=1)
        self.low_lod_label.grid(sticky='e', row=3, column=0, padx=3, pady=1)
        self.superlow_lod_label.grid(sticky='e', row=4, column=0, padx=3, pady=1)
        self.superhigh_lod_cutoff_entry.grid(sticky='ew', row=0, column=1, padx=3, pady=1)
        self.high_lod_cutoff_entry.grid(sticky='ew', row=1, column=1, padx=3, pady=1)
        self.medium_lod_cutoff_entry.grid(sticky='ew', row=2, column=1, padx=3, pady=1)
        self.low_lod_cutoff_entry.grid(sticky='ew', row=3, column=1, padx=3, pady=1)
        self.superlow_lod_cutoff_entry.grid(sticky='ew', row=4, column=1, padx=3, pady=1)


        self.jms_dir_frame.pack(expand=True, fill='x')
        self.tags_dir_frame.pack(expand=True, fill='x')
        self.gbxmodel_path_frame.pack(expand=True, fill='x')

        self.jms_dir_entry.pack(side='left', expand=True, fill='x')
        self.jms_dir_browse_button.pack(side='left')

        self.gbxmodel_path_entry.pack(side='left', expand=True, fill='x')
        self.gbxmodel_path_browse_button.pack(side='left')

        self.tags_dir_entry.pack(side='left', expand=True, fill='x')
        self.tags_dir_browse_button.pack(side='left')

        self.optimize_label.grid(
            sticky='ne', row=3, column=1, padx=3)
        self.optimize_menu.grid(
            sticky='new', row=3, column=2, padx=3, pady=(3, 0))
        self.lods_frame.grid(sticky='ne', row=0, column=3, rowspan=4)
        self.shaders_frame.grid(sticky='nsew', row=0, column=0,
                                columnspan=3, rowspan=3, pady=(0, 3))


        self.shader_names_menu.grid(sticky='new', row=0, column=0,
                                    padx=3, columnspan=5, pady=2)
        self.shader_path_browse_button.grid(sticky='ne', row=1, column=4,
                                            padx=3, pady=2)
        self.shader_types_menu.grid(sticky='new', row=1, column=1,
                                    padx=3, columnspan=3, pady=2)
        self.shader_path_entry.grid(sticky='new', row=2, column=0,
                                    padx=3, columnspan=5, pady=2)

        self.jms_info_hsb.pack(side="bottom", fill='x')
        self.jms_info_vsb.pack(side="right",  fill='y')
        self.jms_info_tree.pack(side='left', fill='both', expand=True)

        self.load_button.pack(side='left', expand=True, fill='both', padx=3)
        self.save_button.pack(side='left', expand=True, fill='both', padx=3)
        self.compile_button.pack(side='right', expand=True, fill='both', padx=3)

        self.apply_style()
        if self.app_root is not self:
            self.transient(self.app_root)

    def populate_model_info_tree(self):
        jms_tree = self.jms_info_tree
        if not jms_tree['columns']:
            jms_tree['columns'] = ('data', )
            jms_tree.heading("#0")
            jms_tree.heading("data")
            jms_tree.column("#0", minwidth=100, width=100)
            jms_tree.column("data", minwidth=50, width=50, stretch=False)

        for iid in self._jms_tree_iids:
            jms_tree.delete(iid)

        self._jms_tree_iids = []

        if not self.jms_models or not self.merged_jms:
            return

        nodes_iid = jms_tree.insert('', 'end', text="Nodes", tags=('item',),
                                    values=(len(self.merged_jms.nodes),))
        self._jms_tree_iids.append(nodes_iid)
        nodes = self.merged_jms.nodes
        for node in nodes:
            iid = jms_tree.insert(nodes_iid, 'end', text=node.name, tags=('item',))
            parent_name = child_name = sibling_name = "NONE"
            if node.parent_index >= 0:
                parent_name = nodes[node.parent_index].name
            if node.sibling_index >= 0:
                child_name = nodes[node.sibling_index].name
            if node.first_child >= 0:
                sibling_name = nodes[node.first_child].name

            jms_tree.insert(iid, 'end', text="Parent",
                            values=(parent_name, ), tags=('item',),)
            jms_tree.insert(iid, 'end', text="First child",
                            values=(child_name, ), tags=('item',),)
            jms_tree.insert(iid, 'end', text="Next sibling",
                            values=(sibling_name, ), tags=('item',),)

            jms_tree.insert(iid, 'end', text="i",
                            values=(node.rot_i, ), tags=('item',),)
            jms_tree.insert(iid, 'end', text="j",
                            values=(node.rot_j, ), tags=('item',),)
            jms_tree.insert(iid, 'end', text="k",
                            values=(node.rot_k, ), tags=('item',),)
            jms_tree.insert(iid, 'end', text="w",
                            values=(node.rot_w, ), tags=('item',),)

            jms_tree.insert(iid, 'end', text="x",
                            values=(node.pos_x, ), tags=('item',),)
            jms_tree.insert(iid, 'end', text="y",
                            values=(node.pos_y, ), tags=('item',),)
            jms_tree.insert(iid, 'end', text="z",
                            values=(node.pos_z, ), tags=('item',),)


        mats_iid = jms_tree.insert('', 'end', text="Materials", tags=('item',),
                                   values=(len(self.merged_jms.materials),))
        self._jms_tree_iids.append(mats_iid)
        for mat in self.merged_jms.materials:
            jms_tree.insert(mats_iid, 'end', text=mat.name, tags=('item',),
                            values=(mat.tiff_path, ))


        regions_iid = jms_tree.insert('', 'end', text="Regions", tags=('item',),
                                      values=(len(self.merged_jms.regions),))
        self._jms_tree_iids.append(regions_iid)
        for region in sorted(self.merged_jms.regions):
            jms_tree.insert(regions_iid, 'end', text=region, tags=('item',),)


        geoms_iid = jms_tree.insert('', 'end', text="Geometries", tags=('item',),
                                    values=(len(self.jms_models),))
        self._jms_tree_iids.append(geoms_iid)
        for jms_model in self.jms_models:
            iid = jms_tree.insert(geoms_iid, 'end', tags=('item',),
                                  text=jms_model.name)
            jms_tree.insert(iid, 'end', text="Vertex count", tags=('item',),
                            values=(len(jms_model.verts), ))
            jms_tree.insert(iid, 'end', text="Triangle count", tags=('item',),
                            values=(len(jms_model.tris), ))

            markers_iid = jms_tree.insert(
                iid, 'end', text="Markers", tags=('item',),
                values=(len(jms_model.markers),))
            for marker in jms_model.markers:
                iid = jms_tree.insert(
                    markers_iid, 'end', tags=('item',), text=marker.name)
                perm_name = marker.permutation
                region_name = jms_model.regions[marker.region]
                parent_name = ""
                if marker.parent >= 0:
                    parent_name = nodes[marker.parent].name

                jms_tree.insert(iid, 'end', text="Permutation",
                                values=(perm_name, ), tags=('item',))
                jms_tree.insert(iid, 'end', text="Region",
                                values=(region_name, ), tags=('item',))
                jms_tree.insert(iid, 'end', text="Parent",
                                values=(parent_name, ), tags=('item',))
                jms_tree.insert(iid, 'end', text="Radius",
                                values=(marker.radius, ), tags=('item',))

                jms_tree.insert(iid, 'end', text="i",
                                values=(marker.rot_i, ), tags=('item',))
                jms_tree.insert(iid, 'end', text="j",
                                values=(marker.rot_j, ), tags=('item',))
                jms_tree.insert(iid, 'end', text="k",
                                values=(marker.rot_k, ), tags=('item',))
                jms_tree.insert(iid, 'end', text="w",
                                values=(marker.rot_w, ), tags=('item',))

                jms_tree.insert(iid, 'end', text="x",
                                values=(marker.pos_x, ), tags=('item',))
                jms_tree.insert(iid, 'end', text="y",
                                values=(marker.pos_y, ), tags=('item',))
                jms_tree.insert(iid, 'end', text="z",
                                values=(marker.pos_z, ), tags=('item',))


    def jms_dir_browse(self):
        if self._compiling or self._loading or self._saving:
            return

        tags_dir = self.tags_dir.get()
        data_dir = join(dirname(dirname(tags_dir)), "data", "")
        jms_dir = self.jms_dir.get()
        if tags_dir and not jms_dir:
            jms_dir = data_dir

        dirpath = askdirectory(
            initialdir=jms_dir, parent=self,
            title="Select the folder of jms/obj models to compile...")

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
        if self._compiling or self._loading or self._saving:
            return

        old_tags_dir = self.tags_dir.get()
        tags_dir = askdirectory(
            initialdir=old_tags_dir, parent=self,
            title="Select the root of the tags directory")

        tags_dir = sanitize_path(join(tags_dir, ""))
        if not tags_dir:
            return

        mod2_path = self.gbxmodel_path.get()
        if old_tags_dir and mod2_path and not is_in_dir(mod2_path, tags_dir):
            # adjust mod2 filepath to be relative to the new tags directory
            mod2_path = join(tags_dir, relpath(mod2_path, old_tags_dir))
            self.gbxmodel_path.set(mod2_path)

        self.app_root.last_load_dir = dirname(tags_dir)
        self.tags_dir.set(tags_dir)

    def gbxmodel_path_browse(self, force=False):
        if not force and (self._compiling or self._loading or self._saving):
            return

        mod2_dir = dirname(self.gbxmodel_path.get())
        if self.tags_dir.get() and not mod2_dir:
            mod2_dir = self.tags_dir.get()

        fp = asksaveasfilename(
            initialdir=mod2_dir, title="Save gbxmodel to...", parent=self,
            filetypes=(("Gearbox model", "*.gbxmodel"), ('All', '*')))

        if not fp:
            return

        fp = sanitize_path(fp)
        if not splitext(fp)[-1]:
            fp += ".gbxmodel"

        self.app_root.last_load_dir = dirname(fp)
        self.gbxmodel_path.set(fp)

        path_pieces = join(self.app_root.last_load_dir, '').split(
            "%stags%s" % (PATHDIV, PATHDIV))
        if len(path_pieces) > 1:
            self.tags_dir.set(join(path_pieces[0], "tags"))

    def apply_style(self, seen=None):
        BinillaWidget.apply_style(self, seen)
        self.update()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry("%sx%s" % (w, h))
        self.minsize(width=w, height=h)

    def get_material(self, index):
        if not isinstance(self.merged_jms, MergedJmsModel):
            return None
        mats = self.merged_jms.materials
        if index >= len(mats) or index < 0:
            return None

        return mats[index]

    def select_shader(self, shader_index):
        self._editing_shader_path = True
        try:
            self._editing_shader_path = False
            mat = self.get_material(shader_index)
            if mat:
                self.shader_names_menu.sel_index = shader_index
                self.shader_path_string_var.set(mat.shader_path)
                self.shader_types_menu.sel_index = shader_type_map.get(
                    mat.shader_type, -1)
            elif shader_index < 0:
                self.shader_types_menu.sel_index = -1
                self.shader_names_menu.sel_index = -1
                self.shader_path_string_var.set("")
        except Exception:
            self._editing_shader_path = False
            raise

    def select_shader_type(self, shader_type):
        mat = self.get_material(self.shader_names_menu.sel_index)
        if mat and shader_type in range(len(shader_types)):
            mat.shader_type = "shader_" + shader_types[shader_type]

    def shader_path_edited(self, *a, **kw):
        if self._editing_shader_path:
            return

        self._editing_shader_path = True
        try:
            shader_path = self.shader_path_string_var.get().replace('/', '\\')
            mat = self.get_material(self.shader_names_menu.sel_index)
            if mat:
                mat.shader_path = shader_path

            self._editing_shader_path = False
        except Exception:
            self._editing_shader_path = False
            raise

    def browse_shader_path(self):
        if self._compiling or self._loading or self._saving:
            return

        tags_dir = sanitize_path(join(self.tags_dir.get(), ""))
        if not tags_dir or not exists(tags_dir):
            return

        shader_dir = dirname(join(tags_dir, self.shader_path_string_var.get()))

        shader_exts = tuple((typ, "*.shader_%s" % typ)
                            for typ in shader_types)
        fp = asksaveasfilename(
            initialdir=shader_dir, parent=self,
            title="Select the shader to use(or where to make one)",
            filetypes=shader_exts + (('All', '*'), )
            )

        fp, ext = splitext(sanitize_path(fp))
        if fp:
            if not is_in_dir(fp, tags_dir):
                print("Specified shader is not located in the tags directory.")
                return

            ext = ext.strip(".").lower()
            self.shader_path_string_var.set(relpath(fp, tags_dir))
            mat = self.get_material(self.shader_names_menu.sel_index)
            if mat and ext in shader_type_map:
                self.shader_types_menu.sel_index = shader_type_map[ext]
                mat.shader_type = ext


    def get_shader_names(self, opt_index=None):
        if opt_index == "active":
            opt_index = self.shader_names_menu.sel_index

        if opt_index is not None:
            return self.merged_jms.materials[opt_index].\
                   shader_path.split("\\")[-1]

        shader_names = {}
        if isinstance(self.merged_jms, MergedJmsModel):
            i = 0
            for mat in self.merged_jms.materials:
                shader_names[i] = mat.shader_path.split("\\")[-1]
                i += 1

        return shader_names

    def destroy(self):
        try:
            self.app_root.tool_windows.pop(self.window_name, None)
        except AttributeError:
            pass
        model_compiler_base_class.destroy(self)

    def load_models(self):
        if not self._compiling and not self._loading and not self._saving:
            self._loading = True
            try:
                self._load_models()
            except Exception:
                print(format_exc())
            try:
                self.populate_model_info_tree()
            except Exception:
                print(format_exc())
            self._loading = False

    def save_models(self):
        if not self._compiling and not self._loading and not self._saving:
            self._saving = True
            try:
                self._save_models()
            except Exception:
                print(format_exc())
            self._saving = False

    def compile_gbxmodel(self):
        if not self._compiling and not self._loading and not self._saving:
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
                ext = splitext(fname)[-1].lower()
                #if ext in ".jms.obj.dae":
                if ext in ".jms.obj":
                    fps.append(join(models_dir, fname))

            break

        if not fps:
            print("    No valid jms files found in the folder.")
            return

        self.mod2_tag = self.merged_jms = None
        optimize_level = max(0, self.optimize_menu.sel_index)

        jms_models = self.jms_models = []
        print("Loading jms files...")
        self.app_root.update()
        for fp in fps:
            try:
                print("    %s" % fp.replace('/', '\\').split("\\")[-1])
                self.app_root.update()

                model_name = basename(fp).split('.')[0]
                ext = splitext(fp)[-1].lower()

                jms_model = None
                if ext == ".jms":
                    with open(fp, "r") as f:
                        jms_model = read_jms(f.read(), '', model_name)
                elif ext == ".obj":
                    with open(fp, "r") as f:
                        jms_model = jms_model_from_obj(f.read(), model_name)
                elif ext == ".dae":
                    jms_model = jms_model_from_dae(fp, model_name)

                if not jms_model:
                    continue

                jms_models.append(jms_model)

                if optimize_level:
                    old_vert_ct = len(jms_model.verts)
                    print("        Optimizing...", end='')
                    jms_model.optimize_geometry(optimize_level == 1)
                    print(" Removed %s verts" %
                          (old_vert_ct - len(jms_model.verts)))

                print("        Calculating normals...")
                jms_model.calculate_vertex_normals()
            except Exception:
                print(format_exc())
                print("    Could not parse jms file.")
                self.app_root.update()

        if not jms_models:
            print("    No valid jms files found.")
            return

        first_crc = None
        for jms_model in jms_models:
            if first_crc is None:
                first_crc = jms_model.node_list_checksum
            elif first_crc != jms_model.node_list_checksum:
                print("    Warning, not all node list checksums match.")
                break


        print("Merging jms data...")
        self.app_root.update()
        self.merged_jms = merged_jms = MergedJmsModel()
        errors_occurred = False
        for jms_model in jms_models:
            errors = merged_jms.merge_jms_model(jms_model)
            errors_occurred |= bool(errors)
            if errors:
                print("    Errors in '%s'" % jms_model.name)
                for error in errors:
                    print("        ", error, sep='')

            self.app_root.update()

        mod2_path = self.gbxmodel_path.get()
        tags_dir = self.tags_dir.get().replace('/', '\\')
        self.shader_names_menu.max_index = len(merged_jms.materials) - 1


        shaders_dir = ""
        if mod2_path:
            shaders_dir = join(dirname(mod2_path), "shaders", '')
        tags_dir = self.tags_dir.get()
        has_local_shaders = exists(shaders_dir) and exists(tags_dir)
        if errors_occurred:
            print("    Errors occurred while loading jms files.")
        elif isfile(mod2_path):
            try:
                self.mod2_tag = mod2_def.build(filepath=mod2_path)

                tagdata = self.mod2_tag.data.tagdata
                self.merged_jms.node_list_checksum = tagdata.node_list_checksum
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
                            ext = ext.lower()
                            if ext.startswith(".shader"):
                                local_shaders.setdefault(
                                    name.split("\\")[-1].lower(), []).append(
                                        join(shaders_dir, filename))
                        break

                    for mat in merged_jms.materials:
                        shader_path = local_shaders.get(mat.name, [""]).pop(0)
                        if "shader_" in mat.shader_type or not shader_path:
                            continue

                        # shader type isnt set. Try to detect its location and
                        # type if possible, or set it to a default value if not
                        shader_path = shader_path.lower().replace("/", "\\")
                        name, ext = splitext(shader_path)
                        mat.shader_path = relpath(name, tags_dir).strip("\\")
                        mat.shader_type = ext.strip(".")

            except Exception:
                print(format_exc())
        else:
            self.superhigh_lod_cutoff.set("0.0")
            self.high_lod_cutoff.set("0.0")
            self.medium_lod_cutoff.set("0.0")
            self.low_lod_cutoff.set("0.0")
            self.superlow_lod_cutoff.set("0.0")


        for mat in merged_jms.materials:
            shader_path = mat.shader_path
            if mat.shader_type in ("shader", ""):
                assume_shaders_dir = not shaders_dir

                if not assume_shaders_dir:
                    try:
                        shader_path = relpath(
                            join(shaders_dir, shader_path), tags_dir)
                        shader_path = shader_path.strip("\\")
                    except ValueError:
                        assume_shaders_dir = True

                mat.shader_type = "shader_model"
            else:
                assume_shaders_dir = False

            if assume_shaders_dir or shader_path.startswith("..\\"):
                shader_path = "shaders\\" + basename(shader_path)

            mat.shader_path = shader_path.lstrip("..\\")


        if not self.mod2_tag:
            print("    Existing gbxmodel not detected or could not be loaded.\n"
                  "        A new gbxmodel will be created.")

        print("Finished loading models. Took %s seconds.\n" %
              str(time.time() - start).split('.')[0])
        self.select_shader(0)

    def _save_models(self):
        models_dir = self.jms_dir.get()
        if not models_dir:
            return

        start = time.time()
        print("Saving jms models...")
        for jms_model in self.jms_models:
            if isinstance(jms_model, JmsModel):
                fname = "%s %s.jms" % (jms_model.perm_name, jms_model.lod_level)
                if not jms_model.is_random_perm:
                    fname = "~" + fname

                write_jms(join(models_dir, fname), jms_model)

        print("Finished saving models. Took %s seconds.\n" %
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

        self.app_root.update()

        errors = compile_gbxmodel(mod2_tag, self.merged_jms)
        if errors:
            for error in errors:
                print(error)
            print("Gbxmodel compilation failed.")
            return

        tags_dir = self.tags_dir.get()
        if tags_dir:
            data_dir = join(dirname(dirname(tags_dir)), "data", "")
            for mat in self.merged_jms.materials:
                try:
                    generate_shader(mat, tags_dir, data_dir)
                except Exception:
                    print(format_exc())
                    print("Failed to generate shader tag.")

        tagdata = mod2_tag.data.tagdata
        tagdata.superhigh_lod_cutoff = superhigh_lod_cutoff
        tagdata.high_lod_cutoff = high_lod_cutoff
        tagdata.medium_lod_cutoff = medium_lod_cutoff
        tagdata.low_lod_cutoff = low_lod_cutoff
        tagdata.superlow_lod_cutoff = superlow_lod_cutoff

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
