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

from pathlib import Path, PureWindowsPath
import threadsafe_tkinter as tk

from copy import deepcopy
from struct import Struct as PyStruct
from traceback import format_exc

from reclaimer.model.jms import ( JmsNode, JmsMaterial, JmsMarker,
     JmsVertex, JmsTriangle, JmsModel, MergedJmsModel, )
from reclaimer.model.jms.util import edge_loop_to_tris
from reclaimer.model.model_compilation import compile_gbxmodel
from reclaimer.util.matrices import euler_to_quaternion, Ray
from reclaimer.util.geometry import planes_to_verts_and_edge_loops
from reclaimer.hek.defs.sbsp import sbsp_def
from reclaimer.hek.defs.mod2 import mod2_def

from supyr_struct.defs.block_def import BlockDef

window_base_class = tk.Toplevel
if __name__ == "__main__":
    window_base_class = tk.Tk


def planes_to_verts_and_tris(planes, center, region=0, mat_id=0,
                             make_fans=False, round_adjust=0.000001):
    raw_verts, edge_loops = planes_to_verts_and_edge_loops(
        planes, center, round_adjust=round_adjust)

    verts = [JmsVertex(0, v[0]*100, v[1]*100, v[2]*100, tex_v=1.0) for v in raw_verts]
    tris = []
    # Calculate verts and triangles from the raw vert positions and edge loops
    for edge_loop in edge_loops:
        tris.extend(edge_loop_to_tris(edge_loop, region, mat_id, 0, make_fans))

    return verts, tris


def get_bsp_surface_edge_loops(bsp, ignore_flags=False):
    surfaces = bsp.surfaces.STEPTREE
    edges = bsp.edges.STEPTREE

    edge_loops = {}
    # loop over each surface in the collision.
    # NOTE: These are polygonal, not just triangular
    for s_i in range(len(surfaces)):
        surface = surfaces[s_i]
        flags = surface.flags
        e_i = surface.first_edge
        if ignore_flags:
            key = (surface.material, )
        else:
            key = (surface.material, flags.two_sided, flags.invisible,
                   flags.climbable, flags.breakable)

        surface_edges = set()
        vert_indices = []
        # loop over each edge in the surface and concatenate
        # the verts that make up the outline until we run out
        while e_i not in surface_edges:
            surface_edges.add(e_i)
            edge = edges[e_i]
            if edge[4] == s_i:
                e_i = edge[2]
                vert_indices.append(edge[0])
            else:
                e_i = edge[3]
                vert_indices.append(edge[1])

        edge_loops.setdefault(key, []).append(vert_indices)

    return edge_loops


def make_bsp_jms_verts(bsp, transform=None):
    verts = [JmsVertex(0, v[0]*100, v[1]*100, v[2]*100, tex_v=1.0)
             for v in bsp.vertices.STEPTREE]
    return verts


def make_marker_jms_model(sbsp_markers, nodes):
    markers = []
    for m in sbsp_markers:
        markers.append(
            JmsMarker(m.name, "bsp", 0, 0, m.rotation.i,
                      m.rotation.j, m.rotation.k, m.rotation.w,
                      m.position.x*100, m.position.y*100, m.position.z*100)
            )

    return JmsModel("bsp", 0, nodes, [], markers, ("markers", ))


def make_lens_flare_jms_model(lens_flare_markers, lens_flares, nodes):
    markers = []
    for m in lens_flare_markers:
        i, j, k, w = euler_to_quaternion(
            m.direction.i/128, m.direction.j/128, m.direction.k/128)
        lens_flare_name = lens_flares[m.lens_flare_index].shader.filepath

        markers.append(
            JmsMarker(lens_flare_name.split("\\")[-1], "bsp", 0, 0, i, j, k, w,
                      m.position.x*100, m.position.y*100, m.position.z*100)
            )

    return JmsModel("bsp", 0, nodes, [], markers, ("lens_flares", ))


def make_mirror_jms_models(clusters, nodes, make_fans=True):
    jms_models = []
    mirrors = []

    for cluster in clusters:
        mirrors.extend(cluster.mirrors.STEPTREE)

    mirror_index = 0
    for mirror in mirrors:
        tris = edge_loop_to_tris(
            len(mirror.vertices.STEPTREE), make_fan=make_fans)
        verts = [
            JmsVertex(0, vert[0] * 100, vert[1] * 100, vert[2] * 100, tex_v=1.0)
            for vert in mirror.vertices.STEPTREE
            ]

        jms_models.append(
            JmsModel("bsp", 0, nodes,
                     [JmsMaterial(mirror.shader.filepath.split("\\")[-1])],
                     (), ("mirror_%s" % mirror_index, ), verts, tris))

        mirror_index += 1

    return jms_models


