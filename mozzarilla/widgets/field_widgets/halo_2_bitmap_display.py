#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

from mozzarilla.widgets.field_widgets.halo_1_bitmap_display import \
     HaloBitmapDisplayButton, HaloBitmapTagFrame



class Halo2BitmapDisplayButton(HaloBitmapDisplayButton):
    def get_base_address(self, tag):
        return 0


class Halo2BitmapTagFrame(HaloBitmapTagFrame):
    bitmap_display_button_class = Halo2BitmapDisplayButton
