import os
import tkinter as tk

from os.path import dirname, join, splitext, relpath
from time import time
from threading import Thread
from tkinter.filedialog import askdirectory, askopenfilename, asksaveasfilename
from tkinter import messagebox
from traceback import format_exc

from binilla.widgets import BinillaWidget
from supyr_struct.defs.constants import *
from supyr_struct.defs.util import *


tool_command_help = {
    "animations": "",
    "bitmap": "",
    "bitmaps": "",
    "build-cache-file": "",
    "build-cache-file-ex": "",
    "build-cache-file-new": "",
    "build-cpp-definition": "",
    "build-packed-file": "",
    "collision-geometry": "",
    "compile-scripts": "",
    "compile-shader-postprocess": "",
    "help": "",
    "hud-messages": "",
    "import-device-defaults": "",
    "import-structure-lightmap-uvs": "",
    "lightmaps": "",
    "merge-scenery": "",
    "model": "",
    "physics": "",
    "process-sounds": "",
    "remove-os-tag-data": "",
    "runtime-cache-view": "",
    "sounds": "",
    "sounds_by_type": "",
    "strings": "",
    "structure": "",
    "structure-breakable-surfaces": "",
    "structure-lens-flares": "",
    "tag-load-test": "",
    "unicode-strings": "",
    "windows-font": "",
    "zoners_model_upgrade": "",
    }


tool_commands = {
    "animations": (
        ("source-directory", ""),
        ),
    "bitmap": (
        ("source-file", ""),
        ),
    "bitmaps": (
        ("source-directory", ""),
        ),
    "build-cache-file": (
        ("scenario-name", ""),
        ),
    "build-cache-file-ex": (
        ("mod-name",           ""),
        ("create-anew",         0),
        ("store-resources",     0),
        ("use-memory-upgrades", 0),
        ("scenario-name",      ""),
        ),
    "build-cache-file-new": (
        ("create-anew",         0),
        ("store-resources",     0),
        ("use-memory-upgrades", 0),
        ("scenario-name",      ""),
        ),
    "build-cpp-definition": (
        ("tag-group",         ""),
        ("add-boost-asserts",  0),
        ),
    "build-packed-file": (
        ("source-directory",    ""),
        ("output-directory",    ""),
        ("file-definition-xml", ""),
        ),
    "collision-geometry": (
        ("source-directory", ""),
        ),
    "compile-scripts": (
        ("scenario-name", ""),
        ),
    "compile-shader-postprocess": (
        ("shader-directory", ""),
        ),
    "help": (
        ("os-tool-command", "", (
            "animations",
            "bitmap",
            "bitmaps",
            "build-cache-file",
            "build-cache-file-ex",
            "build-cache-file-new",
            "build-cpp-definition",
            "build-packed-file",
            "collision-geometry",
            "compile-scripts",
            "compile-shader-postprocess",
            "hud-messages",
            "import-device-defaults",
            "import-structure-lightmap-uvs",
            "lightmaps",
            "merge-scenery",
            "model",
            "physics",
            "process-sounds",
            "remove-os-tag-data",
            "runtime-cache-view",
            "sounds",
            #"sounds_by_type",
            "structure",
            "structure-breakable-surfaces",
            "structure-lens-flares",
            "tag-load-test",
            "unicode-strings",
            "windows-font",
            #"zoners_model_upgrade",
            )
         ),
        ),
    "hud-messages": (
        ("path",          ""),
        ("scenario-name", ""),
        ),
    "import-device-defaults": (
        ("type",          "", ("defaults", "profiles")),
        ("savegame-path", ""),
        ),
    "import-structure-lightmap-uvs": (
        ("structure-bsp", ""),
        ("obj-file",      ""),
        ),
    "lightmaps": (
        ("scenario",        ""),
        ("bsp-name",        ""),
        ("quality",        0.0),
        ("stop-threshold", 0.5),
        ),
    "merge-scenery": (
        ("source-scenario",      ""),
        ("destination-scenario", ""),
        ),
    "model": (
        ("source-directory", ""),
        ),
    "physics": (
        ("source-file", ""),
        ),
    "process-sounds": (
        ("root-path", ""),
        ("substring", ""),
        ("effect", "gain+",
             ("gain+", "gain-", "gain=",
              "maximum-distance", "minimum-distance"),
             ),
        ("value", 0.0),
        ),
    "remove-os-tag-data": (
        ("tag-name",         ""),
        ("tag-type",         ""),
        ("recursive", 0, (0, 1)),
        ),
    "runtime-cache-view": (),
    "sounds": (
        ("directory-name",            ""),
        ("platform",                  "", ("ogg", "xbox", "wav")),
        ("use-high-quality(ogg_only)", 1,  (0, 1)),
        ),
    #"sounds_by_type": (
    #    ("directory-name", ""),
    #    ("type",           ""),
    #    ),
    "strings": (
        ("source-directory", ""),
        ),
    "structure": (
        ("scenario-directory", ""),
        ("bsp-name",           ""),
        ),
    "structure-breakable-surfaces": (
        ("structure-name",   ""),
        ),
    "structure-lens-flares": (
        ("bsp-name", ""),
        ),
    "tag-load-test": (
        ("tag-name", ""),
        ("group",    ""),
        ("prompt-to-continue",       0, (0, 1)),
        ("load-non-resolving-refs",  0, (0, 1)),
        ("print-size",               0, (0, 1)),
        ("verbose",                  0, (0, 1)),
        ),
    "unicode-strings": (
        ("source-directory", ""),
        ),
    "windows-font": (),
    #"zoners_model_upgrade": (),
    }


