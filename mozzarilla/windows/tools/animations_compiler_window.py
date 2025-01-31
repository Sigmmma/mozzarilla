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
from binilla.widgets.scroll_menu import ScrollMenu
from binilla.windows.filedialog import askdirectory, asksaveasfilename

from reclaimer.hek.defs.antr import antr_def
from reclaimer.os_hek.defs.magy import magy_def
from reclaimer.os_hek.defs.antr import antr_def as os_antr_def
from reclaimer.mcc_hek.defs.antr import antr_def as mcc_antr_def
from reclaimer.stubbs.defs.antr import antr_def as stubbs_antr_def
from reclaimer.animation.jma import read_jma, write_jma,\
     JmaAnimation, JmaAnimationSet
from reclaimer.animation import constants as const
from reclaimer.animation.animation_compilation import \
     compile_model_animations
from reclaimer.animation.structs import partial_mod2_def

from supyr_struct.util import is_in_dir, path_normalize,\
     path_split, path_replace

from mozzarilla import editor_constants as e_c

if __name__ == "__main__":
    window_base_class = tk.Tk
else:
    window_base_class = tk.Toplevel

ANIM_DEF_NAMES = (
    "Xbox/PC/CE",
    "OpenSauce",
    "OpenSauce (animations_yelo)",
    "MCC",
    "Stubbs the Zombie"
    )
ANIM_DEFS = {
    0: antr_def,
    1: os_antr_def,
    2: magy_def,
    3: mcc_antr_def,
    #4: stubbs_antr_def,
    }
COMPILE_MODE_NAMES = (
    "Preserve nothing (erase and rebuild tag)",
    "Preserve all used animations/tag values",
    "Preserve everything (non-destructive)"
    )
COMPILE_MODES = {
    0: const.ANIMATION_COMPILE_MODE_NEW,
    1: const.ANIMATION_COMPILE_MODE_PRESERVE,
    2: const.ANIMATION_COMPILE_MODE_ADDITIVE,
    }
PHYSICS_CALC_MODE_NAMES = (
    "Calculate if biped animations are detected",
    "Calculate",
    "Do not calculate",
    )
PHYSICS_CALC_MODES = {
    0: const.PHYSICS_CALC_MODE_GUESS,
    1: const.PHYSICS_CALC_MODE_ALWAYS,
    2: const.PHYSICS_CALC_MODE_NEVER,
    }
COMPRESS_MODE_NAMES = (
    "Use tag compression fields",
    "Always try (overrides tag fields)",
    "Never  try (overrides tag fields)",
    )
COMPRESS_MODES = {
    0: const.ANIMATION_COMPRESS_MODE_USE_FLAG,
    1: const.ANIMATION_COMPRESS_MODE_IF_BETTER,
    2: const.ANIMATION_COMPRESS_MODE_NEVER,
    }

