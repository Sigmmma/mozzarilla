import os
import gc
import tkinter as tk

from os.path import dirname, exists, isdir, join, splitext, relpath
from threading import Thread
from tkinter import messagebox
from traceback import format_exc

from reclaimer.constants import *

# before we do anything, we need to inject these constants so any definitions
# that are built that use them will have them in their descriptor entries.
inject_halo_constants()

from binilla.app_window import *
from binilla.util import do_subprocess, is_main_frozen, get_cwd
from reclaimer.hek.handler import HaloHandler
from reclaimer.os_v3_hek.handler import OsV3HaloHandler
from reclaimer.os_v4_hek.handler import OsV4HaloHandler
from reclaimer.misc.handler import MiscHaloLoader
from reclaimer.stubbs.handler import StubbsHandler

from mozzarilla.config_def import config_def, guerilla_workspace_def
from mozzarilla.widget_picker import *
from mozzarilla.tag_window import HaloTagWindow
from mozzarilla.tools import \
     SearchAndReplaceWindow, SauceRemovalWindow, BitmapConverterWindow,\
     DependencyWindow, TagScannerWindow, DataExtractionWindow,\
     DirectoryFrame, HierarchyFrame, DependencyFrame,\
     bitmap_from_dds, bitmap_from_multiple_dds, bitmap_from_bitmap_source, \
     ModelCompilerWindow, physics_from_jms,\
     hud_message_text_from_hmt, strings_from_txt


default_hotkeys.update({
    '<F1>': "show_dependency_viewer",
    '<F2>': "show_tag_scanner",
    '<F3>': "show_search_and_replace",
    '<F4>': "show_data_extraction_window",

    '<F5>': "switch_tags_dir",
    '<F6>': "set_tags_dir",
    '<F7>': "add_tags_dir",
    #'<F8>': "???",

    '<F9>': "bitmap_from_dds",
    '<F10>': "bitmap_from_bitmap_source",
    '<F11>': "bitmap_from_multiple_dds",
    #'<F12>': "create_hek_pool_window",
    })

this_curr_dir = get_cwd(__file__)


