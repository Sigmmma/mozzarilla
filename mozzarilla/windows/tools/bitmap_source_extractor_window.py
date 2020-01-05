#!/usr/bin/env python3
#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

import os
import threadsafe_tkinter as tk
import zlib

from time import time
from threading import Thread
from struct import unpack, pack_into
from traceback import format_exc

from binilla.widgets.binilla_widget import BinillaWidget
from binilla.windows.filedialog import askdirectory
from mozzarilla import editor_constants as e_c

window_base_class = tk.Toplevel
if __name__ == "__main__":
    window_base_class = tk.Tk


class BitmapSourceExtractorWindow(BinillaWidget, window_base_class):
    _running_thread = None
    stop_extraction = False

    def __init__(self, app_root, *args, **kwargs):
        self.app_root = app_root

        if isinstance(self, tk.Toplevel):
            kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)

        window_base_class.__init__(self, app_root, *args, **kwargs)
        BinillaWidget.__init__(self, app_root, *args, **kwargs)

        self.title("Halo 1 & 2 bitmap source extractor")
        self.resizable(0, 0)
        self.update()
        try:
            self.iconbitmap(e_c.MOZZ_ICON_PATH)
        except Exception:
            print("Could not load window icon.")

        self.tags_dir = tk.StringVar(self)
        self.data_dir = tk.StringVar(self)
        self.tags_dir.set(e_c.WORKING_DIR.joinpath('tags'))
        self.data_dir.set(e_c.WORKING_DIR.joinpath('data'))

        # make the frames
        self.tags_dir_frame = tk.LabelFrame(self, text="Tags directory")
        self.data_dir_frame = tk.LabelFrame(self, text="Data directory")

        # add the filepath boxes
        self.tags_dir_entry = tk.Entry(
            self.tags_dir_frame, textvariable=self.tags_dir)
        self.tags_dir_entry.config(width=55, state=tk.DISABLED)
        self.data_dir_entry = tk.Entry(
            self.data_dir_frame, textvariable=self.data_dir)
        self.data_dir_entry.config(width=55, state=tk.DISABLED)

        # add the buttons
        self.extract_btn = tk.Button(
            self, text="Extract source files", width=22,
            command=self.extract)
        self.tags_dir_browse_btn = tk.Button(
            self.tags_dir_frame, text="Browse",
            width=6, command=self.tags_dir_browse)
        self.data_dir_browse_btn = tk.Button(
            self.data_dir_frame, text="Browse",
            width=6, command=self.data_dir_browse)

        # pack everything
        self.tags_dir_entry.pack(expand=True, fill='x', side='left')
        self.data_dir_entry.pack(expand=True, fill='x', side='left')
        self.tags_dir_browse_btn.pack(fill='x', side='left')
        self.data_dir_browse_btn.pack(fill='x', side='left')

        self.tags_dir_frame.pack(expand=True, fill='both')
        self.data_dir_frame.pack(expand=True, fill='both')
        self.extract_btn.pack(fill='both', padx=5, pady=5)

        if self.app_root is not self and self.app_root:
            self.transient(self.app_root)

        self.apply_style()

    def destroy(self):
        try:
            self.app_root.tool_windows.pop(self.window_name, None)
        except AttributeError:
            pass
        self.stop_extraction = True
        super(BitmapSourceExtractorWindow, self).destroy()

    def apply_style(self, seen=None):
        super(BitmapSourceExtractorWindow, self).apply_style(seen)
        self.update()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry("%sx%s" % (w, h))
        self.minsize(width=w, height=h)

    def tags_dir_browse(self):
        dirpath = askdirectory(initialdir=self.tags_dir.get())
        if dirpath:
            self.tags_dir.set(dirpath)

    def data_dir_browse(self):
        dirpath = askdirectory(initialdir=self.data_dir.get())
        if dirpath:
            self.data_dir.set(dirpath)

    def lock_ui(self):
        for w in (self.tags_dir_browse_btn, self.extract_btn,
                  self.data_dir_browse_btn):
            w.config(state=tk.DISABLED)

    def unlock_ui(self):
        for w in (self.tags_dir_browse_btn, self.extract_btn,
                  self.data_dir_browse_btn):
            w.config(state=tk.NORMAL)

    def thread_wrapper(self, func, *args, **kwargs):
        if self._running_thread is not None:
            return

        try:
            self.lock_ui()
            func(*args, **kwargs)
            self.unlock_ui()
            self._running_thread = None
        except Exception:
            self.unlock_ui()
            self._running_thread = None
            raise

    def extract(self):
        if self._running_thread is None:
            new_thread = Thread(target=self.thread_wrapper,
                                args=(self.do_extract, ))
            new_thread.daemon = True
            new_thread.start()

    def do_extract(self):
        print('Extracting source files...')
        start = time()
        tags_dir = self.tags_dir.get()
        data_dir = self.data_dir.get()

        for root, dirs, files in os.walk(tags_dir):
            for tag_name in files:
                if self.stop_extraction:
                    print("    Conversion cancelled by user.")
                    return
                elif os.path.splitext(tag_name)[-1].lower() != '.bitmap':
                    continue
                tag_path = os.path.join(root, tag_name)

                source_path = data_dir + tag_path.split(tags_dir)[-1]
                source_path = os.path.splitext(source_path)[0] + ".tga"
                source_dir = os.path.dirname(source_path)

                try:
                    with open(tag_path, 'rb') as f:
                        data = f.read()

                    tag_id = data[36:40]
                    engine_id = data[60:64]

                    # make sure this is a bitmap tag
                    if tag_id == b'bitm' and engine_id == b'blam':
                        dims_off = 64+24
                        size_off = 64+28
                        data_off = 64+108
                        end = ">"
                    elif tag_id == b'mtib' and engine_id == b'!MLB':
                        dims_off = 64+16+24
                        size_off = 64+16+28
                        data_off = 64+16
                        # get the size of the bitmap body from the tbfd structure
                        data_off += unpack("<i", data[data_off-4: data_off])[0]
                        end = "<"
                    else:
                        #print("    This file doesnt appear to be a bitmap tag.")
                        continue

                    width, height = unpack(end+"HH", data[dims_off: dims_off+4])
                    comp_size = unpack(end+"i", data[size_off: size_off+4])[0]
                    data = data[data_off: data_off+comp_size]
                except Exception:
                    #print("    Could not load bitmap tag.")
                    continue

                if not len(data):
                    #print("    No source image to extract.")
                    continue

                try:
                    data_size = unpack(end+"I", data[:4])[0]
                    if not data_size:
                        #print('    Source data is blank.')
                        continue

                    data = bytearray(zlib.decompress(data[4:]))
                except Exception:
                    #print('    Could not decompress data.')
                    continue

                print('Extracting %s' % tag_path.split(tags_dir)[-1].lstrip("/\\"))
                try:
                    if not os.path.isdir(source_dir):
                        os.makedirs(source_dir)
                    with open(source_path, 'wb') as f:
                        a_depth = len(data) // (width*height) - 3

                        head = bytearray(18)
                        pack_into('B',  head, 2,  2)
                        pack_into('<H', head, 12, width)
                        pack_into('<H', head, 14, height)
                        pack_into('B',  head, 16, 32)
                        pack_into('B',  head, 17, 32 + ((a_depth*8)&15))
                        f.write(head)
                        f.write(data)
                except Exception:
                    #print(format_exc())
                    print("    Couldn't make Tga file.")

        print('\nFinished. Took %s seconds' % (time() - start))


if __name__ == "__main__":
    try:
        BitmapSourceExtractorWindow(None).mainloop()
        raise SystemExit(0)
    except Exception:
        print(format_exc())
        input()
