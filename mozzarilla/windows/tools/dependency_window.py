#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

from pathlib import Path, PureWindowsPath
import os
import tkinter as tk
import zipfile

from threading import Thread
from traceback import format_exc

from binilla.widgets.binilla_widget import BinillaWidget
from binilla.windows.filedialog import askopenfilename, asksaveasfilename

from supyr_struct.util import path_normalize, is_in_dir, tagpath_to_fullpath
from mozzarilla.widgets.directory_frame import DirectoryFrame,\
     HierarchyFrame, DependencyFrame
from mozzarilla import editor_constants as e_c


class DependencyWindow(tk.Toplevel, BinillaWidget):
    app_root = None
    handler = None

    _zipping = False
    stop_zipping = False

    def __init__(self, app_root, *args, **kwargs):
        self.handler = app_root.handler
        self.app_root = app_root
        kwargs.update(width=400, height=500, bd=0,
                      highlightthickness=0, bg=self.default_bg_color)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)
        BinillaWidget.__init__(self, app_root, *args, **kwargs)
        self.title("[%s] Tag dependency viewer / zipper" %
                   app_root.handler_names[app_root._curr_handler_index])
        self.minsize(width=400, height=100)
        self.update()
        try:
            self.iconbitmap(e_c.MOZZ_ICON_PATH)
        except Exception:
            print("Could not load window icon.")

        # make the tkinter variables
        self.tag_filepath = tk.StringVar(self)

        # make the frames
        self.filepath_frame = tk.LabelFrame(self, text="Select a tag")
        self.button_frame = tk.LabelFrame(self, text="Actions")

        self.display_button = tk.Button(
            self.button_frame, width=25, text='Show dependencies',
            command=self.populate_dependency_tree)

        self.zip_button = tk.Button(
            self.button_frame, width=25, text='Zip tag recursively',
            command=self.recursive_zip)

        self.dependency_frame = DependencyFrame(self, app_root=self.app_root)

        self.filepath_entry = tk.Entry(
            self.filepath_frame, textvariable=self.tag_filepath)
        self.browse_button = tk.Button(
            self.filepath_frame, text="Browse", command=self.browse)

        self.display_button.pack(padx=4, pady=2, side='left')
        self.zip_button.pack(padx=4, pady=2, side='right')

        self.filepath_entry.pack(padx=(4, 0), pady=2, side='left',
                                 expand=True, fill='x')
        self.browse_button.pack(padx=(0, 4), pady=2, side='left')

        self.filepath_frame.pack(fill='x', padx=1)
        self.button_frame.pack(fill='x', padx=1)
        self.dependency_frame.pack(fill='both', padx=1, expand=True)

        self.transient(app_root)
        self.apply_style()
        self.update()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry("%sx%s" % (w, h))
        self.minsize(width=w, height=h)

    def browse(self):
        if self._zipping:
            return

        filetypes = [('All', '*')]

        defs = self.app_root.handler.defs
        for def_id in sorted(defs.keys()):
            filetypes.append((def_id, defs[def_id].ext))
        fp = askopenfilename(
            title="Select a tag", filetypes=filetypes, parent=self,
            initialdir=self.app_root.last_load_dir)

        if not fp:
            return

        self.app_root.last_load_dir = Path(fp).parent
        self.tag_filepath.set(fp)

    def destroy(self):
        try:
            self.app_root.tool_windows.pop(self.window_name, None)
        except AttributeError:
            pass
        self.stop_zipping = True
        tk.Toplevel.destroy(self)

    def get_tag(self, tag_path):
        try:
            return self.handler.get_tag(tag_path, load_unloaded=True)
        except KeyError:
            print(format_exc())
            return None

    def get_dependencies(self, tag):
        def_id = tag.def_id
        dependency_cache = self.handler.tag_ref_cache.get(def_id)

        if not dependency_cache:
            return ()

        nodes = self.handler.get_nodes_by_paths(
            self.handler.tag_ref_cache[def_id], tag.data)

        dependencies = []

        for node in nodes:
            # if the node's filepath is empty, just skip it
            if not node.filepath:
                continue

            ext = '.' + node.tag_class.enum_name

            if tagpath_to_fullpath(
                self.handler.tagsdir, PureWindowsPath(node.filepath), extension=ext
            ) is not None and (self.handler.treat_mode_as_mod2 and ext == '.model'):
                ext = '.gbxmodel'

            dependencies.append(node.filepath + ext)
        return dependencies

    def populate_dependency_tree(self):
        filepath = self.tag_filepath.get()
        if not filepath:
            return

        app = self.app_root
        handler = self.handler = app.handler
        handler_name = app.handler_names[app._curr_handler_index]
        if handler_name not in app.tags_dir_relative:
            print("Change the current tag set.")
            return

        filepath = path_normalize(filepath)

        if not is_in_dir(filepath, self.handler.tagsdir):
            print("%s\nis not in tagsdir\n%s" %
                  (filepath, self.handler.tagsdir))
            return

        rel_filepath = Path(filepath).relative_to(self.handler.tagsdir)
        tag = self.get_tag(rel_filepath)
        if tag is None:
            print("Could not load tag:\n    %s" % filepath)
            return

        self.dependency_frame.handler = handler
        self.dependency_frame.tags_dir = self.handler.tagsdir
        self.dependency_frame.root_tag_path = tag.filepath
        self.dependency_frame.root_tag_text = rel_filepath

        self.dependency_frame.reload()

    def recursive_zip(self):
        if self._zipping:
            return
        try: self.zip_thread.join()
        except Exception: pass
        self.zip_thread = Thread(target=self._recursive_zip)
        self.zip_thread.daemon = True
        self.zip_thread.start()

    def _recursive_zip(self):
        self._zipping = True
        try:
            self.do_recursive_zip()
        except Exception:
            print(format_exc())
        self._zipping = False

    def do_recursive_zip(self):
        tag_path = self.tag_filepath.get()
        if not tag_path:
            return

        app = self.app_root
        handler = self.handler = app.handler
        handler_name = app.handler_names[app._curr_handler_index]
        if handler_name not in app.tags_dir_relative:
            print("Change the current tag set.")
            return

        tag_path = Path(tag_path)
        if not is_in_dir(tag_path, self.handler.tagsdir):
            print("Specified tag is not located within the tags directory")
            return

        tagzip_path = asksaveasfilename(
            initialdir=self.app_root.last_load_dir, parent=self,
            title="Save zipfile to...", filetypes=(("zipfile", "*.zip"), ))

        if not tagzip_path:
            return

        try:
            rel_filepath = tag_path.relative_to(self.handler.tagsdir)
            tag = self.get_tag(rel_filepath)
        except ValueError:
            tag = None

        if tag is None:
            print("Could not load tag:\n    %s" % tag_path)
            return

        # make the zipfile to put everything in
        tagzip_path = os.path.splitext(tagzip_path)[0] + ".zip"

        tags_to_zip = [rel_filepath]
        new_tags_to_zip = []
        seen_tags = set()

        with zipfile.ZipFile(str(tagzip_path), mode='w') as tagzip:
            # loop over all the tags and add them to the zipfile
            while tags_to_zip:
                for rel_filepath in tags_to_zip:
                    tag_path = tagpath_to_fullpath(
                        self.handler.tagsdir, PureWindowsPath(rel_filepath))
                    if self.stop_zipping:
                        print('Recursive zip operation cancelled.\n')
                        return

                    if rel_filepath in seen_tags:
                        continue
                    seen_tags.add(rel_filepath)

                    try:
                        print("Adding '%s' to zipfile" % rel_filepath)
                        app.update_idletasks()
                        tag = self.get_tag(rel_filepath)
                        new_tags_to_zip.extend(self.get_dependencies(tag))

                        # try to conserve memory a bit
                        del tag

                        tagzip.write(str(tag_path), arcname=str(rel_filepath))
                    except Exception:
                        print(format_exc())
                        print("    Could not add '%s' to zipfile." %
                              rel_filepath)

                # replace the tags to zip with the newly collected ones
                tags_to_zip[:] = new_tags_to_zip
                del new_tags_to_zip[:]

        print("\nRecursive zip completed.\n")
