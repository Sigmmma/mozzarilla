#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

import tkinter as tk
import weakref

from array import array

from binilla.widgets.scroll_menu import ScrollMenu
from binilla.widgets.field_widgets import ContainerFrame
from binilla.widgets.bitmap_display_frame import BitmapDisplayFrame,\
     BitmapDisplayButton

from reclaimer.constants import CUBEMAP_PADDING, TYPE_NAME_MAP, FORMAT_NAME_MAP

try:
    import arbytmap
except ImportError:
    arbytmap = None

try:
    from reclaimer.bitmaps.p8_palette import HALO_P8_PALETTE, STUBBS_P8_PALETTE
except ImportError:
    HALO_P8_PALETTE = STUBBS_P8_PALETTE = None

SPRITE_RECTANGLE_TAG = "SPRITE_RECTANGLE"
SPRITE_CENTER_TAG = "SPRITE_CENTER"


class HaloBitmapDisplayBase:
    cubemap_padding = CUBEMAP_PADDING

    @property
    def engine(self):
        if getattr(self.master, "engine", None):
            return self.master.engine

        return getattr(getattr(self.master, "tag_window", None), "engine", None)

    def get_p8_palette(self, tag):
        if getattr(tag, "p8_palette", None):
            return tag.p8_palette
        elif not self.engine:
            return self.master.tag_window.tag.p8_palette
        elif "stubbs" in self.engine:
            return STUBBS_P8_PALETTE
        else:
            return HALO_P8_PALETTE

    def get_base_address(self, tag):
        if tag is None:
            return 0

        for b in tag.data.tagdata.bitmaps.STEPTREE:
            if b.pixels_offset:
                return b.pixels_offset
        return 0

    def is_xbox_bitmap(self, bitmap):
        try:
            return bitmap.base_address == 1073751810
        except AttributeError:
            return False

    def get_bitmap_pixels(self, bitmap_index, tag):
        bitmap = tag.data.tagdata.bitmaps.STEPTREE[bitmap_index]
        is_xbox = self.is_xbox_bitmap(bitmap)
        is_meta_tag = not hasattr(tag, "tags_dir")

        pixel_data = tag.data.tagdata.processed_pixel_data.data
        w, h, d = bitmap.width, bitmap.height, bitmap.depth
        fmt = FORMAT_NAME_MAP[bitmap.format.data]

        off = bitmap.pixels_offset
        if is_meta_tag:
            off -= self.get_base_address(tag)

        # xbox bitmaps are stored all mip level faces first, then
        # the next mip level, whereas pc is the other way. Xbox
        # bitmaps also have padding between each mipmap and bitmap.
        mipmap_count = bitmap.mipmaps + 1
        bitmap_count = 6 if bitmap.type.enum_name == "cubemap" else 1
        i_max = bitmap_count if is_xbox else mipmap_count
        j_max = mipmap_count if is_xbox else bitmap_count
        tex_block = []
        for i in range(i_max):
            if not is_xbox: mw, mh, md = arbytmap.get_mipmap_dimensions(w, h, d, i)

            for j in range(j_max):
                if is_xbox: mw, mh, md = arbytmap.get_mipmap_dimensions(w, h, d, j)

                if fmt == arbytmap.FORMAT_P8_BUMP:
                    tex_block.append(array('B', pixel_data[off: off + mw*mh]))
                    off += len(tex_block[-1])
                else:
                    off = arbytmap.bitmap_io.bitmap_bytes_to_array(
                        pixel_data, off, tex_block, fmt, mw, mh, md)

            # skip the xbox alignment padding to get to the next texture
            if is_xbox:
                size, mod = off, self.cubemap_padding
                off += (mod - (size % mod)) % mod

        return tex_block

    def get_textures(self, tag):
        if tag is None: return ()

        bitmaps = tag.data.tagdata.bitmaps.STEPTREE
        textures = []
        for i in range(len(bitmaps)):
            b = bitmaps[i]
            typ = TYPE_NAME_MAP[0]
            fmt = FORMAT_NAME_MAP[0]
            if b.type.data in range(len(TYPE_NAME_MAP)):
                typ = TYPE_NAME_MAP[b.type.data]

            if b.format.data in range(len(FORMAT_NAME_MAP)):
                fmt = FORMAT_NAME_MAP[b.format.data]

            tex_info = dict(
                width=b.width, height=b.height, depth=b.depth,
                format=fmt, texture_type=typ,
                sub_bitmap_count=6 if typ == "CUBE" else 1,
                swizzled=b.flags.swizzled, mipmap_count=b.mipmaps,
                reswizzler="MORTON", deswizzler="MORTON")

            mipmap_count = b.mipmaps + 1
            if fmt == arbytmap.FORMAT_P8_BUMP:
                p8_palette = self.get_p8_palette(tag)
                tex_info.update(
                    palette=[p8_palette.p8_palette_32bit_packed]*mipmap_count,
                    palette_packed=True, indexing_size=8)

            tex_block = self.get_bitmap_pixels(i, tag)
            if self.is_xbox_bitmap(b) and typ == "CUBE":
                template = tuple(tex_block)
                i = 0
                for f in (0, 2, 1, 3, 4, 5):
                    for m in range(0, (b.mipmaps + 1)*6, 6):
                        tex_block[m + f] = template[i]
                        i += 1

            textures.append((tex_block, tex_info))

        return textures


