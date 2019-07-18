import os

from tkinter.filedialog import askopenfilename
from traceback import format_exc

from supyr_struct.util import sanitize_path

from reclaimer.strings.strings_compilation import compile_unicode_string_list,\
     compile_string_list


def strings_from_txt(app, fp=None):
    load_dir = app.last_data_load_dir
    tags_dir = app.tags_dir
    data_dir = app.data_dir
    if not tags_dir:
        tags_dir = ""
    if not data_dir:
        data_dir = ""

    if not load_dir:
        load_dir = data_dir

    if not fp:
        fp = askopenfilename(
            initialdir=load_dir, parent=app,
            filetypes=(("strings list", "*.txt"), ("All", "*")),
            title="Select hmt file to turn into a (unicode_)string_list tag")

    if not fp:
        return

    try:
        fp = sanitize_path(fp)
        app.last_data_load_dir = os.path.dirname(fp)
        tag_ext = "unicode_string_list"
        tag_cls = "ustr"

        with open(fp, "rb") as f:
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

        with open(fp, "r", encoding=encoding) as f:
            string_data = f.read()
            if "utf-16" in encoding:
                string_data = string_data.lstrip('\ufeff').lstrip('\ufffe')

    except Exception:
        print(format_exc())
        print("    Could not parse file.")
        return

    tag_path = ""
    tag_load_path = ""
    rel_tagpath = os.path.splitext(os.path.relpath(fp, data_dir))[0] + "." + tag_ext
    if not rel_tagpath.startswith(".."):
        tag_path = os.path.join(tags_dir, rel_tagpath)

    if os.path.isfile(tag_path):
        tag_load_path = (tag_path, )

    # make the tag window
    window = app.load_tags(filepaths=tag_load_path, def_id=tag_cls)
    if not window:
        return

    window = window[0]
    tag = window.tag

    window.is_new_tag = True
    tag.filepath = tag_path
    tag.rel_filepath = rel_tagpath

    if 'utf-16' in encoding:
        compile_unicode_string_list(tag, string_data)
    else:
        compile_string_list(tag, string_data)

    # reload the window to display the newly entered info
    window.reload()
    app.update_tag_window_title(window)
    if not os.path.isfile(tag_path):
        # save the tag if it doesnt already exist
        app.save_tag()
