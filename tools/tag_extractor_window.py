import tkinter as tk
import mmap

from os.path import dirname, exists
from tkinter.filedialog import askopenfilename, askdirectory
from traceback import format_exc

from binilla.widgets import BinillaWidget
from reclaimer.os_v4_hek.handler import OsV4HaloHandler
from reclaimer.meta.halo1_map import get_map_version, get_map_header,\
     get_tag_index, get_index_magic, get_map_magic, decompress_map
from supyr_struct.defs.constants import *


class TagExtractorWindow(BinillaWidget, tk.Toplevel):
    app_root = None
    map_path = None
    out_dir = None

    index_magic = None  # the magic DETECTED for this type of map
    map_magic = None  # the magic CALCULATED for this map

    _map_loaded = False
    _extracting = False


    map_data = None  # the complete uncompressed map
    map_is_compressed = False

    # these are the different pieces of the map as parsed blocks
    map_header = None
    tag_index = None

    def __init__(self, app_root, *args, **kwargs):
        self.app_root = app_root
        kwargs.update(width=520, height=450, bd=0, highlightthickness=0)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)

        self.title("Tag Extractor")
        self.minsize(width=520, height=450)

        # make the tkinter variables
        self.map_path = tk.StringVar(self)
        self.out_dir = tk.StringVar(self)
        self.use_resource_names = tk.IntVar(self)
        self.use_hashcaches = tk.IntVar(self)
        self.use_heuristics = tk.IntVar(self)
        try:
            self.out_dir.set(self.app_root.tags_dir)
        except Exception:
            pass
        self.use_resource_names.set(1)

        self.map_path.set("Click browse to load a map for extraction")

        # make the window pane
        self.panes = tk.PanedWindow(self, sashwidth=4)

        # make the frames
        self.map_frame = tk.LabelFrame(self, text="Map to extract from")
        self.map_select_frame = tk.Frame(self.map_frame)
        self.map_action_frame = tk.Frame(self.map_frame)
        self.deprotect_frame = tk.LabelFrame(self, text="Deprotection settings")
        self.out_dir_frame = tk.LabelFrame(self, text="Location to extract to")

        self.explorer_frame = tk.Frame(self.panes)
        self.add_del_frame = tk.Frame(self.explorer_frame)
        self.queue_frame = tk.Frame(self.panes)

        self.panes.add(self.explorer_frame)
        self.panes.add(self.queue_frame)

        # make the entries
        self.map_path_entry = tk.Entry(
            self.map_select_frame, textvariable=self.map_path, state='disabled')
        self.map_path_browse_button = tk.Button(
            self.map_select_frame, text="Browse",
            command=self.map_path_browse, width=6)

        self.out_dir_entry = tk.Entry(
            self.out_dir_frame, textvariable=self.out_dir, state='disabled')
        self.out_dir_browse_button = tk.Button(
            self.out_dir_frame, text="Browse",
            command=self.out_dir_browse, width=6)
        '''
        self.def_ids_scrollbar = tk.Scrollbar(
            self.def_ids_frame, orient="vertical")
        self.def_ids_listbox = tk.Listbox(
            self.def_ids_frame, selectmode='multiple', highlightthickness=0)
        self.def_ids_scrollbar.config(command=self.def_ids_listbox.yview)
        '''
        self.map_info_text = tk.Text(
            self.map_frame, font=self.app_root.fixed_font,
            state='disabled', height=8)

        # make the buttons
        self.begin_button = tk.Button(
            self.map_action_frame, text="Begin extraction",
            command=self.begin_extraction)
        self.cancel_button = tk.Button(
            self.map_action_frame, text="Cancel extraction",
            command=self.cancel_extraction)

        self.use_resource_names_checkbutton = tk.Checkbutton(
            self.deprotect_frame, text="Use resource names",
            variable=self.use_resource_names)
        self.use_hashcaches_checkbutton = tk.Checkbutton(
            self.deprotect_frame, text="Use hashcaches",
            variable=self.use_hashcaches)
        self.use_heuristics_checkbutton = tk.Checkbutton(
            self.deprotect_frame, text="Use heuristics",
            variable=self.use_heuristics)
        self.deprotect_button = tk.Button(
            self.deprotect_frame, text="Deprotect names",
            command=self.deprotect_names)

        self.add_button = tk.Button(self.add_del_frame, text="Add",
                                    width=4, command=self.queue_add)
        self.del_button = tk.Button(self.add_del_frame, text="Del",
                                    width=4, command=self.queue_del)

        self.add_all_button = tk.Button(
            self.add_del_frame, text="Add\nAll", width=4,
            command=self.queue_add_all)
        self.del_all_button = tk.Button(
            self.add_del_frame, text="Del\nAll", width=4,
            command=self.queue_del_all)

        # pack everything
        self.map_path_entry.pack(
            padx=(4, 0), pady=2, side='left', expand=True, fill='x')
        self.map_path_browse_button.pack(padx=(0, 4), pady=2, side='left')

        self.cancel_button.pack(side='right', padx=4, pady=4)
        self.begin_button.pack(side='right', padx=4, pady=4)

        self.use_resource_names_checkbutton.pack(side='left', padx=4, pady=4)
        self.use_hashcaches_checkbutton.pack(side='left', padx=4, pady=4)
        self.use_heuristics_checkbutton.pack(side='left', padx=4, pady=4)
        self.deprotect_button.pack(side='right', padx=4, pady=4)

        self.map_select_frame.pack(fill='x', expand=True, padx=1)
        self.map_info_text.pack(fill='x', expand=True, padx=1)
        self.map_action_frame.pack(fill='x', expand=True, padx=1)

        self.out_dir_entry.pack(
            padx=(4, 0), pady=2, side='left', expand=True, fill='x')
        self.out_dir_browse_button.pack(padx=(0, 4), pady=2, side='left')

        self.add_button.pack(side='top', padx=2, pady=4)
        self.del_button.pack(side='top', padx=2, pady=(0, 20))
        self.add_all_button.pack(side='top', padx=2, pady=(20, 0))
        self.del_all_button.pack(side='top', padx=2, pady=4)

        self.explorer_frame.pack(fill='both', padx=1, expand=True)
        self.add_del_frame.pack(side='right', anchor='center')
        self.queue_frame.pack(fill='y', padx=1, expand=True)

        self.map_frame.pack(fill='x', padx=1)
        self.out_dir_frame.pack(fill='x', padx=1)
        self.deprotect_frame.pack(fill='x', padx=1)
        self.panes.pack(fill='both', expand=True)

        self.panes.paneconfig(self.explorer_frame, sticky='nsew')
        self.panes.paneconfig(self.queue_frame, sticky='nsew')

        self.apply_style()
        self.transient(app_root)

    def destroy(self):
        self.app_root.tool_windows.pop("tag_extractor_window", None)
        tk.Toplevel.destroy(self)

    def queue_add(self, e=None):
        if not self._map_loaded:
            return

    def queue_del(self, e=None):
        if not self._map_loaded:
            return

    def queue_add_all(self, e=None):
        if not self._map_loaded:
            return

    def queue_del_all(self, e=None):
        if not self._map_loaded:
            return

    def load_map(self, map_path=None):
        try:
            if map_path is None:
                map_path = self.map_path.get()
            if not exists(map_path):
                return

            self.map_path.set(map_path)

            with open(map_path, 'r+b') as f:
                comp_map_data = mmap.mmap(f.fileno(), 0)

            self.map_header = get_map_header(comp_map_data)
            self.map_data = decompress_map(comp_map_data, self.map_header)
            self.map_is_compressed = len(comp_map_data) < len(self.map_data)

            self.index_magic = get_index_magic(self.map_header)
            self.map_magic = get_map_magic(self.map_header)

            self.tag_index = get_tag_index(self.map_data, self.map_header)
            self._map_loaded = True

            self.display_map_info()
            try: comp_map_data.close()
            except Exception: pass
        except Exception:
            try: comp_map_data.close()
            except Exception: pass
            self.display_map_info(
                "Could not load map.\nCheck console window for error.")
            raise

    def deprotect_names(self, e=None):
        if not self._map_loaded:
            return
        self.reload_map_explorer()

    def begin_extraction(self, e=None):
        if not self._map_loaded:
            return

    def cancel_extraction(self, e=None):
        if not self._map_loaded:
            return

    def reload_map_explorer(self, mode="hierarchy"):
        if not self._map_loaded:
            return

    def display_map_info(self, string=None):
        if string is None:
            if not self._map_loaded:
                return
            try:
                header = self.map_header
                index = self.tag_index
                comp_size = "Uncompressed"
                if self.map_is_compressed:
                    comp_size = len(self.map_data)

                string = ((
                    "Engine == %s   Map type == %s   Decompressed size == %s\n" +
                    "Map name   == '%s'\n" +
                    "Build date == '%s'\n" +
                    "Index magic  == %s   Map magic == %s\n" +
                    "Index offset == %s   Tag count == %s\n" +
                    "Index header offset  == %s   Metadata length == %s\n" +
                    "Vertex object count  == %s   Model data offset == %s\n" +
                    "Indices object count == %s   Indices offset == %s"
                    ) %
                (get_map_version(header), header.map_type.enum_name, comp_size,
                 header.map_name,
                 header.build_date,
                 self.index_magic, self.map_magic,
                 index.tag_index_offset, index.tag_count,
                 header.tag_index_header_offset, header.tag_index_meta_len,
                 index.vertex_object_count, index.model_raw_data_offset,
                 index.indices_object_count, index.indices_offset,
                 ))
            except Exception:
                string = ""
                print(format_exc())
        try:
            self.map_info_text.config(state='normal')
            self.map_info_text.delete('1.0', 'end')
            self.map_info_text.insert('end', string)
        finally:
            self.map_info_text.config(state='disabled')

    def apply_style(self):
        self.config(bg=self.default_bg_color)
        # pane style
        self.panes.config(bd=self.frame_depth, bg=self.frame_bg_color)
        self.map_info_text.config(fg=self.text_disabled_color,
                                  bg=self.entry_disabled_color)

        # frame styles
        for w in (self.map_select_frame, self.map_action_frame,
                  self.explorer_frame, self.add_del_frame, self.queue_frame):
            w.config(bg=self.default_bg_color)

        # label frame styles
        for w in (self.map_frame, self.out_dir_frame, self.deprotect_frame):
            w.config(fg=self.text_normal_color, bg=self.default_bg_color)

        # button styles
        for w in (self.use_resource_names_checkbutton,
                  self.use_hashcaches_checkbutton,
                  self.use_heuristics_checkbutton,
                  self.add_button, self.del_button,
                  self.add_all_button, self.del_all_button,
                  self.deprotect_button, self.begin_button, self.cancel_button,
                  self.map_path_browse_button, self.out_dir_browse_button):
            w.config(bg=self.button_color, activebackground=self.button_color,
                     fg=self.text_normal_color, bd=self.button_depth,
                     disabledforeground=self.text_disabled_color)

        # entry styles
        for w in (self.map_path_entry, self.out_dir_entry):
            w.config(bd=self.entry_depth,
                bg=self.entry_normal_color, fg=self.text_normal_color,
                disabledbackground=self.entry_disabled_color,
                disabledforeground=self.text_disabled_color,
                selectbackground=self.entry_highlighted_color,
                selectforeground=self.text_highlighted_color)

    def map_path_browse(self):
        fp = askopenfilename(
            initialdir=self.app_root.last_load_dir,
            title="Select map to load", parent=self,
            filetypes=(("Halo mapfile", "*.map"),
                       ("Halo mapfile(extra sauce)", "*.yelo"),
                       ("All", "*")))

        if not fp:
            return

        fp = sanitize_path(fp)
        self.app_root.last_load_dir = dirname(fp)
        self.map_path.set(fp)
        self.load_map()

    def out_dir_browse(self):
        dirpath = askdirectory(initialdir=self.out_dir.get(), parent=self,
                               title="Select the extraction directory")

        if not dirpath:
            return

        dirpath = sanitize_path(dirpath)
        if not dirpath.endswith(PATHDIV):
            dirpath += PATHDIV

        self.out_dir.set(dirpath)
