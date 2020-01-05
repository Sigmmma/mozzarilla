#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

import array
import weakref
import tkinter as tk
import tkinter.ttk as ttk

from traceback import format_exc

from reclaimer.bitmaps.meter_image import meter_image_def

from binilla.widgets.scroll_menu import ScrollMenu
from binilla.widgets.bitmap_display_frame import BitmapDisplayFrame
from binilla.widgets.field_widgets import ContainerFrame, SimpleImageFrame

try:
    import arbytmap
except ImportError:
    arbytmap = None


class MeterImageDisplayFrame(BitmapDisplayFrame):
    def __init__(self, *args, **kwargs):
        BitmapDisplayFrame.__init__(self, *args, **kwargs)
        for w in (self.hsb, self.vsb, self.root_canvas):
            w.pack_forget()

        self.preview_label = tk.Label(self, text="Bitmap preview\t")
        self.image_canvas = tk.Canvas(self, highlightthickness=0)
        self.channel_menu = ScrollMenu(self, menu_width=9, can_scroll=True,
                                       variable=self.channel_index)
        self.save_button = ttk.Button(self, width=11, text="Save as...",
                                      command=self.save_as)

        padx = self.horizontal_padx
        pady = self.horizontal_pady

        self.image_canvas.config(width=1, height=1)
        self.preview_label.pack(side='left', padx=padx, pady=pady, fill='x')
        self.channel_menu.pack(side='left', padx=padx, pady=pady)
        self.save_button.pack(side='left', padx=padx, pady=pady)
        self.image_canvas.pack(side='left', padx=padx, pady=pady,
                               fill='x', expand=True)

        self.apply_style()

    def apply_style(self, seen=None):
        BitmapDisplayFrame.apply_style(self, seen)
        self.image_canvas.config(bg=self.bitmap_canvas_bg_color)


class MeterImageFrame(SimpleImageFrame):
    display_frame_cls = MeterImageDisplayFrame

    def reload(self):
        ContainerFrame.reload(self)
        if self.image_frame and self.node:
            try:
                width = min(640, max(self.node.width, 1))
                height = min(480, max(self.node.height, 1))
                self.image_frame().change_textures(self.get_textures())
            except Exception:
                print(format_exc())
                width = height = 1
            self.image_frame().image_canvas.config(width=width, height=height)

        self.pose_fields()

    def get_textures(self):
        texture_block = []
        if self.node:
            # apparently some meter images tags have fucked endianness
            # on the dimensions and position, so these NEED to be capped
            width = min(640, max(self.node.width, 1))
            height = min(480, max(self.node.height, 1))
            tex_info = dict(width=width, height=height,
                            format=arbytmap.FORMAT_A8R8G8B8)
            pixels = bytearray(width * height * 4)
            for line in meter_image_def.build(rawdata=self.node.meter_data.data):
                off = (line.x_pos + line.y_pos * width) * 4
                pixels[off: off + line.width * 4] = line.line_data

            # need it packed otherwise channel swapping wont occur
            texture_block.append([[array.array("I", pixels)], tex_info])

        return texture_block
