#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

import os
import tkinter as tk

from pathlib import Path, PureWindowsPath
from sys import platform
from traceback import format_exc

from binilla.widgets.binilla_widget import BinillaWidget

# inject this default color
BinillaWidget.active_tags_directory_color = '#%02x%02x%02x' % (40, 170, 80)


class DirectoryFrame(BinillaWidget, tk.Frame):
    app_root = None

    def __init__(self, master, *args, **kwargs):
        kwargs.setdefault('app_root', master)
        self.app_root = kwargs.pop('app_root')

        kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
        BinillaWidget.__init__(self)
        tk.Frame.__init__(self, master, *args, **kwargs)

        self.hierarchy_frame = HierarchyFrame(self, app_root=self.app_root)

        self.hierarchy_frame.pack(fill='both', expand=True)
        self.apply_style()

    def set_root_dir(self, root_dir):
        self.hierarchy_frame.set_root_dir(root_dir)

    def add_root_dir(self, root_dir):
        self.hierarchy_frame.add_root_dir(root_dir)

    def del_root_dir(self, root_dir):
        self.hierarchy_frame.del_root_dir(root_dir)

    def highlight_tags_dir(self, root_dir):
        self.hierarchy_frame.highlight_tags_dir(root_dir)

    def apply_style(self, seen=None):
        self.hierarchy_frame.apply_style(seen)


