import os
import tkinter as tk
import zlib

from math import sqrt
from os.path import splitext, dirname, join, relpath, basename, isfile, exists
from struct import Struct as PyStruct
from tkinter import messagebox
from tkinter.filedialog import askdirectory, asksaveasfilename
from traceback import format_exc

from binilla.util import sanitize_path, is_in_dir, get_cwd
from binilla.widgets import BinillaWidget
from reclaimer.jms import read_jms, MergedJmsModel, GeometryMesh
from reclaimer.hek.defs.mod2 import mod2_def,\
     triangle as mod2_tri_struct, fast_uncompressed_vertex as mod2_vert_struct
from reclaimer.hek.defs.objs.matrices import quaternion_to_matrix, Matrix
from reclaimer.stripify import Stripifier

from reclaimer.common_descs import raw_reflexive, BlockDef

mod2_verts_def = BlockDef(
    raw_reflexive("vertices", mod2_vert_struct),
    endian='>'
    )

mod2_tri_strip_def = BlockDef(
    raw_reflexive("triangle", mod2_tri_struct),
    endian='>'
    )


if __name__ == "__main__":
    model_compiler_base_class = tk.Tk
else:
    model_compiler_base_class = tk.Toplevel

curr_dir = get_cwd(__file__)

LOD_NAMES = ("superhigh", "high", "medium", "low", "superlow")

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

        tagdata = mod2_tag.data.tagdata
        tagdata.base_map_u_scale = self.merged_jms.u_scale
        tagdata.base_map_v_scale = self.merged_jms.v_scale
        tagdata.node_list_checksum = self.merged_jms.node_list_checksum

        # make nodes
        mod2_nodes = tagdata.nodes.STEPTREE
        del mod2_nodes[:]
        for node in self.merged_jms.nodes:
            mod2_nodes.append()
            mod2_node = mod2_nodes[-1]

            mod2_node.name = node.name[: 31]
            mod2_node.next_sibling_node = node.sibling_index
            mod2_node.first_child_node = node.first_child
            mod2_node.parent_node = node.parent_index
            mod2_node.translation[:] = node.pos_x / 100,\
                                       node.pos_y / 100,\
                                       node.pos_z / 100
            mod2_node.rotation[:] = node.rot_i, node.rot_j,\
                                    node.rot_k, node.rot_w

            if node.parent_index >= 0:
                mod2_node.distance_from_parent = sqrt(
                    node.pos_x**2 + node.pos_y**2 + node.pos_z**2) / 100


        # make shader references
        mod2_shaders = tagdata.shaders.STEPTREE
        del mod2_shaders[:]
        for mat in self.merged_jms.materials:
            mod2_shaders.append()
            mod2_shader = mod2_shaders[-1]
            mod2_shader.shader.tag_class.set_to(mat.shader_type)
            mod2_shader.shader.filepath = mat.shader_path


        # make regions
        mod2_regions = tagdata.regions.STEPTREE
        del mod2_regions[:]

        global_markers = {}
        geom_meshes = []
        all_lod_nodes = {lod: set([0]) for lod in LOD_NAMES}
        for region_name in sorted(self.merged_jms.regions):
            region = self.merged_jms.regions[region_name]

            mod2_regions.append()
            mod2_region = mod2_regions[-1]
            mod2_region.name = region_name[: 31]

            mod2_perms = mod2_region.permutations.STEPTREE
            for perm_name in sorted(region.perm_meshes):
                perm = region.perm_meshes[perm_name]

                mod2_perms.append()
                mod2_perm = mod2_perms[-1]
                mod2_perm.name = perm_name[: 31]

                mod2_perm.flags.cannot_be_chosen_randomly = not perm.is_random_perm

                perm_added = False
                for i in range(len(LOD_NAMES)):
                    if LOD_NAMES[i] not in perm.lod_meshes:
                        continue
                    elif not perm.lod_meshes[LOD_NAMES[i]]:
                        continue
                    geom_index = len(geom_meshes)
                    lod_mesh = perm.lod_meshes[LOD_NAMES[i]]
                    geom_meshes.append(lod_mesh)

                    # figure out which nodes this mesh utilizes
                    this_meshes_nodes = set()
                    for mesh in lod_mesh.values():
                        for vert in mesh.verts:
                            if vert.node_1_weight < 1:
                                this_meshes_nodes.add(vert.node_0)
                            if vert.node_1_weight > 0:
                                this_meshes_nodes.add(vert.node_1)

                    all_lod_nodes[LOD_NAMES[i]].update(this_meshes_nodes)

                    while i < 5:
                        setattr(mod2_perm,
                                "%s_geometry_block" % LOD_NAMES[i],
                                geom_index)
                        i += 1

                    perm_added = True


                if len(perm.markers) > 32:
                    for marker in perm.markers:
                        global_markers.setdefault(
                            marker.name[: 31], []).append(marker)
                else:
                    perm_added |= bool(perm.markers)
                    mod2_markers = mod2_perm.local_markers.STEPTREE
                    for marker in perm.markers:
                        mod2_markers.append()
                        mod2_marker = mod2_markers[-1]

                        mod2_marker.name = marker.name[: 31]
                        mod2_marker.node_index = marker.parent
                        mod2_marker.translation[:] = marker.pos_x / 100,\
                                                     marker.pos_y / 100,\
                                                     marker.pos_z / 100
                        mod2_marker.rotation[:] = marker.rot_i, marker.rot_j,\
                                                  marker.rot_k, marker.rot_w


                if not perm_added:
                    del mod2_perms[-1]
                    continue

        if len(geom_meshes) > 256:
            print("Cannot add more than 256 geometries to a model. "
                  "Each material in each region in each permutation "
                  "in each LOD is counted as a single geometry.\n"
                  "This model would contain %s geometries." % len(geom_meshes))
            return

        # make the markers
        mod2_marker_headers = tagdata.markers.STEPTREE
        del mod2_marker_headers[:]
        for marker_name in sorted(global_markers):
            marker_list = global_markers[marker_name]
            mod2_marker_headers.append()
            mod2_marker_header = mod2_marker_headers[-1]

            mod2_marker_header.name = marker_name[: 31]
            mod2_marker_list = mod2_marker_header.marker_instances.STEPTREE

            for marker in marker_list:
                mod2_marker_list.append()
                mod2_marker = mod2_marker_list[-1]

                # figure out which permutation index this marker
                # matches for all the permutations in its region
                i = perm_index = 0
                for perm in mod2_regions[marker.region].permutations.STEPTREE:
                    if perm.name == marker.permutation:
                        perm_index = i
                        break
                    i += 1

                mod2_marker.region_index = marker.region
                mod2_marker.permutation_index = perm_index
                mod2_marker.node_index = marker.parent
                mod2_marker.translation[:] = marker.pos_x / 100,\
                                             marker.pos_y / 100,\
                                             marker.pos_z / 100
                mod2_marker.rotation[:] = marker.rot_i, marker.rot_j,\
                                          marker.rot_k, marker.rot_w

        # set the node counts per lod
        for lod in LOD_NAMES:
            lod_nodes = all_lod_nodes[lod]
            adding = True
            node_ct = len(mod2_nodes)
            
            for i in range(node_ct - 1, -1, -1):
                if i in lod_nodes:
                    break
                node_ct -= 1

            setattr(tagdata, "%s_lod_nodes" % lod, max(0, node_ct - 1))


        # calculate triangle strips
        stripped_geom_meshes = []
        for geom_idx in range(len(geom_meshes)):
            material_meshes = {}
            stripped_geom_meshes.append(material_meshes)
            for mat_idx in sorted(geom_meshes[geom_idx]):
                material_meshes[mat_idx] = mesh_list = []
                geom_mesh = geom_meshes[geom_idx][mat_idx]
                all_verts = geom_mesh.verts

                stripifier = Stripifier(geom_mesh.tris, True)
                stripifier.max_strip_len = 32760
                stripifier.make_strips()
                stripifier.link_strips()

                all_strips = stripifier.all_strips[0]
                if len(all_strips) == 1:
                    mesh_list.append(GeometryMesh(all_verts, all_strips[0]))
                    continue

                print("FUCK FUCK FUCK")
                for strip in all_strips:
                    geom_mesh = GeometryMesh()


        # make the geometries
        mod2_geoms = tagdata.geometries.STEPTREE
        del mod2_geoms[:]
        centroid = [0, 0, 0]
        vert_packer = PyStruct(">14f2h2f").pack_into
        for geom_idx in range(len(stripped_geom_meshes)):
            mod2_geoms.append()
            mod2_parts = mod2_geoms[-1].parts.STEPTREE

            for mat_idx in sorted(stripped_geom_meshes[geom_idx]):
                geom_mesh_list = stripped_geom_meshes[geom_idx][mat_idx]
                for geom_mesh in geom_mesh_list:
                    mod2_parts.append()
                    mod2_part = mod2_parts[-1]
                    mod2_verts = mod2_part.uncompressed_vertices.STEPTREE

                    tris  = geom_mesh.tris
                    verts = geom_mesh.verts
                    mod2_verts.extend(len(verts))

                    mod2_part.shader_index = mat_idx
                    mod2_part.centroid_translation[:] = centroid

                    # TODO: Modify this to take into account local nodes
                    # make a raw vert reflexive and replace the one in the part
                    mod2_part.uncompressed_vertices = mod2_verts_def.build()
                    mod2_verts = mod2_part.uncompressed_vertices.STEPTREE = \
                                 bytearray(68 * len(verts))
                    i = 0
                    for vert in verts:
                        vert_packer(
                            mod2_verts, i,
                            vert.pos_x / 100,  vert.pos_y / 100,  vert.pos_z / 100,
                            vert.norm_i, vert.norm_j, vert.norm_k,
                            # TODO: Calculate the binormal and tangent
                            0, 0, 0,
                            0, 0, 0,
                            vert.tex_u, 1 - vert.tex_v, vert.node_0, vert.node_1,
                            1 - vert.node_1_weight, vert.node_1_weight)
                        i += 68

                    # make a raw tri reflexive and replace the one in the part
                    mod2_part.triangles = mod2_tri_strip_def.build()
                    mod2_tris = mod2_part.triangles.STEPTREE = bytearray(
                        [255, 255]) * (3 * ((len(tris) + 2) // 3))
                    i = 0
                    for tri in tris:
                        mod2_tris[i]     = tri >> 8
                        mod2_tris[i + 1] = tri & 0xFF
                        i += 2


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
