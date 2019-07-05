import os

from struct import unpack
from tkinter.filedialog import askopenfilenames
from traceback import format_exc

from reclaimer.bitmaps.bitmap_decompilation import extract_bitmap_tiff_data
from reclaimer.bitmaps.bitmap_compilation import add_bitmap_to_bitmap_tag,\
     compile_bitmap_from_dds_files

from supyr_struct.defs.constants import PATHDIV
from supyr_struct.util import sanitize_path


def bitmap_from_dds(app, fps=()):
    load_dir = app.bitmap_load_dir
    data_dir = app.data_dir
    if not data_dir:
        data_dir = ""
    if not load_dir:
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

        compile_bitmap_from_dds_files(window.tag, (fp, ))
        window.update_title(fp.split(PATHDIV)[-1])
    
        # reload the window to display the newly entered info
        window.reload()
        # prompt the user to save the tag somewhere
        app.save_tag_as()


def bitmap_from_multiple_dds(app, fps=()):
    load_dir = app.bitmap_load_dir
    data_dir = app.data_dir
    if not data_dir:
        data_dir = ""
    if not load_dir:
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
        window.update_title(fp.split(PATHDIV)[-1])
        app.bitmap_load_dir = os.path.dirname(fp)
        break

    compile_bitmap_from_dds_files(window.tag, fps)

    # reload the window to display the newly entered info
    window.reload()
    # prompt the user to save the tag somewhere
    app.save_tag_as()


def bitmap_from_bitmap_source(app, e=None):
    load_dir = app.bitmap_load_dir
    if not load_dir:
        load_dir = app.last_data_load_dir
    
    fps = askopenfilenames(initialdir=load_dir, parent=app,
                           filetypes=(("bitmap", "*.bitmap"), ("All", "*")),
                           title="Select a bitmap tag to get the source tiff")

    if not fps:
        return

    app.bitmap_load_dir = os.path.dirname(fps[0])

    print('Creating bitmap from uncompressed source image of these bitmaps:')
    for fp in fps:
        fp = sanitize_path(fp)
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
        window.tag.filepath = os.path.join(
            app.tags_dir + window.tag.rel_filepath)

        app.update_tag_window_title(window)

        # reload the window to display the newly entered info
        window.reload()
        # prompt the user to save the tag somewhere
        app.save_tag_as()
