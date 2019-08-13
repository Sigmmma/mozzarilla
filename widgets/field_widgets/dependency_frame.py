import os
import tkinter as tk
import tkinter.ttk as ttk

from copy import copy
from tkinter.filedialog import askopenfilename
from traceback import format_exc

from supyr_struct.defs.constants import PATHDIV
from supyr_struct.util import sanitize_path

from binilla import constants
from binilla.widgets.field_widgets.container_frame import ContainerFrame
from mozzarilla.widgets.field_widgets.halo_1_bitmap_display import HaloBitmapDisplayButton


class DependencyFrame(ContainerFrame):
    open_btn = None
    browse_btn = None
    preview_btn = None
    validate_write_trace = None
    validate_entry_str = None

    def browse_tag(self):
        if self.node is None:
            return

        try:
            try:
                tags_dir = self.tag_window.tag.tags_dir
            except AttributeError as e:
                return

            if not tags_dir.endswith(PATHDIV):
                tags_dir += PATHDIV

            init_dir = sanitize_path(tags_dir)
            try:
                init_dir = os.path.dirname(
                    os.path.join(tags_dir, sanitize_path(self.node.filepath))
                    )
            except Exception:
                pass

            init_dir = sanitize_path(init_dir)

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

            # ALWAYS store the path with \ as the separator. Halo tools expect
            # the windows style '\' separator, not the unix/linux '/' separator
            filepath = filepath.replace('/', '\\')
            tag_path, ext = os.path.splitext(filepath.lower().split(
                tags_dir.lower().replace('/', '\\'))[-1])
            orig_tag_class = copy(self.node.tag_class)
            try:
                self.node.tag_class.set_to(ext[1:])
            except Exception:
                self.node.tag_class.set_to('NONE')
                for filetype in filetypes:
                    ext = filetype[1][1:]
                    if os.path.exists(tags_dir + tag_path + ext):
                        self.node.tag_class.set_to(ext[1:])
                        break

            self.edit_create(
                attr_index=('tag_class', 'filepath'),
                redo_node=dict(
                    tag_class=self.node.tag_class, filepath=tag_path),
                undo_node=dict(
                    tag_class=orig_tag_class, filepath=self.node.filepath))

            self.node.filepath = tag_path
            self.reload()
            self.set_edited()
        except Exception:
            print(format_exc())

    def open_tag(self):
        if self.node is None:
            return

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
                    ext == '.model' and not os.path.exists(filepath + ext)):
                    ext = '.gbxmodel'
            except AttributeError:
                pass

            app.set_active_handler(new_handler)
            app.load_tags(filepaths=filepath + ext)
        except Exception:
            print(format_exc())
        finally:
            app.set_active_handler(cur_handler)

    def get_dependency_tag(self):
        if self.node is None:
            return

        t_w = self.tag_window
        try:
            tags_dir, app, handler = t_w.tag.tags_dir, t_w.app_root, t_w.handler
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
                    ext == '.model' and not os.path.exists(filepath + ext)):
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
        if self.node is None:
            return

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
                ext == '.model' and not os.path.exists(filepath + ext)):
                ext = '.gbxmodel'
        except AttributeError:
            pass

        filepath = filepath + ext
        filepath = sanitize_path(filepath)
        if os.path.exists(filepath):
            widget.data_entry.config(fg=self.text_normal_color)
        else:
            widget.data_entry.config(fg=self.invalid_path_color)

    def pose_fields(self):
        ContainerFrame.pose_fields(self)
        picker = self.widget_picker
        tag_window = self.tag_window

        self.browse_btn = ttk.Button(
            self, width=3, text='...', command=self.browse_tag)
        self.open_btn = ttk.Button(
            self, width=5, text='Open', command=self.open_tag)
        self.preview_btn = None
        try:
            names = self.desc[0]['NAME_MAP'].keys()
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
                tags_dir=tags_dir)

        padx, pady, side= self.horizontal_padx, self.horizontal_pady, 'top'
        if self.desc.get('ORIENT', 'v') in 'hH':
            side = 'left'

        for wid in self.f_widget_ids:
            w = self.f_widgets[wid]
            if w.attr_index == 0:
                # hide the tag class dropdown if not showing hidden and
                # there is only one valid tag class other than NONE
                if w.desc.get('ENTRIES', 0) <= 2 and not self.get_visible(
                        constants.VISIBILITY_HIDDEN):
                    w.pack_forget()
            elif w.attr_index == 'STEPTREE':
                # make sure the filepath has a write trace attached to it
                try:
                    self.delete_validate_trace()
                except Exception:
                    pass

                self.validate_entry_str = w.entry_string
                self.create_validate_trace()
                self.validate_filepath()

        if not hasattr(self.tag_window.tag, "tags_dir"):
            # cant do anything if the tags_dir doesnt exist
            return

        for btn in (self.browse_btn, self.open_btn, self.preview_btn):
            if btn is None: continue
            btn.pack(fill='x', side=side, anchor='nw', padx=padx)

    def create_validate_trace(self):
        self.validate_write_trace = self.write_trace(
            self.validate_entry_str, self.validate_filepath)

    def delete_validate_trace(self):
        self.validate_entry_str.trace_vdelete(
            "w", self.validate_write_trace)
        self.validate_write_trace = self.validate_entry_str = None

    def reload(self):
        '''Resupplies the nodes to the widgets which display them.'''
        try:
            f_widgets = self.f_widgets

            field_indices = range(self.desc['ENTRIES'])
            # if the node has a steptree node, include its index in the indices
            if 'STEPTREE' in self.desc:
                field_indices = tuple(field_indices) + ('STEPTREE',)

            f_widget_ids_map = self.f_widget_ids_map
            if hasattr(self, "preview_btn") and self.preview_btn:
                self.preview_btn.display_frame = None

            # if any of the descriptors are different between
            # the sub-nodes of the previous and new sub-nodes,
            # then this widget will need to be repopulated.
            sub_node = None
            for i in field_indices:
                sub_desc = self.desc[i]
                if hasattr(self.node, "__getitem__"):
                    sub_node = self.node[i]

                if hasattr(sub_node, 'desc'):
                    sub_desc = sub_node.desc

                # only display the enumerator if there are more than 2 options
                if i == 0 and sub_desc['ENTRIES'] <= 2:
                    continue

                w = f_widgets.get(f_widget_ids_map.get(i))

                # if neither would be visible, dont worry about checking it
                if not self.get_visible(sub_desc.get('VISIBLE', True)) and w is None:
                    continue

                # if the descriptors are different, gotta repopulate!
                if not hasattr(w, 'desc') or w.desc is not sub_desc:
                    self.populate()
                    return

            if self.node is not None:
                for wid in self.f_widget_ids:
                    w = f_widgets[wid]

                    w.parent, w.node = self.node, self.node[w.attr_index]
                    w.reload()

            self.validate_filepath()
        except Exception:
            print(format_exc())

    def set_disabled(self, disable=True):
        disable = disable or not self.editable
        if self.node is None and not disable:
            return

        if bool(disable) != self.disabled:
            for w in (self.open_btn, self.browse_btn, self.preview_btn):
                if w:
                    w.config(state=tk.DISABLED if disable else tk.NORMAL)

        ContainerFrame.set_disabled(self, disable)

    def apply_style(self, seen=None):
        ContainerFrame.apply_style(self, seen)
        self.validate_filepath()
