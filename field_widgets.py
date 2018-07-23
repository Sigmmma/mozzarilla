import tkinter as tk
import reclaimer

from array import array
from os.path import dirname, exists, splitext
from tkinter.filedialog import askopenfilename, asksaveasfilename
from traceback import format_exc

from supyr_struct.field_types import UInt8
from supyr_struct.defs.frozen_dict import FrozenDict
from supyr_struct.buffer import get_rawdata
from supyr_struct.defs.audio.wav import wav_def
from supyr_struct.defs.util import *
from binilla import editor_constants
from binilla.field_widgets import *
from binilla.widgets import *

from reclaimer.h2.constants import *

try:
    import arbytmap
    from reclaimer.hek.defs.objs.bitm import P8_PALETTE
except ImportError:
    pass


channel_name_map   = FrozenDict(a='alpha', r='red', g='green', b='blue')
channel_offset_map = FrozenDict(a=24,      r=16,    g=8,       b=0)


def extract_color(chan_char, node):
    return (node >> channel_offset_map[chan_char]) & 0xFF


def inject_color(chan_char, new_val, parent, attr_index):
    off = channel_offset_map[chan_char]
    node = parent[attr_index]
    node = (node & (0xFFFFFFFF - (0xFF << off))) + ((new_val & 0xFF) << off)
    parent[attr_index] = node


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
            lbl.config(width=15, anchor='w',
                       bg=self.default_bg_color, fg=self.text_normal_color,
                       disabledforeground=self.text_disabled_color)

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
        self.image_canvas.delete("SPRITE_RECTANGLE")
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
        if sprite_i in range(len(sprites)):
            sprite = sprites[sprite_i]
            if sprite.bitmap_index not in range(len(bitmaps)):
                return

            bitmap_index = sprite.bitmap_index
            x0, y0, x1, y1 = sprite.left_side,  sprite.top_side,\
                             sprite.right_side, sprite.bottom_side
        elif bitmap_index not in range(len(bitmaps)):
            return

        if bitmap_index != self.bitmap_index.get():
            self.bitmap_menu.sel_index = bitmap_index

        bitmap = bitmaps[bitmap_index]
        mip = self.mipmap_index.get()
        w, h = max(bitmap.width>>mip, 1), max(bitmap.height>>mip, 1)
        x0, y0 = int(round(x0 * w)), int(round(y0 * h))
        x1, y1 = int(round(x1 * w)), int(round(y1 * h))
        if x1 < x0: x0, x1 = x1, x0
        if y1 < y0: y0, y1 = y1, y0
        x0 -= 1; y0 -= 1

        self.image_canvas.create_rectangle(
            (x0, y0, x1, y1), fill=None, dash=(2, 1), tags="SPRITE_RECTANGLE",
            outline=self.bitmap_canvas_outline_color)

    def change_textures(self, textures):
        if not (hasattr(self, "sprite_menu") and
                hasattr(self, "sequence_menu")):
            return

        BitmapDisplayFrame.change_textures(self, textures)
        tag = self.bitmap_tag
        if tag is None: return

        data = tag.data.tagdata
        options = {i+1: str(i) for i in range(len(data.sequences.STEPTREE))}
        options[0] = "None"
        self.sequence_menu.set_options(options)
        self.sequence_menu.sel_index = (self.sequence_menu.max_index >= 0) - 1

    
