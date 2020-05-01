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

from reclaimer.strings.strings_compilation import compile_hud_message_text
from supyr_struct.util import is_path_empty
from binilla.windows.filedialog import askopenfilename

def hacky_detect_encoding(fp):
    fp = Path(fp)
    with fp.open("rb") as f:
        data = f.read(2)

    # Check if the file contains any of the two utf-16 BOMs
    if data[0] == 255 and data[1] == 254:
        encoding = "utf-16-le"
    elif data[1] == 254 and data[0] == 255:
        encoding = "utf-16-be"
    else:
        # If not we default to latin-1
        with fp.open("rb") as f:
            data = f.read()
            encoding = "latin-1"

            # But, if we find a null byte while checking every other byte,
            # we assume utf-16 without BOM
            for i in range(1, len(data), 2):
                if data[i] == 0:
                    encoding = 'utf-16-le'
                    break

    return encoding

def hud_message_text_from_hmt(app, fp=None):
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
            filetypes=(("HUD messages", "*.hmt"), ("All", "*")),
            title="Select hmt file to turn into a hud_message_text tag")

    fp = Path(fp)
    if is_path_empty(fp):
        return

    try:
        app.last_data_load_dir = fp.parent

        print("Creating hud_message_text from this hmt file:")
        print("    %s" % fp)

        with fp.open("r", encoding=hacky_detect_encoding(fp)) as f:
            hmt_string_data = f.read()

    except Exception:
        print(format_exc())
        print("    Could not load hmt file.")
        return

    try:
        rel_filepath = fp.relative_to(data_dir)
    except ValueError:
        rel_filepath = Path("hud messages")

    rel_filepath = rel_filepath.with_suffix(".hud_message_text")

    tag_path = Path("")
    if not is_path_empty(rel_filepath):
        tag_path = tags_dir.joinpath(rel_filepath)

    # make the tag window
    window = app.load_tags(
        filepaths=(tag_path, ) if tag_path.is_file() else "",
        def_id='hmt ')
    if not window:
        return

    window = window[0]
    window.is_new_tag = False
    window.tag.filepath = tag_path
    window.tag.rel_filepath = rel_filepath

    error = compile_hud_message_text(window.tag, hmt_string_data)

    # reload the window to display the newly entered info
    window.reload()
    app.update_tag_window_title(window)
    if error:
        print("    Errors occurred while compiling. " +
              "Tag will not be automatically saved.")
        window.is_new_tag = True
    elif not tag_path.is_file():
        # save the tag if it doesnt already exist
        app.save_tag()