def make_fog_plane_jms_models(fog_planes, nodes, make_fans=True, optimize=False):
    jms_models = []
    materials = [JmsMaterial("+unused$", "<none>", "+unused$")]

    plane_index = 0
    for fog_plane in fog_planes:
        tris = edge_loop_to_tris(
            len(fog_plane.vertices.STEPTREE), make_fan=make_fans)
        verts = [
            JmsVertex(0, vert[0] * 100, vert[1] * 100, vert[2] * 100, tex_v=1.0)
            for vert in fog_plane.vertices.STEPTREE
            ]


        jms_model = JmsModel(
            "bsp", 0, nodes, materials, (),
            ("fog_plane_%s" % plane_index, ), verts, tris)

        if optimize:
            jms_model.optimize_geometry(True)

        jms_models.append(jms_model)
        plane_index += 1

    return jms_models


def make_cluster_portal_jms_models(planes, clusters, cluster_portals, nodes,
                                   make_fans=True, optimize=False):
    jms_models = []
    materials = [
        JmsMaterial("+portal", "<none>", "+portal"),
        JmsMaterial("+portal&", "<none>", "+portal&")
        ]
    materials[1].properties = ""

    cluster_index = 0
    portals_seen = set()
    verts = []
    tris = []
    for cluster in clusters:
        for portal_index in cluster.portals.STEPTREE:
            if portal_index[0] in portals_seen:
                continue

            portals_seen.add(portal_index[0])
            portal = cluster_portals[portal_index[0]]
            shader = 1 if portal.flags.ai_cant_hear_through_this else 0
            portal_plane = planes[portal.plane_index]

            tris.extend(edge_loop_to_tris(
                len(portal.vertices.STEPTREE), mat_id=shader,
                base=len(verts), make_fan=make_fans)
                )
            verts.extend(
                JmsVertex(0, vert[0] * 100, vert[1] * 100, vert[2] * 100, tex_v=1.0)
                for vert in portal.vertices.STEPTREE
                )

    jms_model = JmsModel(
        "bsp", 0, nodes, materials, (),
        ("cluster_portals", ), verts, tris)

    if optimize:
        jms_model.optimize_geometry(True)

    jms_models.append(jms_model)
    return jms_models


def make_weather_polyhedra_jms_models(polyhedras, nodes, make_fans=True,
                                      tolerance=0.0000001):
    jms_models = []
    materials = [JmsMaterial("+weatherpoly", "<none>", "+weatherpoly")]

    polyhedra_index = 0
    for polyhedra in polyhedras:
        verts, tris = planes_to_verts_and_tris(
            polyhedra.planes.STEPTREE, polyhedra.bounding_sphere_center,
            make_fans=make_fans,
            round_adjust=Ray(polyhedra.bounding_sphere_center).mag * tolerance)

        jms_models.append(JmsModel(
            "bsp", 0, nodes, materials, (),
            ("weather_polyhedra_%s" % polyhedra_index, ), verts, tris))

        polyhedra_index += 1

    return jms_models