class HaloBitmapDisplayBase:
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

    def get_textures(self, tag):
        if tag is None: return ()

        textures = []
        is_meta_tag = not hasattr(tag, "tags_dir")

        get_mip_dims = arbytmap.get_mipmap_dimensions
        pixels_base  = self.get_base_address(tag)
        pixel_data = tag.data.tagdata.processed_pixel_data.data
        bitmaps    = tag.data.tagdata.bitmaps.STEPTREE

        for i in range(len(bitmaps)):
            b = bitmaps[i]
            is_xbox = self.is_xbox_bitmap(b)
            tex_block = []
            w, h, d = b.width, b.height, b.depth
            typ = TYPE_NAME_MAP[b.type.data]
            fmt = FORMAT_NAME_MAP[b.format.data]
            tex_info = dict(
                width=w, height=h, depth=d, format=fmt, texture_type=typ,
                swizzled=b.flags.swizzled, mipmap_count=b.mipmaps,
                reswizzler="MORTON", deswizzler="MORTON")

            mipmap_count = b.mipmaps + 1
            bitmap_count = 6 if typ == "CUBE" else 1
            if fmt == arbytmap.FORMAT_P8:
                tex_info.update(
                    palette=[P8_PALETTE.p8_palette_32bit_packed]*mipmap_count,
                    palette_packed=True, indexing_size=8)

            # xbox bitmaps are stored all mip level faces first, then
            # the next mip level, whereas pc is the other way. Xbox
            # bitmaps also have padding between each mipmap and bitmap.
            j_max = bitmap_count if is_xbox else mipmap_count
            k_max = mipmap_count if is_xbox else bitmap_count
            off   = b.pixels_offset
            if is_meta_tag:
                off -= pixels_base

            for j in range(j_max):
                start_off = 0
                if not is_xbox: mw, mh, md = get_mip_dims(w, h, d, j)

                for k in range(k_max):
                    if is_xbox: mw, mh, md = get_mip_dims(w, h, d, k)

                    if fmt == arbytmap.FORMAT_P8:
                        tex_block.append(
                            array('B', pixel_data[off: off + mw*mh]))
                        off += len(tex_block[-1])
                    else:
                        off = arbytmap.bitmap_io.bitmap_bytes_to_array(
                            pixel_data, off, tex_block, fmt, mw, mh, md)

                # skip the xbox alignment padding to get to the next texture
                if is_xbox:
                    size, mod = off - start_off, CUBEMAP_PADDING
                    off += (mod - (size % mod))%mod

            if is_xbox and b.type.enum_name == "cubemap":
                template = tuple(tex_block)
                j = 0
                for f in (0, 2, 1, 3, 4, 5):
                    for m in range(0, (b.mipmaps + 1)*6, 6):
                        tex_block[m + f] = template[j]
                        j += 1

            tex_info['sub_bitmap_count'] = bitmap_count
            textures.append((tex_block, tex_info))

        return textures


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


class Halo2BitmapDisplayButton(HaloBitmapDisplayButton):
    def get_base_address(self, tag):
        return 0


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
            self, width=15, text="Preview", bd=self.button_depth,
            tags_dir=tags_dir, command=self.bitmap_preview,
            bg=self.button_color, fg=self.text_normal_color,
            activebackground=self.button_color,
            disabledforeground=self.text_disabled_color)

        self.preview_btn.pack(anchor='center', pady=10)
        ContainerFrame.pose_fields(self)


class Halo2BitmapTagFrame(HaloBitmapTagFrame):
    bitmap_display_button_class = Halo2BitmapDisplayButton


class HaloColorEntry(NumberEntryFrame):

    def flush(self, *args):
        if self._flushing or not self.needs_flushing:
            return

        try:
            self._flushing = True
            node = self.node
            unit_scale = self.unit_scale
            curr_val = self.entry_string.get()
            try:
                new_node = self.parse_input()
            except Exception:
                # Couldnt cast the string to the node class. This is fine this
                # kind of thing happens when entering data. Just dont flush it
                try: self.entry_string.set(curr_val)
                except Exception: pass
                self._flushing = False
                self.set_needs_flushing(False)
                return

            str_node = str(new_node)

            # dont need to flush anything if the nodes are the same
            if node != new_node:
                # make an edit state
                self.edit_create(undo_node=node, redo_node=new_node)

                self.last_flushed_val = str_node
                self.node = new_node
                f_parent = self.f_widget_parent
                inject_color(self.attr_index, new_node,
                             f_parent.parent, f_parent.attr_index)
                self.f_widget_parent.reload()

            # value may have been clipped, so set the entry string anyway
            self.entry_string.set(str_node)

            self._flushing = False
            self.set_needs_flushing(False)
        except Exception:
            # an error occurred so replace the entry with the last valid string
            self._flushing = False
            self.set_needs_flushing(False)
            raise

    def edit_create(self, **kwargs):
        kwargs['attr_index'] = self.f_widget_parent.attr_index
        kwargs['parent']     = self.f_widget_parent.parent
        kwargs['channel']    = self.attr_index
        FieldWidget.edit_create(self, **kwargs)

    def edit_apply(self=None, *, edit_state, undo=True):
        attr_index = edit_state.attr_index

        w_parent, parent = FieldWidget.get_widget_and_node(
            nodepath=edit_state.nodepath, tag_window=edit_state.tag_window)

        node = edit_state.redo_node
        if undo:
            node = edit_state.undo_node
        inject_color(edit_state.edit_info['channel'],
                     node, parent, edit_state.attr_index)

        if w_parent is not None:
            try:
                w = w_parent.f_widgets[
                    w_parent.f_widget_ids_map[attr_index]]

                w.needs_flushing = False
                w.reload()
                w.set_edited()
            except Exception:
                print(format_exc())


