import os

from tkinter.filedialog import askopenfilename
from traceback import format_exc

from reclaimer.model.jms import read_jms
from reclaimer.physics.physics_compilation import compile_physics

from supyr_struct.util import sanitize_path


def physics_from_jms(app, fp=None):
    load_dir = app.jms_load_dir
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
            filetypes=(("JMS model", "*.jms"), ("All", "*")),
            title="Select jms file to turn into a physics tag")

    if not fp:
        return

    try:
        fp = sanitize_path(fp)
        app.jms_load_dir = os.path.dirname(fp)

        print("Creating physics from this jms file:")
        print("    %s" % fp)
        with open(fp, "r") as f:
            jms_model = read_jms(f.read(), "regions")
    except Exception:
        print(format_exc())
        print("    Could not parse jms file")
        return

    tag_path = os.path.dirname(os.path.dirname(os.path.relpath(fp, data_dir)))
    rel_tagpath = os.path.join(tag_path, "%s.physics" % os.path.basename(tag_path))
    if not tag_path.startswith(".."):
        tag_path = os.path.join(tags_dir, rel_tagpath)
    else:
        tag_path = ""

    updating = False
    if os.path.isfile(tag_path):
        print("    Updating existing physics tag.")
        tag_load_path = (tag_path, )
        updating = True
    else:
        print("    Creating new physics tag.")
        tag_load_path = ""

    # make the tag window
    window = app.load_tags(filepaths=tag_load_path, def_id='phys')
    if not window:
        return
    window = window[0]
    window.is_new_tag = False
    window.tag.filepath = tag_path
    window.tag.rel_filepath = rel_tagpath

    compile_physics(window.tag, jms_model.markers, updating)

    # reload the window to display the newly entered info
    window.reload()
    app.update_tag_window_title(window)
    if not os.path.isfile(tag_path):
        # save the tag if it doesnt already exist
        app.save_tag()
