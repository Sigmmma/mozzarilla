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

from reclaimer.model.jms import read_jms
from reclaimer.physics.physics_compilation import compile_physics
from supyr_struct.util import is_path_empty
from binilla.windows.filedialog import askopenfilename


def physics_from_jms(app, fp=None):
    load_dir = app.jms_load_dir
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
            filetypes=(("JMS model", "*.jms"), ("All", "*")),
            title="Select jms file to turn into a physics tag")

    fp = Path(fp)
    if is_path_empty(fp):
        return

    try:
        app.jms_load_dir = fp.parent
        with fp.open("r") as f:
            jms_model = read_jms(f.read(), "regions")
    except Exception:
        print(format_exc())
        print("    Could not parse jms file")
        return

    try:
        rel_filepath = fp.relative_to(data_dir).parent.parent
        rel_filepath = rel_filepath.joinpath(rel_filepath.stem + ".physics")
    except ValueError:
        rel_filepath = Path("unnamed.physics")

    tag_path = Path("")
    if not is_path_empty(rel_filepath):
        tag_path = tags_dir.joinpath(rel_filepath)

    # make the tag window
    window = app.load_tags(
        filepaths=(tag_path, ) if tag_path.is_file() else "",
        def_id='phys')
    if not window:
        return

    window = window[0]
    window.is_new_tag = False
    window.tag.filepath = tag_path
    window.tag.rel_filepath = rel_filepath

    compile_physics(window.tag, jms_model.markers, tag_path.is_file())

    # reload the window to display the newly entered info
    window.reload()
    app.update_tag_window_title(window)
    if not tag_path.is_file():
        # save the tag if it doesnt already exist
        app.save_tag()
