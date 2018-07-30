import os
import zlib

from os.path import dirname, join, relpath, basename, isfile, exists
from tkinter.filedialog import askdirectory

from supyr_struct.defs.util import sanitize_path, is_in_dir
from reclaimer.jms import read_jms, JmsModel, merge_jms_models
from reclaimer.hek.defs.objs.matrices import quaternion_to_matrix, Matrix


def model_from_jms(app, models_dir="", tag_path=""):
    load_dir = app.jms_load_dir
    tags_dir = app.tags_dir
    data_dir = app.data_dir
    if not tags_dir:
        tags_dir = ""
    if not data_dir:
        data_dir = ""

    if not load_dir:
        load_dir = data_dir

    if not models_dir:
        src_dir = askdirectory(
            initialdir=load_dir, parent=app,
            title="Select folder containing the 'models' folder to compile")

        src_dir = sanitize_path(src_dir)
        models_dir = join(src_dir, "models", "")
        if not src_dir:
            return
        elif not exists(models_dir):
            print("The selected folder does not contain a 'models' folder.")
            return
        elif not is_in_dir(src_dir, data_dir):
            print("The selected folder is not in the data directory.")
            return

        if not tag_path:
            tag_path = join(src_dir, basename(src_dir) + ".gbxmodel")
            tag_path = join(tags_dir, relpath(tag_path, data_dir))


    if not models_dir:
        return


    fps = []
    for _, __, files in os.walk(models_dir):
        for fname in files:
            if fname.lower().endswith(".jms"):
                fps.append(join(models_dir, fname))

        break


    if not fps:
        print("    No valid jms files found in the folder.")
        return


    jms_datas = []
    print("    Parsing jms files...")
    if app: app.update()
    for fp in fps:
        try:
            print("      %s" % fp)
            if app: app.update()
            with open(fp, "r") as f:
                jms_datas.append(read_jms(f.read(), '',
                                          basename(fp).split('.')[0]))
        except Exception:
            print("        Could not parse jms file.")
            if app: app.update()

    if not jms_datas:
        return


    print("    Verifying integrity of jms files and merging them...")
    if app: app.update()
    merged_jms_data = JmsModel()
    all_errors = merge_jms_models(merged_jms_data, *jms_datas)

    if all_errors:
        for jms_name in sorted(all_errors):
            errors = all_errors[jms_name]
            print("    Errors in '%s'" % jms_name)
            for error in errors:
                print("        " + error)

            if app: app.update()

        print("    Cannot compile model.")
        return


    first_crc = None
    for jms_data in jms_datas:
        if first_crc is None:
            first_crc = jms_data.node_list_checksum
        elif first_crc != jms_data.node_list_checksum:
            print("    Warning, not all node list checksums match.")
            break


    updating = isfile(tag_path)
    if updating:
        print("    Updating existing gbxmodel tag.")
        tag_load_path = (tag_path, )
    else:
        print("    Creating new gbxmodel tag.")
        tag_load_path = ""

    if app: app.update()


    # make the tag window
    window = app.load_tags(filepaths=tag_load_path, def_id='mod2')
    if not window:
        return

    window = window[0]
    mod2_tag = window.tag

    window.is_new_tag = False
    mod2_tag.filepath = tag_path
    mod2_tag.rel_filepath = relpath(tag_path, tags_dir)

    tagdata = mod2_tag.data.tagdata




    mod2_tag.calc_internal_data()

    # reload the window to display the newly entered info
    window.reload()
    app.update_tag_window_title(window)
    #app.save_tag()