def make_bsp_coll_jms_models(bsps, materials, nodes, node_transforms=(),
                             ignore_flags=False, make_fans=True):
    jms_models = []
    bsp_index = 0
    for bsp in bsps:
        coll_edge_loops = get_bsp_surface_edge_loops(bsp, ignore_flags)
        node_transform = node_transforms[bsp_index] if node_transforms else None

        coll_materials = []
        mat_info_to_mat_id = {}
        # create materials from the provided materials and the
        # info on the collision properties of each surface.
        for mat_info in coll_edge_loops:
            src_material = materials[mat_info[0]]
            material = JmsMaterial(src_material.name)
            if not ignore_flags:
                if len(mat_info) > 1: material.double_sided = mat_info[1]
                if len(mat_info) > 2: material.large_collideable = mat_info[2]
                if len(mat_info) > 3: material.ladder = mat_info[3]
                if len(mat_info) > 4: material.breakable = mat_info[4]
                material.collision_only = not material.large_collideable
                material.double_sided &= not material.large_collideable
                material.name = material.name + material.properties
                material.shader_path = material.shader_path + material.properties
                material.properties = ""

            mat_info_to_mat_id[mat_info] = len(coll_materials)
            coll_materials.append(material)

        verts = make_bsp_jms_verts(bsp, node_transform)

        tri_count = 0
        # figure out how many triangles we'll be creating
        for mat_info in coll_edge_loops:
            for edge_loop in coll_edge_loops[mat_info]:
                tri_count += len(edge_loop) - 2

        tri_index = 0
        tris = [None] * tri_count
        # create triangles from the edge loops
        for mat_info in coll_edge_loops:
            mat_id = mat_info_to_mat_id[mat_info]
            for edge_loop in coll_edge_loops[mat_info]:
                loop_tris = edge_loop_to_tris(
                    edge_loop, mat_id=mat_id, make_fan=make_fans)
                tris[tri_index: tri_index + len(loop_tris)] = loop_tris
                tri_index += len(loop_tris)

        jms_models.append(
            JmsModel("bsp", 0, nodes, coll_materials, [],
                     ("collision_%s" % bsp_index, ), verts, tris))
        bsp_index += 1

    return jms_models


def make_bsp_lightmap_jms_models(sbsp_body, base_nodes):
    jms_models = []

    lightmaps = sbsp_body.lightmaps.STEPTREE
    all_tris = sbsp_body.surfaces.STEPTREE

    shader_index_by_mat_name = {}
    shader_mats = []
    for i in range(len(lightmaps)):
        lm_index = lightmaps[i].bitmap_index
        if lm_index not in shader_index_by_mat_name and lm_index >= 0:
            shader_index_by_mat_name[lm_index] = len(shader_index_by_mat_name)
            shader_mats.append(JmsMaterial("lightmap_%s" % lm_index))

    uncomp_vert_xyz_unpacker = PyStruct("<3f").unpack_from
    uncomp_vert_ijkuv_unpacker = PyStruct("<5f").unpack_from

    for lightmap in lightmaps:
        verts = []
        tris = []
        mat_index = shader_index_by_mat_name.get(lightmap.bitmap_index, -1)
        if mat_index < 0:
            continue

        for material in lightmap.materials.STEPTREE:
            v_base = len(verts)
            tris.extend(
                JmsTriangle(
                    0, mat_index,
                    tri[0] + v_base, tri[2] + v_base, tri[1] + v_base)
                for tri in all_tris[
                    material.surfaces: material.surfaces + material.surface_count]
                )

            vert_off = 0
            lm_vert_off = 56 * material.vertices_count
            vert_data = material.uncompressed_vertices.data
            for i in range(material.lightmap_vertices_count):
                x, y, z = uncomp_vert_xyz_unpacker(vert_data, vert_off)
                i, j, k, u, v = uncomp_vert_ijkuv_unpacker(vert_data, lm_vert_off)
                vert_off += 56
                lm_vert_off += 20
                verts.append(
                    JmsVertex(0, x * 100, y * 100, z * 100,
                              i, j, k, -1, 0, u, 1 - v)
                )

        jms_models.append(
            JmsModel("bsp", 0, base_nodes, shader_mats, [],
                     ("lightmap_%s" % lightmap.bitmap_index, ), verts, tris))

    return jms_models