class HekToolWrapperWindow(tk.Toplevel, BinillaWidget):
    app_root = None
    config_file = None
    process_threads = ()

    def __init__(self, app_root, *args, **kwargs): 
        self.handler = handler = app_root.handler
        self.app_root = app_root
        self.config_file = getattr(app_root, "config_file", None)
        self.process_threads = {}
        kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)

        self.title("HEK Tool wrapper")
        self.minsize(width=400, height=600)

        self.main_menu = tk.Menu(self)
        self.main_menu.add_command(label="")
        self.file_menu = tk.Menu(self.main_menu, tearoff=0)
        self.edit_menu = tk.Menu(self.main_menu, tearoff=0)
        self.config(menu=self.main_menu)
        self.main_menu.add_cascade(label="File", menu=self.file_menu)
        self.main_menu.add_cascade(label="Edit", menu=self.edit_menu)

        # make the tkinter variables
        self.directory_path = tk.StringVar(self)

        # make the frames
        '''
        self.directory_frame = tk.LabelFrame(self, text="Directory to scan")
        self.def_ids_frame = tk.LabelFrame(
            self, text="Select which tag types to scan")
        self.button_frame = tk.Frame(self.def_ids_frame)

        self.directory_entry = tk.Entry(
            self.directory_frame, textvariable=self.directory_path)
        self.dir_browse_button = tk.Button(
            self.directory_frame, text="Browse", command=self.dir_browse)

        self.def_ids_scrollbar = tk.Scrollbar(
            self.def_ids_frame, orient="vertical")
        self.def_ids_listbox = tk.Listbox(
            self.def_ids_frame, selectmode='multiple', highlightthickness=0,
            yscrollcommand=self.def_ids_scrollbar.set)
        self.def_ids_scrollbar.config(command=self.def_ids_listbox.yview)

        for w in (self.directory_entry, ):
            w.pack(padx=(4, 0), pady=2, side='left', expand=True, fill='x')

        for w in (self.dir_browse_button, ):
            w.pack(padx=(0, 4), pady=2, side='left')

        for w in (self.scan_button, self.cancel_button):
            w.pack(padx=4, pady=2)

        self.def_ids_scrollbar.pack(side='left', fill="y")
        self.directory_frame.pack(fill='x', padx=1)'''
        self.apply_style()

    def apply_style(self):
        self.config(bg=self.default_bg_color)
        for w in():#self.directory_frame, ):
            w.config(fg=self.text_normal_color, bg=self.default_bg_color)

        self.button_frame.config(bg=self.default_bg_color)

        for w in ():#self.dir_browse_button, ):
            w.config(bg=self.button_color, activebackground=self.button_color,
                     fg=self.text_normal_color, bd=self.button_depth,
                     disabledforeground=self.text_disabled_color)

        for w in ():#self.directory_entry, ):
            w.config(bd=self.entry_depth,
                bg=self.entry_normal_color, fg=self.text_normal_color,
                disabledbackground=self.entry_disabled_color,
                disabledforeground=self.text_disabled_color,
                selectbackground=self.entry_highlighted_color,
                selectforeground=self.text_highlighted_color)

    def add_tool_path(self):
        pass

    def remove_tool_path(self):
        pass

    def add_tool_cmd(self):
        pass

    def remove_tool_cmd(self):
        pass

    def tool_path_browse(self):
        if self._scanning:
            return
        filepath = askopenfilename(initialdir=self.tool_path.get(),
                                   parent=self, title="Select Tool.exe")
        if not filepath:
            return

        filepath = sanitize_path(filepath)
        self.app_root.last_load_dir = dirname(filepath)
        self.tool_path.set(filepath)

    def destroy(self):
        if not self.process_threads:
            pass
        elif not messagebox.askyesnocancel(
                "Incomplete Tool processes running!",
                ("Currently running %s Tool processes. "
                 "Do you wish to cancel them and close this window?") %
                len(self.process_threads),
                icon='warning', parent=self):
            return
        tk.Toplevel.destroy(self)
