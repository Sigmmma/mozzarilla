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
from struct import unpack
from traceback import format_exc

from reclaimer.bitmaps.bitmap_decompilation import extract_bitmap_tiff_data
from reclaimer.bitmaps.bitmap_compilation import add_bitmap_to_bitmap_tag,\
     compile_bitmap_from_dds_files
from supyr_struct.util import is_path_empty
from binilla.windows.filedialog import askopenfilenames


def bitmap_from_dds(app, fps=()):
    load_dir = app.bitmap_load_dir
    data_dir = app.data_dir
    if is_path_empty(data_dir):
        data_dir = Path("")

    if is_path_empty(load_dir):
        load_dir = data_dir

    if not fps:
        fps = askopenfilenames(
            initialdir=load_dir, parent=app,
            filetypes=(("DDS image", "*.dds"), ("All", "*")),
            title="Select dds files to turn into bitmap tags")
        fps = [fp for fp in fps if fp.lower().endswith(".dds")]

    if not fps:
        return

    print("Creating bitmaps from dds files")
    for fp in sorted(fps):
        # make the tag window
        window = app.load_tags(filepaths='', def_id='bitm')
        if not window:
            return

        window = window[0]
        window.is_new_tag = True

        compile_bitmap_from_dds_files(window.tag, (Path(fp), ))
        window.update_title(list(Path(fp).parts)[-1])

        # reload the window to display the newly entered info
        window.reload()
        # prompt the user to save the tag somewhere
        app.save_tag_as()


def bitmap_from_multiple_dds(app, fps=()):
    load_dir = app.bitmap_load_dir
    data_dir = app.data_dir
    if is_path_empty(data_dir):
        data_dir = Path("")
    if is_path_empty(load_dir):
        load_dir = data_dir

    if not fps:
        fps = askopenfilenames(
            initialdir=load_dir, parent=app,
            filetypes=(("DDS image", "*.dds"), ("All", "*")),
            title="Select dds files to turn into a single bitmap tag")
        fps = [fp for fp in fps if fp.lower().endswith(".dds")]

    if not fps:
        return

    # make the tag window
    window = app.load_tags(filepaths='', def_id='bitm')
    if not window:
        return

    print("Creating bitmap from dds files")
    window = window[0]
    window.is_new_tag = True

    fps = sorted(fps)

    for fp in fps:
        pure_path = Path(fp)
        window.update_title(list(pure_path.parts)[-1])
        app.bitmap_load_dir = pure_path.parent
        break

    compile_bitmap_from_dds_files(window.tag, fps)

    # reload the window to display the newly entered info
    window.reload()
    # prompt the user to save the tag somewhere
    app.save_tag_as()


def bitmap_from_bitmap_source(app, e=None):
    load_dir = app.bitmap_load_dir
    if is_path_empty(load_dir):
        load_dir = app.last_data_load_dir

    fps = askopenfilenames(initialdir=load_dir, parent=app,
                           filetypes=(("bitmap", "*.bitmap"), ("All", "*")),
                           title="Select a bitmap tag to get the source tiff")

    if not fps:
        return

    app.bitmap_load_dir = os.path.dirname(fps[0])

    print('Creating bitmap from uncompressed source image of these bitmaps:')
    for fp in fps:
        print("  %s" % fp)

        width, height, pixels = extract_bitmap_tiff_data(fp)
        if not pixels:
            continue

        # make the tag window
        try:
            window = app.load_tags(filepaths='', def_id='bitm')
        except LookupError:
            print('    Could not make a new bitmap. Change the tag set.')
        if not window:
            continue

        window = window[0]
        window.is_new_tag = True

        add_bitmap_to_bitmap_tag(
            window.tag, width, height, 1, "texture_2d", "a8r8g8b8", 0, pixels)

        window.tag.rel_filepath = "untitled%s.bitmap" % app.untitled_num
        window.tag.filepath = app.tags_dir.joinpath(window.tag.rel_filepath)

        app.update_tag_window_title(window)

        # reload the window to display the newly entered info
        window.reload()
        # prompt the user to save the tag somewhere
        app.save_tag_as()
