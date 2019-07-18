from mozzarilla.widgets.field_widgets.halo_1_bitmap_display import \
     HaloBitmapDisplayButton, HaloBitmapTagFrame



class Halo2BitmapDisplayButton(HaloBitmapDisplayButton):
    def get_base_address(self, tag):
        return 0


class Halo2BitmapTagFrame(HaloBitmapTagFrame):
    bitmap_display_button_class = Halo2BitmapDisplayButton
