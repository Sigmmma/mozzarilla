#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

import os

from pathlib import Path
from traceback import format_exc

from reclaimer.strings.strings_compilation import compile_unicode_string_list,\
     compile_string_list
from supyr_struct.util import is_path_empty
from binilla.windows.filedialog import askopenfilename


def strings_from_txt(app, fp=None):
    load_dir = app.last_data_load_dir
    tags_dir = app.tags_dir
    data_dir = app.data_dir
    if is_path_empty(tags_dir):
        tags_dir = Path("")
    if is_path_empty(data_dir):
        data_dir = Path("")

    if is_path_empty(load_dir):
        load_dir = data_dir

    if is_path_empty(fp):
        fp = askopenfilename(
            initialdir=load_dir, parent=app,
            filetypes=(("strings list", "*.txt"), ("All", "*")),
            title="Select hmt file to turn into a (unicode_)string_list tag")

    fp = Path(fp)
    if is_path_empty(fp):
        return

    try:
        app.last_data_load_dir = fp.parent
        tag_ext = "unicode_string_list"
        tag_cls = "ustr"

        with fp.open("rb") as f:
            data = f.read(2)

        if data[0] == 255 and data[1] == 254:
            encoding = "utf-16-le"
        elif data[1] == 254 and data[0] == 255:
            encoding = "utf-16-be"
        else:
            encoding = "latin-1"
            tag_ext = "string_list"
            tag_cls = "str#"

        print("Creating %s from this txt file:" % tag_ext)
        print("    %s" % fp)

        with fp.open("r", encoding=encoding) as f:
            string_data = f.read()
            if "utf-16" in encoding:
                string_data = string_data.lstrip('\ufeff').lstrip('\ufffe')

    except Exception:
        print(format_exc())
        print("    Could not parse file.")
        return

    try:
        rel_filepath = fp.relative_to(data_dir)
    except ValueError:
        rel_filepath = Path("strings")

    rel_filepath = rel_filepath.with_suffix("." + tag_ext)

    tag_path = Path("")
    if not is_path_empty(rel_filepath):
        tag_path = tags_dir.joinpath(rel_filepath)

    # make the tag window
    window = app.load_tags(
        filepaths=(tag_path, ) if tag_path.is_file() else "",
        def_id=tag_cls)
    if not window:
        return

    window = window[0]
    window.is_new_tag = True
    window.tag.filepath = tag_path
    window.tag.rel_filepath = rel_filepath

    if 'utf-16' in encoding:
        compile_unicode_string_list(window.tag, string_data)
    else:
        compile_string_list(window.tag, string_data)

    # reload the window to display the newly entered info
    window.reload()
    app.update_tag_window_title(window)
    if not tag_path.is_file():
        # save the tag if it doesnt already exist
        app.save_tag()
