#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

import tkinter as tk

from traceback import format_exc

from supyr_struct.field_types import UInt8

from binilla.widgets.field_widgets import FieldWidget, NumberEntryFrame,\
     ContainerFrame, ColorPickerFrame

from mozzarilla import editor_constants as e_c


def extract_color(chan_char, node):
    return (node >> e_c.channel_offset_map[chan_char]) & 0xFF


def inject_color(chan_char, new_val, parent, attr_index):
    off = e_c.channel_offset_map[chan_char]
    node = parent[attr_index]
    chan_mask = 0xFFFFFFFF - (0xFF << off)
    parent[attr_index] = (node & chan_mask) | ((new_val & 0xFF) << off)


class HaloColorEntry(NumberEntryFrame):

    def set_modified(self, *args):
        if self.node is None or self.needs_flushing:
            return
        elif self.entry_string.get() != self.last_flushed_val:
            self.set_needs_flushing()
            self.set_edited()

    def flush(self, *args):
        if self.node is None or self._flushing or not self.needs_flushing:
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
        #TYPE INITIALIZING IS FUCKING SHIT UP
        FieldWidget.__init__(self, *args, **kwargs)
        kwargs.update(relief='flat', bd=0, highlightthickness=0,
                      bg=self.default_bg_color)
        if self.f_widget_parent is None:
            self.pack_padx = self.pack_pady = 0

        if 'a' in self.desc['COLOR_CHANNELS']:
            self.has_alpha = True
        else:
            self.has_alpha = False

        tk.Frame.__init__(self, *args, **e_c.fix_kwargs(**kwargs))

        self._initialized = True
        self.populate()

    def load_child_node_data(self):
        for chan_char in self.desc['COLOR_CHANNELS']:
            chan = e_c.channel_name_map[chan_char]
            node_val = int(getattr(self, chan) * 255.0 + 0.5)
            w = self.f_widgets.get(self.f_widget_ids_map.get(chan, None), None)
            if w:
                w.load_node_data(self.node, node_val, chan_char,
                                 self.color_descs[chan_char])

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
        w, parent = FieldWidget.get_widget_and_node(
            nodepath=state.nodepath, tag_window=state.tag_window)
        try:
            w = w.f_widgets[w.f_widget_ids_map[attr_index]]
        except Exception:
            pass

        nodes = state.redo_node
        if undo:
            nodes = state.undo_node

        for c in 'argb':
            inject_color(c, nodes[c], parent, attr_index)

        if w is not None:
            try:
                if w.desc != state.desc:
                    return

                w.node = parent[attr_index]
                w.needs_flushing = False
                w.reload()
                w.set_edited()
            except Exception:
                print(format_exc())

    def populate(self):
        content = self
        if hasattr(self, 'content'):
            content = self.content
        if content in (None, self):
            content = tk.Frame(self, relief="sunken", bd=0,
                               highlightthickness=0, bg=self.default_bg_color)

        self.content = content
        self.f_widget_ids = []
        self.f_widget_ids_map = {}
        self.f_widget_ids_map_inv = {}

        # destroy all the child widgets of the content
        if isinstance(self.f_widgets, dict):
            for c in list(self.f_widgets.values()):
                c.destroy()

        self.display_comment(self)

        self.title_label = tk.Label(
            self, anchor='w', justify='left', font=self.get_font("default"),
            width=self.title_size, text=self.gui_name,
            bg=self.default_bg_color, fg=self.text_normal_color)
        self.title_label.pack(fill="x", side="left")

        node = self.node
        desc = self.desc
        self.title_label.tooltip_string = self.tooltip_string = desc.get('TOOLTIP')

        for chan_char in desc['COLOR_CHANNELS']:
            chan = e_c.channel_name_map[chan_char]
            node_val = int(getattr(self, chan) * 255.0 + 0.5)
            # make an entry widget for each color channel
            w = HaloColorEntry(self.content, f_widget_parent=self,
                               desc=self.color_descs[chan_char], node=node_val,
                               parent=self.node, vert_oriented=False,
                               tag_window=self.tag_window, attr_index=chan_char)

            wid = id(w)
            self.f_widget_ids.append(wid)
            self.f_widget_ids_map[chan] = wid
            self.f_widget_ids_map_inv[wid] = chan
            if self.tooltip_string:
                w.tooltip_string = self.tooltip_string

        self.color_btn = tk.Button(
            self.content, width=4, command=self.select_color,
            bd=self.button_depth, bg=self.get_color()[1],
            state=tk.DISABLED if self.disabled else tk.NORMAL)

        self.build_f_widget_cache()
        self.pose_fields()

    def reload(self):
        if self.parent is None:
            return

        self.node = self.parent[self.attr_index]
        if hasattr(self, 'color_btn'):
            if self.disabled:
                self.color_btn.config(state=tk.DISABLED)
            else:
                self.color_btn.config(state=tk.NORMAL)

            self.color_btn.config(bg=self.get_color()[1])

        self.load_child_node_data()
        for wid in self.f_widget_ids:
            self.f_widgets[wid].reload()

    apply_style = FieldWidget.apply_style

    def pose_fields(self):
        ContainerFrame.pose_fields(self)
        self.color_btn.pack(side='left')

    @property
    def alpha(self):
        if self.node is None: return 0.0
        return extract_color('a', self.node) / 255.0

    @alpha.setter
    def alpha(self, new_val):
        if self.node is None: return
        inject_color('a', int(new_val * 255.0 + 0.5),
                     self.parent, self.attr_index)
        self.node = self.parent[self.attr_index]

    @property
    def red(self):
        if self.node is None: return 0.0
        return extract_color('r', self.node) / 255.0

    @red.setter
    def red(self, new_val):
        if self.node is None: return
        inject_color('r', int(new_val * 255.0 + 0.5),
                     self.parent, self.attr_index)
        self.node = self.parent[self.attr_index]

    @property
    def green(self):
        if self.node is None: return 0.0
        return extract_color('g', self.node) / 255.0

    @green.setter
    def green(self, new_val):
        if self.node is None: return
        inject_color('g', int(new_val * 255.0 + 0.5),
                     self.parent, self.attr_index)
        self.node = self.parent[self.attr_index]

    @property
    def blue(self):
        if self.node is None: return 0.0
        return extract_color('b', self.node) / 255.0

    @blue.setter
    def blue(self, new_val):
        if self.node is None: return
        inject_color('b', int(new_val * 255.0 + 0.5),
                     self.parent, self.attr_index)
        self.node = self.parent[self.attr_index]
