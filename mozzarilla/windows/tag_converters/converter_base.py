#!/usr/bin/env python3
#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

from pathlib import Path
from threading import Thread
from time import time
from traceback import format_exc
import os
import threadsafe_tkinter as tk

from binilla.widgets.binilla_widget import BinillaWidget
from binilla.windows.filedialog import askopenfilename, askdirectory
from supyr_struct.util import path_replace, path_split
from mozzarilla import editor_constants as e_c

curr_dir = Path.cwd()

class ConverterBase(BinillaWidget):
    src_ext = "*"
    dst_ext = "*"
    _running_thread = None
    stop_conversion = False

    @property
    def src_exts(self): return (self.src_ext, )

    def __init__(self, app_root, *args, **kwargs):
        self.app_root = app_root
        BinillaWidget.__init__(self, app_root, *args, **kwargs)

    def setup_window(self, *args, **kwargs):
        kwargs.setdefault("title", "%s to %s convertor" %
                          (self.src_ext.capitalize(), self.dst_ext))
        self.title(kwargs.pop("title"))
        self.resizable(0, 0)
        self.update()
        try:
            self.iconbitmap(e_c.MOZZ_ICON_PATH)
        except Exception:
            pass

        # do path_replace to make sure the path works on linux
        tags_dir = Path(path_split(curr_dir, "tags", after=True))
        if self.app_root is not self and hasattr(self.app_root, "tags_dir"):
            tags_dir = getattr(self.app_root, "tags_dir")

        self.tags_dir = tk.StringVar(self, tags_dir)
        self.tag_path = tk.StringVar(self)

        # make the frames
        self.tags_dir_frame = tk.LabelFrame(self, text="Directory of tags")
        self.tag_path_frame = tk.LabelFrame(self, text="Single tag")

        # add the filepath boxes
        self.tags_dir_entry = tk.Entry(
            self.tags_dir_frame, textvariable=self.tags_dir)
        self.tags_dir_entry.config(width=70, state=tk.DISABLED)
        self.tag_path_entry = tk.Entry(
            self.tag_path_frame, textvariable=self.tag_path)
        self.tag_path_entry.config(width=70, state=tk.DISABLED)

        # add the buttons
        self.convert_dir_btn = tk.Button(
            self, text="Convert directory",
            width=15, command=self.convert_dir)
        self.convert_file_btn = tk.Button(
            self, text="Convert tag", width=15,
            command=self.convert_tag)
        self.tags_dir_browse_btn = tk.Button(
            self.tags_dir_frame, text="Browse",
            width=6, command=self.tags_dir_browse)
        self.tag_path_browse_btn = tk.Button(
            self.tag_path_frame, text="Browse",
            width=6, command=self.tag_path_browse)

        if self.app_root and self.app_root is not self:
            self.transient(self.app_root)

    def pack_widgets(self):
        self.tags_dir_entry.pack(expand=True, fill='x', side='left')
        self.tags_dir_browse_btn.pack(fill='x', side='left')
        self.tag_path_entry.pack(expand=True, fill='x', side='left')
        self.tag_path_browse_btn.pack(fill='x', side='left')

        self.tags_dir_frame.pack(expand=True, fill='both')
        self.convert_dir_btn.pack(fill='both', padx=5, pady=5)
        self.tag_path_frame.pack(expand=True, fill='both')
        self.convert_file_btn.pack(fill='both', padx=5, pady=5)

    def destroy(self):
        try:
            self.app_root.tool_windows.pop(self.window_name, None)
        except AttributeError:
            pass
        self.stop_conversion = True

    def apply_style(self, seen=None):
        super(ConverterBase, self).apply_style(seen)
        self.update()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry("%sx%s" % (w, h))
        self.minsize(width=w, height=h)

    def tags_dir_browse(self):
        dirpath = askdirectory(initialdir=self.tags_dir.get())
        if dirpath:
            self.tags_dir.set(dirpath)

    def tag_path_browse(self):
        initialdir = self.tag_path.get()
        if not initialdir:
            initialdir = self.tags_dir.get()

        filetypes = (("%s tag" % self.src_ext, "*.%s" % self.src_ext), )
        filetypes += tuple(("%s tag" % ext, "*.%s" % ext)
                          for ext in self.src_exts if ext != self.src_ext)
        filetypes += (('All', '*'), )
        tag_path = askopenfilename(
            initialdir=initialdir, filetypes=filetypes)
        if tag_path:
            self.tag_path.set(tag_path)

    def convert(self, tag_path):
        raise NotImplementedError("Override this method.")

    def lock_ui(self):
        for w in (self.tags_dir_browse_btn, self.tag_path_browse_btn,
                  self.convert_dir_btn, self.convert_file_btn):
            w.config(state=tk.DISABLED)

    def unlock_ui(self):
        for w in (self.tags_dir_browse_btn, self.tag_path_browse_btn,
                  self.convert_dir_btn, self.convert_file_btn):
            w.config(state=tk.NORMAL)

    def thread_wrapper(self, func, *args, **kwargs):
        if self._running_thread is not None:
            return

        try:
            self.lock_ui()
            func(*args, **kwargs)
        finally:
            self.unlock_ui()
            self._running_thread = None

    def convert_tag(self):
        if self._running_thread is None:
            new_thread = Thread(target=self.thread_wrapper,
                                args=(self.do_convert_tag, ))
            new_thread.daemon = True
            new_thread.start()

    def convert_dir(self):
        if self._running_thread is None:
            new_thread = Thread(target=self.thread_wrapper,
                                args=(self.do_convert_dir, ))
            new_thread.daemon = True
            new_thread.start()

    def do_convert_tag(self, tag_path=None, *args, **kwargs):
        start = time()
        part_of_batch = bool(tag_path)
        if tag_path is None:
            tag_path = self.tag_path.get()

        if not os.path.isfile(tag_path):
            return

        print(tag_path)

        try:
            dst_tag = self.convert(tag_path)
            if not part_of_batch and self.stop_conversion:
                print("    Conversion cancelled by user.")
                return

            if dst_tag:
                #print("    Saving to %s" % dst_tag.filepath)
                dst_tag.serialize(temp=False, backup=False, int_test=False)
        except Exception:
            print(format_exc())

        if not part_of_batch:
            print('    Finished. Took %s seconds.\n' % round(time() - start, 1))

    def do_convert_dir(self, *args, **kwargs):
        print("Converting  %s  to  %s" % (self.src_ext, self.dst_ext))
        start = time()
        valid_ext = "." + self.src_ext
        for root, dirs, files in os.walk(self.tags_dir.get()):
            for filename in files:
                if self.stop_conversion:
                    break

                filepath = Path(root, filename)
                if filepath.suffix.lower() == valid_ext:
                    self.do_convert_tag(str(filepath))

            if self.stop_conversion:
                print("    Conversion cancelled by user.")
                break

        print('    Finished. Took %s seconds.\n' % round(time() - start, 1))