class AnimationsCompilerWindow(window_base_class, BinillaWidget):
    app_root = None
    tags_dir = ''

    jma_anims = ()
    jma_anim_set = None

    _compiling = False
    _loading = False
    _saving = False

    _jma_tree_iids = ()

    delta_tolerance = 1.0
    compression_quality = 100*const.COMPRESS_RATIO_GOOD_CUTOFF

    def __init__(self, app_root, *args, **kwargs):
        if window_base_class == tk.Toplevel:
            kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
            self.app_root = app_root
        else:
            self.app_root = self

        window_base_class.__init__(self, app_root, *args, **kwargs)
        BinillaWidget.__init__(self, *args, **kwargs)

        self.title("Model animations compiler")
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

        self.fix_anim_types = tk.IntVar(self, 0)
        self.delta_tolerance_string = tk.StringVar(
            self, str(self.delta_tolerance))
        self.compression_quality_string = tk.StringVar(
            self, f"{self.compression_quality} %")
        self.delta_tolerance_string.trace(
            "w", lambda *a, s=self: s.set_delta_tolerance())
        self.compression_quality_string.trace(
            "w", lambda *a, s=self: s.set_compression_quality())

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
            self.dirs_frame, text="model_animations output path")

        self.enum_frame = tk.Frame(self.settings_frame)
        self.advanced_frame = tk.LabelFrame(
            self.settings_frame, text="Advanced settings")
        self.spinbox_frame = tk.Frame(self.advanced_frame)
        self.delta_tolerance_frame = tk.LabelFrame(
            self.spinbox_frame, text="Animation delta")
        self.compression_quality_frame = tk.LabelFrame(
            self.spinbox_frame, text="Compression quality")
        self.target_tag_type_frame = tk.LabelFrame(
            self.enum_frame, text="Target engine")
        self.compress_mode_frame = tk.LabelFrame(
            self.enum_frame, text="Compression mode")
        self.compile_mode_frame = tk.LabelFrame(
            self.enum_frame, text="Tag update mode")
        self.physics_mode_frame = tk.LabelFrame(
            self.enum_frame, text=(
                "Calculate biped limp node vectors"
                " (used in death settle physics)"
                )
            )

        self.delta_tolerance_info = tk.Label(
            self.delta_tolerance_frame, justify='left', anchor="w",
            text=("Tweaks the tolerances used to\n"
                  "detect if a node is animated.\n"
                  "Higher values result in smaller,\n"
                  "but less accurate animation tags."))
        self.compression_quality_info = tk.Label(
            self.compression_quality_frame, justify='left', anchor="w",
            text=("Tweaks the tolerances used to\n"
                  "determine compression keyframes.\n"
                  "Lower values result in smaller,\n"
                  "but less accurate animation tags."))
        self.delta_tolerance_spinbox = tk.Spinbox(
            self.delta_tolerance_frame, from_=0, to=100, width=25,
            increment=1, justify="right",
            textvariable=self.delta_tolerance_string)
        self.compression_quality_spinbox = tk.Spinbox(
            self.compression_quality_frame, from_=0, to=100, width=25,
            increment=1, justify="right",
            textvariable=self.compression_quality_string)

        self.target_tag_type_menu = ScrollMenu(
            self.target_tag_type_frame, menu_width=11, options=ANIM_DEF_NAMES
            )
        self.compress_mode_menu = ScrollMenu(
            self.compress_mode_frame, menu_width=11, options=COMPRESS_MODE_NAMES
            )
        self.compile_mode_menu = ScrollMenu(
            self.compile_mode_frame, menu_width=11, options=COMPILE_MODE_NAMES
            )
        self.physics_mode_menu = ScrollMenu(
            self.physics_mode_frame, menu_width=11, options=PHYSICS_CALC_MODE_NAMES
            )

        self.fix_anim_types_cbtn = tk.Checkbutton(
            self.advanced_frame, variable=self.fix_anim_types,
            text=("Fix animation types (i.e. is base, but must be overlay)"), anchor="w")

        self.compress_mode_menu.sel_index   = 0
        self.physics_mode_menu.sel_index    = 0
        self.compile_mode_menu.sel_index    = 1
        self.target_tag_type_menu.sel_index = (
            0 if not hasattr(self.app_root, "handler_name") else
            1 if "OS"       in self.app_root.handler_name   else
            3 if "MCC"      in self.app_root.handler_name   else
            4 if "Stubbs"   in self.app_root.handler_name   else
            0
            )

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
        self.main_frame.pack(fill="both", side='left', pady=4, padx=4)
        self.jma_info_frame.pack(fill="both", side='left', pady=4, padx=4,
                                 expand=True)

        self.dirs_frame.pack(fill="x", padx=4, pady=4)
        self.buttons_frame.pack(fill="x", padx=4, pady=4)
        self.settings_frame.pack(fill="both")

        self.jma_dir_frame.pack(fill='x', padx=4, pady=4)
        self.tags_dir_frame.pack(fill='x', padx=4, pady=4)
        self.model_animations_path_frame.pack(fill='x', padx=4, pady=4)

        self.jma_dir_entry.pack(side='left', fill='x', expand=True)
        self.jma_dir_browse_button.pack(side='left')

        self.model_animations_path_entry.pack(side='left', fill='x', expand=True, padx=2)
        self.model_animations_path_browse_button.pack(side='left')

        self.tags_dir_entry.pack(side='left', fill='x', expand=True, padx=2)
        self.tags_dir_browse_button.pack(side='left')

        self.jma_info_hsb.pack(side="bottom", fill='x')
        self.jma_info_vsb.pack(side="right",  fill='y')
        self.jma_info_tree.pack(side='left', fill='both', expand=True)

        self.load_button.pack(side='left', fill='both', padx=4, expand=True)
        self.save_button.pack(side='left', fill='both', padx=4, expand=True)
        self.compile_button.pack(side='right', fill='both', padx=4, expand=True)

        for w in (self.enum_frame, self.advanced_frame):
            w.pack(expand=True, fill='both', pady=4, padx=4)

        for w in (self.fix_anim_types_cbtn, self.spinbox_frame):
            w.pack(expand=True, fill='both', pady=2, padx=4)

        for w in (self.delta_tolerance_frame, self.compression_quality_frame):
            w.pack(expand=True, side="left", fill='both')

        self.enum_frame.columnconfigure(1, weight=1)
        self.enum_frame.columnconfigure(0, weight=1)
        self.enum_frame.rowconfigure(1, weight=1)
        self.compile_mode_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.target_tag_type_frame.grid(row=1, column=0, sticky="ew")
        self.compress_mode_frame.grid(row=1, column=1, sticky="ew")
        self.physics_mode_frame.grid(row=2, column=0, columnspan=3, sticky="ew")

        self.delta_tolerance_info.pack(fill='both', expand=True, padx=4, pady=4)
        self.delta_tolerance_spinbox.pack(padx=4, pady=4, anchor="w")
        self.compression_quality_info.pack(fill='both', expand=True, padx=4, pady=4)
        self.compression_quality_spinbox.pack(padx=4, pady=4, anchor="w")
        self.target_tag_type_menu.pack(expand=True, fill='both', padx=4, pady=4)
        self.compress_mode_menu.pack(expand=True, fill='both', padx=4, pady=4)
        self.compile_mode_menu.pack(expand=True, fill='both', padx=4, pady=4)
        self.physics_mode_menu.pack(expand=True, fill='both', padx=4, pady=4)

        self.apply_style()
        if self.app_root is not self:
            self.transient(self.app_root)

    def populate_animations_info_tree(self):
        jma_tree = self.jma_info_tree
        if not jma_tree['columns']:
            jma_tree['columns'] = ('data', )
            jma_tree.heading("#0")
            jma_tree.heading("data")
            jma_tree.column("#0", minwidth=100, width=180)
            jma_tree.column("data", minwidth=80, width=130, stretch=False)

        for iid in self._jma_tree_iids:
            jma_tree.delete(iid)

        self._jma_tree_iids = []

        if not self.jma_anims or not self.jma_anim_set:
            return

        # always calculate for informational purposes, and then
        # clear them so they don't get forced into the antr tag
        print("Generating preview node physics values...")
        self.jma_anim_set.calculate_limp_node_data()
        limp_infos  = self.jma_anim_set.limp_node_infos
        self.jma_anim_set.limp_node_infos = []

        nodes_iid = jma_tree.insert('', 'end', text="Nodes", tags=('item',),
                                    values=(len(self.jma_anim_set.nodes),))
        self._jma_tree_iids.append(nodes_iid)
        for n, node in enumerate(self.jma_anim_set.nodes):
            iid = jma_tree.insert(nodes_iid, 'end', text=node.name, tags=('item',))
            parent_name = child_name = sibling_name = "NONE"
            if node.sibling_index >= 0:
                sibling_name = self.jma_anim_set.nodes[node.sibling_index].name
            if node.first_child >= 0:
                child_name = self.jma_anim_set.nodes[node.first_child].name
            if node.parent_index >= 0:
                parent_name = self.jma_anim_set.nodes[node.parent_index].name

            jma_tree.insert(iid, 'end', text="Next sibling",
                            values=(sibling_name, ), tags=('item',),)
            jma_tree.insert(iid, 'end', text="First child",
                            values=(child_name, ), tags=('item',),)
            jma_tree.insert(iid, 'end', text="Parent",
                            values=(parent_name, ), tags=('item',),)

            info = limp_infos[n] if n < len(limp_infos) else None
            joint_type = (""      if not(info and info.axes_free) else
                          "Hinge" if info.axes_free == 1          else
                          "Socket")

            if joint_type:
                jma_tree.insert(iid, 'end', text=f"{joint_type} base i",
                                values=(info.i, ), tags=('item',),)
                jma_tree.insert(iid, 'end', text=f"{joint_type} base j",
                                values=(info.j, ), tags=('item',),)
                jma_tree.insert(iid, 'end', text=f"{joint_type} base k",
                                values=(info.k, ), tags=('item',),)
                jma_tree.insert(iid, 'end', text=f"{joint_type} range",
                                values=(info.vector_range*const.RAD_TO_DEG, ),
                                tags=('item',),)

            if joint_type == "Socket":
                jma_tree.insert(iid, 'end', text="Socket pitch range",
                                values=(info.delta*const.RAD_TO_DEG, ),
                                tags=('item',),)
                jma_tree.insert(iid, 'end', text="Socket roll range",
                                values=(info.cross_delta*const.RAD_TO_DEG, ),
                                tags=('item',),)


        anims_iid = jma_tree.insert('', 'end', text="Animations", tags=('item',),
                                    values=(len(self.jma_anims),))
        self._jma_tree_iids.append(anims_iid)
        for jma_anim in self.jma_anims:
            iid = jma_tree.insert(anims_iid, 'end', tags=('item',),
                                  text=jma_anim.name + jma_anim.ext)
            jma_tree.insert(iid, 'end', text="Version", tags=('item',),
                            values=(jma_anim.version, ))
            jma_tree.insert(iid, 'end', text="Node list checksum", tags=('item',),
                            values=(jma_anim.node_list_checksum, ))
            jma_tree.insert(iid, 'end', text="World relative", tags=('item',),
                            values=(jma_anim.world_relative, ))
            jma_tree.insert(iid, 'end', text="Type", tags=('item',),
                            values=(jma_anim.anim_type, ))
            jma_tree.insert(iid, 'end', text="Frame count", tags=('item',),
                            values=(jma_anim.frame_count, ))
            jma_tree.insert(iid, 'end', text="Node count", tags=('item',),
                            values=(jma_anim.node_count, ))
            jma_tree.insert(iid, 'end', text="Frame info", tags=('item',),
                            values=(jma_anim.frame_info_type, ))

            rot_flags   = jma_anim.rot_flags
            trans_flags = jma_anim.trans_flags
            scale_flags = jma_anim.scale_flags

            node_flags_iid = jma_tree.insert(
                iid, 'end', text="Transform flags", tags=('item',),
                values=(len(jma_anim.nodes),))
            for n, node in enumerate(jma_anim.nodes):
                node_iid = jma_tree.insert(
                    node_flags_iid, 'end', text=node.name,
                    tags=('item',), values=("".join((
                        "R" if rot_flags[n]   else "-",
                        "T" if trans_flags[n] else "-",
                        "S" if scale_flags[n] else "-",
                        ))))
                continue
                jma_tree.insert(node_iid, 'end', text="Rotation",
                                values=(rot_flags[n], ), tags=('item',))
                jma_tree.insert(node_iid, 'end', text="Position",
                                values=(trans_flags[n], ), tags=('item',))
                jma_tree.insert(node_iid, 'end', text="Scale",
                                values=(scale_flags[n], ), tags=('item',))

            continue
            print("REMINDER TO REMOVE THIS DEBUG IN COMPILER WINDOW")
            # code below is very CPU and RAM intensive.
            # don't remove this continue unless debugging

            has_dxdy = "dx" in jma_anim.frame_info_type
            has_dz   = "dz" in jma_anim.frame_info_type
            has_dyaw = "dyaw" in jma_anim.frame_info_type

            root_data_iid = jma_tree.insert(
                iid, 'end', text="Root node data", tags=('item',),
                values=(len(jma_anim.root_node_info),)
                ) if jma_anim.has_frame_info else None
            for f, state in enumerate(jma_anim.root_node_info):
                if not root_data_iid:
                    break

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
            for n, node in enumerate(jma_anim.nodes):
                states_iid = jma_tree.insert(
                    nodes_iid, 'end', text=node.name,
                    tags=('item',))

                for f, frame in enumerate(jma_anim.frames):
                    state = frame[n]
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
        if not self.tags_dir.get():
            work_dir = path_split(dirpath, "data")
            data_dir = os.path.join(work_dir, "data")
            tags_dir = os.path.join(work_dir, "tags")
            self.tags_dir.set(tags_dir)

        if tags_dir and data_dir and os.path.basename(dirpath).lower() == "animations":
            object_dir = os.path.dirname(dirpath)

            if object_dir and is_in_dir(object_dir, data_dir):
                rel_dir  = os.path.relpath(object_dir, data_dir)
                tag_path = os.path.join(tags_dir, rel_dir, os.path.basename(object_dir))
                self.model_animations_path.set(tag_path + ".model_animations")

        self.app_root.last_load_dir = os.path.dirname(dirpath)
        self.jma_dir.set(dirpath)

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
            filetypes=(
                ("Model animations graph", "*.model_animations"),
                ("Yelo model animations graph", "*.model_animations_yelo"),
                ('All', '*')
                ))

        if not fp:
            return
        
        fp = Path(fp).with_suffix(self.get_model_animations_tagdef().ext)

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

    def set_delta_tolerance(self):
        try:
            val_str = self.delta_tolerance_string.get().replace(" ", "")
            val     = max(0.00001, min(100, float(val_str)))

            new_val_str = str("%.10f" % val).rstrip("0").rstrip(".")
            if self.delta_tolerance != val:
                self.delta_tolerance = val
                self.delta_tolerance_string.set(new_val_str)

        except Exception:
            pass

    def set_compression_quality(self):
        try:
            val_str = self.compression_quality_string.get()\
                      .replace(" ", "").split("%")[0].split(".")[0]
            val     = max(0, min(100, int(float(val_str))))

            new_val_str = f"{val} %"
            if self.compression_quality != val or new_val_str != val_str:
                self.compression_quality = val
                self.compression_quality_string.set(new_val_str)

        except Exception:
            pass

    def destroy(self):
        try:
            self.app_root.tool_windows.pop(self.window_name, None)
        except AttributeError:
            pass
        window_base_class.destroy(self)
    
    def get_model_animations_tagdef(self):
        return ANIM_DEFS.get(self.target_tag_type_menu.sel_index, antr_def)
    
    def get_compression_mode(self):
        return COMPRESS_MODES.get(self.compress_mode_menu.sel_index,
                                  const.ANIMATION_COMPRESS_MODE_NEVER)
    
    def get_compile_mode(self):
        return COMPILE_MODES.get(self.compile_mode_menu.sel_index,
                                 const.ANIMATION_COMPILE_MODE_PRESERVE)
    
    def get_physics_calc_mode(self):
        return PHYSICS_CALC_MODES.get(self.physics_mode_menu.sel_index,
                                      const.PHYSICS_CALC_MODE_GUESS)

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
                if ext in const.JMA_ANIMATION_EXTENSIONS:
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
                if ext in const.JMA_ANIMATION_EXTENSIONS:
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
                print("    Compiling model_animations cancelled.")
                return

        try:
            antr_tag = self.get_model_animations_tagdef().build(
                filepath=self.model_animations_path.get()
                )
        except Exception:
            antr_tag = None

        updating = antr_tag is not None
        filepath = Path(self.model_animations_path.get())
        tag_def = self.get_model_animations_tagdef()
        if updating:
            print("Updating existing model_animations tag.")
            antr_tag = tag_def.build(filepath=filepath)
        else:
            print("Creating new model_animations tag.")
            antr_tag = tag_def.build()
            antr_tag.filepath = filepath.with_suffix(tag_def.ext)

        self.update()
        errors = compile_model_animations(
            antr_tag, self.jma_anim_set, False,
            self.get_compile_mode(), self.get_compression_mode(),
            self.delta_tolerance, self.compression_quality/100,
            ">", self.fix_anim_types.get(), self.get_physics_calc_mode()
            )
        if errors:
            for error in errors:
                print(error)

            self.update()
            if not messagebox.askyesno(
                    "Compiling model_animations failed",
                    "Errors occurred while compiling animations(check console). "
                    "Do you want to save the model_animations tag anyway?",
                    icon='warning', parent=self):
                print("    Saving model_animations cancelled.")
                return

        try:
            antr_tag.calc_internal_data()
            antr_tag.serialize(temp=False, backup=False, calc_pointers=False,
                               int_test=False)
            print("    Finished\n")
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