class HaloBitmapDisplayFrame(BitmapDisplayFrame):
    # these mappings have the 2nd and 3rd faces swapped on pc for some reason
    cubemap_cross_mapping = (
        (-1,  1),
        ( 2,  4,  0,  5),
        (-1,  3),
        )

    def __init__(self, master, bitmap_tag=None, *args, **kwargs):
        self.bitmap_tag = bitmap_tag
        textures = kwargs.get('textures', ())
        BitmapDisplayFrame.__init__(self, master, *args, **kwargs)
        self.sequence_index = tk.IntVar(self)
        self.sprite_index   = tk.IntVar(self)

        labels = []
        labels.append(tk.Label(self.controls_frame0, text="Sequence index"))
        labels.append(tk.Label(self.controls_frame1, text="Sprite index"))
        for lbl in labels:
            lbl.config(width=15, anchor='w')

        self.sequence_menu = ScrollMenu(self.controls_frame0, menu_width=7,
                                        variable=self.sequence_index)
        self.sprite_menu = ScrollMenu(self.controls_frame1, menu_width=7,
                                      variable=self.sprite_index)

        padx = self.horizontal_padx
        pady = self.horizontal_pady
        for lbl in labels:
            lbl.pack(side='left', padx=(15, 0), pady=pady)
        self.sequence_menu.pack(side='left', padx=padx, pady=pady)
        self.sprite_menu.pack(side='left', padx=padx, pady=pady)
        self.write_trace(self.sequence_index, self.sequence_changed)
        self.write_trace(self.sprite_index,   self.sprite_changed)

        self.change_textures(textures)
        self.apply_style()

    def sequence_changed(self, *args):
        tag = self.bitmap_tag
        if tag is None:
            self.sprite_menu.set_options(())
            self.sequence_menu.set_options(("None", ))
            self.sprite_menu.sel_index = -1
            self.sequence_menu.sel_index = 0
            return

        sequence_i = self.sequence_index.get() - 1
        options = ()
        sequences = tag.data.tagdata.sequences.STEPTREE
        if sequence_i in range(len(sequences)):
            sequence = sequences[sequence_i]
            options = range(len(sequence.sprites.STEPTREE))
            if not options:
                options = range(sequence.bitmap_count)

        self.sprite_menu.set_options(options)
        self.sprite_menu.sel_index = (self.sprite_menu.max_index >= 0) - 1

    def sprite_changed(self, *args):
        self.image_canvas.delete(SPRITE_RECTANGLE_TAG)
        self.image_canvas.delete(SPRITE_CENTER_TAG)
        tag = self.bitmap_tag
        if tag is None:
            self.sprite_menu.set_options(())
            self.sequence_menu.set_options(("None", ))
            self.sprite_menu.sel_index = -1
            self.sequence_menu.sel_index = 0
            return

        data = tag.data.tagdata
        sequences = data.sequences.STEPTREE
        bitmaps   = data.bitmaps.STEPTREE

        sequence_i = self.sequence_index.get() - 1
        if sequence_i not in range(len(sequences)):
            return

        sequence = sequences[sequence_i]
        sprite_i = self.sprite_index.get()
        sprites = sequence.sprites.STEPTREE
        bitmap_index = sequence.first_bitmap_index + sprite_i
        x0, y0, x1, y1 = 0, 0, 1, 1
        rx, ry = 0.5, 0.5
        if sprite_i in range(len(sprites)):
            sprite = sprites[sprite_i]
            if sprite.bitmap_index not in range(len(bitmaps)):
                return

            bitmap_index = sprite.bitmap_index
            x0, y0, x1, y1 = sprite.left_side,  sprite.top_side,\
                             sprite.right_side, sprite.bottom_side
            rx = x0 + sprite.registration_point_x
            ry = y0 + sprite.registration_point_y
        elif bitmap_index not in range(len(bitmaps)):
            return

        if bitmap_index != self.bitmap_index.get():
            self.bitmap_menu.sel_index = bitmap_index

        bitmap = bitmaps[bitmap_index]
        mip = self.mipmap_index.get()
        w, h = max(bitmap.width>>mip, 1), max(bitmap.height>>mip, 1)
        x0, y0 = int(round(x0 * w)), int(round(y0 * h))
        x1, y1 = int(round(x1 * w)), int(round(y1 * h))
        rx, ry = int(round(rx * w)), int(round(ry * h))
        rx0, rx1 = rx - 1, rx + 1
        ry0, ry1 = ry - 1, ry + 1
        if x1 < x0: x0, x1 = x1, x0
        if y1 < y0: y0, y1 = y1, y0
        if ry1 < ry0: ry0, ry1 = ry1, ry0
        x0 -= 1; y0 -= 1
        rx0 -= 1; ry0 -= 1

        self.image_canvas.create_rectangle(
            (x0, y0, x1, y1), fill=None, dash=(2, 1),
            tags=SPRITE_RECTANGLE_TAG,
            outline=self.bitmap_canvas_outline_color)

        self.image_canvas.create_rectangle(
            (rx0, ry0, rx1, ry1), fill=None,
            tags=SPRITE_CENTER_TAG,
            outline=self.bitmap_canvas_bg_color)

    def change_textures(self, textures):
        BitmapDisplayFrame.change_textures(self, textures)
        tag = self.bitmap_tag
        if tag is None: return

        data = tag.data.tagdata
        options = {i+1: str(i) for i in range(len(data.sequences.STEPTREE))}
        options[0] = "None"

        if not (hasattr(self, "sprite_menu") and
                hasattr(self, "sequence_menu")):
            return
        self.sequence_menu.set_options(options)
        self.sequence_menu.sel_index = (self.sequence_menu.max_index >= 0) - 1