class HaloUInt32ColorPickerFrame(ColorPickerFrame):
    color_descs = dict(
        a=UInt8("a"),
        r=UInt8("r"),
        g=UInt8("g"),
        b=UInt8("b")
        )

    def __init__(self, *args, **kwargs):
        FieldWidget.__init__(self, *args, **kwargs)
        kwargs.update(relief='flat', bd=0, highlightthickness=0,
                      bg=self.default_bg_color)
        if self.f_widget_parent is None:
            self.pack_padx = self.pack_pady = 0

        tk.Frame.__init__(self, *args, **fix_kwargs(**kwargs))

        self._initialized = True
        self.populate()

    @property
    def visible_field_count(self):
        try:
            return len(self.desc["COLOR_CHANNELS"])
        except (IndexError, KeyError, AttributeError):
            return 0

    def edit_create(self, **kwargs):
        kwargs['attr_index'] = self.attr_index
        FieldWidget.edit_create(self, **kwargs)

    def edit_apply(self=None, *, edit_state, undo=True):
        state = edit_state
        attr_index = state.attr_index
        w, parent = FieldWidget.get_widget_and_node(nodepath=state.nodepath,
                                                    tag_window=state.tag_window)
        try:
            w = w.f_widgets[w.f_widget_ids_map[attr_index]]
        except Exception:
            pass

        nodes = state.redo_node
        if undo:
            nodes = state.undo_node

        inject_color('a', int(nodes['a'] * 255.0 + 0.5), parent, attr_index)
        inject_color('r', int(nodes['r'] * 255.0 + 0.5), parent, attr_index)
        inject_color('g', int(nodes['g'] * 255.0 + 0.5), parent, attr_index)
        inject_color('b', int(nodes['b'] * 255.0 + 0.5), parent, attr_index)

        if w is not None:
            try:
                if w.desc is not state.desc:
                    return

                w.node = parent[attr_index]
                w.needs_flushing = False
                w.reload()
                w.set_edited()
            except Exception:
                print(format_exc())

    def reload(self):
        self.node = self.parent[self.attr_index]
        if hasattr(self, 'color_btn'):
            if self.disabled:
                self.color_btn.config(state=tk.DISABLED)
            else:
                self.color_btn.config(state=tk.NORMAL)

            self.color_btn.config(bg=self.get_color()[1])

        f_widgets = self.f_widgets
        f_widget_ids_map = self.f_widget_ids_map
        for chan_char in self.desc['COLOR_CHANNELS']:
            chan = channel_name_map[chan_char]
            w = f_widgets[f_widget_ids_map[chan]]
            w.node = int(getattr(self, chan) * 255.0 + 0.5)
            w.reload()

    def populate(self):
        content = self
        if hasattr(self, 'content'):
            content = self.content
        if content in (None, self):
            content = tk.Frame(self, relief="sunken", bd=0,
                               highlightthickness=0, bg=self.default_bg_color)

        self.content = content
        # clear the f_widget_ids list
        del self.f_widget_ids[:]
        del self.f_widget_ids_map
        del self.f_widget_ids_map_inv

        f_widget_ids = self.f_widget_ids
        f_widget_ids_map = self.f_widget_ids_map = {}
        f_widget_ids_map_inv = self.f_widget_ids_map_inv = {}

        # destroy all the child widgets of the content
        if isinstance(self.f_widgets, dict):
            for c in list(self.f_widgets.values()):
                c.destroy()

        self.display_comment(self)

        try: title_font = self.tag_window.app_root.default_font
        except AttributeError: title_font = None
        self.title_label = tk.Label(
            self, anchor='w', justify='left', font=title_font,
            width=self.title_size, text=self.gui_name,
            bg=self.default_bg_color, fg=self.text_normal_color)
        self.title_label.pack(fill="x", side="left")

        node = self.node
        desc = self.desc
        self.title_label.tooltip_string = self.tooltip_string = desc.get('TOOLTIP')

        for chan_char in desc['COLOR_CHANNELS']:
            chan = channel_name_map[chan_char]
            node_val = int(getattr(self, chan) * 255.0 + 0.5)
            # make an entry widget for each color channel
            w = HaloColorEntry(self.content, f_widget_parent=self,
                               desc=self.color_descs[chan_char],
                               node=node_val, vert_oriented=False,
                               tag_window=self.tag_window, attr_index=chan_char)

            wid = id(w)
            f_widget_ids.append(wid)
            f_widget_ids_map[chan] = wid
            f_widget_ids_map_inv[wid] = chan
            if self.tooltip_string:
                w.tooltip_string = self.tooltip_string

        self.color_btn = tk.Button(
            self.content, width=4, command=self.select_color,
            bd=self.button_depth, bg=self.get_color()[1])

        if self.disabled:
            self.color_btn.config(state=tk.DISABLED)
        else:
            self.color_btn.config(state=tk.NORMAL)

        self.build_f_widget_cache()
        self.pose_fields()

    def pose_fields(self):
        ContainerFrame.pose_fields(self)
        self.color_btn.pack(side='left')

    @property
    def alpha(self):
        return extract_color('a', self.node) / 255.0

    @alpha.setter
    def alpha(self, new_val):
        inject_color('a', int(new_val * 255.0 + 0.5),
                     self.parent, self.attr_index)
        self.node = self.parent[self.attr_index]

    @property
    def red(self):
        return extract_color('r', self.node) / 255.0

    @red.setter
    def red(self, new_val):
        inject_color('r', int(new_val * 255.0 + 0.5),
                     self.parent, self.attr_index)
        self.node = self.parent[self.attr_index]

    @property
    def green(self):
        return extract_color('g', self.node) / 255.0

    @green.setter
    def green(self, new_val):
        inject_color('g', int(new_val * 255.0 + 0.5),
                     self.parent, self.attr_index)
        self.node = self.parent[self.attr_index]

    @property
    def blue(self):
        return extract_color('b', self.node) / 255.0

    @blue.setter
    def blue(self, new_val):
        inject_color('b', int(new_val * 255.0 + 0.5),
                     self.parent, self.attr_index)
        self.node = self.parent[self.attr_index]


