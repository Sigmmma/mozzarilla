#!/usr/bin/env python3
#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

try:
    from .converter_base import ConverterBase
except (ImportError, SystemError):
    from converter_base import ConverterBase

from pathlib import Path
import threadsafe_tkinter as tk

from traceback import format_exc
from struct import pack_into, pack

from binilla.windows.filedialog import askopenfilename

from reclaimer.hek.defs.coll import coll_def
from reclaimer.hek.defs.mod2 import mod2_def
from reclaimer.hek.defs.mode import mode_def
from reclaimer.stubbs.defs.mode import mode_def as stubbs_mode_def
from reclaimer.stubbs.defs.coll import coll_def as stubbs_coll_def
from reclaimer.common_descs import tag_header
from reclaimer.util.matrices import quaternion_to_matrix, Matrix

from supyr_struct.buffer import get_rawdata
from supyr_struct.defs.block_def import BlockDef
from supyr_struct.field_types import FieldType, BytearrayRaw

window_base_class = tk.Toplevel
if __name__ == "__main__":
    window_base_class = tk.Tk

tag_header_def = BlockDef(tag_header)


def undef_size(node, *a, **kwa):
    if node is None:
        return 0
    return len(node)


raw_block_def = BlockDef("raw_block",
    BytearrayRaw('data', SIZE=undef_size)
    )


class Permutation():
    name = ""
    nodes = None
    def __init__(self, name):
        self.name = name
        self.nodes = {}


class Region():
    name = ""
    perms = None
    def __init__(self, name):
        self.name = name
        self.perms = {}


def get_tags(coll_path, model_in_path):
    mod2_path = str(Path(model_in_path).with_suffix('')) + "_COLL.gbxmodel"

    # get whether or not the collision tag is stubbs
    stubbs = tag_header_def.build(filepath=coll_path).version == 11

    if stubbs:
        coll_tag = stubbs_coll_def.build(filepath=coll_path)
    else:
        coll_tag = coll_def.build(filepath=coll_path)

    mod2_tag = mod2_def.build()
    mod2_tag.filepath = mod2_path
    model_in_rawdata = None

    guessed_mode = False
    while model_in_rawdata is None and model_in_path:
        try:
            model_in_rawdata = get_rawdata(filepath=model_in_path)
        except Exception:
            if guessed_mode:
                model_in_rawdata = None
                model_in_path = Path(askopenfilename(
                    initialdir=model_in_path.parent, filetypes=(
                        ('All', '*'), ('Gbxmodel', '*.gbxmodel')),
                    title="Select the gbxmodel to extract nodes from"))
            else:
                model_in_path = model_in_path.with_suffix(".model")
                guessed_mode = True

    if model_in_rawdata is not None:
        # we dont actually care about the geometries or shaders of the gbxmodel
        # tag we're loading, so null them out to speed up the loading process.
        geom_off = 64 + 4*9 + 2*5 + 126 + 12*3

        # make a copy so we dont edit the file
        model_in_rawdata = bytearray(model_in_rawdata)
        model_in_rawdata[geom_off:64 + 232] = b'\x00'*(64 + 232 - geom_off)

        if model_in_rawdata[36:40] == b"mod2":
            model_in_tag = mod2_def.build(rawdata=model_in_rawdata)
        elif stubbs:
            model_in_tag = stubbs_mode_def.build(rawdata=model_in_rawdata)
        else:
            model_in_tag = mode_def.build(rawdata=model_in_rawdata)

        mod2_tag.data.tagdata.nodes = model_in_tag.data.tagdata.nodes
    else:
        model_in_tag = None
        mod2_tag.data.tagdata.nodes.STEPTREE.append()
        node = mod2_tag.data.tagdata.nodes.STEPTREE[-1]
        node.name = "COLLISION ROOT"
        print("    %s" % model_in_path)
        print("    Could not load gbxmodel. Gbxmodel wont have nodes and "
              "the geometry will not be positioned or rotated properly.")

    return coll_tag, model_in_tag, mod2_tag


