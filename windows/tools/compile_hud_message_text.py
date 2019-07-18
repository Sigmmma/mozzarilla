import os

from tkinter.filedialog import askopenfilename
from traceback import format_exc

from supyr_struct.util import sanitize_path
from reclaimer.strings.strings_compilation import compile_hud_message_text


def hud_message_text_from_hmt(app, fp=None):
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
            filetypes=(("HUD messages", "*.hmt"), ("All", "*")),
            title="Select hmt file to turn into a hud_message_text tag")

    if not fp:
        return

    try:
        fp = sanitize_path(fp)
        app.last_data_load_dir = os.path.dirname(fp)

        print("Creating hud_message_text from this hmt file:")
        print("    %s" % fp)
        with open(fp, "r", encoding="utf-16-le") as f:
            hmt_string_data = f.read()
    except Exception:
        print(format_exc())
        print("    Could not load hmt file.")
        return

    tag_path = os.path.dirname(os.path.relpath(fp, data_dir))
    rel_tagpath = os.path.join(tag_path, "hud messages.hud_message_text")
    if not tag_path.startswith(".."):
        tag_path = os.path.join(tags_dir, rel_tagpath)
    else:
        tag_path = ""

    if os.path.isfile(tag_path):
        print("    Updating existing hud_message_text tag.")
        tag_load_path = (tag_path, )
    else:
        print("    Creating new hud_message_text tag.")
        tag_load_path = ""

    # make the tag window
    window = app.load_tags(filepaths=tag_load_path, def_id='hmt ')
    if not window:
        return

    window = window[0]
    window.is_new_tag = False
    window.tag.filepath = tag_path
    window.tag.rel_filepath = rel_tagpath

    error = compile_hud_message_text(window.tag, hmt_string_data)

    # reload the window to display the newly entered info
    window.reload()
    app.update_tag_window_title(window)
    if error:
        print("    Errors occurred while compiling. " +
              "Tag will not be automatically saved.")
        window.is_new_tag = True
    elif not os.path.isfile(tag_path):
        # save the tag if it doesnt already exist
        app.save_tag()