class DependencyFrame(ContainerFrame):

    def browse_tag(self):
        try:
            try:
                tags_dir = self.tag_window.tag.tags_dir
            except AttributeError as e:
                return
            if not tags_dir.endswith(PATHDIV):
                tags_dir += PATHDIV

            init_dir = tags_dir
            try: init_dir = tags_dir + dirname(self.node.filepath)
            except Exception: pass

            filetypes = []
            for ext in sorted(self.node.tag_class.NAME_MAP):
                if ext == 'NONE':
                    continue
                filetypes.append((ext, '*.%s' % ext))
            if len(filetypes) > 1:
                filetypes = (('All', '*'),) + tuple(filetypes)
            else:
                filetypes.append(('All', '*'))

            filepath = askopenfilename(
                initialdir=init_dir, filetypes=filetypes,
                title="Select a tag", parent=self)

            if not filepath:
                return

            filepath = sanitize_path(filepath)
            tag_path, ext = splitext(filepath.lower().split(tags_dir.lower())[-1])
            orig_tag_class = self.node.tag_class.__copy__()
            try:
                self.node.tag_class.set_to(ext[1:])
            except Exception:
                self.node.tag_class.set_to('NONE')
                for filetype in filetypes:
                    ext = filetype[1][1:]
                    if exists(tags_dir + tag_path + ext):
                        self.node.tag_class.set_to(ext[1:])
                        break

            self.edit_create(
                attr_index=('tag_class', 'filepath'),
                redo_node=dict(
                    tag_class=self.node.tag_class, filepath=tag_path),
                undo_node=dict(
                    tag_class=orig_tag_class, filepath=self.node.filepath))

            self.node.filepath = tag_path
            self.set_edited()
            self.reload()
        except Exception:
            print(format_exc())

    def open_tag(self):
        t_w = self.tag_window
        try:
            tag, app = t_w.tag, t_w.app_root
        except AttributeError:
            return

        cur_handler = app.handler
        new_handler = t_w.handler

        try:
            tags_dir = tag.tags_dir
            if not tags_dir.endswith(PATHDIV):
                tags_dir += PATHDIV

            self.flush()
            if not self.node.filepath:
                return

            ext = '.' + self.node.tag_class.enum_name
            filepath = tags_dir + self.node.filepath
            try:
                if (new_handler.treat_mode_as_mod2 and
                    ext == '.model' and not exists(filepath + ext)):
                    ext = '.gbxmodel'
            except AttributeError:
                pass

            app.set_handler(new_handler)
            app.load_tags(filepaths=filepath + ext)
        except Exception:
            print(format_exc())
        finally:
            app.set_handler(cur_handler)

    def get_dependency_tag(self):
        t_w = self.tag_window
        try:
            tags_dir, app, handler = t_w.tag.tags_dir,\
                                     t_w.app_root, t_w.handler
        except AttributeError:
            return

        try:
            if not tags_dir.endswith(PATHDIV):
                tags_dir += PATHDIV

            self.flush()
            if not self.node.filepath:
                return

            ext = '.' + self.node.tag_class.enum_name
            filepath = tags_dir + self.node.filepath
            try:
                if (handler.treat_mode_as_mod2 and
                    ext == '.model' and not exists(filepath + ext)):
                    ext = '.gbxmodel'
            except AttributeError:
                pass
        except Exception:
            print(format_exc())

        try:
            tag = handler.get_tag(filepath + ext)
        except Exception:
            try:
                tag = handler.build_tag(filepath=filepath + ext)
            except Exception:
                return None

        tag.tags_dir = tags_dir  # for use by bitmap preview window
        return tag

    def bitmap_preview(self, e=None):
        f = self.preview_btn.display_frame
        if f is not None and f() is not None:
            return
        try:
            tag = self.get_dependency_tag()
        except Exception:
            tag = None

        if tag is None:
            return
        self.preview_btn.change_bitmap(tag)
        self.preview_btn.show_window(None, self.tag_window.app_root)

    def validate_filepath(self, *args):
        desc = self.desc
        wid = self.f_widget_ids_map.get(desc['NAME_MAP']['filepath'])
        widget = self.f_widgets.get(wid)
        if widget is None:
            return

        try:
            tags_dir = self.tag_window.tag.tags_dir
        except AttributeError:
            return

        if not tags_dir.endswith(PATHDIV):
            tags_dir += PATHDIV

        ext = '.' + self.node.tag_class.enum_name
        filepath = tags_dir + self.node.filepath
        try:
            if (self.tag_window.handler.treat_mode_as_mod2 and
                ext == '.model' and not exists(filepath + ext)):
                ext = '.gbxmodel'
        except AttributeError:
            pass

        filepath = filepath + ext
        filepath = sanitize_path(filepath)
        if exists(filepath):
            widget.data_entry.config(fg=self.text_normal_color)
        else:
            widget.data_entry.config(fg=self.invalid_path_color)

    def pose_fields(self):
        ContainerFrame.pose_fields(self)

        node = self.node
        desc = node.desc
        picker = self.widget_picker
        tag_window = self.tag_window

        btn_kwargs = dict(
            bg=self.button_color, activebackground=self.button_color,
            fg=self.text_normal_color, bd=self.button_depth,
            disabledforeground=self.text_disabled_color,
            )
        self.browse_btn = tk.Button(
            self, width=3, text='...', command=self.browse_tag, **btn_kwargs)
        self.open_btn = tk.Button(
            self, width=5, text='Open', command=self.open_tag, **btn_kwargs)
        self.preview_btn = None
        try:
            names = node.tag_class.NAME_MAP.keys()
            is_bitmap_dependency = len(names) == 2 and "bitmap" in names
        except Exception:
            is_bitmap_dependency = False

        if is_bitmap_dependency:
            try:
                tags_dir = tag_window.tag.tags_dir
                app_root = tag_window.app_root
            except AttributeError:
                tags_dir = ""
                app_root = None
            self.preview_btn = HaloBitmapDisplayButton(
                self, width=7, text="Preview", command=self.bitmap_preview,
                tags_dir=tags_dir, **btn_kwargs)

        padx, pady, side= self.horizontal_padx, self.horizontal_pady, 'top'
        if self.desc.get('ORIENT', 'v') in 'hH':
            side = 'left'

        for wid in self.f_widget_ids:
            w = self.f_widgets[wid]
            sub_desc = w.desc
            if w.attr_index == 0 and sub_desc['ENTRIES'] <= 2:
                w.pack_forget()
            elif sub_desc.get('NAME') == 'filepath':
                self.write_trace(w.entry_string, self.validate_filepath)
                self.validate_filepath()

        if not hasattr(self.tag_window.tag, "tags_dir"):
            # cant do anything if the tags_dir doesnt exist
            return

        for btn in (self.browse_btn, self.open_btn, self.preview_btn):
            if btn is None: continue
            btn.pack(fill='x', side=side, anchor='nw', padx=padx)

    def reload(self):
        '''Resupplies the nodes to the widgets which display them.'''
        try:
            node = self.node
            desc = self.desc
            f_widgets = self.f_widgets

            field_indices = range(len(node))
            # if the node has a steptree node, include its index in the indices
            if hasattr(node, 'STEPTREE'):
                field_indices = tuple(field_indices) + ('STEPTREE',)

            f_widget_ids_map = self.f_widget_ids_map
            all_visible = self.all_visible

            # if any of the descriptors are different between
            # the sub-nodes of the previous and new sub-nodes,
            # then this widget will need to be repopulated.
            for i in field_indices:
                sub_node = node[i]
                sub_desc = desc[i]
                if hasattr(sub_node, 'desc'):
                    sub_desc = sub_node.desc

                # only display the enumerator if there are more than 2 options
                if i == 0 and sub_desc['ENTRIES'] <= 2:
                    continue

                w = f_widgets.get(f_widget_ids_map.get(i))

                # if neither would be visible, dont worry about checking it
                if not(sub_desc.get('VISIBLE',1) or all_visible) and w is None:
                    continue

                # if the descriptors are different, gotta repopulate!
                if not hasattr(w, 'desc') or w.desc is not sub_desc:
                    self.populate()
                    return
                
            for wid in self.f_widget_ids:
                w = f_widgets[wid]

                w.parent, w.node = node, node[w.attr_index]
                w.reload()

            self.validate_filepath()
        except Exception:
            print(format_exc())


