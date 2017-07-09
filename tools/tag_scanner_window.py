import os
import tkinter as tk

from os.path import dirname, join, splitext, relpath
from time import time
from threading import Thread
from tkinter.filedialog import askdirectory, asksaveasfilename
from traceback import format_exc

from binilla.widgets import BinillaWidget
from supyr_struct.defs.constants import *
from supyr_struct.defs.util import *


class TagScannerWindow(tk.Toplevel, BinillaWidget):
    app_root = None
    tags_dir = ''
    handler = None

    _scanning = False
    stop_scanning = False
    print_interval = 5

    listbox_index_to_def_id = ()

    def __init__(self, app_root, *args, **kwargs): 
        self.handler = handler = app_root.handler
        self.app_root = app_root
        kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)

        ext_id_map = handler.ext_id_map
        self.listbox_index_to_def_id = [
            ext_id_map[ext] for ext in sorted(ext_id_map.keys())
            if ext_id_map[ext] in handler.tag_ref_cache]

        tagset = app_root.handler_names[app_root._curr_handler_index]

        self.title("[%s] Tag directory scanner" % tagset)
        self.minsize(width=400, height=250)
        self.resizable(0, 0)

        # make the tkinter variables
        self.directory_path = tk.StringVar(self)
        self.logfile_path = tk.StringVar(self)

        # make the frames
        self.directory_frame = tk.LabelFrame(self, text="Directory to scan")
        self.logfile_frame = tk.LabelFrame(self, text="Output log filepath")
        self.def_ids_frame = tk.LabelFrame(
            self, text="Select which tag types to scan")
        self.button_frame = tk.Frame(self.def_ids_frame)

        self.scan_button = tk.Button(
            self.button_frame, text='Scan directory',
            width=20, command=self.scan_directory)
        self.cancel_button = tk.Button(
            self.button_frame, text='Cancel scan',
            width=20, command=self.cancel_scan)
        self.select_all_button = tk.Button(
            self.button_frame, text='Select all',
            width=20, command=self.select_all)
        self.deselect_all_button = tk.Button(
            self.button_frame, text='Deselect all',
            width=20, command=self.deselect_all)

        self.directory_entry = tk.Entry(
            self.directory_frame, textvariable=self.directory_path)
        self.dir_browse_button = tk.Button(
            self.directory_frame, text="Browse", command=self.dir_browse)

        self.logfile_entry = tk.Entry(
            self.logfile_frame, textvariable=self.logfile_path,)
        self.log_browse_button = tk.Button(
            self.logfile_frame, text="Browse", command=self.log_browse)

        self.def_ids_scrollbar = tk.Scrollbar(
            self.def_ids_frame, orient="vertical")
        self.def_ids_listbox = tk.Listbox(
            self.def_ids_frame, selectmode='multiple', highlightthickness=0)
        self.def_ids_scrollbar.config(command=self.def_ids_listbox.yview)

        for def_id in self.listbox_index_to_def_id:
            tag_ext = handler.id_ext_map[def_id].split('.')[-1]
            self.def_ids_listbox.insert('end', tag_ext)

            # these tag types are massive, so by
            # default dont set them to be scanned
            if def_id in ("sbsp", "scnr"):
                continue
            self.def_ids_listbox.select_set('end')

        for w in (self.directory_entry, self.logfile_entry):
            w.pack(padx=(4, 0), pady=2, side='left', expand=True, fill='x')

        for w in (self.dir_browse_button, self.log_browse_button):
            w.pack(padx=(0, 4), pady=2, side='left')

        for w in (self.scan_button, self.cancel_button):
            w.pack(padx=4, pady=2)

        for w in (self.deselect_all_button, self.select_all_button):
            w.pack(padx=4, pady=2, side='bottom')

        self.def_ids_listbox.pack(side='left', fill="both", expand=True)
        self.def_ids_scrollbar.pack(side='left', fill="y")
        self.button_frame.pack(side='left', fill="y")

        self.directory_frame.pack(fill='x', padx=1)
        self.logfile_frame.pack(fill='x', padx=1)
        self.def_ids_frame.pack(fill='x', padx=1, expand=True)

        self.transient(app_root)

        self.directory_path.set(handler.tagsdir)
        self.logfile_path.set(join(handler.tagsdir, "tag_scanner.log"))
        self.apply_style()

    def apply_style(self):
        self.config(bg=self.default_bg_color)        
        for w in(self.directory_frame, self.logfile_frame, self.def_ids_frame):
            w.config(fg=self.text_normal_color, bg=self.default_bg_color)

        self.button_frame.config(bg=self.default_bg_color)

        for w in (self.scan_button, self.cancel_button,
                  self.select_all_button, self.deselect_all_button,
                  self.dir_browse_button, self.log_browse_button):
            w.config(bg=self.button_color, activebackground=self.button_color,
                     fg=self.text_normal_color, bd=self.button_depth,
                     disabledforeground=self.text_disabled_color)

        for w in (self.directory_entry, self.logfile_entry):
            w.config(bd=self.entry_depth,
                bg=self.entry_normal_color, fg=self.text_normal_color,
                disabledbackground=self.entry_disabled_color,
                disabledforeground=self.text_disabled_color,
                selectbackground=self.entry_highlighted_color,
                selectforeground=self.text_highlighted_color)

        self.def_ids_listbox.config(
            bg=self.enum_normal_color, fg=self.text_normal_color,
            selectbackground=self.enum_highlighted_color,
            selectforeground=self.text_highlighted_color)

    def deselect_all(self):
        if self._scanning:
            return
        self.def_ids_listbox.select_clear(0, 'end')

    def select_all(self):
        if self._scanning:
            return
        for i in range(len(self.listbox_index_to_def_id)):
            self.def_ids_listbox.select_set(i)

    def get_tag(self, filepath):
        handler = self.handler
        def_id = handler.get_def_id(filepath)

        try:
            tag = handler.get_tag(filepath, def_id)
        except KeyError:
            tag = None
        try:
            if tag is None:
                return handler.build_tag(
                    filepath=join(self.tags_dir, filepath))
        except Exception:
            pass
        return tag

    def dir_browse(self):
        if self._scanning:
            return
        dirpath = askdirectory(initialdir=self.directory_path.get(),
                               parent=self, title="Select directory to scan")

        if not dirpath:
            return

        dirpath = sanitize_path(dirpath)
        if not dirpath.endswith(PATHDIV):
            dirpath += PATHDIV

        self.app_root.last_load_dir = dirname(dirpath)
        tags_dir = self.handler.tagsdir
        if not (is_in_dir(dirpath, tags_dir, 0) or
                join(dirpath.lower()) == join(tags_dir.lower())):
            print("Specified directory is not located within the tags directory")
            return

        self.directory_path.set(dirpath)

    def log_browse(self):
        if self._scanning:
            return
        filepath = asksaveasfilename(
            initialdir=dirname(self.logfile_entry.get()),
            title="Save scan log to...", parent=self,
            filetypes=(("tag scanner log", "*.log"), ('All', '*')))

        if not filepath:
            return

        filepath = sanitize_path(filepath)
        self.app_root.last_load_dir = dirname(filepath)

        self.logfile_path.set(filepath)

    def destroy(self):
        self.app_root.tool_windows.pop("tag_scanner_window", None)
        self.stop_scanning = True
        tk.Toplevel.destroy(self)

    def cancel_scan(self):
        self.stop_scanning = True

    def scan_directory(self):
        if self._scanning:
            return
        try: self.scan_thread.join(1.0)
        except Exception: pass
        self.scan_thread = Thread(target=self._scan_directory)
        self.scan_thread.daemon = True
        self.scan_thread.start()

    def _scan_directory(self):
        self._scanning = True
        try:
            self.scan()
        except Exception:
            print(format_exc())
        self._scanning = False

    def scan(self):
        app = self.app_root
        handler = self.handler
        sani = sanitize_path
        self.stop_scanning = False

        tags_dir = self.tags_dir = self.handler.tagsdir
        dirpath = sani(self.directory_path.get())
        logpath = sani(self.logfile_path.get())

        if not (is_in_dir(dirpath, tags_dir, 0) or
                join(dirpath.lower()) == join(tags_dir.lower())):
            print("Specified directory is not located within the tags directory")
            return

        #this is the string to store the entire debug log
        log_name = "HEK Tag Scanner log"
        debuglog = "\n%s%s%s\n\n" % (
            "-"*30, log_name, "-" * (50-len(log_name)))
        debuglog += "tags directory = %s\nscan directory = %s\n\n" % (
            tags_dir, dirpath)
        debuglog += "broken dependencies are listed below\n"

        get_nodes = handler.get_nodes_by_paths
        get_tagref_invalid = handler.get_tagref_invalid

        s_time = time()
        c_time = s_time
        p_int = self.print_interval

        all_tag_paths = {self.listbox_index_to_def_id[int(i)]: [] for i in
                         self.def_ids_listbox.curselection()}
        ext_id_map = handler.ext_id_map
        id_ext_map = handler.id_ext_map

        print("Locating tags...")

        for root, directories, files in os.walk(dirpath):
            if not root.endswith(PATHDIV):
                root += PATHDIV

            root = relpath(root, tags_dir)

            for filename in files:
                filepath = join(sani(root), filename)

                if time() - c_time > p_int:
                    c_time = time()
                    print(' '*4 + filepath)
                    app.update_idletasks()

                if self.stop_scanning:
                    print('Tag scanning operation cancelled.\n')
                    return

                tag_paths = all_tag_paths.get(
                    ext_id_map.get(splitext(filename)[-1].lower()))

                if tag_paths is not None:
                    tag_paths.append(filepath)

        # make the debug string by scanning the tags directory
        for def_id in sorted(all_tag_paths.keys()):
            tag_ref_paths = handler.tag_ref_cache[def_id]

            app.update_idletasks()
            print("Scanning '%s' tags..." % id_ext_map[def_id][1:])
            tags_coll = all_tag_paths[def_id]

            # always display the first tag's filepath
            c_time = time() - p_int + 1

            for filepath in sorted(tags_coll):
                if self.stop_scanning:
                    print('Tag scanning operation cancelled.\n')
                    break

                if time() - c_time > p_int:
                    c_time = time()
                    print(' '*4 + filepath)
                    app.update_idletasks()

                tag = self.get_tag(filepath)
                if tag is None:
                    print("    Could not load '%s'" % filepath)
                    continue

                try:
                    missed = get_nodes(tag_ref_paths, tag.data,
                                       get_tagref_invalid)

                    if not missed:
                        continue

                    debuglog += "\n\n%s\n" % filepath
                    block_name = None

                    for block in missed:
                        if block.NAME != block_name:
                            debuglog += '%s%s\n' % (' '*4, block.NAME)
                            block_name = block.NAME
                        try:
                            ext = '.' + block.tag_class.enum_name
                        except Exception:
                            ext = ''
                        debuglog += '%s%s\n' % (' '*8, block.STEPTREE + ext)

                except Exception:
                    print("    Could not scan '%s'" % tag.filepath)
                    continue

            if self.stop_scanning:
                break

        print("\nScanning took %s seconds." % int(time() - s_time))
        print("Writing logfile to %s..." % logpath)
        app.update_idletasks()

        # make and write to the logfile
        try:
            handler.make_log_file(debuglog, logpath)
            print("Scan completed.\n")
            return
        except Exception:
            pass

        print("Could not create log. Printing log to console instead.\n\n")
        for line in debuglog.split('\n'):
            try:
                print(line)
            except Exception:
                print("<COULD NOT PRINT THIS LINE>")

        print("Scan completed.\n")
