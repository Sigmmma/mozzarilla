import tkinter as tk
import os

from threading import Thread
from time import time
from tkinter.filedialog import askopenfilename, askdirectory
from traceback import format_exc
from os.path import dirname, exists, join, splitext, relpath

from binilla.widgets import BinillaWidget
from binilla.util import get_cwd
from supyr_struct.defs.constants import *
from supyr_struct.defs.util import *

curr_dir = get_cwd(__file__)


class DataExtractionWindow(tk.Toplevel, BinillaWidget):
    tags_dir = ''
    app_root = None
    handler = None
    print_interval = 5

    _extracting = False
    stop_extracting = False
    tag_data_extractors = ()

    listbox_index_to_def_id = ()
    tag_class_fcc_to_ext = ()
    tag_class_ext_to_fcc = ()

    def __init__(self, app_root, *args, **kwargs): 
        self.handler = app_root.handler
        self.app_root = app_root
        kwargs.update(bd=0, highlightthickness=0, bg=self.default_bg_color)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)

        self.tag_data_extractors = getattr(
            self.handler, "tag_data_extractors", None)
        self.tag_class_fcc_to_ext = {k: self.handler.id_ext_map[k].strip(".")
                                     for k in self.handler.id_ext_map}
        self.tag_class_ext_to_fcc = {self.tag_class_fcc_to_ext[k]: k
                                     for k in self.tag_class_fcc_to_ext}
        

        self.title("Tag Data Extractor")
        self.resizable(0, 0)
        self.update()
        try:
            try:
                self.iconbitmap(join(curr_dir, '..', 'mozzarilla.ico'))
            except Exception:
                self.iconbitmap(join(curr_dir, 'icons', 'mozzarilla.ico'))
        except Exception:
            print("Could not load window icon.")

        self.listbox_index_to_def_id = list(sorted(self.tag_data_extractors.keys()))

        # make the tkinter variables
        self.dir_path = tk.StringVar(self, self.handler.tagsdir)
        self.tag_path = tk.StringVar(self)
        self.overwrite = tk.BooleanVar(self)
        self.decode_adpcm = tk.BooleanVar(self)

        # make the frames
        self.options_frame = tk.LabelFrame(
            self, text="Extraction options")
        self.dir_extract_frame = tk.LabelFrame(
            self, text="Directory to extract from")
        self.dir_path_frame = tk.Frame(self.dir_extract_frame)
        self.def_ids_frame = tk.LabelFrame(
            self.dir_extract_frame, text="Select which tag types to extract from")
        self.tag_path_frame = tk.LabelFrame(
            self, text="Tag to extract from")

        self.def_ids_scrollbar = tk.Scrollbar(
            self.def_ids_frame, orient="vertical")
        self.def_ids_listbox = tk.Listbox(
            self.def_ids_frame, selectmode='multiple', highlightthickness=0,
            yscrollcommand=self.def_ids_scrollbar.set, exportselection=False)
        self.def_ids_scrollbar.config(command=self.def_ids_listbox.yview)

        for def_id in self.listbox_index_to_def_id:
            try:
                tag_ext = self.handler.id_ext_map[def_id].split('.')[-1]
            except KeyError:
                # not available with the current tag set
                continue
            self.def_ids_listbox.insert('end', tag_ext)
            self.def_ids_listbox.select_set('end')


        self.overwrite_cbtn = tk.Checkbutton(
            self.options_frame, variable=self.overwrite,
            text="Overwrite existing data files")
        self.decode_adpcm_cbtn = tk.Checkbutton(
            self.options_frame, variable=self.decode_adpcm,
            text="Decode Xbox ADPCM audio")

        self.dir_path_entry = tk.Entry(
            self.dir_path_frame, textvariable=self.dir_path)
        self.dir_browse_button = tk.Button(
            self.dir_path_frame, text="Browse", command=self.dir_browse)
        self.dir_extract_button = tk.Button(
            self.dir_path_frame, text="Extract", command=self.dir_extract)

        self.tag_path_entry = tk.Entry(
            self.tag_path_frame, textvariable=self.tag_path)
        self.tag_browse_button = tk.Button(
            self.tag_path_frame, text="Browse", command=self.tag_browse)
        self.tag_extract_button = tk.Button(
            self.tag_path_frame, text="Extract", command=self.tag_extract)
        
        self.cancel_extraction_button = tk.Button(
            self, text="Cancel extraction", command=self.cancel_extraction)


        self.overwrite_cbtn.pack(fill="x", anchor="nw", side="left")
        self.decode_adpcm_cbtn.pack(fill="x", anchor="nw")


        self.def_ids_listbox.pack(side='left', fill="both", expand=True)
        self.def_ids_scrollbar.pack(side='left', fill="y")


        self.dir_path_entry.pack(
            padx=(4, 0), pady=2, side='left', expand=True, fill='x')
        self.dir_browse_button.pack(padx=(0, 4), pady=2, side='left')
        self.dir_extract_button.pack(padx=(0, 4), pady=2, side='left')

        self.tag_path_entry.pack(
            padx=(4, 0), pady=2, side='left', expand=True, fill='x')
        self.tag_browse_button.pack(padx=(0, 4), pady=2, side='left')
        self.tag_extract_button.pack(padx=(0, 4), pady=2, side='left')

        self.dir_path_frame.pack(fill='x', padx=1)
        self.def_ids_frame.pack(fill='x', padx=1, expand=True)

        self.options_frame.pack(fill='x', padx=1)
        self.dir_extract_frame.pack(fill='x', padx=1)
        self.tag_path_frame.pack(fill='x', padx=1)
        self.cancel_extraction_button.pack(fill='both', padx=1, expand=True)

        self.transient(app_root)
        self.apply_style()
        self.update()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry("%sx%s" % (w, h))
        self.minsize(width=w, height=h)

    def dir_browse(self):
        if self._extracting:
            return
        dirpath = askdirectory(
            initialdir=self.dir_path.get(),
            parent=self, title="Select the directory of tags to extract from")

        if not dirpath:
            return

        dirpath = sanitize_path(dirpath)
        if not dirpath.endswith(PATHDIV):
            dirpath += PATHDIV

        self.app_root.last_load_dir = dirname(dirpath)
        tags_dir = self.handler.tagsdir
        if not (is_in_dir(dirpath, tags_dir, 0) or
                join(dirpath.lower()) == join(tags_dir.lower())):
            print("Specified directory is not located within the tags directory.")
            return

        self.app_root.last_load_dir = dirname(dirpath)
        self.dir_path.set(dirpath)

    def tag_browse(self):
        if self._extracting:
            return
        filetypes = [('All', '*')]

        for def_id in sorted(self.tag_data_extractors.keys()):
            if def_id in self.tag_class_fcc_to_ext:
                filetypes.append(
                    (def_id, "." + self.tag_class_fcc_to_ext[def_id]))

        fp = askopenfilename(
            initialdir=self.app_root.last_load_dir, filetypes=filetypes,
            parent=self, title="Select a tag to extract from")

        if not fp:
            return

        fp = sanitize_path(fp)
        self.app_root.last_load_dir = dirname(fp)
        tags_dir = self.handler.tagsdir
        if not is_in_dir(fp, tags_dir, 0):
            print("Specified tag is not located within the tags directory.")
            return

        self.app_root.last_load_dir = dirname(fp)
        self.tag_path.set(fp)

    def destroy(self):
        try:
            self.app_root.tool_windows.pop(self.window_name, None)
        except AttributeError:
            pass
        self.stop_extracting = True
        tk.Toplevel.destroy(self)

    def cancel_extraction(self):
        self.stop_extracting = True

    def get_tag(self, tag_path):
        handler = self.handler
        def_id = handler.get_def_id(tag_path.lstrip("./\\"))
        try:
            tag = handler.get_tag(tag_path, def_id)
        except (KeyError, LookupError):
            tag = None

        try:
            if tag is None:
                return handler.build_tag(filepath=join(self.tags_dir, tag_path))
        except Exception:
            pass
        return tag

    def dir_extract(self):
        if self._extracting:
            return
        try: self.extract_thread.join(1.0)
        except Exception: pass
        self.extract_thread = Thread(target=self._dir_extract, daemon=True)
        self.extract_thread.start()

    def tag_extract(self):
        if self._extracting:
            return
        try: self.extract_thread.join(1.0)
        except Exception: pass
        self.extract_thread = Thread(target=self._tag_extract, daemon=True)
        self.extract_thread.start()

    def _dir_extract(self):
        self._extracting = True
        self.stop_extracting = False
        try:
            self.do_dir_extract()
        except Exception:
            print(format_exc())
        self._extracting = False

    def _tag_extract(self):
        self._extracting = True
        self.stop_extracting = False
        try:
            self.do_tag_extract()
        except Exception:
            print(format_exc())
        self._extracting = False

    def do_dir_extract(self):
        tags_dir = self.tags_dir = self.handler.tagsdir
        if not tags_dir.endswith(PATHDIV):
            tags_dir += PATHDIV

        tags_path = sanitize_path(self.dir_path.get())
        data_path = join(dirname(dirname(tags_dir)), "data")

        if not (is_in_dir(tags_path, tags_dir, 0) or
                join(tags_path.lower()) == join(tags_dir.lower())):
            print("Specified directory is not located within the tags directory.")
            return

        settings = dict(out_dir=data_path, overwrite=self.overwrite.get(),
                        decode_adpcm=self.decode_adpcm.get(), engine="yelo")
        print("Beginning tag data extracton in:\t%s" % tags_dir)

        s_time = time()
        c_time = s_time
        p_int = self.print_interval

        all_tag_paths = {self.listbox_index_to_def_id[int(i)]: [] for i in
                         self.def_ids_listbox.curselection()}

        print("Locating tags...")

        for root, directories, files in os.walk(tags_path):
            if not root.endswith(PATHDIV):
                root += PATHDIV

            root = relpath(root, tags_dir)
            for filename in files:
                filepath = join(sanitize_path(root), filename)

                if time() - c_time > p_int:
                    c_time = time()
                    print(' '*4 + filepath)
                    self.app_root.update_idletasks()

                if self.stop_extracting:
                    print('Tag data extraction cancelled.\n')
                    return

                tag_paths = all_tag_paths.get(
                    self.tag_class_ext_to_fcc.get(
                        splitext(filename)[-1].lower()[1: ]))

                if tag_paths is not None:
                    tag_paths.append(filepath)

        for def_id in sorted(all_tag_paths):
            extractor = self.tag_data_extractors[def_id]
            if self.stop_extracting:
                print('Tag data extraction cancelled.\n')
                return

            print("Extracting %s" % def_id)
            for filepath in all_tag_paths[def_id]:
                if self.stop_extracting:
                    print('Tag data extraction cancelled.\n')
                    return

                print(' '*4 + filepath)
                self.extract(filepath, extractor, **settings)

        print("Extraction completed.\n")

    def do_tag_extract(self):
        tags_dir = self.tags_dir = self.handler.tagsdir
        tag_path = sanitize_path(self.tag_path.get())
        if not tags_dir.endswith(PATHDIV):
            tags_dir += PATHDIV

        def_id = self.tag_class_ext_to_fcc.get(splitext(tag_path)[-1].lower()[1:])
        if def_id is None or def_id not in self.tag_data_extractors:
            print("Cannot extract data from this kind of tag.")
            return
        elif not is_in_dir(tag_path, tags_dir, 0):
            print("Specified tag is not located within the tags directory.")
            return

        print("Extracting %s" % tag_path)
        self.extract(relpath(tag_path, tags_dir),
                     self.tag_data_extractors[def_id],
                     out_dir=join(dirname(dirname(tags_dir)), "data"),
                     overwrite=self.overwrite.get(), engine="yelo",
                     decode_adpcm=self.decode_adpcm.get()
                     )

        print("Extraction completed.\n")

    def extract(self, tag_path, extractor, **settings):
        if extractor is None:
            print("No extractor defined for this kind of tag.")
            return

        tag = self.get_tag(tag_path)
        if tag is None:
            print((' '*8) + "Could not load tag.")
            return

        try:
            result = extractor(tag.data.tagdata, tag_path, **settings)
        except Exception:
            result = format_exc()

        if result:
            print(result)