def make_bsp_renderable_jms_models(sbsp_body, base_nodes):
    jms_models = []

    lightmaps = sbsp_body.lightmaps.STEPTREE
    all_tris = sbsp_body.surfaces.STEPTREE

    shader_index_by_mat_name = {}
    mat_indices_by_mat_name = {}
    shader_mats = []
    for i in range(len(lightmaps)):
        materials = lightmaps[i].materials.STEPTREE
        for j in range(len(materials)):
            material = materials[j]
            mat_name = PureWindowsPath(material.shader.filepath).name.lower()
            mat_name += "!$" if material.flags.fog_plane else "!"

            if mat_name not in mat_indices_by_mat_name:
                shader_index_by_mat_name[mat_name] = len(shader_mats)
                shader_mats.append(JmsMaterial(mat_name))
                mat_indices_by_mat_name[mat_name] = []
                shader_mats[-1].shader_path = (shader_mats[-1].shader_path +
                                               shader_mats[-1].properties)
                shader_mats[-1].properties = ""

            mat_indices_by_mat_name[mat_name].append((i, j))

    uncomp_vert_unpacker = PyStruct("<14f").unpack_from
    for mat_name in sorted(mat_indices_by_mat_name):
        verts = []
        tris = []
        for i, j in mat_indices_by_mat_name[mat_name]:
            material = lightmaps[i].materials.STEPTREE[j]

            mat_index = shader_index_by_mat_name.get(mat_name)
            if mat_index is None:
                continue

            vert_data = material.uncompressed_vertices.data
            v_base = len(verts)

            tris.extend(
                JmsTriangle(
                    0, mat_index,
                    tri[0] + v_base, tri[2] + v_base, tri[1] + v_base)
                for tri in all_tris[
                    material.surfaces: material.surfaces + material.surface_count]
                )

            for i in range(0, material.vertices_count * 56, 56):
                x, y, z, ni, nj, nk, bi, bj, bk, ti, tj, tk, u, v =\
                   uncomp_vert_unpacker(vert_data, i)
                verts.append(
                    JmsVertex(0, x * 100, y * 100, z * 100,
                              ni, nj, nk, -1, 0, u, 1 - v, 0,
                              bi, bj, bk, ti, tj, tk)
                )

        jms_models.append(
            JmsModel("bsp", 0, base_nodes, shader_mats, [],
                     ("renderable", ), verts, tris))

    return jms_models


def sbsp_to_mod2(
        sbsp_path, include_lens_flares=True, include_markers=True,
        include_weather_polyhedra=True, include_fog_planes=True,
        include_portals=True, include_collision=True, include_renderable=True,
        include_mirrors=True, include_lightmaps=True, fan_weather_polyhedra=True,
        fan_fog_planes=True,  fan_portals=True, fan_collision=True,
        fan_mirrors=True, optimize_fog_planes=False, optimize_portals=False,
        weather_polyhedra_tolerance=0.0000001):

    print("    Loading sbsp tag...")
    sbsp_tag = sbsp_def.build(filepath=sbsp_path)
    mod2_tag = mod2_def.build()

    sbsp_body = sbsp_tag.data.tagdata
    coll_mats = [JmsMaterial(mat.shader.filepath.split("\\")[-1])
                 for mat in sbsp_body.collision_materials.STEPTREE]

    base_nodes = [JmsNode("frame")]
    jms_models = []

    if include_markers:
        print("    Converting markers...")
        try:
            jms_models.append(make_marker_jms_model(
                sbsp_body.markers.STEPTREE, base_nodes))
        except Exception:
            print(format_exc())
            print("    Could not convert markers")

    if include_lens_flares:
        print("    Converting lens flares...")
        try:
            jms_models.append(make_lens_flare_jms_model(
                sbsp_body.lens_flare_markers.STEPTREE,
                sbsp_body.lens_flares.STEPTREE, base_nodes))
        except Exception:
            print(format_exc())
            print("    Could not convert lens flares")

    if include_fog_planes:
        print("    Converting fog planes...")
        try:
            jms_models.extend(make_fog_plane_jms_models(
                sbsp_body.fog_planes.STEPTREE, base_nodes,
                fan_fog_planes, optimize_fog_planes))
        except Exception:
            print(format_exc())
            print("    Could not convert fog planes")

    if include_mirrors:
        print("    Converting mirrors...")
        try:
            jms_models.extend(make_mirror_jms_models(
                sbsp_body.clusters.STEPTREE, base_nodes, fan_mirrors))
        except Exception:
            print(format_exc())
            print("    Could not convert mirrors")

    if include_portals and sbsp_body.collision_bsp.STEPTREE:
        print("    Converting portals...")
        try:
            jms_models.extend(make_cluster_portal_jms_models(
                sbsp_body.collision_bsp.STEPTREE[0].planes.STEPTREE,
                sbsp_body.clusters.STEPTREE, sbsp_body.cluster_portals.STEPTREE,
                base_nodes, fan_portals, optimize_portals))
        except Exception:
            print(format_exc())
            print("    Could not convert portals")

    if include_weather_polyhedra:
        print("    Converting weather polyhedra...")
        try:
            jms_models.extend(make_weather_polyhedra_jms_models(
                sbsp_body.weather_polyhedras.STEPTREE, base_nodes,
                fan_weather_polyhedra, weather_polyhedra_tolerance))
        except Exception:
            print(format_exc())
            print("    Could not convert weather polyhedra")

    if include_collision:
        print("    Converting collision...")
        try:
            jms_models.extend(make_bsp_coll_jms_models(
                sbsp_body.collision_bsp.STEPTREE, coll_mats, base_nodes,
                None, False, fan_collision))
        except Exception:
            print(format_exc())
            print("    Could not convert collision")

    if include_renderable:
        print("    Converting renderable...")
        try:
            jms_models.extend(
                make_bsp_renderable_jms_models(sbsp_body, base_nodes))
        except Exception:
            print(format_exc())
            print("    Could not convert renderable")

    if include_lightmaps:
        print("    Converting lightmaps...")
        try:
            jms_models.extend(
                make_bsp_lightmap_jms_models(sbsp_body, base_nodes))
        except Exception:
            print(format_exc())
            print("    Could not convert lightmaps")

    print("    Compiling gbxmodel...")
    mod2_tag.filepath = str(Path(sbsp_path).with_suffix('')) + "_SBSP.gbxmodel"
    compile_gbxmodel(mod2_tag, MergedJmsModel(*jms_models), True)
    return mod2_tag