class Mozzarilla(Binilla):
    app_name = 'Mozzarilla'
    version = '1.3.9'
    log_filename = 'mozzarilla.log'
    debug = 0

    curr_dir = this_curr_dir
    _mozzarilla_initialized = False

    styles_dir  = this_curr_dir + PATHDIV + "styles"
    config_path = this_curr_dir + '%smozzarilla.cfg' % PATHDIV
    config_def  = config_def
    config_version = 2

    handlers = (
        HaloHandler,
        OsV3HaloHandler,
        OsV4HaloHandler,
        MiscHaloLoader,
        StubbsHandler,
        )

    handler_names = (
        "Halo 1",
        "Halo 1 OS v3",
        "Halo 1 OS v4",
        "Halo 1 Misc",
        "Stubbs the Zombie",
        )

    # names of the handlers that MUST load tags from within their tags_dir
    tags_dir_relative = set((
        "Halo 1",
        "Halo 1 OS v3",
        "Halo 1 OS v4",
        "Stubbs the Zombie",
        ))

    tags_dirs = ()

    _curr_handler_index  = 0
    _curr_tags_dir_index = 0

    widget_picker = def_halo_widget_picker

    tool_windows = None

    window_panes = None
    directory_frame = None
    directory_frame_width = 200
    last_data_load_dir = ""
    jms_load_dir = ""
    bitmap_load_dir = ""

    def __init__(self, *args, **kwargs):
        self.debug = kwargs.pop('debug', self.debug)

        # gotta give it a default handler or else the
        # config file will fail to be created as updating
        # the config requires using methods in the handler.
        kwargs['handler'] = MiscHaloLoader(debug=self.debug)
        self.tags_dir_relative = set(self.tags_dir_relative)
        self.tags_dirs = ["%s%stags%s" % (this_curr_dir, PATHDIV, PATHDIV)]

        Binilla.__init__(self, *args, **kwargs)
        try:
            try:
                self.iconbitmap(join(this_curr_dir, 'mozzarilla.ico'))
            except Exception:
                self.iconbitmap(join(this_curr_dir, 'icons', 'mozzarilla.ico'))
        except Exception:
            print("Could not load window icon.")

        self.file_menu.insert_command("Exit", label="Load guerilla config",
                                      command=self.load_guerilla_config)
        self.file_menu.insert_separator("Exit")

        self.settings_menu.delete(0, "end")  # clear the menu
        self.settings_menu.add_command(label="Set tags directory",
                                       command=self.set_tags_dir)
        self.settings_menu.add_command(label="Add tags directory",
                                       command=self.add_tags_dir)
        self.settings_menu.add_command(label="Remove tags directory",
                                       command=self.remove_tags_dir)

        self.settings_menu.add_separator()
        self.settings_menu.add_command(
            label="Edit config", command=self.show_config_file)
        self.settings_menu.add_separator()
        self.settings_menu.add_command(
            label="Load style", command=self.load_style)
        self.settings_menu.add_command(
            label="Save current style", command=self.make_style)

        # make the tools and tag set menus
        self.tools_menu = tk.Menu(self.main_menu, tearoff=0)
        self.compile_menu = tk.Menu(self.main_menu, tearoff=0)
        self.defs_menu = tk.Menu(self.main_menu, tearoff=0)

        self.main_menu.add_cascade(label="Tag set", menu=self.defs_menu)
        self.main_menu.add_cascade(label="Tools", menu=self.tools_menu)
        self.main_menu.add_cascade(label="Compile Tag", menu=self.compile_menu)
        try:
            if e_c.IS_WIN and not is_main_frozen():
                import hek_pool
                self.main_menu.add_command(label="Launch Pool",
                                           command=self.create_hek_pool_window)
        except ImportError:
            pass

        for i in range(len(self.handler_names)):
            self.defs_menu.add_command(command=lambda i=i:
                                       self.select_defs(i, manual=True))

        self.tools_menu.add_command(
            label="Dependency viewer", command=self.show_dependency_viewer)
        self.tools_menu.add_command(
            label="Tags directory scanner", command=self.show_tag_scanner)
        self.tools_menu.add_separator()
        self.tools_menu.add_command(
            label="Search and replace", command=self.show_search_and_replace)
        self.tools_menu.add_command(
            label="Scenario sauce scrubber", command=self.show_sauce_removal_window)
        self.tools_menu.add_separator()
        self.tools_menu.add_command(
            label="Bitmap converter",
            command=self.show_bitmap_converter_window)
        self.tools_menu.add_separator()
        self.tools_menu.add_command(
            label="Tag data extraction",
            command=self.show_data_extraction_window)

        self.compile_menu.add_command(
            label="Bitmap from dds texture(s)", command=self.bitmap_from_multiple_dds)
        self.compile_menu.add_command(
            label="Bitmap(s) from dds texture", command=self.bitmap_from_dds)
        self.compile_menu.add_command(
            label="Bitmap(s) from bitmap source", command=self.bitmap_from_bitmap_source)
        self.compile_menu.add_separator()
        self.compile_menu.add_command(
            label="Gbxmodel from jms", command=self.show_model_compiler_window)
        self.compile_menu.add_command(
            label="Physics from jms", command=self.physics_from_jms)
        self.compile_menu.add_separator()
        self.compile_menu.add_command(
            label="Hud_message_text from hmt", command=self.hud_message_text_from_hmt)
        self.compile_menu.add_command(
            label="String_list / unicode_string_list from txt", command=self.strings_from_txt)

        self.defs_menu.add_separator()
        self.handlers = list(self.handlers)
        self.handler_names = list(self.handler_names)

        self.select_defs(manual=False)
        self.tool_windows = {}
        self._mozzarilla_initialized = True

        self.make_window_panes()
        self.make_directory_frame(self.window_panes)
        self.make_io_text(self.window_panes)

        try:
            if self.config_file.data.header.flags.load_last_workspace:
                self.load_last_workspace()
        except AttributeError:
            pass

        if self.directory_frame is not None:
            self.directory_frame.highlight_tags_dir(self.tags_dir)
        self.apply_style()

    @property
    def tags_dir(self):
        try:
            return self.tags_dirs[self._curr_tags_dir_index]
        except IndexError:
            return None

    @property
    def data_dir(self):
        try:
            tags_dir = self.tags_dir
            if not tags_dir:
                return ""

            return join(dirname(tags_dir.rstrip(PATHDIV)), "data")
        except IndexError:
            return None

    @tags_dir.setter
    def tags_dir(self, new_val):
        handler = self.handlers[self._curr_handler_index]
        new_val = join(sanitize_path(new_val), '')  # ensure it ends with a \
        self.tags_dirs[self._curr_tags_dir_index] = handler.tagsdir = new_val

    def add_tags_dir(self, e=None, tags_dir=None, manual=True):
        if tags_dir is None:
            tags_dir = askdirectory(initialdir=self.tags_dir, parent=self,
                                    title="Select the tags directory to add")

        if not tags_dir:
            return

        tags_dir = join(sanitize_path(tags_dir), '')
        if tags_dir in self.tags_dirs:
            if manual:
                print("That tags directory already exists.")
            return

        self.tags_dirs.append(tags_dir)
        self.switch_tags_dir(index=len(self.tags_dirs) - 1, manual=False)

        if self.directory_frame is not None:
            self.directory_frame.add_root_dir(tags_dir)

        if manual:
            self.last_load_dir = tags_dir
            curr_index = self._curr_tags_dir_index
            print("Tags directory is currently:\n    %s\n" % self.tags_dir)

    def remove_tags_dir(self, e=None, index=None, manual=True):
        dirs_count = len(self.tags_dirs)
        # need at least 2 tags dirs to delete one manually
        if dirs_count < 2 and manual:
            return

        if index is None:
            index = self._curr_tags_dir_index

        new_index = self._curr_tags_dir_index
        if index <= new_index:
            new_index = max(0, new_index - 1)

        tags_dir = self.tags_dirs[index]
        del self.tags_dirs[index]
        if self.directory_frame is not None:
            self.directory_frame.del_root_dir(tags_dir)

        self.switch_tags_dir(index=new_index, manual=False)

        if manual:
            print("Tags directory is currently:\n    %s\n" % self.tags_dir)

    def set_tags_dir(self, e=None, tags_dir=None, manual=True):
        if tags_dir is None:
            tags_dir = askdirectory(initialdir=self.tags_dir, parent=self,
                                    title="Select the tags directory")

        if not tags_dir:
            return

        tags_dir = join(sanitize_path(tags_dir), '')
        if tags_dir in self.tags_dirs:
            print("That tags directory already exists.")
            return

        if self.directory_frame is not None:
            self.directory_frame.set_root_dir(tags_dir)
            self.directory_frame.highlight_tags_dir(self.tags_dir)
        self.tags_dir = tags_dir

        if manual:
            print("Tags directory is currently:\n    %s\n" % self.tags_dir)

    def switch_tags_dir(self, e=None, index=None, manual=True):
        if index is None:
            index = (self._curr_tags_dir_index + 1) % len(self.tags_dirs)
        if self._curr_tags_dir_index == index:
            return

        self._curr_tags_dir_index = index
        self.handler.tagsdir = self.tags_dir

        if self.directory_frame is not None:
            self.directory_frame.highlight_tags_dir(self.tags_dir)

        for handler in self.handlers:
            try: handler.tagsdir = self.tags_dir
            except Exception: pass

        if manual:
            self.last_load_dir = self.tags_dir
            print("Tags directory is currently:\n    %s\n" % self.tags_dir)

    def apply_config(self, e=None):
        Binilla.apply_config(self)
        config_data = self.config_file.data
        mozz = config_data.mozzarilla
        self._curr_handler_index = mozz.selected_handler.data
        tags_dirs = mozz.tags_dirs
        load_dirs = mozz.load_dirs

        try:
            self.select_defs()
        except Exception:
            pass

        for i in range(len(self.tags_dirs)):
            self.remove_tags_dir(i, manual=False)

        self._curr_tags_dir_index = 0
        for tags_dir in tags_dirs:
            self.add_tags_dir(tags_dir=tags_dir.path, manual=False)
        self.switch_tags_dir(
            index=min(mozz.last_tags_dir, len(self.tags_dirs)), manual=False)

        for s in ("last_data_load_dir", "jms_load_dir",
                  "bitmap_load_dir")[:len(load_dirs)]:
            try: setattr(self, s, load_dirs[s].path)
            except IndexError: pass

        if not self.tags_dir:
            self.tags_dir = self.curr_dir + "%stags%s" % (PATHDIV, PATHDIV)

        for handler in self.handlers:
            try: handler.tagsdir = self.tags_dir
            except Exception: pass

    def load_last_workspace(self):
        if self._mozzarilla_initialized:
            Binilla.load_last_workspace(self)

    def load_guerilla_config(self):
        fp = askopenfilename(initialdir=self.last_load_dir, parent=self,
                             title="Select the tag to load",
                             filetypes=(('Guerilla config', '*.cfg'),
                                        ('All', '*')))

        if not fp:
            return

        self.last_load_dir = dirname(fp)
        workspace = guerilla_workspace_def.build(filepath=fp)

        pad_x = self.io_text.winfo_rootx() - self.winfo_x()
        pad_y = self.io_text.winfo_rooty() - self.winfo_y()

        tl_corner = workspace.data.window_header.t_l_corner
        br_corner = workspace.data.window_header.b_r_corner

        self.geometry("%sx%s+%s+%s" % (
            br_corner.x - tl_corner.x - pad_x,
            br_corner.y - tl_corner.y - pad_y,
            tl_corner.x, tl_corner.y))

        for tag in workspace.data.tags:
            if not tag.is_valid_tag:
                continue

            windows = self.load_tags(tag.filepath)
            if not windows:
                continue

            w = windows[0]

            tl_corner = tag.window_header.t_l_corner
            br_corner = tag.window_header.b_r_corner

            self.place_window_relative(w, pad_x + tl_corner.x,
                                          pad_y + tl_corner.y)
            w.geometry("%sx%s" % (br_corner.x - tl_corner.x,
                                  br_corner.y - tl_corner.y))

    def load_tags(self, filepaths=None, def_id=None):
        tags_dir = self.tags_dir
        # if there is not tags directory, this can be loaded normally
        if tags_dir is None:
            return Binilla.load_tags(self, filepaths, def_id)

        if isinstance(filepaths, tk.Event):
            filepaths = None
        if filepaths is None:
            filetypes = [('All', '*')]
            defs = self.handler.defs
            for id in sorted(defs.keys()):
                filetypes.append((id, defs[id].ext))
            filepaths = askopenfilenames(initialdir=self.last_load_dir,
                                         filetypes=filetypes, parent=self,
                                         title="Select the tag to load")
            if not filepaths:
                return ()

        if isinstance(filepaths, str):
            # account for a stupid bug with certain versions of windows
            if filepaths.startswith('{'):
                filepaths = re.split("\}\W\{", filepaths[1:-1])
            else:
                filepaths = (filepaths, )

        sani = sanitize_path
        handler_name = self.handler_names[self._curr_handler_index]

        sanitized_paths = [sani(path) for path in filepaths]

        # make sure all the chosen tag paths are relative
        # to the current tags directory if they must be
        last_load_dir = self.last_load_dir
        if handler_name in self.tags_dir_relative:
            for i in range(len(sanitized_paths)):
                path = sanitized_paths[i]
                if not path:
                    # path is empty, so making a new tag
                    continue
                elif is_in_dir(path, tags_dir, 0):
                    # make the path relative to the tags_dir
                    last_load_dir = dirname(path)
                    sanitized_paths[i] = relpath(path, tags_dir)
                    continue

                print("Specified tag(s) are not located in the tags directory")
                return ()

        windows = Binilla.load_tags(self, sanitized_paths, def_id)
        self.last_load_dir = last_load_dir

        if not windows:
            print("You might need to change the tag set to load these tag(s).")
            return ()

        return windows

    def load_tag_as(self, e=None):
        '''Prompts the user for a tag to load and loads it.'''
        if self.def_selector_window:
            return

        filetypes = [('All', '*')]
        defs = self.handler.defs
        for def_id in sorted(defs.keys()):
            filetypes.append((def_id, defs[def_id].ext))

        fp = askopenfilename(initialdir=self.last_load_dir,
                             filetypes=filetypes, parent=self,
                             title="Select the tag to load")

        if not fp:
            return

        self.last_load_dir = dirname(fp)
        dsw = DefSelectorWindow(
            self, title="Which tag is this", action=lambda def_id:
            self.load_tags(filepaths=fp, def_id=def_id))
        self.def_selector_window = dsw
        self.place_window_relative(self.def_selector_window, 30, 50)

    def make_config(self, filepath=None):
        if filepath is None:
            filepath = self.config_path

        # create the config file from scratch
        self.config_file = self.config_def.build()
        self.config_file.filepath = filepath

        data = self.config_file.data

        # make sure these have as many entries as they're supposed to
        for block in (data.directory_paths, data.widgets.depths, data.colors):
            block.extend(len(block.NAME_MAP))

        tags_dirs = data.mozzarilla.tags_dirs
        for tags_dir in self.tags_dirs:
            tags_dirs.append()
            tags_dirs[-1].path = tags_dir

        self.update_config()

        c_hotkeys = data.hotkeys
        c_tag_window_hotkeys = data.tag_window_hotkeys

        for k_set, b in ((default_hotkeys, c_hotkeys),
                         (default_tag_window_hotkeys, c_tag_window_hotkeys)):
            default_keys = k_set
            hotkeys = b
            for combo, method in k_set.items():
                hotkeys.append()
                keys = hotkeys[-1].combo

                modifier, key = read_hotkey_string(combo)
                keys.modifier.set_to(modifier)
                keys.key.set_to(key)

                hotkeys[-1].method.set_to(method)

    def make_tag_window(self, tag, *, focus=True, window_cls=None,
                        is_new_tag=False):
        if window_cls is None:
            window_cls = HaloTagWindow
        w = Binilla.make_tag_window(self, tag, focus=focus,
                                    window_cls=window_cls,
                                    is_new_tag=is_new_tag)
        self.update_tag_window_title(w)
        try:
            try:
                w.iconbitmap(join(this_curr_dir, 'mozzarilla.ico'))
            except Exception:
                w.iconbitmap(join(this_curr_dir, 'icons', 'mozzarilla.ico'))
        except Exception:
            pass

        return w

    def make_window_panes(self):
        self.window_panes = tk.PanedWindow(
            self.root_frame, sashrelief='raised', sashwidth=8,
            bd=self.frame_depth, bg=self.frame_bg_color)
        self.window_panes.pack(anchor='nw', fill='both', expand=True)

    def make_io_text(self, master=None):
        if not self._initialized:
            return
        if master is None:
            master = self.root_frame
        Binilla.make_io_text(self, master)

    def make_directory_frame(self, master=None):
        if not self._initialized:
            return
        if master is None:
            master = self.root_frame
        self.directory_frame = DirectoryFrame(self)
        self.directory_frame.pack(expand=True, fill='both')

    def new_tag(self, e=None):
        if self.def_selector_window:
            return

        dsw = DefSelectorWindow(
            self, title="Select a tag to create", action=lambda def_id:
            self.load_tags(filepaths='', def_id=def_id))
        self.def_selector_window = dsw
        self.place_window_relative(self.def_selector_window, 30, 50)

    def save_tag(self, tag=None):
        if isinstance(tag, tk.Event):
            tag = None
        if tag is None:
            if self.selected_tag is None:
                return
            tag = self.selected_tag

        if tag is self.config_file:
            return self.save_config()

        # change the tags filepath to be relative to the current tags directory
        if hasattr(tag, "rel_filepath"):
            tag.filepath = join(tag.tags_dir, tag.rel_filepath)

        return Binilla.save_tag(self, tag)

    def save_tag_as(self, tag=None, filepath=None):
        if isinstance(tag, tk.Event):
            tag = None
        if tag is None:
            if self.selected_tag is None:
                return
            tag = self.selected_tag

        if not hasattr(tag, "serialize"):
            return

        if filepath is None:
            ext = tag.ext
            filepath = asksaveasfilename(
                initialdir=dirname(tag.filepath), parent=self,
                defaultextension=ext, title="Save tag as...",
                filetypes=[(ext[1:], "*" + ext), ('All', '*')])
        else:
            filepath = tag.filepath

        if not filepath:
            return

        # make sure to flush any changes made using widgets to the tag
        w = self.get_tag_window_by_tag(tag)

        # make sure the filepath is sanitized
        filepath = sanitize_path(filepath)

        handler = tag.handler
        tags_dir = self.tags_dir
        tagsdir_rel = handler.tagsdir_relative

        try:
            self.last_load_dir = dirname(filepath)
            if tagsdir_rel:
                filepath = relpath(filepath, tag.tags_dir)

                if tag.tags_dir != tags_dir:
                    # trying to save outside tags directory
                    messagebox.showerror(
                        "Saving outside tags directory", ("Cannot save:\n\n" +
                         "    %s\n\noutside the tags directory:\n\n    %s\n\n" +
                         "Change the tags directory back to save this tag.") %
                        (filepath, tag.tags_dir), parent=self.focus_get())
                    return

            self.add_tag(tag, filepath)
            w.save(temp=False)
        except PermissionError:
            print("This program does not have permission to save to this folder.\n"
                  "Could not save: %s" % filepath)
        except Exception:
            print(format_exc())
            raise IOError("Could not save: %s" % filepath)

        self.update_tag_window_title(w)
        return tag

    def get_handler(self, handler_name=None, initialize=True):
        try:
            menu_index = self.handler_names.index(handler_name)
            handler = self.handlers[menu_index]

            if isinstance(handler, type) and initialize:
                self.handlers[menu_index] = handler = handler(debug=self.debug)

            return handler
        except Exception:
            return None

    def select_defs(self, menu_index=None, manual=True):
        if menu_index is None:
            menu_index = self._curr_handler_index
            try:
                # make sure the current handler index is valid
                self.handler_names[menu_index]
            except Exception:
                menu_index = 0

        try:
            handler_name = self.handler_names[menu_index]
        except Exception:
            print(format_exc())
            handler_name = None

        handler = self.get_handler(handler_name, False)
        if handler is None or handler is self.handler:
            return

        if manual:
            print("Changing tag set to %s" % handler_name)
            self.io_text.update_idletasks()

        if isinstance(handler, type):
            self.handlers[menu_index] = handler(debug=self.debug)

        self.handler = self.handlers[menu_index]
        self._curr_handler_index = menu_index
        for i in range(len(self.handler_names)):
            self.defs_menu.entryconfig(i, label=self.handler_names[i])

        self.defs_menu.entryconfig(self._curr_handler_index,
                                   label=("%s %s" % (handler_name, u'\u2713')))

        if manual:
            print("    Finished")

        self.config_file.data.mozzarilla.selected_handler.data = menu_index

    def set_handler(self, handler=None, index=None, name=None):
        if handler is not None:
            handler_index = self.handlers.index(handler)
            self._curr_handler_index = handler_index
            self.handler = handler
        elif index is not None:
            self._curr_handler_index = handler_index
            self.handler = self.handlers[handler_index]
        elif name is not None:
            handler_index = self.handler_names.index(name)
            self._curr_handler_index = handler_index
            self.handler = self.handlers[handler_index]

    def show_tool_window(self, window_name, window_class,
                         needs_tag_refs=False):
        w = self.tool_windows.get(window_name)
        if w is not None:
            try: del self.tool_windows[window_name]
            except Exception: pass
            try: w.destroy()
            except Exception: pass
            return

        if needs_tag_refs and not hasattr(self.handler, 'tag_ref_cache'):
            print("Change the current tag set.")
            return

        self.tool_windows[window_name] = w = window_class(self)
        w.window_name = window_name
        self.place_window_relative(w, 30, 50); w.focus_set()

    def show_dependency_viewer(self, e=None):
        self.show_tool_window("dependency_window", DependencyWindow, True)

    def show_tag_scanner(self, e=None):
        self.show_tool_window("tag_scanner_window", TagScannerWindow, True)

    def show_bitmap_converter_window(self, e=None):
        self.show_tool_window("show_bitmap_converter_window", BitmapConverterWindow)

    def show_data_extraction_window(self, e=None):
        self.show_tool_window("data_extraction_window", DataExtractionWindow, True)

    def show_model_compiler_window(self, e=None):
        self.show_tool_window("model_compiler_window", ModelCompilerWindow, True)

    def show_search_and_replace(self, e=None):
        self.show_tool_window("s_and_r_window", SearchAndReplaceWindow)

    def show_sauce_removal_window(self, e=None):
        self.show_tool_window("sauce_removal_window", SauceRemovalWindow)

    def create_hek_pool_window(self, e=None):
        try:
            launcher = Thread(
                target=do_subprocess, daemon=True, args=("pythonw", ),
                kwargs=dict(exec_args=("-m", "hek_pool.run"),
                            proc_controller=ProcController(abandon=True)))
            launcher.start()
        except Exception:
            print("Could not open HEK Pool")

    def update_config(self, config_file=None):
        if config_file is None:
            config_file = self.config_file
        Binilla.update_config(self, config_file)

        config_data = config_file.data
        mozz = config_data.mozzarilla
        tags_dirs = mozz.tags_dirs
        load_dirs = mozz.load_dirs

        mozz.selected_handler.data = self._curr_handler_index
        mozz.last_tags_dir = self._curr_tags_dir_index

        sani = sanitize_path
        del tags_dirs[:]
        for tags_dir in self.tags_dirs:
            tags_dirs.append()
            tags_dirs[-1].path = sani(tags_dir)

        if len(load_dirs.NAME_MAP) > len(load_dirs):
            load_dirs.extend(len(load_dirs.NAME_MAP) - len(load_dirs))

        for s in ("last_data_load_dir", "jms_load_dir", "bitmap_load_dir"):
            try: load_dirs[s].path = getattr(self, s)
            except IndexError: pass

        if mozz.flags.show_hierarchy_window and mozz.flags.show_console_window:
            try:
                # idk if this value can ever be negative, so i'm using abs
                mozz.sash_position = abs(self.window_panes.sash_coord(0)[0])
            except Exception:
                pass

    def update_tag_window_title(self, window):
        if not hasattr(window, 'tag'):
            return

        tag = window.tag
        if tag is self.config_file:
            window.update_title('%s %s config' % (self.app_name, self.version))

        if not hasattr(tag, 'tags_dir'):
            return

        tags_dir = tag.tags_dir

        try:
            if tag is self.config_file or not tags_dir:
                return
            handler_name = self.handler_names[self._curr_handler_index]
            if handler_name not in self.tags_dir_relative:
                window.update_title()
                return

            try:
                show_full = self.config_file.data.mozzarilla.\
                            flags.show_full_tags_directory
            except Exception:
                show_full = False

            tags_dir_str = tags_dir[:-1]
            if not show_full:
                tags_dir_str = tags_dir_str.split(PATHDIV)
                if tags_dir_str[-1].lower() != "tags":
                    tags_dir_str = tags_dir_str[-1]
                else:
                    tags_dir_str = tags_dir_str[-2]

            handler_i = self.handlers.index(window.handler)

            title = "[%s][%s][%s]" % (
                self.handler_names[handler_i], tags_dir_str, tag.rel_filepath)
        except Exception:
            pass
        window.update_title(title)

    def apply_style(self, seen=None):
        if not self._initialized:
            return

        Binilla.apply_style(self, seen)
        try:
            try:
                mozz = self.config_file.data.mozzarilla
                show_hierarchy = mozz.flags.show_hierarchy_window
                show_console = mozz.flags.show_console_window
                sash_pos = mozz.sash_position
                self.window_panes.forget(self.directory_frame)
                self.window_panes.forget(self.io_frame)

                if show_hierarchy:
                    self.directory_frame.pack(fill='both', expand=True)
                    self.window_panes.add(self.directory_frame)
                if show_console:
                    self.io_frame.pack(fill='both', expand=True)
                    self.window_panes.add(self.io_frame)

                # if both window panes are shown, we need to position the sash
                if show_hierarchy and show_console and sash_pos != 0:
                    try:
                        self.update_idletasks()
                        self.window_panes.sash_place(0, sash_pos, 1)
                    except Exception:
                        pass
            except Exception:
                print(format_exc())
        except AttributeError: print(format_exc())
        except Exception: print(format_exc())

    def bitmap_from_dds(self, e=None):
        bitmap_from_dds(self)

    def bitmap_from_bitmap_source(self, e=None):
        bitmap_from_bitmap_source(self)

    def bitmap_from_multiple_dds(self, e=None):
        bitmap_from_multiple_dds(self)

    def physics_from_jms(self, e=None):
        physics_from_jms(self)

    def hud_message_text_from_hmt(self, e=None):
        hud_message_text_from_hmt(self)

    def strings_from_txt(self, e=None):
        strings_from_txt(self)