class HaloRawdataFrame(RawdataFrame):

    def delete_node(self):
        undo_node = self.node
        self.node = self.parent[self.attr_index] = self.node[0:0]
        self.edit_create(undo_node=undo_node, redo_node=self.node)

        # until i come up with a better method, i'll have to rely on
        # reloading the root field widget so sizes will be updated
        try:
            self.f_widget_parent.reload()
            self.set_edited()
        except Exception:
            print(format_exc())
            print("Could not reload after deleting data.")

    def edit_apply(self=None, *, edit_state, undo=True):
        attr_index = edit_state.attr_index

        w_parent, parent = FieldWidget.get_widget_and_node(
            nodepath=edit_state.nodepath, tag_window=edit_state.tag_window)

        if undo:
            parent[attr_index] = edit_state.undo_node
        else:
            parent[attr_index] = edit_state.redo_node

        if w_parent is not None:
            try:
                w = w_parent.f_widgets[
                    w_parent.f_widget_ids_map[attr_index]]
                if w.desc is not edit_state.desc:
                    return

                w.node = parent[attr_index]
                w.set_edited()
                w.f_widget_parent.reload()
            except Exception:
                print(format_exc())


class HaloScriptSourceFrame(HaloRawdataFrame):
    @property
    def field_ext(self): return '.hsc'