class SbspConverter(ConverterBase, window_base_class):
    src_ext = "scenario_structure_bsp"
    dst_ext = "gbxmodel"

    weather_tolerance = 0.0000001
    min_weather_tolerance = 0.000000000000001

    def __init__(self, app_root, *args, **kwargs):
        if isinstance(self, tk.Toplevel):
            kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)

        window_base_class.__init__(self, app_root, *args, **kwargs)
        ConverterBase.__init__(self, app_root, *args, **kwargs)
        self.setup_window(*args, **kwargs)

    def setup_window(self, *args, **kwargs):
        ConverterBase.setup_window(self, *args, **kwargs)

        self.include_weather_polyhedra = tk.IntVar(self, 1)
        self.include_fog_planes = tk.IntVar(self, 1)
        self.include_portals = tk.IntVar(self, 1)
        self.include_collision = tk.IntVar(self, 1)
        self.include_renderable = tk.IntVar(self, 1)
        self.include_mirrors = tk.IntVar(self, 0)
        self.include_lightmaps = tk.IntVar(self, 0)

        self.include_markers = tk.IntVar(self, 1)
        self.include_lens_flares = tk.IntVar(self, 0)

        self.fan_portals = tk.IntVar(self, 1)
        self.fan_weather_polyhedra = tk.IntVar(self, 1)
        self.fan_fog_planes = tk.IntVar(self, 1)
        self.fan_mirrors = tk.IntVar(self, 1)
        self.fan_collision = tk.IntVar(self, 1)

        self.optimize_portals = tk.IntVar(self, 0)
        self.optimize_fog_planes = tk.IntVar(self, 0)
        self.weather_tolerance_string = tk.StringVar(self, str(self.weather_tolerance))
        self.weather_tolerance_string.trace(
            "w", lambda *a, s=self: s.set_weather_tolerance())

        # make the frames
        self.include_frame = tk.LabelFrame(self, text="Geometry/markers to include")
        self.weather_tolerance_frame = tk.LabelFrame(self, text="Weather polyhedron tolerance")
        self.topology_frame = tk.LabelFrame(self, text="Topology generation")


        # Generate the important frame and its contents
        include_vars = {
            "Weather polyhedra": self.include_weather_polyhedra,
            "Fog planes": self.include_fog_planes, "Portals": self.include_portals,
            "Collidable": self.include_collision, "Renderable": self.include_renderable,
            "Mirrors": self.include_mirrors, "Lightmaps": self.include_lightmaps,
            "Markers": self.include_markers, "Lens flares": self.include_lens_flares}
        self.include_buttons = []
        for text in ("Collidable", "Portals", "Renderable",
                     "Weather polyhedra", "Fog planes", "Markers",
                     "Mirrors", "Lens flares", "Lightmaps"):
            self.include_buttons.append(tk.Checkbutton(
                self.include_frame, variable=include_vars[text], text=text))

        # Generate the topology frame and its contents
        topology_vars = {
            "Weather polyhedra": self.fan_weather_polyhedra,
            "Fog planes": self.fan_fog_planes, "Mirrors": self.fan_mirrors,
            "Portals": self.fan_portals, "Collision": self.fan_collision}
        self.topology_frames = []
        self.topology_labels = []
        self.topology_buttons = []
        for text in ("Portals", "Fog planes", "Weather polyhedra", "Mirrors", "Collision"):
            var = topology_vars[text]
            f = tk.Frame(self.topology_frame)
            name_lbl = tk.Label(f, text=text, width=17, anchor="w")
            fan_cbtn = tk.Checkbutton(
                f, variable=var, text="Triangle fan")
            strip_cbtn = tk.Checkbutton(
                f, variable=var, text="Triangle strip", onvalue=0, offvalue=1)
            self.topology_frames.append(f)
            self.topology_labels.append(name_lbl)
            self.topology_buttons.extend((fan_cbtn, strip_cbtn))
            if text == "Portals":
                self.topology_buttons.append(tk.Checkbutton(
                    f, variable=self.optimize_portals, text="Optimize"))
            elif text == "Fog planes":
                self.topology_buttons.append(tk.Checkbutton(
                    f, variable=self.optimize_fog_planes, text="Optimize"))

        self.weather_tolerance_info = tk.Label(
            self.weather_tolerance_frame, justify='left', anchor="w",
            text=("Due to how weather polyhedrons work, there is no geometry to extract, so it must be generated. \n"
                  "My method for doing this isn't perfect, so sometimes geometry will be missing faces. Adjust this\n"
                  "value to find the sweet spot. NEVER set to 0, and be wary of setting to 0.0001 or higher.\n"
                  "\tNOTE: You will probably need to manually clean up the generated geometry a bit."))
        self.weather_tolerance_spinbox = tk.Spinbox(
            self.weather_tolerance_frame, from_=self.min_weather_tolerance,
            to=100, width=25, increment=self.weather_tolerance,
            textvariable=self.weather_tolerance_string, justify="right")

        self.pack_widgets()
        self.apply_style()

    def pack_widgets(self):
        ConverterBase.pack_widgets(self)

        # pack everything
        for frame in self.topology_frames:
            frame.pack(expand=True, fill='both')

        for label in self.topology_labels:
            label.pack(anchor='w', padx=10, side='left')

        x = y = 0
        for button in self.include_buttons:
            button.grid(row=y, column=x, padx=5, pady=5, sticky="w")
            x += 1
            if x == 5:
                x = 0
                y += 1

        for button in self.topology_buttons:
            button.pack(anchor='w', padx=5, side='left')

        self.weather_tolerance_info.pack(fill='both', expand=True, padx=5, pady=5)
        self.weather_tolerance_spinbox.pack(padx=5, pady=5)

        self.include_frame.pack(expand=True, fill='both')
        self.topology_frame.pack(expand=True, fill='both')
        self.weather_tolerance_frame.pack(expand=True, fill='both')

    def lock_ui(self):
        ConverterBase.lock_ui(self)
        for w in self.include_buttons: w.config(state=tk.DISABLED)
        for w in self.topology_buttons: w.config(state=tk.DISABLED)
        self.weather_tolerance_spinbox.config(state=tk.DISABLED)

    def unlock_ui(self):
        ConverterBase.unlock_ui(self)
        for w in self.include_buttons: w.config(state=tk.NORMAL)
        for w in self.topology_buttons: w.config(state=tk.NORMAL)
        self.weather_tolerance_spinbox.config(state=tk.NORMAL)

    def set_weather_tolerance(self):
        try:
            new_tolerance = float(self.weather_tolerance_string.get())
            if new_tolerance >= self.min_weather_tolerance:
                self.weather_tolerance = new_tolerance
                return

            self.weather_tolerance = self.min_weather_tolerance
        except Exception:
            return

        self.weather_tolerance_string.set(
            str(("%.20f" % self.weather_tolerance)).rstrip("0").rstrip("."))

    def destroy(self):
        ConverterBase.destroy(self)
        window_base_class.destroy(self)

    def convert(self, tag_path=None):
        return sbsp_to_mod2(
            tag_path, self.include_lens_flares.get(),
            self.include_markers.get(), self.include_weather_polyhedra.get(),
            self.include_fog_planes.get(), self.include_portals.get(),
            self.include_collision.get(), self.include_renderable.get(),
            self.include_mirrors.get(), self.include_lightmaps.get(),
            self.fan_weather_polyhedra.get(), self.fan_fog_planes.get(),
            self.fan_portals.get(), self.fan_collision.get(), self.fan_mirrors.get(),
            self.optimize_fog_planes.get(), self.optimize_portals.get(),
            self.weather_tolerance)


if __name__ == "__main__":
    try:
        SbspConverter(None).mainloop()
        raise SystemExit(0)
    except Exception:
        print(format_exc())
        input()