def get_collections(coll_tag):
    node_names = []
    reg_names = []
    all_perm_names = {}
    sorted_bsps = {}

    # build the region and permutation collections
    for region in coll_tag.data.tagdata.regions.STEPTREE:
        perms_by_region = Region(region.name)
        reg_names.append(region.name)

        perm_names = []
        all_perm_names[region.name] = perm_names

        for perm in region.permutations.STEPTREE:
            node_bsps_by_perm = Permutation(perm.name)
            perm_names.append(perm.name)

            perms_by_region.perms[perm.name] = node_bsps_by_perm

        sorted_bsps[region.name] = perms_by_region

    for node in coll_tag.data.tagdata.nodes.STEPTREE:
        node_names.append(node.name)

    return sorted_bsps, reg_names, all_perm_names, node_names


def get_node_transforms(nodes):
    node_transforms = [None]*len(nodes)

    # create a collection of absolute translations and rotations
    # to move and rotate each nodes collision model into place.
    for node_i in range(len(nodes)):
        node = nodes[node_i]
        trans = node.translation
        rot = node.rotation
        x, y, z = trans.x, trans.y, trans.z
        this_rot = quaternion_to_matrix(rot.i, rot.j, rot.k, rot.w)

        if node.parent_node >= 0:
            parent = node_transforms[node.parent_node]
            trans = Matrix((x, y, z))

            parent_rot = parent[4]
            this_rot = parent_rot * this_rot

            trans = parent_rot * trans
            x = trans[0][0] + parent[0]
            y = trans[1][0] + parent[1]
            z = trans[2][0] + parent[2]
        else:
            parent_rot = quaternion_to_matrix(0, 0, 0, 1)

        node_transforms[node_i] = [x, y, z, parent_rot, this_rot]

    return node_transforms


def sort_node_bsps(coll_tag, sorted_bsps, reg_names, all_perm_names):
    node_bsps = coll_tag.data.tagdata.nodes.STEPTREE
    coll_data = coll_tag.data.tagdata

    # sort the bsps by region, permutation, and node
    for node_i in range(len(node_bsps)):
        node = node_bsps[node_i]
        node_name = node.name

        try:
            region_name = reg_names[node.region]
            perm_names = all_perm_names[region_name]
            region = coll_data.regions.STEPTREE[node.region]
        except (IndexError, KeyError):
            continue

        bsps = node.bsps.STEPTREE
        perms_by_region = sorted_bsps[region_name].perms

        for bsp_i in range(len(bsps)):
            bsp = bsps[bsp_i]
            try:
                node_bsps_by_perm = perms_by_region[perm_names[bsp_i]]
            except (IndexError, KeyError):
                continue

            node_bsps_by_perm.nodes[node_name] = bsp

def make_raw_verts_block(node_bsp, node_transforms, node_i):
    raw_verts = raw_block_def.build()

    # create the uncompressed vertices bytearray that
    # all the parts will reuse. This is wasteful, but
    # i dont care to convert the vertex indices, so w/e
    uncomp_verts = bytearray(68*len(node_bsp.vertices.STEPTREE))
    raw_verts.data = uncomp_verts

    transform = node_transforms[node_i]
    dx, dy, dz = transform[0], transform[1], transform[2]
    rotation = transform[4]
    pos = 0
    for vert in node_bsp.vertices.STEPTREE:
        # rotate the vertices to match the nodes orientation
        trans = rotation * Matrix(vert[:3])

        # also translate the vertices to match the nodes position
        pack_into('>14f2h2f', uncomp_verts, pos,
                  trans[0][0]+dx, trans[1][0]+dy, trans[2][0]+dz,
                  1,0,0,0,1,0,0,0,1,0,0,0,0,1,0)
        pos += 68

    return raw_verts


def make_parts_by_mats(faces, raw_verts, parts, shaders, node_i,
                       use_mats=True, has_frames=True):
    parts_by_mats = {}
    for face in faces:
        mat = face.material
        missing_shader_ct = (mat + 1) - len(shaders)
        if missing_shader_ct > 0:
            for i in range(missing_shader_ct):
                shaders.append()
                shaders[-1].shader.filepath = "MISSING"

        if mat in parts_by_mats:
            continue
        if use_mats or not parts_by_mats:
            parts.append()
        parts_by_mats[mat] = part = parts[-1]

        part.shader_index = mat
        part.local_node_count = 1

        # if there are no frames, all parts
        # will be left parented to frame 0
        if has_frames:
            part.local_nodes[0] = node_i

        part.uncompressed_vertices.size = len(raw_verts.data)//68
        part.uncompressed_vertices.STEPTREE = raw_verts

    return parts_by_mats