class HaloScriptTextFrame(TextFrame):
    syntax  = None
    strings = None

    def __init__(self, *args, **kwargs):
        TextFrame.__init__(self, *args, **kwargs)
        tag_data = self.parent.parent.parent.parent
        self.syntax  = reclaimer.hsc.get_hsc_data_block(
            tag_data.script_syntax_data.data)
        self.strings = tag_data.script_string_data.data.decode("latin-1")
        self.reload()

    def export_node(self): pass
    def import_node(self): pass
    def build_replace_map(self): pass
    def flush(self, *a, **kw): pass
    def set_edited(self, *a, **kw): pass
    def set_needs_flushing(self, *a, **kw): pass

    def reload(self):
        try:
            if None in (self.strings, self.syntax):
                return

            typ = "script"
            if "global" in self.f_widget_parent.node.NAME:
                typ = "global"

            tag_data = self.parent.parent.parent.parent
            new_text = reclaimer.hsc.hsc_bytecode_to_string(
                    self.syntax, self.strings, self.f_widget_parent.attr_index,
                    tag_data.scripts.STEPTREE, tag_data.globals.STEPTREE, typ)

            self.data_text.delete(1.0, tk.END)
            self.data_text.insert(1.0, new_text)
        except Exception:
            print(format_exc())

    populate = reload


