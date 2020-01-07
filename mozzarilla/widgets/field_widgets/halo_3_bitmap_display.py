#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

from binilla.widgets.bitmap_display_frame import BitmapDisplayFrame
from mozzarilla.widgets.field_widgets.halo_1_bitmap_display import \
     HaloBitmapDisplayFrame, HaloBitmapDisplayButton, HaloBitmapTagFrame
from reclaimer.constants import TYPE_NAME_MAP, FORMAT_NAME_MAP
from reclaimer.h3.util import get_virtual_dimension, get_h3_pixel_bytes_size

try:
    import arbytmap
except ImportError:
    arbytmap = None


class Halo3BitmapDisplayFrame(HaloBitmapDisplayFrame):
    cubemap_cross_mapping = BitmapDisplayFrame.cubemap_cross_mapping

    def _display_2d_bitmap(self, force=False, bitmap_mapping=None):
        image_ct = len(self.get_images())
        if bitmap_mapping is None and self.active_image_handler.tex_type == "2D":
            bitmap_mapping = []
            column_ct = image_ct // 4
            for i in range(4 * (column_ct > 1)):
                bitmap_mapping.append(list(i * column_ct + j for
                                           j in range(column_ct)))

            if column_ct * 4 < image_ct:
                bitmap_mapping.append(list(range(column_ct * 4, image_ct)))

        HaloBitmapDisplayFrame._display_2d_bitmap(self, force, bitmap_mapping)


class Halo3BitmapDisplayButton(HaloBitmapDisplayButton):
    display_frame_class = Halo3BitmapDisplayFrame

    def get_base_address(self, tag):
        return 0

    def get_bitmap_pixels(self, bitmap_index, tag):
        bitmap = tag.data.tagdata.bitmaps.STEPTREE[bitmap_index]
        is_meta_tag = not hasattr(tag, "tags_dir")

        off = bitmap.pixels_offset
        pixel_data = tag.data.tagdata.processed_pixel_data.data

        w, h, d = bitmap.width, bitmap.height, bitmap.depth
        tiled = bitmap.format_flags.tiled
        fmt = FORMAT_NAME_MAP[bitmap.format.data]

        # xbox bitmaps are stored all mip level faces first, then
        # the next mip level, whereas pc is the other way. Xbox
        # bitmaps also have padding between each mipmap and bitmap.
        bitmap_count = 1
        mipmap_count = bitmap.mipmaps + 1
        if bitmap.type.enum_name == "cubemap":
            bitmap_count = 6
        elif bitmap.type.enum_name == "multipage_2d":
            bitmap_count = d
            d = 1

        tex_block = []
        if fmt == arbytmap.FORMAT_P8_BUMP:
            fmt = arbytmap.FORMAT_A8

        for i in range(mipmap_count):
            pixel_data_size = get_h3_pixel_bytes_size(fmt, w, h, d, i, tiled)
            for j in range(bitmap_count):
                off = arbytmap.bitmap_io.bitmap_bytes_to_array(
                    pixel_data, off, tex_block, fmt,
                    1, 1, 1, pixel_data_size)

        return tex_block

    def get_textures(self, tag):
        textures = HaloBitmapDisplayButton.get_textures(self, tag)

        bitmaps = tag.data.tagdata.bitmaps.STEPTREE
        for i in range(len(bitmaps)):
            bitmap = bitmaps[i]
            tex_info = textures[i][1]

            if bitmap.type.enum_name == "multipage_2d":
                tex_info.update(depth=1, texture_type=TYPE_NAME_MAP[0],
                                sub_bitmap_count=tex_info["depth"])

            # update the texture info
            tex_info.update(
                packed_width_calc=get_virtual_dimension,
                packed_height_calc=get_virtual_dimension,
                target_packed_width_calc=get_virtual_dimension,
                target_packed_height_calc=get_virtual_dimension,
                big_endian=True, target_big_endian=True,
                tiled=bitmap.format_flags.tiled,
                tile_mode=False, tile_method="DXGI")

        return textures


class Halo3BitmapTagFrame(HaloBitmapTagFrame):
    bitmap_display_button_class = Halo3BitmapDisplayButton