def get_edge_loops_by_mats(faces, edges):
    edge_loops_by_mats = {}
    for f_i in range(len(faces)):
        face = faces[f_i]
        mat = face.material
        if mat in edge_loops_by_mats:
            edge_loops = edge_loops_by_mats[mat]
        else:
            edge_loops_by_mats[mat] = edge_loops = []

        e_i = face.first_edge
        face_edges = set()
        vert_indices = []
        while e_i not in face_edges:
            face_edges.add(e_i)
            edge = edges[e_i]
            if edge[4] == f_i:
                e_i = edge[2]
                vert_indices.append(edge[0])
            else:
                e_i = edge[3]
                vert_indices.append(edge[1])

        edge_loops.append(vert_indices)

    return edge_loops_by_mats


def fill_parts_by_mats(parts_by_mats, edge_loops_by_mats):
    for mat in edge_loops_by_mats:
        loops = edge_loops_by_mats[mat]
        part = parts_by_mats[mat]

        # create the uncompressed triangles bytearray
        tris = part.triangles
        tris.STEPTREE = raw_block_def.build()

        uncomp_tris = b''
        rev = True
        for loop in loops:
            v0 = loop[0]
            v1 = loop[1]
            v0_packed = pack('>h', v0)
            if uncomp_tris:
                uncomp_tris += v0_packed
                rev = not rev

            for v2 in loop[2:]:
                if rev:
                    uncomp_tris += v0_packed*2 + pack('>hh', v1, v2)
                else:
                    uncomp_tris += v0_packed*2 + pack('>hh', v2, v1)

                rev = not rev

                v1 = v2

                # repeat the last vert to break the strip
                uncomp_tris += uncomp_tris[-2:]

        # cut off the last repeated verts
        uncomp_tris = uncomp_tris[:-2]

        # pad the last strip piece up to 3 entries
        uncomp_tris += uncomp_tris[-2:]*(
            (3-((len(uncomp_tris)//2)%3))%3)

        tris.size = len(uncomp_tris)//6
        tris.STEPTREE.data = uncomp_tris


def coll_to_mod2(coll_path, model_in_path=None, guess_mod2=True, use_mats=True):
    if guess_mod2:
        model_in_path = Path(coll_path).with_suffix(".gbxmodel")

    print("    Loading tags")
    coll_tag, model_in_tag, mod2_tag = get_tags(coll_path, model_in_path)
    mod2_data = mod2_tag.data.tagdata


    # TODO: MAKE SURE REGIONS AND PERMUTATIONS MATCH BETWEEN model_in_tag AND coll_tag
    mod2_data.flags.parts_have_local_nodes = True
    mod2_data.base_map_u_scale = 1.0
    mod2_data.base_map_v_scale = 1.0

    nodes   = mod2_data.nodes.STEPTREE
    regions = mod2_data.regions.STEPTREE
    geoms   = mod2_data.geometries.STEPTREE
    shaders = mod2_data.shaders.STEPTREE

    #print("Making materials")
    # build the shaders to represent the materials
    for material in coll_tag.data.tagdata.materials.STEPTREE:
        shaders.append()
        shaders[-1].shader.filepath = material.name

    #print("Getting absolute transforms")
    node_transforms = get_node_transforms(nodes)

    #print("Making collections")
    sorted_bsps, reg_names, perm_names, node_names = get_collections(coll_tag)

    #print("Sorting bsps")
    sort_node_bsps(coll_tag, sorted_bsps, reg_names, perm_names)


    print("    Building regions, permutations, geometries, and parts")
    # build the regions and permutations blocks
    for r_name in reg_names:
        perms_by_region = sorted_bsps[r_name].perms
        first_geom = len(geoms)
        perm_count = len(perms_by_region)

        # create a new region
        regions.append()
        region = regions[-1]

        region.name = r_name
        perms = region.permutations.STEPTREE

        # create as many perms and geoms
        # as we'll need for this region
        for p_name in perm_names[r_name]:
            # make a new geometry to hold all the parts we'll be making
            geoms.append()
            geom = geoms[-1]
            parts = geom.parts.STEPTREE
            node_bsps_by_perm = perms_by_region[p_name].nodes

            # create as many parts as we need for this geometry
            for node_i in range(len(node_names)):
                node_name = node_names[node_i]
                if not model_in_tag:
                    node_i = 0

                if node_name not in node_bsps_by_perm:
                    continue

                node_bsp = node_bsps_by_perm[node_name]
                faces = node_bsp.surfaces.STEPTREE
                edges = node_bsp.edges.STEPTREE

                raw_verts = make_raw_verts_block(
                    node_bsp, node_transforms, node_i)

                # find out how many materials are in this node_bsp
                # and create parts blocks for each of them.
                parts_by_mats = make_parts_by_mats(
                    faces, raw_verts, parts, shaders,
                    node_i, use_mats, model_in_tag)

                # collect all the edge loops that make up all the faces
                edge_loops_by_mats = get_edge_loops_by_mats(faces, edges)

                # loop over each material and create the
                # triangle list for the edges loops in it.
                fill_parts_by_mats(parts_by_mats, edge_loops_by_mats)

            # if we didnt make any parts, this geometry
            # is actually empty and should be deleted.
            if not len(parts):
                del geoms[-1]
                continue

            # create a permutation for this geometry
            perms.append()
            perm = perms[-1]
            perm.name = p_name
            geom_index = len(geoms) - 1
            perm.superlow_geometry_block = geom_index
            perm.low_geometry_block = geom_index
            perm.medium_geometry_block = geom_index
            perm.high_geometry_block = geom_index
            perm.superhigh_geometry_block = geom_index

    return mod2_tag


class CollisionConverter(ConverterBase, window_base_class):
    src_ext = "model_collision_geometry"
    dst_ext = "gbxmodel"

    def __init__(self, app_root, *args, **kwargs):
        if isinstance(self, tk.Toplevel):
            kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)

        window_base_class.__init__(self, app_root, *args, **kwargs)
        ConverterBase.__init__(self, app_root, *args, **kwargs)
        self.setup_window(*args, **kwargs)

    def setup_window(self, *args, **kwargs):
        ConverterBase.setup_window(self, *args, **kwargs)

        self.guess_mod2 = tk.IntVar(self, 1)
        self.use_mats = tk.IntVar(self, 1)

        # make the frames
        self.settings_frame = tk.LabelFrame(self, text="Conversion settings")

        # add the buttons
        self.guess_mod2_checkbutton = tk.Checkbutton(
            self.settings_frame, variable=self.guess_mod2,
            text="Locate gbxmodel in directory")
        self.use_mats_checkbutton = tk.Checkbutton(
            self.settings_frame, variable=self.use_mats,
            text="Use collision materials as shaders")

        self.pack_widgets()
        self.apply_style()

    def pack_widgets(self):
        ConverterBase.pack_widgets(self)

        # pack everything
        self.guess_mod2_checkbutton.pack(anchor='w', padx=10)
        self.use_mats_checkbutton.pack(anchor='w', padx=10)
        self.settings_frame.pack(fill='both', anchor='nw')

    def destroy(self):
        ConverterBase.destroy(self)
        window_base_class.destroy(self)

    def convert(self, tag_path):
        return coll_to_mod2(tag_path, guess_mod2=self.guess_mod2.get(),
                            use_mats=self.use_mats.get())

    def lock_ui(self):
        ConverterBase.lock_ui(self)
        for w in (self.guess_mod2_checkbutton, self.use_mats_checkbutton):
            w.config(state=tk.DISABLED)

    def unlock_ui(self):
        ConverterBase.unlock_ui(self)
        for w in (self.guess_mod2_checkbutton, self.use_mats_checkbutton):
            w.config(state=tk.NORMAL)


if __name__ == "__main__":
    try:
        CollisionConverter(None).mainloop()
        raise SystemExit(0)
    except Exception:
        print(format_exc())
        input()