class SoundSampleFrame(HaloRawdataFrame):

    @property
    def field_ext(self):
        '''The export extension of this FieldWidget.'''
        try:
            if self.parent.parent.compression.enum_name == 'ogg':
                return '.ogg'
        except Exception:
            pass
        return '.wav'

    def import_node(self):
        '''Prompts the user for an exported node file.
        Imports data into the node from the file.'''
        try:
            initialdir = self.tag_window.app_root.last_load_dir
        except AttributeError:
            initialdir = None

        ext = self.field_ext

        filepath = askopenfilename(
            initialdir=initialdir, defaultextension=ext,
            filetypes=[(self.name, "*" + ext), ('All', '*')],
            title="Import sound data from...", parent=self)

        if not filepath:
            return

        ext = splitext(filepath)[1].lower()

        curr_size = None
        index = self.attr_index

        try:
            curr_size = self.parent.get_size(attr_index=index)

            if ext == '.wav':
                # if the file is wav, we need to give it a header
                wav_file = wav_def.build(filepath=filepath)

                sound_data = self.parent.get_root().data.tagdata
                channel_count = sound_data.encoding.data + 1
                sample_rate = 22050 * (sound_data.sample_rate.data + 1)
                wav_fmt = wav_file.data.format

                if wav_fmt.fmt.enum_name not in ('ima_adpcm', 'xbox_adpcm',
                                                 'pcm'):
                    raise TypeError(
                        "Wav file audio format must be either ImaADPCM " +
                        "XboxADPCM, or PCM, not %s" % wav_fmt.fmt.enum_name)

                if sound_data.encoding.data + 1 != wav_fmt.channels:
                    raise TypeError(
                        "Wav file channel count does not match this sound " +
                        "tags channel count. Expected %s, not %s" %
                        (channel_count, wav_fmt.channels))

                if sample_rate != wav_fmt.sample_rate:
                    raise TypeError(
                        "Wav file sample rate does not match this sound " +
                        "tags sample rate. Expected %skHz, not %skHz" %
                        (sample_rate, wav_fmt.sample_rate))

                if 36 * channel_count != wav_fmt.block_align:
                    raise TypeError(
                        "Wav file block size does not match this sound " +
                        "tags block size. Expected %sbytes, not %sbytes" %
                        (36 * channel_count, wav_fmt.block_align))

                rawdata = wav_file.data.wav_data.audio_data
            else:
                rawdata = get_rawdata(filepath=filepath)

            undo_node = self.node
            self.parent.set_size(len(rawdata), attr_index=index)
            self.parent.parse(rawdata=rawdata, attr_index=index)
            self.node = self.parent[index]

            self.edit_create(undo_node=undo_node, redo_node=self.node)

            # until i come up with a better method, i'll have to rely on
            # reloading the root field widget so sizes will be updated
            try:
                self.f_widget_parent.reload()
                self.set_edited()
            except Exception:
                print(format_exc())
                print("Could not reload after importing sound data.")
        except Exception:
            print(format_exc())
            print("Could not import sound data.")
            try: self.parent.set_size(curr_size, attr_index=index)
            except Exception: pass

    def export_node(self):
        try:
            initialdir = self.tag_window.app_root.last_load_dir
        except AttributeError:
            initialdir = None

        def_ext = self.field_ext

        filepath = asksaveasfilename(
            initialdir=initialdir, title="Export sound data to...",
            parent=self, filetypes=[(self.name, '*' + def_ext),
                                    ('All', '*')])

        if not filepath:
            return

        filepath, ext = splitext(filepath)
        if not ext: ext = def_ext
        filepath += ext

        if ext == '.wav':
            # if the file is wav, we need to give it a header
            try:
                wav_file = wav_def.build()
                wav_file.filepath = filepath
                sound_data = self.parent.get_root().data.tagdata

                wav_fmt = wav_file.data.format
                wav_fmt.bits_per_sample = 16
                wav_fmt.channels = sound_data.encoding.data + 1
                wav_fmt.sample_rate = 22050 * (sound_data.sample_rate.data + 1)

                wav_fmt.byte_rate = ((wav_fmt.sample_rate *
                                      wav_fmt.bits_per_sample *
                                      wav_fmt.channels) // 8)

                typ = "ima_adpcm"
                if self.parent.parent.compression.enum_name == 'none':
                    typ = "pcm"

                if typ == "pcm":
                    wav_fmt.fmt.set_to('pcm')
                    wav_fmt.block_align = 2 * wav_fmt.channels
                else:
                    wav_fmt.fmt.set_to('ima_adpcm')
                    wav_fmt.block_align = 36 * wav_fmt.channels

                wav_file.data.wav_data.audio_data = self.node
                wav_file.data.wav_header.filesize = wav_file.data.binsize - 12

                wav_file.serialize(temp=False, backup=False, int_test=False)
            except Exception:
                print(format_exc())
                print("Could not export sound data.")
            return

        try:
            if hasattr(self.node, 'serialize'):
                self.node.serialize(filepath=filepath, clone=self.export_clone,
                                    calc_pointers=self.export_calc_pointers)
            else:
                # the node isnt a block, so we need to call its parents
                # serialize method with the attr_index necessary to export.
                self.parent.serialize(filepath=filepath,
                                      clone=self.export_clone,
                                      calc_pointers=self.export_calc_pointers,
                                      attr_index=self.attr_index)
        except Exception:
            print(format_exc())
            print("Could not export sound data.")


class ReflexiveFrame(DynamicArrayFrame):
    def __init__(self, *args, **kwargs):
        DynamicArrayFrame.__init__(self, *args, **kwargs)

        btn_kwargs = dict(
            bg=self.button_color, fg=self.text_normal_color,
            disabledforeground=self.text_disabled_color,
            bd=self.button_depth,
            )

        self.import_all_btn = tk.Button(
            self.title, width=8, text='Import all',
            command=self.import_all_nodes, **btn_kwargs)
        self.export_all_btn = tk.Button(
            self.buttons, width=8, text='Export all',
            command=self.export_all_nodes, **btn_kwargs)

        # unpack all the buttons
        for w in (self.export_btn, self.import_btn,
                  self.shift_down_btn, self.shift_up_btn,
                  self.delete_all_btn, self.delete_btn,
                  self.duplicate_btn, self.insert_btn, self.add_btn):
            w.forget()
            
        # pack all the buttons(and new ones)
        for w in (self.export_all_btn, self.import_all_btn,
                  self.shift_down_btn, self.shift_up_btn,
                  self.export_btn, self.import_btn,
                  self.delete_all_btn, self.delete_btn,
                  self.duplicate_btn, self.insert_btn, self.add_btn):
            w.pack(side="right", padx=(0, 4), pady=(2, 2))

    def cache_options(self):
        node, desc = self.node, self.desc
        dyn_name_path = desc.get(DYN_NAME_PATH)

        options = {}
        if dyn_name_path:
            try:
                if dyn_name_path.endswith('.filepath'):
                    # if it is a dependency filepath
                    for i in range(len(node)):
                        name = str(node[i].get_neighbor(dyn_name_path))\
                               .replace('/', '\\').split('\\')[-1]\
                               .split('\n')[0]
                        if name:
                            options[i] = name
                else:
                    for i in range(len(node)):
                        name = str(node[i].get_neighbor(dyn_name_path))
                        if name:
                            options[i] = name.split('\n')[0]
                            
            except Exception:
                print(format_exc())
                print("Guess something got mistyped. Tell Moses about it.")
                dyn_name_path = False

        if not dyn_name_path:
            # sort the options by value(values are integers)
            options.update({i: n for n, i in
                            self.desc.get('NAME_MAP', {}).items()
                            if i not in options})
            sub_desc = desc['SUB_STRUCT']
            def_struct_name = sub_desc.get('GUI_NAME', sub_desc['NAME'])

            for i in range(len(node)):
                if i in options:
                    continue
                sub_node = node[i]
                if not hasattr(sub_node, 'desc'):
                    continue
                sub_desc = sub_node.desc
                sub_struct_name = sub_desc.get('GUI_NAME', sub_desc['NAME'])
                if sub_struct_name == def_struct_name:
                    continue

                options[i] = sub_struct_name

        for i, v in options.items():
            options[i] = '%s. %s' % (i, v)

        self.options_sane = True
        self.option_cache = options
        self.sel_menu.update_label()

    def set_import_all_disabled(self, disable=True):
        if disable: self.import_all_btn.config(state="disabled")
        else:       self.import_all_btn.config(state="normal")

    def set_export_all_disabled(self, disable=True):
        if disable: self.export_all_btn.config(state="disabled")
        else:       self.export_all_btn.config(state="normal")

    def export_all_nodes(self):
        try:
            w = self.f_widget_parent
        except Exception:
            return
        w.export_node()

    def import_all_nodes(self):
        try:
            w = self.f_widget_parent
        except Exception:
            return
        w.import_node()
        self.set_edited()


# replace the DynamicEnumFrame with one that has a specialized option generator
class DynamicEnumFrame(DynamicEnumFrame):

    def cache_options(self):
        desc = self.desc
        options = {0: "-1: NONE"}

        dyn_name_path = desc.get(DYN_NAME_PATH)
        if not dyn_name_path:
            print("Missing DYN_NAME_PATH path in dynamic enumerator.")
            print(self.parent.get_root().def_id, self.name)
            print("Tell Moses about this.")
            self.option_cache = options
            return
        try:
            p_out, p_in = dyn_name_path.split(DYN_I)

            # We are ALWAYS going to go to the parent, so we need to slice
            if p_out.startswith('..'): p_out = p_out.split('.', 1)[-1]
            array = self.parent.get_neighbor(p_out)
            for i in range(len(array)):
                name = array[i].get_neighbor(p_in)
                if isinstance(name, list):
                    name = repr(name).strip("[").strip("]")
                else:
                    name = str(name)

                if p_in.endswith('.filepath'):
                    # if it is a dependency filepath
                    options[i + 1] = '%s. %s' % (
                        i, name.replace('/', '\\').split('\\')[-1])
                options[i + 1] = '%s. %s' % (i, name)
        except Exception:
            print(format_exc())
            print("Guess something got mistyped. Tell Moses about this.")
            dyn_name_path = False

        try:
            self.sel_menu.max_index = len(options) - 1
        except Exception:
            pass
        self.option_cache = options
