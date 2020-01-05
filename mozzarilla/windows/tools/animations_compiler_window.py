#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

import os
import time
import tkinter as tk

from pathlib import Path
from tkinter import messagebox
from traceback import format_exc

from binilla.widgets.binilla_widget import BinillaWidget
from binilla.windows.filedialog import askdirectory, asksaveasfilename

from reclaimer.hek.defs.antr import antr_def
from reclaimer.animation.jma import read_jma, write_jma,\
     JmaAnimation, JmaAnimationSet, JMA_ANIMATION_EXTENSIONS
from reclaimer.animation.animation_compilation import \
     compile_model_animations, ANIMATION_COMPILE_MODE_NEW,\
     ANIMATION_COMPILE_MODE_PRESERVE, ANIMATION_COMPILE_MODE_ADDITIVE
from reclaimer.animation.util import partial_mod2_def

from supyr_struct.util import is_in_dir, path_normalize,\
     path_split, path_replace

from mozzarilla import editor_constants as e_c

if __name__ == "__main__":
    window_base_class = tk.Tk
else:
    window_base_class = tk.Toplevel


class AnimationsCompilerWindow(window_base_class, BinillaWidget):
    app_root = None
    tags_dir = ''

    jma_anims = ()
    jma_anim_set = None

    _compiling = False
    _loading = False
    _saving = False

    _jma_tree_iids = ()

    animation_delta_tolerance = 0.00001

    def __init__(self, app_root, *args, **kwargs):
        if window_base_class == tk.Toplevel:
            kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
            self.app_root = app_root
        else:
            self.app_root = self

        window_base_class.__init__(self, app_root, *args, **kwargs)
        BinillaWidget.__init__(self, *args, **kwargs)

        self.title("Model_animations compiler")
        self.resizable(1, 1)
        self.update()
        try:
            self.iconbitmap(e_c.MOZZ_ICON_PATH)
        except Exception:
            print("Could not load window icon.")

        tags_dir = getattr(app_root, "tags_dir", "")

        self.tags_dir = tk.StringVar(self, tags_dir if tags_dir else "")
        self.jma_dir = tk.StringVar(self)
        self.model_animations_path = tk.StringVar(self)

        self.animation_count_limit = tk.IntVar(self, 256)
        self.calculate_limp_limb_vectors = tk.IntVar(self, 0)
        self.update_mode = tk.IntVar(self, ANIMATION_COMPILE_MODE_PRESERVE)
        self.animation_delta_tolerance_string = tk.StringVar(
            self, str(self.animation_delta_tolerance))
        self.animation_delta_tolerance_string.trace(
            "w", lambda *a, s=self: s.set_animation_delta_tolerance())


        # make the frames
        self.main_frame = tk.Frame(self)
        self.jma_info_frame = tk.LabelFrame(
            self, text="Animations info")

        self.dirs_frame = tk.LabelFrame(
            self.main_frame, text="Directories")
        self.buttons_frame = tk.Frame(self.main_frame)
        self.settings_frame = tk.Frame(self.main_frame)

        self.jma_dir_frame = tk.LabelFrame(
            self.dirs_frame, text="Source animations folder")
        self.tags_dir_frame = tk.LabelFrame(
            self.dirs_frame, text="Tags directory root folder")
        self.model_animations_path_frame = tk.LabelFrame(
            self.dirs_frame, text="Model_animations output path")

        self.animation_delta_tolerance_frame = tk.LabelFrame(
            self.settings_frame, text="Animation delta tolerance")
        self.update_mode_frame = tk.LabelFrame(
            self.settings_frame, text="What to do with existing model_animations tag")

        self.compile_mode_replace_rbtn = tk.Radiobutton(
            self.update_mode_frame, anchor="w",
            variable=self.update_mode, value=ANIMATION_COMPILE_MODE_NEW,
            text="Erase all animations/tag values")
        self.compile_mode_preserve_rbtn = tk.Radiobutton(
            self.update_mode_frame, anchor="w",
            variable=self.update_mode, value=ANIMATION_COMPILE_MODE_PRESERVE,
            text="Preserve any used animations/tag values")
        self.compile_mode_additive_rbtn = tk.Radiobutton(
            self.update_mode_frame, anchor="w",
            variable=self.update_mode, value=ANIMATION_COMPILE_MODE_ADDITIVE,
            text="Erase nothing(only add/update animations and values)")

        self.animation_delta_tolerance_info = tk.Label(
            self.animation_delta_tolerance_frame, justify='left', anchor="w",
            text=("How much a nodes position, rotation, or scale\n"
                  "must change from the starting frame for that\n"
                  "type of transform to be considered animated."))
        self.animation_delta_tolerance_spinbox = tk.Spinbox(
            self.animation_delta_tolerance_frame, from_=0,
            to=100, width=25, increment=self.animation_delta_tolerance,
            textvariable=self.animation_delta_tolerance_string, justify="right")

        self.use_os_animation_count_limit_cbtn = tk.Checkbutton(
            self.settings_frame, onvalue=2048, offvalue=256,
            variable=self.animation_count_limit, anchor="w",
            text="Use Open Sauce animation count limit")
        self.calculate_limp_limb_vectors_cbtn = tk.Checkbutton(
            self.settings_frame, variable=self.calculate_limp_limb_vectors,
            text=("Calculate biped limp body node vectors\n"
                  "(requires matching gbxmodel)"), anchor="w")


        self.jma_info_tree = tk.ttk.Treeview(
            self.jma_info_frame, selectmode='browse', padding=(0, 0), height=4)
        self.jma_info_vsb = tk.Scrollbar(
            self.jma_info_frame, orient='vertical',
            command=self.jma_info_tree.yview)
        self.jma_info_hsb = tk.Scrollbar(
            self.jma_info_frame, orient='horizontal',
            command=self.jma_info_tree.xview)
        self.jma_info_tree.config(yscrollcommand=self.jma_info_vsb.set,
                                  xscrollcommand=self.jma_info_hsb.set)

        self.jma_dir_entry = tk.Entry(
            self.jma_dir_frame, textvariable=self.jma_dir, state=tk.DISABLED)
        self.jma_dir_browse_button = tk.Button(
            self.jma_dir_frame, text="Browse", command=self.jma_dir_browse)


        self.tags_dir_entry = tk.Entry(
            self.tags_dir_frame, textvariable=self.tags_dir, state=tk.DISABLED)
        self.tags_dir_browse_button = tk.Button(
            self.tags_dir_frame, text="Browse", command=self.tags_dir_browse)


        self.model_animations_path_entry = tk.Entry(
            self.model_animations_path_frame,
            textvariable=self.model_animations_path,
            state=tk.DISABLED)
        self.model_animations_path_browse_button = tk.Button(
            self.model_animations_path_frame, text="Browse",
            command=self.model_animations_path_browse)


        self.load_button = tk.Button(
            self.buttons_frame, text="Load\nanimations",
            command=self.load_animations)
        self.save_button = tk.Button(
            self.buttons_frame, text="Save as JMA",
            command=self.save_animations)
        self.compile_button = tk.Button(
            self.buttons_frame, text="Compile\nmodel_animations",
            command=self.compile_model_animations)

        self.populate_animations_info_tree()

        # pack everything
        self.main_frame.pack(fill="both", side='left', pady=3, padx=3)
        self.jma_info_frame.pack(fill="both", side='left', pady=3, padx=3,
                                 expand=True)

        self.dirs_frame.pack(fill="x")
        self.buttons_frame.pack(fill="x", pady=3, padx=3)
        self.settings_frame.pack(fill="both")

        self.jma_dir_frame.pack(fill='x')
        self.tags_dir_frame.pack(fill='x')
        self.model_animations_path_frame.pack(fill='x')

        self.jma_dir_entry.pack(side='left', fill='x', expand=True)
        self.jma_dir_browse_button.pack(side='left')

        self.model_animations_path_entry.pack(side='left', fill='x', expand=True)
        self.model_animations_path_browse_button.pack(side='left')

        self.tags_dir_entry.pack(side='left', fill='x', expand=True)
        self.tags_dir_browse_button.pack(side='left')

        self.jma_info_hsb.pack(side="bottom", fill='x')
        self.jma_info_vsb.pack(side="right",  fill='y')
        self.jma_info_tree.pack(side='left', fill='both', expand=True)

        self.load_button.pack(side='left', fill='both', padx=3, expand=True)
        self.save_button.pack(side='left', fill='both', padx=3, expand=True)
        self.compile_button.pack(side='right', fill='both', padx=3, expand=True)

        for w in (self.update_mode_frame,
                  self.animation_delta_tolerance_frame):
            w.pack(expand=True, fill='both')

        for w in (self.compile_mode_replace_rbtn,
                  self.compile_mode_preserve_rbtn,
                  self.compile_mode_additive_rbtn,):
            w.pack(expand=True, fill='both')

        self.animation_delta_tolerance_info.pack(fill='both', expand=True,
                                                 padx=5, pady=5)
        self.animation_delta_tolerance_spinbox.pack(padx=5, pady=5, anchor="w")

        self.use_os_animation_count_limit_cbtn.pack(expand=True, fill='both')
	# TODO: Uncomment this once this works
        #self.calculate_limp_limb_vectors_cbtn.pack(expand=True, fill='both')


        self.apply_style()
        if self.app_root is not self:
            self.transient(self.app_root)

    def populate_animations_info_tree(self):
        jma_tree = self.jma_info_tree
        if not jma_tree['columns']:
            jma_tree['columns'] = ('data', )
            jma_tree.heading("#0")
            jma_tree.heading("data")
            jma_tree.column("#0", minwidth=100, width=100)
            jma_tree.column("data", minwidth=80, width=80, stretch=False)

        for iid in self._jma_tree_iids:
            jma_tree.delete(iid)

        self._jma_tree_iids = []

        if not self.jma_anims or not self.jma_anim_set:
            return

        nodes_iid = jma_tree.insert('', 'end', text="Nodes", tags=('item',),
                                    values=(len(self.jma_anim_set.nodes),))
        self._jma_tree_iids.append(nodes_iid)
        nodes = self.jma_anim_set.nodes
        for node in nodes:
            iid = jma_tree.insert(nodes_iid, 'end', text=node.name, tags=('item',))
            parent_name = child_name = sibling_name = "NONE"
            if node.sibling_index >= 0:
                sibling_name = nodes[node.sibling_index].name
            if node.first_child >= 0:
                child_name = nodes[node.first_child].name
            if node.parent_index >= 0:
                parent_name = nodes[node.parent_index].name

            jma_tree.insert(iid, 'end', text="Next sibling",
                            values=(sibling_name, ), tags=('item',),)
            jma_tree.insert(iid, 'end', text="First child",
                            values=(child_name, ), tags=('item',),)
            jma_tree.insert(iid, 'end', text="Parent",
                            values=(parent_name, ), tags=('item',),)


        anims_iid = jma_tree.insert('', 'end', text="Animations", tags=('item',),
                                    values=(len(self.jma_anims),))
        self._jma_tree_iids.append(anims_iid)
        for jma_anim in self.jma_anims:
            iid = jma_tree.insert(anims_iid, 'end', tags=('item',),
                                  text=jma_anim.name + jma_anim.ext)
            jma_tree.insert(iid, 'end', text="Node list checksum", tags=('item',),
                            values=(jma_anim.node_list_checksum, ))
            jma_tree.insert(iid, 'end', text="World relative", tags=('item',),
                            values=(jma_anim.world_relative, ))
            jma_tree.insert(iid, 'end', text="Type", tags=('item',),
                            values=(jma_anim.anim_type, ))
            jma_tree.insert(iid, 'end', text="Frame info", tags=('item',),
                            values=(jma_anim.frame_info_type, ))

            rot_flags   = jma_anim.rot_flags
            trans_flags = jma_anim.trans_flags
            scale_flags = jma_anim.scale_flags

            node_flags_iid = jma_tree.insert(
                iid, 'end', text="Transform flags", tags=('item',),
                values=(len(jma_anim.nodes),))
            for n in range(len(jma_anim.nodes)):
                node_iid = jma_tree.insert(
                    node_flags_iid, 'end', text=jma_anim.nodes[n].name,
                    tags=('item',), values=(
                        "*" if (rot_flags[n] or
                                trans_flags[n] or
                                scale_flags[n])
                        else "",))

                jma_tree.insert(node_iid, 'end', text="Rotation",
                                values=(rot_flags[n], ), tags=('item',))
                jma_tree.insert(node_iid, 'end', text="Position",
                                values=(trans_flags[n], ), tags=('item',))
                jma_tree.insert(node_iid, 'end', text="Scale",
                                values=(scale_flags[n], ), tags=('item',))

            # code below is very CPU and RAM intensive.
            # don't remove this continue unless debugging
            continue
            print("REMINDER TO REMOVE THIS DEBUG IN COMPILER WINDOW")

            has_dxdy = "dx" in jma_anim.frame_info_type
            has_dz   = "dz" in jma_anim.frame_info_type
            has_dyaw = "dyaw" in jma_anim.frame_info_type

            root_data_iid = jma_tree.insert(
                iid, 'end', text="Root node data", tags=('item',),
                values=(len(jma_anim.root_node_info),))
            for f in range(len(jma_anim.root_node_info)):
                if not has_dxdy and not has_dz and not has_dyaw:
                    break

                state = jma_anim.root_node_info[f]
                frame_iid = jma_tree.insert(
                    root_data_iid, 'end', tags=('item',),
                    text="frame%s" % f
                    )
                if has_dxdy:
                    jma_tree.insert(frame_iid, 'end', text="dx",
                                    values=(state.dx, ), tags=('item',),)
                    jma_tree.insert(frame_iid, 'end', text="dy",
                                    values=(state.dy, ), tags=('item',),)

                if has_dz:
                    jma_tree.insert(frame_iid, 'end', text="dz",
                                    values=(state.dz, ), tags=('item',),)

                if has_dyaw:
                    jma_tree.insert(frame_iid, 'end', text="dyaw",
                                    values=(state.dyaw, ), tags=('item',),)

                if has_dxdy:
                    jma_tree.insert(frame_iid, 'end', text="x",
                                    values=(state.x, ), tags=('item',),)
                    jma_tree.insert(frame_iid, 'end', text="y",
                                    values=(state.y, ), tags=('item',),)

                if has_dz:
                    jma_tree.insert(frame_iid, 'end', text="z",
                                    values=(state.z, ), tags=('item',),)

                if has_dyaw:
                    jma_tree.insert(frame_iid, 'end', text="yaw",
                                    values=(state.yaw, ), tags=('item',),)

            # even more CPU / RAM intensive code past here
            continue
            nodes_iid = jma_tree.insert(
                iid, 'end', text="Frame data", tags=('item',),
                values=(len(jma_anim.nodes),))
            for n in range(len(jma_anim.nodes)):
                states_iid = jma_tree.insert(
                    nodes_iid, 'end', text=jma_anim.nodes[n].name,
                    tags=('item',))

                for f in range(len(jma_anim.frames)):
                    state = jma_anim.frames[f][n]
                    node_iid = jma_tree.insert(
                        states_iid, 'end', tags=('item',),
                        text="frame%s" % f
                        )
                    jma_tree.insert(node_iid, 'end', text="i",
                                    values=(state.rot_i, ), tags=('item',),)
                    jma_tree.insert(node_iid, 'end', text="j",
                                    values=(state.rot_j, ), tags=('item',),)
                    jma_tree.insert(node_iid, 'end', text="k",
                                    values=(state.rot_k, ), tags=('item',),)
                    jma_tree.insert(node_iid, 'end', text="w",
                                    values=(state.rot_w, ), tags=('item',),)

                    jma_tree.insert(node_iid, 'end', text="x",
                                    values=(state.pos_x, ), tags=('item',),)
                    jma_tree.insert(node_iid, 'end', text="y",
                                    values=(state.pos_y, ), tags=('item',),)
                    jma_tree.insert(node_iid, 'end', text="z",
                                    values=(state.pos_z, ), tags=('item',),)

                    jma_tree.insert(node_iid, 'end', text="scale",
                                    values=(state.scale, ), tags=('item',),)


    def jma_dir_browse(self):
        if self._compiling or self._loading or self._saving:
            return

        tags_dir = self.tags_dir.get()
        # Add data to the path and then use path_replace to match the case of any
        # data directory that might already be here.
        data_dir = str(path_replace(Path(tags_dir).parent.joinpath("data"), "data", "data"))
        jma_dir = self.jma_dir.get()
        if tags_dir and not jma_dir:
            jma_dir = data_dir

        dirpath = path_normalize(askdirectory(
            initialdir=jma_dir, parent=self,
            title="Select the folder of animations to compile..."))

        if not dirpath:
            return

        dirpath = str(Path(dirpath))
        if tags_dir and data_dir and os.path.basename(dirpath).lower() == "animations":
            object_dir = os.path.dirname(dirpath)

            if object_dir and is_in_dir(object_dir, data_dir):
                tag_path = os.path.join(object_dir, os.path.basename(object_dir))
                tag_path = os.path.join(tags_dir, os.path.relpath(tag_path, data_dir))
                self.model_animations_path.set(tag_path + ".model_animations")

        self.app_root.last_load_dir = os.path.dirname(dirpath)
        self.jma_dir.set(dirpath)
        if not self.tags_dir.get():
            self.tags_dir.set(
                os.path.join(
                    path_split(self.app_root.last_load_dir, "data"),
                    "tags"))

    def tags_dir_browse(self):
        if self._compiling or self._loading or self._saving:
            return

        old_tags_dir = self.tags_dir.get()
        tags_dir = askdirectory(
            initialdir=old_tags_dir, parent=self,
            title="Select the root of the tags directory")

        if not tags_dir:
            return

        tags_dir = str(Path(tags_dir))

        antr_path = self.model_animations_path.get()
        if old_tags_dir and antr_path and not is_in_dir(antr_path, tags_dir):
            # adjust antr filepath to be relative to the new tags directory
            antr_path = os.path.join(tags_dir, os.path.relpath(antr_path, old_tags_dir))
            self.model_animations_path.set(antr_path)

        self.app_root.last_load_dir = os.path.dirname(tags_dir)
        self.tags_dir.set(tags_dir)

    def model_animations_path_browse(self, force=False):
        if not force and (self._compiling or self._loading or self._saving):
            return

        antr_dir = os.path.dirname(self.model_animations_path.get())
        if self.tags_dir.get() and not antr_dir:
            antr_dir = self.tags_dir.get()

        fp = asksaveasfilename(
            initialdir=antr_dir, title="Save model_animations to...", parent=self,
            filetypes=(("Model animations graph", "*.model_animations"), ('All', '*')))

        if not fp:
            return

        fp = Path(fp).with_suffix(".model_animations")

        self.app_root.last_load_dir = str(fp.parent)
        self.model_animations_path.set(str(fp))

        self.tags_dir.set(
            path_split(self.app_root.last_load_dir, "tags", after=True))

    def apply_style(self, seen=None):
        BinillaWidget.apply_style(self, seen)
        self.update()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry("%sx%s" % (w, h))
        self.minsize(width=w, height=h)

    def set_animation_delta_tolerance(self):
        try:
            new_tolerance = float(self.animation_delta_tolerance_string.get())
            if new_tolerance >= 0:
                self.animation_delta_tolerance = new_tolerance
                return

            self.animation_delta_tolerance = 0
        except Exception:
            return

        self.animation_delta_tolerance_string.set(
            str(("%.20f" % self.animation_delta_tolerance)).rstrip("0").rstrip("."))

    def destroy(self):
        try:
            self.app_root.tool_windows.pop(self.window_name, None)
        except AttributeError:
            pass
        window_base_class.destroy(self)

    def load_animations(self):
        if not self._compiling and not self._loading and not self._saving:
            self._loading = True
            try:
                self._load_animations()
            except Exception:
                print(format_exc())
            try:
                self.populate_animations_info_tree()
            except Exception:
                print(format_exc())
            self._loading = False

    def save_animations(self):
        if not self._compiling and not self._loading and not self._saving:
            self._saving = True
            try:
                self._save_animations()
            except Exception:
                print(format_exc())
            self._saving = False

    def compile_model_animations(self):
        if not self._compiling and not self._loading and not self._saving:
            self._compiling = True
            try:
                self._compile_model_animations()
            except Exception:
                print(format_exc())
            self._compiling = False

    def _load_animations(self):
        animations_dir = self.jma_dir.get()
        if not animations_dir:
            return

        start = time.time()
        print("Locating jma files...")
        fps = []
        for _, __, files in os.walk(animations_dir):
            for fname in files:
                ext = os.path.splitext(fname)[-1].lower()
                if ext in JMA_ANIMATION_EXTENSIONS:
                    fps.append(os.path.join(animations_dir, fname))

            break

        if not fps:
            print("    No valid jma files found in the folder.")
            return

        self.jma_anim_set = None

        jma_anims = self.jma_anims = []
        print("Loading jma files...")
        self.update()
        for fp in fps:
            try:
                #print("    %s" % fp.replace('/', '\\').split("\\")[-1])
                self.update()

                anim_name = os.path.basename(fp)
                ext = os.path.splitext(fp)[-1].lower()

                jma_anim = None
                if ext in JMA_ANIMATION_EXTENSIONS:
                    with open(fp, "r") as f:
                        jma_anim = read_jma(f.read(), '', anim_name)

                if jma_anim:
                    jma_anims.append(jma_anim)
            except Exception:
                print(format_exc())
                print("    Could not parse '%s'" % anim_name)
                self.update()

        if not jma_anims:
            print("    No valid jma files found.")
            return

        first_crc = None
        for jma_anim in jma_anims:
            if first_crc is None:
                first_crc = jma_anim.node_list_checksum
            elif first_crc != jma_anim.node_list_checksum:
                print("    Warning, not all node list checksums match.")
                break


        print("Merging jma data...")
        self.app_root.update()
        self.jma_anim_set = JmaAnimationSet()
        errors_occurred = False
        for jma_anim in jma_anims:
            errors = self.jma_anim_set.merge_jma_animation(jma_anim)
            errors_occurred |= bool(errors)
            if errors:
                print("    Errors in '%s'" % jma_anim.name)
                for error in errors:
                    print("        ", error, sep='')

            self.update()

        antr_path = self.model_animations_path.get()
        if errors_occurred:
            print("    Errors occurred while loading jma files.")

        print("Finished loading animations. Took %s seconds.\n" %
              str(time.time() - start).split('.')[0])

    def _save_animations(self):
        animations_dir = self.jma_dir.get()
        if not animations_dir:
            return

        start = time.time()
        print("Saving jma animations...")
        self.update()
        for jma_anim in self.jma_anims:
            if isinstance(jma_anim, JmaAnimation):
                jma_filepath = os.path.join(
                    animations_dir, jma_anim.name + jma_anim.ext)
                write_jma(jma_filepath, jma_anim)

        print("Finished saving animations. Took %s seconds.\n" %
              str(time.time() - start).split('.')[0])

    def _compile_model_animations(self):
        if not self.jma_anim_set:
            return

        print("Compiling...")
        while not self.model_animations_path.get():
            self.model_animations_path_browse(True)
            if (not self.model_animations_path.get()) and self.warn_cancel():
                print("    Model_animations compilation cancelled.")
                return

        try:
            antr_tag = antr_def.build(filepath=self.model_animations_path.get())
        except Exception:
            antr_tag = None

        mod2_nodes = None
        if self.calculate_limp_limb_vectors.get():
            antr_path = self.model_animations_path.get()
            antr_dir = os.path.dirname(antr_path)
            mod2_path = os.path.join(
                antr_dir, os.path.splitext(os.path.basename(antr_path))[0] + ".gbxmodel")
            while mod2_nodes is None:
                try:
                    mod2_nodes = partial_mod2_def.build(filepath=mod2_path).\
                                 data.tagdata.nodes.STEPTREE
                    break
                except Exception:
                    print("Could not load the selected gbxmodel.")

                mod2_path = asksaveasfilename(
                    initialdir=antr_dir, parent=self,
                    title="Select the gbxmodel to get nodes from",
                    filetypes=(("Gearbox model", "*.gbxmodel"), ('All', '*')))

                if (not mod2_path) and self.warn_cancel():
                    print("    Model_animations compilation cancelled.")
                    return

        updating = antr_tag is not None
        if updating:
            print("Updating existing model_animations tag.")
        else:
            print("Creating new model_animations tag.")
            antr_tag = antr_def.build()

        antr_tag.filepath = self.model_animations_path.get()

        self.update()
        errors = compile_model_animations(antr_tag, self.jma_anim_set, False,
                                          self.animation_count_limit.get(),
                                          self.animation_delta_tolerance,
                                          self.update_mode.get(), mod2_nodes)
        if errors:
            for error in errors:
                print(error)

            self.update()
            if not messagebox.askyesno(
                    "Model_animations compilation failed",
                    "Errors occurred while compiling animations(check console). "
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
            print("    Could not save compiled model_animations.")

    def warn_cancel(self):
        return bool(messagebox.askyesno(
            "Unsaved model_animations",
            "Are you sure you wish to cancel?",
            icon='warning', parent=self))


if __name__ == "__main__":
    AnimationsCompilerWindow(None).mainloop()