class HierarchyFrame(BinillaWidget, tk.Frame):
    tags_dir = ''
    app_root = None
    tags_dir_items = ()
    active_tags_dir = ""

    def __init__(self, master, *args, **kwargs):
        kwargs.update(bg=self.default_bg_color, bd=self.listbox_depth,
            relief='sunken', highlightthickness=0)
        kwargs.setdefault('app_root', master)

        select_mode = kwargs.pop('select_mode', 'browse')

        self.app_root = kwargs.pop('app_root')
        BinillaWidget.__init__(self)
        tk.Frame.__init__(self, master, *args, **kwargs)

        self.tags_tree_frame = tk.Frame(self, highlightthickness=0)

        self.tags_tree = tk.ttk.Treeview(
            self.tags_tree_frame, selectmode=select_mode, padding=(0, 0))
        self.scrollbar_y = tk.Scrollbar(
            self.tags_tree_frame, orient='vertical',
            command=self.tags_tree.yview)
        self.tags_tree.config(yscrollcommand=self.scrollbar_y.set)

        self.tags_tree.bind('<<TreeviewOpen>>', self.open_selected)
        self.tags_tree.bind('<<TreeviewClose>>', self.close_selected)
        self.tags_tree.bind('<Double-Button-1>', self.activate_item)
        self.tags_tree.bind('<Return>', self.activate_item)

        self.tags_tree_frame.pack(fill='both', side='left', expand=True)

        # pack in this order so scrollbars aren't shrunk when resizing
        self.scrollbar_y.pack(side='right', fill='y')
        self.tags_tree.pack(side='right', fill='both', expand=True)

        self.reload()
        self.apply_style()

    def apply_style(self, seen=None):
        BinillaWidget.apply_style(self, seen)
        self.tags_tree_frame.config(bg=self.default_bg_color)

        dir_tree = self.tags_tree
        self.highlight_tags_dir()

    def reload(self):
        dir_tree = self.tags_tree
        self.tags_dir = self.app_root.tags_dir
        if not dir_tree['columns']:
            dir_tree['columns'] = ('size', )
            dir_tree.heading("#0", text='path')
            dir_tree.heading("size", text='info')
            dir_tree.column("#0", minwidth=100, width=100)
            dir_tree.column("size", minwidth=100, width=100, stretch=False)

        for tags_dir in self.tags_dir_items:
            dir_tree.delete(tags_dir)

        self.tags_dir_items = []

        for tags_dir in self.app_root.tags_dirs:
            self.add_root_dir(tags_dir)

    def set_root_dir(self, root_dir):
        dir_tree = self.tags_tree
        curr_root_dir = self.app_root.tags_dir

        tags_dir_index = dir_tree.index(curr_root_dir)
        dir_tree.delete(curr_root_dir)
        self.insert_root_dir(root_dir)

    def add_root_dir(self, root_dir):
        '''
        Alias for insert_root_dir.
        '''
        self.insert_root_dir(root_dir)

    def insert_root_dir(self, root_dir, index='end'):
        '''
        Add new top tag directory to the HierarchyFrame.
        '''
        # Turn "/home/currentuser/" into "~/"
        text = str(root_dir)
        if "linux" in platform:
            home = str(Path.home())
            if text.startswith(home):
                text = "~/" + text[1+len(home):]

        iid = self.tags_tree.insert(
            '', index, iid=root_dir, text=text,
            tags=(root_dir, 'tagdir',))
        self.tags_dir_items.append(iid)
        self.destroy_subitems(iid)

    def del_root_dir(self, root_dir):
        self.tags_tree.delete(root_dir)

    def destroy_subitems(self, directory):
        '''
        Destroys all the given items subitems and creates an empty
        subitem so as to give the item the appearance of being expandable.
        '''
        dir_tree = self.tags_tree

        for child in dir_tree.get_children(directory):
            dir_tree.delete(child)

        # add an empty node to make an "expand" button appear
        dir_tree.insert(directory, 'end')

    def generate_subitems(self, directory):
        dir_tree = self.tags_tree

        directory = str(directory)
        for root, subdirs, files in os.walk(directory):
            for subdir in sorted(subdirs, key=str.casefold):
                folderpath = os.path.join(root, subdir)

                dir_info_str = "%s items" % len(list(os.scandir(folderpath)))

                dir_tree.insert(
                    directory, 'end', text=subdir,
                    iid=folderpath, tags=('item',),
                    values=(dir_info_str, ))

                # loop over each of the new items, give them
                # at least one item so they can be expanded.
                self.destroy_subitems(folderpath)

            for file in sorted(files, key=str.casefold):
                fullpath = os.path.join(root, file)
                try:
                    filesize = os.stat(fullpath).st_size
                    if filesize < 1024:
                        filesize = "%d Bytes" % (filesize)
                    elif filesize < 1024**2:
                        filesize = "%.2f KiB" % (filesize/1024)
                    else:
                        filesize = "%.2f MiB" % (filesize/1024**2)
                except Exception:
                    filesize = 'ERROR'
                dir_tree.insert(directory, 'end', text=file,
                                iid=fullpath, tags=('item',),
                                values=(filesize, ))

            # just do the toplevel of the hierarchy
            break

    def get_item_tags_dir(self, iid):
        '''Returns the tags directory of the given item'''
        dir_tree = self.tags_tree
        prev_parent = iid
        parent = dir_tree.parent(prev_parent)

        while parent:
            prev_parent = parent
            parent = dir_tree.parent(prev_parent)

        return prev_parent

    def open_selected(self, e=None):
        dir_tree = self.tags_tree
        tag_path = dir_tree.focus()
        for child in dir_tree.get_children(tag_path):
            dir_tree.delete(child)

        if tag_path:
            self.generate_subitems(tag_path)

    def close_selected(self, e=None):
        dir_tree = self.tags_tree
        tag_path = dir_tree.focus()
        if tag_path is None:
            return

        if Path(tag_path).is_dir():
            self.destroy_subitems(tag_path)

    def highlight_tags_dir(self, tags_dir=None):
        app = self.app_root
        dir_tree = self.tags_tree
        if tags_dir is None:
              tags_dir = self.app_root.tags_dir

        tags_dir = Path(tags_dir)
        for td in app.tags_dirs:
            if td == tags_dir:
                dir_tree.tag_configure(
                    str(td),
                    background=self.active_tags_directory_color,
                    foreground=self.text_highlighted_color)
                self.active_tags_dir = td
            else:
                dir_tree.tag_configure(
                    str(td),
                    background=self.entry_normal_color,
                    foreground=self.text_normal_color)

    def activate_item(self, e=None):
        dir_tree = self.tags_tree
        tag_path = dir_tree.focus()
        if tag_path is None:
            return

        try:
            app = self.app_root
            tags_dir = Path(self.get_item_tags_dir(tag_path))
            tags_dir_index = self.app_root.get_tags_dir_index(
                self.get_item_tags_dir(tag_path))
            if tags_dir_index is None:
                print("'%s' is not a registered tags directory." % tags_dir)
                return

            self.highlight_tags_dir(tags_dir)
            app.switch_tags_dir(index=tags_dir_index)
        except Exception:
            print(format_exc())

        tag_path = Path(tag_path)
        if tag_path.is_dir():
            app.last_load_dir = tag_path
            return

        try:
            app.load_tags(filepaths=tag_path)
        except Exception:
            print(format_exc())


