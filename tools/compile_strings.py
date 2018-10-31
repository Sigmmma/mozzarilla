import zlib

from os.path import dirname, join, relpath, basename, isfile, splitext
from tkinter.filedialog import askopenfilename
from traceback import format_exc

from supyr_struct.defs.util import sanitize_path
from supyr_struct.defs.constants import PATHDIV


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
        app.last_data_load_dir = dirname(fp)
        tag_ext = "unicode_string_list"
        tag_cls = "ustr"
        max_str_len = 32768
        with open(fp, "rb") as f:
            data = f.read(2) + b'\x00\x00'
            print(data[0], data[1])
            if data[0] == 255 and data[1] == 254:
                encoding="utf-16-le"
            elif data[1] == 254 and data[0] == 255:
                encoding="utf-16-be"
            else:
                tag_ext = "string_list"
                tag_cls = "str#"
                max_str_len = 4096
                encoding = "latin-1"

        print("Creating %s from this txt file:" % tag_ext)
        print("    %s" % fp)

        with open(fp, "r", encoding=encoding) as f:
            string_data = f.read().replace("\r\n", "\n").\
                          replace("\n\r", "\n").replace("\r", "\n")
            if "utf-16" in encoding:
                string_data = string_data.lstrip('\ufeff').lstrip('\ufffe')

            strings = string_data.split("\n###END-STRING###\n")
            if len(strings) > 32767:
                print("    WARNING: Too many strings. Truncating to 32767.")
                del strings[32768: ]

        for i in range(len(strings)):
            string = strings[i]
            if len(strings) > max_str_len:
                print(("    WARNING: String %s is too long." +
                       " Truncating to %s characters") % (i, max_str_len))
                strings[i] = string[max_str_len: ]

    except Exception:
        print(format_exc())
        print("    Could not load parse file.")
        return

    tag_path = ""
    tag_load_path = ""
    rel_tagpath = splitext(relpath(fp, data_dir))[0] + "." + tag_ext
    if not rel_tagpath.startswith(".."):
        tag_path = join(tags_dir, rel_tagpath)

    if isfile(tag_path):
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

    tag_strings = tag.data.tagdata.strings.STEPTREE
    del tag_strings[:]

    for string in strings:
        tag_strings.append()
        tag_string = tag_strings[-1]
        tag_string.data = string

    # reload the window to display the newly entered info
    window.reload()
    app.update_tag_window_title(window)
    if not isfile(tag_path):
        # save the tag if it doesnt already exist
        app.save_tag()
