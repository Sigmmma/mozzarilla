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

from pathlib import PurePath
import threadsafe_tkinter as tk

from math import sqrt
from traceback import format_exc

from reclaimer.hek.defs.mod2    import fast_mod2_def as mod2_def
from reclaimer.stubbs.defs.mode import fast_mode_def as mode_def

window_base_class = tk.Toplevel
if __name__ == "__main__":
    window_base_class = tk.Tk


def convert_model(src_tag, dst_tag, to_gbxmodel):
    src_tag_data = src_tag.data.tagdata
    dst_tag_data = dst_tag.data.tagdata

    # move the first 14 header fields from src tag into dst tag
    # (except for the flags since usually ZONER shouldnt be copied)
    dst_tag_data[1: 14] = src_tag_data[1: 14]
    for flag_name in src_tag_data.flags.NAME_MAP:
        if hasattr(dst_tag_data.flags, flag_name):
            dst_tag_data.flags[flag_name] = src_tag_data.flags[flag_name]

    # fix the fact the mode and mod2 store stuff related to lods
    # in reverse on most platforms(pc stubbs is an exception)
    if dst_tag_data.superhigh_lod_cutoff < dst_tag_data.superlow_lod_cutoff:
        tmp0 = dst_tag_data.superhigh_lod_cutoff
        tmp1 = dst_tag_data.high_lod_cutoff
        dst_tag_data.superhigh_lod_cutoff = dst_tag_data.superlow_lod_cutoff
        dst_tag_data.high_lod_cutoff      = dst_tag_data.low_lod_cutoff
        dst_tag_data.low_lod_cutoff       = tmp1
        dst_tag_data.superlow_lod_cutoff  = tmp0

        tmp0 = dst_tag_data.superhigh_lod_nodes
        tmp1 = dst_tag_data.high_lod_nodes
        dst_tag_data.superhigh_lod_nodes = dst_tag_data.superlow_lod_nodes
        dst_tag_data.high_lod_nodes      = dst_tag_data.low_lod_nodes
        dst_tag_data.low_lod_nodes       = tmp1
        dst_tag_data.superlow_lod_nodes  = tmp0

    # make all markers global ones
    if hasattr(src_tag, "globalize_local_markers"):
        src_tag.globalize_local_markers()

    # move the markers, nodes, regions, and shaders, from mode into mod2
    dst_tag_data.markers = src_tag_data.markers
    dst_tag_data.nodes = src_tag_data.nodes
    dst_tag_data.regions = src_tag_data.regions
    dst_tag_data.shaders = src_tag_data.shaders

    # give the mod2 as many geometries as the mode
    src_tag_geoms = src_tag_data.geometries.STEPTREE
    dst_tag_geoms = dst_tag_data.geometries.STEPTREE
    dst_tag_geoms.extend(len(src_tag_geoms))

    # copy the data from the src_tag_geoms into the dst_tag_geoms
    for i in range(len(dst_tag_geoms)):
        # give the dst_tag_geom as many parts as the src_tag_geom
        src_tag_parts = src_tag_geoms[i].parts.STEPTREE
        dst_tag_parts = dst_tag_geoms[i].parts.STEPTREE
        dst_tag_parts.extend(len(src_tag_parts))

        # copy the data from the src_tag_parts into the dst_tag_parts
        for j in range(len(dst_tag_parts)):
            src_tag_part = src_tag_parts[j]
            dst_tag_part = dst_tag_parts[j]

            # move the first 9 part fields from src_tag into dst_tag
            # (except for the flags since usually ZONER shouldnt be copied)
            dst_tag_part[1: 9] = src_tag_part[1: 9]

            src_local_nodes = getattr(src_tag_part, "local_nodes", None)
            dst_local_nodes = getattr(dst_tag_part, "local_nodes", None)
            if not getattr(src_tag_part.flags, "ZONER", False):
                src_local_nodes = None

            if dst_local_nodes and src_local_nodes:
                # converting from a gbxmodel with local nodes to a gbxmodel
                # with local nodes. copy the local nodes and node count
                dst_tag_part.flags.ZONER = True
                dst_tag_part.local_node_count = src_tag_part.local_node_count
                dst_tag_part.local_nodes[:] = src_local_nodes[:]
            elif src_local_nodes:
                # converting from a gbxmodel with local nodes to
                # something without them. make the nodes absolute.
                src_tag.delocalize_part_nodes(i, j)

            # move the vertices and triangles from the src_tag into the dst_tag
            dst_tag_part.triangles = src_tag_part.triangles
            dst_tag_part.uncompressed_vertices = src_tag_part.uncompressed_vertices
            dst_tag_part.compressed_vertices   = src_tag_part.compressed_vertices

            uncomp_verts = dst_tag_part.uncompressed_vertices
            comp_verts   = dst_tag_part.compressed_vertices

            if to_gbxmodel:
                # if the compressed vertices are valid or
                # the uncompressed are not then we don't have
                # any conversion to do(already uncompressed)
                if not uncomp_verts.size or comp_verts.size:
                    dst_tag.decompress_part_verts(i, j)
            elif not comp_verts.size or uncomp_verts.size:
                # the uncompressed vertices are valid or
                # the compressed are not, so we don't have
                # any conversion to do(already compressed)
                dst_tag.compress_part_verts(i, j)

    dst_tag.calc_internal_data()


class ModelConverter(ConverterBase, window_base_class):
    to_gbxmodel = True
    src_ext = "model"
    dst_ext = "gbxmodel"

    def __init__(self, app_root, *args, **kwargs):
        if isinstance(self, tk.Toplevel):
            kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)

        window_base_class.__init__(self, app_root, *args, **kwargs)
        ConverterBase.__init__(self, app_root, *args, **kwargs)
        self.setup_window(*args, **kwargs)

    def setup_window(self, *args, **kwargs):
        ConverterBase.setup_window(self, *args, **kwargs)
        self.pack_widgets()
        self.apply_style()

    def destroy(self):
        ConverterBase.destroy(self)
        window_base_class.destroy(self)

    def convert(self, tag_path):
        if self.to_gbxmodel:
            src_tag = mode_def.build(filepath=tag_path)
            dst_tag = mod2_def.build()
        else:
            src_tag = mod2_def.build(filepath=tag_path)
            dst_tag = mode_def.build()

        dst_tag.filepath = PurePath(tag_path).with_suffix("." + self.dst_ext)
        convert_model(src_tag, dst_tag, self.to_gbxmodel)
        return dst_tag


if __name__ == "__main__":
    try:
        ModelConverter(None).mainloop()
        raise SystemExit(0)
    except Exception:
        print(format_exc())
        input()