class HaloBitmapDisplayButton(HaloBitmapDisplayBase, BitmapDisplayButton):
    tags_dir = ""
    display_frame_class = HaloBitmapDisplayFrame

    def __init__(self, *args, **kwargs):
        self.tags_dir = kwargs.pop("tags_dir", self.tags_dir)
        BitmapDisplayButton.__init__(self, *args, **kwargs)

    def show_window(self, e=None, parent=None):
        w = tk.Toplevel()
        tag = self.bitmap_tag
        self.display_frame = weakref.ref(self.display_frame_class(w, tag))
        self.display_frame().change_textures(self.get_textures(self.bitmap_tag))
        self.display_frame().pack(expand=True, fill="both")

        try:
            tag_name = "untitled"
            tag_name = tag.filepath.lower()
            tag_name = tag_name.split(self.tags_dir.lower(), 1)[-1]
        except Exception:
            pass
        w.title("Preview: %s" % tag_name)
        w.transient(parent)
        w.focus_force()
        return w


class HaloBitmapTagFrame(ContainerFrame):
    bitmap_display_button_class = HaloBitmapDisplayButton

    def bitmap_preview(self, e=None):
        f = self.preview_btn.display_frame
        if f is not None and f() is not None:
            return

        try:
            tag = self.tag_window.tag
        except AttributeError:
            return
        self.preview_btn.change_bitmap(tag)
        self.preview_btn.show_window(None, self.tag_window.app_root)

    def pose_fields(self):
        try:
            tags_dir = self.tag_window.tag.tags_dir
        except AttributeError:
            tags_dir = ""
        self.preview_btn = self.bitmap_display_button_class(
            self, width=15, text="Preview",
            tags_dir=tags_dir, command=self.bitmap_preview,)

        self.preview_btn.pack(anchor='center', pady=10)
        ContainerFrame.pose_fields(self)
