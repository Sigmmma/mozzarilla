#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

import tkinter as tk

from binilla.widgets.binilla_widget import BinillaWidget
from binilla.widgets.bitmap_display_frame import BitmapDisplayFrame
from binilla.widgets.field_widgets import ContainerFrame, SimpleImageFrame

try:
    import arbytmap
except ImportError:
    arbytmap = None


class FontCharacterDisplayFrame(BitmapDisplayFrame, BinillaWidget):
    def __init__(self, *args, **kwargs):
        BitmapDisplayFrame.__init__(self, *args, **kwargs)
        self.labels_frame = tk.Frame(self, highlightthickness=0)
        self.preview_frame = tk.Frame(self, highlightthickness=0)

        self.font_label0 = tk.Label(self.labels_frame, text="UTF-16 character\t")
        self.font_label1 = tk.Label(self.labels_frame, text="Bitmap preview\t")

        self.preview_label = tk.Label(self.preview_frame, text="")
        self.preview_label.font_type = "font_tag_preview"
        for lbl in (self.font_label0, self.font_label1):
            lbl.config(width=30, anchor='w',
                       disabledforeground=self.text_disabled_color)

        for w in (self.hsb, self.vsb, self.root_canvas):
            w.pack_forget()

        self.image_canvas = tk.Canvas(self.preview_frame, highlightthickness=0)
        padx = self.horizontal_padx
        pady = self.horizontal_pady

        self.image_canvas.config(width=1, height=1)
        self.labels_frame.pack(fill='both', side='left')
        self.preview_frame.pack(fill='both', side='left')
        for w in (self.font_label0, self.font_label1,
                  self.preview_label, self.image_canvas):
            w.pack(fill='x', padx=padx, pady=pady)

        self.apply_style()

    def apply_style(self, seen=None):
        BitmapDisplayFrame.apply_style(self, seen)
        self.image_canvas.config(bg=self.bitmap_canvas_bg_color)


class FontCharacterFrame(SimpleImageFrame):
    display_frame_cls = FontCharacterDisplayFrame

    def reload(self):
        ContainerFrame.reload(self)
        if self.image_frame and self.node:
            node = self.node
            try:
                char_int = node.character
                char = bytes([char_int & 0xFF, char_int >> 8]).decode("utf-16-le")
                width = max(node.bitmap_width, node.character_width, 1)
                height = max(node.bitmap_height, 32)
                self.image_frame().change_textures(self.get_textures())
            except Exception:
                width = height = 1
                char = ""
            self.image_frame().preview_label.config(text=char)
            self.image_frame().image_canvas.config(width=width, height=height)

        self.pose_fields()

    def get_textures(self):
        texture_block = []
        if self.node and self.tag:
            width = min(640, max(self.node.bitmap_width, 1))
            height = min(480, max(self.node.bitmap_height, 1))
            tex_info = dict(width=width, height=height,
                            format=arbytmap.FORMAT_L8)
            pixels_count = width * height
            all_pixels = self.tag.data.tagdata.pixels.data
            pixels = all_pixels[self.node.pixels_offset:
                                self.node.pixels_offset + pixels_count]
            pixels += b'\x00' * (pixels_count - len(pixels))
            texture_block.append([[pixels], tex_info])

        return texture_block
