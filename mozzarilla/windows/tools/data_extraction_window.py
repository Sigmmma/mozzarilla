#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

import os
import sys
import tkinter as tk

from pathlib import Path
from supyr_struct.util import path_split, is_in_dir
from threading import Thread
from time import time
from traceback import format_exc

from binilla.widgets.binilla_widget import BinillaWidget
from binilla.windows.filedialog import askopenfilename, askdirectory

from reclaimer.halo_script.hsc import get_h1_scenario_script_object_type_strings

from mozzarilla import editor_constants as e_c


class DataExtractionWindow(tk.Toplevel, BinillaWidget):
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
        BinillaWidget.__init__(self, app_root, *args, **kwargs)

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
            self.iconbitmap(e_c.MOZZ_ICON_PATH)
        except Exception:
            print("Could not load window icon.")

        self.listbox_index_to_def_id = list(sorted(
            k for k in self.tag_data_extractors.keys()
            if k in self.tag_class_fcc_to_ext))

        # make the tkinter variables
        self.dir_path = tk.StringVar(self, self.handler.tagsdir)
        self.tag_path = tk.StringVar(self)
        self.overwrite = tk.BooleanVar(self)
        self.decode_adpcm = tk.BooleanVar(self)
        self.use_scenario_names_in_scripts = tk.BooleanVar(self)

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
        self.use_scenario_names_in_scripts_cbtn = tk.Checkbutton(
            self.options_frame, variable=self.use_scenario_names_in_scripts,
            text="Use scenario names in scripts")

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
        self.use_scenario_names_in_scripts_cbtn.pack(fill="x", anchor="nw", side="left")


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

        self.app_root.last_load_dir = dirpath
        if not is_in_dir(dirpath, self.handler.tagsdir):
            print('Directory "%s" is not located inside tags dir: "%s"'
                  % (dirpath, self.handler.tagsdir))
            return

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
            initialdir=str(self.app_root.last_load_dir), filetypes=filetypes,
            parent=self, title="Select a tag to extract from")

        if not fp:
            return

        fp = Path(fp)
        self.app_root.last_load_dir = fp.parent
        if not is_in_dir(fp, self.handler.tagsdir):
            print("Tag %s is not located in tags directory %s"
                  % (fp, self.handler.tagsdir))
            return

        self.app_root.last_load_dir = fp.parent
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
        def_id = self.handler.get_def_id(tag_path)
        try:
            tag = self.handler.get_tag(tag_path, def_id)
        except (KeyError, LookupError):
            tag = None

        try:
            if tag is None:
                return self.handler.build_tag(
                    filepath=self.handler.tagsdir.joinpath(tag_path))
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
        tags_path = self.dir_path.get()
        data_path = self.handler.tagsdir.parent.joinpath("data")

        if not is_in_dir(tags_path, self.handler.tagsdir):
            print("Directory %s is not located inside tags dir: %s"
                  % (tags_path, self.handler.tagsdir))
            return

        settings = dict(out_dir=str(data_path), overwrite=self.overwrite.get(),
                        decode_adpcm=self.decode_adpcm.get(), engine="yelo")

        print("Beginning tag data extracton in:\t%s" % self.handler.tagsdir)

        s_time = time()
        c_time = s_time
        p_int = self.print_interval

        all_tag_paths = {self.listbox_index_to_def_id[int(i)]: [] for i in
                         self.def_ids_listbox.curselection()}

        print("Locating tags...")

        for root, directories, files in os.walk(tags_path):
            root = Path(root)
            try:
                root = root.relative_to(self.handler.tagsdir)
            except ValueError:
                continue

            for filename in files:
                filepath = root.joinpath(filename)

                if time() - c_time > p_int:
                    c_time = time()
                    print(' '*4, filepath, sep="")
                    self.app_root.update_idletasks()

                if self.stop_extracting:
                    print('Tag data extraction cancelled.\n')
                    return

                tag_paths = all_tag_paths.get(
                    self.tag_class_ext_to_fcc.get(
                        filepath.suffix[1:].lower()))

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

                print(' '*4, filepath, sep="")
                self.extract(filepath, extractor, **settings)

        print("Extraction completed.\n")

    def do_tag_extract(self):
        tag_path = self.tag_path.get()

        def_id = self.tag_class_ext_to_fcc.get(Path(tag_path).suffix[1:].lower())
        if def_id is None or def_id not in self.tag_data_extractors:
            print("Cannot extract data from this kind of tag.")
            return
        else:
            if not is_in_dir(tag_path, self.handler.tagsdir):
                print("Tag %s is not located within tags directory: %s"
                      % (tag_path, self.handler.tagsdir))
                return

        print("Extracting %s" % tag_path)
        self.extract(os.path.relpath(tag_path, str(self.handler.tagsdir)),
                     self.tag_data_extractors[def_id],
                     out_dir=str(Path(path_split(self.handler.tagsdir, "tags")).joinpath("data")),
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
            if (self.use_scenario_names_in_scripts.get() and
                tag.data[0].tag_class.enum_name == "scenario"):
                settings["hsc_node_strings_by_type"] = get_h1_scenario_script_object_type_strings(tag.data.tagdata)
        except Exception:
            print(format_exc())

        try:
            result = extractor(
                tag.data.tagdata, str(tag_path), byteswap_pcm_samples=True,
                **settings)
        except Exception:
            result = format_exc()

        if result:
            print(result)