class DependencyFrame(HierarchyFrame):
    root_tag_path = ''
    root_tag_text = None
    _initialized = False
    handler = None

    def __init__(self, master, *args, **kwargs):
        HierarchyFrame.__init__(self, master, *args, **kwargs)
        self.handler = self.app_root.handler
        self._initialized = True

    def apply_style(self, seen=None):
        HierarchyFrame.apply_style(self, seen)
        self.tags_tree.tag_configure(
            'badref', foreground=self.invalid_path_color,
            background=self.default_bg_color)

    def get_item_tags_dir(*args, **kwargs): pass

    def highlight_tags_dir(*args, **kwargs): pass

    def reload(self):
        dir_tree = self.tags_tree
        if self.handler is not None:
            self.tags_dir = self.handler.tagsdir
        else:
            self.tags_dir = Path("")

        if not dir_tree['columns']:
            dir_tree["columns"]=("dependency", )
            dir_tree.heading("#0", text='Filepath')
            dir_tree.heading("dependency", text='Dependency path')

        if not self._initialized:
            return

        for item in dir_tree.get_children():
            try: dir_tree.delete(item)
            except Exception: pass

        root = self.root_tag_path
        text = self.root_tag_text
        if text is None:
            text = root

        iid = self.tags_tree.insert(
            '', 'end', iid=self.root_tag_path, text=text,
            tags=(root, 'item'), values=('', root))
        self.destroy_subitems(iid)

    def get_dependencies(self, tag_path):
        tag = self.master.get_tag(tag_path)
        if tag is None:
            print(("Unable to load '%s'.\n" % tag_path) +
                  "    You may need to change the tag set to load this tag.")
            return ()

        handler = self.handler
        d_id = tag.def_id
        dependency_cache = handler.tag_ref_cache.get(d_id)

        if not dependency_cache:
            return ()

        dependencies = []

        for block in handler.get_nodes_by_paths(dependency_cache, tag.data):
            # if the node's filepath is empty, just skip it
            if not block.filepath:
                continue
            dependencies.append(block)
        return dependencies

    def destroy_subitems(self, iid):
        '''
        Destroys all the given items subitems and creates an empty
        subitem so as to give the item the appearance of being expandable.
        '''
        dir_tree = self.tags_tree

        for child in dir_tree.get_children(iid):
            dir_tree.delete(child)

        # add an empty node to make an "expand" button appear
        tag_path = Path(dir_tree.item(iid)['values'][-1])
        if not tag_path.is_file():
            dir_tree.item(iid, tags=('badref', 'item'))
        elif self.get_dependencies(tag_path):
            dir_tree.insert(iid, 'end')

    def close_selected(self, e=None):
        dir_tree = self.tags_tree
        iid = dir_tree.focus()
        if iid:
            self.destroy_subitems(iid)

    def generate_subitems(self, parent_iid):
        tags_dir = self.handler.tagsdir
        dir_tree = self.tags_tree
        parent_tag_path = Path(dir_tree.item(parent_iid)['values'][-1])

        if not parent_tag_path.is_file():
            return

        for tag_ref_block in self.get_dependencies(parent_tag_path):
            filepath = Path(PureWindowsPath(tag_ref_block.filepath))
            try:
                ext = '.' + tag_ref_block.tag_class.enum_name
                if (self.handler.treat_mode_as_mod2 and ext == '.model' and
                not Path(tags_dir, str(filepath) + ".model").is_file()):
                    ext = '.gbxmodel'
            except Exception:
                ext = ''
            tag_path = str(filepath) + ext

            dependency_name = tag_ref_block.NAME
            last_block = tag_ref_block
            parent = last_block.parent
            while parent is not None and hasattr(parent, 'NAME'):
                name = parent.NAME
                f_type = parent.TYPE
                if f_type.is_array:
                    index = parent.index(last_block)
                    dependency_name = '[%s].%s' % (index, dependency_name)
                elif name not in ('tagdata', 'data'):
                    if not last_block.TYPE.is_array:
                        name += '.'
                    dependency_name = name + dependency_name
                last_block = parent
                parent = last_block.parent

            # slice off the extension and the period
            dependency_name = dependency_name.split('.', 1)[-1]

            iid = dir_tree.insert(
                parent_iid, 'end', text=tag_path, tags=('item',),
                values=(dependency_name, Path(tags_dir, tag_path)))

            self.destroy_subitems(iid)

    def activate_item(self, e=None):
        dir_tree = self.tags_tree
        active = dir_tree.focus()
        if active is None:
            return

        tag_path = Path(dir_tree.item(active)['values'][-1])
        try:
            app = self.app_root
            tags_dir = self.get_item_tags_dir(tag_path)
            self.highlight_tags_dir(tags_dir)
        except Exception:
            print(format_exc())

        if tag_path.is_dir():
            return

        try:
            app.load_tags(filepaths=tag_path)
        except Exception:
            print(format_exc())
